# Architecture

**Status: approved design (Gate 1 closed), implemented and complete —
data model, intake/validation/parsing/classification/state machine
(Phase 5), single-agent baseline and independent investigators
(Phase 6/7), reconciliation (Phase 8, real-run-fixed and Gate 6
cleared), the human review UI (Phase 9), security test audit +
observability (Phase 10), CI/CD (Phase 11), and a defined, provisioned
deployment target (Phase 12). See README for the project summary and
`limitations.md` for the full honest accounting. No live upload-to-review
HTTP pipeline exists; every UI-visible case is seeded from
already-executed real output.

## Problem

A vendor evidence package (security questionnaire, SOC-style report, DPA,
privacy policy, AI/model documentation, subprocessor list, contract/SLA)
contains many claims. A reviewer needs to know which are supported,
contradicted, unverified, or ambiguous — and why — before making an approval
decision. The AI assists that determination; it never makes it.

## Technical thesis

Independently executed, domain-scoped AI investigators, isolated from each
other's context and conclusions, are hypothesized to catch verification
errors that a strong single-agent baseline misses. This is tested at **Gate
6**, not assumed. See [`evaluation.md`](evaluation.md) and
[ADR-006](decisions/ADR-006-gate6-methodology.md).

## End-to-end flow

```
Vendor Evidence Package (PDF/DOCX/TXT/MD)
        │
        ▼
INTAKE → VALIDATE (file type, size, parseability)
        │
        ▼
DOCUMENT CLASSIFICATION (deterministic doc_type → domain routing table)
        │
        ├─────────────────────────────┐
        ▼                              ▼
 Security Investigator          Privacy / AI-Gov Investigator
 (sees ONLY security-routed      (sees ONLY privacy-routed
  documents; extracts its OWN    documents; extracts its OWN
  claims and verifies them —     claims and verifies them —
  independently, ADR-004)        independently, ADR-004)
        │                              │
        ▼                              ▼
 Structured Findings           Structured Findings
        └──────────────┬───────────────┘
                        ▼
         DETERMINISTIC RECONCILIATION
         (schema-level diff first; semantic
          adjudication only where deterministic
          comparison can't resolve it)
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
        No conflicts        Conflicts detected
              │                   ▼
              │          TARGETED RE-INVESTIGATION
              │          (max 1 bounded round, decision #13;
              │           neutral domain-scoped follow-up,
              │           never exposes the other agent's
              │           identity or conclusion — ADR-007)
              │                   │
              │          still unresolved → open conflict
              └─────────┬─────────┘
                        ▼
                  SYNTHESIZE REPORT
                        ▼
         HUMAN REVIEW — mandatory for every case,
         including the no-conflict path (decision #3).
         The system never auto-finalizes.
                        ▼
              Human decision recorded (immutable)
                        ▼
                   FINALIZED
```

## Deterministic vs. single-agent vs. multi-agent

| Sub-task | Deterministic | Single agent | Multi-agent |
|---|---|---|---|
| File validation, MIME/size checks | Fully handles it | — | — |
| Document classification/routing | Fully rule-based for 9/10 doc_types; `other` requires an explicit domain (no model fallback exists yet — Phase 5 has no agents) | Future fallback, if ever needed | — |
| Claim extraction | — | Can do it | Done independently per domain (ADR-004) |
| Domain-specific claim verification | — | Does most of it in one pass | Tests whether domain isolation catches what one pass misses |
| Schema-level contradiction detection (e.g. "30 days" vs "90 days") | Fully handles it, no LLM call | Unnecessary | Unnecessary |
| Semantic-level contradiction detection | — | Can attempt | The actual hypothesis under test |
| Final risk decision | Never automated | Never automated | Never automated — human only |

## Technology stack

