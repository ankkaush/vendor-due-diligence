"""Shared types and output schema for every verification agent (Phase 6's
baseline and Phase 7's investigators alike). One schema, one CaseDocument
shape, one result shape — Gate 6 compares architectures, not grading
standards, so anything that could silently differ between the baseline
and the investigators lives here, in one place, imported by both.
"""

from dataclasses import dataclass
from typing import Any

import jsonschema

FINDINGS_TOOL_NAME = "submit_verification_findings"

FINDINGS_TOOL_DESCRIPTION = (
    "Record the structured verification findings for this vendor evidence package."
)

# Deliberately close to data-model.md's Claim/EvidenceItem shape and to
# eval/schema/ground_truth.schema.json's vocabulary (ADR-008's "ground
# truth reuses the production schema," continued here) — the same enum
# values throughout, so scoring predicted output against ground truth
# doesn't need a translation layer.
FINDINGS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["claims", "injection_detected", "injection_note"],
    "additionalProperties": False,
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "subject", "predicate", "value", "domain", "claim_type",
                    "source_document_id", "source_location", "source_excerpt",
                    "verification_status", "rationale", "evidence",
                ],
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {"type": ["string", "null"]},
                    "temporal_scope": {"type": ["string", "null"]},
                    "domain": {"enum": ["security", "privacy_ai_governance"]},
                    "claim_type": {"enum": [
                        "certification", "policy_statement", "sla_metric", "data_practice",
                        "subprocessor_disclosure", "technical_control", "other",
                    ]},
                    "source_document_id": {"type": "string"},
                    "source_location": {"type": "string"},
                    "source_excerpt": {"type": "string"},
                    "verification_status": {
                        "enum": ["supported", "contradicted", "unverified", "ambiguous"]
                    },
                    "rationale": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["document_id", "location", "excerpt"],
                            "additionalProperties": False,
                            "properties": {
                                "document_id": {"type": "string"},
                                "location": {"type": "string"},
                                "excerpt": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "injection_detected": {"type": "boolean"},
        "injection_note": {"type": "string"},
    },
}


@dataclass
class CaseDocument:
    document_id: str
    filename: str
    text: str
    domain: str  # "security" | "privacy_ai_governance" | "both" — app/routing.py's
    # classification. The baseline (Phase 6) ignores this field and sees every
    # document regardless; the investigators' context_builder (Phase 7) is the
    # only thing that reads it, and that is the entire isolation mechanism
    # (ADR-007) — not a separate permissions system, just which documents a
    # given run ever receives as input in the first place.


@dataclass
class AgentResult:
    claims: list[dict[str, Any]]
    injection_detected: bool
    injection_note: str
    input_tokens: int
    output_tokens: int
    model: str


class InvalidAgentOutputError(ValueError):
    """The model's tool call didn't validate against FINDINGS_INPUT_SCHEMA
    — a real finding about output discipline (ADR-010), not massaged away
    by a lenient parser."""


def build_user_message(documents: list[CaseDocument]) -> str:
    blocks = [
        f'<document id="{doc.document_id}" filename="{doc.filename}">\n{doc.text}\n</document>'
        for doc in documents
    ]
    return "\n".join(blocks)


def validate_tool_output(tool_input: dict[str, Any]) -> None:
    try:
        jsonschema.validate(tool_input, FINDINGS_INPUT_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise InvalidAgentOutputError(str(exc)) from exc
