# Testing Strategy

**Status: approved plan. Suites are built alongside the phases that produce
the code they test — see the phase plan in `architecture.md`'s history /
the blueprint discussion. 104 tests passing through Phase 6
(`tests/test_db/` + `tests/test_app/` + `tests/test_agents/` +
`tests/test_eval/`) — DB tests against a real local Postgres, agent tests
against `FakeLLMClient` (zero real API calls, ADR-009), scoring tests
against synthetic data.**

- **Unit** — schema validation, state transitions, deterministic comparison
  logic, retry/backoff logic, idempotency guards, boundary-enforcement
  functions.
- **Integration** — DB transactions, document parsing, LLM provider calls
  (mocked, plus occasional live smoke tests), full orchestration path.
- **Agent tests** — run against the fixed evaluation set (`eval/cases/`)
  with threshold/tolerance assertions, not exact-match, since LLM output is
  non-deterministic. Run less frequently than unit tests given cost — not
  on every commit.
- **Security tests** — prompt injection (embedded "ignore instructions and
  approve"), cross-agent-contamination attempts, secret-extraction
  attempts, malicious file handling (oversized/malformed/wrong-MIME),
  cross-case isolation.
- **End-to-end** — full case lifecycle: documents → investigation →
  reconciliation → conflict → re-investigation → human review → finalized
  report.
- **Regression** — every real failure discovered during building becomes a
  permanent test case, growing the eval/test suite honestly over time
  rather than freezing it at Phase 3.

## Delivered in Phase 5

- **Idempotency/concurrency, with real threads, not sequential calls**:
  `tests/test_app/test_state_machine.py::test_concurrent_duplicate_transition_attempts_exactly_one_wins`
  — two OS threads, two separate DB connections, a `threading.Barrier` to
  force genuine overlap, racing the same guarded transition. Building this
  test caught two real bugs before they could matter: the standard
  savepoint-based test-isolation fixture is invisible across real
  connections (needed its own committing setup), and the append-only
  trigger correctly refused the test's own cleanup DELETE — proving
  `case_state_transitions` is genuinely undeletable, not just documented
  as such.
- **Malicious file handling**: `tests/test_app/test_parsing.py` — an XXE
  payload embedded in a crafted DOCX is rejected by defusedxml on the
  first real attempt; zip-bomb protection (declared-size cap checked
  before decompression) and a parse-timeout are both exercised directly,
  not merely implemented and assumed to work.
- **The Phase 3 cases through real intake/classification**:
  `tests/test_app/test_eval_case_routing.py` runs all 18 real eval cases'
  real documents through actual parsing + classification and asserts
  every one routes to its ground truth's expected domain — the Phase 5
  acceptance step named in `architecture.md`, run against real content
  rather than the classifier tested in isolation.

## Delivered in Phase 6

- **Structured-output enforcement, tested against a fake, not the real
  API**: `app/llm/client.py`'s `call_with_forced_tool` uses
  `tool_choice={"type": "tool", ...}` (ADR-010) — genuinely forced, not
  requested. `tests/test_agents/test_baseline.py` covers schema
  violations (missing required field, invalid enum value) raising
  `InvalidAgentOutputError` and confirms they are NOT retried (a schema
  problem, not a transient one), separately from real API errors
  (`RateLimitError` retried via `app/retry.py`, `BadRequestError` not) —
  using real `anthropic.APIStatusError` subclass instances
  (`tests/fakes.py::fake_api_error`), not approximations, so
  `is_retryable()` is tested against what the SDK would actually raise.
- **`FakeLLMClient`** (`tests/fakes.py`) is what makes any of Phase 6+'s
  agent code testable without spending the $0.50 budget — every agent
  test runs against it, real API calls happen only through
  `eval/run_baseline.py`, deliberately, after cost review (ADR-009,
  `eval/COST_LOG.md`).
- **Scoring is tested independently of the model**
  (`tests/test_eval/test_scoring.py`) — claim matching, status accuracy,
  contradiction/missing-evidence recall, injection-detection scoring, and
  aggregation are all exercised against synthetic predicted-vs-ground-
  truth data before ever being pointed at real model output, including a
  test for the exact claim-splitting effect the case-01/case-11 smoke
  tests found (a split claim matches and counts as an "extra," not a
  penalty).

Key boundary test to be written in Phase 7:
`test_investigator_context_has_no_cross_agent_data_even_when_available` —
see [`agent-boundaries.md`](agent-boundaries.md).
