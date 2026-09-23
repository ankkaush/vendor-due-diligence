# ADR-007: Agent independence is enforced by data-access boundaries, not execution order

**Status:** Accepted
**Date:** 2026-09-23

## Context

An earlier description of agent isolation partly relied on execution
ordering ("Agent B's context is built before Agent A's findings exist"). An
ordering-based guarantee is not sufficient: it silently breaks under retries,
crash-resume, concurrent execution, or simply if Agent A happens to finish
first for scheduling reasons unrelated to the design.

## Decision

Each investigator's context-builder function (`build_security_context`,
`build_privacy_context`) has a **restricted query surface**: it can only
query documents matching its own domain in a fixed routing table. Neither
function has any code path, parameter, or join capable of reaching another
agent's `Finding` or `AgentRun` rows — regardless of whether those rows
already exist, regardless of execution order, retries, or resumption.

This is verified by a specific test —
`test_investigator_context_has_no_cross_agent_data_even_when_available` —
which seeds the other agent's findings first, then asserts the boundary
still holds. The test is designed to catch a future "helpful" join added
for debugging convenience.

## Re-investigation

During the bounded re-investigation round (max 1, decision #13), the
re-invoked agent receives a neutral, domain-scoped follow-up question
formulated by the orchestrator — never the other agent's identity or stated
conclusion. Exposing "Agent B concluded X" would anchor the re-investigating
agent on a claim rather than have it reason independently, defeating the
purpose of re-investigation.

## Consequences

- Boundary enforcement is testable and provable, not just asserted in
  documentation.
- The re-investigation reformulation logic is explicit orchestrator
  responsibility, not something left implicit for the agent prompt to
  handle.
