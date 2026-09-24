# Evaluation

**Status: Phase 6, 7, and 8 complete with real executed runs. Gate 6 has
been checked against its pre-registered threshold and is judged NOT
cleared — see "Phase 8 reconciliation results" below and
[ADR-006](decisions/ADR-006-gate6-methodology.md)'s "Gate 6 decision,
executed 2026-09-24" section for the full criteria table and root-cause
analysis. $0.370 of $0.50 spent; no further real API spend is
authorized.** See "Phase 6 baseline results", "Phase 7 investigator
results", and "Phase 8 reconciliation results" below. Gate 6's final
numeric threshold was locked 2026-09-24 in
[ADR-006](decisions/ADR-006-gate6-methodology.md) — later than originally
planned (that ADR's own "Process gap, recorded honestly" section explains
what happened) — ahead of Phase 8, the comparison it actually protects.

Evaluation is designed before the pipeline, not after. See
[ADR-006](decisions/ADR-006-gate6-methodology.md) for the full Gate 6
procedure.

## Systems compared

1. **Deterministic baseline** — schema-level checks only. Establishes the
   floor.
2. **Strong single-agent baseline** — full evidence package in one context,
   asked for the same structured verification output. Must be genuinely
   strong, not a strawman — the burden of proof is on multi-agent to beat
   it.
3. **Independent multi-agent** — Security + Privacy/AI-Gov investigators
   under the boundaries in [`agent-boundaries.md`](agent-boundaries.md).

## Metrics

**Agent-level:** claim extraction precision/recall, evidence-grounding rate
(near-100% required — every claim in a finding must cite a real evidence
item), contradiction-detection recall/precision, unsupported-claim
detection rate, structured-output validity rate.

**System-level:** case-level correctness, missed-risk rate, human override
rate, escalation rate, latency, token usage, cost per case, retry rate.

**The central question, reported explicitly as a delta, not buried in
aggregate accuracy:** which verification errors does the independent
multi-agent architecture catch that the strong single-agent baseline
misses?

## Phase 6 baseline results (executed, not projected)

`app/agents/baseline.py` run against all 18 real cases via
`python -m eval.run_baseline`, approved per ADR-009's cost-review
discipline. Full breakdown in `eval/COST_LOG.md`; raw output in
`eval/results/baseline_20260924T080217Z.json`.

| Metric | Value |
|---|---|
| Structured output validity | 100% (18/18) |
| Overall claim recall | 86.5% |
| Status accuracy on matched claims | 59.8% |
| Contradiction recall | 62.5% |
| Missing-evidence recall | 100% |
| Injection detection rate | 100% (4/4 planted attempts) |
| Mean evidence grounding rate | 100% |
| Cost | $0.139160 (18 cases) |

