"""Deterministic document classification: doc_type -> investigator domain.

This is the routing table referenced throughout the design docs
(architecture.md's CLASSIFYING state, agent-boundaries.md's "allowed
documents" boundary) made concrete. A document's `domain` is what
Phase 7's context-builders actually filter on — `security` reaches only
the security investigator, `privacy_ai_governance` only the privacy one,
`both` reaches both.

Nine of the ten doc_types have an unambiguous default. `other` has none —
Phase 5 has no LLM available to make that call (ADR-003/architecture.md:
zero agents until Phase 6+), so an "other"-typed document requires an
explicit domain at ingestion time; there is no silent fallback.

A document's domain can also be explicitly overridden away from its
doc_type's default, because real documents don't respect clean
categories. eval/ground_truth/case-12.json is the concrete example this
module exists to get right: its security_questionnaire.md contains a
GDPR/privacy question alongside security questions. Routing it "security
only" by default would make the privacy investigator structurally unable
to ever see — and therefore extract — that claim, silently turning a
realistic mixed-content document into an unreachable one. case-12's
document is explicitly classified `domain="both"` for exactly this
reason (see its expected_handling_notes) — this was found by building
this routing table, not designed in from the start.
"""

DEFAULT_DOMAIN_BY_DOC_TYPE: dict[str, str] = {
    "security_questionnaire": "security",
    "security_whitepaper": "security",
    "soc_report": "security",
    "pentest_attestation": "security",
    "contract_sla": "security",
    "dpa": "privacy_ai_governance",
    "privacy_policy": "privacy_ai_governance",
    "ai_governance_doc": "privacy_ai_governance",
    "subprocessor_list": "privacy_ai_governance",
    # "other" is intentionally absent — see module docstring.
}

VALID_DOMAINS = {"security", "privacy_ai_governance", "both"}


class UnclassifiableDocumentError(ValueError):
    """Raised when a doc_type has no default domain and none was supplied."""


def classify_document_domain(doc_type: str, explicit_domain: str | None = None) -> str:
    """Return the domain a document should be routed under.

    An explicit_domain always wins over the default, for the mixed-content
    case described above. Only "other" requires one; supplying an
    explicit_domain for any other doc_type is allowed too (a human
    reviewer might know better than the default) but not required.
    """
    if explicit_domain is not None:
        if explicit_domain not in VALID_DOMAINS:
            raise ValueError(
                f"invalid domain {explicit_domain!r}; must be one of {sorted(VALID_DOMAINS)}"
            )
        return explicit_domain

    default = DEFAULT_DOMAIN_BY_DOC_TYPE.get(doc_type)
    if default is None:
        raise UnclassifiableDocumentError(
            f"doc_type {doc_type!r} has no default domain and none was supplied — "
            "'other'-typed documents must be classified explicitly. Phase 5 has no "
            "LLM available to infer this; a later phase may add a model-assisted "
            "fallback (architecture.md's CLASSIFYING note), but that does not exist yet."
        )
    return default
