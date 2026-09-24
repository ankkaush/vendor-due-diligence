from app.agents.schema import AgentResult, CaseDocument
from app.reconcile import (
    ADJUDICATION_TOOL_NAME,
    find_deterministic_conflicts,
    pool_claims,
    reconcile,
)
from tests.fakes import FakeLLMClient

# --- pool_claims / find_deterministic_conflicts (pure, no LLM) -------------


def _claim(subject, predicate, value, **overrides):
    base = {
        "subject": subject, "predicate": predicate, "value": value,
        "unit": None, "temporal_scope": None, "domain": "security",
        "claim_type": "technical_control", "source_document_id": "doc-a",
        "source_location": "x", "source_excerpt": "x",
        "verification_status": "supported", "rationale": "x", "evidence": [],
    }
    base.update(overrides)
    return base


def test_pool_claims_assigns_stable_prefixed_ids():
    sec = AgentResult(
        claims=[_claim("a", "p", "1")], injection_detected=False, injection_note="",
        input_tokens=0, output_tokens=0, model="m",
    )
    priv = AgentResult(
        claims=[_claim("b", "p", "2")], injection_detected=False, injection_note="",
        input_tokens=0, output_tokens=0, model="m",
    )
    pooled = pool_claims(sec, priv)
    assert [c.claim_id for c in pooled] == ["security-0", "privacy-0"]
    assert pooled[0].agent_type == "security_investigator"
    assert pooled[1].agent_type == "privacy_investigator"


def test_deterministic_conflict_found_for_same_agent_same_topic_different_value():
    pooled = pool_claims(
        AgentResult(
            claims=[
                _claim("data retention period", "retention_period", "30"),
                _claim("data retention period", "retention_period", "90"),
            ],
            injection_detected=False, injection_note="", input_tokens=0, output_tokens=0,
            model="m",
        ),
        AgentResult(claims=[], injection_detected=False, injection_note="",
                    input_tokens=0, output_tokens=0, model="m"),
    )
    conflicts = find_deterministic_conflicts(pooled)
    assert len(conflicts) == 1
    assert conflicts[0].claim_ids == ("security-0", "security-1")
    assert conflicts[0].agent_type == "security_investigator"


def test_no_conflict_when_same_topic_and_same_value():
    pooled = pool_claims(
        AgentResult(
            claims=[
                _claim("data retention period", "retention_period", "30"),
                _claim("data retention period", "retention_period", "30"),
            ],
            injection_detected=False, injection_note="", input_tokens=0, output_tokens=0,
            model="m",
        ),
        AgentResult(claims=[], injection_detected=False, injection_note="",
                    input_tokens=0, output_tokens=0, model="m"),
    )
    assert find_deterministic_conflicts(pooled) == []


def test_no_conflict_when_different_topics():
    pooled = pool_claims(
        AgentResult(
            claims=[
                _claim("encryption algorithm", "uses_algorithm", "AES-256"),
                _claim("penetration testing", "performed_with_frequency", "annual"),
            ],
            injection_detected=False, injection_note="", input_tokens=0, output_tokens=0,
            model="m",
        ),
        AgentResult(claims=[], injection_detected=False, injection_note="",
                    input_tokens=0, output_tokens=0, model="m"),
    )
    assert find_deterministic_conflicts(pooled) == []


def test_no_deterministic_conflict_across_different_agents():
    """Cross-domain pairs are semantic adjudication's job, not the
    deterministic pass (app/reconcile.py's module docstring) — even if
    subject/predicate happen to line up."""
    pooled = pool_claims(
        AgentResult(
            claims=[_claim("data location", "processed_in", "EU")],
            injection_detected=False, injection_note="", input_tokens=0, output_tokens=0,
            model="m",
        ),
        AgentResult(
            claims=[_claim("data location", "processed_in", "US")],
            injection_detected=False, injection_note="", input_tokens=0, output_tokens=0,
            model="m",
        ),
    )
    assert find_deterministic_conflicts(pooled) == []


# --- reconcile() orchestration, with FakeLLMClient --------------------------

DOCS = [
    CaseDocument(document_id="doc-a", filename="a.md", text="A content.", domain="security"),
    CaseDocument(document_id="doc-b", filename="b.md", text="B content.", domain="security"),
]

REINVESTIGATION_RESOLVED = {
    "resolved": True, "explanation": "Reconciled: exception applies.",
    "resolution_status": "contradicted",
}
NO_SEMANTIC_CONFLICTS = {"conflicts": []}


def test_reconcile_runs_reinvestigation_before_semantic_adjudication_and_updates_statuses():
    security = AgentResult(
        claims=[
            _claim("data retention period", "retention_period", "30", source_document_id="doc-a"),
            _claim("data retention period", "retention_period", "90", source_document_id="doc-b"),
        ],
        injection_detected=False, injection_note="", input_tokens=0, output_tokens=0, model="m",
    )
    # A claim left over after the deterministic pass consumes the security
    # pair, so there's still something for semantic adjudication to see —
    # otherwise the empty-input guard (like investigator.py's empty-domain
    # guard) skips that call entirely, which is its own documented behavior
    # below, not what this test is checking.
    privacy = AgentResult(
        claims=[_claim("unrelated claim", "p", "v", domain="privacy_ai_governance")],
        injection_detected=False, injection_note="",
        input_tokens=0, output_tokens=0, model="m",
    )
    # Call order: reinvestigation (1 deterministic conflict) then semantic adjudication.
    client = FakeLLMClient(responses=[REINVESTIGATION_RESOLVED, NO_SEMANTIC_CONFLICTS])

    result = reconcile(
        client, model="m", security_result=security, privacy_result=privacy, documents=DOCS,
    )

    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.status == "resolved"
    assert conflict.resolution_method == "reinvestigation"
    assert set(conflict.claim_ids) == {"security-0", "security-1"}

    # Both claims' verification_status updated to the reinvestigation's resolution.
    updated = {c.claim_id: c.data["verification_status"] for c in result.reconciled_claims}
    assert updated["security-0"] == "contradicted"
    assert updated["security-1"] == "contradicted"

    assert client.calls[1]["tool_name"] == ADJUDICATION_TOOL_NAME
    # And the semantic call only received the leftover claim, not the two
    # already handled deterministically.
    assert "unrelated claim" in client.calls[1]["user_message"]
    assert "data retention period" not in client.calls[1]["user_message"]


