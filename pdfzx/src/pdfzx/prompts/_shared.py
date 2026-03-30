from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel

COMMON_HIDDEN_TEXT_RULE = "Do not use or infer any hidden full text."
COMMON_JSON_RULE = "keep output strictly as JSON matching the requested schema"
COMMON_CONFIDENCE_RULE = "`confidence` must be between 0 and 1"
COMMON_REASONING_RULE = "`reasoning_summary` should be concise and evidence-based"


def build_system_prompt(
    *,
    role: str,
    input_scope: str,
    goals: Sequence[str],
    evidence_priority: Sequence[str] = (),
    rules: Sequence[str],
) -> str:
    """Build a compact shared system prompt body."""
    sections = [role, "", f"You will receive only {input_scope}. {COMMON_HIDDEN_TEXT_RULE}", ""]
    sections.extend(["Goals:", *[f"- {goal}" for goal in goals]])
    if evidence_priority:
        sections.extend(["", "Evidence priority:", *[f"- {item}" for item in evidence_priority]])
    sections.extend(["", "Rules:", *[f"- {rule}" for rule in rules]])
    return "\n".join(sections).strip()


def dump_prompt_input(prompt_input: BaseModel) -> str:
    """Serialize structured prompt input for the LLM user message."""
    return json.dumps(prompt_input.model_dump(mode="json"), ensure_ascii=False, indent=2)
