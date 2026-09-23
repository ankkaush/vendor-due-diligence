# Failure Modes and Risks

**Status: approved design; expanded as real failures are discovered
(each becomes a regression test — see `testing.md`).**

## System failure modes (mitigated by design)

| Failure mode | Mitigation |
|---|---|
| LLM timeout / 5xx / rate-limit | Retry with exponential backoff + jitter, bounded attempts |
| Malformed structured output | Schema validation rejects and retries (bounded); never silently accepted |
| Partial agent failure (one investigator fails, the other succeeds) | Orchestrator proceeds with a flagged gap, does not block the case |
| Duplicate execution (double submission, retried orchestrator call) | Partial unique index on `(case_id, agent_type)` non-terminal runs |
| Concurrent finalization | Transaction-guarded status update; second writer gets 0 rows affected, not a silent overwrite |
| Provider outage | Non-retryable failure path, case marked `FAILED` with reason, resumable |
| Stale/crashed workflow state | Periodic reconciliation query finds cases stuck past a threshold |
| Malicious/malformed documents | Size cap, MIME allow-list, parse timeout, reject-on-failure |
| Prompt injection | No privileged action available to hijack (ADR-003); tested explicitly (`threat-model.md`) |
| Re-investigation loop | Hard-bounded to 1 round (decision #13) — disagreement is itself information, not a defect to iterate away |

## Project-level risks (honest, not hidden)

- **The single-agent baseline may be "too strong,"** and the multi-agent
  thesis may fail Gate 6. This is a legitimate engineering finding, not a
  planning failure — see [ADR-006](decisions/ADR-006-gate6-methodology.md).
- **Synthetic evidence may be too clean,** making both systems look
  artificially strong and the comparison uninformative. Mitigated by
  deliberately writing subtle, realistically messy contradictions into the
  evaluation dataset (Phase 3), not just obvious ones.
- **Scope creep to more investigators** before Gate 6 even resolves with 2
  — explicitly guarded against (decision #1).
- **Ground-truth dataset construction taking longer than expected** — it is
  genuinely the hardest phase; budgeted for accordingly rather than rushed.
