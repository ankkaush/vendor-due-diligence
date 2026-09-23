"""Validate eval/ground_truth/*.json against eval/schema/ground_truth.schema.json.

This is evaluation-dataset tooling (Phase 3), not part of the vendor
verification application. It checks two things a JSON Schema alone can't:

1. Structural conformance (via the schema).
2. Referential integrity — every claim's source_document_id, every
   evidence_item's document_id, every conflict's claim_ids, and every
   injection_attempt's document_id must actually point at an id declared
   elsewhere in the same case file. A ground-truth file with a dangling
   reference is a labeling bug, and it's cheap to catch here rather than
   discovering it later as a confusing evaluation result.

Usage:
    python eval/validate_ground_truth.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

EVAL_DIR = Path(__file__).parent
SCHEMA_PATH = EVAL_DIR / "schema" / "ground_truth.schema.json"
GROUND_TRUTH_DIR = EVAL_DIR / "ground_truth"


def load_schema() -> dict:
    with SCHEMA_PATH.open() as f:
        return json.load(f)


def referential_errors(case: dict) -> list[str]:
    errors: list[str] = []
    doc_ids = {d["document_id"] for d in case.get("document_manifest", [])}
    claim_ids = {c["claim_id"] for c in case.get("claims", [])}

    seen_claim_ids: set[str] = set()
    for claim in case.get("claims", []):
        cid = claim["claim_id"]
        if cid in seen_claim_ids:
            errors.append(f"duplicate claim_id: {cid}")
        seen_claim_ids.add(cid)

        if claim["source_document_id"] not in doc_ids:
            errors.append(
                f"claim {cid}: source_document_id "
                f"{claim['source_document_id']!r} not in document_manifest"
            )
        for item in claim.get("evidence_items", []):
            if item["document_id"] not in doc_ids:
                errors.append(
                    f"claim {cid}: evidence_item document_id "
                    f"{item['document_id']!r} not in document_manifest"
                )

        planted = claim.get("is_planted_issue")
        issue_type = claim.get("issue_type")
        if planted and issue_type is None:
            errors.append(f"claim {cid}: is_planted_issue is true but issue_type is null")
        if not planted and issue_type is not None:
            errors.append(
                f"claim {cid}: issue_type is set ({issue_type!r}) but "
                f"is_planted_issue is false"
            )

    for conflict in case.get("expected_conflicts", []):
        for ref in conflict["claim_ids"]:
            if ref not in claim_ids:
                errors.append(
                    f"conflict {conflict['conflict_id']}: claim_id "
                    f"{ref!r} not found among claims"
                )

    for injection in case.get("injection_attempts", []):
        if injection["document_id"] not in doc_ids:
            errors.append(
                f"injection {injection['injection_id']}: document_id "
                f"{injection['document_id']!r} not in document_manifest"
            )

    return errors


def main() -> int:
    schema = load_schema()
    validator = Draft202012Validator(schema)

    case_files = sorted(GROUND_TRUTH_DIR.glob("*.json"))
    if not case_files:
        print(f"No ground-truth files found in {GROUND_TRUTH_DIR}")
        return 1

    total_errors = 0
    for path in case_files:
        with path.open() as f:
            case = json.load(f)

        schema_errors = sorted(validator.iter_errors(case), key=lambda e: e.path)
        ref_errors = referential_errors(case) if not schema_errors else []
        errors = [f"schema: {e.message} (at {'/'.join(map(str, e.path))})" for e in schema_errors]
        errors += ref_errors

        if errors:
            total_errors += len(errors)
            print(f"FAIL {path.name}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"OK   {path.name}  ({len(case['claims'])} claims)")

    print(f"\n{len(case_files)} case file(s) checked, {total_errors} error(s).")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
