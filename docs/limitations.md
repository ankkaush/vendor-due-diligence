# Limitations

**Status: finalized (Phase 13, 2026-09-25) against what was actually
built across 12 real implementation phases — not the day-1 speculative
list alone. Split into three honest categories below: deliberate scope
decisions made in advance and never revisited because nothing changed
the reasoning; what Gate 6 actually concluded, since this file promised
to report it plainly either way; and gaps found only by actually
building and, in Phase 12's case, actually trying to deploy — recorded
as real findings, not retroactively smoothed into "always the plan."**

## Deliberate scope decisions (made at design time, still true)

- **Synthetic data only.** No real vendor, customer, or personal data is
  used anywhere — evaluation results describe performance on a constructed
  dataset, not a claim about real-world vendor risk assessment.
- **No live external evidence retrieval.** Investigators reason only over
  the uploaded evidence package; there is no web search, no external API
  cross-referencing, no live certificate/registry lookups.
- **No OCR / scanned-PDF support.** Only text-extractable PDF, DOCX, TXT,
  and Markdown are supported.
- **Single LLM provider (Anthropic).** No multi-provider comparison or
  fallback.
- **Hard $0.50 total API budget for the entire project (ADR-009).**
  Model choice is made from measured cost at smoke-test time, not the
  most capable model available — a disclosed resource constraint, not a
  claim that a more expensive model would perform differently. The
  single-agent baseline's "strength" refers to its architecture,
  prompt/context design, evidence-grounding rigor, and evaluation
  methodology, all independent of model tier. **Final spend: $0.424 of
  $0.50** across six real runs (calibration, baseline, investigators,
  reconciliation × 2, the fix rerun) — never exceeded, never worked
  around.
- **Single-reviewer auth model.** No multi-user roles, permissions, or
  organizational workflow beyond one reviewer persona.
- **Not multi-tenant, not a SaaS product.** No billing, no account
  management, no product roadmap.

## What Gate 6 actually concluded

This file committed to reporting Gate 6's outcome here plainly,
whichever way it went. It went, in order: **regression found, root-caused,
fixed, and re-verified as cleared** — not a clean story, but an honest
one, and the more informative for not being clean.

- The real Phase 8 run (reconciliation, unmodified) found a genuine
  regression against the pre-registered secondary criterion: −8.0 points
  against a 5.0-point tolerance, traced to two specific implementation
  defects (semantic adjudication over-triggering and unconditionally
  overwriting a correct label; bounded re-investigation resolving a
  conflict the ground truth deliberately designed to be unresolvable) —
  not a property of the independent-investigation architecture itself.
- Both defects were fixed (confidence-gated adjudication; a
  document-grounding constraint on re-investigation), fake-tested at
  zero cost, cost-projected, and re-run for real under explicit
  authorization.
- **Result: all four pre-registered ADR-006 criteria pass.**
  `cross_domain_conflict` recovery is decisive (66.7%→100%) — the exact
  structural gap the whole multi-agent architecture exists to close,
  and which domain-isolated investigators structurally cannot close
  alone. The secondary regression tolerance now passes with margin
  (+1.3pt vs. a 5pt limit). Cost and latency both land near 1.5–1.6× the
  baseline, inside the 2.5×/3× ceilings.
- **Stated with the same rigor the finding itself required**: case-01
  and case-07 informed the fix's design, so their individual recovery
  is expected, not independent confirmation. The genuinely independent
  evidence — the pooled aggregate clearing with margin across all 43
  matched claims, `none_clean`'s broad-but-incomplete recovery, and
  case-18 (never part of the diagnosis) correctly triggering the new
  low-confidence path on its own — is what the "cleared" verdict
  actually rests on. Full accounting: [ADR-006](decisions/ADR-006-gate6-methodology.md).

**The honest conclusion**: the core technical thesis — that independently
executed, domain-scoped investigators catch verification errors a
strong single-agent baseline structurally cannot, at acceptable cost —
is supported by real evidence, not assumed. That support required
finding and fixing a real bug in the reconciliation layer first; a
system that had shipped the first (buggy) result without checking it
against the pre-registered criteria would have reported a false
regression. The checking is what makes the "cleared" verdict worth
trusting.

