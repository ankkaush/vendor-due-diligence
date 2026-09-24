"""Scoring tests against synthetic predicted-vs-ground-truth data — no
API calls, no database. Mirrors real shapes (a minimal ground-truth case
dict, a minimal predicted-claims list) without needing the full eval
fixtures, so the matching/aggregation logic can be verified in isolation
before it's ever pointed at real model output.
"""

from eval.scoring import CaseMetrics, aggregate, match_claims, score_case

GT_CASE = {
    "case_id": "synthetic-01",
    "document_manifest": [
        {"document_id": "doc-a", "filename": "a.md"},
        {"document_id": "doc-b", "filename": "b.md"},
    ],
    "claims": [
        {
            "claim_id": "c1",
            "source_document_id": "doc-a",
            "subject": "data retention period",
            "source_excerpt": "shall delete all customer personal data within 30 days",
            "expected_verification_status": "supported",
            "issue_type": None,
        },
        {
            "claim_id": "c2",
            "source_document_id": "doc-b",
            "subject": "penetration testing",
            "source_excerpt": "engages a third-party firm to perform an annual penetration test",
            "expected_verification_status": "unverified",
            "issue_type": "missing_evidence",
        },
    ],
    "injection_attempts": [],
}


def test_exact_match_gives_full_recall_and_correct_status():
    predicted = [
        {
            "source_document_id": "doc-a",
            "subject": "data retention period",
            "source_excerpt": "shall delete all customer personal data within 30 days",
            "verification_status": "supported",
            "evidence": [],
        },
        {
            "source_document_id": "doc-b",
            "subject": "penetration testing",
            "source_excerpt": "engages a third-party firm to perform an annual penetration test",
            "verification_status": "unverified",
            "evidence": [],
        },
    ]
    metrics = score_case(GT_CASE, predicted, injection_detected=False)
    assert metrics.matched_claims == 2
    assert metrics.unmatched_ground_truth_claims == []
    assert metrics.status_accuracy_on_matched == 1.0
    assert metrics.missing_evidence_recall == 1.0


def test_wrong_status_on_a_matched_claim_is_counted_incorrect():
    predicted = [
        {
            "source_document_id": "doc-a",
            "subject": "data retention period",
            "source_excerpt": "shall delete all customer personal data within 30 days",
            "verification_status": "contradicted",  # wrong — ground truth says supported
            "evidence": [],
        },
    ]
    metrics = score_case(
        {**GT_CASE, "claims": [GT_CASE["claims"][0]]}, predicted, injection_detected=False,
    )
    assert metrics.matched_claims == 1
    assert metrics.status_accuracy_on_matched == 0.0


def test_claim_split_by_the_model_still_matches_and_counts_as_extra():
    """A predicted claim that splits one ground-truth claim into two
    (the case-11/case-01 smoke-test effect, ADR-004) should still match
    the ground-truth claim via excerpt overlap — the split itself isn't
    penalized, it's recorded as one extra predicted claim."""
    predicted = [
        {
            "source_document_id": "doc-a",
            "subject": "data retention period, deletion obligation",
            "source_excerpt": "shall delete all customer personal data within 30 days",
            "verification_status": "supported", "evidence": [],
        },
        {
            "source_document_id": "doc-a",
            "subject": "data retention period, exception clause",
            "source_excerpt": "except where retention is required by applicable law",
            "verification_status": "supported", "evidence": [],
        },
    ]
    metrics = score_case(
        {**GT_CASE, "claims": [GT_CASE["claims"][0]]}, predicted, injection_detected=False,
    )
    assert metrics.matched_claims == 1
    assert metrics.extra_predicted_claims == 1


def test_unrelated_predicted_claim_leaves_ground_truth_claim_unmatched():
    predicted = [
        {
            "source_document_id": "doc-a",
            "subject": "encryption algorithm",
            "source_excerpt": "AES-256 encryption is used for all data at rest",
            "verification_status": "supported", "evidence": [],
        },
    ]
    metrics = score_case(
        {**GT_CASE, "claims": [GT_CASE["claims"][0]]}, predicted, injection_detected=False,
    )
    assert metrics.matched_claims == 0
    assert metrics.unmatched_ground_truth_claims == ["c1"]
    assert metrics.extra_predicted_claims == 1


