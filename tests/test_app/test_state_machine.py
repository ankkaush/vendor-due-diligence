"""State machine tests, including the real-concurrency race test the
Phase 5 acceptance criterion (architecture.md) calls for: a case must
move through its transitions correctly and idempotently under concurrent
duplicate submission — proven with two actual OS threads racing on the
same case, not just two sequential calls that happen not to overlap.
"""

import threading

import pytest
from sqlalchemy.orm import Session

from app.db.base import engine
from app.db.models import Case, CaseStateTransition, Vendor
from app.state_machine import (
    TERMINAL_STATUSES,
    TRANSITIONS,
    InvalidTransitionError,
    transition_case,
)


def _make_case(session, status="VALIDATING") -> Case:
    vendor = Vendor(name="State Machine Test Vendor")
    session.add(vendor)
    session.flush()
    case = Case(vendor_id=vendor.id, status=status)
    session.add(case)
    session.flush()
    return case


def test_valid_transition_applies_and_records_history(db_session):
    case = _make_case(db_session, status="VALIDATING")
    applied = transition_case(
        db_session, case.id, from_status="VALIDATING", to_status="DOCUMENTS_READY"
    )
    assert applied is True

    refreshed = db_session.get(Case, case.id)
    assert refreshed.status == "DOCUMENTS_READY"

    history = db_session.query(CaseStateTransition).filter_by(case_id=case.id).one()
    assert history.from_status == "VALIDATING"
    assert history.to_status == "DOCUMENTS_READY"


def test_transition_from_wrong_actual_status_is_a_no_op_not_an_error(db_session):
    case = _make_case(db_session, status="DOCUMENTS_READY")  # not VALIDATING
    applied = transition_case(
        db_session, case.id, from_status="VALIDATING", to_status="DOCUMENTS_READY"
    )
    assert applied is False
    assert db_session.get(Case, case.id).status == "DOCUMENTS_READY"  # unchanged


def test_undefined_edge_is_rejected(db_session):
    case = _make_case(db_session, status="INTAKE")
    with pytest.raises(InvalidTransitionError):
        transition_case(db_session, case.id, from_status="INTAKE", to_status="FINALIZED")


def test_terminal_statuses_have_no_outgoing_edges():
    for status in TERMINAL_STATUSES:
        assert TRANSITIONS[status] == set()


def test_concurrent_duplicate_transition_attempts_exactly_one_wins():
    """The Phase 5 acceptance criterion, with real concurrency: two
    threads, each with its own DB session/connection, both attempt
    VALIDATING -> DOCUMENTS_READY on the SAME case at the same time.
    Exactly one must succeed; the database guard — not application
    locking — is what makes this safe.

    Deliberately does NOT use the db_session fixture: that fixture runs
    everything inside a SAVEPOINT nested in an outer transaction that is
    only ever rolled back (tests/conftest.py), so a case created through
    it is never actually committed and is invisible to the separate,
    genuinely independent connections this test needs — confirmed by
    actually hitting that as a failure (both threads got False, because
    neither could see the row at all) before writing it this way."""
    setup_connection = engine.connect()
    setup_session = Session(bind=setup_connection)
    case_id = None
    try:
        case = _make_case(setup_session, status="VALIDATING")
        setup_session.commit()  # must be really committed to be visible to other connections
        case_id = case.id

        results = []
        barrier = threading.Barrier(2)

        def attempt():
            connection = engine.connect()
            session = Session(bind=connection)
            try:
                barrier.wait(timeout=5)  # force genuine overlap, not a lucky sequential race
                applied = transition_case(
                    session, case_id, from_status="VALIDATING", to_status="DOCUMENTS_READY"
                )
                session.commit()
                results.append(applied)
            finally:
                session.close()
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert sorted(results) == [False, True], (
            f"expected exactly one winner and one no-op, got {results}"
        )

        final_case = setup_session.get(Case, case_id)
        setup_session.refresh(final_case)
        assert final_case.status == "DOCUMENTS_READY"
        transitions = (
            setup_session.query(CaseStateTransition).filter_by(case_id=case_id).all()
        )
        # Exactly one history row for this hop, not two — the loser never
        # wrote one, because it never passed the guard.
        assert len(transitions) == 1
    finally:
        # No cleanup delete here, on purpose, discovered while writing this
        # test: an early version tried to DELETE the case_state_transitions
        # rows this test committed, and the append-only trigger correctly
        # refused — case_state_transitions genuinely cannot be deleted, by
        # design (data-model.md), which transitively means a Case with any
        # transition history can't be deleted either (its FK is still
        # referenced). That's the schema working as intended, not a test
        # bug to work around — this test's rows are left in the local dev
        # database rather than force-deleting real safety guarantees to
        # make cleanup convenient. `docker compose down -v` resets the
        # local test DB entirely if accumulated test data ever matters.
        setup_session.close()
        setup_connection.close()
