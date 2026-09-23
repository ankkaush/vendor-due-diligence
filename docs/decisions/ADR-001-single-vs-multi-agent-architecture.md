# ADR-001: Multi-agent architecture is a tested hypothesis, not an assumption

**Status:** Accepted
**Date:** 2026-09-23

## Context

Track B Project 6 exists to demonstrate genuine multi-agent engineering
judgment, not to showcase agents for their own sake. The risk is building a
multi-agent system because the project was scoped as one, regardless of
whether it's actually justified by the problem.

## Decision

The MVP uses exactly two independent domain investigators — Security, and
Privacy/AI-Governance — the smallest architecture that can meaningfully test
whether independent, domain-scoped reasoning catches verification errors a
strong single-agent baseline misses. No additional investigators are added
before Gate 6 resolves. The single-agent baseline is built and measured
first (Phase 6), before the multi-agent system (Phase 7), so the comparison
has a genuine floor to beat rather than a strawman.

## Consequences

- If Gate 6 shows no meaningful advantage within the pre-registered
  cost/latency tolerance (ADR-006), the architecture is simplified to
  single-agent + deterministic reconciliation, and this is documented as a
  legitimate finding, not hidden.
- Portfolio value comes from the measurement and the judgment shown, not
  from the multi-agent label surviving regardless of evidence.
