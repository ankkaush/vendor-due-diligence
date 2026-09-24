"""Phase 5 acceptance step (architecture.md): run the Phase 3 evaluation
cases through real intake and classification — not the classifier alone
in isolation — and confirm every document is routed to the domain its
ground truth expects.

This is also, incidentally, the first time all ~70 real hand-written
eval documents get pushed through the actual parser rather than just
being read as plain files — a genuine regression check on parsing.py
against real, varied content, not just the crafted unit-test fixtures in
test_parsing.py.
"""

import json
from pathlib import Path

import pytest

from app.intake import create_case, ingest_document

REPO_ROOT = Path(__file__).parent.parent.parent
GROUND_TRUTH_DIR = REPO_ROOT / "eval" / "ground_truth"
CASES_DIR = REPO_ROOT / "eval" / "cases"

MIME_BY_EXTENSION = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Documents that need an explicit domain at ingestion time, for two
# distinct reasons (app/routing.py):
# 1. doc_type="other" has no default at all — routing.py refuses to
#    guess, by design, for any document typed this way.
# 2. case-12's questionnaire has a real default (security) but is
#    deliberately overridden to "both" because it blends domains — the
#    one case where the override changes the outcome rather than merely
#    supplying what "other" lacks.
KNOWN_EXPLICIT_OVERRIDES = {
    ("case-12", "doc-questionnaire"): "both",
    ("case-02", "doc-backup-policy"): "privacy_ai_governance",
    ("case-13", "doc-terms"): "privacy_ai_governance",
    ("case-18", "doc-backup-policy"): "privacy_ai_governance",
}


def _load_all_cases() -> list[dict]:
    cases = []
    for path in sorted(GROUND_TRUTH_DIR.glob("*.json")):
        with path.open() as f:
            cases.append(json.load(f))
    return cases


ALL_CASES = _load_all_cases()


@pytest.mark.parametrize("case_gt", ALL_CASES, ids=[c["case_id"] for c in ALL_CASES])
def test_case_documents_ingest_and_route_to_the_expected_domain(db_session, case_gt):
    case_id = case_gt["case_id"]
    case = create_case(db_session, case_gt["vendor_name"])

    for doc in case_gt["document_manifest"]:
        file_path = CASES_DIR / case_id / doc["filename"]
        assert file_path.exists(), f"missing eval fixture file: {file_path}"

        mime_type = MIME_BY_EXTENSION[file_path.suffix]
        override = KNOWN_EXPLICIT_OVERRIDES.get((case_id, doc["document_id"]))

        document = ingest_document(
            db_session, case,
            filename=doc["filename"],
            mime_type=mime_type,
            doc_type=doc["doc_type"],
            content=file_path.read_bytes(),
            explicit_domain=override,
        )

        assert document.domain == doc["domain"], (
            f"{case_id}/{doc['document_id']}: routed to {document.domain!r}, "
            f"ground truth expects {doc['domain']!r}"
        )


def test_every_ground_truth_domain_override_is_accounted_for():
    """If a future case adds a document whose ground-truth domain doesn't
    match its doc_type's plain default, it needs an entry in
    KNOWN_EXPLICIT_OVERRIDES above (or a fix to the default table) — this
    test fails loudly instead of the parametrized test above silently
    skipping the mismatch."""
    from app.routing import classify_document_domain

    for case_gt in ALL_CASES:
        for doc in case_gt["document_manifest"]:
            key = (case_gt["case_id"], doc["document_id"])
            if key in KNOWN_EXPLICIT_OVERRIDES:
                continue
            assert classify_document_domain(doc["doc_type"]) == doc["domain"], (
                f"{key}: default classification doesn't match ground truth and "
                "isn't in KNOWN_EXPLICIT_OVERRIDES — add it there or fix the "
                "default table in app/routing.py"
            )
