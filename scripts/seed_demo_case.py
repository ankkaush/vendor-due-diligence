"""Seeds real cases into the local Postgres from already-executed, already-paid
real API output — zero new API spend (ADR-009) — so Phase 9's review UI has
something genuine to show.

No orchestrator that runs the live pipeline end-to-end exists yet (that's a
separate, larger piece of future work requiring its own ADR-009 cost review
before any real spend). This script deliberately doesn't build that. It
reuses the real, already-validated Phase 7 investigator output
(eval/results/investigators_20260924T082006Z.json) and the real Phase 8 fix
rerun's reconciliation output (eval/results/reconciliation_20260924T143706Z.json)
— the same "reuse already-paid-for real output" discipline Phase 8 itself
used to avoid re-running investigators for reconciliation — and replays it
through the real intake/state-machine/persistence code paths (app.intake,
app.state_machine, app.persist), so what lands in Postgres is the actual
real model output, not synthetic demo data.

Usage:
    python -m scripts.seed_demo_case                      # seeds the default set
    python -m scripts.seed_demo_case case-01 case-07       # seeds specific cases
"""

import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.schema import AgentResult
from app.db.base import SessionLocal
from app.intake import create_case, ingest_document, mark_documents_ready, start_validation
from app.persist import persist_agent_result, persist_reconciliation
from app.reconcile import Conflict, ReconciliationResult
from app.reinvestigate import ReinvestigationRecord
from app.state_machine import transition_case

REPO_ROOT = Path(__file__).parent.parent
GROUND_TRUTH_DIR = REPO_ROOT / "eval" / "ground_truth"
CASES_DIR = REPO_ROOT / "eval" / "cases"
RESULTS_DIR = REPO_ROOT / "eval" / "results"

INVESTIGATOR_RESULTS_PATH = RESULTS_DIR / "investigators_20260924T082006Z.json"
RECONCILIATION_RESULTS_PATH = RESULTS_DIR / "reconciliation_20260924T143706Z.json"

MODEL = "claude-haiku-4-5-20251001"
PRICE_PER_MTOK_INPUT = 1.00
PRICE_PER_MTOK_OUTPUT = 5.00

DEFAULT_CASE_IDS = ["case-01", "case-07", "case-18"]

MIME_TYPE_BY_EXTENSION = {".md": "text/markdown", ".txt": "text/plain"}


def _cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * PRICE_PER_MTOK_INPUT + (
        output_tokens / 1_000_000
    ) * PRICE_PER_MTOK_OUTPUT


def _load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def _by_case_id(results: dict) -> dict[str, dict]:
    return {r["case_id"]: r for r in results["results"]}


def _agent_result_from_saved(data: dict) -> AgentResult:
    return AgentResult(
        claims=data["claims"], injection_detected=data["injection_detected"],
        injection_note=data["injection_note"], input_tokens=data["input_tokens"],
        output_tokens=data["output_tokens"], model=MODEL,
    )


def _reconciliation_result_from_saved(data: dict) -> ReconciliationResult:
    conflicts = [
        Conflict(
            claim_ids=c["claim_ids"], conflict_type=c["conflict_type"], status=c["status"],
            resolution_method=c["resolution_method"],
            resolution_rationale=c["resolution_rationale"],
        )
        for c in data["conflicts"]
    ]
    reinvestigation_records = [
        ReinvestigationRecord(
            conflict_claim_ids=tuple(r["conflict_claim_ids"]), agent_type=r["agent_type"],
            resolved=r["resolved"], explanation=r["explanation"],
            resolution_status=r["resolution_status"], input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
        )
        for r in data["reinvestigation_records"]
    ]
    return ReconciliationResult(
        reconciled_claims=[], conflicts=conflicts, semantic_input_tokens=0,
        semantic_output_tokens=0, reinvestigation_records=reinvestigation_records,
    )


