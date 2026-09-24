"""Bounded, single-round targeted re-investigation (decision #13,
ADR-007) for deterministic conflicts (app.reconcile.find_deterministic_conflicts).

Both claims in a deterministic conflict are always produced by the SAME
investigator (app.reconcile's module docstring explains why: routing
already guarantees same-domain documents reach one agent) — so this is a
same-agent follow-up over documents that agent already has, never a
cross-boundary call. The follow-up is still deliberately neutral,
per ADR-007: it describes the discrepancy found in the agent's OWN prior
output, not "the other agent disagrees with you" (there is no other
agent involved here at all) — the anchoring risk ADR-007 guards against
is being told what conclusion to reach, and this prompt asks the agent
to re-examine, not to agree or disagree with anyone.

Exactly one round: this module has no retry-the-round loop and no
parameter for a second attempt. If the agent still can't resolve it from
its own documents, that is the answer — case-18 was deliberately built
so a real conflict has no resolving evidence anywhere in the package,
and "stays unresolved, escalate to human" is the correct outcome, not a
failure to keep trying.
"""

from dataclasses import dataclass
from typing import Any

from app.agents.context_builder import build_context
from app.agents.prompts import OUTPUT_INSTRUCTION
from app.agents.schema import CaseDocument, build_user_message
from app.llm.client import LLMClient, is_retryable
from app.retry import call_with_retry

REINVESTIGATION_TOOL_NAME = "submit_reinvestigation_outcome"
REINVESTIGATION_TOOL_DESCRIPTION = (
    "Record the outcome of re-examining a specific discrepancy in your own prior findings."
)
REINVESTIGATION_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["resolved", "explanation"],
    "additionalProperties": False,
    "properties": {
        "resolved": {"type": "boolean"},
        "explanation": {"type": "string"},
        "resolution_status": {
            "type": ["string", "null"],
            "enum": ["supported", "contradicted", "unverified", "ambiguous", None],
        },
    },
}

REINVESTIGATION_TASK_TEMPLATE = """You previously reviewed the documents below and, among \
other claims, identified the following two that describe what may be the same underlying \
fact but state different values:

- Claim A: subject "{subject_a}", value "{value_a}"
- Claim B: subject "{subject_b}", value "{value_b}"

Re-examine your documents specifically for this topic. Determine one of two things:
1. These are actually consistent — e.g. one is a stated exception to the other, or they \
concern genuinely different scopes or time periods that were not initially obvious. If so, \
explain the reconciling detail and which value (if either) should be treated as authoritative.
2. They do genuinely conflict, and nothing in your documents resolves which is authoritative. \
If so, say so plainly — do not guess or invent a resolution your documents do not support."""


def run_reinvestigation(
    client: LLMClient,
    *,
    model: str,
    agent_type: str,
    domain: str,
    documents: list[CaseDocument],
    claim_a: dict,
    claim_b: dict,
    max_tokens: int = 1024,
    max_attempts: int = 3,
) -> dict:
    """One bounded call. Returns a dict with resolved/explanation/
    resolution_status — the caller (app.reconcile orchestration) decides
    what to do with an unresolved outcome (mark the Conflict open/
    escalated), this function does not retry the round itself."""
    context_documents = build_context(documents, domain)
    task = REINVESTIGATION_TASK_TEMPLATE.format(
        subject_a=claim_a.get("subject"), value_a=claim_a.get("value"),
        subject_b=claim_b.get("subject"), value_b=claim_b.get("value"),
    )
    system = "\n\n".join([task, OUTPUT_INSTRUCTION]).format(
        tool_name=REINVESTIGATION_TOOL_NAME
    )
    user_message = build_user_message(context_documents)

    def attempt() -> dict:
        result = client.call_with_forced_tool(
            model=model,
            system=system,
            user_message=user_message,
            tool_name=REINVESTIGATION_TOOL_NAME,
            tool_description=REINVESTIGATION_TOOL_DESCRIPTION,
            tool_input_schema=REINVESTIGATION_INPUT_SCHEMA,
            max_tokens=max_tokens,
        )
        return {
            "resolved": result.tool_input["resolved"],
            "explanation": result.tool_input["explanation"],
            "resolution_status": result.tool_input.get("resolution_status"),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }

    return call_with_retry(attempt, is_retryable=is_retryable, max_attempts=max_attempts)


@dataclass
class ReinvestigationRecord:
    """What app.reconcile needs to know happened, for the Conflict record
    and for cost accounting — a thin wrapper so the orchestration layer
    doesn't reach into the raw dict shape directly."""

    conflict_claim_ids: tuple[str, str]
    agent_type: str
    resolved: bool
    explanation: str
    resolution_status: str | None
    input_tokens: int
    output_tokens: int
