# Observability

**Status: implemented (Phase 10) — `app/observability.py`. Both
integrations are no-op until real credentials are set (`.env`'s
`LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`, `SENTRY_DSN`); nothing here required
signing up for either service to build or test. Tested against a fake
Langfuse client (`tests/test_app/test_observability.py`), never the real
SDK — zero network, zero cost, matching every other LLM-adjacent test in
this repo (ADR-009).**

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

## Implementation (Phase 10)

`TracedLLMClient` (`app/observability.py`) wraps any `LLMClient`
(app/llm/client.py) and implements the identical Protocol — additive,
not invasive: no agent module, no existing test, and no already-tested
Phase 6/7/8 call site had to change. A caller that wants tracing
constructs `TracedLLMClient(AnthropicLLMClient(key))` instead of the
bare client (already wired into `eval/run_baseline.py`,
`eval/run_investigators.py`, `eval/run_reconciliation.py` for any future
real run); everything above it is unaware of the difference.

Redaction is a concrete, unit-tested function (`redact_for_trace`), not
a policy statement trusted to hold: every prompt/completion sent to
Langfuse is a bounded excerpt (200 chars) plus a sha256 hash and the
true length — enough to debug from or confirm two traces reference the
same content, never the full text.

Case-level correlation (`case → workflow_run → agent_run → llm_call`)
is a constructor-time `trace_id` argument
(`TracedLLMClient(client, trace_id=str(case.id))`), ready for whenever a
live orchestrator exists to supply it — `call_with_forced_tool`'s
signature itself never grew case_id/agent_run_id parameters, since no
current real caller could populate them (`limitations.md`).

Tracing can never break the operation it observes: every Langfuse SDK
call is wrapped and any failure is swallowed, not re-raised
(`tests/test_app/test_observability.py::test_traced_client_never_lets_a_broken_langfuse_sdk_break_the_real_call`).

Sentry (`configure_sentry()`) is called once at app startup
(`app/web/main.py`) and is a no-op without `SENTRY_DSN` set.
