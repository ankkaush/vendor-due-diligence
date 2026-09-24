"""Bridges the in-memory agent/reconciliation output (app.agents.schema.AgentResult,
app.reconcile.ReconciliationResult) into the DB evidence graph (app.db.models),
so a case has something for the review UI (Phase 9) to actually show.

No prior phase needed this: Phase 6/7's eval runners never touched the DB
(scoring runs against raw JSON), and Phase 8's reconciliation likewise
operated purely on in-memory PooledClaim objects. This module is that
missing bridge, written now because Phase 9 is the first thing that
actually needs a case's real findings sitting in Postgres.

Design choice, not an oversight: reconciliation's conclusion (whether from
deterministic-conflict re-investigation or semantic adjudication) is never
written as a mutated or duplicated Finding row. data-model.md's own
mutability table already draws this line — "Claim/EvidenceItem/Conflict
graph: append-only for facts; mutable only for conflict resolution
status" — so a Finding stays exactly what one AgentRun concluded, and the
reconciler's read lives on Conflict (status/resolution_rationale) instead,
linked back to the original Findings via ConflictFinding. The review UI
renders both side by side, which is arguably better for a human reviewer
than a silently overwritten status — they see the tension a conflict
represents, not just its resolution.

A related, real gap surfaced here, not hidden: Claim.evidence_requirement
is NOT NULL in the schema and reused by eval/schema/ground_truth.schema.json,
but app.agents.schema.FINDINGS_INPUT_SCHEMA never asks the model for it —
no phase's agent prompt produces this field. Persisted here as an empty
string with this comment as the record of why, rather than a fabricated
value that would misrepresent what the pipeline actually extracted.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.agents.schema import AgentResult
from app.audit import record_event
from app.db.models import (
    AgentRun,
    Case,
    Claim,
    Conflict,
    ConflictFinding,
    DocumentVersion,
    EvidenceItem,
    Finding,
    FindingEvidenceItem,
    ReInvestigation,
)
from app.reconcile import ReconciliationResult

EVIDENCE_REQUIREMENT_NOT_EXTRACTED = ""  # see module docstring


def persist_agent_result(
    session: Session,
    *,
    case: Case,
    agent_type: str,
    model: str,
    result: AgentResult,
    document_version_by_doc_id: dict[str, DocumentVersion],
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    cost_usd: float | None = None,
    actor: str = "system",
) -> tuple[AgentRun, list[tuple[Claim, Finding]]]:
    """Persists one completed agent run and every claim/finding/evidence
    item it produced. Returns the AgentRun plus (Claim, Finding) pairs in
    the same order as result.claims, so a caller pooling claims the same
    way app.reconcile.pool_claims does can build a stable id -> Claim map."""
    now = datetime.now(UTC)
    agent_run = AgentRun(
        case_id=case.id, agent_type=agent_type, status="succeeded", model=model,
        started_at=started_at or now, completed_at=completed_at or now,
        input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        cost_usd=cost_usd, retry_count=0,
    )
    session.add(agent_run)
    session.flush()

    pairs: list[tuple[Claim, Finding]] = []
    for c in result.claims:
        source_version = document_version_by_doc_id[c["source_document_id"]]
        claim = Claim(
            case_id=case.id, agent_run_id=agent_run.id, domain=c["domain"],
            claim_type=c["claim_type"], subject=c["subject"], predicate=c["predicate"],
            value=c["value"], unit=c.get("unit"), temporal_scope=c.get("temporal_scope"),
            source_document_version_id=source_version.id, source_location=c["source_location"],
            source_excerpt=c["source_excerpt"],
            evidence_requirement=EVIDENCE_REQUIREMENT_NOT_EXTRACTED,
        )
        session.add(claim)
        session.flush()

        finding = Finding(
            case_id=case.id, agent_run_id=agent_run.id, claim_id=claim.id,
            verification_status=c["verification_status"], rationale=c["rationale"],
        )
        session.add(finding)
        session.flush()

        for ev in c["evidence"]:
            ev_version = document_version_by_doc_id[ev["document_id"]]
            evidence_item = EvidenceItem(
                claim_id=claim.id, document_version_id=ev_version.id,
                location=ev["location"], excerpt=ev["excerpt"],
                content_hash=hashlib.sha256(ev["excerpt"].encode()).hexdigest(),
            )
            session.add(evidence_item)
            session.flush()
            session.add(FindingEvidenceItem(
                finding_id=finding.id, evidence_item_id=evidence_item.id,
            ))

        pairs.append((claim, finding))

    record_event(
        session, case_id=case.id, event_type="agent_run.persisted", actor=actor,
        payload={"agent_run_id": str(agent_run.id), "agent_type": agent_type, "claims": len(pairs)},
    )
    session.flush()
    return agent_run, pairs


def persist_reconciliation(
    session: Session,
    *,
    case: Case,
    model: str,
    reconciliation: ReconciliationResult,
    claim_by_pooled_id: dict[str, Claim],
    finding_by_claim_id: dict[Any, Finding],
    actor: str = "system",
) -> list[Conflict]:
    """Persists every Conflict app.reconcile.reconcile() found, linked to
    the original Findings it concerns via ConflictFinding, plus one
    AgentRun + ReInvestigation row per bounded re-investigation call
    actually made (app.reinvestigate — always same-agent, per its module
    docstring)."""
    reinvest_by_claim_ids = {
        tuple(sorted(r.conflict_claim_ids)): r for r in reconciliation.reinvestigation_records
    }

    conflicts: list[Conflict] = []
    for sc in reconciliation.conflicts:
        resolved_at = datetime.now(UTC) if sc.status == "resolved" else None
        conflict = Conflict(
            case_id=case.id, conflict_type=sc.conflict_type, status=sc.status,
            resolution_method=sc.resolution_method, resolution_rationale=sc.resolution_rationale,
            resolved_at=resolved_at,
        )
        session.add(conflict)
        session.flush()

        for cid in sc.claim_ids:
            claim = claim_by_pooled_id[cid]
            finding = finding_by_claim_id[claim.id]
            session.add(ConflictFinding(conflict_id=conflict.id, finding_id=finding.id))

        if sc.resolution_method == "reinvestigation":
            key = tuple(sorted(sc.claim_ids))
            record = reinvest_by_claim_ids.get(key)
            if record is not None:
                now = datetime.now(UTC)
                run = AgentRun(
                    case_id=case.id, agent_type=record.agent_type, status="succeeded",
                    model=model, started_at=now, completed_at=now,
                    input_tokens=record.input_tokens, output_tokens=record.output_tokens,
                    retry_count=0,
                )
                session.add(run)
                session.flush()
                session.add(ReInvestigation(
                    conflict_id=conflict.id, agent_run_id=run.id, outcome=record.explanation,
                ))

        conflicts.append(conflict)

    record_event(
        session, case_id=case.id, event_type="reconciliation.persisted", actor=actor,
        payload={"conflicts": len(conflicts)},
    )
    session.flush()
    return conflicts
