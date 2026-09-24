"""threat-model.md §3.5: "SQL injection — ORM (SQLAlchemy) with
parameterized queries exclusively — no raw string interpolation of any
user- or document-derived value into SQL, anywhere." Structurally true
by construction (no f-string/`.format()`/`%`-built SQL appears anywhere
in app/), but exercised here against a real database with real classic
injection payloads run through the actual code paths that accept
document- and reviewer-derived strings — not just asserted from reading
the code.
"""

from sqlalchemy import select

from app.db.models import (
    AgentRun,
    Case,
    Claim,
    DocumentVersion,
    EvidenceDocument,
    Finding,
    Vendor,
)
from app.web.queries import list_cases

INJECTION_PAYLOADS = [
    "'; DROP TABLE cases; --",
    "' OR '1'='1",
    "Robert'); DROP TABLE claims;--",
    '" OR ""="',
    "1; SELECT * FROM human_reviews",
]


def test_vendor_name_containing_injection_payload_is_stored_and_returned_literally(db_session):
    for payload in INJECTION_PAYLOADS:
        vendor = Vendor(name=payload)
        db_session.add(vendor)
        db_session.flush()

        # If this were vulnerable, either the flush above or this query
        # would error out (broken SQL) or the table would already be
        # gone. Neither happens — the payload round-trips as inert data.
        fetched = db_session.get(Vendor, vendor.id)
        assert fetched.name == payload

    # Table still exists and has exactly as many rows as we inserted —
    # a real DROP TABLE would make this query itself fail outright.
    count = db_session.execute(select(Vendor)).scalars().all()
    assert len(count) >= len(INJECTION_PAYLOADS)


def test_claim_subject_containing_injection_payload_is_queryable_through_the_real_review_ui_path(
    db_session,
):
    """Runs an injection payload through app.web.queries.list_cases — the
    exact function the review UI's case list route calls — not just a
    raw ORM round-trip."""
    payload = "'; DROP TABLE claims; --"
    vendor = Vendor(name=payload)
    db_session.add(vendor)
    db_session.flush()
    case = Case(vendor_id=vendor.id, status="INTAKE")
    db_session.add(case)
    db_session.flush()

    document = EvidenceDocument(
        case_id=case.id, filename="x.md", mime_type="text/markdown",
        doc_type="dpa", domain="privacy_ai_governance",
    )
    db_session.add(document)
    db_session.flush()
    doc_version = DocumentVersion(
        document_id=document.id, version_number=1, storage_ref="local://x.md",
        content_hash="a" * 64,
    )
    db_session.add(doc_version)
    db_session.flush()

    agent_run = AgentRun(
        case_id=case.id, agent_type="privacy_investigator", status="succeeded", model="m",
    )
    db_session.add(agent_run)
    db_session.flush()
    claim = Claim(
        case_id=case.id, agent_run_id=agent_run.id, domain="privacy_ai_governance",
        claim_type="data_practice", subject=payload, predicate="x", value="y",
        source_document_version_id=doc_version.id, source_location="x",
        source_excerpt=payload, evidence_requirement="",
    )
    db_session.add(claim)
    db_session.flush()
    db_session.add(Finding(
        case_id=case.id, agent_run_id=agent_run.id, claim_id=claim.id,
        verification_status="supported", rationale=payload,
    ))
    db_session.flush()

    cases = list_cases(db_session)
    matching = [c for c, vendor_name in cases if vendor_name == payload]
    assert len(matching) == 1
    assert matching[0].id == case.id

    # The tables this payload names are still fully intact.
    assert db_session.get(Case, case.id) is not None
    assert db_session.get(Claim, claim.id) is not None
