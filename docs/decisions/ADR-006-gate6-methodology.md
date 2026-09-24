# ADR-006: Gate 6 methodology — pre-registered threshold, injection excluded from the superiority test

**Status:** Accepted. Quality metrics locked 2026-09-23. Cost/latency
tolerance and the final quality bar locked 2026-09-24 — later than this
ADR originally committed to (before Phase 7 results, not after); see
"Process gap, recorded honestly" below for what happened and how the
threshold was still locked properly before the comparison it actually
protects (Phase 8).
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

## Process gap, recorded honestly (2026-09-24)

This ADR committed to appending the numeric cost/latency tolerance
**before** Phase 7 results were computed or reviewed. That didn't
happen — Phase 7's real investigator run was executed and its results
reviewed (`evaluation.md`, `eval/COST_LOG.md`) without a pre-registered
number to check it against. Recorded plainly rather than left
unacknowledged: the discipline this ADR was designed to enforce was not
followed for the Phase 6→7 comparison.

What limits the actual damage: Phase 7 was always scoped as a raw,
pre-reconciliation diagnostic step ("NOT yet: reconciliation logic
beyond raw comparison," architecture.md), not the final architecture
decision — so no Gate 6 pass/fail verdict was claimed on it, in
`evaluation.md` or anywhere else; what's there is a descriptive category
breakdown, not a threshold check. The real Gate 6 decision — is the
*reconciled* multi-agent architecture kept or simplified — is still
ahead, at Phase 8. The pre-registration discipline still has a real
comparison left to protect, and is applied properly below, before that
one.

**Locked now, before Phase 8 exists, using Phase 6 + Phase 7's actual
measured data:**

- **Cost tolerance: reconciled multi-agent total cost per case must not
  exceed 2.5× the baseline's per-case cost.** Derivation: baseline
  measured at $0.139160/18 = $0.00773/case; raw investigators alone
  (before reconciliation/re-investigation overhead) already measured at
  $0.170121/18 = $0.00945/case, i.e. 1.22×. 2.5× gives real headroom
  above that observed ratio for reconciliation's additional
  re-investigation calls (bounded to at most one round per conflict,
  decision #13) without being an arbitrary round number invented with no
  data behind it.
- **Latency tolerance: 3× baseline's per-case latency.** Wider than the
  cost multiplier because the eval harness runs both investigators
  sequentially (`eval/run_investigators.py`'s for-loop) — a real
  orchestrator could run them concurrently, but this harness doesn't
  measure that, so the recorded latency is a conservative
  (worse-than-necessary) upper bound, not a claim about the
  architecture's real wall-clock potential.
- **Quality bar, derived directly from the Phase 7 category breakdown
  (`eval/COST_LOG.md`'s "Phase 7 — real investigator run" section):**
  reconciliation must raise `cross_domain_conflict` status accuracy to
  at or above baseline's measured 66.7% on that category (case-08/14/18,
  6 claims) — the specific, structural gap raw investigators cannot
  close alone — **without** regressing the categories where investigators
  already reached parity-or-better (62.8% vs. baseline's 61.5%,
  excluding cross-domain conflict) by more than 5 percentage points.

If Phase 8 doesn't clear this, the architecture is simplified per this
ADR's original consequence — and the fact that this bar was set from
real Phase 6/7 data (even though later than originally planned) rather
than invented after seeing Phase 8's results is what keeps that outcome
honest.
