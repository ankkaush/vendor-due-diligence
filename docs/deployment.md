# Deployment

**Status (2026-09-25): not live. Real progress, honestly short of the
goal.** The Supabase database is real (below). A Render Blueprint was
created from the real GitHub repo and `render.yaml`, and the first
deploy attempt was made — for real, in the account owner's own Render
account, with me walking through it live. It **failed**: Supabase's
direct-connection host resolves to an IPv6 address in this project's
region, and Render's outbound network can't reach it
(`OperationalError: ... Network is unreachable`). The fix (Supabase's
connection pooler, which is IPv4-reachable) was identified and handed
off, but not confirmed working — the account owner chose to pause here
rather than push through it in this session. See "What's actually true
right now" below and `limitations.md` for the unvarnished summary.

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

## Runbook

Steps 1–3 are done for real (repo pushed, Blueprint created). Step 4 is
where it currently stands — the fix is identified, not yet confirmed.

1. ~~Push this repo to GitHub.~~ Done: [github.com/ankkaush/vendor-due-diligence](https://github.com/ankkaush/vendor-due-diligence)
   (public, per `security.md`'s stated design).
2. ~~Create a Render Blueprint from the repo.~~ Done — `render.yaml`
   detected automatically, `sync: false` variables prompted for and
   filled in (`APP_BASE_URL` set to a best-guess value before the real
   one was assigned, per the note below; `REVIEWER_USERNAME`/
   `REVIEWER_PASSWORD` set to real values, not the `.env.example`
   defaults; `ANTHROPIC_API_KEY`/Langfuse/Sentry left blank — nothing
   deployed calls them yet).
3. ~~First deploy attempt.~~ **Failed.** `DATABASE_URL` initially used
   Supabase's *direct* connection
   (`db.zkzlxigjicusifibpwvc.supabase.co:5432`) — the original guidance
   here reasoned this would be simpler than a pooler and avoid
   prepared-statement quirks, which turned out to be the wrong tradeoff
   to have prioritized: that host resolves to an **IPv6-only** address
   in this project's region, and Render's build environment has no IPv6
   egress. The build failed with
   `psycopg.OperationalError: ... Network is unreachable`, addressed to
   a `2600:...` literal.
4. **Not yet done: switch `DATABASE_URL` to Supabase's session pooler**,
   which is IPv4-reachable. In Supabase's dashboard → the project →
   **Connect** button → **Session pooler** tab, copy the shown
   connection string (username becomes `postgres.zkzlxigjicusifibpwvc`,
   host becomes something like `aws-0-us-east-1.pooler.supabase.com`,
   port stays `5432`), prefix the scheme with `+psycopg` as before, and
   update the `DATABASE_URL` env var in Render's dashboard (Environment
   tab) — saving it triggers an automatic redeploy. This is the single
   next step to get a live deployment.
5. **Also outstanding: `APP_BASE_URL`.** It was set to a guessed value
   (`https://vendor-due-diligence.onrender.com`) before Render assigned
   the real one, because — this app being plain server-rendered pages
   and form POSTs, never cross-origin `fetch`/XHR — CORS being
   temporarily wrong doesn't block basic use. Once a deploy succeeds,
   confirm the real assigned URL and correct this value if it differs.
6. **Verify, once step 4 succeeds:**
   - `curl https://<your-app>.onrender.com/healthz` → `{"status":
     "healthy"}` — a real DB round-trip, not just "the process started."
   - Load `/cases` in a browser — Basic auth should prompt, and the real
     credentials from step 2 should work.
   - Optionally, run `python -m scripts.seed_demo_case` locally against
     the production `DATABASE_URL` (via the session pooler) to put real
     (already-paid-for, zero new API cost) demo cases in front of the
     deployed review UI — the same script Phase 9 used locally.

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

## What's actually true right now

- Real, live, verified: the Supabase Postgres project, the public GitHub
  repo, CI green on every push, the Render Blueprint and its configured
  env vars.
- Attempted for real and currently failing: the actual running,
  reachable web service. One concrete, diagnosed, IPv4/IPv6 network
  incompatibility stands between here and a live URL.
- Not a code defect — every piece of application code involved
  (`render.yaml`, `app/config.py`, `app/web/main.py`) behaved exactly as
  designed. The gap is purely infrastructure-compatibility, found only
  by actually trying to deploy, not by anything reviewable in advance.

## Auth

Single-reviewer basic auth for the review interface. No multi-user roles or
permission system — this is a portfolio automation with one reviewer
persona, not an org with an RBAC problem.

## Explicitly not needed (see `limitations.md`)

Kubernetes, microservices, Redis, Kafka, Celery, Temporal, any event bus,
multi-tenant auth, custom backup infrastructure. None of these solve a
problem this project actually has.
