"""Prompt contract for assigning one document to an existing taxonomy child."""

from __future__ import annotations

import json
from typing import Annotated
from typing import Literal

from pydantic import BaseModel
from pydantic import Field
from pydantic import StringConstraints

from pdfzx.models import DocumentRecord
from pdfzx.prompts._shared import build_system_prompt

TAXONOMY_ASSIGNMENT_WORKFLOW = "taxonomy_assignment"
TAXONOMY_ASSIGNMENT_PROMPT_VERSION = "v4"

TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT = build_system_prompt(
    role="You are assigning one document to one existing child taxonomy label.",
    input_scope=(
        "a parent taxonomy node, its existing child labels, and one compact document summary"
    ),
    goals=[
        "either assign the document to one existing child label or keep it in the current node",
        "prefer the broadest fitting child at the current layer",
        "prefer the document's apparent topic over literal keywords in the title",
    ],
    evidence_priority=[
        "current path hints",
        "metadata title",
        "document file name and normalised name",
    ],
    rules=[
        "return `assignment_action` as either `child` or `stay`",
        (
            "if `assignment_action` is `child`, return exactly one `assigned_child` "
            "chosen from `child_labels`"
        ),
        "if `assignment_action` is `stay`, return `assigned_child` as null",
        "do not invent a new label",
        "treat the existing current_path as a strong prior for the document's topical area",
        (
            "do not assign by filename keyword alone when current_path or metadata_title "
            "indicates a different subject"
        ),
        "prefer broad current-layer labels over implied deeper subtopics",
        "prefer `stay` over forcing a weak child assignment",
        "set `confidence` to one of: high, medium, low",
        "set `reasoning_summary` to a short non-empty evidence-based explanation",
        "keep output strictly as JSON matching the requested schema",
    ],
)


class TaxonomyAssignmentDocumentSummary(BaseModel):
    """Compact document facts for assignment probing."""

    sha256: str
    file_name: str
    normalised_name: str | None = None
    current_path: str | None = None
    metadata_title: str | None = None


class TaxonomyAssignmentPromptInput(BaseModel):
    """Prompt input for assigning one document under one parent node."""

    node_path: str
    child_labels: list[str] = Field(default_factory=list)
    document: TaxonomyAssignmentDocumentSummary


class TaxonomyAssignmentResponse(BaseModel):
    """Structured output for one taxonomy assignment decision."""

    assignment_action: Literal["child", "stay"]
    assigned_child: str | None = None
    confidence: Literal["high", "medium", "low"]
    reasoning_summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def build_taxonomy_assignment_prompt_input(
    *,
    node_path: str,
    child_labels: list[str],
    record: DocumentRecord,
) -> TaxonomyAssignmentPromptInput:
    """Build the allowed prompt payload for one document assignment."""
    current_path = record.paths[0] if record.paths else None
    return TaxonomyAssignmentPromptInput(
        node_path=node_path,
        child_labels=child_labels,
        document=TaxonomyAssignmentDocumentSummary(
            sha256=record.sha256,
            file_name=record.file_name,
            normalised_name=record.normalised_name,
            current_path=current_path,
            metadata_title=record.metadata.title,
        ),
    )


def build_taxonomy_assignment_user_prompt(
    prompt_input: TaxonomyAssignmentPromptInput,
) -> str:
    """Serialize prompt input for the assignment user message."""
    payload = prompt_input.model_dump(mode="json")
    payload["document"].pop("sha256", None)
    return json.dumps(payload, ensure_ascii=False, indent=2)
