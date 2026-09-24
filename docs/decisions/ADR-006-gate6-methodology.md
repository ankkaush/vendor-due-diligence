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

## Gate 6 decision, executed 2026-09-24: NOT cleared as pre-registered

Real Phase 8 run: `eval/results/reconciliation_20260924T121800Z.json`,
full analysis in `eval/COST_LOG.md`'s "Phase 8 — real reconciliation
run, executed" section. Checked against the four criteria locked above,
in order:

| Criterion | Threshold | Measured | Result |
|---|---|---|---|
| `cross_domain_conflict` status accuracy | ≥ 66.7% | **100%** | **PASS** |
| Regression elsewhere (excl. cross_domain_conflict) | ≤ 5.0 pt | **-8.0 pt** (61.5%→53.5%) | **FAIL** |
| Cost per case vs. baseline | ≤ 2.5× | 1.60× ($0.012374 vs. $0.007731) | PASS |
| Latency per case vs. baseline | ≤ 3.0× | 1.56× (13.50s vs. 8.67s) | PASS |

Three of four criteria pass comfortably. The one that fails is not
close (8.0 pt against a 5.0 pt tolerance) and is not a rounding
artifact — it is explained by two distinct, identified mechanisms in
the reconciliation layer, not by noise:

1. **Semantic adjudication over-triggers.** It is instructed to catch
   conflicts "even where the connection is not obvious from matching
   wording" (by design, to compensate for the deterministic pass's
   under-recall — see the Phase 8 projection section above) and, on the
   real data, sometimes manufactures a "conflict" between claims that
   are merely thematically adjacent, not actually contradictory.
   Example: case-01 has exactly one planted issue, but semantic
   adjudication flagged two conflicts — the second invents an
   "operational interdependency" between a 24/7-monitoring claim and a
   30-day deletion commitment that is stated nowhere in the documents.
2. **`reconcile()`'s handling of a flagged semantic conflict is
   unconditional.** Every claim in any flagged conflict is force-set to
   `contradicted`, with no distinction for confidence or ambiguity — so
   a single over-triggered flag directly corrupts a previously-correct
   label rather than, e.g., degrading to "ambiguous" for human review.
   This is what turns over-triggering into a measured accuracy
   regression rather than a harmless false alarm.

A third, narrower issue was found in bounded re-investigation
specifically (not semantic adjudication): on case-07 — a version
conflict the ground truth deliberately designed to be *unresolvable*
from the documents alone (two DPA retention periods, no reconciling
changelog) — re-investigation incorrectly resolved it to `supported`
by reasoning that the later-dated document is authoritative, a
generic real-world heuristic the documents themselves never state.
The ground truth's own handling notes call this exact behavior out as
the wrong answer. This is a single-case, one-directional finding, not
a pattern across cases (case-16's re-investigation call, by contrast,
correctly recognized a deterministic-pass false positive and left both
claims `supported` — showing the mechanism works when the input
conflict is itself real).

**Decision: per the pre-registered "AND" structure of this ADR's
locked criteria, Gate 6 is judged NOT cleared.** This is stated
plainly rather than rounded up to a pass because the primary signal
looks strong — the literal, pre-registered bar required all of the
above, and one of them was missed by a real, explained margin, not a
trivial one.

**This is not read as a refutation of the core hypothesis.** The
criterion Gate 6 was specifically designed to test — does
reconciliation recover the `cross_domain_conflict` category that
domain-isolated investigators structurally cannot resolve alone — is
decisively answered yes (66.7%→100%, exactly the mechanism Phase 7
predicted). The failure is localized to two identified, specific
implementation defects in the reconciliation layer (semantic
adjudication's over-triggering + its unconditional status overwrite;
re-investigation's insufficient grounding-in-the-document constraint),
not a structural property of independent investigation plus
reconciliation as an architecture. Per this ADR's consequence clause,
the honest next decision is between: (a) simplify to single-agent +
deterministic reconciliation only, accepting the loss of the
cross-domain recovery this run demonstrated, or (b) attempt a targeted
fix to the two identified defects and re-run — which is a new,
separate cost-review-and-approval decision under ADR-009, not an
automatic continuation of this one. No further real API spend has been
authorized for a fix-and-rerun; this section records the diagnosis,
not a decision to proceed.
