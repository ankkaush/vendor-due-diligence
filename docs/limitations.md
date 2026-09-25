# Limitations

**Status: seeded with known-up-front limitations at design time. Finalized
honestly in Phase 13 against what was actually built, including whatever
Gate 6 concludes.**

These are deliberate scope decisions, not gaps discovered late:

- **Synthetic data only.** No real vendor, customer, or personal data is
  used anywhere — evaluation results describe performance on a constructed
  dataset, not a claim about real-world vendor risk assessment.
- **No live external evidence retrieval.** Investigators reason only over
  the uploaded evidence package; there is no web search, no external API
  cross-referencing, no live certificate/registry lookups in the MVP.
- **No OCR / scanned-PDF support.** Only text-extractable PDF, DOCX, TXT,
  and Markdown are supported.
- **Single LLM provider (Anthropic).** No multi-provider comparison or
  fallback.
- **Hard $0.50 total API budget for the entire project (ADR-009).** Model
  choice for the baseline and the multi-agent system is made from measured
  cost at smoke-test time, not the most capable model available — this is
  a disclosed resource constraint, not a claim that a more expensive model
  would perform differently. The single-agent baseline's "strength" refers
  to its architecture, prompt/context design, evidence-grounding rigor,
  and evaluation methodology, all of which are independent of model tier
  and held to the same standard regardless of budget.
- **Single-reviewer auth model.** No multi-user roles, permissions, or
  organizational workflow beyond one reviewer persona.
- **No live upload-to-review pipeline yet (as of Phase 9).** The review UI
  (`app/web/`) renders real cases, but nothing yet wires a document upload
  through the full live pipeline (investigate → reconcile → synthesize)
  end to end over HTTP — that orchestrator is a separate, larger piece of
  work needing its own ADR-009 cost review before any real spend.
  Phase 9's demo cases are seeded (`scripts/seed_demo_case.py`) from
  already-executed, already-paid real Phase 7/8 output, not a live run.
- **Not multi-tenant, not a SaaS product.** No billing, no account
  management, no product roadmap.
- **Not actually deployed yet (as of Phase 12).** The Supabase database
  is real (project `vendor-due-diligence`, created 2026-09-25 —
  `deployment.md`), but the Render half of deployment requires an
  account I have no access to and can't create — a genuine agent
  constraint, not a technical one. `render.yaml`, the health check,
  CORS, security headers, and auth rate limiting are all built and
  tested; `deployment.md`'s runbook is exactly what's left for the
  account owner to execute.
- **The multi-agent architecture may not be justified by the evidence.**
  Gate 6 is a real test, not a formality — if the strong single-agent
  baseline performs comparably, the shipped architecture reflects that
  finding rather than preserving multi-agent for its own sake. Whatever
  Gate 6 concludes will be reported here plainly.
