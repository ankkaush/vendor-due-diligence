"""ORM models implementing the evidence/state model from docs/data-model.md.

Enum string values are deliberately identical to eval/schema/ground_truth.schema.json
wherever both describe the same concept (doc_type, domain, claim_type,
verification_status, conflict_type) — ADR-008 already established that the
ground-truth ontology reuses this schema; this is that reuse made literal.
issue_type/is_planted_issue/expected_handling_notes are eval-only concepts
and correctly do NOT appear here (ADR-008's explicit boundary).

Three tables are append-only by design (case_state_transitions,
human_reviews, audit_events): UPDATE and DELETE are blocked at the database
level via triggers (see alembic/versions/0001_initial_schema.py), not left
to application-level discipline alone — the same "deterministic enforcement
over convention" principle used for agent context boundaries (ADR-007)
applies here to audit-trail integrity.

case.status intentionally has no SECURITY_RUNNING/PRIVACY_RUNNING sub-states
(architecture.md's diagram shows these as a parallel note, not literal case
states) — per-agent progress lives on AgentRun.status instead, keeping the
workflow-state vs. agent-state distinction from data-model.md exact.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# --- Enums --------------------------------------------------------------
# create_type=False: types are created explicitly in the migration (one
# CREATE TYPE per enum, reused across columns) rather than implicitly
# per-column, so Alembic's DDL is explicit and reviewable.

CaseStatus = ENUM(
    "INTAKE", "VALIDATING", "VALIDATION_FAILED", "DOCUMENTS_READY", "CLASSIFYING",
    "INVESTIGATING", "INVESTIGATIONS_COMPLETE", "RECONCILING", "REINVESTIGATING",
    "RECONCILING_POST_REINVESTIGATION", "SYNTHESIZING", "AWAITING_HUMAN_REVIEW",
    "FINALIZED", "FAILED", "CANCELLED",
    name="case_status", create_type=False,
)

DocType = ENUM(
    "security_questionnaire", "security_whitepaper", "soc_report", "dpa",
    "privacy_policy", "ai_governance_doc", "subprocessor_list", "contract_sla",
    "pentest_attestation", "other",
    name="doc_type", create_type=False,
)

DocumentDomain = ENUM(
    "security", "privacy_ai_governance", "both",
    name="document_domain", create_type=False,
)
ClaimDomain = ENUM(
    "security", "privacy_ai_governance",
    name="claim_domain", create_type=False,
)

ClaimType = ENUM(
    "certification", "policy_statement", "sla_metric", "data_practice",
    "subprocessor_disclosure", "technical_control", "other",
    name="claim_type", create_type=False,
)

AgentType = ENUM(
    "security_investigator", "privacy_investigator", "single_agent_baseline",
    name="agent_type", create_type=False,
)

AgentRunStatus = ENUM(
    "pending", "running", "succeeded", "failed",
    name="agent_run_status", create_type=False,
)

VerificationStatus = ENUM(
    "supported", "contradicted", "unverified", "ambiguous",
    name="verification_status", create_type=False,
)

ConflictType = ENUM(
    "direct_contradiction", "subtle_contradiction", "cross_domain_conflict", "version_conflict",
    name="conflict_type", create_type=False,
)

ConflictStatus = ENUM(
    "open", "reinvestigating", "escalated", "resolved",
    name="conflict_status", create_type=False,
)

HumanDecision = ENUM(
    "approved", "rejected", "conditional", "needs_more_info",
    name="human_decision", create_type=False,
)


# --- Core entities --------------------------------------------------------

class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cases: Mapped[list["Case"]] = relationship(back_populates="vendor")


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = _uuid_pk()
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    status: Mapped[str] = mapped_column(CaseStatus, nullable=False, server_default="INTAKE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vendor: Mapped["Vendor"] = relationship(back_populates="cases")
    documents: Mapped[list["EvidenceDocument"]] = relationship(back_populates="case")


class CaseStateTransition(Base):
    """Append-only. Control-flow state the orchestrator queries directly —
    distinct from AuditEvent, which is a general observability log covering
    every entity type, not just case status (see data-model.md)."""

    __tablename__ = "case_state_transitions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(CaseStatus, nullable=True)
    to_status: Mapped[str] = mapped_column(CaseStatus, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceDocument(Base):
    __tablename__ = "evidence_documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(DocType, nullable=False)
    domain: Mapped[str] = mapped_column(DocumentDomain, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    case: Mapped["Case"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_documents.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    storage_ref: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_text_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["EvidenceDocument"] = relationship(back_populates="versions")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        # Idempotency (architecture.md): at most one non-terminal AgentRun
        # per (case_id, agent_type), enforced by the database, not just
        # application logic. Implemented as a partial unique index in the
        # migration (Postgres partial indexes aren't expressible directly
        # via a portable SQLAlchemy Index() with a dialect-neutral API, so
        # it's added with raw DDL alongside this table's CREATE).
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    agent_type: Mapped[str] = mapped_column(AgentType, nullable=False)
    status: Mapped[str] = mapped_column(AgentRunStatus, nullable=False, server_default="pending")
    model: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    retry_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    domain: Mapped[str] = mapped_column(ClaimDomain, nullable=False)
    claim_type: Mapped[str] = mapped_column(ClaimType, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    source_location: Mapped[str] = mapped_column(Text, nullable=False)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_requirement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    location: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False)
    verification_status: Mapped[str] = mapped_column(VerificationStatus, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FindingEvidenceItem(Base):
    """Join table: which EvidenceItems a Finding actually cites. A proper
    FK-backed join table rather than an array column, so every citation is
    referentially guaranteed to point at a real EvidenceItem — the
    evidence-grounding requirement (evaluation.md) enforced structurally."""

    __tablename__ = "finding_evidence_items"

    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"), primary_key=True)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_items.id"), primary_key=True
    )


class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    conflict_type: Mapped[str] = mapped_column(ConflictType, nullable=False)
    status: Mapped[str] = mapped_column(ConflictStatus, nullable=False, server_default="open")
    resolution_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConflictFinding(Base):
    """Join table linking a Conflict to the >=2 Findings that disagree."""

    __tablename__ = "conflict_findings"

    conflict_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conflicts.id"), primary_key=True)
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"), primary_key=True)


class ReInvestigation(Base):
    __tablename__ = "reinvestigations"
    __table_args__ = (
        # Decision #13 (max one re-investigation round) enforced at the
        # schema level, not just application logic: a second row for the
        # same conflict is a constraint violation, not a possibility the
        # orchestrator has to remember to prevent.
        UniqueConstraint("conflict_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    conflict_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conflicts.id"), nullable=False)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HumanReview(Base):
    """Append-only (see module docstring). A reviewer overriding a prior
    decision creates a NEW row; it never updates an existing one."""

    __tablename__ = "human_reviews"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(HumanDecision, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HumanReviewOverride(Base):
    """Join table: which Findings a given HumanReview explicitly overrode."""

    __tablename__ = "human_review_overrides"

    human_review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("human_reviews.id"), primary_key=True
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"), primary_key=True)


class AuditEvent(Base):
    """Append-only (see module docstring). General observability/audit
    log across every entity type — case → agent_run → llm_call → evidence →
    finding → conflict → reinvestigation → human_decision, per
    observability.md's trace hierarchy. Distinct from CaseStateTransition,
    which the orchestrator uses for control flow, not just history."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
