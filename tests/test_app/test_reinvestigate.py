import anthropic
import pytest

from app.agents.schema import CaseDocument
from app.reinvestigate import run_reinvestigation
from app.retry import RetriesExhaustedError
from tests.fakes import FakeLLMClient, fake_api_error

SECURITY_DOC = CaseDocument(
    document_id="doc-sec", filename="s.md", text="Security content.", domain="security",
)
PRIVACY_DOC_V1 = CaseDocument(
    document_id="doc-dpa", filename="dpa.md", text="Retention: 30 days.",
    domain="privacy_ai_governance",
)
PRIVACY_DOC_V2 = CaseDocument(
    document_id="doc-backup", filename="backup.md", text="Backup retention: 90 days.",
    domain="privacy_ai_governance",
)
ALL_DOCS = [SECURITY_DOC, PRIVACY_DOC_V1, PRIVACY_DOC_V2]

CLAIM_A = {"subject": "data retention period", "value": "30"}
CLAIM_B = {"subject": "backup retention period", "value": "90"}

RESOLVED_RESPONSE = {
    "resolved": True,
    "explanation": "The backup retention is a distinct operational policy from the "
                    "contractual deletion commitment; the DPA's 30-day figure governs.",
    "resolution_status": "contradicted",
}
UNRESOLVED_RESPONSE = {
    "resolved": False,
    "explanation": "No document in my set reconciles the two figures.",
    "resolution_status": None,
}


def test_reinvestigation_only_receives_documents_for_its_own_domain():
    client = FakeLLMClient(responses=[RESOLVED_RESPONSE])
    run_reinvestigation(
        client, model="m", agent_type="privacy_investigator", domain="privacy_ai_governance",
        documents=ALL_DOCS, claim_a=CLAIM_A, claim_b=CLAIM_B,
    )
    user_message = client.calls[0]["user_message"]
    assert 'id="doc-dpa"' in user_message
    assert 'id="doc-backup"' in user_message
    assert 'id="doc-sec"' not in user_message
    assert "Security content" not in user_message


def test_prompt_describes_the_discrepancy_neutrally_not_as_another_agents_claim():
    """ADR-007: the follow-up must not be framed as 'agent X disagrees
    with you' — there is no other agent in this picture at all, only the
    same investigator's own two claims."""
    client = FakeLLMClient(responses=[RESOLVED_RESPONSE])
    run_reinvestigation(
        client, model="m", agent_type="privacy_investigator", domain="privacy_ai_governance",
        documents=ALL_DOCS, claim_a=CLAIM_A, claim_b=CLAIM_B,
    )
    system = client.calls[0]["system"]
    assert "data retention period" in system
    assert "backup retention period" in system
    assert "another investigator" not in system.lower()
    assert "the other agent" not in system.lower()


def test_prompt_rules_out_later_effective_date_alone_as_a_resolution():
    """Phase 8's real run showed this exact failure mode: re-investigation
    resolved a deliberately unresolvable version conflict (case-07 — two
    DPA versions, no changelog) by treating the later-dated document as
    automatically authoritative, which the case's ground truth explicitly
    designed to be wrong (eval/COST_LOG.md). The prompt must rule this
    shortcut out explicitly, not just say "don't invent a resolution.\""""
    client = FakeLLMClient(responses=[RESOLVED_RESPONSE])
    run_reinvestigation(
        client, model="m", agent_type="privacy_investigator", domain="privacy_ai_governance",
        documents=ALL_DOCS, claim_a=CLAIM_A, claim_b=CLAIM_B,
    )
    system = client.calls[0]["system"].lower()
    assert "later effective date" in system or "later revision date" in system
    assert "does not" in system or "not, by itself" in system
    assert "supersede" in system


def test_resolved_outcome_is_parsed():
    client = FakeLLMClient(responses=[RESOLVED_RESPONSE])
    result = run_reinvestigation(
        client, model="m", agent_type="privacy_investigator", domain="privacy_ai_governance",
        documents=ALL_DOCS, claim_a=CLAIM_A, claim_b=CLAIM_B,
    )
    assert result["resolved"] is True
    assert result["resolution_status"] == "contradicted"


def test_unresolved_outcome_is_parsed_and_is_not_an_error():
    """case-18's design point: a genuinely unresolvable conflict is a
    valid, expected outcome, not a failure."""
    client = FakeLLMClient(responses=[UNRESOLVED_RESPONSE])
    result = run_reinvestigation(
        client, model="m", agent_type="privacy_investigator", domain="privacy_ai_governance",
        documents=ALL_DOCS, claim_a=CLAIM_A, claim_b=CLAIM_B,
    )
    assert result["resolved"] is False
    assert result["resolution_status"] is None


def test_retryable_error_is_retried_then_succeeds():
    client = FakeLLMClient(responses=[
        fake_api_error(anthropic.RateLimitError, 429), RESOLVED_RESPONSE,
    ])
    result = run_reinvestigation(
        client, model="m", agent_type="privacy_investigator", domain="privacy_ai_governance",
        documents=ALL_DOCS, claim_a=CLAIM_A, claim_b=CLAIM_B, max_attempts=3,
    )
    assert result["resolved"] is True
    assert len(client.calls) == 2


def test_exhausting_retries_raises():
    client = FakeLLMClient(responses=[fake_api_error(anthropic.RateLimitError, 429)] * 3)
    with pytest.raises(RetriesExhaustedError):
        run_reinvestigation(
            client, model="m", agent_type="privacy_investigator", domain="privacy_ai_governance",
            documents=ALL_DOCS, claim_a=CLAIM_A, claim_b=CLAIM_B, max_attempts=3,
        )
