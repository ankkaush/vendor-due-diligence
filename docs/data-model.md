# Data Model

**Status: approved design (Phase 4 target for implementation).**

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
