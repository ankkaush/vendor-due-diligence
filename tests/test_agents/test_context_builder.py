import pytest

from app.agents.context_builder import build_context
from app.agents.schema import CaseDocument

SECURITY_DOC = CaseDocument(
    document_id="d-sec", filename="s.md", text="security", domain="security"
)
PRIVACY_DOC = CaseDocument(
    document_id="d-priv", filename="p.md", text="privacy", domain="privacy_ai_governance"
)
BOTH_DOC = CaseDocument(document_id="d-both", filename="b.md", text="both", domain="both")

ALL_DOCS = [SECURITY_DOC, PRIVACY_DOC, BOTH_DOC]


def test_security_domain_gets_security_and_both_docs_only():
    result = build_context(ALL_DOCS, "security")
    assert {d.document_id for d in result} == {"d-sec", "d-both"}


def test_privacy_domain_gets_privacy_and_both_docs_only():
    result = build_context(ALL_DOCS, "privacy_ai_governance")
    assert {d.document_id for d in result} == {"d-priv", "d-both"}


def test_security_context_never_contains_privacy_only_document():
    result = build_context(ALL_DOCS, "security")
    assert "d-priv" not in {d.document_id for d in result}
    assert not any("privacy" in d.text for d in result)


def test_privacy_context_never_contains_security_only_document():
    result = build_context(ALL_DOCS, "privacy_ai_governance")
    assert "d-sec" not in {d.document_id for d in result}
    assert not any(d.text == "security" for d in result)


def test_no_matching_documents_returns_empty_list():
    result = build_context([SECURITY_DOC], "privacy_ai_governance")
    assert result == []


def test_invalid_domain_is_rejected():
    with pytest.raises(ValueError, match="domain must be one of"):
        build_context(ALL_DOCS, "not_a_real_domain")
