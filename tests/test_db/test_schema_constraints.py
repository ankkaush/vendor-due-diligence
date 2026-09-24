"""Constraint tests: the database-enforced guarantees the architecture
depends on, not just documented conventions.
"""

import pytest
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.db.models import (
    AgentRun,
    AuditEvent,
    Case,
    CaseStateTransition,
    Conflict,
    HumanReview,
    ReInvestigation,
    Vendor,
)


def _make_case(session) -> Case:
    vendor = Vendor(name="Constraint Test Vendor")
    session.add(vendor)
    session.flush()
    case = Case(vendor_id=vendor.id)
    session.add(case)
    session.flush()
    return case


def test_duplicate_non_terminal_agent_run_is_rejected(db_session):
    """architecture.md: at most one non-terminal AgentRun per
    (case_id, agent_type) — the idempotency guarantee that prevents
    duplicate execution on retry, enforced by a partial unique index."""
    case = _make_case(db_session)

    first = AgentRun(
        case_id=case.id, agent_type="security_investigator",
        status="running", model="claude-haiku-4-5-20251001",
    )
    db_session.add(first)
    db_session.flush()

    duplicate = AgentRun(
        case_id=case.id, agent_type="security_investigator",
        status="pending", model="claude-haiku-4-5-20251001",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_terminal_agent_runs_do_not_collide(db_session):
    """The partial index only covers pending/running — a case can
    legitimately have multiple terminal (succeeded/failed) runs for the
    same agent_type over time (e.g. after a retry produced a new row),
    which must NOT be blocked."""
    case = _make_case(db_session)

    db_session.add(AgentRun(
        case_id=case.id, agent_type="security_investigator",
        status="failed", model="claude-haiku-4-5-20251001",
    ))
    db_session.flush()
    db_session.add(AgentRun(
        case_id=case.id, agent_type="security_investigator",
        status="succeeded", model="claude-haiku-4-5-20251001",
    ))
    db_session.flush()  # must not raise

    count = (
        db_session.query(AgentRun)
        .filter_by(case_id=case.id, agent_type="security_investigator")
        .count()
    )
    assert count == 2


def test_second_reinvestigation_round_is_rejected(db_session):
    """Decision #13: max one re-investigation round per conflict,
    enforced by a unique constraint on conflict_id, not just application
    discipline that could be bypassed under pressure to 'just try once
    more'."""
    case = _make_case(db_session)
    conflict = Conflict(case_id=case.id, conflict_type="direct_contradiction")
    db_session.add(conflict)
    db_session.flush()

    run_1 = AgentRun(
        case_id=case.id, agent_type="privacy_investigator",
        status="succeeded", model="claude-haiku-4-5-20251001",
    )
    db_session.add(run_1)
    db_session.flush()
    db_session.add(ReInvestigation(conflict_id=conflict.id, agent_run_id=run_1.id))
    db_session.flush()

    run_2 = AgentRun(
        case_id=case.id, agent_type="privacy_investigator",
        status="succeeded", model="claude-haiku-4-5-20251001",
    )
    db_session.add(run_2)
    db_session.flush()
    db_session.add(ReInvestigation(conflict_id=conflict.id, agent_run_id=run_2.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    "make_row",
    [
        lambda case: CaseStateTransition(case_id=case.id, from_status=None, to_status="INTAKE"),
        lambda case: HumanReview(case_id=case.id, reviewer_id="ankit", decision="approved"),
        lambda case: AuditEvent(case_id=case.id, event_type="test.event", actor="system"),
    ],
    ids=["case_state_transitions", "human_reviews", "audit_events"],
)
def test_append_only_tables_reject_update(db_session, make_row):
    """data-model.md / security.md: these tables are append-only by
    design, enforced by a database trigger — verified here by actually
    attempting an UPDATE and an DELETE and confirming both are refused,
    not just documented as forbidden."""
    case = _make_case(db_session)
    row = make_row(case)
    db_session.add(row)
    db_session.flush()

    row_id = row.id
    table = row.__table__

    with pytest.raises(ProgrammingError, match="append-only"):
        db_session.execute(table.update().where(table.c.id == row_id).values(id=row_id))
        db_session.flush()
    # No manual rollback here: the fixture's outer transaction.rollback()
    # at teardown safely recovers an aborted transaction regardless — an
    # explicit session.rollback() on a session bound to that same external
    # connection risks double-rolling-back the fixture's own transaction.


@pytest.mark.parametrize(
    "make_row",
    [
        lambda case: CaseStateTransition(case_id=case.id, from_status=None, to_status="INTAKE"),
        lambda case: HumanReview(case_id=case.id, reviewer_id="ankit", decision="approved"),
        lambda case: AuditEvent(case_id=case.id, event_type="test.event", actor="system"),
    ],
    ids=["case_state_transitions", "human_reviews", "audit_events"],
)
def test_append_only_tables_reject_delete(db_session, make_row):
    case = _make_case(db_session)
    row = make_row(case)
    db_session.add(row)
    db_session.flush()

    row_id = row.id
    table = row.__table__

    with pytest.raises(ProgrammingError, match="append-only"):
        db_session.execute(table.delete().where(table.c.id == row_id))
        db_session.flush()


def test_every_externally_referenced_entity_uses_a_uuid_primary_key():
    """threat-model.md §3.1: "UUID (not sequential integer) primary keys
    on every externally-referenced entity" — defense in depth against ID
    enumeration even behind auth (security.md). Checked against the real
    mapped column type for every model a URL or form field could name,
    not just the ones a reviewer happens to remember to check."""
    from sqlalchemy.dialects.postgresql import UUID

    from app.db import models

    externally_referenced = [
        models.Vendor, models.Case, models.EvidenceDocument, models.DocumentVersion,
        models.AgentRun, models.Claim, models.EvidenceItem, models.Finding,
        models.Conflict, models.ReInvestigation, models.HumanReview, models.AuditEvent,
    ]
    for model in externally_referenced:
        id_column = model.__table__.c.id
        assert isinstance(id_column.type, UUID), (
            f"{model.__name__}.id is {id_column.type!r}, not a UUID — "
            "sequential/serial IDs would make this entity enumerable."
        )
