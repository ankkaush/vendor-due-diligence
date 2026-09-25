"""Route tests for the human review UI (Phase 9).

Covers exactly the hard security rules security.md locks in for this
phase: auth on every route, CSRF on the one state-changing form, and
Jinja2 autoescaping actually holding for document/LLM-derived content —
plus the review-submission workflow itself (decision recorded, case
finalized, idempotent under a duplicate submit).
"""

from app.db.models import AgentRun, Case, Claim, DocumentVersion, EvidenceDocument, Finding, Vendor
from app.web.routes import router
from tests.test_web.conftest import REVIEWER_AUTH


def _build_reviewable_case(session, *, vendor_name="Test Vendor", status="AWAITING_HUMAN_REVIEW"):
    vendor = Vendor(name=vendor_name)
    session.add(vendor)
    session.flush()
    case = Case(vendor_id=vendor.id, status=status)
    session.add(case)
    session.flush()

    document = EvidenceDocument(
        case_id=case.id, filename="dpa.md", mime_type="text/markdown",
        doc_type="dpa", domain="privacy_ai_governance",
    )
    session.add(document)
    session.flush()
    doc_version = DocumentVersion(
        document_id=document.id, version_number=1, storage_ref="local://dpa.md",
        content_hash="deadbeef" * 8,
    )
    session.add(doc_version)
    session.flush()

    agent_run = AgentRun(
        case_id=case.id, agent_type="privacy_investigator", status="succeeded",
        model="claude-haiku-4-5-20251001",
    )
    session.add(agent_run)
    session.flush()

    claim = Claim(
        case_id=case.id, agent_run_id=agent_run.id, domain="privacy_ai_governance",
        claim_type="data_practice", subject="data retention", predicate="retention_period",
        value="30", unit="days", source_document_version_id=doc_version.id,
        source_location="Section 4",
        source_excerpt="<script>alert('xss')</script> delete within 30 days",
        evidence_requirement="",
    )
    session.add(claim)
    session.flush()
    finding = Finding(
        case_id=case.id, agent_run_id=agent_run.id, claim_id=claim.id,
        verification_status="supported",
        rationale="Stated directly in the DPA <script>alert('xss')</script>.",
    )
    session.add(finding)
    session.flush()

    return case, claim, finding


def _csrf_token(response) -> str:
    import re
    match = re.search(r'name="csrf_token" value="([^"]*)"', response.text)
    assert match, "csrf_token hidden field not found in response"
    return match.group(1)


# --- Auth --------------------------------------------------------------


def test_cases_list_requires_auth(client):
    response = client.get("/cases")
    assert response.status_code == 401


def test_cases_list_rejects_wrong_credentials(client):
    response = client.get("/cases", auth=("reviewer", "wrong-password"))
    assert response.status_code == 401


def test_cases_list_succeeds_with_correct_credentials(client, db_session):
    _build_reviewable_case(db_session, vendor_name="Auth Test Vendor")
    response = client.get("/cases", auth=REVIEWER_AUTH)
    assert response.status_code == 200
    assert "Auth Test Vendor" in response.text


def test_case_detail_requires_auth(client, db_session):
    case, _, _ = _build_reviewable_case(db_session)
    response = client.get(f"/cases/{case.id}")
    assert response.status_code == 401


def test_case_detail_404_for_unknown_case(client):
    import uuid

    response = client.get(f"/cases/{uuid.uuid4()}", auth=REVIEWER_AUTH)
    assert response.status_code == 404


# --- Health check (Phase 12) ------------------------------------------


