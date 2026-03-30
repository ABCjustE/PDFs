from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.llm_suggestion import probe_document_suggestion
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionResponse


class _FakeParsedResponse:
    def __init__(self, parsed: LlmDocumentSuggestionResponse) -> None:
        self.output_parsed = parsed


class _FakeResponsesAPI:
    def __init__(self, parsed: LlmDocumentSuggestionResponse) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeParsedResponse(self._parsed)


class _FakeClient:
    def __init__(self, parsed: LlmDocumentSuggestionResponse) -> None:
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
                    file_name="sample_book_3rd.pdf",
                    normalised_name="Sample Book 3rd.pdf",
                    metadata_title="Sample Book Third Edition",
                    metadata_extra_json={"publisher": "Pub"},
                    languages_json=["en"],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            session.commit()
    finally:
        engine.dispose()


def test_probe_document_suggestion_builds_prompt_and_can_persist(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    _seed_document(db_path)
    fake_client = _FakeClient(
        LlmDocumentSuggestionResponse(
            suggested_file_name="Sample Book.pdf",
            suggested_author=None,
            suggested_publisher="Pub",
            suggested_edition="3rd edition",
            suggested_labels=["books"],
            reasoning_summary="Filename contains edition and publisher noise.",
        )
    )

    result = probe_document_suggestion(
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
    assert result.prompt_input["file_name"] == "sample_book_3rd.pdf"
    assert result.parsed_response is not None
    assert result.parsed_response["suggested_file_name"] == "Sample Book.pdf"
    assert len(fake_client.responses.calls) == 1


def test_probe_document_suggestion_skips_existing_same_prompt(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    _seed_document(db_path)
    fake_client = _FakeClient(
        LlmDocumentSuggestionResponse(
            suggested_file_name="Sample Book.pdf",
            suggested_labels=["books"],
            reasoning_summary="test",
        )
    )

    first = probe_document_suggestion(
        sqlite_db_path=db_path,
        sha256="abc",
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        persist=True,
        client=fake_client,
    )
    second = probe_document_suggestion(
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
