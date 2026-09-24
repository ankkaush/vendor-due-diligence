# API Cost Ledger

**Hard ceiling: $0.50 total, for the entire project, never exceeded (ADR-009).**
This file is updated after every real Anthropic API call — no exceptions,
no batching updates "for later."

| Date | Purpose | Model | Input tokens | Output tokens | Cost (USD) | Running total | Remaining |
|---|---|---|---|---|---|---|---|
| 2026-09-23 | Smoke test attempt #1 (case-11) — **failed before inference**, HTTP 400: API key not scoped to a workspace. No tokens processed. | claude-haiku-4-5-20251001 | 0 | 0 | $0.00 | $0.00 | $0.50 |
| 2026-09-23 | Smoke test attempt #2 (case-11) — **succeeded**, new workspace-scoped key. | claude-haiku-4-5-20251001 | 455 | 356 | $0.002235 | $0.002235 | $0.497765 |
| 2026-09-23 | Calibration #2 (case-01, 3 docs) — **succeeded**. | claude-haiku-4-5-20251001 | 1085 | 962 | $0.005895 | $0.008130 | $0.491870 |

### Findings from the successful smoke test

- **Estimate held up well.** Predicted ~487 input tokens from a char/4
  approximation; actual was 455 — close enough to trust the same
  approximation for a rough full-run projection, pending a second data
  point from a larger case.
- **Claim granularity varies between runs, as expected.** Ground truth
  for case-11 defines 2 claims; the model returned 3, splitting the
  training-use statement into two related-but-distinct claims. Not
  wrong — a real, concrete illustration of exactly the "independent
  extraction produces different claim boundaries" effect ADR-004 was
  designed around, not something to force into a stricter grading
  scheme.
- **Injection handling: correct on this one sample.** `injection_detected: true`,
  and the note explicitly states the reviewer-note text does not override
  verification and that the substantive claims were assessed independently
  of it — the behavior case-11's ground truth specifies. One sample is a
  good sign, not a security test suite; the real, adversarial version of
  this check is Phase 10's full injection test suite.
- **Real engineering finding for Phase 6/7 design:** the raw response was
  wrapped in a ```` ```json ... ``` ```` markdown fence despite the prompt
  saying "respond with ONLY valid JSON," which broke naive `json.loads`.
  Asking nicely in the system prompt is not enough — the real baseline
  and investigator implementations need actual structured-output
  enforcement (Anthropic tool-use / forced JSON schema, or defensive
  fence-stripping before parsing), not prompt instruction alone. This is
  exactly why "structured-output validity rate" is already a Phase 6
  evaluation metric (`evaluation.md`) — this smoke test is the first
  concrete evidence of why that metric earns its place.

### Findings from calibration #2 (case-01)

- **Input scaling confirmed and fit precisely.** With two real points
  (case-11: 730 chars → 455 tokens; case-01: 3,210 chars incl. document
  tags → 1,085 tokens), a linear model `input_tokens ≈ 270 + 0.254 × chars`
  fits both exactly (2 points, 2 unknowns — this is a minimal fit, not
  independent confirmation of linearity, but it's the best available
  until a third, differently-sized data point exists).
- **Claim extraction ran hotter than ground truth assumes.** Case-01's
  ground truth defines 6 claims; the model returned 9, because it treated
  the SOC report's and DPA's own statements as claims in their own right
  (e.g. "SOC audit period dates," "sub-processor obligations"), not just
  cross-references supporting the questionnaire's claims. This is a
  second real instance of the extraction-granularity variance already
  seen in case-11, now shown to inflate output token count too — the
  output/input ratio (0.78 for case-11, 0.89 for case-01, averaging
  ~0.83) already reflects this in the projection below, but the
  underlying ontology mismatch (are a SOC report's own statements
  "claims" or "evidence for the vendor's claims"?) is a real Phase 6
  prompt-design question, not just a cost question — worth deciding
  deliberately rather than letting it fall out of whatever the model
  happens to do.
- **Structured-output fencing recurred.** Same markdown-fence wrapping as
  case-11, on a different, larger prompt. Confirms this is a systematic
  model behavior, not a one-off fluke — reinforces ADR-010.
- **No false-positive injection flag.** Case-01 has no planted injection;
  `injection_detected: false` was correct.

