# ADR-005: Render + Supabase, server-rendered UI, no separate frontend deployment

**Status:** Accepted
**Date:** 2026-09-23

## Context

This is a solo portfolio automation, not a SaaS product. Deployment needs to
be real (not "works locally") without introducing infrastructure that
exists only to look senior.

## Decision

- Backend + reviewer UI: Render, as a single FastAPI application serving
  server-rendered Jinja2/HTMX pages (decision #4) — no separate frontend
  deployment or framework.
- Database: Supabase Postgres.
- Migrations: Alembic, run against production on deploy.

## Rationale

Jinja2/HTMX was chosen over Next.js because the frontend is not this
project's technical thesis — the engineering story is ingestion → evidence →
independent investigation → reconciliation → conflict handling →
provenance → evaluation → human review. A single deployed app with no
separate frontend build/deploy pipeline keeps deployment surface
proportional to what the project is actually demonstrating.

## Consequences

- No CDN/edge deployment story, no client-side framework — acceptable,
  matches the "no unnecessary infrastructure" principle governing this
  project.
- Kubernetes, Redis, Kafka, Celery, Temporal, and microservices remain
  explicitly out of scope (see `limitations.md`) — case volume for a
  portfolio system does not create a problem any of these solve.

## Execution note (2026-09-25)

Phase 12 executed the Supabase half of this decision for real: project
`vendor-due-diligence` (ref `zkzlxigjicusifibpwvc`, region `us-east-1`,
free tier, $0/month — confirmed via the Supabase management API's cost
check before creation) in the account's existing organization. Schema
is applied via `render.yaml`'s `buildCommand: ... && alembic upgrade
head` on first deploy, not as a separate manual step (`preDeployCommand`
would be cleaner but Render's free tier rejects it — hit live during
Blueprint creation, corrected the same day).

The Render half was not executed by me — I have no Render account access and
cannot create third-party accounts on the user's behalf (an agent
constraint, not a technical one, distinct from anything this ADR
decided). `render.yaml` and every piece of required production hygiene
(health check, CORS, security headers, auth rate limiting) are built
and tested; `deployment.md`'s runbook is what's left for the account
owner to execute. See `limitations.md`.
