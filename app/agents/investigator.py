"""Independent domain-scoped investigators (Phase 7, ADR-001/ADR-004/ADR-007).

Two agent types — security_investigator, privacy_investigator — that
share everything Gate 6 needs held constant (the verification rubric,
evidence-grounding and injection-resistance instructions, the output
schema, the retry policy: app/agents/prompts.py, app/agents/schema.py)
and differ only in domain framing and, critically, in which documents
they ever see at all (app/agents/context_builder.py). Each extracts and
verifies its own claims independently — there is no shared upstream
claim-extraction step (ADR-004): claim identification itself is part of
what independence is testing.
"""

from app.agents.context_builder import build_context
from app.agents.prompts import (
    EVIDENCE_GROUNDING_INSTRUCTION,
    INJECTION_RESISTANCE_INSTRUCTION,
    OUTPUT_INSTRUCTION,
    VERIFICATION_RUBRIC,
)
from app.agents.schema import (
    FINDINGS_INPUT_SCHEMA,
    FINDINGS_TOOL_DESCRIPTION,
    FINDINGS_TOOL_NAME,
    AgentResult,
    CaseDocument,
    build_user_message,
    validate_tool_output,
)
from app.llm.client import LLMClient, is_retryable
from app.retry import call_with_retry

AGENT_TYPE_TO_DOMAIN = {
    "security_investigator": "security",
    "privacy_investigator": "privacy_ai_governance",
}

DOMAIN_TASK_PREAMBLE = {
    "security": """You are the SECURITY investigator in an independent, multi-perspective \
vendor due-diligence review. A separate investigator is independently reviewing this \
vendor's privacy and AI-governance documentation; you do not have access to their work \
and will not see it before or after this review, and you should not assume anything \
about content you have not personally been given.

You have been given only the documents classified as security-relevant for this case: \
security questionnaires, security whitepapers, SOC-style reports, penetration-test \
attestations, and contract/SLA documents with security-relevant terms. Your job is to \
identify the vendor's security-domain claims — certifications, technical controls \
(encryption, access control, monitoring), testing practices, and infrastructure \
commitments — and verify each one against the documents you have.

If verifying a claim would require a document outside your scope (a DPA, a privacy \
policy, a subprocessor list), that is not a gap in your access to work around — it means \
the claim cannot be verified from what you have, and unverified is very likely the \
correct, honest answer. Do not speculate about what a document you don't have might say.""",

    "privacy_ai_governance": """You are the PRIVACY/AI-GOVERNANCE investigator in an \
independent, multi-perspective vendor due-diligence review. A separate investigator is \
independently reviewing this vendor's security documentation; you do not have access to \
their work and will not see it before or after this review, and you should not assume \
anything about content you have not personally been given.

You have been given only the documents classified as privacy/AI-governance-relevant for \
this case: DPAs, privacy policies, subprocessor lists, and AI/model governance \
documentation. Your job is to identify the vendor's privacy and AI-governance claims — \
data handling and retention practices, subprocessor disclosures, policy commitments, and \
AI/model training and data-use practices — and verify each one against the documents you \
have.

If verifying a claim would require a document outside your scope (a security \
questionnaire, a SOC report, a penetration-test attestation), that is not a gap in your \
access to work around — it means the claim cannot be verified from what you have, and \
unverified is very likely the correct, honest answer. Do not speculate about what a \
document you don't have might say.""",
}


def _build_system_prompt(domain: str) -> str:
    return "\n\n".join([
        DOMAIN_TASK_PREAMBLE[domain],
        VERIFICATION_RUBRIC,
        EVIDENCE_GROUNDING_INSTRUCTION,
        INJECTION_RESISTANCE_INSTRUCTION,
        OUTPUT_INSTRUCTION,
    ]).format(tool_name=FINDINGS_TOOL_NAME)


def run_investigator(
    client: LLMClient,
    *,
    model: str,
    agent_type: str,
    documents: list[CaseDocument],
    max_tokens: int = 4096,
    max_attempts: int = 3,
) -> AgentResult:
    """Run one independent investigator. `documents` is the FULL case
    document set — build_context() (the only place domain filtering
    happens) restricts it to this agent_type's domain before anything
    else touches it. Same retry/validation policy as run_baseline
    (app.agents.baseline) — a schema violation is not retried (ADR-010),
    a retryable API error is (app.llm.client.is_retryable)."""
    if agent_type not in AGENT_TYPE_TO_DOMAIN:
        raise ValueError(f"unknown agent_type {agent_type!r}")
    domain = AGENT_TYPE_TO_DOMAIN[agent_type]

    context_documents = build_context(documents, domain)
    if not context_documents:
        # A real, non-hypothetical case (5 of 18 eval cases have zero
        # documents for one investigator, e.g. case-03 has no privacy
        # documents at all) — found by measuring real prompt sizes before
        # the real run, not discovered as a wasted API call afterward.
        # There is nothing in this domain to investigate; calling the
        # model with an empty evidence package would be meaningless and
        # would spend real budget for a response that can only be "no
        # claims found." No LLM call, no cost, no tokens.
        return AgentResult(
            claims=[], injection_detected=False, injection_note="",
            input_tokens=0, output_tokens=0, model=model,
        )

    system = _build_system_prompt(domain)
    user_message = build_user_message(context_documents)

    def attempt() -> AgentResult:
        result = client.call_with_forced_tool(
            model=model,
            system=system,
            user_message=user_message,
            tool_name=FINDINGS_TOOL_NAME,
            tool_description=FINDINGS_TOOL_DESCRIPTION,
            tool_input_schema=FINDINGS_INPUT_SCHEMA,
            max_tokens=max_tokens,
        )
        validate_tool_output(result.tool_input)
        return AgentResult(
            claims=result.tool_input["claims"],
            injection_detected=result.tool_input["injection_detected"],
            injection_note=result.tool_input["injection_note"],
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model=result.model,
        )

    return call_with_retry(attempt, is_retryable=is_retryable, max_attempts=max_attempts)
