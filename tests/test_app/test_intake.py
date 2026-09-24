import pytest

from app.db.models import DocumentVersion, EvidenceDocument
from app.intake import (
    MAX_UPLOAD_BYTES,
    UploadValidationError,
    create_case,
    ingest_document,
    mark_documents_ready,
    start_validation,
    validate_upload,
)
from app.parsing import ParsingError

# --- validate_upload ------------------------------------------------------


def test_validate_upload_accepts_a_well_formed_markdown_file():
    validate_upload("doc.md", "text/markdown", b"# Fine\n\nBody text.")  # must not raise


def test_validate_upload_rejects_disallowed_mime_type():
    with pytest.raises(UploadValidationError, match="MIME type not allowed"):
        validate_upload("script.exe", "application/x-msdownload", b"MZ\x90\x00")


def test_validate_upload_rejects_empty_file():
    with pytest.raises(UploadValidationError, match="empty file"):
        validate_upload("empty.txt", "text/plain", b"")


def test_validate_upload_rejects_oversized_file():
    oversized = b"a" * (MAX_UPLOAD_BYTES + 1)
    with pytest.raises(UploadValidationError, match="exceeds"):
        validate_upload("big.txt", "text/plain", oversized)


def test_validate_upload_rejects_mime_content_mismatch():
    """threat-model.md §3.1: the claimed Content-Type is untrustworthy —
    binary content claiming to be a PDF, without the PDF magic bytes,
    must be rejected."""
    with pytest.raises(UploadValidationError, match="does not match claimed MIME type"):
        validate_upload("fake.pdf", "application/pdf", b"this is not a pdf")


def test_validate_upload_rejects_binary_content_claiming_to_be_text():
    with pytest.raises(UploadValidationError, match="does not match claimed MIME type"):
        validate_upload("fake.txt", "text/plain", b"\x00\x01\x02\xff\xfe binary junk")


# --- create_case / ingest_document -----------------------------------------


def test_create_case_starts_in_intake_with_history_and_audit_event(db_session):
    from app.db.models import AuditEvent, CaseStateTransition

    case = create_case(db_session, "Intake Test Vendor")
    assert case.status == "INTAKE"

    transitions = db_session.query(CaseStateTransition).filter_by(case_id=case.id).all()
    assert len(transitions) == 1
    assert transitions[0].from_status is None
    assert transitions[0].to_status == "INTAKE"

    events = db_session.query(AuditEvent).filter_by(case_id=case.id).all()
    assert any(e.event_type == "case.created" for e in events)


def test_create_case_reuses_an_existing_vendor_by_name(db_session):
    case_1 = create_case(db_session, "Repeat Vendor")
    case_2 = create_case(db_session, "Repeat Vendor")
    assert case_1.vendor_id == case_2.vendor_id
    assert case_1.id != case_2.id


def test_ingest_document_persists_document_version_with_parsed_text(db_session):
    case = create_case(db_session, "Ingest Test Vendor")
    document = ingest_document(
        db_session, case,
        filename="dpa.md", mime_type="text/markdown", doc_type="dpa",
        content=b"# DPA\n\nRetention period is 30 days.",
    )
    assert document.domain == "privacy_ai_governance"  # dpa's default

    version = db_session.query(DocumentVersion).filter_by(document_id=document.id).one()
    assert version.version_number == 1
    assert version.content_hash  # sha256 populated
    assert version.parsed_text_ref is not None

    from pathlib import Path
    parsed_path = Path(__file__).parent.parent.parent / version.parsed_text_ref
    assert "Retention period is 30 days" in parsed_path.read_text()


def test_ingest_document_with_explicit_domain_override(db_session):
    case = create_case(db_session, "Override Test Vendor")
    document = ingest_document(
        db_session, case,
        filename="mixed-questionnaire.md", mime_type="text/markdown",
        doc_type="security_questionnaire",
        content=b"Contains both security and privacy content.",
        explicit_domain="both",
    )
    assert document.domain == "both"


def test_ingest_document_failure_does_not_persist_a_document_version(db_session):
    case = create_case(db_session, "Bad Upload Test Vendor")
    with pytest.raises(UploadValidationError):
        ingest_document(
            db_session, case,
            filename="bad.pdf", mime_type="application/pdf",
            doc_type="soc_report", content=b"not a real pdf",
        )
    assert db_session.query(EvidenceDocument).filter_by(case_id=case.id).count() == 0


def test_ingest_document_parse_failure_is_recorded_as_an_audit_event(db_session):
    from app.db.models import AuditEvent

    case = create_case(db_session, "Parse Failure Test Vendor")
    with pytest.raises(ParsingError):
        ingest_document(
            db_session, case,
            filename="fake.docx", mime_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            doc_type="dpa",
            content=b"PK\x03\x04" + b"not a real zip after the magic bytes",
        )
    events = db_session.query(AuditEvent).filter_by(case_id=case.id).all()
    assert any(e.event_type == "document.parse_failed" for e in events)


# --- validation -> documents_ready pipeline ---------------------------------


def test_full_intake_pipeline_reaches_documents_ready(db_session):
    case = create_case(db_session, "Full Pipeline Vendor")
    ingest_document(
        db_session, case, filename="dpa.md", mime_type="text/markdown",
        doc_type="dpa", content=b"Retention: 30 days.",
    )
    assert start_validation(db_session, case.id) is True
    assert mark_documents_ready(db_session, case.id) is True
    db_session.refresh(case)
    assert case.status == "DOCUMENTS_READY"


def test_start_validation_twice_is_idempotent_not_an_error(db_session):
    case = create_case(db_session, "Idempotent Validation Vendor")
    assert start_validation(db_session, case.id) is True
    assert start_validation(db_session, case.id) is False  # already past INTAKE, not an error
