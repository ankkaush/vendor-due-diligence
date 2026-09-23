# ADR-009: $0.50 total API budget — spend discipline, model choice deferred to measurement

**Status:** Accepted
**Date:** 2026-09-23

## Context

Cost management was already planned (decision #11: set the cost ceiling
after Phase 6 baseline measurement; ADR-006: lock the Gate 6 cost/latency
tolerance from real baseline data). The project owner has now set a harder,
more specific constraint: **$0.50 is the absolute total Anthropic API
budget for the entire project, never to be exceeded** — not a per-case
estimate, the entire remaining spend.

## Decision

**Spend discipline:**

1. Development, unit tests, and integration tests use a mocked/fake LLM
   client exclusively. Zero real API calls during iteration or debugging
   (Phases 5–9).
2. Real Anthropic API calls happen only at deliberate, pre-announced
   evaluation checkpoints — never incidentally.
3. The first real call ever made is a single, tiny, one-case smoke test —
   and it does not happen until its expected cost has been presented to
   and reviewed by the project owner.
4. The smoke test's actual measured token usage and cost calibrate every
   subsequent estimate — no further real spend is committed on the basis
   of a guess once real numbers exist.
5. Remaining budget is allocated explicitly across the checkpoints that
   still need it (smoke test → baseline run → multi-agent run), tracked as
   a running ledger (`eval/COST_LOG.md`), not just monitored against a
   ceiling after the fact.
6. Each real evaluation pass (baseline, multi-agent) runs once, after full
   validation against mocks — no repeated or exploratory real runs.
7. If a planned step risks exceeding the $0.50 total, execution stops and
   the project owner is asked before any further real call is made.

**Model selection is explicitly not pinned now.** The hard constraint is
the $0.50 total, not "use the cheapest model" as a standing assumption.
Which model is used is decided at the time of the smoke test, based on
then-current published pricing and the smoke test's measured token usage —
because pricing and model availability can both change between this ADR
and implementation. In practice this will likely still mean the cheapest
suitable tier, since illustrative token-size estimates from the built
exemplar cases put one full baseline+multi-agent comparison pass at
roughly $0.05–$0.10 on a cheap tier versus roughly $0.60–$0.70 on a
flagship tier — i.e. a flagship-tier model would exceed the entire budget
on a single pass before any debugging iteration. That arithmetic, not a
prior preference for "cheap," is what will most likely drive the choice —
but it is confirmed empirically, not assumed in advance.

**The single-agent baseline is not described as "weak" because of this
constraint.** Its strength is about architecture: prompt design, context
construction, evidence-grounding rigor, structured-output discipline, and
evaluation methodology (Gate 6's actual comparison criteria, ADR-006) — not
about using the most expensive model available. The model/budget
constraint is documented as an explicit, disclosed project limitation (see
`limitations.md`), separate from and not a caveat on the baseline's
architectural rigor. Gate 6's question is genuinely still meaningful under
this framing: *does independent multi-agent verification add measurable
value on top of a well-engineered single-agent baseline, given a fixed,
shared, budget-constrained model* — arguably a more realistic real-world
question than "value at unlimited budget" would have been anyway.

## Consequences

- A smoke-test plan (case used, expected token count, expected cost, model
  candidate(s), and current pricing source) is presented for explicit
  review before the first real API call — no real call happens without
  that review, per the project owner's instruction.
- `eval/COST_LOG.md` is the running ledger of actual spend, starting from
  $0.00, updated after every real call from here forward.
- If the smoke test's measured cost makes the full evaluation infeasible
  within $0.50 even on the cheapest tier, the fallback is reducing
  evaluation scope (e.g. fewer cases, or baseline-only) — the $0.50 ceiling
  is not negotiable, evaluation scope is.
