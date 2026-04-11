from __future__ import annotations

import json

from pdfzx.models import DocumentRecord
from pdfzx.models import PdfMetadata
from pdfzx.partitioning.proposal import propose_taxonomy_bags
from pdfzx.prompts.taxonomy_partition_proposal import TAXONOMY_PARTITION_PROPOSAL_PROMPT_VERSION
from pdfzx.prompts.taxonomy_partition_proposal import TAXONOMY_PARTITION_PROPOSAL_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_partition_proposal import SampledDocumentSummary
from pdfzx.prompts.taxonomy_partition_proposal import TaxonomyPartitionProposalResponse
from pdfzx.prompts.taxonomy_partition_proposal import build_sampled_document_summary
from pdfzx.prompts.taxonomy_partition_proposal import build_taxonomy_partition_proposal_user_prompt


class _FakeParsedResponse:
    def __init__(self, parsed: TaxonomyPartitionProposalResponse) -> None:
        self.output_parsed = parsed


class _FakeResponsesAPI:
    def __init__(self, parsed: TaxonomyPartitionProposalResponse) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeParsedResponse(self._parsed)


class _FakeClient:
    def __init__(self, parsed: TaxonomyPartitionProposalResponse) -> None:
        self.responses = _FakeResponsesAPI(parsed)


def test_partition_proposal_prompt_user_payload_is_json() -> None:
    payload = build_taxonomy_partition_proposal_user_prompt(
        prompt_input=type(
            "PromptInput",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "batch_index": 0,
                    "taxonomy_bag_before": ["Programming"],
                    "chunk_documents": [
                        {
                            "sha256": "abc",
                            "file_name": "Example.pdf",
                            "normalised_name": "Example.pdf",
                            "current_path": "Books/CS/Example.pdf",
                            "metadata_title": "Example",
                        }
                    ],
                }
            },
        )()
    )

    decoded = json.loads(payload)
    assert decoded["batch_index"] == 0
    assert "sha256" not in decoded["chunk_documents"][0]


def test_partition_proposal_prompt_constants_are_defined() -> None:
    assert TAXONOMY_PARTITION_PROPOSAL_PROMPT_VERSION == "v1"
    assert "accumulating candidate taxonomy categories" in TAXONOMY_PARTITION_PROPOSAL_SYSTEM_PROMPT
    assert "path-safe" in TAXONOMY_PARTITION_PROPOSAL_SYSTEM_PROMPT


def test_build_sampled_document_summary_is_compact() -> None:
    record = DocumentRecord(
        sha256="abc",
        md5="def",
        file_name="Example.pdf",
        normalised_name="Example.pdf",
        paths=["Books/CS/Python/Example.pdf"],
        metadata=PdfMetadata(
            title="Example Title",
            author="Ignored Author",
            creator="Ignored Creator",
        ),
    )

    summary = build_sampled_document_summary(record)

    assert summary.sha256 == "abc"
    assert summary.current_path == "Books/CS/Python/Example.pdf"
    assert summary.metadata_title == "Example Title"


def test_propose_taxonomy_bags_calls_prompt_and_returns_structured_payload() -> None:
    fake_client = _FakeClient(
        TaxonomyPartitionProposalResponse(
            taxonomy_bag_after=["Python", "Workshop Series"],
        )
    )

    result = propose_taxonomy_bags(
        batch_index=0,
        chunk_documents=[
            SampledDocumentSummary(
                sha256="a",
                file_name="Clean Code In Python.pdf",
                normalised_name="Clean Code In Python.pdf",
                current_path="Books/CS/Python/Clean Code In Python.pdf",
                metadata_title="Clean Code in Python",
            )
        ],
        taxonomy_bag_before=["Programming"],
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        client=fake_client,
    )

    assert result.prompt_input["batch_index"] == 0
    assert result.prompt_input["chunk_documents"][0]["sha256"] == "a"
    assert result.parsed_response["taxonomy_bag_after"] == ["Python", "Workshop Series"]
    assert len(fake_client.responses.calls) == 1
