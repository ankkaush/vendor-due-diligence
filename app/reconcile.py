"""Deterministic-first reconciliation of pooled investigator claims
(Phase 8, architecture.md's RECONCILING step).

Two distinct mechanisms, deliberately different, because Phase 7's real
evaluation showed they solve different problems:

1. **Deterministic conflict detection** (`find_deterministic_conflicts`):
   claims from the SAME domain with matching subject/predicate but
   different values — e.g. case-02/case-07/case-18's retention-period
   pairs. Both claims in a deterministic conflict always come from the
   same investigator (routing already guarantees same-domain documents
   reach the same agent), so resolving one is a same-agent follow-up
   question, not a cross-boundary one — see app/reinvestigate.py.

2. **Semantic adjudication** (`adjudicate_semantic_conflicts`, one LLM
   call per case, not per pair): claims that are substantively in tension
   despite different surface subject/predicate wording — the
   cross_domain_conflict category Phase 7's raw investigators measured at
   0% (eval/COST_LOG.md), because resolving it requires comparing BOTH
   domains' claims side by side, which neither domain-scoped investigator
   can do alone (ADR-007) but the reconciler — which is not
   context-restricted, because it isn't an investigator — can. No
   re-investigation call is needed for a genuine cross-domain conflict:
   asking either investigator to "look again" wouldn't give it the other
   domain's document it structurally never receives.
"""

from dataclasses import dataclass
from typing import Any

from app.agents.prompts import OUTPUT_INSTRUCTION
from app.agents.schema import AgentResult, CaseDocument
from app.llm.client import LLMClient, is_retryable
from app.reinvestigate import ReinvestigationRecord, run_reinvestigation
from app.retry import call_with_retry

WORD_MIN_LEN = 3


def _word_set(text: str) -> set[str]:
    return {w.lower() for w in text.split() if len(w) > WORD_MIN_LEN}


def _jaccard(a: str, b: str) -> float:
    wa, wb = _word_set(a), _word_set(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


SAME_TOPIC_THRESHOLD = 0.4


@dataclass
class PooledClaim:
    """A claim tagged with a stable id and which agent produced it —
    reconciliation's own bookkeeping, not part of the agent output
    schema (app/agents/schema.py), since only the reconciler needs it."""

    claim_id: str
    agent_type: str
    domain: str
    data: dict[str, Any]  # the raw claim dict from AgentResult.claims


def pool_claims(security_result: AgentResult, privacy_result: AgentResult) -> list[PooledClaim]:
    pooled = []
    for i, claim in enumerate(security_result.claims):
        pooled.append(PooledClaim(f"security-{i}", "security_investigator", "security", claim))
    for i, claim in enumerate(privacy_result.claims):
        pooled.append(
            PooledClaim(f"privacy-{i}", "privacy_investigator", "privacy_ai_governance", claim)
        )
    return pooled


@dataclass
class DeterministicConflict:
    claim_ids: tuple[str, str]
    agent_type: str  # both claims are always from the same agent — see module docstring
    subject_similarity: float


def find_deterministic_conflicts(claims: list[PooledClaim]) -> list[DeterministicConflict]:
    """Same domain, matching subject/predicate, different value. Pure,
    no LLM — this is the "schema-level diff" architecture.md specifies
    runs before any semantic adjudication is attempted."""
    conflicts = []
    for i, a in enumerate(claims):
        for b in claims[i + 1:]:
            if a.agent_type != b.agent_type:
                continue  # cross-domain pairs are semantic adjudication's job, not this pass's
            if a.data.get("predicate") != b.data.get("predicate"):
                continue
            similarity = _jaccard(a.data.get("subject", ""), b.data.get("subject", ""))
            if similarity < SAME_TOPIC_THRESHOLD:
                continue
            if a.data.get("value") == b.data.get("value"):
                continue  # same topic, same value — agreement, not a conflict
            conflicts.append(DeterministicConflict(
                claim_ids=(a.claim_id, b.claim_id),
                agent_type=a.agent_type,
                subject_similarity=similarity,
            ))
    return conflicts


# --- Semantic adjudication (one LLM call per case) --------------------------

ADJUDICATION_TOOL_NAME = "submit_semantic_conflicts"
ADJUDICATION_TOOL_DESCRIPTION = (
    "Record any substantive conflicts found among the pooled claims, beyond "
    "the ones already identified by exact-topic matching."
)
ADJUDICATION_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["conflicts"],
    "additionalProperties": False,
    "properties": {
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["claim_ids", "conflict_type", "confidence", "rationale"],
                "additionalProperties": False,
                "properties": {
                    "claim_ids": {
                        "type": "array", "items": {"type": "string"}, "minItems": 2,
                    },
                    "conflict_type": {"enum": [
                        "direct_contradiction", "subtle_contradiction",
                        "cross_domain_conflict", "version_conflict",
                    ]},
                    "confidence": {"enum": ["high", "low"]},
                    "rationale": {"type": "string"},
                },
            },
        },
    },
}

