from __future__ import annotations

from pathlib import Path

from openai import OpenAI
from sqlalchemy.orm import Session

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.db.models import Document
from pdfzx.db.session import create_sqlite_engine
from pdfzx.llm.workflows.base import BatchSuggestionResult
from pdfzx.llm.workflows.base import ProbeSuggestionResult
from pdfzx.llm.workflows.base import batch_prompt_workflow
from pdfzx.llm.workflows.base import probe_prompt_workflow
from pdfzx.llm.workflows.toc_review_suggestion import TocReviewSuggestionWorkflow


def probe_toc_review_suggestion(  # noqa: PLR0913
    *,
    sqlite_db_path,
    sha256: str,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    persist: bool = False,
    force: bool = False,
    max_toc_entries: int = DEFAULT_LLM_MAX_TOC_ENTRIES,
    client: OpenAI | None = None,
) -> ProbeSuggestionResult:
    """Probe the ToC-review prompt against one stored document."""
    engine = create_sqlite_engine(sqlite_db_path)
    try:
        with Session(engine) as session:
            document = session.get(Document, sha256)
            if document is not None and not document.toc_entries:
                return ProbeSuggestionResult(
                    should_request=False,
                    reason="document has no ToC entries to review",
                    prompt_id=None,
                    prompt_input=None,
                    parsed_response=None,
                    persisted=False,
                )
    finally:
        engine.dispose()

    return probe_prompt_workflow(
        workflow=TocReviewSuggestionWorkflow(max_toc_entries=max_toc_entries),
        sqlite_db_path=sqlite_db_path,
        sha256=sha256,
        online_features=online_features,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        persist=persist,
        force=force,
        client=client,
    )


def batch_toc_review_suggestion(  # noqa: PLR0913
    *,
    sqlite_db_path,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    require_digital: bool = False,
    require_toc: bool = False,
    limit: int | None = None,
    force: bool = False,
    max_toc_entries: int = DEFAULT_LLM_MAX_TOC_ENTRIES,
    max_concurrency: int = 1,
    output_ndjson: Path | None = None,
    client: OpenAI | None = None,
) -> BatchSuggestionResult:
    """Run the ToC-review workflow over a filtered batch."""
    return batch_prompt_workflow(
        workflow=TocReviewSuggestionWorkflow(max_toc_entries=max_toc_entries),
        workflow_name="llm_toc_review_suggestion",
        sqlite_db_path=sqlite_db_path,
        online_features=online_features,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        require_digital=require_digital,
        require_toc=require_toc,
        limit=limit,
        force=force,
        max_concurrency=max_concurrency,
        output_ndjson=output_ndjson,
        client=client,
    )
