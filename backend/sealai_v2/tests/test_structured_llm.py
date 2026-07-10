from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from sealai_v2.core.contracts import LlmResult, ModelConfig
from sealai_v2.llm.client import OpenAiLlmClient
from sealai_v2.llm.structured import StructuredOutputError, generate_structured
from sealai_v2.tests._fakes import ScriptedFakeLlmClient


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


class _Completions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content='{"answer":"ok"}')
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(choices=[choice], model="test-model", usage=None)


def test_openai_compatible_client_sends_strict_json_schema():
    completions = _Completions()
    inner = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client = OpenAiLlmClient(inner, provider="mistral")
    result = asyncio.run(
        client.generate_structured(
            system="S",
            user="U",
            model_config=ModelConfig("test-model"),
            schema_name="test_output",
            json_schema=_Output.model_json_schema(),
        )
    )
    assert result.text == '{"answer":"ok"}'
    response_format = completions.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "test_output"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False


def test_schema_validation_repairs_exactly_once_with_same_model():
    client = ScriptedFakeLlmClient(["not-json", '{"answer":"repaired"}'])
    parsed, result = asyncio.run(
        generate_structured(
            client,
            output_type=_Output,
            schema_name="test_output",
            system="S",
            user="U",
            model_config=ModelConfig("same-model"),
        )
    )
    assert parsed.answer == "repaired"
    assert result.model == "same-model"
    assert len(client.calls) == 2
    assert {call["model"] for call in client.calls} == {"same-model"}


def test_schema_validation_stops_after_one_failed_repair():
    client = ScriptedFakeLlmClient(["bad", "still bad", '{"answer":"too late"}'])
    with pytest.raises(StructuredOutputError):
        asyncio.run(
            generate_structured(
                client,
                output_type=_Output,
                schema_name="test_output",
                system="S",
                user="U",
                model_config=ModelConfig("same-model"),
            )
        )
    assert len(client.calls) == 2


class _NoNativeClient:
    async def generate(self, *, system, user, model_config):
        return LlmResult(text='{"answer":"fallback"}', model=model_config.model)


def test_offline_protocol_fake_uses_local_validation_fallback():
    parsed, _ = asyncio.run(
        generate_structured(
            _NoNativeClient(),
            output_type=_Output,
            schema_name="test_output",
            system="S",
            user="U",
            model_config=ModelConfig("fake"),
        )
    )
    assert parsed.answer == "fallback"
