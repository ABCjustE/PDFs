from __future__ import annotations

from openai import OpenAI

from pdfzx.config import DEFAULT_LLM_MAX_TOC_ENTRIES
from pdfzx.llm.workflows.base import ProbeSuggestionResult
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