ADJUDICATION_SYSTEM_PROMPT = "\n\n".join([
    """You are the reconciler in a multi-agent vendor due-diligence review. Two independent \
investigators — security and privacy/AI-governance — each reviewed only their own domain's \
documents and produced the claims below, tagged with a claim_id and which investigator \
produced them. Neither investigator could see the other's claims or documents while working.

## Your task

You, unlike either investigator, can see both sets of claims side by side. Identify any \
pairs (or larger groups) of claims that are substantively in tension with each other — \
including cases where the connection is not obvious from matching wording (e.g. a security \
claim about where data is processed conflicting with a privacy claim disclosing a \
sub-processor's location). Do not re-flag claims that are simply about unrelated topics. \
Do not fabricate a conflict between claims that are actually compatible — a claim being \
vague or under-specified is not, by itself, a conflict with a more specific claim elsewhere \
unless they are actually incompatible.

## Confidence

For every conflict you report, also assign a confidence level:

- **high**: the claims themselves, taken at face value as written, explicitly assert facts or \
values that cannot both be true. You don't need to add an assumption they don't state to see \
the incompatibility.
- **low**: the claims are thematically related and could plausibly interact, but establishing \
an actual conflict requires an inference beyond what either claim states outright.

Do not report a conflict — at any confidence level — built on an inferred operational \
dependency between two claims about different subjects (e.g. "claim A's monitoring would be \
needed to verify claim B's deletion happened") unless one of the documents actually states \
that dependency. If you find yourself constructing a scenario or mechanism connecting two \
claims that neither claim nor any document actually describes, that is not a conflict — leave \
it out entirely, don't report it as low confidence.

For each conflict, cite the exact claim_ids involved and explain the substantive tension in \
rationale — this is read by a human reviewer deciding what to do about it, not just a label.""",
    OUTPUT_INSTRUCTION,
]).format(tool_name=ADJUDICATION_TOOL_NAME)


def _build_adjudication_user_message(claims: list[PooledClaim]) -> str:
    lines = []
    for c in claims:
        lines.append(
            f'<claim id="{c.claim_id}" agent="{c.agent_type}" domain="{c.domain}">\n'
            f'subject: {c.data.get("subject")}\n'
            f'predicate: {c.data.get("predicate")}\n'
            f'value: {c.data.get("value")}\n'
            f'verification_status: {c.data.get("verification_status")}\n'
            f'rationale: {c.data.get("rationale")}\n'
            f"</claim>"
        )
    return "\n".join(lines)


@dataclass
class SemanticConflict:
    claim_ids: list[str]
    conflict_type: str
    confidence: str  # "high" | "low" — only "high" may overwrite verification_status
    rationale: str


@dataclass
class AdjudicationResult:
    conflicts: list[SemanticConflict]
    input_tokens: int
    output_tokens: int


