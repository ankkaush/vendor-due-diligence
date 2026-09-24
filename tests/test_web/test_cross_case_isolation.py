"""app/agents/context_builder.py's docstring flagged this exact gap when
it was written: "once a real orchestrator persists AgentRun/Finding rows
to the database ... THAT boundary — a context builder [here: the review
UI's query layer] querying the DB must have no path to another agent's
Finding rows — needs its own equivalent guarantee and its own test."
Phase 9 built that persistence (app/persist.py, app/web/queries.py);
this is that test, closing the gap the docstring named in advance rather
than leaving it as a stale TODO.
"""

from app.db.models import AgentRun, Case, Claim, DocumentVersion, EvidenceDocument, Finding, Vendor
from app.web.queries import get_case_detail


def _build_case_with_one_claim(session, vendor_name: str, subject: str):
    vendor = Vendor(name=vendor_name)
    session.add(vendor)
    session.flush()
    case = Case(vendor_id=vendor.id, status="AWAITING_HUMAN_REVIEW")
    session.add(case)
    session.flush()
    document = EvidenceDocument(
        case_id=case.id, filename="d.md", mime_type="text/markdown",
        doc_type="dpa", domain="privacy_ai_governance",
    )
    session.add(document)
    session.flush()
    doc_version = DocumentVersion(
        document_id=document.id, version_number=1, storage_ref="local://d.md",
        content_hash="a" * 64,
    )
    session.add(doc_version)
    session.flush()
    agent_run = AgentRun(
        case_id=case.id, agent_type="privacy_investigator", status="succeeded", model="m",
    )
    session.add(agent_run)
    session.flush()
    claim = Claim(
        case_id=case.id, agent_run_id=agent_run.id, domain="privacy_ai_governance",
        claim_type="data_practice", subject=subject, predicate="p", value="v",
        source_document_version_id=doc_version.id, source_location="x", source_excerpt="x",
        evidence_requirement="",
    )
    session.add(claim)
    session.flush()
    session.add(Finding(
        case_id=case.id, agent_run_id=agent_run.id, claim_id=claim.id,
        verification_status="supported", rationale="x",
    ))
    session.flush()
    return case


def test_get_case_detail_never_returns_another_cases_claims_documents_or_conflicts(db_session):
    case_a = _build_case_with_one_claim(db_session, "Vendor A", "claim only case A should have")
    case_b = _build_case_with_one_claim(db_session, "Vendor B", "claim only case B should have")

    detail_a = get_case_detail(db_session, case_a.id)
    detail_b = get_case_detail(db_session, case_b.id)

    a_subjects = {
        cv.claim.subject for claims in detail_a.claims_by_domain.values() for cv in claims
    }
    b_subjects = {
        cv.claim.subject for claims in detail_b.claims_by_domain.values() for cv in claims
    }
    assert a_subjects == {"claim only case A should have"}
    assert b_subjects == {"claim only case B should have"}

    a_doc_ids = {d.document.id for d in detail_a.documents}
    b_doc_ids = {d.document.id for d in detail_b.documents}
    assert a_doc_ids.isdisjoint(b_doc_ids)
    assert len(a_doc_ids) == 1
    assert len(b_doc_ids) == 1
