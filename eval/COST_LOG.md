# API Cost Ledger

**Hard ceiling: $0.50 total, for the entire project, never exceeded (ADR-009).**
This file is updated after every real Anthropic API call from this point
forward — no exceptions, no batching updates "for later." Nothing has been
spent yet; every case built so far (`eval/cases/`, `eval/ground_truth/`) is
static text and JSON, authored without any API calls.

| Date | Purpose | Model | Input tokens | Output tokens | Cost (USD) | Running total | Remaining |
|---|---|---|---|---|---|---|---|
| — | *(no real API calls made yet)* | — | — | — | $0.00 | $0.00 | $0.50 |

## Before the next row is added

Per ADR-009, the first real call is a single one-case smoke test, and it
does not happen until the project owner has explicitly reviewed:

1. Which case is used and why.
2. The candidate model(s) and current published pricing at the time.
3. The expected token count and expected cost, estimated from the actual
   case content.
4. What happens if the measured cost differs meaningfully from the
   estimate (see ADR-009 consequences).

That review has not happened yet — this ledger stays at $0.00 until it
does.
