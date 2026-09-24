import anthropic
import pytest

from app.agents.investigator import run_investigator
from app.agents.schema import CaseDocument, InvalidAgentOutputError
from app.retry import RetriesExhaustedError
from tests.fakes import FakeLLMClient, fake_api_error

SECURITY_DOC = CaseDocument(
    document_id="doc-sec", filename="s.md",
    text="Security whitepaper content.", domain="security",
)
PRIVACY_DOC = CaseDocument(
    document_id="doc-priv", filename="p.md",
    text="DPA content, retention 30 days.", domain="privacy_ai_governance",
)
BOTH_DOC = CaseDocument(
    document_id="doc-both", filename="b.md",
    text="Questionnaire mixing both domains.", domain="both",
)
ALL_DOCS = [SECURITY_DOC, PRIVACY_DOC, BOTH_DOC]

VALID_RESPONSE = {
    "claims": [{
        "subject": "x", "predicate": "y", "value": "z", "unit": None,
        "temporal_scope": None, "domain": "security", "claim_type": "technical_control",
        "source_document_id": "doc-sec", "source_location": "x", "source_excerpt": "x",
        "verification_status": "supported", "rationale": "x", "evidence": [],
    }],
    "injection_detected": False, "injection_note": "",
}


def test_empty_domain_skips_the_api_call_entirely():
    """A real scenario, not a hypothetical: 5 of 18 real eval cases have
    zero documents for one investigator (e.g. case-03 has no privacy
    documents at all). Calling the model with nothing to investigate
    would be meaningless and would spend real budget for a response that
    can only be empty — found by measuring real prompt sizes before the
    real run, not discovered as a wasted API call afterward."""
    client = FakeLLMClient(responses=[])  # would raise if called at all
    security_only_docs = [SECURITY_DOC]
    result = run_investigator(
        client, model="m", agent_type="privacy_investigator", documents=security_only_docs,
    )
    assert result.claims == []
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert len(client.calls) == 0


def test_unknown_agent_type_is_rejected():
    client = FakeLLMClient(responses=[VALID_RESPONSE])
    with pytest.raises(ValueError, match="unknown agent_type"):
        run_investigator(client, model="m", agent_type="not_a_real_agent", documents=ALL_DOCS)


def test_security_investigator_only_receives_security_and_both_documents():
    client = FakeLLMClient(responses=[VALID_RESPONSE])
    run_investigator(client, model="m", agent_type="security_investigator", documents=ALL_DOCS)
    user_message = client.calls[0]["user_message"]
    assert 'id="doc-sec"' in user_message
    assert 'id="doc-both"' in user_message
    assert 'id="doc-priv"' not in user_message
    assert "DPA content" not in user_message


def test_privacy_investigator_only_receives_privacy_and_both_documents():
    client = FakeLLMClient(responses=[VALID_RESPONSE])
    run_investigator(client, model="m", agent_type="privacy_investigator", documents=ALL_DOCS)
    user_message = client.calls[0]["user_message"]
    assert 'id="doc-priv"' in user_message
    assert 'id="doc-both"' in user_message
    assert 'id="doc-sec"' not in user_message
    assert "Security whitepaper" not in user_message


def test_security_and_privacy_prompts_have_different_domain_framing():
    client_a = FakeLLMClient(responses=[VALID_RESPONSE])
    client_b = FakeLLMClient(responses=[VALID_RESPONSE])
    run_investigator(client_a, model="m", agent_type="security_investigator", documents=ALL_DOCS)
    run_investigator(client_b, model="m", agent_type="privacy_investigator", documents=ALL_DOCS)

    system_a, system_b = client_a.calls[0]["system"], client_b.calls[0]["system"]
    assert system_a != system_b
    assert "SECURITY investigator" in system_a
    assert "PRIVACY/AI-GOVERNANCE investigator" in system_b


def test_both_investigators_share_the_identical_verification_rubric():
    """Gate 6 fairness (ADR-006): domain framing may differ, the grading
    standard must not."""
    client_a = FakeLLMClient(responses=[VALID_RESPONSE])
    client_b = FakeLLMClient(responses=[VALID_RESPONSE])
    run_investigator(client_a, model="m", agent_type="security_investigator", documents=ALL_DOCS)
    run_investigator(client_b, model="m", agent_type="privacy_investigator", documents=ALL_DOCS)

    from app.agents.prompts import VERIFICATION_RUBRIC
    assert VERIFICATION_RUBRIC in client_a.calls[0]["system"]
    assert VERIFICATION_RUBRIC in client_b.calls[0]["system"]


def test_investigator_prompt_instructs_scope_limited_honesty():
    """Domain-scoped agents need explicit guidance that being unable to
    verify due to restricted scope is a real 'unverified,' not a defect
    to route around by speculating — otherwise restricting context could
    just push the model toward guessing instead of admitting the limit."""
    client = FakeLLMClient(responses=[VALID_RESPONSE])
    run_investigator(client, model="m", agent_type="security_investigator", documents=ALL_DOCS)
    assert "unverified is very likely the correct" in client.calls[0]["system"]


def test_missing_required_field_raises_and_is_not_retried():
    malformed = {"claims": [], "injection_detected": False}  # missing injection_note
    client = FakeLLMClient(responses=[malformed])
    with pytest.raises(InvalidAgentOutputError):
        run_investigator(
            client, model="m", agent_type="security_investigator", documents=ALL_DOCS,
        )
    assert len(client.calls) == 1


def test_retryable_error_is_retried_then_succeeds():
    client = FakeLLMClient(responses=[
        fake_api_error(anthropic.RateLimitError, 429), VALID_RESPONSE,
    ])
    result = run_investigator(
        client, model="m", agent_type="security_investigator", documents=ALL_DOCS, max_attempts=3,
    )
    assert len(result.claims) == 1
    assert len(client.calls) == 2


def test_exhausting_retries_raises():
    client = FakeLLMClient(responses=[fake_api_error(anthropic.RateLimitError, 429)] * 3)
    with pytest.raises(RetriesExhaustedError):
        run_investigator(
            client, model="m", agent_type="security_investigator",
            documents=ALL_DOCS, max_attempts=3,
        )
