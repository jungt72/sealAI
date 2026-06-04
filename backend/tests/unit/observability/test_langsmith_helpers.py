from __future__ import annotations

import os
import sys
import types

import pytest

from app.observability.langsmith import (
    configure_langsmith_environment,
    emit_redacted_observation_span,
    langsmith_capture_llm_content,
    langsmith_enabled,
    langsmith_redacted_observation_spans,
    langsmith_trace_langgraph_children,
    langsmith_tracing_disabled,
    wrap_openai_client,
)
from app.observability.sealai_quality import redact_trace_value


def test_wrap_openai_client_is_noop_when_langsmith_disabled(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_CAPTURE_LLM_CONTENT", raising=False)

    client = object()

    assert langsmith_enabled() is False
    assert wrap_openai_client(client) is client


def test_wrap_openai_client_is_noop_when_raw_llm_capture_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test")
    monkeypatch.delenv("LANGSMITH_CAPTURE_LLM_CONTENT", raising=False)

    client = object()

    assert langsmith_enabled() is True
    assert langsmith_capture_llm_content() is False
    assert wrap_openai_client(client) is client


def test_langgraph_child_tracing_defaults_to_disabled(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACE_LANGGRAPH_CHILDREN", raising=False)

    assert langsmith_trace_langgraph_children() is False


def test_langgraph_child_tracing_can_be_enabled(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACE_LANGGRAPH_CHILDREN", "true")

    assert langsmith_trace_langgraph_children() is True


def test_redacted_observation_spans_default_to_enabled(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_REDACTED_OBSERVATION_SPANS", raising=False)

    assert langsmith_redacted_observation_spans() is True


def test_redacted_observation_spans_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_REDACTED_OBSERVATION_SPANS", "false")

    assert langsmith_redacted_observation_spans() is False


def test_structured_outputs_keep_auditable_shape_but_redact_text() -> None:
    safe = redact_trace_value(
        {
            "nodes": ["turn_boundary", "output_contract"],
            "status": "expected_interrupt",
            "message": "Bitte dichte meinen privaten Pumpenfall ab.",
        },
        key="outputs",
    )

    assert safe["nodes"] == ["turn_boundary", "output_contract"]
    assert safe["status"] == "expected_interrupt"
    assert safe["message"]["redacted"] is True
    assert safe["message"]["kind"] == "content"


def test_tracing_disabled_context_is_safe_without_langsmith_package() -> None:
    with langsmith_tracing_disabled(disabled=True):
        marker = "ok"

    assert marker == "ok"


def test_tracing_disabled_context_preserves_body_attribute_errors(monkeypatch) -> None:
    exits: list[type[BaseException] | None] = []

    class FakeTracingContext:
        def __enter__(self) -> None:
            return None

        def __exit__(self, exc_type, exc, traceback) -> bool:  # noqa: ANN001
            exits.append(exc_type)
            return False

    fake_langsmith = types.SimpleNamespace(
        tracing_context=lambda *, enabled=False: FakeTracingContext()
    )
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)

    with pytest.raises(AttributeError, match="body failure"):
        with langsmith_tracing_disabled(disabled=True):
            raise AttributeError("body failure")

    assert exits == [AttributeError]


def test_tracing_disabled_context_cleanup_failure_does_not_break_user_path(
    monkeypatch,
) -> None:
    class BrokenExitTracingContext:
        def __enter__(self) -> None:
            return None

        def __exit__(self, exc_type, exc, traceback) -> bool:  # noqa: ANN001
            raise RuntimeError("langsmith cleanup failed")

    fake_langsmith = types.SimpleNamespace(
        tracing_context=lambda *, enabled=False: BrokenExitTracingContext()
    )
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)

    with langsmith_tracing_disabled(disabled=True):
        marker = "ok"

    assert marker == "ok"


def test_configure_langsmith_sets_modern_and_legacy_env(monkeypatch) -> None:
    for key in (
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGCHAIN_PROJECT",
    ):
        monkeypatch.delenv(key, raising=False)

    enabled = configure_langsmith_environment(
        tracing_enabled=True,
        api_key="lsv2-test",
        project="sealai-test",
    )

    assert enabled is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "lsv2-test"
    assert os.environ["LANGCHAIN_API_KEY"] == "lsv2-test"
    assert os.environ["LANGSMITH_PROJECT"] == "sealai-test"
    assert os.environ["LANGCHAIN_PROJECT"] == "sealai-test"


@pytest.mark.asyncio
async def test_redacted_observation_span_is_noop_when_langsmith_disabled(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    await emit_redacted_observation_span(
        span_name="sealai.test",
        component="test",
        inputs={"message": "secret customer wording"},
        outputs={"answer": "secret answer"},
    )