## Gaps found only by building (not known at design time)

- **No live upload-to-review pipeline exists.** The review UI (Phase 9,
  `app/web/`) renders real cases and records real human decisions, but
  nothing wires a document upload through the full live pipeline
  (investigate → reconcile → synthesize → persist) end to end over
  HTTP. Every case in the database was seeded
  (`scripts/seed_demo_case.py`) from already-executed, already-paid
  real Phase 7/8 output — genuine model output, replayed through the
  real persistence code path, but not a live run. Building that
  orchestrator is separate, larger work needing its own ADR-009 cost
  review before any real spend, and was never attempted.
- **Langfuse/Sentry are built and tested but never connected to real
  accounts.** `app/observability.py`'s `TracedLLMClient` and
  `configure_sentry()` are real, tested against a fake client
  (`tests/test_app/test_observability.py`) — but no real Langfuse or
  Sentry credentials were ever set, locally or in production, because
  nothing in this session's actual usage generated a real LLM call or
  application error worth tracing. The redaction policy and the
  never-let-tracing-break-the-call guarantee are verified; what a real
  trace or error report actually looks like in either dashboard is not.
- **The app is not deployed.** Phase 12 got further than "not
  attempted" — a real Supabase database exists, a real Render Blueprint
  was created from the real public repo, and a real first deploy was
  attempted with the account owner driving it live. It failed:
  Supabase's direct-connection host resolves to an IPv6 address in this
  project's region, and Render's build environment has no IPv6 egress —
  a real, diagnosed infrastructure incompatibility, not a code defect.
  The fix (Supabase's IPv4-reachable session pooler) is identified and
  documented; the account owner chose to pause before confirming it
  works. See `deployment.md`'s runbook for exactly where it stands.
- **Rate limiting on an upload endpoint doesn't exist**, because the
  upload endpoint itself doesn't exist. Auth-boundary rate limiting
  (failed-login throttling) does (`app/web/ratelimit.py`, Phase 12).
- **DB connection pooling was never configured.** SQLAlchemy's default
  pool settings are in effect; deployment.md's hygiene table has always
  listed this as open, correctly.
- **The `evidence_requirement` field is a real, if minor, schema/agent
  gap.** `Claim.evidence_requirement` is `NOT NULL` and reused by the
  ground-truth schema (ADR-008), but no agent's tool schema
  (`FINDINGS_INPUT_SCHEMA`) ever asks the model to produce it — found
  while building Phase 9's persistence bridge (`app/persist.py`), and
  persisted as an empty string with that finding recorded in code, not
  silently worked around with a fabricated value.
- **A CI bug shipped and was caught by CI itself, not by review.**
  `pytest tests/` (the bare console script, as CI's own workflow runs
  it) could not import `tests/` or `eval/` — every local run throughout
  this project used `python -m pytest`, which added the working
  directory to `sys.path` as a side effect nothing had verified against
  the other invocation style. Found the first time this repo was
  actually pushed and CI actually ran, fixed the same day
  (`pythonpath = ["."]` in `pyproject.toml`). Recorded here because it's
  a real example of exactly the risk Phase 11 existed to catch — one
  that a purely local, "it works when I run it" verification would
  never have surfaced.
- **Two Dependabot PRs are open, unmerged.** Routine GitHub Actions
  version bumps, opened automatically the moment the repo went public;
  left for the account owner rather than merged unilaterally.

## Explicitly out of scope (see `architecture.md`, ADR-002/003)

Kubernetes, microservices, Redis, Kafka, Celery, Temporal, any event
bus, multi-tenant auth, custom backup infrastructure, live external
tools for agents. None of these solve a problem this project actually
has — case volume for a portfolio system, and a deliberately bounded
threat surface (ADR-003), don't create the conditions any of them
exist to address.
