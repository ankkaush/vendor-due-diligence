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

## Execution note

The Supabase half of this decision was executed for real: project
`vendor-due-diligence` (region `us-east-1`, free tier, $0/month) was
provisioned in the account's existing organization. Schema is applied
via `render.yaml`'s `buildCommand: ... && alembic upgrade head` at
deploy time, not as a separate manual step (`preDeployCommand` would be
cleaner but isn't available on Render's free tier).

`render.yaml` and every piece of required production hygiene (health
check, CORS, security headers, auth rate limiting) are built and
tested — see `deployment.md` for the full target description and
runbook.
