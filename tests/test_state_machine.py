"""State machine unit tests — spec-direct rules (Doc 00 §26, Doc 03, Doc 09)."""

import pytest

from packages.domain.enums import OpportunityState as S
from packages.domain.state_machine import TransitionError, assert_transition, can_transition


def test_full_linear_chain_is_walkable():
    from packages.domain.enums import MAIN_CHAIN_STATES

    for i in range(len(MAIN_CHAIN_STATES) - 1):
        current, nxt = MAIN_CHAIN_STATES[i], MAIN_CHAIN_STATES[i + 1]
        assert can_transition(current, nxt), f"{current} → {nxt} must be allowed"


def test_skipping_the_chain_is_illegal():
    assert not can_transition(S.DISCOVERED, S.CLUSTERED)
    assert not can_transition(S.RESEARCHING, S.READY)
    assert not can_transition(S.DRAFTING, S.PUBLISHED)


def test_backward_moves_are_illegal():
    assert not can_transition(S.RESEARCHING, S.CANDIDATE)
    assert not can_transition(S.READY, S.DRAFTING)


def test_published_history_cannot_be_rejected():
    for terminal in (S.PUBLISHED, S.ANALYZING, S.LEARNING, S.SCHEDULED):
        assert not can_transition(terminal, S.REJECTED)
        assert not can_transition(terminal, S.CANCELLED)


def test_quarantine_flow_doc09():
    from packages.domain.enums import QuarantineState as Q
    from packages.domain.state_machine import can_transition_quarantine

    assert can_transition(S.CANDIDATE, S.QUARANTINED)
    assert can_transition_quarantine(Q.QUARANTINED, Q.AWAITING_CONFIRMATION)
    assert can_transition_quarantine(Q.AWAITING_CONFIRMATION, Q.REASSESSMENT_DUE)
    assert can_transition_quarantine(Q.REASSESSMENT_DUE, Q.CLEARED)
    assert can_transition_quarantine(Q.REASSESSMENT_DUE, Q.REJECTED)
    assert not can_transition_quarantine(Q.QUARANTINED, Q.CLEARED)  # no shortcut
    # outcomes return to the opportunity machine
    assert can_transition(S.QUARANTINED, S.CANDIDATE)  # cleared
    assert can_transition(S.QUARANTINED, S.REJECTED)  # reassessment rejected


def test_rights_and_fact_blocking_doc16():
    assert can_transition(S.RIGHTS_CHECK, S.RIGHTS_BLOCKED)
    assert can_transition(S.RIGHTS_BLOCKED, S.RIGHTS_CHECK)  # revalidation, Doc 11
    assert can_transition(S.FACT_CHECK, S.FACT_CHECK_FAILED)


def test_needs_research_loop_doc12():
    assert can_transition(S.CANDIDATE, S.NEEDS_RESEARCH)
    assert can_transition(S.OPPORTUNITY_SCORED, S.NEEDS_RESEARCH)
    assert can_transition(S.NEEDS_RESEARCH, S.RESEARCHING)


def test_unknown_transition_raises():
    with pytest.raises(TransitionError):
        assert_transition(S.DISCOVERED, S.PUBLISHED)
