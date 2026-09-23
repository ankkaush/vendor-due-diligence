"""Acceptance test for Phase 4: the full evidence chain from data-model.md,

    Claim -> EvidenceItem -> SourceDocument(Version) -> Location ->
    AgentFinding -> VerificationStatus -> HumanDecision

works end to end with real sample rows, and that cross-case isolation
holds at the query level (threat-model.md section 3.3/3.5).
"""

import uuid

from app.db.models import (
    AgentRun,
    AuditEvent,
    Case,
    CaseStateTransition,
    Claim,
    Conflict,
    ConflictFinding,
    DocumentVersion,
    EvidenceDocument,
    EvidenceItem,
    Finding,
    FindingEvidenceItem,
    HumanReview,
    HumanReviewOverride,
    ReInvestigation,
    Vendor,
)


def _build_full_case(session, vendor_name: str):
    """Build one complete case through every entity in the evidence chain,
    returning the key objects a test might want to assert against."""
    vendor = Vendor(name=vendor_name)
    session.add(vendor)
    session.flush()

    case = Case(vendor_id=vendor.id, status="INTAKE")
    session.add(case)
    session.flush()

    session.add(CaseStateTransition(case_id=case.id, from_status=None, to_status="INTAKE"))

    document = EvidenceDocument(
        case_id=case.id,
        filename="dpa.md",
        mime_type="text/markdown",
        doc_type="dpa",
        domain="privacy_ai_governance",
    )
    session.add(document)
    session.flush()

    doc_version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        storage_ref="local://dpa.md",
        content_hash="deadbeef" * 8,
    )
    session.add(doc_version)
    session.flush()

    agent_run = AgentRun(
        case_id=case.id,
        agent_type="privacy_investigator",
        status="succeeded",
        model="claude-haiku-4-5-20251001",
    )
    session.add(agent_run)
    session.flush()

    claim = Claim(
        case_id=case.id,
        agent_run_id=agent_run.id,
        domain="privacy_ai_governance",
        claim_type="data_practice",
        subject="data retention after termination",
        predicate="retention_period",
        value="30",
        unit="days",
        source_document_version_id=doc_version.id,
        source_location="Section 4",
        source_excerpt="Vendor shall delete all customer personal data within 30 days.",
        evidence_requirement="None beyond the DPA itself.",
    )
    session.add(claim)
    session.flush()

    evidence_item = EvidenceItem(
        claim_id=claim.id,
        document_version_id=doc_version.id,
        location="Section 4",
        excerpt="delete all customer personal data within 30 days",
        content_hash="cafebabe" * 8,
    )
    session.add(evidence_item)
    session.flush()

    finding = Finding(
        case_id=case.id,
        agent_run_id=agent_run.id,
        claim_id=claim.id,
        verification_status="supported",
        rationale="DPA states the retention period directly; no contradicting document found.",
    )
    session.add(finding)
    session.flush()

    session.add(FindingEvidenceItem(finding_id=finding.id, evidence_item_id=evidence_item.id))

    conflict = Conflict(case_id=case.id, conflict_type="direct_contradiction", status="open")
    session.add(conflict)
    session.flush()
    session.add(ConflictFinding(conflict_id=conflict.id, finding_id=finding.id))

    reinvestigation_run = AgentRun(
        case_id=case.id,
        agent_type="privacy_investigator",
        status="succeeded",
        model="claude-haiku-4-5-20251001",
    )
    session.add(reinvestigation_run)
    session.flush()
    session.add(
        ReInvestigation(
            conflict_id=conflict.id,
            agent_run_id=reinvestigation_run.id,
            outcome="Unresolved within this package; escalated to human review.",
        )
    )

    human_review = HumanReview(
        case_id=case.id,
        reviewer_id="ankit",
        decision="conditional",
        comments="Retention conflict needs vendor clarification before approval.",
    )
    session.add(human_review)
    session.flush()
    session.add(HumanReviewOverride(human_review_id=human_review.id, finding_id=finding.id))

    session.add(
        AuditEvent(
            case_id=case.id,
            event_type="human_review.decided",
            actor=f"human:{human_review.reviewer_id}",
            payload={"decision": human_review.decision},
        )
    )
    session.flush()

    return {
        "vendor": vendor,
        "case": case,
        "document": document,
        "doc_version": doc_version,
        "claim": claim,
        "evidence_item": evidence_item,
        "finding": finding,
        "conflict": conflict,
        "human_review": human_review,
    }


