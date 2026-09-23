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
