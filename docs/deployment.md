# Deployment

**Status: target approved (ADR-005). Phase 12, split honestly across what
I can do and what only the account owner can: the Supabase project is
created for real (below); Render's half is prepared — `render.yaml`,
health check, CORS, security headers, and auth rate limiting are all
built and tested — but not yet executed, because I have no Render
account access and can't create one (dedicated agent constraint, not a
technical one). The runbook below is exactly what's left to run.**

## Target

- **Application:** Render (FastAPI backend + server-rendered Jinja2/HTMX
  frontend, same app — no separate frontend deployment, decision #4/#8).
  Blueprint: [`render.yaml`](../render.yaml).
- **Database:** Supabase Postgres. **Created 2026-09-25**: project
  `vendor-due-diligence`, ref `zkzlxigjicusifibpwvc`, region `us-east-1`,
  free tier ($0/month), in the same Supabase organization as the
  account's other projects. Schema not yet applied — that happens via
  `buildCommand: pip install -e . && alembic upgrade head` on first
  deploy (below), not as a separate manual step, so `alembic_version`
  stays the single source of truth for what's been applied.
  `preDeployCommand` would be the cleaner place for this — it runs after
  the build, before the new version serves traffic — but Render's free
  tier rejects it outright ("pre-deploy command is not supported for
  free tier services"), a real platform constraint hit live at Blueprint
  creation, not found by reading docs in advance.
- **Migrations:** Alembic, run against production on deploy.

## Runbook: what's left to do (Render account owner only)

1. **Push this repo to GitHub** (no remote is configured yet — this
   repo has been entirely local until now).
2. **Get the Supabase DB password.** The project above was created via
   the Supabase management API, which does not return the auto-generated
   database password (by design — Supabase never exposes it outside the
   dashboard once set). In the [Supabase dashboard](https://supabase.com/dashboard/project/zkzlxigjicusifibpwvc) →
   Project Settings → Database → Connection string, either copy the
   password shown there or reset it. Use the **direct connection**
   (`db.zkzlxigjicusifibpwvc.supabase.co:5432`), not the pooled
   (PgBouncer) one — this is one long-running service, not a serverless
   fan-out, so the direct connection is simpler and avoids
   prepared-statement quirks some poolers have with SQLAlchemy.
3. **In Render, create a new Blueprint** from the GitHub repo. Render
   detects `render.yaml` automatically and prompts for every `sync:
   false` variable once, at creation:

   | Variable | Value |
   |---|---|
   | `APP_BASE_URL` | The service's own URL, e.g. `https://vendor-due-diligence.onrender.com` — Render shows this before you finish creating the service; CORS is locked to exactly this string (`app/web/main.py`), so it must match exactly, no trailing slash |
   | `DATABASE_URL` | `postgresql+psycopg://postgres:<password from step 2>@db.zkzlxigjicusifibpwvc.supabase.co:5432/postgres` — note the `+psycopg` (the app's SQLAlchemy driver), which Supabase's own dashboard string won't include |
   | `ANTHROPIC_API_KEY` | Real key, for whenever a live orchestrator exists to use it (`limitations.md` — nothing calls it yet) |
   | `REVIEWER_USERNAME` / `REVIEWER_PASSWORD` | Real credentials for the one reviewer persona — not the local dev defaults in `.env.example` |
   | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Optional — leave blank to keep tracing a no-op (`observability.md`) |
   | `SENTRY_DSN` | Optional — leave blank to keep error tracking a no-op |

   `APP_SECRET_KEY` is not prompted for — `generateValue: true` has
   Render generate a real random 256-bit value itself.
4. **Deploy.** Render's build step runs `pip install -e .` then
   `alembic upgrade head` against the real Supabase database (this is
   the first time the schema is actually applied there), then starts
   `uvicorn`.
5. **Verify**, in order:
   - `curl https://<your-app>.onrender.com/healthz` → `{"status":
     "healthy"}` — a real DB round-trip, not just "the process started."
   - Load `/cases` in a browser — Basic auth should prompt, and the real
     credentials from step 3 should work.
   - Optionally, run `python -m scripts.seed_demo_case` locally against
     the production `DATABASE_URL` to put real (already-paid-for, zero
     new API cost) demo cases in front of the deployed review UI — the
     same script Phase 9 used locally.

## Required production hygiene

| Item | Status |
|---|---|
| Health check endpoint | Built and tested — `GET /healthz`, real DB round-trip (`app/web/routes.py`) |
| Structured env config | `pydantic-settings` (`app/config.py`), since Phase 4 |
| Secrets via Render's secret manager | `render.yaml`'s `sync: false` / `generateValue: true` — no secret is ever committed |
| HTTPS by default | Render's platform default; not this app's responsibility to configure |
| Security headers, incl. HSTS | Built and tested (`app/web/main.py`'s `SecurityHeadersMiddleware`) — HSTS is conditional on `APP_ENV=production`, set by `render.yaml` |
| CORS locked to the app's own origin | Built and tested — `allow_origins=[settings.APP_BASE_URL]`, never a wildcard |
| Rate limiting on the auth boundary | Built and tested (`app/web/ratelimit.py`) — closes threat-model.md 3.6.3, the one row Phase 10 left open for this phase |
| Upload size limits, app level | Built since Phase 5 (`MAX_UPLOAD_BYTES`, `app/intake.py`) |
| Upload size limits, proxy level | **Still open** — there's no live upload HTTP endpoint yet for a proxy-level cap to apply to (`limitations.md`); nothing to configure until that endpoint exists |
| Dependabot-driven dependency updates | Configured since Phase 1 (`.github/dependabot.yml`) |
| Supabase's managed automatic backups | Platform default on the created project; nothing for this app to configure |

## Auth

Single-reviewer basic auth for the review interface. No multi-user roles or
permission system — this is a portfolio automation with one reviewer
persona, not an org with an RBAC problem.

## Explicitly not needed (see `limitations.md`)

Kubernetes, microservices, Redis, Kafka, Celery, Temporal, any event bus,
multi-tenant auth, custom backup infrastructure. None of these solve a
problem this project actually has.