def test_full_evidence_chain_end_to_end(db_session):
    """Claim -> EvidenceItem -> DocumentVersion -> Finding ->
    VerificationStatus -> HumanDecision, with sample data at every step."""
    built = _build_full_case(db_session, "Chain Test Vendor")

    # Traceability: every conclusion must be walkable back to its evidence.
    finding = db_session.get(Finding, built["finding"].id)
    assert finding.verification_status == "supported"

    claim = db_session.get(Claim, finding.claim_id)
    assert claim.id == built["claim"].id

    doc_version = db_session.get(DocumentVersion, claim.source_document_version_id)
    assert doc_version.id == built["doc_version"].id
    assert doc_version.document_id == built["document"].id

    fei = (
        db_session.query(FindingEvidenceItem)
        .filter_by(finding_id=finding.id)
        .one()
    )
    evidence_item = db_session.get(EvidenceItem, fei.evidence_item_id)
    assert evidence_item.document_version_id == doc_version.id

    human_review = db_session.get(HumanReview, built["human_review"].id)
    assert human_review.case_id == built["case"].id
    override = (
        db_session.query(HumanReviewOverride)
        .filter_by(human_review_id=human_review.id)
        .one()
    )
    assert override.finding_id == finding.id


def test_cross_case_isolation(db_session):
    """A query scoped to one case must never return another case's claims
    — threat-model.md's cross-case-leakage mitigation, proven, not just
    asserted in a doc."""
    case_a = _build_full_case(db_session, "Vendor A")
    case_b = _build_full_case(db_session, "Vendor B")

    claims_in_a = db_session.query(Claim).filter_by(case_id=case_a["case"].id).all()
    claims_in_b = db_session.query(Claim).filter_by(case_id=case_b["case"].id).all()

    assert len(claims_in_a) == 1
    assert len(claims_in_b) == 1
    assert claims_in_a[0].id != claims_in_b[0].id
    assert claims_in_a[0].case_id != claims_in_b[0].case_id


def test_claim_records_which_agent_run_extracted_it(db_session):
    """ADR-004: independent claim extraction must be traceable per agent
    run, so extraction agreement/disagreement is queryable directly."""
    built = _build_full_case(db_session, "ADR-004 Test Vendor")
    claim = db_session.get(Claim, built["claim"].id)
    agent_run = db_session.get(AgentRun, claim.agent_run_id)
    assert agent_run.agent_type == "privacy_investigator"


def test_nonexistent_source_document_version_is_rejected(db_session):
    """FK integrity: a claim cannot reference a document version that
    doesn't exist."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    vendor = Vendor(name="FK Test Vendor")
    db_session.add(vendor)
    db_session.flush()
    case = Case(vendor_id=vendor.id)
    db_session.add(case)
    db_session.flush()
    agent_run = AgentRun(
        case_id=case.id, agent_type="security_investigator",
        status="succeeded", model="claude-haiku-4-5-20251001",
    )
    db_session.add(agent_run)
    db_session.flush()

    bad_claim = Claim(
        case_id=case.id,
        agent_run_id=agent_run.id,
        domain="security",
        claim_type="technical_control",
        subject="x", predicate="y", value="z",
        source_document_version_id=uuid.uuid4(),  # does not exist
        source_location="nowhere",
        source_excerpt="n/a",
        evidence_requirement="n/a",
    )
    db_session.add(bad_claim)
    with pytest.raises(IntegrityError):
        db_session.flush()
