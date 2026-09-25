# Vendor Due-Diligence & Evidence Verification

**Status: complete.** A finished AI/GenAI engineering project that
experimentally evaluated whether independently executed, domain-scoped
AI investigators catch verification errors a strong single-agent
baseline misses — including reconciliation, bounded re-investigation,
human review, security controls, observability infrastructure, and
CI/CD, all built and verified against a documented evaluation
methodology. Full honest accounting of scope and known limitations:
[`docs/limitations.md`](docs/limitations.md).

Repo: [github.com/ankkaush/vendor-due-diligence](https://github.com/ankkaush/vendor-due-diligence) (public).

A portfolio system that helps a human reviewer determine which vendor claims
in a due-diligence evidence package (security questionnaire, SOC-style
report, DPA, privacy policy, AI/model documentation, subprocessor list,
contract/SLA) are **supported**, **contradicted**, **unverified**, or
**ambiguous** — with every conclusion traceable back to a specific document
and location.

This is not a chatbot, not a RAG assistant, and not an autonomous approval
system. The AI never approves or rejects a vendor. A human always does.

## The technical thesis

The central question this project is built to answer, not assume:

> Do independently executed, domain-scoped AI investigators — isolated from
> each other's context and conclusions — catch verification errors that a
> strong single-agent baseline, given the same evidence, misses? At what
> cost?

Two domain investigators (Security; Privacy/AI-Governance) run independently
under a deterministic orchestrator that enforces their context boundaries at
the data-access level, not by instruction. Their findings are reconciled
deterministically first, escalated to bounded AI adjudication only where
needed, and always finalized by a human reviewer. If the multi-agent
architecture doesn't earn its complexity against a genuinely strong
single-agent baseline, the architecture gets simplified — that comparison is
a designed, pre-registered experiment (see [`docs/evaluation.md`](docs/evaluation.md)
and [ADR-006](docs/decisions/ADR-006-gate6-methodology.md)), not a foregone conclusion.

## Results: Gate 6

Gate 6 is the pre-registered decision point: does the multi-agent
architecture earn its complexity against the single-agent baseline,
within a locked cost/latency tolerance? The result, in the order it
actually happened:

1. **The first real reconciliation run found a genuine regression.**
   `cross_domain_conflict` recovery — the specific, structural gap
   domain-isolated investigators cannot close alone — hit the target
   decisively (66.7%→100%). But the secondary criterion (no more than a
   5-point regression elsewhere) failed by 8 points, against the
   pre-registered threshold.
2. **Root-caused, not rationalized.** Two specific defects in the
   reconciliation layer: semantic adjudication over-triggering and
   unconditionally overwriting a correct label, and bounded
   re-investigation resolving a conflict the evaluation set deliberately
   designed to be unresolvable. Neither is a property of the
   independent-investigation architecture itself.
3. **Fixed and re-verified for real.** Confidence-gated adjudication (a
   low-confidence flag no longer silently overwrites a finding) and a
   document-grounding constraint on re-investigation — fake-tested at
   zero cost first, then re-run for real under explicit cost review.
4. **Result: all four pre-registered criteria pass.**
   `cross_domain_conflict` recovery stays decisive (66.7%→100%); the
   secondary tolerance now passes with margin (+1.3pt vs. a 5pt limit);
   cost and latency land near 1.5–1.6× the baseline, inside the 2.5×/3×
   ceilings.
5. **Reported with the same rigor the finding itself required.** The two
   cases used to diagnose the defects are excluded from being counted as
   independent confirmation of the fix — the aggregate clearing with
   margin across all matched claims, and a previously-undiagnosed case
   independently triggering the new safeguard correctly, are what the
   "cleared" verdict actually rests on.

Full methodology, pre-registration, and the complete honest accounting
of this result: [ADR-006](docs/decisions/ADR-006-gate6-methodology.md)
and [`docs/evaluation.md`](docs/evaluation.md). Total real API spend
across the whole evaluation: **$0.424 of a hard $0.50 ceiling**
(ADR-009) — never exceeded.

## Architecture

Evidence flows through a deterministic state machine
(`app/state_machine.py`), not an LLM-driven loop: intake → validation →
document classification → two independent investigators, each seeing
only its own domain's documents (security-boundary enforced at the
data-access level, ADR-007, not by prompt instruction) → deterministic
reconciliation (schema-level diff first) → bounded semantic adjudication
and re-investigation only where deterministic comparison can't resolve
a conflict → mandatory human review → an append-only finalized record.

Every conclusion is traceable back to a specific document and location
(`docs/data-model.md`'s evidence chain: Claim → EvidenceItem →
SourceDocument → Finding → VerificationStatus → HumanDecision). Backend
is Python/FastAPI with SQLAlchemy/Alembic over Postgres; the frontend is
server-rendered Jinja2 — no separate frontend build or framework,
because the frontend isn't this project's technical thesis. Full design:
[`docs/architecture.md`](docs/architecture.md).

## Security engineering

The threat model (`docs/threat-model.md`) was written before any
application code, not reverse-engineered after — trust boundaries,
assets, and a threat/mitigation/phase table were the spec every later
phase had to satisfy. That table was then audited row by row against a
real, named test (not re-asserted from memory): 30 threat rows checked,
most already covered by tests written for other reasons, seven genuine
gaps found and closed — including indirect prompt injection via document
metadata, SQL injection run with real adversarial payloads through the
actual query path, cross-case data isolation at the persisted-query
layer, and failed-login rate limiting.

