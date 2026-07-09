"""Phase 3A (live token streaming) — LangSmith hide-gate proof for the STREAMING path.

Safety-critical (audit finding class). langsmith's ``wrap_openai`` has native streaming support: it
accumulates the streamed chunks via an internal ``reduce_fn`` and RECONSTRUCTS a full output dict.
This test proves that the reconstructed streamed content — which DOES carry the completion text —
is then dropped to ``{}`` by the exact same ``_hide_run_outputs`` gate this repo configures in
production (``obs.safe_trace.resolve_langsmith_client_policy`` → ``hide_outputs=True``), so streamed
smalltalk tokens can NEVER leak to LangSmith. It uses SYNTHETIC chunks + a real ``langsmith.Client``
with NO network (nothing is submitted — we assert on the hide function directly, the exact gate the
SDK applies before any run is sent). Follows tests/test_safe_trace.py's stub/assert conventions.

Skipped only if langsmith/openai are absent from the venv (they are present in the running backend);
where present it pins the ACTUAL installed 0.4.x behavior, not a mock of it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langsmith")
pytest.importorskip("openai")

from langsmith import Client as LsClient  # noqa: E402
from langsmith.wrappers._openai import _reduce_chat  # noqa: E402
from openai.types.chat import ChatCompletionChunk  # noqa: E402
from openai.types.chat.chat_completion_chunk import (  # noqa: E402
    Choice,
    ChoiceDelta,
)

from sealai_v2.obs.safe_trace import resolve_langsmith_client_policy  # noqa: E402

# synthetic, non-sensitive smalltalk text (never real customer data)
_SENTINEL = "SENTINEL-STREAMED-SMALLTALK-DO-NOT-LEAK"


def _chunk(content: str, *, finish: str | None = None) -> ChatCompletionChunk:
    return ChatCompletionChunk(
        id="chatcmpl-test",
        object="chat.completion.chunk",
        created=0,
        model="fake-smalltalk",
        choices=[
            Choice(index=0, delta=ChoiceDelta(content=content), finish_reason=finish)
        ],
        usage=None,
    )


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "APP_ENV",
        "SEALAI_V2_LANGSMITH_TRACING_MODE",
        "SEALAI_V2_TRACE_HMAC_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)


def _prod_client() -> LsClient:
    policy = resolve_langsmith_client_policy()
    assert policy.hide_inputs is True and policy.hide_outputs is True
    # api_key set so construction never reads env / attempts discovery; no network happens here.
    return LsClient(
        api_key="test-not-used",
        auto_batch_tracing=False,
        hide_inputs=policy.hide_inputs,
        hide_outputs=policy.hide_outputs,
    )


def test_reconstructed_stream_carries_content_then_hidden_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)  # default env → production → hide both
    chunks = [_chunk("Hal"), _chunk("lo! "), _chunk(_SENTINEL, finish="stop")]

    reconstructed = _reduce_chat(chunks)
    # sanity: the reduce step really DOES reconstruct the streamed content, so the hide is meaningful
    assert _SENTINEL in repr(reconstructed)

    client = _prod_client()
    hidden = client._hide_run_outputs(reconstructed)
    assert hidden == {}  # the reconstructed streamed output is dropped wholesale
    assert _SENTINEL not in repr(hidden)


def test_stream_inputs_also_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    client = _prod_client()
    inputs = {"messages": [{"role": "user", "content": _SENTINEL}]}
    assert client._hide_run_inputs(inputs) == {}


def test_hide_gate_holds_even_if_full_synthetic_requested_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An operator setting the "reveal" mode in production must NOT unhide streamed outputs.
    _clear_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SEALAI_V2_LANGSMITH_TRACING_MODE", "full_synthetic_only")
    reconstructed = _reduce_chat([_chunk(_SENTINEL, finish="stop")])
    client = _prod_client()  # re-resolves policy under this env; still hidden
    assert client._hide_run_outputs(reconstructed) == {}
