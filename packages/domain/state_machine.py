"""State machine rules (Doc 00 §26, Doc 03).

Spec-direct rules:
- the main chain is linear and ordered exactly as Doc 03 lists it;
- the quarantine flow is QUARANTINED → AWAITING_CONFIRMATION →
  REASSESSMENT_DUE → CLEARED / REJECTED (Doc 09);
- rights blocking: RIGHTS_CHECK → RIGHTS_BLOCKED; re-verification re-enters
  RIGHTS_CHECK (Doc 11 revalidation + gate);
- fact failure: FACT_CHECK → FACT_CHECK_FAILED (Doc 16);
- duplicates: DISCOVERED/CLUSTERED → DUPLICATE (Doc 16 duplicate rule).

Minimal connector rules (declared here, documented as implementation
decisions — the spec names the auxiliary states without their full graph):
- human terminal decisions REJECTED/CANCELLED from any main-chain state
  before publication (PUBLISHED and later are history, Doc 15 corrections
  pipeline applies there instead);
- NEEDS_RESEARCH entered from CANDIDATE/OPPORTUNITY_SCORED (JEV decision,
  Doc 12) and re-entering the chain at RESEARCHING;
- BLOCKED from any pre-READY main-chain state as an operational hold;
- CLEARED returns to CANDIDATE.
"""

from packages.domain.enums import MAIN_CHAIN_STATES, OpportunityState

S = OpportunityState

TRANSITIONS: dict[OpportunityState, frozenset[OpportunityState]] = {}


def _add(current: OpportunityState, targets: tuple[OpportunityState, ...]) -> None:
    TRANSITIONS[current] = TRANSITIONS.get(current, frozenset()) | frozenset(targets)


# Linear main chain (spec-direct)
for _i in range(len(MAIN_CHAIN_STATES) - 1):
    _add(MAIN_CHAIN_STATES[_i], (MAIN_CHAIN_STATES[_i + 1],))

# Human terminal decisions from the pre-publication chain
_PUBLISHED_ONWARD = frozenset(
    {S.PUBLISHED, S.ANALYZING, S.LEARNING, S.SCHEDULED}
)
for _state in MAIN_CHAIN_STATES:
    if _state not in _PUBLISHED_ONWARD:
        _add(_state, (S.REJECTED, S.CANCELLED))

# Quarantine (Doc 09): CANDIDATE → QUARANTINED enters the quarantine lifecycle
# (its own sub-state chain lives in QUARANTINE_CHAIN below); cleared returns to
# the pipeline at CANDIDATE, rejected after reassessment goes to REJECTED.
_add(S.CANDIDATE, (S.QUARANTINED,))
_add(S.QUARANTINED, (S.CANDIDATE, S.REJECTED))

# Quarantine lifecycle (Doc 09), tracked with QuarantineState:
# QUARANTINED → AWAITING_CONFIRMATION → REASSESSMENT_DUE → CLEARED / REJECTED
from packages.domain.enums import QuarantineState  # noqa: E402

QUARANTINE_CHAIN: tuple[QuarantineState, ...] = (
    QuarantineState.QUARANTINED,
    QuarantineState.AWAITING_CONFIRMATION,
    QuarantineState.REASSESSMENT_DUE,
)
QUARANTINE_TERMINALS: tuple[QuarantineState, ...] = (
    QuarantineState.CLEARED,
    QuarantineState.REJECTED,
)


def can_transition_quarantine(current: QuarantineState, target: QuarantineState) -> bool:
    if current is QuarantineState.REASSESSMENT_DUE:
        return target in QUARANTINE_TERMINALS
    for i, state in enumerate(QUARANTINE_CHAIN):
        if current is state and i + 1 < len(QUARANTINE_CHAIN):
            return target is QUARANTINE_CHAIN[i + 1]
    return False

# Failure / blocking states
_add(S.FACT_CHECK, (S.FACT_CHECK_FAILED,))
_add(S.RIGHTS_CHECK, (S.RIGHTS_BLOCKED,))
_add(S.RIGHTS_BLOCKED, (S.RIGHTS_CHECK,))
_add(S.DISCOVERED, (S.DUPLICATE,))
_add(S.CLUSTERED, (S.DUPLICATE,))

# Research loop (Doc 12 NEEDS_RESEARCH decision)
_add(S.CANDIDATE, (S.NEEDS_RESEARCH,))
_add(S.OPPORTUNITY_SCORED, (S.NEEDS_RESEARCH,))
_add(S.NEEDS_RESEARCH, (S.RESEARCHING,))

# Operational hold before READY
for _state in MAIN_CHAIN_STATES:
    if _state is not S.READY and MAIN_CHAIN_STATES.index(_state) < MAIN_CHAIN_STATES.index(S.READY):
        _add(_state, (S.BLOCKED,))


class TransitionError(Exception):
    """Fail closed: any transition not explicitly allowed is refused."""


def can_transition(current: OpportunityState, target: OpportunityState) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: OpportunityState, target: OpportunityState) -> None:
    if current not in TRANSITIONS and current not in set(OpportunityState):
        raise TransitionError(f"unknown current state: {current}")
    if not can_transition(current, target):
        raise TransitionError(f"transition not allowed: {current} → {target}")
