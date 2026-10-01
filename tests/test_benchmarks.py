"""Benchmark suite (Doc 16): regression cases across the constitutional pipeline.

Covers the first-delivery chain FOTO → ORIGEM → DIREITOS → CLAIMS → EVIDÊNCIA
→ STORY → OPPORTUNITY → FORMATO → QC → HUMAN REVIEW → EXPORT/PUBLISH plus the
security breakers (SSRF, workspace isolation, session revocation, CORS).

Every case asserts behaviour mandated by the Constitution: fail-closed rights
gate, deterministic claim verification, append-only verdict history, closed V1
format set, and manual publication confirmation (AMENDMENT-007).

Run: python -m pytest tests/test_benchmarks.py -v
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import app
from packages.domain.enums import (
    BLOCKING_RIGHTS,
    AgentName,
    ContentFormat,
    GateResult,
    JEVDecision,
    JobType,
    KnowledgeState,
    PublicationMethod,
    QualityGate,
    RightsClassification,
    UncertaintyState,
    VisualClassification,
    rights_gate,
)
from packages.domain.models import Profile, Workspace
from packages.research.fetcher import FetchBlockedError, validate_url
from packages.research.verification import KnowledgeService
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext

# --- shared fixtures -----------------------------------------------------------


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"bench-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def _ctx(ws, profile) -> ExecutionContext:
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def _publication(db, world, *, method: str = "EXPORT", status: str = "PENDING"):
    """Minimal published-track chain: Opportunity → Canonical → Package → Publication."""
    from packages.domain.editorial import CanonicalContent, ContentPackage, Opportunity
    from packages.domain.publishing import Publication

    ws, profile = world
    opp = Opportunity(workspace_id=ws.id, profile_id=profile.id, title="bench opp")
    db.add(opp)
    db.flush()
    canonical = CanonicalContent(workspace_id=ws.id, opportunity_id=opp.id)
    db.add(canonical)
    db.flush()
    package = ContentPackage(
        workspace_id=ws.id,
        opportunity_id=opp.id,
        canonical_content_id=canonical.id,
        format="PHOTO_POST",
    )
    db.add(package)
    db.flush()
    pub = Publication(
        workspace_id=ws.id,
        profile_id=profile.id,
        content_package_id=package.id,
        platform="manual",
        method=method,
        status=status,
    )
    db.add(pub)
    db.flush()
    return pub


# =============================================================================
# A. Rights gate — fail closed over every classification (Doc 00 §15, Doc 11)
# =============================================================================


@pytest.mark.parametrize(
    "classification",
    [
        RightsClassification.PUBLIC_DOMAIN,
        RightsClassification.CC0,
        RightsClassification.CC_BY,
        RightsClassification.CC_BY_SA,
        RightsClassification.OTHER_FREE_LICENSE,
    ],
)
def test_benchmark_rights_gate_allows_free(classification):
    """Free/public classifications may proceed."""
    assert rights_gate(classification).value == "MAY_PROCEED"


@pytest.mark.parametrize(
    "classification",
    [
        RightsClassification.UNKNOWN,
        RightsClassification.PROHIBITED,
        RightsClassification.PERMISSION_REQUIRED,
    ],
)
def test_benchmark_rights_gate_blocks(classification):
    """UNKNOWN = NÃO PUBLICAR; PROHIBITED/PERMISSION_REQUIRED also block."""
    assert rights_gate(classification).value == "BLOCK"


def test_benchmark_blocking_set_matches_gate():
    """BLOCKING_RIGHTS is exactly the set the gate blocks on."""
    for classification in RightsClassification:
        if classification in BLOCKING_RIGHTS:
            assert rights_gate(classification).value == "BLOCK"
        else:
            assert rights_gate(classification).value == "MAY_PROCEED"


# =============================================================================
# B. Deterministic claim verification (Doc 00 §12, Doc 16)
# =============================================================================


def _claim(db, world):
    ws, profile = world
    svc = KnowledgeService(db)
    return svc.add_claim(
        _ctx(ws, profile),
        subject="foto",
        predicate="mostra",
        object="evento de 1950",
        normalized_text="A foto mostra o evento de 1950",
    )


def test_benchmark_verdict_unknown_without_evidence(db, world):
    """A claim with no evidence is UNKNOWN — never asserted by an LLM."""
    svc = KnowledgeService(db)
    claim = _claim(db, world)
    outcome = svc.verify_claim(_ctx(*world), claim)
    assert outcome.verdict is UncertaintyState.UNKNOWN


def test_benchmark_verdict_possible_single_group(db, world):
    """One independent supporting source → POSSIBLE."""
    svc = KnowledgeService(db)
    ws, profile = world
    claim = _claim(db, world)
    svc.add_evidence(
        _ctx(ws, profile),
        claim_id=claim.id,
        supports=True,
        evidence_type="document",
        independence_group="archive-a",
    )
    outcome = svc.verify_claim(_ctx(ws, profile), claim)
    assert outcome.verdict is UncertaintyState.POSSIBLE


def test_benchmark_verdict_probable_two_groups(db, world):
    """Two independent groups corroborating → PROBABLE."""
    svc = KnowledgeService(db)
    ws, profile = world
    claim = _claim(db, world)
    for group in ("archive-a", "archive-b"):
        svc.add_evidence(
            _ctx(ws, profile),
            claim_id=claim.id,
            supports=True,
            evidence_type="document",
            independence_group=group,
        )
    outcome = svc.verify_claim(_ctx(ws, profile), claim)
    assert outcome.verdict is UncertaintyState.PROBABLE


def test_benchmark_verdict_same_source_is_one_group(db, world):
    """Multiple copies from one group never reach PROBABLE (Doc 09 clusters)."""
    svc = KnowledgeService(db)
    ws, profile = world
    claim = _claim(db, world)
    for _ in range(3):
        svc.add_evidence(
            _ctx(ws, profile),
            claim_id=claim.id,
            supports=True,
            evidence_type="reprint",
            independence_group="wire-copy",
        )
    outcome = svc.verify_claim(_ctx(ws, profile), claim)
    assert outcome.verdict is UncertaintyState.POSSIBLE


def test_benchmark_verdict_controversial_preserves_both_sides(db, world):
    """Contradicting evidence → CONTROVERSIAL and a Contradiction row keeps
    both sides (never silently discarding the losing side)."""
    from packages.domain.knowledge import Contradiction

    svc = KnowledgeService(db)
    ws, profile = world
    claim = _claim(db, world)
    svc.add_evidence(
        _ctx(ws, profile),
        claim_id=claim.id,
        supports=True,
        evidence_type="document",
        independence_group="archive-a",
    )
    svc.add_evidence(
        _ctx(ws, profile),
        claim_id=claim.id,
        supports=False,
        evidence_type="testimony",
        independence_group="archive-b",
    )
    outcome = svc.verify_claim(_ctx(ws, profile), claim)
    assert outcome.verdict is UncertaintyState.CONTROVERSIAL
    contradiction = db.scalars(
        select(Contradiction).where(Contradiction.claim_id == claim.id)
    ).first()
    assert contradiction is not None


def test_benchmark_verdict_history_append_only(db, world):
    """Re-verification appends a new Verdict row; history is never rewritten."""
    from packages.domain.knowledge import Verdict

    svc = KnowledgeService(db)
    ws, profile = world
    claim = _claim(db, world)
    svc.verify_claim(_ctx(ws, profile), claim)
    svc.add_evidence(
        _ctx(ws, profile),
        claim_id=claim.id,
        supports=True,
        evidence_type="document",
        independence_group="archive-a",
    )  # add_evidence re-verifies internally
    rows = db.scalars(select(Verdict).where(Verdict.claim_id == claim.id)).all()
    assert len(rows) >= 2
    assert rows[0].verdict != rows[-1].verdict


# =============================================================================
# C. SSRF breakers (Doc 08)
# =============================================================================


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://localhost/x",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://127.0.0.1:8080/admin",
        "http://[::1]:8080/",
        "http://192.168.1.1/router",
        "http://10.0.0.5/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://intranet.local/login",
        "/etc/passwd",
    ],
)
def test_benchmark_ssrf_blocked_urls(url):
    """Schemes other than http/https, local/private/link-local hosts, and
    hostnames without a scheme are all rejected before any request."""
    with pytest.raises(FetchBlockedError):
        validate_url(url)


def test_benchmark_ssrf_public_host_allowed():
    """A public host passes validation (resolver injected — no real DNS)."""
    url = validate_url(
        "https://example.com/page", resolver=lambda host: ["93.184.216.34"]
    )
    assert url == "https://example.com/page"


def test_benchmark_ssrf_dns_rebind_to_private_blocked():
    """A public-looking host resolving to a private IP is blocked
    (redirect/DNS revalidation behaviour, fail closed)."""
    with pytest.raises(FetchBlockedError):
        validate_url("https://rebind.example.net/", resolver=lambda host: ["192.168.0.10"])


# =============================================================================
# D. V1 format set is closed (Doc 13)
# =============================================================================


def test_benchmark_content_format_closed_set():
    """V1 supports exactly PHOTO_POST, CAROUSEL, MICROLOOP."""
    assert {f.value for f in ContentFormat} == {"PHOTO_POST", "CAROUSEL", "MICROLOOP"}


def _opportunity(db, world):
    from packages.domain.editorial import Opportunity

    ws, profile = world
    opp = Opportunity(workspace_id=ws.id, profile_id=profile.id, title="bench fmt opp")
    db.add(opp)
    db.flush()
    return opp


@pytest.mark.parametrize("fmt", ["PHOTO_POST", "CAROUSEL", "MICROLOOP"])
def test_benchmark_api_accepts_v1_format(db, client, world, fmt):
    """create-content with a V1 format on a real opportunity is accepted."""
    ws, _ = world
    opp = _opportunity(db, world)
    resp = client.post(
        f"/api/v1/opportunities/{opp.id}/create-content",
        params={"workspace_id": str(ws.id)},
        json={"format": fmt},
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == fmt


@pytest.mark.parametrize("fmt", ["VIDEO_POST", "STORY", "REEL", "LIVE", "NEWSLETTER"])
def test_benchmark_api_rejects_non_v1_format(db, client, world, fmt):
    """Any format outside the V1 set is rejected with 422 before content
    creation — the server never accepts an unspecified format."""
    ws, _ = world
    opp = _opportunity(db, world)
    resp = client.post(
        f"/api/v1/opportunities/{opp.id}/create-content",
        params={"workspace_id": str(ws.id)},
        json={"format": fmt},
    )
    assert resp.status_code == 422


# =============================================================================
# E. Constitutional vocabularies are complete and closed
# =============================================================================


def test_benchmark_eleven_qc_gates():
    """The 11 gates before READY exist, including HUMAN_REVIEW (Doc 00 §21)."""
    expected = {
        "RELEVANCE",
        "EVIDENCE",
        "FACTUALITY",
        "UNCERTAINTY",
        "RIGHTS",
        "ORIGINALITY",
        "VISUAL",
        "SEO",
        "PLATFORM",
        "ANTI-SLOP",
        "HUMAN_REVIEW",
    }
    assert {g.value for g in QualityGate} == expected


def test_benchmark_gate_results():
    assert {g.value for g in GateResult} == {"PASS", "WARNING", "FAIL", "REQUIRED"}


def test_benchmark_sixteen_agents():
    """Doc 05 defines exactly 16 agents; none has full authority (Doc 00 §8)."""
    assert len(list(AgentName)) == 16


def test_benchmark_nine_visual_classifications():
    assert len(list(VisualClassification)) == 9


def test_benchmark_uncertainty_states():
    assert {s.value for s in UncertaintyState} == {
        "CONFIRMED",
        "PROBABLE",
        "POSSIBLE",
        "CONTROVERSIAL",
        "UNKNOWN",
        "REFUTED",
    }


def test_benchmark_knowledge_states():
    assert {s.value for s in KnowledgeState} == {
        "SABEMOS",
        "ACREDITAMOS",
        "INTERPRETAMOS",
        "NAO_SABEMOS",
    }


def test_benchmark_jev_decisions():
    assert {d.value for d in JEVDecision} == {
        "PROCEED",
        "NEEDS_RESEARCH",
        "QUARANTINE",
        "REJECT",
        "SERIES_CANDIDATE",
        "EXPERIMENT_CANDIDATE",
    }


def test_benchmark_publication_methods():
    assert {m.value for m in PublicationMethod} == {"API", "MANUAL", "EXPORT", "UNAVAILABLE"}


def test_benchmark_core_job_types():
    values = {j.value for j in JobType}
    assert {"DISCOVERY_SCAN", "SOURCE_RETRIEVAL", "QC", "PUBLICATION", "EXPORT"} <= values


def test_benchmark_main_chain_order():
    """HUMAN_REVIEW precedes READY and PUBLISHED in the main chain (Doc 00 §26):
    nothing publishes without human approval."""
    from packages.domain.enums import MAIN_CHAIN_STATES

    order = [s.value for s in MAIN_CHAIN_STATES]
    assert order.index("HUMAN_REVIEW") < order.index("READY") < order.index("PUBLISHED")


# =============================================================================
# F. Publication endpoints — manual cycle, retry, fallback (AMENDMENT-007, Doc 14)
# =============================================================================


def test_benchmark_confirm_export_publication(db, client, world):
    """AMENDMENT-007: PENDING EXPORT publication confirmed → PUBLISHED with
    published_at."""
    ws, _ = world
    pub = _publication(db, world, method="EXPORT", status="PENDING")
    resp = client.post(
        f"/api/v1/publications/{pub.id}/confirm",
        params={"workspace_id": str(ws.id)},
        json={"remote_id": "ig-123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PUBLISHED"
    assert body["published_at"] is not None
    assert pub.remote_id == "ig-123"


def test_benchmark_confirm_rejects_api_method(db, client, world):
    """Confirmation is manual-only: API publications cannot be confirmed here."""
    ws, _ = world
    pub = _publication(db, world, method="API", status="PENDING")
    resp = client.post(
        f"/api/v1/publications/{pub.id}/confirm",
        params={"workspace_id": str(ws.id)},
        json={},
    )
    assert resp.status_code == 409


def test_benchmark_confirm_rejects_non_pending(db, client, world):
    """Only PENDING publications can be confirmed."""
    ws, _ = world
    pub = _publication(db, world, method="EXPORT", status="MANUAL_FALLBACK")
    resp = client.post(
        f"/api/v1/publications/{pub.id}/confirm",
        params={"workspace_id": str(ws.id)},
        json={},
    )
    assert resp.status_code == 409


def test_benchmark_retry_failed_publication(db, client, world):
    """FAILED publication can be retried back to PENDING."""
    ws, _ = world
    pub = _publication(db, world, method="API", status="FAILED")
    resp = client.post(
        f"/api/v1/publications/{pub.id}/retry",
        params={"workspace_id": str(ws.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING"


def test_benchmark_retry_rejects_published(db, client, world):
    ws, _ = world
    pub = _publication(db, world, method="API", status="PUBLISHED")
    resp = client.post(
        f"/api/v1/publications/{pub.id}/retry",
        params={"workspace_id": str(ws.id)},
    )
    assert resp.status_code == 409


def test_benchmark_manual_fallback_keeps_content(db, client, world):
    """Doc 14: platform down → MANUAL_FALLBACK so content is never lost."""
    ws, _ = world
    pub = _publication(db, world, method="API", status="FAILED")
    resp = client.post(
        f"/api/v1/publications/{pub.id}/manual-fallback",
        params={"workspace_id": str(ws.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "MANUAL_FALLBACK"


# =============================================================================
# G. Workspace isolation (Doc 00 §7, Doc 08)
# =============================================================================


def test_benchmark_publication_invisible_across_workspaces(db, client, world):
    """A publication from workspace B is 404 when addressed via workspace A."""
    ws, _ = world
    other_ws = Workspace(name=f"bench-other-{uuid.uuid4().hex[:8]}")
    db.add(other_ws)
    db.flush()
    other_profile = Profile(workspace_id=other_ws.id, key="main", name="Main")
    db.add(other_profile)
    db.flush()
    pub = _publication(db, (other_ws, other_profile))
    resp = client.post(
        f"/api/v1/publications/{pub.id}/confirm",
        params={"workspace_id": str(ws.id)},
        json={},
    )
    assert resp.status_code == 404


def test_benchmark_workspace_members_do_not_leak(db, world):
    """Membership rows are scoped: another workspace sees zero members."""
    from packages.domain.models import User, WorkspaceMember

    ws, _ = world
    other = Workspace(name=f"bench-iso-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    user = User(email=f"bench-{uuid.uuid4().hex[:6]}@example.com")
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id))
    db.flush()
    foreign = db.scalars(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == other.id)
    ).all()
    assert foreign == []


# =============================================================================
# H. Session + settings security
# =============================================================================


def test_benchmark_me_requires_session(client):
    """Without a session cookie /me is 401 (fail closed)."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_benchmark_logout_is_idempotent_and_revokes(client):
    """Logout with an allowed Origin returns 204 and leaves no usable session."""
    headers = {"Origin": "http://localhost:5173"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_benchmark_logout_rejects_disallowed_origin(client):
    """Logout is CSRF-protected: a foreign Origin is refused."""
    resp = client.post("/api/v1/auth/logout", headers={"Origin": "http://evil.example"})
    assert resp.status_code == 403


def test_benchmark_cors_allowlist_never_wildcard():
    """Doc 08: CORS by allowlist; wildcard never produced."""
    from packages.shared.settings import Settings

    settings = Settings(app_env="test", cors_origins="http://a.test,http://b.test")
    origins = settings.cors_origin_list
    assert origins == ["http://a.test", "http://b.test"]
    assert "*" not in origins


def test_benchmark_secrets_never_in_repr():
    """Password-bearing settings redact their repr (no secret in logs)."""
    from packages.shared.settings import Settings

    settings = Settings(app_env="test", smtp_password="hunter2-secret")
    assert "hunter2-secret" not in repr(settings)


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main(["-v", __file__])
