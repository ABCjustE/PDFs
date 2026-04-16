from __future__ import annotations

from pydantic import BaseModel

from pdfzx.llm.workflows.base import _PendingBatchRequest
from pdfzx.llm.workflows.base import _run_prompt_request


class _PromptInput(BaseModel):
    name: str


class _ResponseModel(BaseModel):
    result: str


class _Workflow:
    system_prompt = "system"
    response_model = _ResponseModel

    def build_user_prompt(self, prompt_input: _PromptInput) -> str:
        return prompt_input.model_dump_json()


class _FakeParsedResponse:
    def __init__(self, parsed: _ResponseModel | None) -> None:
        self.output_parsed = parsed


class _FakeResponsesAPI:
    def __init__(self, side_effects: list[object]) -> None:
        self._side_effects = list(side_effects)
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        effect = self._side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class _FakeClient:
    def __init__(self, side_effects: list[object]) -> None:
        self.responses = _FakeResponsesAPI(side_effects)


def test_run_prompt_request_retries_failures_with_exponential_backoff(monkeypatch) -> None:
    sleep_calls: list[float] = []
    monkeypatch.setattr("pdfzx.llm.workflows.base.time.sleep", sleep_calls.append)
    client = _FakeClient(
        [
            RuntimeError("first"),
            RuntimeError("second"),
            _FakeParsedResponse(_ResponseModel(result="ok")),
        ]
    )

    result = _run_prompt_request(
        workflow=_Workflow(),
        openai_client=client,
        openai_model="gpt-4o-mini",
        request=_PendingBatchRequest(
            sha256="a" * 64, prompt_input_model=_PromptInput(name="example")
        ),
    )

    assert result[0] == "a" * 64
    assert result[2] == _ResponseModel(result="ok")
    assert result[3] is None
    assert sleep_calls == [2.0, 4.0]
    assert len(client.responses.calls) == 3


def test_run_prompt_request_gives_up_after_max_retries(monkeypatch) -> None:
    sleep_calls: list[float] = []
    monkeypatch.setattr("pdfzx.llm.workflows.base.time.sleep", sleep_calls.append)
    client = _FakeClient([RuntimeError("first"), RuntimeError("second"), RuntimeError("boom")])

    result = _run_prompt_request(
        workflow=_Workflow(),
        openai_client=client,
        openai_model="gpt-4o-mini",
        request=_PendingBatchRequest(
            sha256="b" * 64, prompt_input_model=_PromptInput(name="example")
        ),
    )

    assert result[0] == "b" * 64
    assert result[2] is None
    assert result[3] == "boom"
    assert sleep_calls == [2.0, 4.0]
    assert len(client.responses.calls) == 3
