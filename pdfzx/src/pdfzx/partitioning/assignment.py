"""Prompt runner for taxonomy assignment probing."""

from __future__ import annotations

import time
from dataclasses import dataclass

from openai import OpenAI

from pdfzx.prompts.taxonomy_assignment import TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT
from pdfzx.prompts.taxonomy_assignment import TaxonomyAssignmentPromptInput
from pdfzx.prompts.taxonomy_assignment import TaxonomyAssignmentResponse
from pdfzx.prompts.taxonomy_assignment import build_taxonomy_assignment_user_prompt


@dataclass(slots=True)
class TaxonomyAssignmentResult:
    """Result payload for one taxonomy assignment prompt call."""

    prompt_input: dict[str, object]
    parsed_response: dict[str, object]


def _is_rate_limit_error(exc: Exception) -> bool:
    return exc.__class__.__name__ == "RateLimitError" or getattr(exc, "status_code", None) == 429


def assign_taxonomy_child(  # noqa: PLR0913
    *,
    prompt_input: TaxonomyAssignmentPromptInput,
    online_features: bool,
    openai_api_key: str | None,
    openai_model: str,
    client: OpenAI | None = None,
    max_retries: int = 2,
    retry_delay_seconds: float = 2.0,
) -> TaxonomyAssignmentResult:
    """Call the taxonomy assignment prompt for one document."""
    if not online_features:
        msg = "PDFZX_ONLINE_FEATURES is disabled"
        raise ValueError(msg)
    if not openai_api_key:
        msg = "PDFZX_OPENAI_API_KEY is required for taxonomy assignment"
        raise ValueError(msg)
    openai_client = client or OpenAI(api_key=openai_api_key)
    user_prompt = build_taxonomy_assignment_user_prompt(prompt_input)
    attempts = max_retries + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = openai_client.responses.parse(
                model=openai_model,
                instructions=TAXONOMY_ASSIGNMENT_SYSTEM_PROMPT,
                input=user_prompt,
                text_format=TaxonomyAssignmentResponse,
            )
            break
        except Exception as exc:
            last_error = exc
            if not _is_rate_limit_error(exc) or attempt + 1 >= attempts:
                raise
            time.sleep(retry_delay_seconds * (2**attempt))
    else:
        if last_error is not None:
            raise last_error
        msg = "taxonomy assignment request failed without a captured exception"
        raise RuntimeError(msg)
    parsed = response.output_parsed
    if parsed is None:
        msg = "LLM response did not contain a parsed taxonomy assignment payload"
        raise ValueError(msg)
    child_labels = {option.label for option in prompt_input.child_options}
    if parsed.assignment_action == "child" and parsed.assigned_child not in child_labels:
        msg = f"LLM returned unknown child label: {parsed.assigned_child}"
        raise ValueError(msg)
    if parsed.assignment_action == "stay" and parsed.assigned_child is not None:
        msg = "LLM returned assigned_child for a stay action"
        raise ValueError(msg)
    return TaxonomyAssignmentResult(
        prompt_input=prompt_input.model_dump(mode="json"),
        parsed_response=parsed.model_dump(mode="json"),
    )
