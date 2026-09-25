# Vendor Due-Diligence & Evidence Verification

**Status (2026-09-25): all 13 planned phases complete or honestly
closed out. Gate 6 — the core technical thesis — is cleared by real,
re-verified evidence. The one thing not true yet is a live deployed
URL. Full account: [`docs/limitations.md`](docs/limitations.md).**

| | |
|---|---|
| **Core hypothesis (Gate 6)** | **Cleared.** Independent investigation + reconciliation recovers `cross_domain_conflict` decisively (66.7%→100%) within cost/latency budget — found regressed on the first real run, root-caused to two reconciliation-layer bugs, fixed, re-verified. [ADR-006](docs/decisions/ADR-006-gate6-methodology.md) |
| **Real API spend** | $0.424 of a hard $0.50 ceiling (ADR-009), across 6 real runs. Never exceeded. |
| **Tests** | 189 passing, real Postgres + `FakeLLMClient` (zero-cost), all in CI |
| **Human review UI** | Built, tested, working — real cases, real decisions, real DB |
| **Security** | Every `threat-model.md` §3 row checked against a named test |
| **CI/CD** | GitHub Actions, green, no secrets needed |
| **Deployment** | **Not live.** Supabase DB is real; Render deploy attempted for real and currently blocked on an IPv4/IPv6 infrastructure mismatch, fix identified, not yet confirmed. [`docs/deployment.md`](docs/deployment.md) |
| **Live upload → pipeline** | Not built — demo cases are seeded from already-executed real output, not a live run |

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

## Why this exists

This is a solo AI/GenAI engineering portfolio project — built for learning,
demonstrated engineering judgment, and interview discussion. It is
deliberately **not** a SaaS product: no multi-tenancy, no billing, no
product roadmap. It is one real automation, built with the same
seriousness as a production system, that a company could plausibly plug into
an internal vendor-review workflow — real evaluated model behavior, real
tests, real CI, a real (if not yet live) deployment target, not a demo
that only works in a notebook.

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
and port from anything else on the machine — production uses Supabase
([ADR-005](docs/decisions/ADR-005-deployment-target.md)).

## License

MIT — see [`LICENSE`](LICENSE). All evidence documents used in development
and evaluation are synthetic. No real vendor, customer, or personal data is
used anywhere in this repository.
