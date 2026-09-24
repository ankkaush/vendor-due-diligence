"""Run the real single-agent baseline against all 18 eval cases (Phase 6).

This is the real, budget-tracked evaluation checkpoint ADR-009 requires
review for — distinct from the smoke tests (eval/smoke_test.py), which
only proved connectivity and calibrated cost. This script makes 18 real
calls against the actual baseline agent (app/agents/baseline.py), not a
toy prompt.

Refuses to run without --i-have-reviewed-the-cost-estimate, same
discipline as the smoke test. Every real call's cost is accumulated and
checked against the remaining $0.50 budget (eval/COST_LOG.md) as it
runs — if a case would push cumulative spend over budget, execution
stops before that call, not after.

Usage (only after review/approval; run as a module, not a bare script,
so `app`/`eval` imports resolve from the repo root):
    python -m eval.run_baseline --i-have-reviewed-the-cost-estimate
    python -m eval.run_baseline --i-have-reviewed-the-cost-estimate --cases case-11
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from app.agents.baseline import CaseDocument, InvalidAgentOutputError, run_baseline
from app.llm.client import AnthropicLLMClient
from app.retry import RetriesExhaustedError
from eval.scoring import CaseMetrics, aggregate, score_case

REPO_ROOT = Path(__file__).parent.parent
GROUND_TRUTH_DIR = REPO_ROOT / "eval" / "ground_truth"
CASES_DIR = REPO_ROOT / "eval" / "cases"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
COST_LOG_PATH = REPO_ROOT / "eval" / "COST_LOG.md"

MODEL = "claude-haiku-4-5-20251001"

# Sourced 2026-09-23 from https://platform.claude.com/docs/en/about-claude/pricing
# — same rates already used and verified in eval/smoke_test.py.
PRICE_PER_MTOK_INPUT: float | None = 1.00
PRICE_PER_MTOK_OUTPUT: float | None = 5.00

BUDGET_TOTAL_USD = 0.50
# Sum of every real-call row already in COST_LOG.md before this run.
PRIOR_SPEND_USD = 0.147290  # calibration ($0.008130) + Phase 6 baseline run ($0.139160)


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


def load_case(case_id: str) -> tuple[dict, list[CaseDocument]]:
    with (GROUND_TRUTH_DIR / f"{case_id}.json").open() as f:
        ground_truth = json.load(f)
    documents = [
        CaseDocument(
            document_id=doc["document_id"],
            filename=doc["filename"],
            text=(CASES_DIR / case_id / doc["filename"]).read_text(),
        )
        for doc in ground_truth["document_manifest"]
    ]
    return ground_truth, documents


def run_one_case(client, case_id: str) -> dict:
    ground_truth, documents = load_case(case_id)
    start = time.monotonic()
    try:
        result = run_baseline(client, model=MODEL, documents=documents)
        latency_s = time.monotonic() - start
        cost = (
            (result.input_tokens / 1_000_000) * PRICE_PER_MTOK_INPUT
            + (result.output_tokens / 1_000_000) * PRICE_PER_MTOK_OUTPUT
        )
        metrics = score_case(
            ground_truth, result.claims, injection_detected=result.injection_detected,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            cost_usd=cost, latency_s=latency_s, retry_count=0,
        )
        raw = {
            "claims": result.claims,
            "injection_detected": result.injection_detected,
            "injection_note": result.injection_note,
        }
    except (InvalidAgentOutputError, RetriesExhaustedError) as exc:
        latency_s = time.monotonic() - start
        metrics = score_case(
            ground_truth, None, injection_detected=None,
            latency_s=latency_s, error=str(exc),
        )
        raw = {"error": str(exc)}

    return {"case_id": case_id, "metrics": asdict(metrics), "raw_output": raw}


def confirm_pricing_is_set() -> None:
    if PRICE_PER_MTOK_INPUT is None or PRICE_PER_MTOK_OUTPUT is None:
        print("Refusing to run: pricing constants unset.", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--i-have-reviewed-the-cost-estimate", action="store_true")
    parser.add_argument(
        "--cases", nargs="*", default=None,
        help="Run only these case IDs (e.g. case-01 case-10). Default: all 18.",
    )
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

    case_ids = args.cases or sorted(p.stem for p in GROUND_TRUTH_DIR.glob("case-*.json"))

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

        print(f"Running {case_id}...")
        outcome = run_one_case(client, case_id)
        results.append(outcome)
        case_cost = outcome["metrics"]["cost_usd"]
        cumulative_spend += case_cost
        print(
            f"  cost=${case_cost:.6f}  cumulative=${cumulative_spend:.6f}  "
            f"remaining=${BUDGET_TOTAL_USD - cumulative_spend:.6f}"
        )

    case_metrics_objs = [CaseMetrics(**r["metrics"]) for r in results]
    agg = aggregate(case_metrics_objs)

    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_path = RESULTS_DIR / f"baseline_{timestamp}.json"
    out_path.write_text(json.dumps({
        "model": MODEL, "results": results, "aggregate": asdict(agg),
    }, indent=2))

    print(f"\n=== Aggregate ({agg.num_cases} cases) ===")
    print(f"Structured output validity: {agg.structured_output_validity_rate:.1%}")
    print(f"Overall claim recall: {agg.overall_claim_recall:.1%}")
    print(f"Status accuracy on matched claims: {agg.mean_status_accuracy_on_matched}")
    print(f"Contradiction recall: {agg.contradiction_recall}")
    print(f"Missing-evidence recall: {agg.missing_evidence_recall}")
    print(f"Injection detection rate: {agg.injection_detection_rate}")
    print(f"Mean evidence grounding rate: {agg.mean_evidence_grounding_rate:.1%}")
    print(f"Total cost: ${agg.total_cost_usd:.6f}")
    print(f"Results written to {out_path}")
    print(
        f"\nReminder: append a row to {COST_LOG_PATH} with the real total "
        "cost above, and update PRIOR_SPEND_USD in this script for next time."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