| Layer | Choice | Reference |
|---|---|---|
| Backend | Python + FastAPI | |
| Database | PostgreSQL (Supabase) | ADR-005 |
| LLM provider | Anthropic (sole provider for MVP) | ADR-001, decision #5 |
| Orchestration | Explicit Python state machine | ADR-002 |
| Frontend | Server-rendered Jinja2 + HTMX | decision #4 |
| Observability | Langfuse (LLM tracing/cost) + Sentry (app errors) | decision #7, observability.md |
| Deployment | Render (app) + Supabase (Postgres) | ADR-005 |

No LangGraph/CrewAI/AutoGen/Temporal, no Kubernetes/Redis/Kafka/Celery, no
multi-tenant SaaS architecture. See [`limitations.md`](limitations.md) and
the ADRs for why each was deliberately excluded.

## State machine

```
INTAKE → VALIDATING → VALIDATION_FAILED (terminal, human resubmits)
                    → DOCUMENTS_READY → CLASSIFYING → INVESTIGATING
                        (parallel: SECURITY_RUNNING, PRIVACY_RUNNING)
                    → INVESTIGATIONS_COMPLETE → RECONCILING
                        → [no conflicts] → SYNTHESIZING
                        → [conflicts] → REINVESTIGATING (max 1 round)
                                      → RECONCILING_POST_REINVESTIGATION → SYNTHESIZING
                    → AWAITING_HUMAN_REVIEW → FINALIZED
                    → FAILED (resumable from last checkpoint where possible)
                    → CANCELLED
```

Every transition is an append-only row plus a transaction-guarded status
update (`UPDATE ... WHERE status = <expected>`), so concurrent workers can't
double-advance or double-finalize a case. See [`data-model.md`](data-model.md).

**Implemented:** [`app/state_machine.py`](../app/state_machine.py) — the
graph above as data (`TRANSITIONS`), plus the guarded `transition_case()`.
Proven under real concurrency, not just asserted: two threads on separate
DB connections racing the same transition, exactly one wins
(`tests/test_app/test_state_machine.py`). `FAILED`'s resume path is
deliberately not implemented yet — there's nothing to resume into until
Phase 6/7's agents exist; scoped out explicitly, not forgotten.

## Reconciliation (RECONCILING / REINVESTIGATING)

