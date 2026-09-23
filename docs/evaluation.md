# Evaluation

**Status: approved methodology. Dataset construction is Phase 3 (before the
baseline is built). Numbers populated starting Phase 6.**

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

~18 synthetic vendor evidence packages (3–5 documents each), each with an
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

## Cost ceiling

Set after Phase 6 baseline measurement, not before (decision #11). Expected
cost/case, worst-case cost/case, and total evaluation-run cost are estimated
from real token usage once the baseline exists, then an explicit ceiling is
set and enforced (not merely reported) before the full evaluation run.
