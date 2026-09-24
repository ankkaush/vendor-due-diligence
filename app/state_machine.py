"""The case state machine from architecture.md, made real.

Two separate concerns, deliberately kept apart:
1. `TRANSITIONS` — which edges are legal at all. A wrong edge is a bug,
   raised immediately (InvalidTransitionError), not silently ignored.
2. `transition_case()`'s WHERE-guarded UPDATE — whether THIS transition,
   right now, actually applies, given the row's real current state. Losing
   this race is not a bug, it's two writers doing their job; the guard
   makes the outcome correct regardless of timing, which is the entire
   point of testing it with real concurrent threads
   (tests/test_app/test_state_machine.py), not just sequential calls.

Case creation (from_status=None -> INTAKE) happens at INSERT time in
app/intake.py, not through this module — there's no row to guard an
UPDATE against yet. Everything from INTAKE onward goes through
transition_case().

FAILED, VALIDATION_FAILED, FINALIZED, and CANCELLED are modeled as
terminal (no outgoing edges) for Phase 5. architecture.md describes FAILED
as "resumable from last checkpoint where possible" — that resume logic
depends on what steps actually exist to resume into, which doesn't exist
until Phase 6/7's agents do. Scoped out here deliberately, not forgotten.
"""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.audit import record_event
from app.db.models import Case, CaseStateTransition

TRANSITIONS: dict[str, set[str]] = {
    "INTAKE": {"VALIDATING", "FAILED", "CANCELLED"},
    "VALIDATING": {"VALIDATION_FAILED", "DOCUMENTS_READY", "FAILED", "CANCELLED"},
    "VALIDATION_FAILED": set(),
    "DOCUMENTS_READY": {"CLASSIFYING", "FAILED", "CANCELLED"},
    "CLASSIFYING": {"INVESTIGATING", "FAILED", "CANCELLED"},
    "INVESTIGATING": {"INVESTIGATIONS_COMPLETE", "FAILED", "CANCELLED"},
    "INVESTIGATIONS_COMPLETE": {"RECONCILING", "FAILED", "CANCELLED"},
    "RECONCILING": {"SYNTHESIZING", "REINVESTIGATING", "FAILED", "CANCELLED"},
    "REINVESTIGATING": {"RECONCILING_POST_REINVESTIGATION", "FAILED", "CANCELLED"},
    "RECONCILING_POST_REINVESTIGATION": {"SYNTHESIZING", "FAILED", "CANCELLED"},
    "SYNTHESIZING": {"AWAITING_HUMAN_REVIEW", "FAILED", "CANCELLED"},
    "AWAITING_HUMAN_REVIEW": {"FINALIZED", "FAILED", "CANCELLED"},
    "FINALIZED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}

TERMINAL_STATUSES = {status for status, edges in TRANSITIONS.items() if not edges}


class InvalidTransitionError(ValueError):
    """The requested edge doesn't exist in the graph at all — a bug in the
    caller, never a normal runtime occurrence."""


def transition_case(
    session: Session,
    case_id,
    *,
    from_status: str,
    to_status: str,
    actor: str = "system",
) -> bool:
    """Attempt from_status -> to_status for one case.

    Returns True if applied, False if the case's real current status
    wasn't from_status when the UPDATE ran — i.e. this specific attempt
    lost a race (or is a stale retry of an already-applied transition).
    False is not an error: callers treat it the same way architecture.md's
    finalize-guard does — "someone else already handled it," not a
    failure to surface.
    """
    if to_status not in TRANSITIONS.get(from_status, set()):
        raise InvalidTransitionError(f"{from_status} -> {to_status} is not a valid transition")

    result = session.execute(
        update(Case)
        .where(Case.id == case_id, Case.status == from_status)
        .values(status=to_status)
    )
    if result.rowcount == 0:
        return False

    session.add(CaseStateTransition(case_id=case_id, from_status=from_status, to_status=to_status))
    record_event(
        session,
        case_id=case_id,
        event_type="case.transitioned",
        actor=actor,
        payload={"from": from_status, "to": to_status},
    )
    session.flush()
    return True
