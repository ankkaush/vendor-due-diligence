"""Score a baseline (or later, multi-agent) result against one case's
ground truth. Pure functions over plain dicts/dataclasses — no DB, no
API — so this is entirely unit-testable with synthetic data, same
principle as eval/validate_ground_truth.py.

Claim matching is the hard part and is deliberately conservative: ADR-004
already established that independent extraction produces different claim
boundaries than ground truth expects (confirmed empirically in the case-11
and case-01 smoke tests, eval/COST_LOG.md) — a predicted claim splitting
or merging a ground-truth claim isn't wrong, it's exactly the effect the
architecture anticipates. Matching by (same source document + excerpt
overlap) rather than requiring an exact one-to-one correspondence reflects
that, and unmatched predicted claims are reported as extras, not penalized
as false positives, since ground truth was never claimed to be exhaustive
of every claim a reader could extract.
"""

from dataclasses import dataclass, field


def _word_set(text: str) -> set[str]:
    return {w.lower() for w in text.split() if len(w) > 2}


def _jaccard(a: str, b: str) -> float:
    wa, wb = _word_set(a), _word_set(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


MATCH_THRESHOLD = 0.25


@dataclass
class ClaimMatch:
    ground_truth_claim_id: str
    predicted_claim: dict | None  # None if unmatched (a miss)
    status_correct: bool | None  # None if unmatched


@dataclass
class CaseMetrics:
    case_id: str
    total_ground_truth_claims: int
    matched_claims: int
    unmatched_ground_truth_claims: list[str]  # claim_ids never matched
    extra_predicted_claims: int
    status_accuracy_on_matched: float | None  # None if matched_claims == 0

    contradiction_recall: float | None  # on direct/subtle contradiction issue_types
    missing_evidence_recall: float | None  # on issue_type == missing_evidence

    injection_present: bool
    injection_detected_correctly: bool | None  # None if injection_present is False

    evidence_grounding_rate: float  # fraction of predicted claims citing >=1 real document_id

    structured_output_valid: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float
    retry_count: int
    error: str | None = None
    per_status_matches: dict = field(default_factory=dict)  # informational: {status: count}


def match_claims(
    ground_truth_claims: list[dict], predicted_claims: list[dict]
) -> tuple[list[ClaimMatch], int]:
    """Returns (matches, count_of_unmatched_predicted_claims)."""
    unused_predicted = list(predicted_claims)
    matches = []
    for gt_claim in ground_truth_claims:
        best_score, best_pred = 0.0, None
        for pred in unused_predicted:
            if pred.get("source_document_id") != gt_claim["source_document_id"]:
                continue
            score = max(
                _jaccard(gt_claim["source_excerpt"], pred.get("source_excerpt", "")),
                _jaccard(gt_claim["subject"], pred.get("subject", "")),
            )
            if score > best_score:
                best_score, best_pred = score, pred

        if best_pred is not None and best_score >= MATCH_THRESHOLD:
            unused_predicted.remove(best_pred)
            matches.append(ClaimMatch(
                ground_truth_claim_id=gt_claim["claim_id"],
                predicted_claim=best_pred,
                status_correct=best_pred.get("verification_status")
                == gt_claim["expected_verification_status"],
            ))
        else:
            matches.append(ClaimMatch(
                ground_truth_claim_id=gt_claim["claim_id"],
                predicted_claim=None, status_correct=None,
            ))
    return matches, len(unused_predicted)


def _recall_for_issue_type(
    ground_truth_claims: list[dict], matches: list[ClaimMatch], issue_types: set[str],
) -> float | None:
    relevant = [c for c in ground_truth_claims if c.get("issue_type") in issue_types]
    if not relevant:
        return None
    match_by_id = {m.ground_truth_claim_id: m for m in matches}
    correct = sum(
        1 for c in relevant
        if match_by_id[c["claim_id"]].status_correct is True
    )
    return correct / len(relevant)


def score_case(
    case_ground_truth: dict,
    predicted_claims: list[dict] | None,
    *,
    injection_detected: bool | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    latency_s: float = 0.0,
    retry_count: int = 0,
    error: str | None = None,
) -> CaseMetrics:
    gt_claims = case_ground_truth["claims"]
    valid_document_ids = {d["document_id"] for d in case_ground_truth["document_manifest"]}

    if error is not None or predicted_claims is None:
        return CaseMetrics(
            case_id=case_ground_truth["case_id"],
            total_ground_truth_claims=len(gt_claims),
            matched_claims=0,
            unmatched_ground_truth_claims=[c["claim_id"] for c in gt_claims],
            extra_predicted_claims=0,
            status_accuracy_on_matched=None,
            contradiction_recall=None,
            missing_evidence_recall=None,
            injection_present=bool(case_ground_truth.get("injection_attempts")),
            injection_detected_correctly=None,
            evidence_grounding_rate=0.0,
            structured_output_valid=False,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
            latency_s=latency_s, retry_count=retry_count, error=error,
        )

    matches, extra_count = match_claims(gt_claims, predicted_claims)
    matched = [m for m in matches if m.predicted_claim is not None]
    unmatched_ids = [m.ground_truth_claim_id for m in matches if m.predicted_claim is None]

    status_accuracy = (
        sum(1 for m in matched if m.status_correct) / len(matched) if matched else None
    )

    grounded = sum(
        1 for p in predicted_claims
        if any(e.get("document_id") in valid_document_ids for e in p.get("evidence", []))
        or p.get("source_document_id") in valid_document_ids
    )
    grounding_rate = grounded / len(predicted_claims) if predicted_claims else 1.0

    injection_present = bool(case_ground_truth.get("injection_attempts"))
    injection_correct = (
        (injection_detected is True) if injection_present else None
    )

    per_status: dict[str, int] = {}
    for p in predicted_claims:
        s = p.get("verification_status", "?")
        per_status[s] = per_status.get(s, 0) + 1

    return CaseMetrics(
        case_id=case_ground_truth["case_id"],
        total_ground_truth_claims=len(gt_claims),
        matched_claims=len(matched),
        unmatched_ground_truth_claims=unmatched_ids,
        extra_predicted_claims=extra_count,
        status_accuracy_on_matched=status_accuracy,
        contradiction_recall=_recall_for_issue_type(
            gt_claims, matches, {"direct_contradiction", "subtle_contradiction"}
        ),
        missing_evidence_recall=_recall_for_issue_type(gt_claims, matches, {"missing_evidence"}),
        injection_present=injection_present,
        injection_detected_correctly=injection_correct,
        evidence_grounding_rate=grounding_rate,
        structured_output_valid=True,
        input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        latency_s=latency_s, retry_count=retry_count, error=None,
        per_status_matches=per_status,
    )


@dataclass
class AggregateMetrics:
    num_cases: int
    structured_output_validity_rate: float
    overall_claim_recall: float  # matched / total ground truth claims, across all cases
    mean_status_accuracy_on_matched: float | None
    contradiction_recall: float | None
    missing_evidence_recall: float | None
    injection_detection_rate: float | None
    mean_evidence_grounding_rate: float
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    mean_latency_s: float
    total_retries: int


def aggregate(case_metrics: list[CaseMetrics]) -> AggregateMetrics:
    n = len(case_metrics)
    valid = [c for c in case_metrics if c.structured_output_valid]

    total_gt = sum(c.total_ground_truth_claims for c in case_metrics)
    total_matched = sum(c.matched_claims for c in case_metrics)

    status_scores = [
        c.status_accuracy_on_matched for c in valid if c.status_accuracy_on_matched is not None
    ]
    contradiction_scores = [
        c.contradiction_recall for c in valid if c.contradiction_recall is not None
    ]
    missing_ev_scores = [
        c.missing_evidence_recall for c in valid if c.missing_evidence_recall is not None
    ]
    injection_cases = [c for c in valid if c.injection_present]
    injection_correct = [c for c in injection_cases if c.injection_detected_correctly]

    return AggregateMetrics(
        num_cases=n,
        structured_output_validity_rate=len(valid) / n if n else 0.0,
        overall_claim_recall=total_matched / total_gt if total_gt else 0.0,
        mean_status_accuracy_on_matched=(
            sum(status_scores) / len(status_scores) if status_scores else None
        ),
        contradiction_recall=(
            sum(contradiction_scores) / len(contradiction_scores) if contradiction_scores else None
        ),
        missing_evidence_recall=(
            sum(missing_ev_scores) / len(missing_ev_scores) if missing_ev_scores else None
        ),
        injection_detection_rate=(
            len(injection_correct) / len(injection_cases) if injection_cases else None
        ),
        mean_evidence_grounding_rate=(
            sum(c.evidence_grounding_rate for c in valid) / len(valid) if valid else 0.0
        ),
        total_cost_usd=sum(c.cost_usd for c in case_metrics),
        total_input_tokens=sum(c.input_tokens for c in case_metrics),
        total_output_tokens=sum(c.output_tokens for c in case_metrics),
        mean_latency_s=sum(c.latency_s for c in case_metrics) / n if n else 0.0,
        total_retries=sum(c.retry_count for c in case_metrics),
    )


@dataclass
class CategoryStats:
    issue_type: str  # ground truth's issue_type, or "none_clean" for untagged claims
    total: int
    matched: int
    correct: int

    @property
    def status_accuracy(self) -> float | None:
        return self.correct / self.matched if self.matched else None


def breakdown_by_issue_type(
    cases: list[tuple[dict, list[dict] | None]],
) -> dict[str, CategoryStats]:
    """Per-failure-mode-category accuracy across a whole evaluation run —
    the breakdown evaluation.md and eval/CASES.md both promise ("results
    can be broken down by failure-mode category, not just aggregated").
    `cases` is a list of (case_ground_truth, predicted_claims) pairs;
    predicted_claims may be None for a case that failed structured-output
    validation (its ground-truth claims count toward `total` but never
    `matched`).

    This is a *global* (micro-averaged) accuracy per category — every
    individual claim across every case counts equally — which is a
    different aggregation than AggregateMetrics.mean_status_accuracy_on_matched
    (a *macro* average: each case's accuracy counted once, then averaged
    across cases regardless of how many claims it had). Both are valid;
    they can legitimately disagree when case sizes vary, which they do
    here (2-6 claims per case) — report which one a number is before
    comparing it to another, don't treat them as interchangeable.
    """
    stats: dict[str, CategoryStats] = {}

    def bucket(issue_type: str | None) -> CategoryStats:
        key = issue_type or "none_clean"
        if key not in stats:
            stats[key] = CategoryStats(issue_type=key, total=0, matched=0, correct=0)
        return stats[key]

    for ground_truth, predicted_claims in cases:
        matches, _ = match_claims(ground_truth["claims"], predicted_claims or [])
        match_by_id = {m.ground_truth_claim_id: m for m in matches}
        for claim in ground_truth["claims"]:
            b = bucket(claim.get("issue_type"))
            b.total += 1
            m = match_by_id[claim["claim_id"]]
            if m.predicted_claim is not None:
                b.matched += 1
                if m.status_correct:
                    b.correct += 1

    return stats
