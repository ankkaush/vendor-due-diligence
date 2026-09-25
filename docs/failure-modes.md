# Failure Modes and Risks

**Status: approved design; expanded as real failures are discovered
(each becomes a regression test — see `testing.md`). Status column
added in Phase 13 — this table originally stated every mitigation as
uniform fact; three rows described behavior only a live orchestrator
would exercise, and no live orchestrator was ever built
(`limitations.md`). Corrected here rather than left to imply more than
what actually runs.**

## System failure modes

| Failure mode | Mitigation | Status |
|---|---|---|
| LLM timeout / 5xx / rate-limit | Retry with exponential backoff + jitter, bounded attempts | Implemented, tested (`app/retry.py`) |
| Malformed structured output | Schema validation rejects and retries (bounded); never silently accepted | Implemented, tested (ADR-010) |
| Partial agent failure (one investigator fails, the other succeeds) | Orchestrator proceeds with a flagged gap, does not block the case | **Not implemented** — no live orchestrator exists to proceed past anything (`limitations.md`). The related, actually-built case — an investigator having zero documents in its domain — is handled (`app/agents/investigator.py`'s empty-domain skip, tested), but that's a different failure mode: no documents, not a failed call |
| Duplicate execution (double submission, retried orchestrator call) | Partial unique index on `(case_id, agent_type)` non-terminal runs | Implemented, tested (`tests/test_db/test_schema_constraints.py`) |
| Concurrent finalization | Transaction-guarded status update; second writer gets 0 rows affected, not a silent overwrite | Implemented, tested with real concurrent threads (`tests/test_app/test_state_machine.py`), and reused for the human-review finalize path (Phase 9) |
| Provider outage | Non-retryable failure path, case marked `FAILED` with reason, resumable | **Partially implemented**: retryable-vs-not classification is real and tested; `FAILED` is a real terminal state in the state machine with transitions defined into it from every state — but the *resumable* half was explicitly scoped out when the state machine was built ("nothing to resume into until agents exist," `app/state_machine.py`) and never revisited, since no live orchestrator exists to resume in the first place |
| Stale/crashed workflow state | Periodic reconciliation query finds cases stuck past a threshold | **Not implemented** — no scheduler or periodic job exists anywhere in this codebase |
| Malicious/malformed documents | Size cap, MIME allow-list, parse timeout, reject-on-failure | Implemented, tested (Phase 5 — XXE, zip-bomb, timeout, oversized/wrong-MIME all exercised directly) |
| Prompt injection | No privileged action available to hijack (ADR-003); tested explicitly (`threat-model.md`) | Implemented, tested |
| Re-investigation loop | Hard-bounded to 1 round (decision #13) — disagreement is itself information, not a defect to iterate away | Implemented, tested (`UNIQUE(conflict_id)` on `reinvestigations`) |

## Project-level risks (honest, not hidden)

- **Resolved (2026-09-24), not merely mitigated**: the single-agent
  baseline was a genuinely strong comparison, and the first real
  reconciliation run *did* fail the pre-registered secondary criterion
  — this risk materialized, not just a hypothetical. Root-caused to two
  specific reconciliation-layer defects, fixed, and re-verified as
  cleared on the real re-run. The risk was real; the response to it —
  measure, don't round up to a pass, fix the actual defect, re-measure
  — is the part worth recording here. Full account:
  [ADR-006](decisions/ADR-006-gate6-methodology.md), `limitations.md`.
- **Synthetic evidence may be too clean,** making both systems look
  artificially strong and the comparison uninformative. Mitigated by
  deliberately writing subtle, realistically messy contradictions into the
  evaluation dataset (Phase 3), not just obvious ones.
- **Scope creep to more investigators** before Gate 6 even resolves with 2
  — explicitly guarded against (decision #1).
- **Ground-truth dataset construction taking longer than expected** — it is
  genuinely the hardest phase; budgeted for accordingly rather than rushed.
