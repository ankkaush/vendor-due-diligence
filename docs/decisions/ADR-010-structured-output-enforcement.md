# ADR-010: Structured output must be enforced, not requested

**Status:** Accepted, implemented Phase 6 — `app/llm/client.py`'s
`call_with_forced_tool` (`tool_choice={"type": "tool", "name": ...}`),
consumed by `app/agents/baseline.py`. Verified in
`tests/test_agents/test_baseline.py` against `FakeLLMClient`, not yet
against the real API (that happens as part of the Phase 6 evaluation run,
pending cost review — `eval/COST_LOG.md`).
**Date:** 2026-09-23

## Context

Two real smoke-test calls (`eval/smoke_test.py`, `eval/COST_LOG.md`) —
one on case-11, one on case-01, different sizes, different content — both
returned their JSON response wrapped in a ` ```json ... ``` ` markdown
code fence, despite the system prompt explicitly stating "Respond with
ONLY valid JSON, no other text." Both calls broke a naive `json.loads()`
call. This is not a one-off fluke; it recurred identically on two
unrelated prompts, which is exactly the kind of systematic behavior a
production system has to design around rather than hope away.

The project's whole premise depends on structured, schema-validated agent
output (Section 8 of the blueprint; `data-model.md`'s `Finding` schema;
"structured-output validity rate" already listed as a Phase 6 evaluation
metric in `evaluation.md`). If the mechanism for getting that structure is
"ask nicely in the system prompt," the failure mode isn't hypothetical —
it's already been observed, twice, before any application code exists.

## Decision

Phase 6 (single-agent baseline) and Phase 7 (independent investigators)
must use Anthropic's native structured-output enforcement — forced tool
use with a JSON-schema-defined input (a "tool call" whose sole purpose is
to carry the structured `Finding`/`Claim` payload, not to perform an
action) — rather than relying on prompt instruction alone to produce
parseable JSON.

A defensive fallback parser (e.g. stripping a leading/trailing markdown
fence before `json.loads`) may still exist as a second line of defense,
but it is not a substitute for enforcement and must not be the primary
mechanism — if the *enforced* path still produces something schema-
invalid, that is a genuine finding worth surfacing (retry, log, escalate
per the existing bounded-retry policy in `architecture.md`'s state
machine), not something to silently paper over with more string-munging.

**Required test** (Phase 6, to be added to `testing.md`'s agent-test
suite): a test that submits real (or recorded/mocked) model output through
the actual parsing path and asserts it succeeds via the enforced
structured-output mechanism specifically — not via a fence-stripping
fallback catching what enforcement should have prevented. If the fallback
path is ever what makes the test pass, that is a failing signal about the
enforcement mechanism, not a passing test.

## Consequences

- Small added implementation cost in Phase 6/7: defining tool/schema
  definitions for `Claim`/`Finding` extraction, rather than only writing
  a natural-language instruction.
- Removes an entire class of "valid content, wrong wrapper" parsing
  failures from being a normal-path concern — a parse failure downstream
  of enforcement becomes a real schema-violation signal, which is exactly
  what "structured-output validity rate" is supposed to measure. Without
  enforcement, that metric would partly be measuring prompt-phrasing luck
  instead of the agent's actual output discipline.
- This finding came from $0.008 of real, deliberate calibration spend —
  a concrete example of why the smoke-test discipline (ADR-009) is worth
  the small cost: it surfaced a real implementation requirement before a
  single line of Phase 6 code was written, rather than after.
