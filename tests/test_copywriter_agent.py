"""Copywriter agent tests: schema + semantic gates with a FAKE provider.

No real LLM call happens here — the fake returns canned JSON. Database
seeds use the same Postgres the other integration tests use (conftest.db).
"""

import json
import uuid

import pytest

from agents import copywriter as cw
from packages.providers.gemini import ProviderUnavailable


class FakeProvider:
    """Returns a canned provider result; records calls (echo-style)."""

    key = "fake"

    def __init__(self, *, result: dict | None = None, error: Exception | None = None):
        self.result = result or {}
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def call(self, capability_key: str, payload: dict) -> dict:
        self.calls.append((capability_key, payload))
        if self.error is not None:
            raise self.error
        return self.result


def _provider_payload(
    claim_id: str,
    *,
    title="O bondinho de 1911",
    caption="Uma marca da cidade que atravessa o século. " * 3,
) -> dict:
    return {
        "text": json.dumps(
            {
                "title": title,
                "caption": caption,
                "claim_ids_used": [claim_id],
                "slides": [],
                "seo": {"entities": ["Bondinho"], "keywords": ["1911"]},
            }
        ),
        "json": {
            "title": title,
            "caption": caption,
            "claim_ids_used": [claim_id],
            "slides": [],
            "seo": {"entities": ["Bondinho"], "keywords": ["1911"]},
        },
        "provider": "fake",
        "model": "fake-model",
        "finish_reason": "STOP",
    }


@pytest.fixture()
def seeded_package(db):
    """Workspace + profile + opportunity (FORMAT_SELECTED) + canonical +
    package + one POSSIBLE claim attached. Returns (package, claim, ctx)."""
    from packages.domain.editorial import (
        CanonicalContent,
        ContentPackage,
        Opportunity,
        OpportunityClaim,
    )
    from packages.domain.enums import OpportunityState, UncertaintyState
    from packages.domain.knowledge import Claim
    from packages.domain.models import Profile, Workspace
    from packages.shared.execution_context import ExecutionContext

    ws = Workspace(name=f"cw-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    ctx = ExecutionContext(workspace_id=ws.id, profile_id=profile.id)

    opp = Opportunity(
        workspace_id=ws.id,
        profile_id=profile.id,
        title="Bondinho do Pão de Açúcar",
        state=OpportunityState.FORMAT_SELECTED.value,
    )
    db.add(opp)
    db.flush()
    canonical = CanonicalContent(
        workspace_id=ws.id,
        opportunity_id=opp.id,
        editorial_angle="memória urbana",
        key_message="o bondinho começou em 1911",
    )
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
    claim = Claim(
        workspace_id=ws.id,
        profile_id=profile.id,
        normalized_text="O bondinho começou a operar em 1911",
        subject="Bondinho",
        predicate="começou a operar em",
        object="1911",
        status=UncertaintyState.POSSIBLE.value,
    )
    db.add(claim)
    db.flush()
    db.add(
        OpportunityClaim(
            workspace_id=ws.id,
            opportunity_id=opp.id,
            ref_id=claim.id,
        )
    )
    db.commit()
    db.expire_all()
    return package, claim, ctx


def test_write_draft_valid_output(db, seeded_package):
    package, claim, ctx = seeded_package
    provider = FakeProvider(result=_provider_payload(str(claim.id)))
    output, provenance = cw.write_draft(db, ctx, package, provider)
    assert output.title
    assert output.claim_ids_used == [str(claim.id)]
    assert provenance["provider"] == "fake"
    assert provenance["model"] == "fake-model"
    # prompt carries the canonical data and the claim block
    sent_prompt = provider.calls[0][1]["prompt"]
    assert "Bondinho do Pão de Açúcar" in sent_prompt
    assert str(claim.id) in sent_prompt


def test_invented_claim_is_blocked(db, seeded_package):
    package, _claim, ctx = seeded_package
    fake_id = str(uuid.uuid4())
    provider = FakeProvider(result=_provider_payload(fake_id))
    with pytest.raises(cw.CopywriterBlocked, match="not attached-and-usable"):
        cw.write_draft(db, ctx, package, provider)


def test_unknown_verdict_claim_is_blocked(db, seeded_package):
    from packages.domain.enums import UncertaintyState

    package, claim, ctx = seeded_package
    claim.status = UncertaintyState.UNKNOWN.value
    db.commit()
    provider = FakeProvider(result=_provider_payload(str(claim.id)))
    with pytest.raises(cw.CopywriterBlocked):
        cw.write_draft(db, ctx, package, provider)


def test_malformed_model_json_is_blocked(db, seeded_package):
    package, claim, ctx = seeded_package
    broken = _provider_payload(str(claim.id))
    broken["json"] = {"title": 123}  # wrong shape, missing caption
    broken["text"] = json.dumps(broken["json"])
    provider = FakeProvider(result=broken)
    with pytest.raises(cw.CopywriterBlocked, match="schema validation"):
        cw.write_draft(db, ctx, package, provider)


def test_provider_unavailable_propagates_for_retry(db, seeded_package):
    package, _claim, ctx = seeded_package
    provider = FakeProvider(error=ProviderUnavailable("rate limited"))
    with pytest.raises(ProviderUnavailable):
        cw.write_draft(db, ctx, package, provider)


def test_empty_title_is_blocked(db, seeded_package):
    package, claim, ctx = seeded_package
    provider = FakeProvider(result=_provider_payload(str(claim.id), title="  "))
    with pytest.raises(cw.CopywriterBlocked, match="empty title"):
        cw.write_draft(db, ctx, package, provider)


def test_no_claims_used_is_blocked(db, seeded_package):
    package, claim, ctx = seeded_package
    payload = _provider_payload(str(claim.id))
    payload["json"]["claim_ids_used"] = []
    payload["text"] = json.dumps(payload["json"])
    provider = FakeProvider(result=payload)
    with pytest.raises(cw.CopywriterBlocked, match="uses no claims"):
        cw.write_draft(db, ctx, package, provider)


def test_prompt_template_is_versioned_and_present():
    from agents.copywriter import PROMPT_VERSION, TEMPLATE_PATH

    assert PROMPT_VERSION == "copywriter_v1"
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "version 1" in text
    assert "{claims_block}" in text
