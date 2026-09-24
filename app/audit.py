"""Generic append-only audit logging (observability.md's trace hierarchy).

Deliberately the thinnest possible wrapper: every phase from here on calls
record_event() for anything worth a durable, human-readable trail (case
created, document ingested, state transition, agent run started/finished,
finding created, human decision). This module doesn't decide WHAT is
audit-worthy — callers do — it only guarantees HOW it's written: one
append-only row, never mutated (audit_events' database trigger enforces
that independently of this code — see app/db/models.py, ADR-007-adjacent
security.md discussion).
"""

from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def record_event(
    session: Session,
    *,
    case_id,
    event_type: str,
    actor: str,
    payload: dict | None = None,
) -> AuditEvent:
    """Write one audit_events row. Does not commit — caller controls the
    transaction boundary, so an audit event and the business change it
    describes land in the same commit or not at all."""
    event = AuditEvent(case_id=case_id, event_type=event_type, actor=actor, payload=payload)
    session.add(event)
    session.flush()
    return event
