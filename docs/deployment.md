# Deployment

**Status: deployment target defined and provisioned (ADR-005); the
application is built with full production hygiene (below) and is ready
to deploy via the included Blueprint. This document is the reference
for how the system is meant to run in production.**

## Target

- **Application:** Render (FastAPI backend + server-rendered Jinja2/HTMX
  frontend, same app — no separate frontend deployment, decision #4/#8).
  Blueprint: [`render.yaml`](../render.yaml).
- **Database:** Supabase Postgres. Project `vendor-due-diligence`
  (region `us-east-1`, free tier). Schema is applied via
  `buildCommand: pip install -e . && alembic upgrade head` at deploy
  time, not as a separate manual step, so `alembic_version` stays the
  single source of truth for what's been applied. (`preDeployCommand`
  would be the cleaner place for this — it runs after the build, before
  the new version serves traffic — but it isn't available on Render's
  free tier.)
- **Migrations:** Alembic, run against production on deploy.

## Runbook

1. **Push the repo to GitHub** and connect it in Render as a Blueprint.
   Render detects `render.yaml` automatically and prompts once for every
   `sync: false` variable:

   | Variable | Value |
   |---|---|
   | `APP_BASE_URL` | The service's own URL (e.g. `https://vendor-due-diligence.onrender.com`) — CORS is locked to exactly this string (`app/web/main.py`), no trailing slash |
   | `DATABASE_URL` | Supabase's **session pooler** connection string (Supabase dashboard → project → Connect → "Session pooler" tab), with the scheme changed to `postgresql+psycopg://` — e.g. `postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`. Use the pooler rather than the direct connection: Supabase's direct-connection host can resolve to an IPv6-only address depending on region, which some hosts (including Render's build environment) can't route to — the pooler is IPv4-reachable and avoids that class of issue entirely. |
   | `ANTHROPIC_API_KEY` | Real key, for whenever a live orchestrator exists to use it (`limitations.md` — nothing deployed calls it yet) |
   | `REVIEWER_USERNAME` / `REVIEWER_PASSWORD` | Real credentials for the one reviewer persona — not the local dev defaults in `.env.example` |
   | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Optional — leave blank to keep tracing a no-op (`observability.md`) |
   | `SENTRY_DSN` | Optional — leave blank to keep error tracking a no-op |

   `APP_SECRET_KEY` is not prompted for — `generateValue: true` has
   Render generate a real random 256-bit value itself.
2. **Deploy.** Render's build step runs `pip install -e .` then
   `alembic upgrade head` against the database, then starts `uvicorn`.
3. **Verify:**
   - `curl https://<your-app>.onrender.com/healthz` → `{"status":
     "healthy"}` — a real DB round-trip, not just "the process started."
   - Load `/cases` in a browser — Basic auth should prompt, and the
     reviewer credentials from step 1 should work.
   - Optionally, run `python -m scripts.seed_demo_case` locally against
     the production `DATABASE_URL` to put real (already-paid-for, zero
     new API cost) demo cases in front of the deployed review UI — the
     same script used for local development.

## Required production hygiene

| Item | Status |
|---|---|
| Health check endpoint | `GET /healthz`, real DB round-trip (`app/web/routes.py`) |
| Structured env config | `pydantic-settings` (`app/config.py`) |
| Secrets via Render's secret manager | `render.yaml`'s `sync: false` / `generateValue: true` — no secret is ever committed |
| HTTPS by default | Render's platform default |
| Security headers, incl. HSTS | `app/web/main.py`'s `SecurityHeadersMiddleware` — HSTS is conditional on `APP_ENV=production`, set by `render.yaml` |
| CORS locked to the app's own origin | `allow_origins=[settings.APP_BASE_URL]`, never a wildcard |
| Rate limiting on the auth boundary | `app/web/ratelimit.py` — failed-login throttling, in-memory, per-IP |
| Upload size limits, app level | `MAX_UPLOAD_BYTES` (`app/intake.py`) |
| Upload size limits, proxy level | No live upload HTTP endpoint exists yet for a proxy-level cap to apply to — nothing to configure until that endpoint exists (`limitations.md`) |
| Dependabot-driven dependency updates | `.github/dependabot.yml` |
| Supabase's managed automatic backups | Platform default; nothing for this app to configure |

## Auth

Single-reviewer basic auth for the review interface. No multi-user roles or
permission system — this is a portfolio automation with one reviewer
persona, not an org with an RBAC problem.

## Explicitly not needed (see `limitations.md`)

Kubernetes, microservices, Redis, Kafka, Celery, Temporal, any event bus,
multi-tenant auth, custom backup infrastructure. None of these solve a
problem this project actually has.
