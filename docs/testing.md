# Testing Strategy

**Status: approved plan. Suites are built alongside the phases that produce
the code they test — see the phase plan in `architecture.md`'s history /
the blueprint discussion. 81 tests passing through Phase 5
(`tests/test_db/` + `tests/test_app/`), all against a real local Postgres
(`docker compose up -d`), none mocked at the DB layer.**

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

Key boundary test to be written in Phase 7:
`test_investigator_context_has_no_cross_agent_data_even_when_available` —
see [`agent-boundaries.md`](agent-boundaries.md).

Key structured-output test to be written in Phase 6
([ADR-010](decisions/ADR-010-structured-output-enforcement.md)): a test
confirming parsed output succeeds via the enforced structured-output
mechanism (forced tool use / JSON schema) specifically, not via a
defensive fence-stripping fallback catching what enforcement should have
prevented. Motivated by two real smoke-test calls
(`eval/COST_LOG.md`) both returning JSON wrapped in a markdown code fence
despite an explicit prompt instruction not to — a real, reproduced
failure mode, not a hypothetical one.