def seed_case(session: Session, case_id: str) -> None:
    ground_truth = _load_json(GROUND_TRUTH_DIR / f"{case_id}.json")
    investigator_data = _by_case_id(_load_json(INVESTIGATOR_RESULTS_PATH))[case_id]
    reconciliation_data = _by_case_id(_load_json(RECONCILIATION_RESULTS_PATH))[case_id]

    print(f"\n=== Seeding {case_id}: {ground_truth['vendor_name']} ===")

    case = create_case(session, ground_truth["vendor_name"], actor="seed_script")

    document_version_by_doc_id = {}
    for doc in ground_truth["document_manifest"]:
        path = CASES_DIR / case_id / doc["filename"]
        content = path.read_bytes()
        mime_type = MIME_TYPE_BY_EXTENSION[path.suffix]
        document = ingest_document(
            session, case, filename=doc["filename"], mime_type=mime_type,
            doc_type=doc["doc_type"], content=content,
            explicit_domain=doc["domain"], actor="seed_script",
        )
        document_version_by_doc_id[doc["document_id"]] = document.versions[0]

    start_validation(session, case.id, actor="seed_script")
    mark_documents_ready(session, case.id, actor="seed_script")
    transition_case(
        session, case.id, from_status="DOCUMENTS_READY", to_status="CLASSIFYING",
        actor="seed_script",
    )
    transition_case(
        session, case.id, from_status="CLASSIFYING", to_status="INVESTIGATING",
        actor="seed_script",
    )

    security_result = _agent_result_from_saved(
        investigator_data["per_agent"]["security_investigator"]
    )
    privacy_result = _agent_result_from_saved(
        investigator_data["per_agent"]["privacy_investigator"]
    )

    _, security_pairs = persist_agent_result(
        session, case=case, agent_type="security_investigator", model=MODEL,
        result=security_result, document_version_by_doc_id=document_version_by_doc_id,
        cost_usd=_cost(security_result.input_tokens, security_result.output_tokens),
        actor="seed_script",
    )
    _, privacy_pairs = persist_agent_result(
        session, case=case, agent_type="privacy_investigator", model=MODEL,
        result=privacy_result, document_version_by_doc_id=document_version_by_doc_id,
        cost_usd=_cost(privacy_result.input_tokens, privacy_result.output_tokens),
        actor="seed_script",
    )

    # Same claim-id scheme as app.reconcile.pool_claims — "security-{i}",
    # "privacy-{i}" — so the saved reconciliation output's claim_ids
    # resolve to the real, just-persisted Claim rows.
    claim_by_pooled_id = {f"security-{i}": claim for i, (claim, _) in enumerate(security_pairs)}
    claim_by_pooled_id.update(
        {f"privacy-{i}": claim for i, (claim, _) in enumerate(privacy_pairs)}
    )
    finding_by_claim_id = {
        claim.id: finding for claim, finding in [*security_pairs, *privacy_pairs]
    }

    transition_case(
        session, case.id, from_status="INVESTIGATING",
        to_status="INVESTIGATIONS_COMPLETE", actor="seed_script",
    )
    transition_case(
        session, case.id, from_status="INVESTIGATIONS_COMPLETE",
        to_status="RECONCILING", actor="seed_script",
    )

    reconciliation = _reconciliation_result_from_saved(reconciliation_data)
    persist_reconciliation(
        session, case=case, model=MODEL, reconciliation=reconciliation,
        claim_by_pooled_id=claim_by_pooled_id, finding_by_claim_id=finding_by_claim_id,
        actor="seed_script",
    )

    if reconciliation.reinvestigation_records:
        transition_case(
            session, case.id, from_status="RECONCILING", to_status="REINVESTIGATING",
            actor="seed_script",
        )
        transition_case(
            session, case.id, from_status="REINVESTIGATING",
            to_status="RECONCILING_POST_REINVESTIGATION", actor="seed_script",
        )
        transition_case(
            session, case.id, from_status="RECONCILING_POST_REINVESTIGATION",
            to_status="SYNTHESIZING", actor="seed_script",
        )
    else:
        transition_case(
            session, case.id, from_status="RECONCILING", to_status="SYNTHESIZING",
            actor="seed_script",
        )

    transition_case(
        session, case.id, from_status="SYNTHESIZING", to_status="AWAITING_HUMAN_REVIEW",
        actor="seed_script",
    )

    session.commit()
    print(
        f"  case_id={case.id} claims={len(security_pairs) + len(privacy_pairs)} "
        f"conflicts={len(reconciliation.conflicts)} status=AWAITING_HUMAN_REVIEW"
    )


def main() -> None:
    case_ids = sys.argv[1:] or DEFAULT_CASE_IDS
    session = SessionLocal()
    try:
        for case_id in case_ids:
            seed_case(session, case_id)
    finally:
        session.close()
    print("\nDone. Start the review UI with: uvicorn app.web.main:app --reload")


if __name__ == "__main__":
    main()
