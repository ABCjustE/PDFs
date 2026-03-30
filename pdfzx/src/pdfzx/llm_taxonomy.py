from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.llm.workflows.base import BatchSuggestionResult
from pdfzx.llm.workflows.base import ProbeSuggestionResult
from pdfzx.llm.workflows.base import batch_prompt_workflow
from pdfzx.llm.workflows.base import probe_prompt_workflow
from pdfzx.llm.workflows.taxonomy_suggestion import TaxonomySuggestionWorkflow


def probe_taxonomy_suggestion(  # noqa: PLR0913
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
    """Probe the taxonomy-suggestion prompt against one stored document."""
    return probe_prompt_workflow(
        workflow=TaxonomySuggestionWorkflow(max_toc_entries=max_toc_entries),
        sqlite_db_path=sqlite_db_path,
        sha256=sha256,
        online_features=online_features,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        persist=persist,
        force=force,
        client=client,
    )


def batch_taxonomy_suggestion(  # noqa: PLR0913
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
    """Run the taxonomy-suggestion workflow over a filtered batch."""
    return batch_prompt_workflow(
        workflow=TaxonomySuggestionWorkflow(max_toc_entries=max_toc_entries),
        workflow_name="llm_taxonomy_suggestion",
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