def adjudicate_semantic_conflicts(
    client: LLMClient,
    *,
    model: str,
    claims: list[PooledClaim],
    max_tokens: int = 2048,
    max_attempts: int = 3,
) -> AdjudicationResult:
    """One call, given every pooled claim for a case at once — deliberately
    not one call per candidate pair, both for cost and because the
    reconciler benefits from seeing the whole picture at once, the same
    reason a human reconciler would review a full claim list rather than
    isolated pairs."""
    if not claims:
        return AdjudicationResult(conflicts=[], input_tokens=0, output_tokens=0)

    user_message = _build_adjudication_user_message(claims)

    def attempt() -> AdjudicationResult:
        result = client.call_with_forced_tool(
            model=model,
            system=ADJUDICATION_SYSTEM_PROMPT,
            user_message=user_message,
            tool_name=ADJUDICATION_TOOL_NAME,
            tool_description=ADJUDICATION_TOOL_DESCRIPTION,
            tool_input_schema=ADJUDICATION_INPUT_SCHEMA,
            max_tokens=max_tokens,
        )
        conflicts = [
            SemanticConflict(
                claim_ids=c["claim_ids"], conflict_type=c["conflict_type"],
                confidence=c["confidence"], rationale=c["rationale"],
            )
            for c in result.tool_input["conflicts"]
        ]
        return AdjudicationResult(
            conflicts=conflicts,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    return call_with_retry(attempt, is_retryable=is_retryable, max_attempts=max_attempts)


# --- Orchestration: deterministic -> re-investigation, plus semantic ------


@dataclass
class Conflict:
    claim_ids: list[str]
    conflict_type: str
    status: str  # "resolved" | "open" (escalated to human review, decision #3)
    resolution_method: str  # "reinvestigation" | "semantic_adjudication"
    resolution_rationale: str


@dataclass
class ReconciliationResult:
    reconciled_claims: list[PooledClaim]  # verification_status updated in place where resolved
    conflicts: list[Conflict]
    semantic_input_tokens: int
    semantic_output_tokens: int
    reinvestigation_records: list[ReinvestigationRecord]


def reconcile(
    client: LLMClient,
    *,
    model: str,
    security_result: AgentResult,
    privacy_result: AgentResult,
    documents: list[CaseDocument],
) -> ReconciliationResult:
    """The full RECONCILING step (architecture.md): deterministic
    conflicts get one bounded re-investigation round each
    (app.reinvestigate — always same-agent, per this module's docstring);
    remaining claims go through one semantic-adjudication call, which
    resolves cross-domain-style conflicts directly (no re-investigation —
    see module docstring for why one wouldn't help there)."""
    pooled = pool_claims(security_result, privacy_result)
    claim_by_id = {c.claim_id: c for c in pooled}

    deterministic = find_deterministic_conflicts(pooled)
    deterministic_ids = {cid for dc in deterministic for cid in dc.claim_ids}

    conflicts: list[Conflict] = []
    reinvestigation_records: list[ReinvestigationRecord] = []

    for dc in deterministic:
        claim_a = claim_by_id[dc.claim_ids[0]]
        claim_b = claim_by_id[dc.claim_ids[1]]
        outcome = run_reinvestigation(
            client, model=model, agent_type=dc.agent_type, domain=claim_a.domain,
            documents=documents, claim_a=claim_a.data, claim_b=claim_b.data,
        )
        reinvestigation_records.append(ReinvestigationRecord(
            conflict_claim_ids=dc.claim_ids, agent_type=dc.agent_type,
            resolved=outcome["resolved"], explanation=outcome["explanation"],
            resolution_status=outcome.get("resolution_status"),
            input_tokens=outcome["input_tokens"], output_tokens=outcome["output_tokens"],
        ))
        if outcome["resolved"] and outcome.get("resolution_status"):
            claim_a.data["verification_status"] = outcome["resolution_status"]
            claim_b.data["verification_status"] = outcome["resolution_status"]
        conflicts.append(Conflict(
            claim_ids=list(dc.claim_ids),
            conflict_type="direct_contradiction",
            status="resolved" if outcome["resolved"] else "open",
            resolution_method="reinvestigation",
            resolution_rationale=outcome["explanation"],
        ))

    remaining = [c for c in pooled if c.claim_id not in deterministic_ids]
    adjudication = adjudicate_semantic_conflicts(client, model=model, claims=remaining)
    for sc in adjudication.conflicts:
        if sc.confidence == "high":
            for cid in sc.claim_ids:
                if cid in claim_by_id:
                    claim_by_id[cid].data["verification_status"] = "contradicted"
        # "low" confidence leaves verification_status untouched — a speculative
        # adjudication must not silently overwrite an otherwise-correct label
        # (Gate 6's Phase 8 run showed this is exactly how over-triggered
        # semantic adjudication turns into a measured accuracy regression).
        conflicts.append(Conflict(
            claim_ids=sc.claim_ids,
            conflict_type=sc.conflict_type,
            status="resolved" if sc.confidence == "high" else "open",
            resolution_method="semantic_adjudication",
            resolution_rationale=sc.rationale,
        ))

    return ReconciliationResult(
        reconciled_claims=pooled,
        conflicts=conflicts,
        semantic_input_tokens=adjudication.input_tokens,
        semantic_output_tokens=adjudication.output_tokens,
        reinvestigation_records=reinvestigation_records,
    )
