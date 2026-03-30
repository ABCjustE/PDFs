from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.db.models import Document
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.llm_toc_review import probe_toc_review_suggestion
from pdfzx.prompts.llm_toc_review_suggestion import LlmTocReviewSuggestionResponse


class _FakeParsedResponse:
    def __init__(self, parsed: LlmTocReviewSuggestionResponse) -> None:
        self.output_parsed = parsed


class _FakeResponsesAPI:
    def __init__(self, parsed: LlmTocReviewSuggestionResponse) -> None:
        self._parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeParsedResponse(self._parsed)


class _FakeClient:
    def __init__(self, parsed: LlmTocReviewSuggestionResponse) -> None:
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
                        title="Preface" if index == 0 else f"Chapter {index}",
                        page=index + 1,
                        position=index,
                    )
                )
            session.commit()
    finally:
        engine.dispose()


def test_probe_toc_review_builds_prompt_and_can_persist(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    _seed_document(db_path)
    fake_client = _FakeClient(
        LlmTocReviewSuggestionResponse(
            toc_is_valid=True,
            toc_matches_document=True,
            preface_page=1,
            preface_label="Preface",
            confidence=0.88,
            reasoning_summary="The ToC is coherent and on-topic.",
        )
    )

    result = probe_toc_review_suggestion(
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
    assert len(result.prompt_input["toc"]) == DEFAULT_LLM_MAX_TOC_ENTRIES
    assert result.prompt_input["toc"][0]["title"] == "Preface"
    assert result.parsed_response is not None
    assert result.parsed_response["preface_page"] == 1
    assert len(fake_client.responses.calls) == 1


def test_probe_toc_review_skips_existing_same_prompt(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    _seed_document(db_path)
    fake_client = _FakeClient(
        LlmTocReviewSuggestionResponse(
            toc_is_valid=True,
            toc_matches_document=True,
            preface_page=1,
            preface_label="Preface",
            confidence=0.88,
            reasoning_summary="The ToC is coherent and on-topic.",
        )
    )

    first = probe_toc_review_suggestion(
        sqlite_db_path=db_path,
        sha256="abc",
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        persist=True,
        client=fake_client,
    )
    second = probe_toc_review_suggestion(
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


def test_probe_toc_review_skips_document_without_toc(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="empty",
                    md5="def",
                    file_name="empty.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            session.commit()
    finally:
        engine.dispose()

    result = probe_toc_review_suggestion(
        sqlite_db_path=db_path,
        sha256="empty",
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        client=_FakeClient(
            LlmTocReviewSuggestionResponse(
                toc_is_valid=True,
                toc_matches_document=True,
                preface_page=None,
                preface_label=None,
                confidence=0.5,
                reasoning_summary="unused",
            )
        ),
    )

    assert result.should_request is False
    assert result.reason == "document has no ToC entries to review"
    assert result.prompt_input is None
    assert result.parsed_response is None
    assert result.persisted is False
