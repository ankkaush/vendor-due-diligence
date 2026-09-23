# ADR-006: Gate 6 methodology — pre-registered threshold, injection excluded from the superiority test

**Status:** Accepted (quality metrics and procedure locked now; numeric
cost/latency tolerance to be appended after Phase 6 baseline measurement,
before Phase 7 results are reviewed)
**Date:** 2026-09-23

## Context

Gate 6 decides whether the multi-agent architecture earns its complexity.
Two methodological risks needed to be closed off in advance: (1) locking an
arbitrary cost/latency multiplier before any real baseline data exists, and
(2) letting prompt-injection test results — which are largely a property of
the harness, not of multi-agent reasoning — count as evidence for the core
hypothesis.

## Decision

**Quality metrics (fixed now):** contradiction detection, unsupported-claim
detection, evidence grounding, ambiguous-evidence handling, domain-specific
omissions, cross-document verification errors — specifically, which of
these errors multi-agent catches that the single-agent baseline misses.

**Cost/latency tolerance (procedure fixed now, magnitude deferred):** after
Phase 6, the baseline's actual cost, latency, and retry/failure rate are
measured and recorded in `evaluation.md`. Only then is a specific tolerance
multiplier chosen and appended to this ADR, dated, **before** Phase 7/8
results are computed or reviewed. This is a pre-registration discipline —
the threshold is derived from real baseline data and locked before the
treatment data exists, preventing both an arbitrary a priori guess and
post-hoc goalpost-moving.

**Prompt-injection resistance is excluded from the Gate 6 quality
comparison.** Both architectures share the same structural mitigation (no
tools, no DB credentials, no approve/reject action available to either
agent type — ADR-003), so injection resistance is a security property of
the harness, not evidence about verification-reasoning quality. It is
tested as a mandatory, independent pass/fail requirement for both
architectures and reported separately in `evaluation.md` — a failure here
is disqualifying regardless of Gate 6's outcome, but a pass is not counted
toward multi-agent's case.

One nuance recorded, not discarded: domain-scoped investigators structurally
limit an injected instruction's blast radius (an instruction embedded in a
security document never reaches the privacy investigator's context at all).
This is a genuine consequence of domain scoping, but it is reported as a
labeled secondary observation, not folded into the Gate 6 pass/fail
decision.

## Consequences

- If multi-agent fails to clear the locked quality bar within the locked
  tolerance, the architecture is simplified to single-agent +
  deterministic reconciliation, and this is documented as the outcome —
  not treated as a project failure.
- The dated threshold-lock entry appended after Phase 6 is the artifact
  that makes this defensible as genuine measurement rather than
  post-hoc rationalization.
