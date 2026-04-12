from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pdfzx.models import DocumentRecord
from pdfzx.partitioning.assignment import assign_taxonomy_child
from pdfzx.prompts.taxonomy_assignment import TAXONOMY_ASSIGNMENT_PROMPT_VERSION
from pdfzx.prompts.taxonomy_assignment import TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_assignment import TaxonomyAssignmentResponse
from pdfzx.prompts.taxonomy_assignment import build_taxonomy_assignment_prompt_input
from pdfzx.prompts.taxonomy_assignment import build_taxonomy_assignment_user_prompt


def test_taxonomy_assignment_prompt_user_payload_is_json() -> None:
    prompt_input = build_taxonomy_assignment_prompt_input(
        node_path="Root",
        child_labels=["Physics", "Mathematics", "Others"],
        record=DocumentRecord(
            sha256="a" * 64,
            md5="b" * 32,
            file_name="Quantum Mechanics Notes.pdf",
            normalised_name="Quantum Mechanics Notes.pdf",
            paths=["Root/old/Quantum Mechanics Notes.pdf"],
            first_seen_job="job-1",
            last_seen_job="job-1",
        ),
    )

    payload = build_taxonomy_assignment_user_prompt(prompt_input)
    decoded = json.loads(payload)
    assert decoded["node_path"] == "Root"
    assert decoded["child_labels"] == ["Physics", "Mathematics", "Others"]
    assert "sha256" not in decoded["document"]


def test_taxonomy_assignment_prompt_constants_are_defined() -> None:
    assert TAXONOMY_ASSIGNMENT_PROMPT_VERSION == "v1"
    assert "choose exactly one existing child label" in TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT


@pytest.mark.parametrize("reasoning_summary", [None, "", "   "])
def test_taxonomy_assignment_response_requires_non_empty_reasoning_summary(
    reasoning_summary: str | None,
) -> None:
    with pytest.raises(ValidationError):
        TaxonomyAssignmentResponse(
            assigned_child="Physics",
            confidence="high",
            reasoning_summary=reasoning_summary,
        )


def test_assign_taxonomy_child_retries_rate_limit() -> None:
    prompt_input = build_taxonomy_assignment_prompt_input(
        node_path="Root",
        child_labels=["Physics", "Mathematics", "Others"],
        record=DocumentRecord(
            sha256="a" * 64,
            md5="b" * 32,
            file_name="Quantum Mechanics Notes.pdf",
            normalised_name="Quantum Mechanics Notes.pdf",
            paths=["Root/old/Quantum Mechanics Notes.pdf"],
            first_seen_job="job-1",
            last_seen_job="job-1",
        ),
    )

    class RateLimitError(Exception):
        status_code = 429

    class FakeResponses:
        def __init__(self) -> None:
            self.calls = 0

        def parse(self, **_: object) -> SimpleNamespace:
            self.calls += 1
            if self.calls == 1:
                msg = "too many requests"
                raise RateLimitError(msg)
            return SimpleNamespace(
                output_parsed=TaxonomyAssignmentResponse(
                    assigned_child="Physics",
                    confidence="high",
                    reasoning_summary="Filename strongly indicates physics.",
                )
            )

    fake_client = SimpleNamespace(responses=FakeResponses())
    result = assign_taxonomy_child(
        prompt_input=prompt_input,
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-test",
        client=fake_client,  # type: ignore[arg-type]
        retry_delay_seconds=0.0,
    )

    assert result.parsed_response["assigned_child"] == "Physics"
    assert fake_client.responses.calls == 2
