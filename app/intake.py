"""Case creation and document ingestion — the INTAKE -> DOCUMENTS_READY
half of the state machine (architecture.md), with real validation.

No HTTP layer here by design: Phase 5's job is to prove the deterministic
skeleton (validation, classification, persistence, state transitions,
audit trail, idempotency) is correct as a tested service layer. Wiring an
actual upload endpoint on top of these functions is a thin layer that
belongs with whichever phase first needs the app reachable over HTTP —
premature to add now with no auth (Phase 9) and nothing yet to route to
beyond this module.
"""

import hashlib
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import storage
from app.audit import record_event
from app.db.models import Case, CaseStateTransition, DocumentVersion, EvidenceDocument, Vendor
from app.parsing import ParsingError, parse_document
from app.routing import classify_document_domain
from app.state_machine import transition_case

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB — generous for due-diligence documents


class UploadValidationError(ValueError):
    """Rejected before any parsing is attempted — bad MIME type, empty or
    oversized file, or content that doesn't match its claimed type."""


def _sniff_matches(mime_type: str, content: bytes) -> bool:
    """Content-sniffing, not trust in the client-supplied MIME type
    (threat-model.md §3.1: "client-supplied Content-Type is untrustworthy").
    """
    if mime_type == "application/pdf":
        return content[:5] == b"%PDF-"
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return content[:4] == b"PK\x03\x04"
    if mime_type in ("text/plain", "text/markdown"):
        # No reliable magic bytes for plain text. A NUL byte in the first
        # 1KB is a strong signal of a binary file mislabeled as text;
        # failing to decode as UTF-8 is a second, independent check.
        if b"\x00" in content[:1024]:
            return False
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False


def validate_upload(filename: str, mime_type: str, content: bytes) -> None:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise UploadValidationError(f"MIME type not allowed: {mime_type!r}")
    if len(content) == 0:
        raise UploadValidationError(f"{filename}: empty file")
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadValidationError(f"{filename}: exceeds {MAX_UPLOAD_BYTES}-byte upload limit")
    if not _sniff_matches(mime_type, content):
        raise UploadValidationError(
            f"{filename}: content does not match claimed MIME type {mime_type!r}"
        )


def get_or_create_vendor(session: Session, name: str) -> Vendor:
    vendor = session.query(Vendor).filter_by(name=name).one_or_none()
    if vendor is not None:
        return vendor
    vendor = Vendor(name=name)
    session.add(vendor)
    session.flush()
    return vendor


def create_case(session: Session, vendor_name: str, actor: str = "system") -> Case:
    vendor = get_or_create_vendor(session, vendor_name)
    case = Case(vendor_id=vendor.id, status="INTAKE")
    session.add(case)
    session.flush()

    # The one transition not made through state_machine.transition_case():
    # there's no prior row state to guard against yet.
    session.add(CaseStateTransition(case_id=case.id, from_status=None, to_status="INTAKE"))
    record_event(
        session, case_id=case.id, event_type="case.created", actor=actor,
        payload={"vendor_name": vendor_name},
    )
    session.flush()
    return case


def ingest_document(
    session: Session,
    case: Case,
    *,
    filename: str,
    mime_type: str,
    doc_type: str,
    content: bytes,
    explicit_domain: str | None = None,
    actor: str = "system",
) -> EvidenceDocument:
    """Validate, classify, parse, store, and persist one document as
    version 1. Raises UploadValidationError or ParsingError on failure —
    nothing partial is ever committed to the DB; the caller's transaction
    boundary decides whether a failed document aborts the whole case or
    is reported as a gap (that policy belongs to Phase 6+'s orchestrator,
    not here)."""
    validate_upload(filename, mime_type, content)
    domain = classify_document_domain(doc_type, explicit_domain)

    document = EvidenceDocument(
        case_id=case.id, filename=filename, mime_type=mime_type,
        doc_type=doc_type, domain=domain,
    )
    session.add(document)
    session.flush()

    content_hash = hashlib.sha256(content).hexdigest()
    storage_ref = storage.save_original(case.id, document.id, 1, filename, content)

    try:
        parsed = parse_document(content, mime_type)
    except ParsingError as exc:
        record_event(
            session, case_id=case.id, event_type="document.parse_failed", actor=actor,
            payload={"document_id": str(document.id), "filename": filename, "error": str(exc)},
        )
        raise

    parsed_text_ref = storage.save_parsed_text(case.id, document.id, 1, parsed.text)

    session.add(DocumentVersion(
        document_id=document.id,
        version_number=1,
        storage_ref=storage_ref,
        parsed_text_ref=parsed_text_ref,
        page_count=parsed.page_count,
        content_hash=content_hash,
        parsed_at=datetime.now(UTC),
    ))
    record_event(
        session, case_id=case.id, event_type="document.ingested", actor=actor,
        payload={"document_id": str(document.id), "doc_type": doc_type, "domain": domain},
    )
    session.flush()
    return document


def start_validation(session: Session, case_id, actor: str = "system") -> bool:
    return transition_case(
        session, case_id, from_status="INTAKE", to_status="VALIDATING", actor=actor
    )


def mark_documents_ready(session: Session, case_id, actor: str = "system") -> bool:
    """VALIDATING -> DOCUMENTS_READY. Idempotent under concurrent duplicate
    calls: exactly one caller applies the transition (transition_case's
    WHERE-guarded UPDATE), the other observes False and must treat that
    as "already handled," not an error — the acceptance criterion this
    module exists to satisfy (architecture.md Phase 5), exercised with
    real concurrent threads in tests/test_app/test_state_machine.py."""
    return transition_case(
        session, case_id, from_status="VALIDATING", to_status="DOCUMENTS_READY", actor=actor
    )
