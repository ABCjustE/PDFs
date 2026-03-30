from __future__ import annotations

from sqlalchemy.orm import Session

from pdfzx.db.models import Document
from pdfzx.db.services.llm_toc_review_service import LlmTocReviewSuggestionService
from pdfzx.db.session import create_sqlite_engine
from pdfzx.db.session import init_sqlite_db
from pdfzx.prompts.llm_toc_review_suggestion import LlmTocReviewSuggestionResponse


def test_llm_toc_review_service_skips_existing_same_prompt(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    init_sqlite_db(db_path)
    engine = create_sqlite_engine(db_path)

    try:
        with Session(engine) as session:
            session.add(
                Document(
                    sha256="abc",
                    md5="def",
                    file_name="signals.pdf",
                    metadata_extra_json={},
                    languages_json=[],
                    is_digital=True,
                    force_extracted=False,
                )
            )
            session.commit()

            service = LlmTocReviewSuggestionService(
                session, model_provider="openai", model="gpt-4o-mini"
            )
            first = service.should_request_for_document(sha256="abc")
            assert first.should_request is True

            service.store_response(
                sha256="abc",
                response=LlmTocReviewSuggestionResponse(
                    toc_is_valid=True,
                    toc_matches_document=True,
                    preface_page=3,
                    preface_label="Preface",
                    confidence=0.87,
                    reasoning_summary="ToC matches the document topic.",
                ),
            )
            session.commit()

            second = service.should_request_for_document(sha256="abc")
            assert second.should_request is False
            assert second.prompt_id == first.prompt_id
    finally:
        engine.dispose()