**Structured-output enforcement (ADR-010) and injection resistance both
came back clean — 100% each.** Those aren't close calls: forced tool use
produced zero schema violations across 18 real calls, and every planted
injection attempt (direct, indirect, and the two that specifically
targeted the case's own planted conflicts) was flagged without changing
the affected claims' assessment.

**Status accuracy (59.8%) is the number that matters most for Gate 6,
and it was investigated case-by-case before being reported, not just
aggregated.** It is not a scoring artifact — the claim matches are
correct — it reflects two real, partly opposite baseline miscalibrations:

1. **Over-conservative on single-document self-attested technical
   claims.** A straightforward claim like "AES-256 encryption is used,"
   sourced from exactly one document with nothing to corroborate or
   contradict it, is repeatedly marked `unverified` instead of
   `supported` (case-11: both claims; case-14-c3; case-16-c3) — despite
   the system prompt explicitly stating self-attested claims without a
   contradicting signal count as supported. The rule isn't being applied
   consistently.
2. **Over-lenient on vague wording** — the opposite failure, on a
   similarly single-document claim: case-05-c1, the deliberately planted
   false-positive trap (vague retention language that should be
   `ambiguous`), was marked `supported` instead.
3. **Asymmetric contradiction handling** — case-07 (version conflict)
   and case-14-c2 (cross-domain conflict) each have two linked claims
   that should both be `contradicted`; the baseline caught the conflict
   from one document's side but scored the other document's claim as
   `supported`/`unverified` in isolation, missing that it's the same
   conflict.

None of these are edge cases outside what the dataset was built to
probe — they land squarely on `eval/CASES.md`'s deliberately planted
traps (case-05's ambiguous-vs-supported trap, case-07/14's paired-
conflict consistency, case-11/16's self-attestation rule). This is
exactly the kind of finding Gate 6 exists to surface, and it sets a
concrete, non-trivial bar: multi-agent doesn't need to be perfect to
clear it, but "does independent verification catch these specific
failure patterns" is now a real, falsifiable question with a measured
baseline to test against, not a hypothetical one.

## Phase 7 investigator results (executed, raw comparison — no reconciliation yet)

Both investigators run against all real 18 cases via
`python -m eval.run_investigators`, claims pooled with no reconciliation
(that's Phase 8). Full breakdown in `eval/COST_LOG.md`; raw output in
`eval/results/investigators_20260924T082006Z.json`.

| Metric | Baseline (Phase 6) | Investigators (Phase 7, raw) |
|---|---|---|
| Structured output validity | 100% | 100% |
| Overall claim recall | 86.5% | 94.2% |
| Status accuracy on matched claims | 59.8% | 52.3% |
| Contradiction recall | 62.5% | 75.0% |
| Injection detection rate | 100% | 100% |
| Cost | $0.139160 | $0.170121 |

**Read the 52.3% vs. 59.8% delta by category, not as one number — it
tells a completely different story than the aggregate suggests.**
`eval.scoring.breakdown_by_issue_type` (new this phase, unit-tested,
also usable as `python -m eval.compare_results`) breaks status accuracy
down by the ground truth's planted `issue_type`:

| Category | Baseline | Investigators | Δ | n |
|---|---|---|---|---|
| `cross_domain_conflict` | 66.7% | **0.0%** | −66.7% | 6 |
| `subtle_contradiction` | 66.7% | **100%** | +33.3% | 3 |
| `direct_contradiction` | 66.7% | **100%** | +33.3% | 4 |
| `ambiguous_wording` | 0.0% | 33.3% | +33.3% | 3 |
| `missing_evidence` | 100% | 100% | 0 | 4 |
| `version_conflict` | 50.0% | 50.0% | 0 | 3 |
| `misleading_wording` / `outdated_evidence` | 0.0% | 0.0% | 0 | 1, 2 |
| everything else (clean/untagged claims) | 65.2% | 61.5% | −3.7% | 26 |

**One category — `cross_domain_conflict` — accounts for almost the
entire aggregate gap, and it does so for a structural reason, not a
quality one.** Those 6 claims (case-08/14/18) are, by design, only
resolvable by comparing evidence from *both* domains at once — exactly
what Phase 8's reconciliation exists to do and Phase 7 explicitly
doesn't attempt. Checked directly against case-08's raw output: the
security investigator marked the EU-only residency claim `unverified` —
defensible from what it alone can see — and the privacy investigator
marked the India-based sub-processor disclosure `supported` — also
defensible in isolation, since nothing in its own context contradicts
it. Neither investigator is wrong given its restricted evidence; ground
truth expects `contradicted`, which requires both.

**Excluding that one structurally-expected category, the architectures
are close to parity, with investigators marginally ahead** (pooling
every individual claim globally, not averaging per-case): baseline
61.5% (24/39), investigators 62.8% (27/43) — and investigators show a
real edge specifically on `subtle_contradiction` and
`direct_contradiction` (100% vs. 66.7% each), though both are small
samples (n=3, n=4) and should be read as a promising signal, not a
settled result.

**What this means for Gate 6, concretely:** raw multi-agent output,
even before any reconciliation exists, is not "worse" in any way that
matters — it's already roughly at parity outside the one category it
was never supposed to solve alone. The real, falsifiable question for
Phase 8 is narrow and precise: does reconciliation recover
`cross_domain_conflict` specifically? ADR-006 (updated 2026-09-24, after
this run — see its "Process gap, recorded honestly" section for why that
timing isn't quite what was originally planned) locks the exact bar:
reconciliation must bring that category to ≥66.7% (baseline's number)
without regressing the already-at-parity categories by more than 5
points, within a 2.5× cost / 3× latency tolerance derived from this
run's real numbers.

## Phase 8 reconciliation results (executed, Gate 6 checked)

`app/reconcile.py` (deterministic conflict detection + semantic
adjudication) and `app/reinvestigate.py` (bounded, single-round,
same-agent re-investigation) run against all 18 cases via
`python -m eval.run_reconciliation`, reusing Phase 7's saved
investigator output. Full breakdown and root-cause analysis in
`eval/COST_LOG.md`'s "Phase 8 — real reconciliation run, executed"
section; raw output in
`eval/results/reconciliation_20260924T121800Z.json`.

| Category | Baseline | Reconciled | Δ | n |
|---|---|---|---|---|
| `cross_domain_conflict` | 66.7% | **100%** | **+33.3%** | 6 |
| `direct_contradiction` | 66.7% | 100% | +33.3% | 4 |
| `subtle_contradiction` | 66.7% | 100% | +33.3% | 3 |
| `misleading_wording` | 0.0% | 100% | +100% | 1 |
| `missing_evidence` | 100% | 75.0% | −25.0% | 4 |
| `none_clean` | 65.2% | 53.8% | −11.4% | 26 |
| `version_conflict` | 50.0% | 0.0% | −50.0% | 3 |
| `ambiguous_wording` / `outdated_evidence` | 0.0% | 0.0% / 0.0% | 0 | 3, 2 |

**Checked against ADR-006's four locked criteria:**

| Criterion | Threshold | Measured | Result |
|---|---|---|---|
| `cross_domain_conflict` accuracy | ≥ 66.7% | 100% | **PASS** |
| Regression elsewhere (excl. cross_domain_conflict, 61.5%→53.5%) | ≤ 5.0 pt | −8.0 pt | **FAIL** |
| Cost per case vs. baseline | ≤ 2.5× | 1.60× | PASS |
| Latency per case vs. baseline | ≤ 3.0× | 1.56× | PASS |

**Gate 6 is judged NOT cleared.** The primary, structural target this
gate was designed to test — does reconciliation recover
`cross_domain_conflict`, the category domain-isolated investigators
cannot resolve alone — is a decisive, clean win (66.7%→100%, exactly
the mechanism Phase 7 predicted). But the pre-registered criteria are
an AND, not a weighted score, and the secondary regression tolerance is
missed by a real margin (8.0 pt against 5.0 pt), so the gate as
literally written is not cleared.

**Root cause, traced to actual model output, not left as an aggregate
number:** two specific reconciliation-layer defects, not a property of
the independent-investigation architecture itself.

1. Semantic adjudication over-triggers — it sometimes flags a
   "conflict" between claims that are merely thematically adjacent
   (e.g., inventing an unstated dependency between a 24/7-monitoring
   claim and an unrelated 30-day-deletion commitment in case-01, which
   has only one actual planted issue).
2. `reconcile()` responds to any flagged conflict by unconditionally
   forcing every involved claim to `contradicted`, with no softer
   outcome for a low-confidence flag — turning each over-trigger
   directly into a wrong label. This combination is the most likely
   driver of the broad `none_clean` regression (26 claims, the largest
   category).

A third, narrower defect was found in bounded re-investigation:
case-07 is deliberately designed to be unresolvable from the documents
alone (two DPA versions, no reconciling changelog), but
re-investigation resolved it anyway using a generic "later document
wins" heuristic never stated in the documents — exactly the behavior
the case's ground truth notes call out as wrong. This is contrasted
with case-16, where re-investigation correctly recognized a
deterministic-pass false positive and left both claims unchanged,
showing the mechanism is not broken in general.

Full reasoning, including why this is read as two fixable
implementation defects rather than a refutation of the core hypothesis,
and what decision follows from here, is in
[ADR-006](decisions/ADR-006-gate6-methodology.md)'s "Gate 6 decision,
executed 2026-09-24" section.

## Gate 6 methodology (pre-registration)

**As designed:** lock the quantitative bar from Phase 6's real numbers
before the treatment (multi-agent) data exists, so the threshold can't be
shaped by already knowing the result.

**As actually executed:** step 2 below was supposed to happen before
Phase 7's results were reviewed — it didn't (ADR-006's "Process gap,
recorded honestly" section). Phase 7's raw investigator run was reviewed
without a pre-set numeric bar to check it against. What limits the
damage: Phase 7 was always a diagnostic step, not the final decision (no
pass/fail verdict was claimed on it — see "Phase 7 investigator results"
above, which reports a category breakdown, not a gate outcome), and the
real decision this discipline protects — Phase 8's reconciled-vs-baseline
comparison — still had its threshold locked properly, from real Phase 6
*and* Phase 7 data, before Phase 8 exists.

1. Phase 6 completes → baseline quality, cost, latency measured and
   recorded here. ✅ done.
2. ~~Before Phase 7 results are reviewed~~ → in practice, before **Phase
   8** results exist: [ADR-006](decisions/ADR-006-gate6-methodology.md)
   locks the quality-improvement bar and the cost/latency tolerance,
   derived from Phase 6 + Phase 7's actual measured numbers. ✅ done
   2026-09-24.
3. Phase 8 (reconciliation) runs against that locked bar.
4. If multi-agent doesn't clear it, the architecture is simplified and
   that result is documented honestly — a measured "it wasn't worth it,
   here's the data" is the correct outcome if that's what the evidence
   shows.

**Prompt-injection resistance is excluded from this comparison.** It is
tested as a mandatory, independent security pass/fail for both
architectures (see [`threat-model.md`](threat-model.md)) and reported
separately — it is a security property of the harness (neither
investigator agent has any privileged action to hijack), not evidence about
verification-reasoning quality.

## Ground-truth dataset

**Status: Phase 3 complete. All 18 cases built and validated; see
`eval/CASES.md` for the full plan, coverage check, and build status.**

18 synthetic vendor evidence packages (3–5 documents each), each with an
explicit ground-truth label file covering: supported claims, unsupported
claims, direct contradictions, subtle contradictions, missing evidence,
ambiguous wording, outdated/conflicting document versions, cross-domain
inconsistencies, misleading wording, prompt-injection attempts, and
incomplete packages. Each ground-truth claim is tagged with `issue_type` and
`is_planted_issue` (ADR-008) so results can be broken down by failure-mode
category, not just aggregated — the interesting finding is likely to be
"multi-agent wins on category X, not on category Y," which an aggregate
number would hide.

Dataset construction (Phase 3a: ontology, Phase 3b: case construction) is
completed **before** the single-agent baseline is implemented (Phase 6).

### Ontology (Phase 3a)

The ground-truth schema is formalized at
[`eval/schema/ground_truth.schema.json`](../eval/schema/ground_truth.schema.json)
(JSON Schema 2020-12) and reuses the production `Claim`/`EvidenceItem` field
shape from `data-model.md`, plus eval-only fields per ADR-008: `issue_type`,
`is_planted_issue`, `expected_handling_notes`. No numeric
`expected_confidence` field — `expected_verification_status` (including
`ambiguous`) is the sole graded label.

Each case file also carries a `document_manifest`, an `expected_conflicts`
array (linking ≥2 claim IDs with a `conflict_type`, for scoring
contradiction-detection directly rather than inferring it from individual
claim statuses), and an `injection_attempts` array (structurally separate
from `claims`, since a planted injection isn't a vendor assertion to verify
— it's an adversarial artifact with its own `expected_behavior`).

[`eval/validate_ground_truth.py`](../eval/validate_ground_truth.py) checks
every case file against the schema and additionally verifies referential
integrity — every `source_document_id`, `evidence_item.document_id`,
`expected_conflicts[].claim_ids`, and `injection_attempts[].document_id`
must resolve to an id actually declared in that same case file. Both the
schema check and the referential check were deliberately exercised against
broken input (an invalid enum value, and a dangling document reference) to
confirm they actually fail before being trusted to pass — the same
discipline as the Phase 1 gitleaks test.

Run it with:

```bash
pip install -e ".[eval]"
python eval/validate_ground_truth.py
```

### Case plan (Phase 3b)

See [`eval/CASES.md`](../eval/CASES.md) for the full 18-case matrix and
the coverage check against every required failure-mode category. All 18
cases are built, pass schema/referential validation, and — as of Phase 6
— have now been run through both real parsing/classification
(`tests/test_app/test_eval_case_routing.py`) and a real model
(`eval/run_baseline.py`).

## Cost ceiling

**Hard constraint: $0.50 total Anthropic API spend for the entire project,
never exceeded (ADR-009).** This supersedes the earlier, looser framing of
decision #11 with a specific number and an explicit spend discipline:

- All development, unit, and integration testing uses a mocked LLM client
  — zero real API calls before a deliberate evaluation checkpoint.
- The first real call is one tiny one-case smoke test, run only after its
  expected cost is reviewed and approved (see `eval/COST_LOG.md`).
- Model selection is decided at that point from measured real cost and
  then-current pricing, not assumed in advance (ADR-009) — the constraint
  is the $0.50 total, not a standing preference for the cheapest model.
- Each real evaluation pass (baseline, then multi-agent) runs once, after
  full validation against mocks.
- Actual spend is tracked in `eval/COST_LOG.md` from the first real call
  onward, not just checked against a ceiling after the fact.

**Actual spend so far (measured, not projected):** $0.008130 (two
calibration calls) + $0.139160 (the real Phase 6 baseline run, all 18
cases) = **$0.147290 spent, $0.352710 of $0.50 remaining.** Full
per-case breakdown in `eval/COST_LOG.md`.

**What's still a projection:** Phase 7's investigator and
re-investigation calls. The earlier toy-prompt-based estimate (~$0.148
for a full baseline+multi-agent comparison pass) is now known to have
understated the baseline's real cost by roughly 25–40% once the real
prompt and forced-tool-use overhead were measured — the same correction
should be expected for investigator-call estimates once Phase 7's real
prompts exist, and that projection should be recalibrated the same way
(measure the real prompt, don't re-guess) before committing to the full
Gate 6 run.
