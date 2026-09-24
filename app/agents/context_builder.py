"""The entire mechanism that enforces agent-boundary isolation (ADR-007,
agent-boundaries.md). Deliberately this small — "the smallest justified
multi-agent architecture" (Phase 7 scope) means the boundary isn't a
permissions system, a query allowlist, or anything else that could be
misconfigured; it's a single filter with no path around it.

Each investigator's run function (app/agents/investigator.py) calls
build_context() and ONLY build_context() to obtain its documents. There
is no other function anywhere that hands a domain-scoped investigator a
document, and build_context()'s signature accepts a document list and a
domain string — nothing else. It has no parameter for another agent's
findings, another agent's run id, or any prior conclusion, because
findings are never an input to context construction in the first place.
That is the isolation: not access control on data that could theoretically
be reached, but the absence of any path to it at all.

The equivalent DB-level guarantee this note originally deferred: Phase 9
built the persistence layer (app/persist.py) and the review UI's query
layer (app/web/queries.py), and Phase 10 closed the gap this paragraph
named in advance —
tests/test_web/test_cross_case_isolation.py::test_get_case_detail_never_returns_another_cases_claims_documents_or_conflicts
proves get_case_detail() never returns another case's Claim/Finding/
Conflict rows even when both exist in the same database at once, the
same shape of guarantee this module proves for in-memory context
construction, mirrored for the persisted path.
"""

from app.agents.schema import CaseDocument

VALID_DOMAINS = {"security", "privacy_ai_governance"}


def build_context(documents: list[CaseDocument], domain: str) -> list[CaseDocument]:
    """Documents routed to `domain`, plus any tagged "both" (case-12's
    mixed-content scenario, app/routing.py). Nothing else is reachable
    through this function — not a different domain's documents, not
    another agent's output, not case metadata beyond what's in
    CaseDocument."""
    if domain not in VALID_DOMAINS:
        raise ValueError(f"domain must be one of {sorted(VALID_DOMAINS)}, got {domain!r}")
    return [doc for doc in documents if doc.domain in (domain, "both")]
