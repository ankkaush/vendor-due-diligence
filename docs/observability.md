# Observability

**Status: approved design (Phase 10 target for full instrumentation).**

Built into the architecture from the start, not bolted on at the end.

## Trace hierarchy

```
case → workflow_run → agent_run → llm_call → evidence → finding →
conflict → reinvestigation → human_decision
```

## Tooling

- **Langfuse** — LLM tracing: prompts, completions, tool calls (none in
  MVP), tokens, cost, latency, retries. Every trace correlates to
  `case_id`/`agent_run_id`.
- **Sentry** — application/runtime errors: DB failures, unhandled
  exceptions, provider outages. Distinct failure layer from LLM reasoning
  quality, which Langfuse covers.

## Redaction policy

Full vendor document text is **not** sent to Langfuse by default. Traces
carry excerpt hashes and short, bounded snippets sufficient for debugging
and evaluation, not complete documents. This is a deliberate data-
minimization decision, not an oversight — Langfuse is a third-party service,
and minimizing what leaves the local system is good hygiene even when the
underlying documents are synthetic.

Secrets are never logged or traced, anywhere, under any circumstance.

## What's tracked per unit

`case_id`, `run_id`, `agent_id`/`agent_type`, model, timestamps, latency,
token usage, cost, retry count, failures, evidence references, conflicts,
human decisions. This is the same data that feeds [`evaluation.md`](evaluation.md)'s
metrics — observability and evaluation share one instrumentation layer, not
two.
