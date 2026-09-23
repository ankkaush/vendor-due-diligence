# Data Model

**Status: implemented (Phase 4).** Schema: [`app/db/models.py`](../app/db/models.py).
Migration: [`alembic/versions/c28dd1c04d1e_initial_schema.py`](../alembic/versions/c28dd1c04d1e_initial_schema.py).
Verified: migration up/down cycles cleanly; constraint and evidence-chain
tests pass in [`tests/test_db/`](../tests/test_db/) against a real local
Postgres (`docker compose up -d`, isolated per-project on port 5437 —
never the production Supabase instance).

## Entities and lifecycle

```
Vendor ──< Case ──< EvidenceDocument ──< DocumentVersion
                       │
                       ├──< Claim (tagged: extracted_by agent_run_id)
                       │       └──< EvidenceItem ──> DocumentVersion + location
                       │
Case ──< AgentRun (security_investigator | privacy_investigator | single_agent_baseline)
                       └──< Finding (per claim: status, rationale, evidence_item_ids)
Case ──< Conflict (links ≥2 Findings) ──< ReInvestigation (bounded to 1 round)
Case ──< HumanReview (immutable, append-only — never updates a prior review)
Case ──< AuditEvent (append-only: every state transition, agent run, decision)
```

## Core evidence chain

Every conclusion in the final report must be traceable down this chain — if
it can't be traced, it isn't in the report:

```
Claim → EvidenceItem → SourceDocument(Version) → Location →
AgentFinding → VerificationStatus → HumanDecision
```

## Key design decisions

- **Documents are versioned.** A vendor resubmitting a corrected DPA creates
  a new `DocumentVersion`; existing evidence links keep pointing at the
  version they actually referenced, so provenance survives resubmission.
- **`HumanReview` is append-only.** Overriding a finding creates a new row
  referencing what it overrides — it never mutates the AI's original
  finding. The audit trail shows both what the AI concluded and what the
  human decided, never just the final state.
- **Claims are extracted independently per agent, not shared.** Each `Claim`
  row records which `AgentRun` extracted it (ADR-004). If both investigators
  independently identify "the same" real-world claim, that agreement is
  itself a measurable signal, not something deduplicated away upstream.
- **Idempotency is a schema-level constraint, not just application logic.**
  A partial unique index ensures at most one non-terminal `AgentRun` per
  `(case_id, agent_type)`.
- **Externally-referenced entities use UUID primary keys**, not sequential
  integers — `Case`, `EvidenceDocument`, and anything else addressable via a
  URL or form field. This is defense-in-depth against ID enumeration even
  though every route is auth-gated (see `threat-model.md` §3.1, `security.md`).
- **`case.status` has no `SECURITY_RUNNING`/`PRIVACY_RUNNING` sub-states.**
  `architecture.md`'s diagram shows these as a parallel-execution note, not
  literal case states — per-agent progress lives on `AgentRun.status`
  instead, which is exactly the workflow-state-vs-agent-state distinction
  this table already draws.
- **Append-only is a database trigger, not just a convention.**
  `case_state_transitions`, `human_reviews`, and `audit_events` reject
  UPDATE and DELETE at the database level (a `BEFORE UPDATE OR DELETE`
  trigger raising an exception), regardless of which role issues the
  query — verified directly in `tests/test_db/test_schema_constraints.py`
  by actually attempting both and confirming both are refused.
- **Decision #13 (max one re-investigation round) is a `UNIQUE(conflict_id)`
  constraint** on `reinvestigations`, not application logic that could be
  bypassed under pressure to "just try once more."
- **Enum values are identical to `eval/schema/ground_truth.schema.json`**
  wherever both describe the same concept (`doc_type`, `domain`,
  `claim_type`, `verification_status`, `conflict_type`) — ADR-008's "ground
  truth reuses the production schema" made literal, not just a stated
  intention.

## State vs. business vs. evidence vs. agent state

| State type | What it holds | Mutability |
|---|---|---|
| Workflow state | `case.status` enum driving orchestration | Transitions only, transaction-guarded |
| Business state | Vendor/case identity, decision outcome | Normal relational updates |
| Evidence state | Claim/EvidenceItem/Conflict graph | Append-only for facts; mutable only for conflict resolution status |
| Agent state | `AgentRun` execution record (tokens, cost, latency, retries) | Written once per run, the observability substrate |

## Ground-truth ontology

The evaluation dataset's label schema reuses these same `Claim`/
`EvidenceItem` fields plus eval-only metadata (`issue_type`,
`is_planted_issue`, `expected_handling_notes`) — see
[ADR-008](decisions/ADR-008-ground-truth-ontology.md). No numeric
`expected_confidence` field: `verification_status` (including `ambiguous`)
is the sole graded label until confidence is rigorously defined.