**Implemented (Phase 8):** [`app/reconcile.py`](../app/reconcile.py) +
[`app/reinvestigate.py`](../app/reinvestigate.py). Two distinct
mechanisms, chosen deliberately from what Phase 7's real evaluation
showed (`docs/evaluation.md`'s category breakdown):

1. **Deterministic conflict detection** — same-agent claims with matching
   subject/predicate but different values (e.g. two retention-period
   figures from one investigator's own documents). Resolved via one
   bounded re-investigation call (decision #13) back to the *same*
   investigator — a same-agent follow-up over documents it already has,
   never a cross-boundary call, since routing already guarantees a
   same-domain conflict was found by one agent in the first place. The
   follow-up is phrased neutrally (ADR-007): it describes the agent's own
   prior discrepancy, never "the other agent disagrees."
2. **Semantic adjudication** — one LLM call per case, given every
   remaining pooled claim from both investigators at once, to catch
   conflicts that don't share matching wording — this is what recovers
   `cross_domain_conflict`, since only the reconciler (not either
   domain-locked investigator) can see both sides at once. No
   re-investigation is used here: asking either investigator to "look
   again" wouldn't surface the other domain's document it structurally
   never receives.

A genuinely unresolvable conflict (case-18's deliberately-planted pair,
`eval/CASES.md`) is expected to stay `open` after its one bounded
re-investigation round — that's the correct outcome, not a failure to
keep trying (`tests/test_app/test_reinvestigate.py`,
`tests/test_app/test_reconcile.py`).

## Human review UI (AWAITING_HUMAN_REVIEW / FINALIZED)

**Implemented (Phase 9):** [`app/web/`](../app/web/) — FastAPI +
server-rendered Jinja2 (decision #4/#8), no HTMX yet (deliberately
deferred progressive-enhancement polish, not a blocker: plain form
POST/redirect works without it). Single-reviewer HTTP Basic auth
(`app/web/auth.py`, deployment.md) gates every route — there is no
unauthenticated route, including document content, which is rendered
only inside the already-gated case detail page rather than through a
separate file route (security.md's Phase 5/9 rule). The one
state-changing endpoint, review submission, is CSRF-protected via a
signed double-submit cookie (`app/web/csrf.py`) and reuses
`app.state_machine.transition_case()`'s WHERE-guarded update for the
AWAITING_HUMAN_REVIEW -> FINALIZED transition — the same idempotency
guarantee Phase 5 proved under real concurrent threads, not a new
mechanism for this one more caller.

**The missing piece this phase had to build first:** nothing before
Phase 9 ever wrote an `AgentResult` or `ReconciliationResult` into the
DB's evidence graph — Phase 6/7/8's eval runners score raw JSON, never
touch Postgres. [`app/persist.py`](../app/persist.py) is that bridge.
One deliberate design choice in it: a conflict's resolution (whether
from bounded re-investigation or semantic adjudication) is never
written as a mutated or duplicated `Finding` row — data-model.md's own
mutability table already draws this line ("Claim/EvidenceItem/Conflict
graph: append-only for facts; mutable only for conflict resolution
status"), so a `Finding` stays exactly what one `AgentRun` concluded,
and the reconciler's read lives on `Conflict` (status +
resolution_rationale), linked back via `ConflictFinding`. The review UI
renders both side by side — the human sees the tension a conflict
represents, not a silently overwritten status.

No live orchestrator wires document upload through the real pipeline
over HTTP yet (that's separate, larger future work needing its own
ADR-009 cost review). Phase 9's demo cases are seeded
(`scripts/seed_demo_case.py`) from already-executed, already-paid real
Phase 7/8 output — zero new API spend, same reuse discipline Phase 8
itself used — replayed through the real `app.intake` /
`app.state_machine` / `app.persist` code paths, not synthetic data.

## Document classification (routing table)

The routing table Phase 5 was scoped to decide: a deterministic
`doc_type → domain` default ([`app/routing.py`](../app/routing.py)),
reusing the same domain vocabulary as `eval/schema/ground_truth.schema.json`.
Nine of ten `doc_type`s have an unambiguous default; `other` has none —
Phase 5 has no LLM to infer it, so it requires an explicit domain at
ingestion time rather than guessing.

A document's domain can also be explicitly overridden away from its
default, because real documents don't respect clean categories. This
isn't hypothetical: building this table surfaced a real inconsistency in
`eval/ground_truth/case-12.json` — a `security_questionnaire` containing a
GDPR question, with the questionnaire tagged `domain: "security"` but the
GDPR claim tagged `domain: "privacy_ai_governance"`. Routed "security
only" by default, the privacy investigator would never see that document
and the claim would be structurally unreachable — a ground-truth bug the
routing table made visible, not a hypothetical edge case. Fixed by
tagging that specific document `domain: "both"`
(`tests/test_app/test_eval_case_routing.py` runs all 18 real eval cases'
real documents through actual intake + classification and asserts every
one routes to its ground truth's expected domain).

## Related ADRs

- [ADR-001](decisions/ADR-001-single-vs-multi-agent-architecture.md) — multi-agent as a tested hypothesis
- [ADR-002](decisions/ADR-002-explicit-orchestration-vs-framework.md) — explicit orchestration over a framework
- [ADR-003](decisions/ADR-003-no-live-external-evidence-tools.md) — no live external tools in MVP
- [ADR-004](decisions/ADR-004-independent-claim-extraction.md) — per-agent claim extraction
- [ADR-005](decisions/ADR-005-deployment-target.md) — deployment target
- [ADR-006](decisions/ADR-006-gate6-methodology.md) — Gate 6 methodology
- [ADR-007](decisions/ADR-007-agent-context-isolation.md) — data-access-boundary isolation
- [ADR-008](decisions/ADR-008-ground-truth-ontology.md) — ground-truth ontology
