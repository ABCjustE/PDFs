from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.db.models import Document
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.llm_taxonomy import probe_taxonomy_suggestion
from pdfzx.prompts.llm_taxonomy_suggestion import LlmTaxonomySuggestionResponse


class _FakeParsedResponse:
    def __init__(self, parsed: LlmTaxonomySuggestionResponse) -> None:
        self.output_parsed = parsed


class _FakeResponsesAPI:
    def __init__(self, parsed: LlmTaxonomySuggestionResponse) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeParsedResponse(self._parsed)


class _FakeClient:
    def __init__(self, parsed: LlmTaxonomySuggestionResponse) -> None:
        self.responses = _FakeResponsesAPI(parsed)


def _seed_document(db_path) -> None:
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="abc",
                    md5="def",
                    file_name="bayesian_methods.pdf",
                    normalised_name="Bayesian Methods.pdf",
                    metadata_title="Bayesian Methods",
                    metadata_extra_json={"publisher": "Pub"},
                    languages_json=["en"],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            for index in range(35):
                session.add(
                    DocumentTocEntry(
                        sha256="abc",
                        level=1,
                        title=f"Chapter {index}",
                        page=index + 1,
                        position=index,
                    )
                )
            session.commit()
    finally:
        engine.dispose()


def test_probe_taxonomy_suggestion_builds_prompt_and_can_persist(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    _seed_document(db_path)
    fake_client = _FakeClient(
        LlmTaxonomySuggestionResponse(
            suggested_taxonomy_path="Artificial Intelligence/Bayesian Methods",
            suggested_document_type="book",
            suggested_new_subcategory=None,
            confidence=0.82,
            reasoning_summary="Filename indicates Bayesian methods.",
        )
    )

    result = probe_taxonomy_suggestion(
        sqlite_db_path=db_path,
        sha256="abc",
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        persist=True,
        client=fake_client,
    )

    assert result.should_request is True
    assert result.persisted is True
    assert result.prompt_input is not None
    assert result.prompt_input["file_name"] == "bayesian_methods.pdf"
    assert len(result.prompt_input["toc"]) == DEFAULT_LLM_MAX_TOC_ENTRIES
    assert result.prompt_input["toc"][0]["title"] == "Chapter 0"
    assert (
        result.prompt_input["toc"][-1]["title"]
        == f"Chapter {DEFAULT_LLM_MAX_TOC_ENTRIES - 1}"
    )
    assert result.parsed_response is not None
    assert result.parsed_response["suggested_document_type"] == "book"
    assert len(fake_client.responses.calls) == 1


def test_probe_taxonomy_suggestion_skips_existing_same_prompt(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    _seed_document(db_path)
    fake_client = _FakeClient(
        LlmTaxonomySuggestionResponse(
            suggested_taxonomy_path="Artificial Intelligence/Bayesian Methods",
            suggested_document_type="book",
            confidence=0.82,
            reasoning_summary="test",
        )
    )

    first = probe_taxonomy_suggestion(
        sqlite_db_path=db_path,
        sha256="abc",
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        persist=True,
        client=fake_client,
    )
    second = probe_taxonomy_suggestion(
        sqlite_db_path=db_path,
        sha256="abc",
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        persist=False,
        client=fake_client,
    )

    assert first.persisted is True
    assert second.should_request is False
    assert second.parsed_response is None
    assert len(fake_client.responses.calls) == 1
