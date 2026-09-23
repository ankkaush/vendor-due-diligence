# ADR-008: Ground-truth ontology reuses the production Claim/EvidenceItem schema

**Status:** Accepted
**Date:** 2026-09-23

## Context

The evaluation dataset (Phase 3) is itself part of the measurement system.
If "what counts as a claim" and "what counts as valid evidence" aren't
consistently defined before labeling begins, apparently precise metrics may
actually measure inconsistent labeling. A separate, ad hoc ground-truth
format would also require a translation layer before automated scoring
against real agent output.

## Decision

The ground-truth label schema is the production `Claim`/`EvidenceItem`
schema (`data-model.md`) — claim ID, domain, claim type, subject,
predicate, value, unit, temporal scope, evidence requirement, evidence
location(s) with document-version reference, expected verification
status — plus eval-only metadata not present on the production tables:
`issue_type` (e.g. `direct_contradiction`, `subtle_contradiction`,
`missing_evidence`, `ambiguous_wording`, `outdated_evidence`,
`version_conflict`, `cross_domain_conflict`, `misleading_wording`,
`injection_attempt`), `is_planted_issue`, and `expected_handling_notes`.

No numeric `expected_confidence` field is included: confidence has not been
rigorously defined (per the original project brief's own caution), so
grading against an undefined target would launder that ambiguity into the
metrics. `verification_status` — including the `ambiguous` category —
is the sole graded label.

This ontology is defined as Phase 3a, before case construction (Phase 3b)
begins.

## Rationale

- Reusing the production schema means ground truth doubles as an early
  pilot of the Phase 4 data model — if labeling 18 cases by hand reveals
  the schema is awkward, that's a cheap signal to revise it before any
  database code exists.
- `issue_type`/`is_planted_issue` tagging is what makes the Gate 6 question
  answerable with precision: results can be broken down by failure-mode
  category (e.g. multi-agent wins specifically on cross-domain conflicts)
  rather than reported only as one aggregate number that would hide that
  finding.

## Consequences

- `issue_type`/`is_planted_issue`/`expected_handling_notes` are eval-only
  fields and must not leak into the production `Claim` table — they
  describe the dataset, not the domain.
