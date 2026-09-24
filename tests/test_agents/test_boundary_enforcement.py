"""ADR-007 / agent-boundaries.md's core guarantee, tested directly rather
than only asserted in documentation: an investigator's context cannot
contain another agent's output, even when that output exists and is
sitting in scope right next to the call that builds the other agent's
context.

Scope note, stated honestly: this phase has no persisted AgentRun/Finding
data (no orchestrator/DB wiring yet — app/agents/investigator.py is a
pure function, same as app/agents/baseline.py). What's proven here is
that (1) run_investigator's own signature has no path by which another
agent's result could reach it, and (2) even when a security investigator
has already produced real, distinctive findings and that result is held
in the very same test — the kind of situation "even when available" is
meant to cover — the privacy investigator's actual prompt contains zero
trace of it. When a real orchestrator later persists Finding rows to the
database, that boundary needs the same proof in its own shape (a context
builder with no query path to another agent's DB rows) — this test is
the pattern that one should follow, not a substitute for it.
"""

import inspect

from app.agents.investigator import run_investigator
from app.agents.schema import CaseDocument
from tests.fakes import FakeLLMClient

SECURITY_DOC = CaseDocument(
    document_id="doc-sec", filename="s.md",
    text="Security whitepaper content.", domain="security",
)
PRIVACY_DOC = CaseDocument(
    document_id="doc-priv", filename="p.md",
    text="DPA content, retention 30 days.", domain="privacy_ai_governance",
)
ALL_DOCS = [SECURITY_DOC, PRIVACY_DOC]

# A response with a deliberately unique marker standing in for "real,
# distinctive findings" — if this string ever showed up in the privacy
# investigator's prompt, that would prove a leak, not a coincidence.
SECURITY_MARKER = "SECURITY_FINDING_MARKER_7f3c9a1e"
SECURITY_RESPONSE = {
    "claims": [{
        "subject": SECURITY_MARKER, "predicate": "y", "value": "z", "unit": None,
        "temporal_scope": None, "domain": "security", "claim_type": "technical_control",
        "source_document_id": "doc-sec", "source_location": "x",
        "source_excerpt": f"excerpt containing {SECURITY_MARKER}",
        "verification_status": "supported",
        "rationale": f"rationale mentioning {SECURITY_MARKER} explicitly",
        "evidence": [],
    }],
    "injection_detected": False, "injection_note": "",
}

PRIVACY_RESPONSE = {
    "claims": [], "injection_detected": False, "injection_note": "",
}


def test_run_investigator_signature_has_no_path_to_another_agents_output():
    """Structural guarantee: it is not possible to even attempt to pass
    another agent's result into a context-building call, because no such
    parameter exists. This isn't access control on reachable data — the
    data is simply not part of the function's input at all."""
    params = set(inspect.signature(run_investigator).parameters)
    assert params == {
        "client", "model", "agent_type", "documents", "max_tokens", "max_attempts",
    }
    assert not any("finding" in p or "result" in p or "other" in p for p in params)


def test_investigator_context_has_no_cross_agent_data_even_when_available():
    security_client = FakeLLMClient(responses=[SECURITY_RESPONSE])
    security_result = run_investigator(
        security_client, model="m", agent_type="security_investigator", documents=ALL_DOCS,
    )
    # Confirm the marker is genuinely present in security's real output —
    # otherwise this test would trivially pass for the wrong reason.
    assert SECURITY_MARKER in security_result.claims[0]["subject"]
    assert security_result is not None  # "available," per the test's name — it exists now

    privacy_client = FakeLLMClient(responses=[PRIVACY_RESPONSE])
    run_investigator(
        privacy_client, model="m", agent_type="privacy_investigator", documents=ALL_DOCS,
    )

    privacy_system = privacy_client.calls[0]["system"]
    privacy_user_message = privacy_client.calls[0]["user_message"]
    assert SECURITY_MARKER not in privacy_system
    assert SECURITY_MARKER not in privacy_user_message
    # Also confirm no document text unique to the security investigator's
    # domain leaked in, not just the marker specifically.
    assert "Security whitepaper" not in privacy_user_message


def test_order_of_execution_does_not_affect_isolation():
    """The boundary must hold regardless of which investigator runs
    first (architecture.md: 'This must hold regardless of execution
    order... Agent A runs first; Agent B runs first; both run
    concurrently')."""
    privacy_client = FakeLLMClient(responses=[PRIVACY_RESPONSE])
    run_investigator(
        privacy_client, model="m", agent_type="privacy_investigator", documents=ALL_DOCS,
    )
    security_client = FakeLLMClient(responses=[SECURITY_RESPONSE])
    run_investigator(
        security_client, model="m", agent_type="security_investigator", documents=ALL_DOCS,
    )

    assert SECURITY_MARKER not in privacy_client.calls[0]["system"]
    assert SECURITY_MARKER not in privacy_client.calls[0]["user_message"]
