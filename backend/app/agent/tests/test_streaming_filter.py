"""
Unit tests for Phase 0A.4 — Streaming Node Filter.

Contract under test:
- Tokens from BLOCKED nodes (reasoning_node, evidence_tool_node, selection_node)
  must NOT appear in the SSE stream.
- Tokens from ALLOWED nodes (fast_guidance_node, final_response_node)
  MUST appear in the SSE stream.
- The [DONE] sentinel is always the last frame.
- A state_update frame is emitted once when the graph finishes.
"""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.api.sse_runtime import (
    AGENT_SPEAKING_NODES,
    _node_name_from_event,
    agent_sse_generator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stream_event(
    *,
    event: str,
    name: str | None = None,
    node: str | None = None,
    chunk_text: str | None = None,
    output: dict | None = None,
) -> dict:
    """Build a minimal astream_events v2 dict."""
    raw: dict[str, Any] = {"event": event}
    if name:
        raw["name"] = name
    metadata: dict[str, Any] = {}
    if node:
        metadata["langgraph_node"] = node
    if metadata:
        raw["metadata"] = metadata
    data: dict[str, Any] = {}
    if chunk_text is not None:
        chunk = MagicMock()
        chunk.content = chunk_text
        data["chunk"] = chunk
    if output is not None:
        data["output"] = output
    raw["data"] = data
    return raw


async def _collect_frames(gen: AsyncGenerator[str, None]) -> list[dict]:
    """Collect all SSE frames from a generator, parse JSON payload."""
    frames = []
    async for raw_frame in gen:
        line = raw_frame.strip()
        if not line:
            continue
        if line == "data: [DONE]":
            frames.append({"type": "[DONE]"})
        elif line.startswith("data: "):
            frames.append(json.loads(line[len("data: "):]))
    return frames


def _make_graph_mock(events: list[dict]) -> Any:
    """Return a mock graph whose astream_events yields the given events."""
    async def _astream():
        for evt in events:
            yield evt

    graph = MagicMock()
    graph.astream_events = MagicMock(return_value=_astream())
    return graph


# ---------------------------------------------------------------------------
# 1. AGENT_SPEAKING_NODES constant
# ---------------------------------------------------------------------------

class TestSpeakingNodesConstant:
    def test_allowed_nodes_present(self):
        assert "fast_guidance_node" in AGENT_SPEAKING_NODES
        assert "final_response_node" in AGENT_SPEAKING_NODES

    def test_internal_nodes_absent(self):
        for blocked in ("reasoning_node", "evidence_tool_node", "selection_node"):
            assert blocked not in AGENT_SPEAKING_NODES, f"{blocked} must be blocked"


# ---------------------------------------------------------------------------
# 2. _node_name_from_event helper
# ---------------------------------------------------------------------------

class TestNodeNameFromEvent:
    def test_langgraph_node_in_metadata(self):
        evt = {"metadata": {"langgraph_node": "fast_guidance_node"}}
        assert _node_name_from_event(evt) == "fast_guidance_node"

    def test_top_level_name_fallback(self):
        evt = {"name": "reasoning_node", "metadata": {}}
        assert _node_name_from_event(evt) == "reasoning_node"

    def test_metadata_takes_priority_over_name(self):
        evt = {"name": "LangGraph", "metadata": {"langgraph_node": "final_response_node"}}
        assert _node_name_from_event(evt) == "final_response_node"

    def test_none_for_empty_event(self):
        assert _node_name_from_event({}) is None


# ---------------------------------------------------------------------------
# 3. Token streaming filter
# ---------------------------------------------------------------------------

class TestTokenStreamFilter:
    @pytest.mark.asyncio
    async def test_reasoning_node_tokens_are_blocked(self):
        """Tokens from reasoning_node must NOT appear in the stream."""
        events = [
            _make_stream_event(
                event="on_chat_model_stream",
                node="reasoning_node",
                chunk_text="internal reasoning token",
            ),
            _make_stream_event(event="on_chain_end", name="LangGraph", output={}),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        text_frames = [f for f in frames if f.get("type") == "text_chunk"]
        assert text_frames == [], "reasoning_node tokens must be filtered out"

    @pytest.mark.asyncio
    async def test_evidence_tool_node_tokens_are_blocked(self):
        """Tokens from evidence_tool_node must NOT appear in the stream."""
        events = [
            _make_stream_event(
                event="on_chat_model_stream",
                node="evidence_tool_node",
                chunk_text="tool token",
            ),
            _make_stream_event(event="on_chain_end", name="LangGraph", output={}),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        text_frames = [f for f in frames if f.get("type") == "text_chunk"]
        assert text_frames == []

    @pytest.mark.asyncio
    async def test_selection_node_tokens_are_blocked(self):
        """Tokens from selection_node must NOT appear in the stream."""
        events = [
            _make_stream_event(
                event="on_chat_model_stream",
                node="selection_node",
                chunk_text="selection token",
            ),
            _make_stream_event(event="on_chain_end", name="LangGraph", output={}),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        text_frames = [f for f in frames if f.get("type") == "text_chunk"]
        assert text_frames == []

    @pytest.mark.asyncio
    async def test_fast_guidance_node_tokens_pass_through(self):
        """Tokens from fast_guidance_node MUST reach the client."""
        events = [
            _make_stream_event(
                event="on_chat_model_stream",
                node="fast_guidance_node",
                chunk_text="FKM ist ein Fluorelastomer.",
            ),
            _make_stream_event(event="on_chain_end", name="LangGraph", output={}),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        text_frames = [f for f in frames if f.get("type") == "text_chunk"]
        assert len(text_frames) == 1
        assert text_frames[0]["text"] == "FKM ist ein Fluorelastomer."

    @pytest.mark.asyncio
    async def test_final_response_node_tokens_pass_through(self):
        """Tokens from final_response_node MUST reach the client."""
        events = [
            _make_stream_event(
                event="on_chat_model_stream",
                node="final_response_node",
                chunk_text="Empfehlung: FKM A75.",
            ),
            _make_stream_event(event="on_chain_end", name="LangGraph", output={}),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        text_frames = [f for f in frames if f.get("type") == "text_chunk"]
        assert len(text_frames) == 1
        assert text_frames[0]["text"] == "Empfehlung: FKM A75."

    @pytest.mark.asyncio
    async def test_mixed_stream_only_allowed_tokens_pass(self):
        """Mix of allowed + blocked nodes: only allowed tokens get through."""
        events = [
            _make_stream_event(
                event="on_chat_model_stream",
                node="reasoning_node",
                chunk_text="reasoning token — blocked",
            ),
            _make_stream_event(
                event="on_chat_model_stream",
                node="fast_guidance_node",
                chunk_text="visible answer",
            ),
            _make_stream_event(
                event="on_chat_model_stream",
                node="evidence_tool_node",
                chunk_text="tool processing — blocked",
            ),
            _make_stream_event(event="on_chain_end", name="LangGraph", output={}),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        text_frames = [f for f in frames if f.get("type") == "text_chunk"]
        assert len(text_frames) == 1
        assert text_frames[0]["text"] == "visible answer"


# ---------------------------------------------------------------------------
# 4. Stream structure guarantees
# ---------------------------------------------------------------------------

class TestStreamStructure:
    @pytest.mark.asyncio
    async def test_done_sentinel_always_last(self):
        events = [
            _make_stream_event(event="on_chain_end", name="LangGraph", output={}),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        assert frames[-1]["type"] == "[DONE]"

    @pytest.mark.asyncio
    async def test_state_update_emitted_on_completion(self):
        output = {
            "sealing_state": {"governance": {}},
            "working_profile": {"medium": "water"},
            "run_meta": {"model_id": "gpt-4o-mini", "path": "fast"},
        }
        events = [
            _make_stream_event(event="on_chain_end", name="LangGraph", output=output),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        state_frames = [f for f in frames if f.get("type") == "state_update"]
        assert len(state_frames) == 1
        sf = state_frames[0]
        assert sf["run_meta"]["model_id"] == "gpt-4o-mini"
        assert sf["run_meta"]["path"] == "fast"

    @pytest.mark.asyncio
    async def test_run_meta_forwarded_in_state_update(self):
        """run_meta from graph output is forwarded to the client in state_update."""
        output = {
            "run_meta": {
                "model_id": "gpt-4o-mini",
                "prompt_version": "fast_guidance_prompt_v1",
                "policy_version": "interaction_policy_v2",
                "path": "fast",
            }
        }
        events = [
            _make_stream_event(event="on_chain_end", name="LangGraph", output=output),
        ]
        graph = _make_graph_mock(events)
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        state_frames = [f for f in frames if f.get("type") == "state_update"]
        run_meta = state_frames[0]["run_meta"]
        assert run_meta["prompt_version"] == "fast_guidance_prompt_v1"
        assert run_meta["policy_version"] == "interaction_policy_v2"

    @pytest.mark.asyncio
    async def test_error_still_sends_done(self):
        """Even on exception, [DONE] must be the last frame."""
        async def _boom():
            yield {"event": "on_chain_start", "data": {}, "metadata": {}, "name": "x"}
            raise RuntimeError("simulated failure")

        graph = MagicMock()
        graph.astream_events = MagicMock(return_value=_boom())
        frames = await _collect_frames(agent_sse_generator({}, graph=graph))

        assert frames[-1]["type"] == "[DONE]"
        error_frames = [f for f in frames if f.get("type") == "error"]
        assert len(error_frames) == 1
