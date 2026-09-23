# Security

**Status: baseline established (Phase 1). Expanded in Phase 10 with the full security test suite.**

This repository is public from its first commit. Security hygiene starts
before application code, not after.

## Secrets

- No API keys, tokens, or credentials in source, prompts, test fixtures,
  logs, screenshots, or the README — ever.
- `.env` holds real local secrets and is gitignored. `.env.example`
  documents variable names only, with empty/placeholder values, and is the
  only env file committed.
- In production (Render), secrets are set via the platform's secret manager,
  not committed anywhere.
- `gitleaks` runs as a pre-commit hook (`.pre-commit-config.yaml`) and blocks
  a commit containing a detected secret pattern before it ever reaches git
  history.
- GitHub's secret scanning is automatically active on public repositories;
  Dependabot is configured via `.github/dependabot.yml` for dependency and
  Actions updates.

## If a secret is ever committed

1. **Revoke** the key immediately at the provider (Anthropic, Supabase,
   Langfuse, Sentry, etc.) — do this before anything else.
2. **Rotate** — issue a new key.
3. **Remove** the secret from the current working tree/code.
4. **Assess** whether it's reachable in git history (`git log -p`,
   `gitleaks detect --source .`).
5. **Clean history if required**, using `git filter-repo` (preferred over
   BFG for a small repo), then force-push with an explicit note that this
   rewrites public history — a deliberate, rare action, never a reflex.

Revocation (step 1) happens regardless of whether history is cleaned — a key
that has ever been pushed to a public repo must be treated as compromised
even if it's later removed from history.

## Untrusted documents

Every uploaded vendor evidence document is treated as **untrusted data**,
never as instructions. This is enforced structurally, not by asking the
model nicely:

- Document text enters an LLM call only inside a clearly delimited "evidence
  content" block within a fixed system prompt the document cannot alter.
- Agent output is constrained to a strict schema (verification status enum,
  citations, rationale string) — there is no free-text channel through
  which an injected instruction could cause an unintended action.
- Investigator agents have **no tools, no database credentials, and no
  network access** in the MVP (ADR-003). They cannot approve or reject a
  vendor, cannot write to the database, and cannot make external requests.
  Prompt injection has nowhere to escalate to, because there is nothing
  privileged for it to reach.
- Persistence and all side effects belong exclusively to deterministic
  orchestrator code, which only ever consumes schema-validated agent output.

See [`threat-model.md`](threat-model.md) for the full threat/mitigation
table and [`agent-boundaries.md`](agent-boundaries.md) for how independence
between agents is enforced at the data-access level.

## Data handling

- All evidence documents used anywhere in this repository — development,
  testing, and the evaluation dataset — are synthetic. No real vendor,
  customer, or personal data is used at any point.
- Observability traces (Langfuse) redact/truncate document text by default
  — see [`observability.md`](observability.md).
