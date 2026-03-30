from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.services.llm_document_service import LlmDocumentSuggestionService
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.prompts.llm_document_suggestion import LlmDocumentSuggestionResponse


def test_should_request_false_when_same_document_and_prompt_already_exist(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="abc",
                    md5="def",
                    file_name="sample.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            session.commit()

            service = LlmDocumentSuggestionService(
                session, model_provider="openai", model="gpt-4o-mini"
            )
            response = LlmDocumentSuggestionResponse(
                suggested_file_name="Sample.pdf",
                suggested_labels=["sample"],
                reasoning_summary="test",
            )
            service.store_response(sha256="abc", response=response)
            session.commit()

            decision = service.should_request_for_document(sha256="abc")

            assert decision.should_request is False
            assert decision.prompt_id is not None
    finally:
        engine.dispose()


def test_prompt_upsert_reuses_same_prompt_identity(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            service = LlmDocumentSuggestionService(
                session, model_provider="openai", model="gpt-4o-mini"
            )
            first = service.ensure_prompt()
            session.commit()
            second = service.ensure_prompt()
            session.commit()

            assert first.id == second.id
    finally:
        engine.dispose()


def test_store_response_requires_existing_document(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            service = LlmDocumentSuggestionService(
                session, model_provider="openai", model="gpt-4o-mini"
            )
            response = LlmDocumentSuggestionResponse(
                suggested_file_name="Sample.pdf",
                suggested_labels=["sample"],
                reasoning_summary="test",
            )
            try:
                service.store_response(sha256="missing", response=response)
            except ValueError as exc:
                assert "Document not found" in str(exc)
            else:
                raise AssertionError("Expected ValueError")
    finally:
        engine.dispose()
