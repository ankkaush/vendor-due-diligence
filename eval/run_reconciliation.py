"""Run reconciliation (Phase 8) against all 18 cases and score the result
against ground truth — the actual Gate 6 comparison ADR-006 locked a
threshold for.

Deliberately reuses the ALREADY-SAVED Phase 7 investigator output
(eval/results/investigators_<ts>.json) instead of re-running the
investigators from scratch: reconciliation's job is to take existing
findings and reconcile them, it doesn't need fresh investigator calls for
this, and re-running them would spend real budget on calls whose output
we already have and already validated (100% structured-output validity,
eval/COST_LOG.md). The only new real spend here is semantic adjudication
(one call per case, skipped when nothing remains after the deterministic
pass — app/reconcile.py) and bounded re-investigation (one call per
deterministic conflict, app/reinvestigate.py).

Same review discipline as the Phase 6/7 runners (ADR-009): refuses to run
without --i-have-reviewed-the-cost-estimate, checks cumulative spend
against the $0.50 ceiling before every case, halts before any call that
would exceed it.

Usage (only after review/approval):
    python -m eval.run_reconciliation --i-have-reviewed-the-cost-estimate \\
        --investigator-results eval/results/investigators_<ts>.json
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from app.agents.schema import AgentResult, CaseDocument
from app.llm.client import AnthropicLLMClient
from app.reconcile import reconcile
from eval.scoring import CaseMetrics, aggregate, score_case

REPO_ROOT = Path(__file__).parent.parent
GROUND_TRUTH_DIR = REPO_ROOT / "eval" / "ground_truth"
CASES_DIR = REPO_ROOT / "eval" / "cases"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
COST_LOG_PATH = REPO_ROOT / "eval" / "COST_LOG.md"

MODEL = "claude-haiku-4-5-20251001"

PRICE_PER_MTOK_INPUT: float | None = 1.00
PRICE_PER_MTOK_OUTPUT: float | None = 5.00

BUDGET_TOTAL_USD = 0.50
PRIOR_SPEND_USD = 0.370018  # calibration + Phase 6 + Phase 7 + this script's own Phase 8 run


def load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    print("No ANTHROPIC_API_KEY found. Set it locally first.", file=sys.stderr)
    sys.exit(1)


def load_case_documents(case_id: str) -> list[CaseDocument]:
    with (GROUND_TRUTH_DIR / f"{case_id}.json").open() as f:
        ground_truth = json.load(f)
    return [
        CaseDocument(
            document_id=doc["document_id"], filename=doc["filename"],
            text=(CASES_DIR / case_id / doc["filename"]).read_text(),
            domain=doc["domain"],
        )
        for doc in ground_truth["document_manifest"]
    ]


def agent_result_from_saved(data: dict) -> AgentResult:
    return AgentResult(
        claims=data["claims"], injection_detected=data["injection_detected"],
        injection_note=data["injection_note"], input_tokens=data["input_tokens"],
        output_tokens=data["output_tokens"], model=MODEL,
    )


def run_one_case(client, case_id: str, saved_result: dict) -> dict:
    with (GROUND_TRUTH_DIR / f"{case_id}.json").open() as f:
        ground_truth = json.load(f)
    documents = load_case_documents(case_id)

    security = agent_result_from_saved(saved_result["per_agent"]["security_investigator"])
    privacy = agent_result_from_saved(saved_result["per_agent"]["privacy_investigator"])

    start = time.monotonic()
    reconciliation = reconcile(
        client, model=MODEL, security_result=security, privacy_result=privacy,
        documents=documents,
    )
    latency_s = time.monotonic() - start

    reconciled_claims = [c.data for c in reconciliation.reconciled_claims]
    reinvest_input = sum(r.input_tokens for r in reconciliation.reinvestigation_records)
    reinvest_output = sum(r.output_tokens for r in reconciliation.reinvestigation_records)
    new_input_tokens = reconciliation.semantic_input_tokens + reinvest_input
    new_output_tokens = reconciliation.semantic_output_tokens + reinvest_output
    new_cost = (
        (new_input_tokens / 1_000_000) * PRICE_PER_MTOK_INPUT
        + (new_output_tokens / 1_000_000) * PRICE_PER_MTOK_OUTPUT
    )

    injection_detected = security.injection_detected or privacy.injection_detected
    metrics = score_case(
        ground_truth, reconciled_claims, injection_detected=injection_detected,
        input_tokens=new_input_tokens, output_tokens=new_output_tokens,
        cost_usd=new_cost, latency_s=latency_s,
    )

    return {
        "case_id": case_id,
        "metrics": asdict(metrics),
        "conflicts": [asdict(c) for c in reconciliation.conflicts],
        "reinvestigation_records": [asdict(r) for r in reconciliation.reinvestigation_records],
        "reconciled_claims": reconciled_claims,
    }


def confirm_pricing_is_set() -> None:
    if PRICE_PER_MTOK_INPUT is None or PRICE_PER_MTOK_OUTPUT is None:
        print("Refusing to run: pricing constants unset.", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--i-have-reviewed-the-cost-estimate", action="store_true")
    parser.add_argument("--investigator-results", required=True)
    parser.add_argument("--cases", nargs="*", default=None)
    args = parser.parse_args()

    if not args.i_have_reviewed_the_cost_estimate:
        print(
            "Refusing to run without --i-have-reviewed-the-cost-estimate. "
            "Per ADR-009, expected cost must be reviewed before any real "
            "evaluation run.",
            file=sys.stderr,
        )
        return 1

    confirm_pricing_is_set()
    api_key = load_api_key()
    client = AnthropicLLMClient(api_key=api_key)

    saved = json.loads(Path(args.investigator_results).read_text())
    saved_by_case = {r["case_id"]: r for r in saved["results"]}

    case_ids = args.cases or sorted(saved_by_case.keys())

    cumulative_spend = PRIOR_SPEND_USD
    results = []
    for case_id in case_ids:
        if cumulative_spend >= BUDGET_TOTAL_USD:
            print(
                f"STOPPING before {case_id}: cumulative spend ${cumulative_spend:.4f} "
                f"has reached the ${BUDGET_TOTAL_USD:.2f} budget.",
                file=sys.stderr,
            )
            break

        print(f"Reconciling {case_id}...")
        outcome = run_one_case(client, case_id, saved_by_case[case_id])
        results.append(outcome)
        case_cost = outcome["metrics"]["cost_usd"]
        cumulative_spend += case_cost
        n_conflicts = len(outcome["conflicts"])
        remaining = BUDGET_TOTAL_USD - cumulative_spend
        print(
            f"  conflicts={n_conflicts}  cost=${case_cost:.6f}  "
            f"cumulative=${cumulative_spend:.6f}  remaining=${remaining:.6f}"
        )

    case_metrics_objs = [CaseMetrics(**r["metrics"]) for r in results]
    agg = aggregate(case_metrics_objs)

    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_path = RESULTS_DIR / f"reconciliation_{timestamp}.json"
    out_path.write_text(json.dumps({
        "model": MODEL, "results": results, "aggregate": asdict(agg),
    }, indent=2))

    print(f"\n=== Aggregate ({agg.num_cases} cases) ===")
    print(f"Structured output validity: {agg.structured_output_validity_rate:.1%}")
    print(f"Overall claim recall: {agg.overall_claim_recall:.1%}")
    print(f"Status accuracy on matched claims: {agg.mean_status_accuracy_on_matched}")
    print(f"Contradiction recall: {agg.contradiction_recall}")
    print(f"Missing-evidence recall: {agg.missing_evidence_recall}")
    print(f"Total new cost (reconciliation only): ${agg.total_cost_usd:.6f}")
    print(f"Results written to {out_path}")
    print(
        f"\nReminder: append a row to {COST_LOG_PATH} with the real total "
        "cost above, and update PRIOR_SPEND_USD in this script for next time."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
