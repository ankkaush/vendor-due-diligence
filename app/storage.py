"""Local filesystem storage for uploaded documents and their extracted text.

Deliberately local-disk, not a cloud object store: Phase 5 needs a real
place to put bytes, not a speculative abstraction for a storage backend
nothing uses yet. data/uploads/ is gitignored (.gitignore, added in
Phase 1) specifically so uploaded evidence — even synthetic test uploads
— is never at risk of being committed. Swapping this for Supabase Storage
or similar is a Phase 12 deployment concern if it turns out to matter;
nothing above this module needs to change for that (storage_ref is an
opaque string as far as callers are concerned).
"""

from pathlib import Path
from uuid import UUID

DATA_ROOT = Path(__file__).parent.parent / "data" / "uploads"


def _document_dir(case_id: UUID, document_id: UUID, version_number: int) -> Path:
    return DATA_ROOT / str(case_id) / str(document_id) / f"v{version_number}"


def save_original(
    case_id: UUID, document_id: UUID, version_number: int, filename: str, content: bytes
) -> str:
    """Persist the original uploaded bytes. Returns the storage_ref to
    record on DocumentVersion."""
    directory = _document_dir(case_id, document_id, version_number)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(content)
    return str(path.relative_to(DATA_ROOT.parent.parent))


def save_parsed_text(case_id: UUID, document_id: UUID, version_number: int, text: str) -> str:
    """Persist extracted text alongside the original. Returns the
    parsed_text_ref to record on DocumentVersion."""
    directory = _document_dir(case_id, document_id, version_number)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "parsed.txt"
    path.write_text(text, encoding="utf-8")
    return str(path.relative_to(DATA_ROOT.parent.parent))


def read_parsed_text(parsed_text_ref: str) -> str:
    """Inverse of save_parsed_text — the review UI (Phase 9) is the first
    reader of stored parsed text; nothing before it needed one."""
    return (DATA_ROOT.parent.parent / parsed_text_ref).read_text(encoding="utf-8")
