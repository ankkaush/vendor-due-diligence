import pytest

from app.routing import (
    DEFAULT_DOMAIN_BY_DOC_TYPE,
    UnclassifiableDocumentError,
    classify_document_domain,
)


@pytest.mark.parametrize("doc_type,expected", DEFAULT_DOMAIN_BY_DOC_TYPE.items())
def test_default_classification_for_every_known_doc_type(doc_type, expected):
    assert classify_document_domain(doc_type) == expected


def test_other_doc_type_requires_explicit_domain():
    with pytest.raises(UnclassifiableDocumentError):
        classify_document_domain("other")


def test_other_doc_type_with_explicit_domain_is_accepted():
    assert classify_document_domain("other", explicit_domain="privacy_ai_governance") == (
        "privacy_ai_governance"
    )


def test_explicit_domain_overrides_the_default():
    # The case-12 scenario: a security_questionnaire that blends security
    # and privacy content gets explicitly routed to both investigators,
    # overriding its normally security-only default.
    assert classify_document_domain("security_questionnaire", explicit_domain="both") == "both"


def test_invalid_explicit_domain_is_rejected():
    with pytest.raises(ValueError, match="invalid domain"):
        classify_document_domain("dpa", explicit_domain="not_a_real_domain")
