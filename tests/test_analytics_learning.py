"""Analytics + learning tests (Doc 15): append-only metrics, deterministic
comment classification, testimony never confirmation, rules need HUMAN REVIEW."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import app
from packages.domain.enums import QualifiedSignal
from packages.domain.models import Profile, User, Workspace, WorkspaceMember
from packages.domain.publishing import MetricEvent, Publication
from packages.research.analytics import AnalyticsService, classify_comment
from packages.research.learning import LearningError, LearningService
from packages.shared.db import get_session
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def world(db):
    ws = Workspace(name=f"ana-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    return ws, profile


def _ctx(ws, profile):
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def _publication(db, world) -> Publication:
    from packages.domain.editorial import CanonicalContent, ContentPackage, Opportunity

    ws, profile = world
    opp = Opportunity(workspace_id=ws.id, profile_id=profile.id, title="t", state="LEARNING")
    db.add(opp)
    db.flush()
    canonical = CanonicalContent(workspace_id=ws.id, opportunity_id=opp.id)
    db.add(canonical)
    db.flush()
    package = ContentPackage(
        workspace_id=ws.id, opportunity_id=opp.id,
        canonical_content_id=canonical.id, format="PHOTO_POST",
    )
    db.add(package)
    db.flush()
    pub = Publication(
        workspace_id=ws.id, profile_id=profile.id,
        content_package_id=package.id,
        platform="instagram", method="EXPORT", status="PUBLISHED",
    )
    db.add(pub)
    db.flush()
    return pub


def test_metrics_are_append_only(db, world):
    """Doc 15: each collection creates new events, history never overwritten."""
    ws, profile = world
    ctx = _ctx(ws, profile)
    service = AnalyticsService(db)
    pub = _publication(db, world)
    service.record_metrics(ctx, pub, {"REACH": 100})
    service.record_metrics(ctx, pub, {"REACH": 250})
    events = list(db.scalars(select(MetricEvent).where(MetricEvent.publication_id == pub.id)))
    assert len(events) == 2  # both kept
    snapshot = service.publication_snapshot(ctx, pub)
    assert snapshot["metrics"]["REACH"] == 250  # latest value


def test_overview_sums_latest_per_publication(db, world):
    ws, profile = world
    ctx = _ctx(ws, profile)
    service = AnalyticsService(db)
    p1, p2 = _publication(db, world), _publication(db, world)
    service.record_metrics(ctx, p1, {"REACH": 100, "SAVES": 10})
    service.record_metrics(ctx, p2, {"REACH": 300})
    overview = service.overview(ws.id, profile.id)
    assert overview["publications"] == 2
    assert overview["totals"]["REACH"] == 400
    assert overview["totals"]["SAVES"] == 10


def test_comment_classifier_deterministic():
    cases = [
        ("Qual a fonte dessa informação?", QualifiedSignal.SOURCE_REQUEST),
        ("Você errou, na verdade foi em 1931", QualifiedSignal.CORRECTION),
        ("Tenho uma foto do meu avô na obra!", QualifiedSignal.DOCUMENT_SUBMISSION),
        ("Minha avó trabalhava lá e contava essa história", QualifiedSignal.TESTIMONY),
        ("E depois? Continua!", QualifiedSignal.CONTINUATION_REQUEST),
        ("Ótimo post", None),
        ("Ganhe seguidores clique aqui http://spam.test", None),  # spam
    ]
    for text, expected in cases:
        intent, signal = classify_comment(text)
        assert signal == expected, f"{text!r} → {signal}"
    spam_intent, spam_signal = classify_comment("Ganhe seguidores clique aqui http://spam.test")
    assert spam_intent == "SPAM" and spam_signal is None


def test_testimony_is_possible_oral_history_not_confirmation(db, world):
    """Doc 15: classify POSSIBLE_ORAL_HISTORY — never auto-confirmation."""
    ws, profile = world
    service = AnalyticsService(db)
    pub = _publication(db, world)
    comment = service.add_comment(
        _ctx(ws, profile), pub,
        text="Minha avó trabalhava lá e contava essa história", author_ref="user1",
    )
    assert comment.qualified_signal == QualifiedSignal.TESTIMONY.value
    # the record never claims it is confirmed history
    assert comment.qualified_signal == "TESTIMONY"


def test_qualified_signals_listing(db, world):
    ws, profile = world
    ctx = _ctx(ws, profile)
    service = AnalyticsService(db)
    pub = _publication(db, world)
    service.add_comment(ctx, pub, text="Qual a fonte?")
    service.add_comment(ctx, pub, text="Belo trabalho")
    signals = service.qualified_signals(ws.id, profile.id)
    assert len(signals) == 1
    assert signals[0].qualified_signal == QualifiedSignal.SOURCE_REQUEST.value


def test_analytics_writes_and_snapshots_are_profile_scoped(db, world):
    ws, profile = world
    service = AnalyticsService(db)
    publication = _publication(db, world)
    foreign_profile = Profile(workspace_id=ws.id, key="foreign", name="Foreign")
    db.add(foreign_profile)
    db.flush()
    foreign_ctx = _ctx(ws, foreign_profile)

    with pytest.raises(LookupError, match="publication not found"):
        service.record_metrics(foreign_ctx, publication, {"REACH": 100})
    with pytest.raises(LookupError, match="publication not found"):
        service.publication_snapshot(foreign_ctx, publication)
    with pytest.raises(LookupError, match="publication not found"):
        service.add_comment(foreign_ctx, publication, text="private comment")

    events = db.scalars(
        select(MetricEvent).where(MetricEvent.publication_id == publication.id)
    ).all()
    assert events == []
    assert service.overview(ws.id, profile.id)["publications"] == 1
    assert service.list_comments(ws.id, foreign_profile.id) == []


def test_metrics_api_rejects_mismatched_profile_id(client, db, world):
    ws, profile = world
    publication = _publication(db, world)
    foreign_profile = Profile(workspace_id=ws.id, key="api-foreign", name="Foreign")
    db.add(foreign_profile)
    db.flush()

    response = client.post(
        f"/api/v1/analytics/publications/{publication.id}/collect?workspace_id={ws.id}",
        json={"profile_id": str(foreign_profile.id), "values": {"REACH": 100}},
    )

    assert response.status_code == 404
    assert db.scalars(
        select(MetricEvent).where(MetricEvent.publication_id == publication.id)
    ).all() == []


def test_rule_cannot_activate_without_human_review(db, world):
    """Doc 15: RULE_CANDIDATE → HUMAN REVIEW → ACTIVE_RULE. Fail closed."""
    ws, profile = world
    ctx = _ctx(ws, profile)
    learning = LearningService(db)
    rule = learning.propose_rule(ctx, statement="carrossel com 7 slides retém mais")
    with pytest.raises(LearningError, match="human review required"):
        learning.activate_rule(ctx, rule)
    assert rule.status == "CANDIDATE"

    reviewer = User(name="Learning Reviewer", email=f"reviewer-{uuid.uuid4().hex[:8]}@example.test")
    db.add(reviewer)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=reviewer.id))
    db.flush()
    learning.review_rule(ctx, rule, reviewed_by=reviewer.id, notes="concordo")
    learning.activate_rule(ctx, rule)
    assert rule.status == "ACTIVE"


def test_api_rule_review_attributes_authenticated_actor(client, db, world):
    ws, profile = world
    service = LearningService(db)
    rule = service.propose_rule(_ctx(ws, profile), statement="API review actor")
    actor = User(name="API Reviewer", email=f"api-reviewer-{uuid.uuid4().hex[:8]}@example.test")
    spoofed = User(name="Spoofed Reviewer", email=f"spoofed-{uuid.uuid4().hex[:8]}@example.test")
    db.add_all([actor, spoofed])
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=actor.id))
    db.flush()

    from apps.api.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: actor
    response = client.post(
        f"/api/v1/learning/rules/{rule.id}/review?workspace_id={ws.id}&profile_id={profile.id}",
        json={"reviewed_by": str(spoofed.id), "notes": "authenticated actor wins"},
    )

    assert response.status_code == 200, response.text
    db.refresh(rule)
    assert rule.reviewed_by == actor.id
    assert rule.reviewed_by != spoofed.id


def test_rule_review_requires_workspace_member(db, world):
    ws, profile = world
    ctx = _ctx(ws, profile)
    learning = LearningService(db)
    rule = learning.propose_rule(ctx, statement="reviewer must belong to workspace")

    with pytest.raises(LearningError, match="reviewer is not a workspace member"):
        learning.review_rule(ctx, rule, reviewed_by=uuid.uuid4())
    assert rule.status == "CANDIDATE"


def test_experiment_requires_control_and_variant(db, world):
    ws, profile = world
    ctx = _ctx(ws, profile)
    learning = LearningService(db)
    with pytest.raises(LearningError, match="control and at least one variant"):
        learning.create_experiment(ctx, hypothesis="h", variants={"control": {}})
    with pytest.raises(LearningError, match="control and at least one variant"):
        learning.create_experiment(
            ctx,
            hypothesis="h",
            variants={"variant-a": {}, "variant-b": {}},
        )
    experiment = learning.create_experiment(
        ctx,
        hypothesis="5 vs 8 slides",
        variants={"control": {"slides": 5}, "variant": {"slides": 8}},
    )
    learning.record_result(
        ctx, experiment, {"control_reach": 100, "variant_reach": 140}, decision="variant wins"
    )
    assert experiment.status == "COMPLETED"


def test_learning_mutations_are_profile_scoped(db, world):
    ws, profile = world
    service = LearningService(db)
    ctx = _ctx(ws, profile)
    experiment = service.create_experiment(
        ctx,
        hypothesis="control versus variant",
        variants={"control": {}, "variant": {}},
    )
    rule = service.propose_rule(ctx, statement="keep private to profile")
    foreign_profile = Profile(workspace_id=ws.id, key="foreign-learning", name="Foreign")
    db.add(foreign_profile)
    db.flush()
    foreign_ctx = _ctx(ws, foreign_profile)

    with pytest.raises(LearningError, match="experiment not found"):
        service.record_result(foreign_ctx, experiment, {"winner": "variant"})
    with pytest.raises(LearningError, match="rule not found"):
        service.review_rule(foreign_ctx, rule, reviewed_by=uuid.uuid4())
    with pytest.raises(LearningError, match="rule not found"):
        service.activate_rule(foreign_ctx, rule)
    with pytest.raises(LearningError, match="origin experiment not found"):
        service.propose_rule(
            foreign_ctx,
            statement="foreign experiment source",
            origin_experiment_id=experiment.id,
        )

    assert experiment.status == "RUNNING"
    assert rule.status == "CANDIDATE"


def test_rule_with_experiment_origin_requires_recorded_result(db, world):
    ws, profile = world
    service = LearningService(db)
    experiment = service.create_experiment(
        _ctx(ws, profile),
        hypothesis="test hypothesis",
        variants={"control": {}, "variant": {}},
    )

    with pytest.raises(LearningError, match="recorded result"):
        service.propose_rule(
            _ctx(ws, profile),
            statement="candidate from unfinished experiment",
            origin_experiment_id=experiment.id,
        )
