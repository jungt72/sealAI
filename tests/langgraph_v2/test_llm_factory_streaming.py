from __future__ import annotations

import pytest

pytest.skip(
    "Legacy LangGraph v2 llm-factory streaming test disabled during agent-path canonization.",
    allow_module_level=True,
)

from app.langgraph_v2.utils import llm_factory


@pytest.mark.asyncio
async def test_run_llm_stream_fake_llm_calls_on_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "1")

    chunks: list[str] = []

    async def on_chunk(part: str) -> None:
        chunks.append(part)

    prompt = "x" * 150  # lang genug für mehrere Fake-Parts
    result = await llm_factory.run_llm_stream(
        model="gpt-test",
        prompt=prompt,
        system="System prompt",
        temperature=0.0,
        max_tokens=100,
        on_chunk=on_chunk,
    )

    assert result.startswith("[FAKE_LLM_RESPONSE]")
    # Fake-Streaming liefert mindestens einen Chunk, meistens mehrere
    assert len(chunks) >= 1
    assert "".join(chunks).strip() == result


@pytest.mark.asyncio
async def test_run_llm_stream_fake_llm_without_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "1")

    prompt = "kurzer prompt"
    result = await llm_factory.run_llm_stream(
        model="gpt-test",
        prompt=prompt,
        system="System prompt",
        temperature=0.0,
        max_tokens=50,
        on_chunk=None,
    )

    assert result.startswith("[FAKE_LLM_RESPONSE]")