### Revised full-run projection (calibrated, not guessed)

Using the fitted input model and measured output/input ratio (~0.83)
against the actual document sizes of all 18 built cases, with the same
60%-of-case-size assumption for domain-scoped investigator calls as
before (still unverified — no real investigator-shaped call has been
made) and the original rough estimate retained for the 7 re-investigation
calls (also unmeasured):

| Component | Calls | Input tok | Output tok | Cost |
|---|---|---|---|---|
| Baseline (1/case × 18) | 18 | ~10,300 | ~8,600 | ~$0.053 |
| Investigators (2/case × 18) | 36 | ~16,250 | ~13,560 | ~$0.084 |
| Re-investigation (unmeasured estimate) | 7 | ~3,500 | ~1,400 | ~$0.011 |
| **Total, one full comparison pass** | **61** | | | **~$0.148** |

**This revises the earlier $0.23 guess down to ~$0.15** — the original
per-call size assumptions overestimated input tokens more than they
underestimated output tokens. After both calibration calls
($0.008130 spent), a ~$0.148 full run would leave **~$0.344 of the $0.50
budget remaining**.

Two things this projection still doesn't cover, flagged rather than
hidden: no investigator-shaped call (domain-subset input) or
re-investigation-shaped call has actually been measured — both legs are
still extrapolated, not calibrated. If either turns out meaningfully
different from these assumptions once Phase 7 exists, this projection
should be revisited before running the full 61-call evaluation for real.

## Phase 6 — real baseline run projection (pending review, not yet executed)

The earlier ~$0.148 full-comparison-pass projection above used the toy
smoke-test prompt's size. The actual Phase 6 baseline agent
(`app/agents/baseline.py`) has a real, considerably larger system prompt
(rubric definitions, grounding requirements, injection-handling
instructions) plus forced-tool-use overhead, so that projection is
**superseded for the baseline portion** by the measurement below, taken
directly from the real prompt and real tool schema against all 18 cases'
actual document sizes — not re-estimated from scratch.

| Component | Measured value |
|---|---|
| System prompt | 3,553 chars → 888 tokens |
| Tool schema (`FINDINGS_INPUT_SCHEMA`) | 1,382 chars → 346 tokens |
| Anthropic's forced-tool-choice overhead (Haiku 4.5, documented) | 588 tokens |
| Total user-message chars, all 18 cases (real documents) | 24,271 chars |
| Ground-truth claim count, all 18 cases | 52 |