def test_semantic_adjudication_is_skipped_when_deterministic_pass_consumes_everything():
    """The empty-input guard in adjudicate_semantic_conflicts (mirrors
    investigator.py's empty-domain guard): if every pooled claim was
    already accounted for by the deterministic pass, there is nothing
    left to adjudicate, so no second API call is made."""
    security = AgentResult(
        claims=[
            _claim("data retention period", "retention_period", "30", source_document_id="doc-a"),
            _claim("data retention period", "retention_period", "90", source_document_id="doc-b"),
        ],
        injection_detected=False, injection_note="", input_tokens=0, output_tokens=0, model="m",
    )
    privacy = AgentResult(
        claims=[], injection_detected=False, injection_note="",
        input_tokens=0, output_tokens=0, model="m",
    )
    client = FakeLLMClient(responses=[REINVESTIGATION_RESOLVED])  # no second response scripted
    result = reconcile(
        client, model="m", security_result=security, privacy_result=privacy, documents=DOCS,
    )
    assert len(result.conflicts) == 1
    assert len(client.calls) == 1  # reinvestigation only; semantic call skipped


def test_reconcile_leaves_conflict_open_when_reinvestigation_cannot_resolve():
    security = AgentResult(
        claims=[
            _claim("retention", "retention_period", "30", source_document_id="doc-a"),
            _claim("retention", "retention_period", "120", source_document_id="doc-b"),
        ],
        injection_detected=False, injection_note="", input_tokens=0, output_tokens=0, model="m",
    )
    privacy = AgentResult(
        claims=[], injection_detected=False, injection_note="",
        input_tokens=0, output_tokens=0, model="m",
    )
    unresolved = {"resolved": False, "explanation": "No reconciling evidence found.",
                  "resolution_status": None}
    client = FakeLLMClient(responses=[unresolved, NO_SEMANTIC_CONFLICTS])

    result = reconcile(
        client, model="m", security_result=security, privacy_result=privacy, documents=DOCS,
    )
    assert result.conflicts[0].status == "open"
    # Original statuses untouched — no fabricated resolution.
    updated = {c.claim_id: c.data["verification_status"] for c in result.reconciled_claims}
    assert updated["security-0"] == "supported"  # the _claim() default, unchanged
    assert updated["security-1"] == "supported"


def test_reconcile_applies_semantic_conflicts_across_domains():
    security = AgentResult(
        claims=[_claim(
            "data residency", "processed_in", "EU only", domain="security",
            source_document_id="doc-a", verification_status="unverified",
        )],
        injection_detected=False, injection_note="", input_tokens=0, output_tokens=0, model="m",
    )
    privacy = AgentResult(
        claims=[_claim(
            "sub-processor location", "located_in", "United States",
            domain="privacy_ai_governance", source_document_id="doc-b",
            verification_status="supported",
        )],
        injection_detected=False, injection_note="", input_tokens=0, output_tokens=0, model="m",
    )
    semantic_response = {
        "conflicts": [{
            "claim_ids": ["security-0", "privacy-0"],
            "conflict_type": "cross_domain_conflict",
            "rationale": "EU-only claim conflicts with a US-based sub-processor disclosure.",
        }],
    }
    # No deterministic conflicts here, so only one call: semantic adjudication.
    client = FakeLLMClient(responses=[semantic_response])

    result = reconcile(
        client, model="m", security_result=security, privacy_result=privacy, documents=DOCS,
    )

    assert len(result.conflicts) == 1
    assert result.conflicts[0].conflict_type == "cross_domain_conflict"
    assert result.conflicts[0].resolution_method == "semantic_adjudication"
    assert result.conflicts[0].status == "resolved"

    updated = {c.claim_id: c.data["verification_status"] for c in result.reconciled_claims}
    assert updated["security-0"] == "contradicted"
    assert updated["privacy-0"] == "contradicted"


def test_reconcile_with_no_conflicts_at_all_makes_only_one_semantic_call():
    security = AgentResult(
        claims=[_claim("x", "y", "z")], injection_detected=False, injection_note="",
        input_tokens=0, output_tokens=0, model="m",
    )
    privacy = AgentResult(
        claims=[], injection_detected=False, injection_note="",
        input_tokens=0, output_tokens=0, model="m",
    )
    client = FakeLLMClient(responses=[NO_SEMANTIC_CONFLICTS])
    result = reconcile(
        client, model="m", security_result=security, privacy_result=privacy, documents=DOCS,
    )
    assert result.conflicts == []
    assert len(client.calls) == 1


def test_reconcile_with_zero_pooled_claims_skips_semantic_call_entirely():
    empty = AgentResult(
        claims=[], injection_detected=False, injection_note="",
        input_tokens=0, output_tokens=0, model="m",
    )
    client = FakeLLMClient(responses=[])  # would raise if called at all
    result = reconcile(
        client, model="m", security_result=empty, privacy_result=empty, documents=DOCS,
    )
    assert result.conflicts == []
    assert len(client.calls) == 0
