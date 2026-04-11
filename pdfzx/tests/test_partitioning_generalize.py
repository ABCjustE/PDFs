from __future__ import annotations

from pdfzx.partitioning.generalize import generalize_taxonomy_bag
from pdfzx.prompts.taxonomy_partition_generalize import TaxonomyPartitionGeneralizeResponse


class _FakeParsedResponse:
    def __init__(self, parsed: TaxonomyPartitionGeneralizeResponse) -> None:
        self.output_parsed = parsed


class _FakeResponsesAPI:
    def __init__(self, parsed: TaxonomyPartitionGeneralizeResponse) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeParsedResponse(self._parsed)


class _FakeClient:
    def __init__(self, parsed: TaxonomyPartitionGeneralizeResponse) -> None:
        self.responses = _FakeResponsesAPI(parsed)


def test_generalize_taxonomy_bag_calls_prompt_and_returns_structured_payload() -> None:
    fake_client = _FakeClient(
        TaxonomyPartitionGeneralizeResponse(
            taxonomy_bag_after=["Physics", "Mathematics", "Computer Science"],
        )
    )

    result = generalize_taxonomy_bag(
        taxonomy_bag_before=["Quantum Mechanics", "Mathematics Analysis"],
        candidate_counts={"Physics": 4, "Mathematics": 3},
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        client=fake_client,
    )

    assert result.prompt_input["candidate_counts"]["Physics"] == 4
    assert result.parsed_response["taxonomy_bag_after"] == [
        "Physics",
        "Mathematics",
        "Computer Science",
    ]
    assert len(fake_client.responses.calls) == 1
