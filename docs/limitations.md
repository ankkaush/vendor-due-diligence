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
- **Single-reviewer auth model.** No multi-user roles, permissions, or
  organizational workflow beyond one reviewer persona.
- **Not multi-tenant, not a SaaS product.** No billing, no account
  management, no product roadmap.
- **The multi-agent architecture may not be justified by the evidence.**
  Gate 6 is a real test, not a formality — if the strong single-agent
  baseline performs comparably, the shipped architecture reflects that
  finding rather than preserving multi-agent for its own sake. Whatever
  Gate 6 concludes will be reported here plainly.
