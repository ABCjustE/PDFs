from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.services.llm_taxonomy_service import LlmTaxonomySuggestionService
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.prompts.llm_taxonomy_suggestion import LlmTaxonomySuggestionResponse


def test_taxonomy_should_request_false_when_same_document_and_prompt_already_exist(tmp_path) -> None:
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

            service = LlmTaxonomySuggestionService(
                session, model_provider="openai", model="gpt-4o-mini"
            )
            response = LlmTaxonomySuggestionResponse(
                suggested_taxonomy_path="Computer Science/Software Engineering",
                suggested_document_type="book",
                confidence=0.7,
                reasoning_summary="test",
            )
            service.store_response(sha256="abc", response=response)
            session.commit()

            decision = service.should_request_for_document(sha256="abc")

            assert decision.should_request is False
            assert decision.prompt_id is not None
    finally:
        engine.dispose()


def test_taxonomy_store_response_requires_existing_document(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        with Session(engine) as session:
            service = LlmTaxonomySuggestionService(
                session, model_provider="openai", model="gpt-4o-mini"
            )
            response = LlmTaxonomySuggestionResponse(
                suggested_taxonomy_path="Computer Science/Software Engineering",
                suggested_document_type="book",
                confidence=0.7,
                reasoning_summary="test",
            )
            with pytest.raises(ValueError, match="Document not found"):
                service.store_response(sha256="missing", response=response)
    finally:
        engine.dispose()
