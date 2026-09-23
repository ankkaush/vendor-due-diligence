# ADR-004: Claim extraction happens inside each investigator, independently

**Status:** Accepted
**Date:** 2026-09-23

## Context

A shared upstream "claim extraction" stage could extract one canonical
claim list and hand it to both investigators, reducing redundant work. But
that would silently reintroduce a single point of agreement before
independence ever starts — both investigators would only be *verifying* a
shared list, not *investigating* independently.

## Decision

Each investigator receives its own domain-routed document subset and
extracts its own claims from it, then verifies those claims itself. There is
no shared upstream claim-extraction stage.

## Rationale

If both investigators happen to independently identify "the same"
real-world claim, that agreement is itself a meaningful signal. If they
identify different claims from overlapping text, that divergence is
informative too — and both signals are lost if claim identification is
centralized upstream.

## Consequences

- Some extraction work is duplicated across investigators (acceptable —
  the whole point is testing independent reasoning, not minimizing token
  spend at the cost of the experiment's validity).
- The `Claim` table records which `AgentRun` extracted each claim
  (`data-model.md`), so extraction agreement/disagreement is queryable
  directly from the schema.
