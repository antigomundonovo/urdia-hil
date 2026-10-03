"""Owner-provided historical facts (assets/datasets/historical_facts.json)
verified through the DETERMINISTIC judge (Doc 16).

For each fact: claim + supporting evidence from 2 INDEPENDENT sources
-> engine verdict must be PROBABLE (the engine never awards CONFIRMED —
that stays human, Doc 16).

Special canonical case H3 (bondinho): the POPULAR BELIEF ("1911") is the
claim and a contradicting source is registered -> CONTROVERSIAL with the
Contradiction row preserved (both sides kept, Doc 16).
"""

import json
from pathlib import Path

import pytest

from packages.domain.enums import UncertaintyState
from packages.domain.knowledge import Contradiction
from packages.domain.models import Source
from packages.research.verification import KnowledgeService
from packages.shared.execution_context import ExecutionContext

DATASET_PATH = Path("assets/datasets/historical_facts.json")


@pytest.fixture()
def dataset():
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert data["dataset"] == "historical_facts"
    assert len(data["cases"]) >= 3
    return data["cases"]


@pytest.fixture()
def world(db):
    import uuid

    from packages.domain.models import Profile, Workspace

    ws = Workspace(name=f"hist-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    db.commit()
    ctx = ExecutionContext(workspace_id=ws.id, profile_id=profile.id)
    return ws, profile, ctx


def _source(db, world, name: str, url: str) -> Source:
    ws, profile, _ctx = world
    src = Source(
        workspace_id=ws.id,
        profile_id=profile.id,
        url=url,
        source_type="rss",
        publisher=name,
    )
    db.add(src)
    db.flush()
    return src


def test_every_owner_fact_reaches_probable_with_two_independent_sources(db, world, dataset):
    """Canonical benchmark: each real fact, corroborated by 2 independent
    sources, must be judged PROBABLE (never CONFIRMED — human authority)."""
    knowledge = KnowledgeService(db)
    for fact in dataset:
        claim = knowledge.add_claim(
            world[2], normalized_text=fact["statement"], claim_type="historical_fact"
        )
        for i in (1, 2):
            src = _source(db, world, f"{fact['source_name']} #{i}", f"{fact['source_url']}?e={i}")
            knowledge.add_evidence(
                world[2],
                claim_id=claim.id,
                supports=True,
                source_id=src.id,
                independence_group=f"{fact['id']}-group-{i}",
                strength=5,
            )
        outcome = knowledge.verify_claim(world[2], claim)
        assert outcome.verdict is UncertaintyState.PROBABLE, (
            f"{fact['id']} judged {outcome.verdict.value}: {outcome.reason}"
        )
        assert outcome.supporting_groups >= 2
        db.rollback()  # each fact is its own scenario


def test_bondinho_popular_belief_is_flagged_controversial(db, world, dataset):
    """H3 is the canonical controversy case: the POPULAR BELIEF (1911) is
    contradicted by the real source (1912). The judge must keep BOTH sides
    (Contradiction row) and mark the popular claim CONTROVERSIAL."""
    belief_case = next(c for c in dataset if "popular_belief" in c)
    assert belief_case["popular_belief"] == "O bondinho começou a operar em 1911"

    knowledge = KnowledgeService(db)
    popular = knowledge.add_claim(
        world[2], normalized_text=belief_case["popular_belief"], claim_type="historical_fact"
    )
    contradicting_src = _source(
        db, world, belief_case["source_name"], belief_case["source_url"]
    )
    knowledge.add_evidence(
        world[2],
        claim_id=popular.id,
        supports=False,  # the real source CONTRADICTS the popular belief
        source_id=contradicting_src.id,
        excerpt="Primeiro trecho inaugurado em 27 de outubro de 1912",
        strength=5,
    )
    outcome = knowledge.verify_claim(world[2], popular)
    assert outcome.verdict is UncertaintyState.CONTROVERSIAL
    assert outcome.contradicting_sources >= 1

    # the contradiction row preserves BOTH sides (Doc 16)
    rows = db.query(Contradiction).filter_by(claim_id=popular.id).all()
    assert rows, "contradiction must be recorded, never overwritten"


def test_dataset_statements_feed_copywriter_guard(db, world, dataset):
    """The Copywriter's semantic gate accepts the canonical facts as usable
    claims (verified PROBABLE) — the dataset is directly usable as draft
    context without inventing anything."""
    knowledge = KnowledgeService(db)
    fact = dataset[0]
    claim = knowledge.add_claim(
        world[2], normalized_text=fact["statement"], claim_type="historical_fact"
    )
    for i in (1, 2):
        src = _source(db, world, f"{fact['source_name']} #{i}", f"{fact['source_url']}?e={i}")
        knowledge.add_evidence(
            world[2],
            claim_id=claim.id,
            supports=True,
            source_id=src.id,
            independence_group=f"copy-group-{i}",
        )
    from agents.copywriter import USABLE_VERDICTS

    outcome = knowledge.verify_claim(world[2], claim)
    assert outcome.verdict.value in USABLE_VERDICTS