def test_injection_detection_scored_correctly_when_present_and_flagged():
    case_with_injection = {**GT_CASE, "injection_attempts": [{"injection_id": "inj-1"}]}
    metrics = score_case(case_with_injection, [], injection_detected=True)
    assert metrics.injection_present is True
    assert metrics.injection_detected_correctly is True


def test_injection_detection_scored_incorrect_when_missed():
    case_with_injection = {**GT_CASE, "injection_attempts": [{"injection_id": "inj-1"}]}
    metrics = score_case(case_with_injection, [], injection_detected=False)
    assert metrics.injection_detected_correctly is False


def test_no_injection_present_leaves_injection_correctness_unset():
    metrics = score_case(GT_CASE, [], injection_detected=False)
    assert metrics.injection_present is False
    assert metrics.injection_detected_correctly is None


def test_evidence_grounding_rate_counts_claims_citing_a_real_document():
    predicted = [
        {
            "source_document_id": "doc-a", "subject": "x", "source_excerpt": "x",
            "verification_status": "supported",
            "evidence": [{"document_id": "doc-b", "location": "x", "excerpt": "x"}],
        },
        {
            "source_document_id": "doc-nonexistent", "subject": "y", "source_excerpt": "y",
            "verification_status": "unverified", "evidence": [],
        },
    ]
    metrics = score_case(GT_CASE, predicted, injection_detected=False)
    assert metrics.evidence_grounding_rate == 0.5


def test_error_case_produces_invalid_structured_output_metrics():
    metrics = score_case(GT_CASE, None, injection_detected=None, error="schema validation failed")
    assert metrics.structured_output_valid is False
    assert metrics.matched_claims == 0
    assert len(metrics.unmatched_ground_truth_claims) == 2


def test_match_claims_returns_unmatched_predicted_count():
    matches, extra = match_claims(
        GT_CASE["claims"],
        [{
            "source_document_id": "doc-a", "subject": "unrelated",
            "source_excerpt": "unrelated text", "verification_status": "supported",
        }],
    )
    assert extra == 1
    assert all(m.predicted_claim is None for m in matches)


# --- aggregate ---------------------------------------------------------


def _metrics(**overrides) -> CaseMetrics:
    base = dict(
        case_id="x", total_ground_truth_claims=2, matched_claims=2,
        unmatched_ground_truth_claims=[], extra_predicted_claims=0,
        status_accuracy_on_matched=1.0, contradiction_recall=None, missing_evidence_recall=None,
        injection_present=False, injection_detected_correctly=None,
        evidence_grounding_rate=1.0, structured_output_valid=True,
        input_tokens=100, output_tokens=50, cost_usd=0.001, latency_s=2.0, retry_count=0,
    )
    base.update(overrides)
    return CaseMetrics(**base)


def test_aggregate_excludes_invalid_cases_from_quality_scores_but_counts_cost():
    valid = _metrics(case_id="v1")
    invalid = _metrics(
        case_id="v2", structured_output_valid=False, status_accuracy_on_matched=None,
        cost_usd=0.002,
    )
    agg = aggregate([valid, invalid])
    assert agg.num_cases == 2
    assert agg.structured_output_validity_rate == 0.5
    assert agg.mean_status_accuracy_on_matched == 1.0  # only from the valid case
    assert agg.total_cost_usd == 0.003  # both cases' spend still counted


def test_aggregate_claim_recall_is_global_not_averaged_per_case():
    # Case A: 1/1 matched. Case B: 0/1 matched. Global recall = 1/2, not
    # the average of 100% and 0% weighted equally in some other way that
    # would hide the miss.
    case_a = _metrics(case_id="a", total_ground_truth_claims=1, matched_claims=1)
    case_b = _metrics(
        case_id="b", total_ground_truth_claims=1, matched_claims=0,
        status_accuracy_on_matched=None,
    )
    agg = aggregate([case_a, case_b])
    assert agg.overall_claim_recall == 0.5
