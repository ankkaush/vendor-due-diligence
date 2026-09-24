# Evaluation

**Status: Phase 6 complete. Real baseline run executed 2026-09-24 against
all 18 cases (`eval/COST_LOG.md`, `eval/results/baseline_20260924T080217Z.json`)
— see "Phase 6 baseline results" below. This is now the number Phase
7/8's multi-agent architecture has to beat at Gate 6.**

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

## Gate 6 methodology (pre-registration)

1. Phase 6 completes → baseline quality, cost, latency, and retry/failure
   rate are measured and recorded here.
2. **Before** Phase 7/8 results are computed or reviewed,
   [ADR-006](decisions/ADR-006-gate6-methodology.md) is dated and locks the
   quality-improvement bar (on the metrics above) and the cost/latency
   tolerance multiplier — derived from the baseline's actual numbers, not
   invented in advance.
3. Only then does the multi-agent evaluation run and Gate 6 get decided.
4. If multi-agent doesn't clear the pre-registered bar, the architecture is
   simplified and that result is documented honestly — a measured "it
   wasn't worth it, here's the data" is the correct outcome if that's what
   the evidence shows.

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
