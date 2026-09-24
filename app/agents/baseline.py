"""The strong single-agent baseline (Phase 6, ADR-001/ADR-006).

This is the floor the multi-agent architecture has to beat at Gate 6. Its
"strength" is architectural, not about model tier (ADR-009): full-package
context (unlike the domain-scoped investigators Phase 7 adds), the exact
same verification rubric and evidence-grounding/injection-resistance
instructions the investigators use (app/agents/prompts.py — a different
prompt would mean Gate 6 was comparing grading standards, not
architectures), and enforced structured output (ADR-010) — not a quick
prompt asking nicely.

Pure function shape by design: documents in, structured findings out. No
database, no case object, no HTTP — callable identically from
eval/run_baseline.py and from a real orchestrator once one exists.
"""

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
    InvalidAgentOutputError,
    build_user_message,
    validate_tool_output,
)
from app.llm.client import LLMClient, is_retryable
from app.retry import call_with_retry

TASK_PREAMBLE = """You are performing an evidence-based verification pass over a complete \
vendor due-diligence evidence package, as part of an internal vendor review. \
You are given every document submitted for this case.

## Your task

Identify the distinct factual claims the vendor makes across these documents, and for \
each one, determine whether the package's own evidence supports it. You are not \
approving or rejecting the vendor — that decision is made by a human reviewer after \
your findings are reviewed. Your job is to trace each claim to evidence, not to render \
a verdict on the vendor."""

SYSTEM_PROMPT = "\n\n".join([
    TASK_PREAMBLE,
    VERIFICATION_RUBRIC,
    EVIDENCE_GROUNDING_INSTRUCTION,
    INJECTION_RESISTANCE_INSTRUCTION,
    OUTPUT_INSTRUCTION,
])

# Re-exported for backward-compatible imports (`from app.agents.baseline
# import CaseDocument`, etc.) — the canonical definitions now live in
# app.agents.schema, shared with app.agents.investigator.
__all__ = [
    "SYSTEM_PROMPT", "FINDINGS_TOOL_NAME", "FINDINGS_TOOL_DESCRIPTION",
    "FINDINGS_INPUT_SCHEMA", "CaseDocument", "AgentResult", "InvalidAgentOutputError",
    "run_baseline",
]


def run_baseline(
    client: LLMClient,
    *,
    model: str,
    documents: list[CaseDocument],
    max_tokens: int = 4096,
    max_attempts: int = 3,
) -> AgentResult:
    """Run the baseline verification pass once. Retries only on
    architecture.md's retryable-failure classes (app.llm.client.is_retryable)
    — a malformed/invalid tool call is NOT retried here, since that is a
    prompt/schema problem a retry can't fix; it's raised as
    InvalidAgentOutputError for the caller (eval/run_baseline.py) to
    record as a real structured-output-validity failure, per ADR-010."""
    system = SYSTEM_PROMPT.format(tool_name=FINDINGS_TOOL_NAME)
    user_message = build_user_message(documents)

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