Applying the same input-token linear fit as before (now including the
888 + 346 + 588 fixed overhead per call) and an output estimate scaled
from the case-01/case-11 finding that real extraction runs ~1.5× the
ground-truth claim count at ~180 tokens/claim (the real schema is richer
than the smoke test's toy one — 11 required fields per claim, not 3):

| Scenario | Input tok | Output tok | Cost |
|---|---|---|---|
| Expected (1.5× claims, 180 tok/claim) | 38,862 | ~14,580 | **~$0.112** |
| Conservative bound (2× claims, 220 tok/claim) | 38,862 | ~23,420 | **~$0.156** |

## Phase 6 — real baseline run, executed 2026-09-24

Approved and run: `python -m eval.run_baseline --i-have-reviewed-the-cost-estimate`.
All 18 cases completed, zero structured-output failures.

| Case | Input tok | Output tok | Cost |
|---|---|---|---|
| case-01 | 2,567 | 2,204 | $0.013587 |
| case-02 | 2,320 | 1,654 | $0.010590 |
| case-03 | 2,185 | 1,068 | $0.007525 |
| case-04 | 2,040 | 902 | $0.006550 |
| case-05 | 1,989 | 723 | $0.005604 |
| case-06 | 2,095 | 959 | $0.006890 |
| case-07 | 1,991 | 675 | $0.005366 |
| case-08 | 2,058 | 1,077 | $0.007443 |
| case-09 | 2,042 | 1,057 | $0.007327 |
| case-10 | 2,228 | 896 | $0.006708 |
| case-11 | 1,982 | 678 | $0.005372 |
| case-12 | 2,125 | 640 | $0.005325 |
| case-13 | 2,009 | 782 | $0.005919 |
| case-14 | 2,117 | 1,651 | $0.010372 |
| case-15 | 2,122 | 744 | $0.005842 |
| case-16 | 2,044 | 1,019 | $0.007139 |
| case-17 | 2,266 | 1,257 | $0.008551 |
| case-18 | 2,340 | 2,142 | $0.013050 |
| **Total** | **38,520** | **20,128** | **$0.139160** |

**Estimate check:** input landed almost exactly on the projection (38,520
actual vs. 38,862 projected — the linear fit held up well beyond the two
original calibration points). Output landed between the expected and
conservative scenarios (20,128 vs. 14,580 expected / 23,420 conservative)
— real per-claim output ran a bit richer than the 180 tok/claim estimate,
consistent with the model tending to write fuller rationale text than
the smoke-test calibration samples suggested.

**Cumulative spend: $0.008130 (calibration) + $0.139160 (this run) =
$0.147290 of $0.50. Remaining: $0.352710.**

### Aggregate results

| Metric | Value |
|---|---|
| Structured output validity | 100% (18/18) |
| Overall claim recall | 86.5% |
| Status accuracy on matched claims | 59.8% |
| Contradiction recall | 62.5% |
| Missing-evidence recall | 100% |
| Injection detection rate | 100% (4/4 planted attempts) |
| Mean evidence grounding rate | 100% |

Full raw output: `eval/results/baseline_20260924T080217Z.json`.

### What the 59.8% status accuracy actually is — investigated, not just reported

This is the headline number for the whole project's thesis, so it was
worth reading the actual predicted-vs-ground-truth claims before writing
it up, not just trusting the aggregate. It is **not** a scoring bug —
the claim matches are correct — it's two real, somewhat opposite
baseline miscalibrations:

1. **Over-conservative on single-document self-attested technical
   claims.** case-11 (both claims 0% correct), case-14-c3, and
   case-16-c3 all mark a straightforward claim like "AES-256 encryption
   is used" — sourced from exactly one document, nothing to
   corroborate or contradict — as `unverified` instead of `supported`,
   despite the system prompt explicitly stating self-attested claims
   without a contradicting signal count as supported. The model isn't
   consistently applying that rule.
2. **Over-lenient on vague wording.** case-05-c1 — the deliberate
   false-positive trap (vague retention language that should be
   `ambiguous`) — was marked `supported` instead. The opposite failure
   mode from #1, on a similarly single-document claim.
3. **Asymmetric contradiction handling.** case-07 (version conflict)
   and case-14-c2 (cross-domain conflict) each have two linked claims
   that should both be `contradicted`; the baseline caught the
   contradiction from one document's side but scored the other
   document's claim as `supported`/`unverified` in isolation, missing
   that it's the *same* conflict.

None of these are hypothetical edge cases — they're exactly the
deliberately-planted traps in `eval/CASES.md`'s design (case-05's
ambiguous-vs-contradiction trap, case-07/14's paired-conflict
consistency, case-11/16's self-attestation rule). The baseline is
applying surface pattern-matching more than the precise rubric in
several places, not failing randomly.

After the $0.008130 already spent: **expected cumulative ~$0.120,
worst-case bound ~$0.164 — leaving $0.336–$0.380 of the $0.50 budget**
for Phase 7's investigators and any re-investigation calls once those
exist. `eval/run_baseline.py` is built, tested against `FakeLLMClient`
(zero real calls — `tests/test_agents/test_baseline.py`, 11 tests), and
enforces the same $0.50 hard stop live: cumulative spend is checked
before every case, not just projected in advance, and execution halts
before any call that would exceed it.

**Status: executed and reviewed** — see "Phase 6 — real baseline run"
above for actual results.

## Phase 7 — investigator run projection (pending review, not yet executed)

`app/agents/investigator.py` and `app/agents/context_builder.py` are
built and unit-tested against `FakeLLMClient` (30 tests,
`tests/test_agents/`). `eval/run_investigators.py` runs both
investigators against all 18 real cases, pools their claims (raw
comparison, no reconciliation — Phase 8), and scores against the same
ground truth `eval/run_baseline.py` used.

**A real finding from sizing this before spending anything:** measuring
the actual `build_context()` output against all 18 cases showed 9 of the
36 case/investigator pairs have zero documents in that domain (e.g.
case-03 has no privacy documents at all). `run_investigator` now skips
the API call entirely in that case rather than sending an empty evidence
package — see `docs/agent-boundaries.md` and
`tests/test_agents/test_investigator.py::test_empty_domain_skips_the_api_call_entirely`.
This means the real run is **27 calls, not 36** — the projection below
already reflects that.

| Component | Measured value |
|---|---|
| Security investigator system prompt | 1,043 tokens |
| Privacy investigator system prompt | 1,037 tokens |
| Tool schema + forced-tool-choice overhead (unchanged from Phase 6) | 346 + 588 tokens |
| Actual calls that will be made (of 36 possible) | 27 |
| Total user-message chars, all non-empty calls | 25,026 (15,304 security + 9,722 privacy) |

| Scenario | Input tok | Output tok | Cost |
|---|---|---|---|
| Expected (1.5× relevant claims, 180 tok/claim) | 59,557 | ~14,850 | **~$0.134** |
| Conservative bound (2× claims, 220 tok/claim) | 59,557 | ~17,800* | **~$0.178** |

\* conservative-bound output recomputed at the higher per-claim rate;
see the calculation this table is drawn from for the exact per-case
breakdown.

After the $0.147290 already spent (calibration + Phase 6 baseline):
**expected cumulative ~$0.281, worst case ~$0.325 — leaving $0.175–$0.219
of the $0.50 budget** for Phase 8's reconciliation/re-investigation calls,
once those exist.

**Status: executed and reviewed** — see "Phase 7 — real investigator run"
below for actual results.

## Phase 7 — real investigator run, executed 2026-09-24

Approved and run: `python -m eval.run_investigators --i-have-reviewed-the-cost-estimate`.
All 18 cases, both investigators each, zero structured-output failures.
27 of 36 possible calls actually made (9 skipped — empty domain, no
API cost).

| Case | Input tok | Output tok | Cost |
|---|---|---|---|
| case-01 | 4,619 | 2,500 | $0.017119 |
| case-02 | 4,372 | 1,480 | $0.011772 |
| case-03 | 2,316 | 1,125 | $0.007941 |
| case-04 | 4,092 | 1,137 | $0.009777 |
| case-05 | 2,121 | 784 | $0.006041 |
| case-06 | 2,226 | 883 | $0.006641 |
| case-07 | 2,123 | 771 | $0.005978 |
| case-08 | 4,110 | 1,105 | $0.009635 |
| case-09 | 2,173 | 867 | $0.006508 |
| case-10 | 2,359 | 1,134 | $0.008029 |
| case-11 | 2,114 | 672 | $0.005474 |
| case-12 | 4,367 | 964 | $0.009187 |
| case-13 | 2,141 | 850 | $0.006391 |
| case-14 | 4,169 | 1,580 | $0.012069 |
| case-15 | 2,253 | 1,495 | $0.009728 |
| case-16 | 4,096 | 1,271 | $0.010451 |
| case-17 | 4,318 | 1,775 | $0.013193 |
| case-18 | 4,392 | 1,959 | $0.014187 |
| **Total** | **58,361** | **22,352** | **$0.170121** |

**Estimate check:** input landed slightly under the projection (58,361
actual vs. 59,557 projected). Output ran higher than even the
conservative scenario (22,352 vs. ~17,800) — richer per-claim rationale
again, same pattern as Phase 6. Total cost landed almost exactly on the
conservative bound ($0.170 vs. $0.178 projected).

**Cumulative spend: $0.147290 (through Phase 6) + $0.170121 (this run) =
$0.317411 of $0.50. Remaining: $0.182589.**

### Aggregate results (raw pooled investigator claims, no reconciliation)

| Metric | Baseline (Phase 6) | Investigators (Phase 7) |
|---|---|---|
| Structured output validity | 100% | 100% |
| Overall claim recall | 86.5% | 94.2% |
| Status accuracy on matched claims (macro, per-case mean) | 59.8% | 52.3% |
| Contradiction recall | 62.5% | 75.0% |
| Missing-evidence recall | 100% | 100% |
| Injection detection rate | 100% | 100% |
| Mean evidence grounding rate | 100% | 100% |
| Cost | $0.139160 | $0.170121 |

Full raw output: `eval/results/investigators_20260924T082006Z.json`.

### The aggregate status-accuracy drop, investigated by category — not just reported

Read at face value, 52.3% vs. 59.8% looks like multi-agent is worse. It
isn't that simple, and the category breakdown
(`eval/compare_results.py`, `eval.scoring.breakdown_by_issue_type` — new
this run, unit-tested in `tests/test_eval/test_scoring.py`) shows why:

```
category                     baseline acc investigators acc    delta  total
ambiguous_wording                    0.0%            33.3%   +33.3%  3
cross_domain_conflict               66.7%             0.0%   -66.7%  6
direct_contradiction                66.7%           100.0%   +33.3%  4
misleading_wording                   0.0%             0.0%    +0.0%  1
missing_evidence                   100.0%           100.0%    +0.0%  4
none_clean                          65.2%            61.5%    -3.7%  26
outdated_evidence                    0.0%             0.0%    +0.0%  2
subtle_contradiction                66.7%           100.0%   +33.3%  3
version_conflict                    50.0%            50.0%    +0.0%  3
```

**One category — `cross_domain_conflict` — explains almost the entire
aggregate gap, and it does so for a structural reason, not a quality
one.** These 6 claims (case-08, case-14, case-18) are, by the design of
those cases, only resolvable by comparing evidence from *both* domains —
that is exactly what reconciliation (Phase 8, not built yet) exists to
do. A domain-scoped investigator, working alone as Phase 7 requires
(ADR-007), structurally cannot produce "contradicted" for a claim whose
contradicting evidence lives in a document it never receives. Checked
directly (`case-08`): the security investigator marked the EU-only
residency claim `unverified` — a defensible answer from what it can
see — and the privacy investigator marked the India-based sub-processor
disclosure `supported` — also defensible in isolation, since nothing in
its own context contradicts it. Neither is wrong given what it had;
ground truth expects `contradicted`, which requires both.

**Excluding that one structurally-expected category, the two
architectures are close to parity, with investigators very slightly
ahead** (global/micro-averaged, pooling every individual claim rather
than averaging per-case): baseline 61.5% (24/39 correct), investigators
62.8% (27/43 correct). Within that, investigators show a real,
consistent edge specifically on **subtle_contradiction (100% vs. 66.7%)**
and **direct_contradiction (100% vs. 66.7%)** — though both categories
have small sample sizes (n=3, n=4) and should be read as a promising
signal, not a settled result. `missing_evidence` is tied at a perfect
100% for both. `misleading_wording` and `outdated_evidence` are tied at
0% for both (n=1, n=2 — a single case each; not enough data to
distinguish "both architectures share the same weakness" from "these
categories are just hard to test with one case").

**What this sets up for Phase 8, precisely and falsifiably:** does
reconciliation recover the `cross_domain_conflict` category specifically?
If comparing the two investigators' pooled output (case-08/14/18) lets a
deterministic reconciliation step correctly flag those 6 claims as
conflicting — something neither investigator could do alone — that is
concrete evidence of exactly the value multi-agent decomposition is
supposed to provide, measurable against a number that already exists
(baseline's 66.7% on this same category). If it doesn't recover them,
that's meaningful too, per Gate 6 / ADR-006's commitment to accept
either outcome honestly.

## Phase 8 — reconciliation run projection (pending review, not yet executed)

`app/reconcile.py` (deterministic conflict detection + semantic
adjudication) and `app/reinvestigate.py` (bounded, single-round,
same-agent re-investigation) are built and unit-tested against
`FakeLLMClient` (17 tests, `tests/test_app/test_reconcile.py` +
`tests/test_app/test_reinvestigate.py`). `eval/run_reconciliation.py`
reuses the ALREADY-SAVED Phase 7 investigator output
(`eval/results/investigators_20260924T082006Z.json`) instead of
re-running the investigators — no new spend for that half, only for
reconciliation's own calls.

**Running the real deterministic pass against the real saved Phase 7
output (no API cost, pure function) before projecting anything found a
genuine, useful fact**: it catches only 2 of the ~6 expected conflicts
(case-07, case-16) — fewer than hoped, because the investigators'
`subject` field isn't always topically descriptive enough for
jaccard-similarity matching to recognize two claims as "the same topic."
This isn't a bug to fix before running — it's exactly why the
architecture has a semantic-adjudication fallback in the first place:
every claim the deterministic pass doesn't confidently pair off flows
into the semantic call instead, which is explicitly instructed to catch
conflicts "even where the connection is not obvious from matching
wording." Measuring this first, before estimating cost, changed the
projection meaningfully (17 semantic calls instead of a hoped-for
handful, but each smaller since real per-case pooled-claim counts are
now known exactly, not guessed).

| Component | Measured / derived value |
|---|---|
| Deterministic conflicts found (free, no API call) | 2 (case-07, case-16) |
| Cases requiring a semantic-adjudication call | 17 of 18 (case-07 has nothing left over) |
| Semantic adjudication system prompt | 334 tokens |
| Re-investigation calls needed | 2 (one per deterministic conflict) |

| Scenario | Input tok (est) | Output tok (est) | Cost |
|---|---|---|---|
| Semantic adjudication (17 calls) | ~30,146 | ~5,610 | — |
| Re-investigation (2 calls) | ~2,196 | ~300 | — |
| **Total** | **~32,342** | **~5,910** | **~$0.062** |

After the $0.317411 already spent: **expected cumulative ~$0.379,
leaving ~$0.121 of the $0.50 budget** — comfortable margin, and this is
the last real spend expected before Phase 9 (human review UI, no API
calls).

**Not yet run.** Per ADR-009, this needs explicit review and approval
before executing:

```bash
python -m eval.run_reconciliation --i-have-reviewed-the-cost-estimate \
    --investigator-results eval/results/investigators_20260924T082006Z.json
```

## Phase 8 — real reconciliation run, executed 2026-09-24

Approved and run:
```bash
python -m eval.run_reconciliation --i-have-reviewed-the-cost-estimate \
    --investigator-results eval/results/investigators_20260924T082006Z.json
```
All 18 cases, 100% structured-output validity across all semantic-
adjudication and re-investigation calls. Reused Phase 7's saved
investigator output — no investigator API calls were re-made.

| Metric | Value |
|---|---|
| Total new cost (this run only) | **$0.052607** |
| Total input / output tokens | 29,712 / 4,579 |
| Deterministic conflicts found | 2 (case-07, case-16) |
| Semantic adjudication calls made | 17 (case-07 had nothing left over) |
| Re-investigation calls made | 2 |
| Mean latency (incremental, this run only) | 3.166s/case |

**Estimate check:** landed under projection ($0.052607 vs. ~$0.062
projected) — fewer semantic conflicts were actually flagged by the
model than the token-count estimate assumed.

**Cumulative spend: $0.317411 (through Phase 7) + $0.052607 (this run)
= $0.370018 of $0.50. Remaining: $0.129982.**

Full raw output: `eval/results/reconciliation_20260924T121800Z.json`.

### Gate 6 result, checked against the criteria locked in ADR-006

```
category                     baseline acc   reconciled acc    delta  total
ambiguous_wording                    0.0%             0.0%    +0.0%  3
cross_domain_conflict               66.7%           100.0%   +33.3%  6
direct_contradiction                66.7%           100.0%   +33.3%  4
misleading_wording                   0.0%           100.0%  +100.0%  1
missing_evidence                   100.0%            75.0%   -25.0%  4
none_clean                          65.2%            53.8%   -11.4%  26
outdated_evidence                    0.0%             0.0%    +0.0%  2
subtle_contradiction                66.7%           100.0%   +33.3%  3
version_conflict                    50.0%             0.0%   -50.0%  3
[excl. cross_domain_conflict] baseline: acc=61.5% (24/39)
[excl. cross_domain_conflict] reconciled: acc=53.5% (23/43)
```

| Criterion | Threshold | Measured | Result |
|---|---|---|---|
| `cross_domain_conflict` status accuracy | ≥ 66.7% | 100% | **PASS** |
| Regression elsewhere (excl. cross_domain_conflict) | ≤ 5.0 pt | -8.0 pt | **FAIL** |
| Cost/case vs. baseline (full pipeline: $0.170121 + $0.052607 = $0.222728 / 18) | ≤ 2.5× | 1.60× | PASS |
| Latency/case vs. baseline (full pipeline: 10.332s + 3.166s) | ≤ 3.0× | 1.56× | PASS |

**Gate 6 is judged NOT cleared** — three of four criteria pass, and the
primary target (the exact structural gap Phase 7 identified) is a
decisive, clean win, but the pre-registered "AND" over all four
criteria means the one real miss (-8.0 pt against a 5.0 pt tolerance)
is disqualifying as written. Full reasoning, including why this is not
read as a refutation of the core hypothesis, is in
[`ADR-006`](decisions/ADR-006-gate6-methodology.md)'s "Gate 6 decision,
executed 2026-09-24" section.

### Root cause, investigated before writing any of this up

Not accepted at face value — two specific claims were traced back to
the actual model-generated rationale text behind them:

- **`case-01-c6` (missing_evidence, correct as `unverified` from the
  investigator) got force-flipped to `contradicted`.** Cause: semantic
  adjudication flagged it as a "subtle_contradiction" against an
  unrelated 30-day-deletion claim, reasoning that 24/7 monitoring
  "may" be needed to verify the deletion happened — a dependency
  invented by the model, not stated in any document. case-01 has
  exactly one planted issue; this is a second, spurious flag.
  `reconcile()` then unconditionally sets every claim in *any* flagged
  conflict to `contradicted`, so a weak, speculative adjudication
  produces a hard incorrect label with no softer outcome available.
  This same over-trigger-then-overwrite mechanism is the most likely
  driver of the broad `none_clean` regression (26 claims, the largest
  category) — cases with one real planted issue are also picking up
  extra, spurious semantic flags on their otherwise-clean claims.
- **`case-07-c1` (version_conflict, correctly `contradicted` from the
  investigator — one of only 2 deterministically-caught conflicts) got
  incorrectly resolved to `supported`.** case-07 is deliberately
  designed (`eval/ground_truth/case-07.json`'s
  `expected_handling_notes`) to be unresolvable from the documents
  alone — two DPA versions with different retention periods and no
  changelog — specifically so a system doesn't silently treat the
  later-dated document as authoritative. Re-investigation's actual
  explanation text did exactly that: "The authoritative value is 60
  days, as it applies under the current version (v2) with the more
  recent effective date... The 30-day value was superseded." That's a
  generic real-world heuristic, not a document-grounded resolution —
  the re-investigation prompt doesn't constrain the model to resolve
  only from what the documents themselves state.
- **Checked for contrast, not just confirmation**: `case-16`'s
  deterministic "conflict" (two different sub-processors — Ridgeline
  Hosting vs. Junction Analytics — mismatched as "same topic, different
  value" by jaccard similarity) is itself a false positive from the
  deterministic pass, and re-investigation correctly recognized this
  and left both claims `supported`. This shows the re-investigation
  mechanism isn't broken in general — it resolves genuinely-not-a-
  conflict cases correctly; it specifically fails when a conflict is
  real but the documents provide no actual resolution, because nothing
  stops it from reaching for outside-of-document reasoning instead of
  saying so.

## Phase 8 fix rerun — executed 2026-09-24

Two targeted, scoped fixes to the reconciliation layer (`app/reconcile.py`,
`app/reinvestigate.py`), built and fake-tested (146 tests) before any
real spend, then run once for real against the same 18 cases, same
saved Phase 7 investigator output, same ground truth — no baseline
rerun, no investigator rerun, no ground-truth changes, no further
prompt tuning after seeing results, per the explicit terms this rerun
was authorized under.

**Fix A** (semantic adjudication over-triggering + blunt overwrite):
added a required `confidence` (`high`/`low`) field to the adjudication
tool schema, tightened the prompt to define it and explicitly forbid
reporting a conflict built on an inferred, undocumented dependency
between claims about different subjects, and changed `reconcile()` so
only `high` confidence forces `verification_status` to `contradicted`
— `low` confidence leaves the claim untouched and opens the conflict
for human review instead.

**Fix B** (re-investigation resolving unresolvable conflicts): added an
explicit carve-out to the re-investigation prompt — a later effective
date alone does not establish supersession; only an explicit
changelog, amendment clause, or explicit supersession statement in the
documents does.

**Zero-cost measurement before spending anything** (chars/4 heuristic,
cross-checked against the one real documented data point — 339.5 est.
vs. 334 actual for the old adjudication prompt, within 2%): projected
~$0.058 new spend, ~$0.428 cumulative. Real run landed under that.

Command run:
```bash
python -m eval.run_reconciliation --i-have-reviewed-the-cost-estimate \
    --investigator-results eval/results/investigators_20260924T082006Z.json
```

| Metric | Value |
|---|---|
| Total new cost (this run only) | **$0.053499** |
| Total input / output tokens | 33,509 / 3,998 |
| Mean latency (incremental, this run only) | 2.673s/case |
| Structured output validity | 100% |

**Cumulative spend: $0.370018 (through the original Phase 8 run) +
$0.053499 (this fix rerun) = $0.423517 of $0.50. Remaining: $0.076483.**

Full raw output: `eval/results/reconciliation_20260924T143706Z.json`.

### Gate 6, rechecked against ADR-006's four criteria

```
category                     baseline acc   reconciled acc    delta  total
ambiguous_wording                    0.0%             0.0%    +0.0%  3
cross_domain_conflict               66.7%           100.0%   +33.3%  6
direct_contradiction                66.7%           100.0%   +33.3%  4
misleading_wording                   0.0%           100.0%  +100.0%  1
missing_evidence                   100.0%           100.0%    +0.0%  4
none_clean                          65.2%            61.5%    -3.7%  26
outdated_evidence                    0.0%             0.0%    +0.0%  2
subtle_contradiction                66.7%           100.0%   +33.3%  3
version_conflict                    50.0%            50.0%    +0.0%  3
[excl. cross_domain_conflict] baseline: acc=61.5% (24/39)
[excl. cross_domain_conflict] reconciled: acc=62.8% (27/43)
```

| Criterion | Threshold | Measured | Result |
|---|---|---|---|
| `cross_domain_conflict` status accuracy | ≥ 66.7% | 100% | **PASS** |
| Regression elsewhere (excl. cross_domain_conflict) | ≤ 5.0 pt | **+1.3 pt** | **PASS** |
| Cost/case vs. baseline (full pipeline: $0.170121 + $0.053499 = $0.223620 / 18) | ≤ 2.5× | 1.61× | PASS |
| Latency/case vs. baseline (full pipeline: 10.332s + 2.673s) | ≤ 3.0× | 1.50× | PASS |

**All four criteria pass. Gate 6 is judged CLEARED under the fixed
implementation** — full reasoning in
[`ADR-006`](decisions/ADR-006-gate6-methodology.md)'s "Gate 6 decision,
updated 2026-09-24 after the fix rerun" section, including the
experimental-integrity caveat that follows.

### What's independent evidence and what isn't — stated plainly, not glossed over

case-01 and case-07 are the exact cases used to diagnose and scope
these fixes. Their recovery is expected, not confirmation:

- `missing_evidence` (75%→100%, n=4): this is entirely case-01-c6
  flipping back — diagnosis-informed, not independent.
- `version_conflict` (0%→50%, n=3): driven by case-07 — also
  diagnosis-informed.

The genuinely independent signal is elsewhere:

- **`none_clean` (26 claims, only a small fraction touched by either
  diagnosed case) recovered from 53.8% to 61.5% — a real, broad
  improvement, but incomplete**: still 3.7 points below baseline's
  65.2%, not fully back to parity. The over-triggering mechanism was
  reduced, not eliminated — some spurious high-confidence flags likely
  still exist elsewhere. Reported as a partial win, not a full fix.
- **No category regressed versus the original (buggy) Phase 8 run** —
  every category held steady or improved when compared directly
  (`eval/compare_results.py eval/results/reconciliation_20260924T121800Z.json
  eval/results/reconciliation_20260924T143706Z.json`).
- **A genuinely new, previously-unseen case exercised the new `low`
  confidence path correctly**: case-18 (not a diagnosis case) produced
  a new speculative semantic-adjudication flag this run (backup
  retention vs. EU data residency) that the model itself described as
  low confidence, reasoning explicitly that the connection was
  inferred, not stated. `reconcile()` correctly left both claims'
  status untouched instead of forcing `contradicted` — the mechanism
  generalizing to a case that didn't inform its design, which is the
  actual independent evidence for whether Fix A works, not case-01.

## Discipline going forward

No further real API calls without explicit review and approval, per
ADR-009.