def test_healthz_requires_no_auth_and_reports_healthy(client):
    """deployment.md: infrastructure hitting the health check shouldn't
    need reviewer credentials — and a real DB round-trip, not a bare
    200, is what makes this a meaningful deploy/rollback signal."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


# --- XSS / autoescaping --------------------------------------------------


def test_no_separate_unauthenticated_document_route_exists():
    """threat-model.md §3.6: "Every document fetch is gated by the same
    auth + case_id check as the case view itself — no separate
    unauthenticated file route." Verified structurally against the real
    route table: document text is embedded only in the already-auth-
    gated /cases/{case_id} response (app/web/queries.py), and no other
    route pattern exists at all — not a claim checked by reading the
    code, but an assertion against the actual registered routes."""
    paths = {r.path for r in router.routes}
    assert paths == {
        "/", "/healthz", "/cases", "/cases/{case_id}", "/cases/{case_id}/review",
    }
    for path in paths:
        assert "document" not in path
        assert "file" not in path
        assert "download" not in path


def test_document_derived_content_is_escaped_not_rendered_raw(client, db_session):
    """security.md: 'Jinja2 autoescaping stays on everywhere ... Prevents
    stored XSS in the review UI' — checked against a literal <script> tag
    in claim rationale/source_excerpt, not just claimed."""
    case, _, _ = _build_reviewable_case(db_session)
    response = client.get(f"/cases/{case.id}", auth=REVIEWER_AUTH)
    assert response.status_code == 200
    assert "<script>alert('xss')</script>" not in response.text
    assert "&lt;script&gt;" in response.text


# --- Review submission ----------------------------------------------------


def test_review_form_present_when_awaiting_review(client, db_session):
    case, _, _ = _build_reviewable_case(db_session, status="AWAITING_HUMAN_REVIEW")
    response = client.get(f"/cases/{case.id}", auth=REVIEWER_AUTH)
    assert "Submit review and finalize case" in response.text
    assert response.cookies.get("csrf_token") is not None


def test_review_form_absent_when_not_awaiting_review(client, db_session):
    case, _, _ = _build_reviewable_case(db_session, status="CLASSIFYING")
    response = client.get(f"/cases/{case.id}", auth=REVIEWER_AUTH)
    assert "Submit review and finalize case" not in response.text


def test_review_submission_requires_csrf_token(client, db_session):
    case, _, _ = _build_reviewable_case(db_session)
    response = client.post(
        f"/cases/{case.id}/review",
        data={"csrf_token": "not-a-real-token", "decision": "approved"},
        auth=REVIEWER_AUTH,
    )
    assert response.status_code == 403


def test_review_submission_requires_auth(client, db_session):
    case, _, _ = _build_reviewable_case(db_session)
    response = client.post(
        f"/cases/{case.id}/review", data={"csrf_token": "x", "decision": "approved"},
    )
    assert response.status_code == 401


def test_review_submission_rejects_invalid_decision(client, db_session):
    case, _, _ = _build_reviewable_case(db_session)
    get_response = client.get(f"/cases/{case.id}", auth=REVIEWER_AUTH)
    token = _csrf_token(get_response)
    client.cookies.set("csrf_token", token)

    response = client.post(
        f"/cases/{case.id}/review",
        data={"csrf_token": token, "decision": "not_a_real_decision"},
        auth=REVIEWER_AUTH,
    )
    assert response.status_code == 422


def test_review_submission_finalizes_case_and_records_decision(client, db_session):
    case, _, finding = _build_reviewable_case(db_session)
    get_response = client.get(f"/cases/{case.id}", auth=REVIEWER_AUTH)
    token = _csrf_token(get_response)
    client.cookies.set("csrf_token", token)

    response = client.post(
        f"/cases/{case.id}/review",
        data={
            "csrf_token": token, "decision": "approved", "comments": "Looks good.",
            "override_finding_ids": [str(finding.id)],
        },
        auth=REVIEWER_AUTH,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/cases/{case.id}"

    db_session.refresh(case)
    assert case.status == "FINALIZED"
    assert case.finalized_at is not None

    detail_response = client.get(f"/cases/{case.id}", auth=REVIEWER_AUTH)
    assert "approved" in detail_response.text
    assert "Looks good." in detail_response.text
    assert "Submit review and finalize case" not in detail_response.text


def test_duplicate_review_submission_is_rejected_not_double_recorded(client, db_session):
    """Idempotency under a double-submit — reuses the same guarded
    transition_case() Phase 5 already proved under real concurrency
    (tests/test_app/test_state_machine.py), not a new mechanism."""
    case, _, _ = _build_reviewable_case(db_session)
    get_response = client.get(f"/cases/{case.id}", auth=REVIEWER_AUTH)
    token = _csrf_token(get_response)
    client.cookies.set("csrf_token", token)

    first = client.post(
        f"/cases/{case.id}/review",
        data={"csrf_token": token, "decision": "approved"},
        auth=REVIEWER_AUTH,
        follow_redirects=False,
    )
    assert first.status_code == 303

    second = client.post(
        f"/cases/{case.id}/review",
        data={"csrf_token": token, "decision": "rejected"},
        auth=REVIEWER_AUTH,
        follow_redirects=False,
    )
    assert second.status_code == 409

    from app.db.models import HumanReview

    reviews = (
        db_session.query(HumanReview).filter_by(case_id=case.id).all()
    )
    assert len(reviews) == 1
    assert reviews[0].decision == "approved"
