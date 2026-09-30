"""Analytics + learning tests (Doc 15): append-only metrics, deterministic
comment classification, testimony never confirmation, rules need HUMAN REVIEW."""

import uuid

import pytest
from sqlalchemy import select

from packages.domain.enums import QualifiedSignal
from packages.domain.models import Profile, Workspace
from packages.domain.publishing import MetricEvent, Publication
from packages.research.analytics import AnalyticsService, classify_comment
from packages.research.learning import LearningError, LearningService
from packages.shared.execution_context import ExecutionContext


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
    snapshot = service.publication_snapshot(publication=pub)
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


def test_rule_cannot_activate_without_human_review(db, world):
    """Doc 15: RULE_CANDIDATE → HUMAN REVIEW → ACTIVE_RULE. Fail closed."""
    ws, profile = world
    ctx = _ctx(ws, profile)
    learning = LearningService(db)
    rule = learning.propose_rule(ctx, statement="carrossel com 7 slides retém mais")
    with pytest.raises(LearningError, match="human review required"):
        learning.activate_rule(ctx, rule)
    assert rule.status == "CANDIDATE"

    learning.review_rule(ctx, rule, reviewed_by=uuid.uuid4(), notes="concordo")
    learning.activate_rule(ctx, rule)
    assert rule.status == "ACTIVE"


def test_experiment_requires_control_and_variant(db, world):
    ws, profile = world
    ctx = _ctx(ws, profile)
    learning = LearningService(db)
    with pytest.raises(LearningError, match="2 variants"):
        learning.create_experiment(ctx, hypothesis="h", variants={"control": {}})
    experiment = learning.create_experiment(
        ctx,
        hypothesis="5 vs 8 slides",
        variants={"control": {"slides": 5}, "variant": {"slides": 8}},
    )
    learning.record_result(
        ctx, experiment, {"control_reach": 100, "variant_reach": 140}, decision="variant wins"
    )
    assert experiment.status == "COMPLETED"
