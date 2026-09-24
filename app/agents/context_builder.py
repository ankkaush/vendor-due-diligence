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

What this does NOT yet cover: once a real orchestrator persists AgentRun/
Finding rows to the database (a later phase), THAT boundary — a context
builder querying the DB must have no path to another agent's Finding rows
— needs its own equivalent guarantee and its own test in that shape,
mirroring this one. Scoped out here deliberately; there is no persisted
Finding data for this phase to leak in the first place.
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
