"""Run the real independent investigators against all 18 eval cases
(Phase 7). Raw comparison only — both investigators' claims are pooled
and scored against ground truth exactly as the baseline is, with no
deterministic reconciliation or conflict detection (that's Phase 8;
architecture.md's Phase 7 scope is explicitly "NOT yet: reconciliation
logic beyond raw comparison").

Same review discipline as eval/run_baseline.py (ADR-009): refuses to run
without --i-have-reviewed-the-cost-estimate, checks cumulative spend
against the $0.50 ceiling before every case (now two calls per case, not
one), and halts before any call that would exceed it.

Usage (only after review/approval):
    python -m eval.run_investigators --i-have-reviewed-the-cost-estimate
    python -m eval.run_investigators --i-have-reviewed-the-cost-estimate --cases case-08
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from app.agents.investigator import run_investigator
from app.agents.schema import CaseDocument, InvalidAgentOutputError
from app.llm.client import AnthropicLLMClient
from app.observability import TracedLLMClient
from app.retry import RetriesExhaustedError
from eval.scoring import CaseMetrics, aggregate, score_case

REPO_ROOT = Path(__file__).parent.parent
GROUND_TRUTH_DIR = REPO_ROOT / "eval" / "ground_truth"
CASES_DIR = REPO_ROOT / "eval" / "cases"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
COST_LOG_PATH = REPO_ROOT / "eval" / "COST_LOG.md"

MODEL = "claude-haiku-4-5-20251001"

# Sourced 2026-09-23 from https://platform.claude.com/docs/en/about-claude/pricing
PRICE_PER_MTOK_INPUT: float | None = 1.00
PRICE_PER_MTOK_OUTPUT: float | None = 5.00

BUDGET_TOTAL_USD = 0.50
# Sum of every real-call row already in eval/COST_LOG.md before this run.
PRIOR_SPEND_USD = 0.317411  # calibration + Phase 6 baseline + this Phase 7 run


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
            domain=doc["domain"],
        )
        for doc in ground_truth["document_manifest"]
    ]
    return ground_truth, documents


def run_one_case(client, case_id: str) -> dict:
    ground_truth, documents = load_case(case_id)
    per_agent = {}
    combined_claims = []
    injection_detected = False
    total_input_tokens = total_output_tokens = 0
    error = None

    for agent_type in ("security_investigator", "privacy_investigator"):
        start = time.monotonic()
        try:
            result = run_investigator(
                client, model=MODEL, agent_type=agent_type, documents=documents,
            )
            latency_s = time.monotonic() - start
            per_agent[agent_type] = {
                "claims": result.claims,
                "injection_detected": result.injection_detected,
                "injection_note": result.injection_note,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_s": latency_s,
            }
            combined_claims.extend(result.claims)
            injection_detected = injection_detected or result.injection_detected
            total_input_tokens += result.input_tokens
            total_output_tokens += result.output_tokens
        except (InvalidAgentOutputError, RetriesExhaustedError) as exc:
            per_agent[agent_type] = {"error": str(exc)}
            error = f"{agent_type}: {exc}"

    cost = (
        (total_input_tokens / 1_000_000) * PRICE_PER_MTOK_INPUT
        + (total_output_tokens / 1_000_000) * PRICE_PER_MTOK_OUTPUT
    )

    if error is not None:
        metrics = score_case(ground_truth, None, injection_detected=None, error=error)
    else:
        metrics = score_case(
            ground_truth, combined_claims, injection_detected=injection_detected,
            input_tokens=total_input_tokens, output_tokens=total_output_tokens,
            cost_usd=cost, latency_s=sum(a.get("latency_s", 0) for a in per_agent.values()),
        )

    return {"case_id": case_id, "metrics": asdict(metrics), "per_agent": per_agent}


def confirm_pricing_is_set() -> None:
    if PRICE_PER_MTOK_INPUT is None or PRICE_PER_MTOK_OUTPUT is None:
        print("Refusing to run: pricing constants unset.", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--i-have-reviewed-the-cost-estimate", action="store_true")
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
    # TracedLLMClient no-ops without LANGFUSE_PUBLIC_KEY/SECRET_KEY set
    # (observability.md) — wrapping here costs nothing when unconfigured.
    client = TracedLLMClient(AnthropicLLMClient(api_key=api_key))

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

        print(f"Running {case_id} (security + privacy investigators)...")
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
    out_path = RESULTS_DIR / f"investigators_{timestamp}.json"
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
