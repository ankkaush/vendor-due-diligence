"""Read-side query helpers assembling what the review templates need.

Kept separate from app.web.routes so the shape of a case's evidence graph
(claims grouped by domain, which findings a conflict concerns, which
evidence backs a finding) is expressed once, in plain dataclasses, rather
than inline in a route handler or — worse — as query logic embedded in a
Jinja2 template. app.db.models deliberately doesn't declare every
relationship (Claim<->Finding, Conflict<->Finding, ...), so these are
explicit queries, not `.relationship` traversals.
"""

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
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
    FindingEvidenceItem,
    HumanReview,
    Vendor,
)


@dataclass
class ClaimView:
    claim: Claim
    finding: Finding
    agent_type: str
    evidence_items: list[EvidenceItem]


@dataclass
class ConflictView:
    conflict: Conflict
    claims: list[ClaimView]


@dataclass
class DocumentView:
    document: EvidenceDocument
    version: DocumentVersion
    text: str


@dataclass
class CaseDetailView:
    case: Case
    vendor_name: str
    documents: list[DocumentView]
    claims_by_domain: dict[str, list[ClaimView]] = field(default_factory=dict)
    conflicts: list[ConflictView] = field(default_factory=list)
    human_reviews: list[HumanReview] = field(default_factory=list)

    @property
    def can_review(self) -> bool:
        return self.case.status == "AWAITING_HUMAN_REVIEW"

    @property
    def all_finding_ids(self) -> list[UUID]:
        return [
            cv.finding.id for claims in self.claims_by_domain.values() for cv in claims
        ]


def list_cases(session: Session) -> list[tuple[Case, str]]:
    rows = session.execute(
        select(Case, Vendor.name).join(Vendor, Case.vendor_id == Vendor.id)
        .order_by(Case.created_at.desc())
    ).all()
    return [(case, vendor_name) for case, vendor_name in rows]


def get_case_detail(session: Session, case_id: UUID) -> CaseDetailView | None:
    case = session.get(Case, case_id)
    if case is None:
        return None
    vendor = session.get(Vendor, case.vendor_id)

    documents = []
    for document in (
        session.execute(select(EvidenceDocument).where(EvidenceDocument.case_id == case_id))
        .scalars().all()
    ):
        version = session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
        ).scalars().first()
        text = ""
        if version is not None and version.parsed_text_ref:
            text = storage.read_parsed_text(version.parsed_text_ref)
        documents.append(DocumentView(document=document, version=version, text=text))

    agent_type_by_run_id = {
        run.id: run.agent_type
        for run in session.execute(
            select(AgentRun).where(AgentRun.case_id == case_id)
        ).scalars().all()
    }

    claims_by_domain: dict[str, list[ClaimView]] = {}
    finding_by_id: dict[UUID, ClaimView] = {}
    for claim in (
        session.execute(select(Claim).where(Claim.case_id == case_id)).scalars().all()
    ):
        finding = session.execute(
            select(Finding).where(Finding.claim_id == claim.id)
        ).scalars().first()
        if finding is None:
            continue
        evidence_items = session.execute(
            select(EvidenceItem)
            .join(FindingEvidenceItem, FindingEvidenceItem.evidence_item_id == EvidenceItem.id)
            .where(FindingEvidenceItem.finding_id == finding.id)
        ).scalars().all()
        claim_view = ClaimView(
            claim=claim, finding=finding,
            agent_type=agent_type_by_run_id.get(claim.agent_run_id, "unknown"),
            evidence_items=list(evidence_items),
        )
        claims_by_domain.setdefault(claim.domain, []).append(claim_view)
        finding_by_id[finding.id] = claim_view

    conflicts = []
    for conflict in (
        session.execute(select(Conflict).where(Conflict.case_id == case_id)).scalars().all()
    ):
        finding_ids = session.execute(
            select(ConflictFinding.finding_id).where(ConflictFinding.conflict_id == conflict.id)
        ).scalars().all()
        conflicts.append(ConflictView(
            conflict=conflict,
            claims=[finding_by_id[fid] for fid in finding_ids if fid in finding_by_id],
        ))

    human_reviews = list(
        session.execute(
            select(HumanReview).where(HumanReview.case_id == case_id)
            .order_by(HumanReview.decided_at)
        ).scalars().all()
    )

    return CaseDetailView(
        case=case, vendor_name=vendor.name if vendor else "unknown",
        documents=documents, claims_by_domain=claims_by_domain,
        conflicts=conflicts, human_reviews=human_reviews,
    )
