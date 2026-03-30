from __future__ import annotations

import json

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.models import DocumentTocEntry
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.llm_taxonomy import batch_taxonomy_suggestion
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


def test_batch_taxonomy_suggestion_filters_digital_and_toc(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    Document(
                        sha256="with-toc",
                        md5="a" * 32,
                        file_name="good.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                    Document(
                        sha256="no-toc",
                        md5="b" * 32,
                        file_name="missing.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=True,
                        force_extracted=False,
                    ),
                    Document(
                        sha256="scanned",
                        md5="c" * 32,
                        file_name="scanned.pdf",
                        metadata_extra_json={},
                        languages_json=[],
                        is_digital=False,
                        force_extracted=False,
                    ),
                ]
            )
            session.add(
                DocumentTocEntry(
                    sha256="with-toc",
                    level=1,
                    title="Preface",
                    page=1,
                    position=0,
                )
            )
            session.commit()
    finally:
        engine.dispose()

    fake_client = _FakeClient(
        LlmTaxonomySuggestionResponse(
            suggested_taxonomy_path="Reference Miscellaneous/Manuals and Reference",
            suggested_document_type="book",
            suggested_new_subcategory=None,
            confidence=0.8,
            reasoning_summary="test",
        )
    )

    result = batch_taxonomy_suggestion(
        sqlite_db_path=db_path,
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        require_digital=True,
        require_toc=True,
        client=fake_client,
    )

    assert result.total_candidates == 1
    assert result.requested == 1
    assert result.persisted == 1
    assert result.skipped_existing == 0
    assert result.skipped_ineligible == 0
    assert result.failed == 0
    assert len(fake_client.responses.calls) == 1


def test_batch_taxonomy_suggestion_writes_output_ndjson(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    output_path = tmp_path / "taxonomy.ndjson"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="with-toc",
                    md5="a" * 32,
                    file_name="good.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            session.add(
                DocumentTocEntry(
                    sha256="with-toc",
                    level=1,
                    title="Preface",
                    page=1,
                    position=0,
                )
            )
            session.commit()
    finally:
        engine.dispose()

    fake_client = _FakeClient(
        LlmTaxonomySuggestionResponse(
            suggested_taxonomy_path="Reference Miscellaneous/Manuals and Reference",
            suggested_document_type="book",
            suggested_new_subcategory=None,
            confidence=0.8,
            reasoning_summary="test",
        )
    )

    batch_taxonomy_suggestion(
        sqlite_db_path=db_path,
        online_features=True,
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        output_ndjson=output_path,
        client=fake_client,
    )

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["workflow"] == "llm_taxonomy_suggestion"
    assert payload["sha256"] == "with-toc"
    assert payload["status"] == "persisted"
    assert payload["prompt_input"]["file_name"] == "good.pdf"
    assert payload["parsed_response"]["suggested_document_type"] == "book"
