from __future__ import annotations

from openai import OpenAI

from pdfzx.llm.workflows.base import BatchSuggestionResult
from pdfzx.llm.workflows.base import ProbeSuggestionResult
from pdfzx.llm.workflows.base import batch_prompt_workflow
from pdfzx.llm.workflows.base import probe_prompt_workflow
from pdfzx.llm.workflows.document_suggestion import DocumentSuggestionWorkflow


def probe_document_suggestion(  # noqa: PLR0913
    *,
    sqlite_db_path,
    sha256: str,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    persist: bool = False,
    force: bool = False,
    client: OpenAI | None = None,
) -> ProbeSuggestionResult:
    """Probe the document-suggestion prompt against one stored document."""
    return probe_prompt_workflow(
        workflow=DocumentSuggestionWorkflow(),
        sqlite_db_path=sqlite_db_path,
        sha256=sha256,
        online_features=online_features,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        persist=persist,
        force=force,
        client=client,
    )


def batch_document_suggestion(  # noqa: PLR0913
    *,
    sqlite_db_path,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    require_digital: bool = False,
    require_toc: bool = False,
    limit: int | None = None,
    force: bool = False,
    output_ndjson=None,
    client: OpenAI | None = None,
) -> BatchSuggestionResult:
    """Run the document-suggestion workflow over a filtered batch."""
    return batch_prompt_workflow(
        workflow=DocumentSuggestionWorkflow(),
        workflow_name="llm_document_suggestion",
        sqlite_db_path=sqlite_db_path,
        online_features=online_features,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        require_digital=require_digital,
        require_toc=require_toc,
        limit=limit,
        force=force,
        output_ndjson=output_ndjson,
        client=client,
    )
