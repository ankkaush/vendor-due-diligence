# API Cost Ledger

**Hard ceiling: $0.50 total, for the entire project, never exceeded (ADR-009).**
This file is updated after every real Anthropic API call from this point
forward — no exceptions, no batching updates "for later." Nothing has been
spent yet; every case built so far (`eval/cases/`, `eval/ground_truth/`) is
static text and JSON, authored without any API calls.

| Date | Purpose | Model | Input tokens | Output tokens | Cost (USD) | Running total | Remaining |
|---|---|---|---|---|---|---|---|
| 2026-09-23 | Smoke test attempt #1 (case-11) — **failed before inference**, HTTP 400: API key not scoped to a workspace (`anthropic-workspace-id` header required). No tokens processed. | claude-haiku-4-5-20251001 | 0 | 0 | $0.00 | $0.00 | $0.50 |

Smoke-test plan was reviewed and approved per the prior conversation
(case-11, real pricing sourced 2026-09-23: $1/$5 per MTok in/out for
Haiku 4.5). Execution failed at the request-validation stage before any
model inference occurred, so no cost was incurred — confirm this against
the Anthropic Console usage page once the key issue is fixed, since this
entry is inferred from the error type, not independently verified against
billing.

## Next step

Fix the API key's workspace scoping (see chat), then re-run:

```bash
python eval/smoke_test.py --i-have-reviewed-the-cost-estimate
```

No further review is required to retry the *same already-approved* case-11
smoke test after fixing the key — the approval covered this specific call,
not a new one.
