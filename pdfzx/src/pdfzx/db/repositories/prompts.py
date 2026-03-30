from __future__ import annotations

from datetime import UTC
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pdfzx.db.models import Prompt


class PromptRepository:
    """CRUD helpers for prompt records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_identity(
        self, *, workflow_name: str, model_provider: str, model: str, prompt_version: str
    ) -> Prompt | None:
        stmt = select(Prompt).where(
            Prompt.workflow_name == workflow_name,
            Prompt.model_provider == model_provider,
            Prompt.model == model,
            Prompt.prompt_version == prompt_version,
        )
        return self._session.scalar(stmt)

    def get_active(self, *, workflow_name: str) -> Prompt | None:
        stmt = (
            select(Prompt)
            .where(Prompt.workflow_name == workflow_name, Prompt.active.is_(True))
            .order_by(Prompt.updated_at.desc(), Prompt.id.desc())
        )
        return self._session.scalar(stmt)

    def upsert(
        self,
        *,
        workflow_name: str,
        prompt_text: str,
        model_provider: str,
        model: str,
        prompt_version: str,
        active: bool = True,
    ) -> Prompt:
        now = datetime.now(tz=UTC).replace(tzinfo=None)
        prompt = self.get_by_identity(
            workflow_name=workflow_name,
            model_provider=model_provider,
            model=model,
            prompt_version=prompt_version,
        )
        if prompt is None:
            prompt = Prompt(
                workflow_name=workflow_name,
                prompt_text=prompt_text,
                model_provider=model_provider,
                model=model,
                prompt_version=prompt_version,
                active=active,
                created_at=now,
                updated_at=now,
            )
            self._session.add(prompt)
            self._session.flush()
            return prompt

        prompt.prompt_text = prompt_text
        prompt.active = active
        prompt.updated_at = now
        self._session.flush()
        return prompt
