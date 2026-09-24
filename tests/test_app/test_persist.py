"""Tests for app.persist — the bridge from in-memory AgentResult /
ReconciliationResult into the DB evidence graph (Phase 9). Runs against
the real local Postgres (tests/conftest.py's db_session), not mocked,
since this module's entire job is getting the ORM writes right.
"""

from app.agents.schema import AgentResult
from app.db.models import (
    AgentRun,
    Case,
    Claim,
    Conflict,
    ConflictFinding,
    DocumentVersion,
    EvidenceDocument,
    EvidenceItem,
    Finding,
    ReInvestigation,
    Vendor,
)
from app.persist import persist_agent_result, persist_reconciliation
from app.reconcile import Conflict as ConflictData
from app.reconcile import ReconciliationResult
from app.reinvestigate import ReinvestigationRecord


def _make_case_with_document(session, *, filename="dpa.md", domain="privacy_ai_governance"):
    vendor = Vendor(name="Persist Test Vendor")
    session.add(vendor)
    session.flush()
    case = Case(vendor_id=vendor.id, status="INVESTIGATING")
    session.add(case)
    session.flush()
    document = EvidenceDocument(
        case_id=case.id, filename=filename, mime_type="text/markdown",
        doc_type="dpa", domain=domain,
    )
    session.add(document)
    session.flush()
    doc_version = DocumentVersion(
        document_id=document.id, version_number=1, storage_ref=f"local://{filename}",
        content_hash="deadbeef" * 8,
    )
    session.add(doc_version)
    session.flush()
    return case, doc_version


def _claim_dict(**overrides):
    base = {
        "subject": "data retention", "predicate": "retention_period", "value": "30",
        "unit": "days", "temporal_scope": None, "domain": "privacy_ai_governance",
        "claim_type": "data_practice", "source_document_id": "doc-dpa",
        "source_location": "Section 4", "source_excerpt": "delete within 30 days",
        "verification_status": "supported", "rationale": "Stated directly in the DPA.",
        "evidence": [{"document_id": "doc-dpa", "location": "Section 4", "excerpt": "30 days"}],
    }
    base.update(overrides)
    return base


def test_persist_agent_result_creates_agent_run_claim_finding_and_evidence(db_session):
    case, doc_version = _make_case_with_document(db_session)
    result = AgentResult(
        claims=[_claim_dict()], injection_detected=False, injection_note="",
        input_tokens=100, output_tokens=50, model="claude-haiku-4-5-20251001",
    )

    agent_run, pairs = persist_agent_result(
        db_session, case=case, agent_type="privacy_investigator",
        model="claude-haiku-4-5-20251001", result=result,
        document_version_by_doc_id={"doc-dpa": doc_version}, cost_usd=0.001234,
    )

    assert agent_run.id is not None
    assert agent_run.input_tokens == 100
    assert float(agent_run.cost_usd) == 0.001234
    assert len(pairs) == 1
    claim, finding = pairs[0]

    persisted_claim = db_session.get(Claim, claim.id)
    assert persisted_claim.subject == "data retention"
    assert persisted_claim.source_document_version_id == doc_version.id
    assert persisted_claim.agent_run_id == agent_run.id

    persisted_finding = db_session.get(Finding, finding.id)
    assert persisted_finding.verification_status == "supported"
    assert persisted_finding.claim_id == claim.id

    evidence_items = (
        db_session.query(EvidenceItem).filter_by(claim_id=claim.id).all()
    )
    assert len(evidence_items) == 1
    assert evidence_items[0].document_version_id == doc_version.id


def test_persist_agent_result_evidence_requirement_gap_is_recorded_honestly(db_session):
    """FINDINGS_INPUT_SCHEMA never asks the model for evidence_requirement
    (a ground-truth-only field per ADR-008) but Claim.evidence_requirement
    is NOT NULL — app.persist's module docstring records this gap rather
    than fabricating a plausible-looking value."""
    case, doc_version = _make_case_with_document(db_session)
    result = AgentResult(
        claims=[_claim_dict()], injection_detected=False, injection_note="",
        input_tokens=10, output_tokens=5, model="m",
    )
    _, pairs = persist_agent_result(
        db_session, case=case, agent_type="privacy_investigator", model="m",
        result=result, document_version_by_doc_id={"doc-dpa": doc_version},
    )
    claim, _ = pairs[0]
    assert db_session.get(Claim, claim.id).evidence_requirement == ""


