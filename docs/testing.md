# Testing Strategy

**Status: approved plan. Suites are built alongside the phases that produce
the code they test — see the phase plan in `architecture.md`'s history /
the blueprint discussion. 146 tests passing through Phase 8's
reconciliation fix (`tests/test_db/` + `tests/test_app/` + `tests/test_agents/` +
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

## Delivered in Phase 7

- **The named boundary test**:
  `tests/test_agents/test_boundary_enforcement.py::test_investigator_context_has_no_cross_agent_data_even_when_available`
  — see [`agent-boundaries.md`](agent-boundaries.md) for what it proves
  and its explicit scope note (document-level isolation, not yet
  DB-level, since no persisted Finding data exists this phase). A
  companion test asserts the guarantee structurally too:
  `run_investigator`'s signature has no parameter through which another
  agent's output could ever be passed in, and a third confirms the
  isolation holds regardless of execution order.
- **A real edge case found by measuring, not by running**: sizing the
  real Phase 7 evaluation cost before spending anything revealed 9 of 36
  case/investigator pairs across the 18 real cases have zero documents in
  that investigator's domain (e.g. case-03 has no privacy documents at
  all). `app/agents/investigator.py` now skips the API call entirely in
  that case — tested in `test_empty_domain_skips_the_api_call_entirely`,
  which passes a `FakeLLMClient` with zero scripted responses so the test
  fails loudly if a call is ever attempted.
- **Rubric parity across architectures**:
  `test_both_investigators_share_the_identical_verification_rubric`
  asserts the exact same `VERIFICATION_RUBRIC` text
  (`app/agents/prompts.py`) appears in both investigators' prompts and
  matches what the Phase 6 baseline uses — Gate 6 needs to compare
  architectures, not accidentally compare differently-worded grading
  standards (ADR-006).

## Delivered in Phase 8

- **Deterministic conflict detection is a pure function, fully tested
  without any model at all** (`tests/test_app/test_reconcile.py`): same
  agent, matching subject/predicate, different value → conflict; same
  topic same value → no conflict (agreement, not flagged); different
  agents with matching subject/predicate → correctly NOT flagged by this
  pass at all (that's semantic adjudication's job — a dedicated test
  asserts the deterministic pass stays out of it even when the fields
  line up).
- **The empty-input guard pattern repeats, deliberately** —
  `test_semantic_adjudication_is_skipped_when_deterministic_pass_consumes_everything`
  confirms that if every pooled claim was already resolved
  deterministically, the semantic-adjudication call is skipped entirely
  (same principle as Phase 7's empty-domain guard) — found and tested
  before spending anything, not after.
- **Re-investigation's neutrality, tested directly**:
  `test_prompt_describes_the_discrepancy_neutrally_not_as_another_agents_claim`
  asserts the follow-up prompt describes the agent's own prior
  discrepancy without ever framing it as "another investigator
  disagrees" — ADR-007's anchoring-avoidance requirement, checked in the
  actual prompt text, not just claimed in a docstring.
- **Unresolved is a valid, tested outcome, not an error path**:
  `test_unresolved_outcome_is_parsed_and_is_not_an_error` and
  `test_reconcile_leaves_conflict_open_when_reinvestigation_cannot_resolve`
  — case-18's deliberately-unresolvable conflict needs the system to say
  "I don't know, here's why" cleanly, not raise or fabricate an answer.
- **Fix for the real Phase 8 regression, tested before it cost
  anything**: the real run found semantic adjudication over-triggering
  and forcing an incorrect `contradicted` label; a `confidence` field
  was added and `test_low_confidence_semantic_conflict_leaves_status_untouched_and_stays_open`
  confirms `reconcile()` leaves `verification_status` alone and opens
  the conflict for human review instead, rather than repeating the
  unconditional overwrite. `test_prompt_rules_out_later_effective_date_alone_as_a_resolution`
  does the same for the paired re-investigation defect — asserting the
  prompt text itself rules out "later document wins" as a sufficient
  resolution, the exact reasoning the real run's case-07 failure relied
  on.
