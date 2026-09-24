"""Parsing tests. test_docx_xxe_attack_is_rejected is the single most
important test in this module — it's the direct verification of the
threat-model.md §3.2 / security.md requirement this whole module exists
to satisfy, not a generic robustness nice-to-have.
"""

import io
import time
import zipfile

import pytest
from pypdf import PdfWriter

from app import parsing
from app.parsing import ParsingError, parse_document

# --- text/markdown -----------------------------------------------------


def test_parse_plain_text():
    result = parse_document(b"Hello, this is plain text.", "text/plain")
    assert result.text == "Hello, this is plain text."
    assert result.page_count is None


def test_parse_markdown():
    result = parse_document(b"# Heading\n\nSome body text.", "text/markdown")
    assert "Heading" in result.text


def test_parse_text_rejects_invalid_utf8():
    with pytest.raises(ParsingError, match="not valid UTF-8"):
        parse_document(b"\xff\xfe\x00\x01invalid", "text/plain")


# --- PDF -----------------------------------------------------------------


def _minimal_valid_pdf(num_pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_parse_pdf_reports_correct_page_count():
    result = parse_document(_minimal_valid_pdf(num_pages=3), "application/pdf")
    assert result.page_count == 3


def test_parse_pdf_rejects_malformed_content():
    with pytest.raises(ParsingError, match="malformed PDF"):
        parse_document(b"%PDF-1.4\nthis is not actually a valid pdf body", "application/pdf")


# --- DOCX ------------------------------------------------------------------

DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _make_docx(document_xml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def _valid_document_xml(text: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{DOCX_NS}">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>""".encode()


def test_parse_docx_extracts_paragraph_text():
    result = parse_document(_make_docx(_valid_document_xml("Hello DOCX")), (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ))
    assert "Hello DOCX" in result.text


def test_parse_docx_xxe_attack_is_rejected():
    """threat-model.md §3.2: a crafted DOCX attempting to read a local
    file via an external XML entity must be rejected outright, not
    silently resolved and not silently ignored — it must raise."""
    xxe_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE w:document [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<w:document xmlns:w="{DOCX_NS}">
  <w:body>
    <w:p><w:r><w:t>&xxe;</w:t></w:r></w:p>
  </w:body>
</w:document>""".encode()

    with pytest.raises(ParsingError, match="malformed or unsafe"):
        parse_document(_make_docx(xxe_payload), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ))


def test_parse_docx_rejects_non_zip_content():
    with pytest.raises(ParsingError, match="not a valid DOCX"):
        parse_document(b"this is not a zip file at all", (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ))


def test_parse_docx_rejects_zip_missing_document_xml():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("some_other_file.txt", "not the right entry")
    with pytest.raises(ParsingError, match="no word/document.xml"):
        parse_document(buf.getvalue(), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ))


def test_parse_docx_rejects_declared_size_over_cap(monkeypatch):
    """Zip-bomb protection (threat-model.md §3.2): the DECLARED
    decompressed size is checked before any decompression happens.
    A tiny cap here proves the check fires; it doesn't require an
    actually enormous file to prove the logic works."""
    monkeypatch.setattr(parsing, "MAX_DECOMPRESSED_BYTES", 10)
    xml = _valid_document_xml("This paragraph is longer than ten bytes.")
    assert len(xml) > 10
    with pytest.raises(ParsingError, match="exceeding the 10-byte cap"):
        parse_document(_make_docx(xml), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ))


# --- Unsupported types / timeout -------------------------------------------


def test_unsupported_mime_type_is_rejected():
    with pytest.raises(ParsingError, match="unsupported mime_type"):
        parse_document(b"whatever", "application/octet-stream")


def test_parse_timeout_fires_on_a_hung_parse():
    """threat-model.md §3.2: parser hang on adversarial input must fail
    explicitly, not hang forever. Tests the _timeout mechanism directly
    with a short window rather than waiting out the real
    PARSE_TIMEOUT_S (15s) in the test suite."""
    with pytest.raises(ParsingError, match="exceeded 1s timeout"):
        with parsing._timeout(1):
            time.sleep(2)


def test_parse_document_takes_bytes_only_never_a_filesystem_path():
    """threat-model.md §3.2's last row: parser errors must not leak
    server file paths to a client. parse_document has no code path that
    could — it only ever reads from an in-memory BytesIO wrapping the
    bytes argument, never touching a real path — checked directly against
    its signature, not just trusted from reading the code."""
    import inspect

    params = inspect.signature(parse_document).parameters
    assert "path" not in params
    assert "filename" not in params
    assert "content" in params


@pytest.mark.parametrize("mime_type,content", [
    ("application/pdf", b"%PDF-not-actually-valid"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"not a zip"),
    ("text/plain", b"\xff\xfe\x00\x01 not valid utf-8"),
])
def test_parse_errors_never_mention_a_filesystem_path(mime_type, content):
    """The generic-client-error half of this mitigation (never showing a
    ParsingError's raw text to an HTTP client) has no endpoint to test
    against yet — no live upload route exists (limitations.md). What's
    testable now: the error text itself never contains anything
    path-shaped, since nothing here ever had a path to begin with."""
    with pytest.raises(ParsingError) as exc_info:
        parse_document(content, mime_type)
    message = str(exc_info.value)
    assert "/" not in message.replace("word/document.xml", "")  # only expected literal slash
    assert "Users" not in message
    assert "tmp" not in message.lower()
