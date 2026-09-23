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

## Discipline going forward

No further real API calls without explicit review and approval, per
ADR-009. The next real spend is expected to be the actual Phase 6/7
evaluation run, not before.
