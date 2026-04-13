from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pdfzx.models import DocumentRecord
from pdfzx.partitioning.assignment import assign_taxonomy_child
from pdfzx.prompts.taxonomy_assignment import TAXONOMY_ASSIGNMENT_PROMPT_VERSION
from pdfzx.prompts.taxonomy_assignment import TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_assignment import TaxonomyAssignmentChildOption
from pdfzx.prompts.taxonomy_assignment import TaxonomyAssignmentResponse
from pdfzx.prompts.taxonomy_assignment import build_taxonomy_assignment_prompt_input
from pdfzx.prompts.taxonomy_assignment import build_taxonomy_assignment_user_prompt


def test_taxonomy_assignment_prompt_user_payload_is_json() -> None:
    prompt_input = build_taxonomy_assignment_prompt_input(
        node_path="Root",
        child_options=[
            TaxonomyAssignmentChildOption(
                label="Physics", topic_terms=["Quantum Mechanics", "Electromagnetism"]
            ),
            TaxonomyAssignmentChildOption(label="Mathematics", topic_terms=[]),
            TaxonomyAssignmentChildOption(label="Others", topic_terms=[]),
        ],
        record=DocumentRecord(
            sha256="a" * 64,
            md5="b" * 32,
            file_name="Quantum Mechanics Notes.pdf",
            normalised_name="Quantum Mechanics Notes.pdf",
            paths=[
                "Root/old/Quantum Mechanics Notes.pdf",
                "Books/Physics/Quantum Mechanics Notes.pdf",
            ],
            first_seen_job="job-1",
            last_seen_job="job-1",
        ),
    )

    payload = build_taxonomy_assignment_user_prompt(prompt_input)
    decoded = json.loads(payload)
    assert decoded["node_path"] == "Root"
    assert decoded["child_options"][0] == {
        "label": "Physics",
        "topic_terms": ["Quantum Mechanics", "Electromagnetism"],
    }
    assert "sha256" not in decoded["document"]
    assert decoded["document"]["current_paths"] == [
        "Books/Physics/Quantum Mechanics Notes.pdf",
        "Root/old/Quantum Mechanics Notes.pdf",
    ]


def test_taxonomy_assignment_prompt_constants_are_defined() -> None:
    assert TAXONOMY_ASSIGNMENT_PROMPT_VERSION == "v5"
    assert (
        "either assign the document to one existing child label or keep it in the current node"
        in (TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT)
    )
    assert "current document paths as a strong prior" in TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT
    assert "use child topic terms to disambiguate similar child labels" in (
        TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT
    )
    assert "do not assign by filename keyword alone" in TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT


@pytest.mark.parametrize("reasoning_summary", [None, "", "   "])
def test_taxonomy_assignment_response_requires_non_empty_reasoning_summary(
    reasoning_summary: str | None,
) -> None:
    with pytest.raises(ValidationError):
        TaxonomyAssignmentResponse(
            assignment_action="child",
            assigned_child="Physics",
            confidence="high",
            reasoning_summary=reasoning_summary,
        )


def test_assign_taxonomy_child_retries_rate_limit() -> None:
    prompt_input = build_taxonomy_assignment_prompt_input(
        node_path="Root",
        child_options=[
            TaxonomyAssignmentChildOption(label="Physics", topic_terms=["Mechanics"]),
            TaxonomyAssignmentChildOption(label="Mathematics", topic_terms=[]),
            TaxonomyAssignmentChildOption(label="Others", topic_terms=[]),
        ],
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
                    assignment_action="child",
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
    assert result.parsed_response["assignment_action"] == "child"
    assert fake_client.responses.calls == 2


def test_assign_taxonomy_child_allows_stay_action() -> None:
    prompt_input = build_taxonomy_assignment_prompt_input(
        node_path="Root/Computer Science/Programming",
        child_options=[
            TaxonomyAssignmentChildOption(label="Python", topic_terms=["Django"]),
            TaxonomyAssignmentChildOption(label="Java", topic_terms=["JVM"]),
            TaxonomyAssignmentChildOption(label="C++", topic_terms=["Templates"]),
            TaxonomyAssignmentChildOption(label="Others", topic_terms=[]),
        ],
        record=DocumentRecord(
            sha256="c" * 64,
            md5="d" * 32,
            file_name="Programming Languages Overview.pdf",
            normalised_name="Programming Languages Overview.pdf",
            paths=["Books/CS/Programming/Programming Languages Overview.pdf"],
            first_seen_job="job-1",
            last_seen_job="job-1",
        ),
    )

    class FakeResponses:
        def parse(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                output_parsed=TaxonomyAssignmentResponse(
                    assignment_action="stay",
                    assigned_child=None,
                    confidence="medium",
                    reasoning_summary="This is a broad overview that does not fit one child well.",
                )
            )

    fake_client = SimpleNamespace(responses=FakeResponses())
    result = assign_taxonomy_child(
        prompt_input=prompt_input,
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-test",
        client=fake_client,  # type: ignore[arg-type]
    )

    assert result.parsed_response["assignment_action"] == "stay"
    assert result.parsed_response["assigned_child"] is None
