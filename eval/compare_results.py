"""Compare two eval runs (e.g. baseline vs. investigators, or later,
investigators vs. reconciled output) by failure-mode category — the
breakdown evaluation.md and eval/CASES.md promise, and the actual
mechanism for answering Gate 6's real question: "which verification
errors does architecture B catch that architecture A misses," not just
whether one aggregate number is bigger than another.

Reads no API, no DB — pure analysis over already-saved eval/results/*.json
files and eval/ground_truth/*.json. Safe to run as often as needed, no
budget implications.

Usage:
    python -m eval.compare_results \\
        eval/results/baseline_<ts>.json eval/results/investigators_<ts>.json
"""

import json
import sys
from pathlib import Path

from eval.scoring import breakdown_by_issue_type

REPO_ROOT = Path(__file__).parent.parent
GROUND_TRUTH_DIR = REPO_ROOT / "eval" / "ground_truth"


def _load_ground_truth(case_id: str) -> dict:
    with (GROUND_TRUTH_DIR / f"{case_id}.json").open() as f:
        return json.load(f)


def _predicted_claims_from_baseline_result(result: dict) -> list[dict] | None:
    if "error" in result.get("raw_output", {}):
        return None
    return result["raw_output"].get("claims", [])


def _predicted_claims_from_investigator_result(result: dict) -> list[dict] | None:
    per_agent = result.get("per_agent", {})
    if any("error" in data for data in per_agent.values()):
        return None
    claims: list[dict] = []
    for data in per_agent.values():
        claims.extend(data.get("claims", []))
    return claims


def _predicted_claims_from_reconciliation_result(result: dict) -> list[dict] | None:
    return result.get("reconciled_claims", [])


def _cases_for(run: dict) -> list[tuple[dict, list[dict] | None]]:
    first = run["results"][0] if run["results"] else {}
    if "reconciled_claims" in first:
        extractor = _predicted_claims_from_reconciliation_result
    elif "per_agent" in first:
        extractor = _predicted_claims_from_investigator_result
    else:
        extractor = _predicted_claims_from_baseline_result
    return [
        (_load_ground_truth(r["case_id"]), extractor(r))
        for r in run["results"]
    ]


def compare(path_a: Path, path_b: Path, label_a: str, label_b: str) -> None:
    run_a = json.loads(path_a.read_text())
    run_b = json.loads(path_b.read_text())

    breakdown_a = breakdown_by_issue_type(_cases_for(run_a))
    breakdown_b = breakdown_by_issue_type(_cases_for(run_b))

    categories = sorted(set(breakdown_a) | set(breakdown_b))
    print(f"{'category':24} {label_a + ' acc':>16} {label_b + ' acc':>16} {'delta':>8}  total")
    for cat in categories:
        a, b = breakdown_a.get(cat), breakdown_b.get(cat)
        a_acc = a.status_accuracy if a else None
        b_acc = b.status_accuracy if b else None
        delta = (b_acc - a_acc) if (a_acc is not None and b_acc is not None) else None
        total = a.total if a else (b.total if b else 0)
        a_str = f"{a_acc:.1%}" if a_acc is not None else "n/a"
        b_str = f"{b_acc:.1%}" if b_acc is not None else "n/a"
        d_str = f"{delta:+.1%}" if delta is not None else "n/a"
        print(f"{cat:24} {a_str:>16} {b_str:>16} {d_str:>8}  {total}")

    # Global (micro-averaged, all categories pooled) and the same excluding
    # cross_domain_conflict, since that category is structurally
    # unresolvable pre-reconciliation and dominates the aggregate delta.
    exclusion_scenarios = [
        (set(), "all categories"),
        ({"cross_domain_conflict"}, "excl. cross_domain_conflict"),
    ]
    for exclude, note in exclusion_scenarios:
        for label, breakdown in [(label_a, breakdown_a), (label_b, breakdown_b)]:
            matched = sum(s.matched for cat, s in breakdown.items() if cat not in exclude)
            correct = sum(s.correct for cat, s in breakdown.items() if cat not in exclude)
            acc = correct / matched if matched else None
            acc_str = f"{acc:.1%}" if acc is not None else "n/a"
            print(f"[{note}] {label}: matched={matched} correct={correct} acc={acc_str}")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 5):
        print(
            "Usage: python -m eval.compare_results <a_results.json> <b_results.json> "
            "[label_a label_b]",
            file=sys.stderr,
        )
        sys.exit(1)
    label_a = sys.argv[3] if len(sys.argv) == 5 else "a"
    label_b = sys.argv[4] if len(sys.argv) == 5 else "b"
    compare(Path(sys.argv[1]), Path(sys.argv[2]), label_a, label_b)