Concretely: CSRF tokens on every state-changing form, Jinja2
autoescaping verified against a real `<script>` payload (not just
configured), UUID primary keys against enumeration, append-only audit
and human-review tables enforced by database trigger (not application
convention), structured-output schema validation on every LLM call, and
a documented secrets/incident-response policy. All of it runs in CI on
every push, against a real Postgres, not a mock.

## Human review workflow

A human reviewer is the sole decision authority — the AI never
approves or rejects a vendor. The review UI shows, per case: every
source document, every extracted claim grouped by domain with its
verification status and rationale, and every conflict reconciliation
found, with the resolution rationale a human can agree or disagree
with. A review decision (approved / rejected / conditional / needs more
info, with optional per-finding overrides) is CSRF-protected, requires
authentication, and is idempotent under a concurrent duplicate
submission — finalizing a case reuses the same guarded state-transition
mechanism proven under real concurrent threads elsewhere in the system.

## Lessons learned

- **Pre-registration discipline caught a result that looked fine and
  wasn't.** Locking the Gate 6 threshold before the deciding run existed
  is what turned "the aggregate number went up" into "the aggregate
  number went up but a specific, pre-declared criterion actually
  failed" — the gap between those two readings is exactly where a less
  disciplined evaluation would have shipped a false positive.
- **Mock-first, cost-gated development (ADR-009) made aggressive
  iteration safe.** Every agent, every reconciliation path, every
  security control was built and fully tested against fakes before a
  single real API call — real spend only ever bought new evidence, never
  debugging.
- **Real runs surface bugs fake-tested code cannot.** The reconciliation
  regression only existed once real model output was reconciled for
  real; no unit test against a scripted fake could have produced it,
  because the bug was in how genuinely variable model behavior
  interacted with the reconciliation logic, not in the logic in
  isolation.
- **CI catches what "it works on my machine" can't.** A real import bug
  — invisible across dozens of successful local test runs — surfaced
  the first time this repository's own CI actually executed the suite,
  because local runs and CI invoked the test runner in two subtly
  different ways. Fixed the same day it was found.
- **Deterministic-first design paid for itself.** Routing conflict
  detection through a cheap, exact schema-level diff before ever calling
  an LLM meant the expensive, fuzzy step (semantic adjudication) only
  ever had to handle what genuinely needed judgment — and confining the
  later confidence-gating fix to that one layer, rather than the
  deterministic pass, kept the fix small and precisely targeted.

## Why this exists

This is a solo AI/GenAI engineering portfolio project — built for learning,
demonstrated engineering judgment, and interview discussion. It is
deliberately **not** a SaaS product: no multi-tenancy, no billing, no
product roadmap. It is one real piece of engineering, built with the same
seriousness as a production system, that a company could plausibly plug into
an internal vendor-review workflow — real evaluated model behavior, real
tests, real CI, not a demo that only works in a notebook.

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | System design, data flow, tech stack, state machine |
| [`docs/security.md`](docs/security.md) | Secret management, repo hygiene, incident procedure |
| [`docs/threat-model.md`](docs/threat-model.md) | Assets, trust boundaries, threats, mitigations |
| [`docs/data-model.md`](docs/data-model.md) | Entities, evidence provenance chain, lifecycle |
| [`docs/agent-boundaries.md`](docs/agent-boundaries.md) | How agent independence is technically enforced |
| [`docs/evaluation.md`](docs/evaluation.md) | Ground-truth dataset, metrics, Gate 6 methodology |
| [`docs/observability.md`](docs/observability.md) | Tracing, cost tracking, redaction policy |
| [`docs/testing.md`](docs/testing.md) | Test strategy across unit/integration/agent/security/e2e |
| [`docs/deployment.md`](docs/deployment.md) | Deployment target and production hygiene |
| [`docs/failure-modes.md`](docs/failure-modes.md) | Known risks and how they're mitigated |
| [`docs/limitations.md`](docs/limitations.md) | Full honest accounting of scope and known limitations |
| [`docs/decisions/`](docs/decisions/) | ADRs for every architecturally significant decision |

## Local development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
cp .env.example .env   # then fill in real values — never commit .env

docker compose up -d          # isolated local Postgres, port 5437
alembic upgrade head          # apply the schema
pytest tests/                 # 189 tests: schema, intake, parsing, state machine, agents, boundaries, reconciliation, web, security

# Optional: seed a few real cases (from already-executed real API output,
# zero new spend) so the review UI has something to show:
python -m scripts.seed_demo_case
uvicorn app.web.main:app --reload   # http://localhost:8000/cases, basic auth from .env
```

`pre-commit install` wires up secret scanning (gitleaks) and linting to run
on every commit. This is not optional for this repository — see
[`docs/security.md`](docs/security.md).

The local Postgres container is dev/test only, isolated by container name
and port from anything else on the machine — the production target is
Supabase ([ADR-005](docs/decisions/ADR-005-deployment-target.md)).

## License

MIT — see [`LICENSE`](LICENSE). All evidence documents used in development
and evaluation are synthetic. No real vendor, customer, or personal data is
used anywhere in this repository.
