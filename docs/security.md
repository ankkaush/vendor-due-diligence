# Security

**Status: baseline established (Phase 1); expanded with concrete
requirements (Phase 2). The full threat/mitigation/phase mapping lives in
[`threat-model.md`](threat-model.md) — this file covers secrets, incident
response, and the hard coding rules that fall out of it.**

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
  history — this was tested against a deliberately planted fake AWS/
  Anthropic-style key during Phase 1 and confirmed working before the first
  real commit was made.
- GitHub's secret scanning is automatically active on public repositories;
  Dependabot is configured via `.github/dependabot.yml`.

## If a secret is ever committed

1. **Revoke** the key immediately at the provider — before anything else.
2. **Rotate** — issue a new key.
3. **Remove** the secret from the current working tree/code.
4. **Assess** whether it's reachable in git history (`git log -p`,
   `gitleaks detect --source .`).
5. **Clean history if required**, using `git filter-repo`, then force-push
   with an explicit note that this rewrites public history — a deliberate,
   rare action, never a reflex.

Revocation (step 1) happens regardless of whether history is cleaned — a key
that has ever been pushed to a public repo is treated as compromised even
after removal from history.

## Untrusted documents

Every uploaded vendor evidence document is treated as **untrusted data**,
never as instructions, enforced structurally:

- Document text enters an LLM call only inside a clearly delimited "evidence
  content" block within a fixed system prompt the document cannot alter.
- Agent output is constrained to a strict schema — there is no free-text
  channel through which an injected instruction could cause an unintended
  action.
- Investigator agents have **no tools, no database credentials, and no
  network access** (ADR-003). Prompt injection has nothing privileged to
  escalate into.
- Untrusted content's reach extends all the way to the review UI: document
  text and LLM-derived rationale can contain literal HTML/script content,
  which is a stored-XSS vector against the reviewer's own browser if ever
  rendered unescaped. See the coding rule below — this is not hypothetical,
  it's the direct consequence of "untrusted data flows through to a
  rendered page."

## Secure coding requirements (hard rules, not per-case judgment calls)

These fall directly out of `threat-model.md` §3 and are binding on the
phases noted:

| Rule | Why | Enforced in |
|---|---|---|
| XML parsing (DOCX) disables external entity resolution and DTD processing | Prevents XXE | Phase 5 |
| No user- or document-derived string is ever interpolated into raw SQL — ORM/parameterized queries only | Prevents SQL injection | Phase 4–5 |
| No user- or document-controlled string is ever passed to a subprocess/shell call | Prevents command injection via crafted filenames | Phase 5 |
| Jinja2 autoescaping stays on everywhere; `\|safe` is never applied to document- or LLM-derived content | Prevents stored XSS in the review UI | Phase 9 |
| Every state-changing form (override, approve/reject/finalize) carries a CSRF token | Prevents CSRF | Phase 9 |
| Externally-referenced entities (`Case`, `EvidenceDocument`, ...) use UUID primary keys, not sequential integers | Reduces ID enumeration even behind auth | Phase 4 |
| Application DB role is least-privilege, never a superuser; Supabase `service_role` key is only used server-side, never referenced by any client-facing template/script | Limits blast radius of a DB credential leak | Phase 4 |
| Every document fetch is gated by the same auth + `case_id` check as the case view — no separate unauthenticated file route | Prevents direct-link bypass of case-level access control | Phase 5, 9 |

## Data handling

- All evidence documents used anywhere in this repository — development,
  testing, and the evaluation dataset — are synthetic. No real vendor,
  customer, or personal data is used at any point, and synthetic documents
  are written to avoid coincidentally realistic real names/companies.
- Observability traces (Langfuse) redact/truncate document text by default
  — see [`observability.md`](observability.md).
