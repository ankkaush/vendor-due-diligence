"""Document text extraction for the four supported types (decision #10:
PDF, DOCX, TXT, MD — no OCR).

Every mitigation here is a direct line item from threat-model.md §3.2:
- XXE: DOCX's internal XML is parsed with defusedxml, not stdlib
  ElementTree — external entity/DTD resolution is disabled by
  construction, not by remembering to pass a flag correctly.
- Zip-bomb: DOCX is a zip; decompressed size is checked against each
  entry's declared size BEFORE reading it, not after.
- Parser hang: every parse runs under a hard wall-clock timeout
  (SIGALRM) and fails loudly rather than hanging.
- No silent best-effort parsing: any failure raises ParsingError; nothing
  downstream ever sees partial/corrupt text without knowing it happened.
"""

import contextlib
import signal
import zipfile
from dataclasses import dataclass
from io import BytesIO

import defusedxml.ElementTree as safe_ET
from pypdf import PdfReader
from pypdf.errors import PdfReadError

PARSE_TIMEOUT_S = 15
MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024  # 20MB — generous for a due-diligence doc, not a bomb

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ParsingError(Exception):
    """Any parse failure — malformed input, timeout, or a decompression
    limit tripped. Deliberately one exception type: callers don't need to
    distinguish why parsing failed, only that it did, and must not accept
    partial output."""


@dataclass
class ParsedDocument:
    text: str
    page_count: int | None = None


@contextlib.contextmanager
def _timeout(seconds: int):
    def _raise_timeout(signum, frame):
        raise ParsingError(f"parsing exceeded {seconds}s timeout")

    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def parse_document(content: bytes, mime_type: str) -> ParsedDocument:
    with _timeout(PARSE_TIMEOUT_S):
        if mime_type == "text/plain" or mime_type == "text/markdown":
            return _parse_text(content)
        if mime_type == "application/pdf":
            return _parse_pdf(content)
        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return _parse_docx(content)
    raise ParsingError(f"unsupported mime_type: {mime_type!r}")


def _parse_text(content: bytes) -> ParsedDocument:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParsingError(f"not valid UTF-8 text: {exc}") from exc
    return ParsedDocument(text=text, page_count=None)


def _parse_pdf(content: bytes) -> ParsedDocument:
    try:
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise ParsingError(f"malformed PDF: {exc}") from exc
    return ParsedDocument(text="\n\n".join(pages), page_count=len(pages))


def _parse_docx(content: bytes) -> ParsedDocument:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            try:
                info = archive.getinfo("word/document.xml")
            except KeyError as exc:
                raise ParsingError("not a valid DOCX: no word/document.xml") from exc

            if info.file_size > MAX_DECOMPRESSED_BYTES:
                raise ParsingError(
                    f"word/document.xml declares {info.file_size} bytes decompressed, "
                    f"exceeding the {MAX_DECOMPRESSED_BYTES}-byte cap — refusing to extract"
                )

            xml_bytes = archive.read(info)
    except zipfile.BadZipFile as exc:
        raise ParsingError(f"not a valid DOCX (not a zip): {exc}") from exc

    try:
        # defusedxml.ElementTree.fromstring: external entities and DTDs are
        # rejected by construction — not a flag that can be forgotten.
        root = safe_ET.fromstring(xml_bytes)
    except Exception as exc:  # noqa: BLE001 — defusedxml raises several distinct types for "unsafe/malformed XML"
        raise ParsingError(f"malformed or unsafe DOCX XML: {exc}") from exc

    paragraphs = []
    for paragraph in root.iter(f"{WORD_NS}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{WORD_NS}t"))
        paragraphs.append(text)

    return ParsedDocument(text="\n".join(paragraphs), page_count=None)
