# ADR-003: No live external evidence-retrieval tools in the MVP

**Status:** Accepted
**Date:** 2026-09-23

## Context

Investigators could plausibly be given web search or external API access to
corroborate vendor claims (e.g. certificate transparency lookups, registry
checks). This would expand the threat surface significantly: SSRF risk,
malicious-URL handling, and indirect prompt injection from fetched web
content — none of which bear on the technical thesis (independent reasoning
over a fixed evidence package).

## Decision

MVP investigators reason only over the uploaded, fixed evidence package.
They have no tools, no network access, and no database credentials.

## Rationale

This is also the load-bearing security decision: because investigators have
no privileged action available (no tool calls, no writes, no external
requests), a successful prompt injection has nowhere to escalate to. Adding
live external tools before the core hypothesis is even validated would
introduce real security surface for a capability that isn't part of what's
being tested.

## Consequences

- Evidence gaps (e.g. "no penetration-test evidence provided") are reported
  as gaps, not resolved by fetching external corroboration.
- If a genuine need for external verification emerges after Gate 6, it is
  scoped and threat-modeled as a deliberate addition — not assumed now.
