# Vendor Due-Diligence & Evidence Verification

**Status: early build — Phases 6, 7, and 8 complete with real executed
evaluation runs (baseline vs. raw multi-agent vs. reconciled — see
`docs/evaluation.md`). Gate 6's first real check found a genuine
regression, traced to two specific reconciliation-layer defects (not a
flaw in the core independent-investigation hypothesis); both were
fixed, fake-tested, and re-run for real. Gate 6 is now judged
**cleared** against its pre-registered threshold (ADR-006) — cross-domain
conflict recovery is a decisive 66.7%→100%, and the secondary
regression tolerance now passes with margin (+1.3pt vs. a 5pt limit) —
with an explicit experimental-integrity caveat, since the two cases
that diagnosed the bugs also informed the fix: see
[ADR-006](docs/decisions/ADR-006-gate6-methodology.md)'s "Gate 6
decision, updated 2026-09-24 after the fix rerun" section for the full,
honest analysis of what is and isn't independent confirmation. **Phase 9
(human review UI) is built and tested** — FastAPI + Jinja2, single-reviewer
auth, CSRF-protected review submission, real cases seeded from
already-executed real output (zero new spend). **Phase 10 (security test
audit + observability) is complete** — every `threat-model.md` §3 row is
checked against a real test (section 7's audit table), seven genuine
gaps found and closed, three honestly recorded as open and deferred to
Phase 11/12 where they were always scoped to belong; Langfuse/Sentry
integration (`app/observability.py`) is built and tested against a fake
client, no account required. **Phase 11 (CI/CD) is complete** —
`.github/workflows/ci.yml` runs the full suite against a real Postgres
service container plus a migration up/down/up cycle on every push/PR,
and the same pre-commit hooks (gitleaks included) run as their own job;
no secret is referenced anywhere in the workflow, since nothing it runs
ever needs one (ADR-009). 183 tests. $0.424 of $0.50 spent; no further
real API spend is planned. No live upload-to-pipeline HTTP flow yet —
see `docs/limitations.md`.**

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

## Why this exists

This is a solo AI/GenAI engineering portfolio project — built for learning,
demonstrated engineering judgment, and interview discussion. It is
deliberately **not** a SaaS product: no multi-tenancy, no billing, no
product roadmap. It is one real, deployed automation, built with the same
seriousness as a production system, that a company could plausibly plug into
an internal vendor-review workflow.

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
| [`docs/limitations.md`](docs/limitations.md) | What this system deliberately does not do |
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
pytest tests/                 # 183 tests: schema, intake, parsing, state machine, agents, boundaries, reconciliation, web, security

# Optional: seed a few real cases (from already-executed real API output,
# zero new spend) so the review UI has something to show:
python -m scripts.seed_demo_case
uvicorn app.web.main:app --reload   # http://localhost:8000/cases, basic auth from .env
```

`pre-commit install` wires up secret scanning (gitleaks) and linting to run
on every commit. This is not optional for this repository — see
[`docs/security.md`](docs/security.md).

The local Postgres container is dev/test only, isolated by container name
and port from anything else on the machine — production uses Supabase
([ADR-005](docs/decisions/ADR-005-deployment-target.md)).

## License

MIT — see [`LICENSE`](LICENSE). All evidence documents used in development
and evaluation are synthetic. No real vendor, customer, or personal data is
used anywhere in this repository.