def test_persist_reconciliation_links_conflict_to_original_findings_without_mutating_them(
    db_session,
):
    """Design choice documented in app.persist's module docstring: a
    resolved conflict never overwrites or duplicates a Finding — the
    reconciler's read lives on Conflict, findings stay exactly what the
    agent concluded."""
    case, doc_version = _make_case_with_document(db_session)
    security_result = AgentResult(
        claims=[_claim_dict(domain="security", source_document_id="doc-dpa")],
        injection_detected=False, injection_note="", input_tokens=10, output_tokens=5, model="m",
    )
    privacy_result = AgentResult(
        claims=[_claim_dict(value="60", source_document_id="doc-dpa")],
        injection_detected=False, injection_note="", input_tokens=10, output_tokens=5, model="m",
    )
    _, security_pairs = persist_agent_result(
        db_session, case=case, agent_type="security_investigator", model="m",
        result=security_result, document_version_by_doc_id={"doc-dpa": doc_version},
    )
    _, privacy_pairs = persist_agent_result(
        db_session, case=case, agent_type="privacy_investigator", model="m",
        result=privacy_result, document_version_by_doc_id={"doc-dpa": doc_version},
    )
    claim_by_pooled_id = {"security-0": security_pairs[0][0], "privacy-0": privacy_pairs[0][0]}
    finding_by_claim_id = {
        security_pairs[0][0].id: security_pairs[0][1],
        privacy_pairs[0][0].id: privacy_pairs[0][1],
    }

    reconciliation = ReconciliationResult(
        reconciled_claims=[], semantic_input_tokens=0, semantic_output_tokens=0,
        reinvestigation_records=[],
        conflicts=[ConflictData(
            claim_ids=["security-0", "privacy-0"], conflict_type="cross_domain_conflict",
            status="open", resolution_method="semantic_adjudication",
            resolution_rationale="Low-confidence, thematically related tension.",
        )],
    )

    conflicts = persist_reconciliation(
        db_session, case=case, model="m", reconciliation=reconciliation,
        claim_by_pooled_id=claim_by_pooled_id, finding_by_claim_id=finding_by_claim_id,
    )

    assert len(conflicts) == 1
    conflict = db_session.get(Conflict, conflicts[0].id)
    assert conflict.status == "open"
    assert conflict.resolution_rationale == "Low-confidence, thematically related tension."

    links = db_session.query(ConflictFinding).filter_by(conflict_id=conflict.id).all()
    assert {link.finding_id for link in links} == {
        security_pairs[0][1].id, privacy_pairs[0][1].id,
    }

    # Untouched — the whole point of not mutating Findings on a conflict.
    assert db_session.get(Finding, security_pairs[0][1].id).verification_status == "supported"
    assert db_session.get(Finding, privacy_pairs[0][1].id).verification_status == "supported"


def test_persist_reconciliation_creates_reinvestigation_agent_run(db_session):
    case, doc_version = _make_case_with_document(db_session)
    result = AgentResult(
        claims=[
            _claim_dict(subject="retention", value="30"),
            _claim_dict(subject="retention", value="60"),
        ],
        injection_detected=False, injection_note="", input_tokens=10, output_tokens=5, model="m",
    )
    _, pairs = persist_agent_result(
        db_session, case=case, agent_type="privacy_investigator", model="m",
        result=result, document_version_by_doc_id={"doc-dpa": doc_version},
    )
    claim_by_pooled_id = {"privacy-0": pairs[0][0], "privacy-1": pairs[1][0]}
    finding_by_claim_id = {pairs[0][0].id: pairs[0][1], pairs[1][0].id: pairs[1][1]}

    reconciliation = ReconciliationResult(
        reconciled_claims=[], semantic_input_tokens=0, semantic_output_tokens=0,
        reinvestigation_records=[ReinvestigationRecord(
            conflict_claim_ids=("privacy-0", "privacy-1"), agent_type="privacy_investigator",
            resolved=True, explanation="Same document, different sections; 60 supersedes 30.",
            resolution_status="contradicted", input_tokens=200, output_tokens=80,
        )],
        conflicts=[ConflictData(
            claim_ids=["privacy-0", "privacy-1"], conflict_type="direct_contradiction",
            status="resolved", resolution_method="reinvestigation",
            resolution_rationale="Same document, different sections; 60 supersedes 30.",
        )],
    )

    conflicts = persist_reconciliation(
        db_session, case=case, model="claude-haiku-4-5-20251001",
        reconciliation=reconciliation, claim_by_pooled_id=claim_by_pooled_id,
        finding_by_claim_id=finding_by_claim_id,
    )

    reinvestigation = (
        db_session.query(ReInvestigation).filter_by(conflict_id=conflicts[0].id).one()
    )
    assert reinvestigation.outcome == "Same document, different sections; 60 supersedes 30."
    run = db_session.get(AgentRun, reinvestigation.agent_run_id)
    assert run.agent_type == "privacy_investigator"
    assert run.input_tokens == 200
    assert run.output_tokens == 80
