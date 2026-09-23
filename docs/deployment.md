# Deployment

**Status: approved target (ADR-005). Not yet deployed — Phase 12.**

## Target

- **Application:** Render (FastAPI backend + server-rendered Jinja2/HTMX
  frontend, same app — no separate frontend deployment, decision #4/#8).
- **Database:** Supabase Postgres.
- **Migrations:** Alembic, run against production on deploy.

## Required production hygiene (in scope)

Health check endpoint, structured env config (`pydantic-settings`), secrets
via Render's secret manager, HTTPS by default, CORS locked to the app's own
origin, standard security headers middleware, basic rate limiting on the
upload endpoint, upload size limits enforced at both proxy and app level,
Dependabot-driven dependency updates, reliance on Supabase's managed
automatic backups.

## Auth

Single-reviewer basic auth for the review interface. No multi-user roles or
permission system — this is a portfolio automation with one reviewer
persona, not an org with an RBAC problem.

## Explicitly not needed (see `limitations.md`)

Kubernetes, microservices, Redis, Kafka, Celery, Temporal, any event bus,
multi-tenant auth, custom backup infrastructure. None of these solve a
problem this project actually has.
