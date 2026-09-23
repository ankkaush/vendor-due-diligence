# ADR-002: Explicit Python orchestration, not an agent framework

**Status:** Accepted
**Date:** 2026-09-23

## Context

LangGraph, CrewAI, and AutoGen would let us "put a framework on the
README," but the workflow here is a known, bounded DAG with one bounded
retry/re-investigation loop — not a case where an agent dynamically decides
the next step or the graph topology.

## Decision

Use an explicit Python state machine (Postgres-backed status enum +
transaction-guarded transitions) for orchestration. No LangGraph, CrewAI,
AutoGen, or Temporal in the MVP.

## Rationale

- The core technical thesis of this project is about **context isolation
  between agents** (ADR-007). A framework's abstractions would obscure
  exactly the mechanism being demonstrated and tested — explicit code makes
  state transitions, persistence, retries, idempotency, and boundary
  enforcement visible and directly testable.
- A framework earns adoption by solving a concrete problem plain code
  can't. No such problem has been identified for this workflow's shape.

## Consequences

- More orchestration code is written by hand than a framework would
  provide out of the box — accepted, because that code is the point.
- Revisit only if a concrete need for runtime-conditional branching emerges
  that can't be cleanly expressed as a static DAG. None is anticipated for
  the MVP scope.
