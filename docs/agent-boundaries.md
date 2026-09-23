# Agent Boundaries

**Status: approved design (Phase 7 target for implementation and boundary tests).**

Agent independence is a technically enforced property, not an instruction
("Agent A is told not to see Agent B's output"). See
[ADR-007](decisions/ADR-007-agent-context-isolation.md) for the full
rationale.

## The invariant

`build_security_context(case_id)` and `build_privacy_context(case_id)` each
have a **restricted query surface**: they can only query
`EvidenceDocument`/`DocumentVersion` rows matching that agent's domain in a
fixed routing table. Neither function has any code path, parameter, or join
capable of reaching `Finding` or another agent's `AgentRun` rows — not
"won't," **can't**.

This must hold regardless of:
- execution order (Agent A first, Agent B first, or concurrent),
- whether the other agent has already completed and its findings already
  exist in the database,
- workflow crash-and-resume,
- retries of either agent.

**Verification:** `test_investigator_context_has_no_cross_agent_data_even_when_available`
seeds Agent A's `Finding` rows first, then calls Agent B's context-builder,
and asserts the returned context contains no reference — direct or
indirect — to Agent A's data. This test is designed to fail loudly if a
future "debugging convenience" join is added.

## Per-agent boundary specification

| Boundary | Security Investigator | Privacy/AI-Gov Investigator |
|---|---|---|
| Allowed documents | Security-routed `doc_type`s only | Privacy/AI-governance-routed `doc_type`s only |
| Allowed DB records | Read-only, scoped to its own case + its own domain documents | Same, own domain |
| Tools/APIs | None (ADR-003) | None (ADR-003) |
| Output fields | Strict schema: verification_status, claim_text, evidence_citations[], rationale | Same schema, own domain |
| Forbidden data | The other investigator's `Finding`/`AgentRun` rows, at all times | Same |
| Execution identity | Own `AgentRun` row, own token/cost/timeout accounting | Same |
| Persistence | None — returns structured output; orchestrator writes it | Same |

Both agents are pure functions: context in, schema-validated JSON out. All
persistence and side effects belong to deterministic orchestrator code.

## Re-investigation preserves independence too

When a conflict triggers the bounded re-investigation round (max 1, decision
#13), the re-invoked agent is given a **neutral, domain-scoped follow-up** —
e.g. "re-examine the retention-period claim, with particular attention to
[document/section]" — never "Agent B concluded X, do you agree?" Exposing
the other agent's conclusion would reintroduce the anchoring risk that
independence exists to prevent. The orchestrator reformulates disagreements;
it never relays them verbatim.
