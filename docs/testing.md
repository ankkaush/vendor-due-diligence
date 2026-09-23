# Testing Strategy

**Status: approved plan. Suites are built alongside the phases that produce
the code they test — see the phase plan in `architecture.md`'s history /
the blueprint discussion.**

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

Key boundary test to be written in Phase 7:
`test_investigator_context_has_no_cross_agent_data_even_when_available` —
see [`agent-boundaries.md`](agent-boundaries.md).
