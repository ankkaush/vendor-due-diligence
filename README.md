# Vendor Due-Diligence & Evidence Verification

**Status: early build — Phase 1 (repository/security foundation) in progress. No application code yet.**

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
```

`pre-commit install` wires up secret scanning (gitleaks) and linting to run
on every commit. This is not optional for this repository — see
[`docs/security.md`](docs/security.md).

## License

MIT — see [`LICENSE`](LICENSE). All evidence documents used in development
and evaluation are synthetic. No real vendor, customer, or personal data is
used anywhere in this repository.
