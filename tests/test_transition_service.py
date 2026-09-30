"""Transition Service (Doc 03 checklist): rule + gates + required data + audit."""

import uuid

import pytest

from packages.domain.enums import OpportunityState as S
from packages.domain.state_machine import TransitionError
from packages.governance.transition_service import TransitionService
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def world(db):
    from packages.domain.models import Workspace

    ws = Workspace(name=f"ts-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    return ws


def _ctx(ws):
    return ExecutionContext(workspace_id=ws.id)


def test_legal_transition_audited(db, world):
    entity = uuid.uuid4()
    event = TransitionService(db).apply(
        _ctx(world),
        entity_type="opportunity",
        entity_id=entity,
        current=S.DISCOVERED,
        target=S.NORMALIZED,
        reason="normalized by pipeline",
    )
    assert event.previous_state == "DISCOVERED"
    assert event.new_state == "NORMALIZED"
    assert event.rule_version == "constitution-1.0"


def test_illegal_transition_refused_and_not_audited(db, world):
    service = TransitionService(db)
    with pytest.raises(TransitionError):
        service.apply(
            _ctx(world),
            entity_type="opportunity",
            entity_id=uuid.uuid4(),
            current=S.DISCOVERED,
            target=S.PUBLISHED,
            reason="shortcut attempt",
        )
    from packages.domain.repositories import AuditRepository

    assert AuditRepository(db).list_for_workspace(world.id) == []


def test_gates_fail_closed(db, world):
    with pytest.raises(TransitionError, match="gate status"):
        TransitionService(db).apply(
            _ctx(world),
            entity_type="opportunity",
            entity_id=uuid.uuid4(),
            current=S.QUALITY_CONTROL,
            target=S.HUMAN_REVIEW,
            gates_ok=False,
        )


def test_required_data_missing_blocks(db, world):
    with pytest.raises(TransitionError, match="required data missing"):
        TransitionService(db).apply(
            _ctx(world),
            entity_type="opportunity",
            entity_id=uuid.uuid4(),
            current=S.HUMAN_REVIEW,
            target=S.READY,
            required_data={"approved_by": None},
        )


def test_missing_workspace_context_blocks(db):
    ctx = ExecutionContext(workspace_id=uuid.uuid4())  # nonexistent workspace
    with pytest.raises(TransitionError, match="workspace"):
        TransitionService(db).apply(
            ctx,
            entity_type="opportunity",
            entity_id=uuid.uuid4(),
            current=S.DISCOVERED,
            target=S.NORMALIZED,
        )
