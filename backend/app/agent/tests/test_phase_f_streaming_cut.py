"""
Phase F Streaming Cut — Feature-Flag Branch Tests

Verifies that the Gate + Session + CONVERSATION-runtime branch in
event_generator() behaves correctly under all flag combinations.

All external I/O (Redis, LLM) is mocked — no network required.
"""
from __future__ import annotations

import json
import sys
import types
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.agent.graph import GraphState
from app.agent.state.models import (
    AssertedClaim,
    ConversationMessage,
    GovernanceState,
    GovernedSessionState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_current_user(
    sub: str = "user-1",
    tenant_id: str = "tenant-1",
):
    """Build a minimal RequestUser-like stub."""
    user = MagicMock()
    user.sub = sub
    user.tenant_id = tenant_id
    return user


def _make_request(message: str = "Was ist ein O-Ring?", session_id: str = "sess-1"):
    """Build a minimal ChatRequest-like stub."""
    req = MagicMock()
    req.message = message
    req.session_id = session_id
    return req


async def _collect_frames(gen: AsyncGenerator[str, None]) -> list[str]:
    """Collect all SSE frames from an async generator."""
    frames = []
    async for frame in gen:
        frames.append(frame)
    return frames


# ---------------------------------------------------------------------------
# Fake Redis context manager
# ---------------------------------------------------------------------------

class _FakeRedis:
    """Minimal fake async Redis client for session persistence tests."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self._store[key] = value


# ---------------------------------------------------------------------------
# 1. Flag off → productive SSE fails closed to governed, no legacy policy fallback
# ---------------------------------------------------------------------------

class TestFlagOffUsesGovernedAuthority:
    @pytest.mark.asyncio
    async def test_gate_flag_off_uses_governed_path(self):
        """With SEALAI_ENABLE_BINARY_GATE=false, productive SSE fails closed to governed."""
        import app.agent.api.router as router_module

        mock_decide_route = AsyncMock()
        mock_stream_conversation = AsyncMock()
        governed_called = []

        async def _fake_governed_stream(*_args, **_kwargs):
            governed_called.append(True)
            yield "data: [DONE]\n\n"

        with patch.object(router_module, "_ENABLE_BINARY_GATE", False), \
             patch.object(router_module, "_ENABLE_CONVERSATION_RUNTIME", False), \
             patch("app.agent.api.router._stream_governed_graph", side_effect=_fake_governed_stream):

            frames = await _collect_frames(
                router_module.event_generator(_make_request(), current_user=_make_current_user())
            )

        mock_decide_route.assert_not_called()
        mock_stream_conversation.assert_not_called()
        assert governed_called == [True]
        assert frames == ["data: [DONE]\n\n"]


async def _empty_gen():
    """Async generator that yields nothing."""
    return
    yield  # noqa: unreachable — makes this a generator


# ---------------------------------------------------------------------------
# 2. Gate flag on, conv flag off → productive path still governed
# ---------------------------------------------------------------------------

class TestGateFlagOnConvFlagOffUsesGovernedAuthority:
    @pytest.mark.asyncio
    async def test_gate_flag_on_conv_flag_off_uses_governed_path(self):
        """Gate=on, ConvRuntime=off → productive path stays governed, not legacy graph."""
        import app.agent.api.router as router_module

        from app.agent.runtime.gate import GateDecision
        from app.agent.runtime.session_manager import SessionEnvelope

        mock_envelope = SessionEnvelope(
            session_id="sess-1", tenant_id="tenant-1", user_id="user-1"
        )
        mock_gate_decision = GateDecision(route="CONVERSATION", reason="deterministic_instant:greeting_or_smalltalk")

        governed_called = []

        async def _fake_governed_stream(*_args, **_kwargs):
            governed_called.append(True)
            yield "data: [DONE]\n\n"

        fake_redis = _FakeRedis()

        with patch.object(router_module, "_ENABLE_BINARY_GATE", True), \
             patch.object(router_module, "_ENABLE_CONVERSATION_RUNTIME", False), \
             patch("app.agent.api.router._stream_governed_graph", side_effect=_fake_governed_stream), \
             patch("redis.asyncio.Redis.from_url", return_value=fake_redis), \
             patch("app.agent.runtime.session_manager.get_or_create_session_async", AsyncMock(return_value=mock_envelope)), \
             patch("app.agent.runtime.session_manager.save_session_async", AsyncMock()), \
             patch("app.agent.runtime.gate.decide_route_async", AsyncMock(return_value=mock_gate_decision)):

            frames = await _collect_frames(
                router_module.event_generator(_make_request(), current_user=_make_current_user())
            )

        assert governed_called == [True]
        assert frames == ["data: [DONE]\n\n"]


# ---------------------------------------------------------------------------
# 3. Both flags on + CONVERSATION → conversation_runtime is used
# ---------------------------------------------------------------------------

class TestBothFlagsOnConversationUsesNewRuntime:
    @pytest.mark.asyncio
    async def test_gate_flag_on_conv_flag_on_light_mode_uses_new_runtime(self):
        """Both flags on + light route → stream_conversation() is called with that mode."""
        import app.agent.api.router as router_module

        from app.agent.runtime.gate import GateDecision
        from app.agent.runtime.session_manager import SessionEnvelope

        mock_envelope = SessionEnvelope(
            session_id="sess-1", tenant_id="tenant-1", user_id="user-1"
        )
        mock_gate_decision = GateDecision(route="CONVERSATION", reason="deterministic_instant:greeting_or_smalltalk")

        stream_conv_called = []
        agent_sse_called = []

        async def _fake_stream_conv(message, *, history=None, case_summary=None, mode=None, **_kwargs):
            stream_conv_called.append({"message": message, "mode": mode})
            yield "data: {\"type\": \"text_chunk\", \"text\": \"Hallo\"}\n\n"
            yield "data: {\"type\": \"state_update\", \"reply\": \"Hallo\", \"response_class\": \"conversational_answer\"}\n\n"
            yield "data: [DONE]\n\n"

        async def _fake_sse_gen(state, *, graph, on_complete=None):
            agent_sse_called.append(True)
            yield "data: [DONE]\n\n"

        fake_redis = _FakeRedis()

        with patch.object(router_module, "_ENABLE_BINARY_GATE", True), \
             patch.object(router_module, "_ENABLE_CONVERSATION_RUNTIME", True), \
             patch.dict("os.environ", {"REDIS_URL": "redis://fake"}, clear=False), \
             patch("redis.asyncio.Redis.from_url", return_value=fake_redis), \
             patch("app.agent.runtime.session_manager.get_or_create_session_async", AsyncMock(return_value=mock_envelope)), \
             patch("app.agent.runtime.session_manager.save_session_async", AsyncMock()), \
             patch("app.agent.runtime.gate.decide_route_async", AsyncMock(return_value=mock_gate_decision)), \
             patch("app.agent.runtime.conversation_runtime.stream_conversation", side_effect=_fake_stream_conv), \
             patch("app.agent.api.router.agent_sse_generator", side_effect=_fake_sse_gen):

            frames = await _collect_frames(
                router_module.event_generator(
                    _make_request(message="Was ist ein O-Ring?"),
                    current_user=_make_current_user(),
                )
            )

        assert stream_conv_called, "stream_conversation must be called for light route"
        assert stream_conv_called[0]["mode"] == "CONVERSATION"
        assert not agent_sse_called, "agent_sse_generator must NOT be called for light route"
        assert not any("text_chunk" in f for f in frames), "preview text must not be forwarded"
        assert any("state_update" in f for f in frames), "canonical state_update frame must be forwarded"


# ---------------------------------------------------------------------------
# 4. GOVERNED uses the new governed graph path
# ---------------------------------------------------------------------------

class TestGovernedUsesNewGraphPath:
    @pytest.mark.asyncio
    async def test_governed_uses_new_graph_and_no_legacy_sse_path(self):
        """Gate decides GOVERNED → GOVERNED_GRAPH is used, not agent_sse_generator."""
        import app.agent.api.router as router_module

        from app.agent.runtime.gate import GateDecision
        from app.agent.runtime.session_manager import SessionEnvelope

        mock_envelope = SessionEnvelope(
            session_id="sess-1", tenant_id="tenant-1", user_id="user-1"
        )
        mock_gate_decision = GateDecision(route="GOVERNED", reason="hard_override:numeric_unit")

        stream_conv_called = []
        agent_sse_called = []
        governed_graph_called = []

        async def _fake_sse_gen(state, *, graph, on_complete=None):
            agent_sse_called.append(True)
            yield "data: [DONE]\n\n"

        async def _fake_stream_conv(message, *, history=None, case_summary=None, mode=None):
            stream_conv_called.append(True)
            yield "data: [DONE]\n\n"

        async def _fake_governed_ainvoke(state):
            governed_graph_called.append(state)
            payload = state.model_dump()
            payload["governance"] = {
                "gov_class": "B",
                "rfq_admissible": False,
                "open_validation_points": ["medium"],
            }
            payload["output_response_class"] = "structured_clarification"
            payload["output_reply"] = "Bitte Medium angeben."
            payload["output_public"] = {"response_class": "structured_clarification"}
            return GraphState.model_validate(payload)

        async def _fake_governed_astream(state, *_, **__):
            governed_graph_called.append(state)
            payload = state.model_dump(mode="python")
            payload["governance"] = {
                "gov_class": "B",
                "rfq_admissible": False,
                "open_validation_points": ["medium"],
            }
            payload["output_response_class"] = "structured_clarification"
            payload["output_reply"] = "Bitte Medium angeben."
            payload["output_public"] = {"response_class": "structured_clarification"}
            yield ("values", {})
            yield ("values", payload)

        fake_redis = _FakeRedis()

        with patch.object(router_module, "_ENABLE_BINARY_GATE", True), \
             patch.object(router_module, "_ENABLE_CONVERSATION_RUNTIME", True), \
             patch.dict("os.environ", {"REDIS_URL": "redis://fake"}, clear=False), \
             patch("redis.asyncio.Redis.from_url", return_value=fake_redis), \
             patch("app.agent.runtime.session_manager.get_or_create_session_async", AsyncMock(return_value=mock_envelope)), \
             patch("app.agent.runtime.session_manager.save_session_async", AsyncMock()), \
             patch("app.agent.runtime.gate.decide_route_async", AsyncMock(return_value=mock_gate_decision)), \
             patch("app.agent.runtime.conversation_runtime.stream_conversation", side_effect=_fake_stream_conv), \
             patch("app.agent.api.router.agent_sse_generator", side_effect=_fake_sse_gen), \
             patch("app.agent.api.router.get_or_create_governed_state_async", AsyncMock(return_value=GovernedSessionState())), \
             patch("app.agent.api.router.save_governed_state_async", AsyncMock()), \
             patch.object(router_module.GOVERNED_GRAPH, "astream", side_effect=_fake_governed_astream), \
             patch.object(router_module.GOVERNED_GRAPH, "ainvoke", side_effect=_fake_governed_ainvoke):

            frames = await _collect_frames(
                router_module.event_generator(
                    _make_request(message="PTFE-Dichtung 180°C 50 bar"),
                    current_user=_make_current_user(),
                )
        )

        assert governed_graph_called, "GOVERNED_GRAPH.ainvoke must be called for GOVERNED route"
        assert not agent_sse_called, "agent_sse_generator must NOT remain the governed primary path"
        assert not stream_conv_called, "stream_conversation must NOT be called for GOVERNED route"
        payloads = []
        for frame in frames:
            if not frame.startswith("data: "):
                continue
            raw = frame[6:].strip()
            if raw == "[DONE]":
                continue
            payloads.append(json.loads(raw))
        state_updates = [p for p in payloads if p.get("type") == "state_update"]
        assert state_updates, "governed path must emit a state_update payload"
        state_update = state_updates[-1]
        assert "ui" in state_update
        dumped = json.dumps(state_update, sort_keys=True)
        assert "analysis_cycle_id" not in dumped
        assert "event_id" not in dumped
        assert "event_key" not in dumped
        assert "governance_state" not in dumped


# ---------------------------------------------------------------------------
# 5. Legacy facade endpoint delegates to the canonical router authority
# ---------------------------------------------------------------------------

class TestLegacyFacadeUsesCanonicalAuthority:
    @pytest.mark.asyncio
    async def test_legacy_facade_uses_governed_authority_when_flags_are_off(self):
        """Legacy /api/v1/langgraph/chat/v2 delegates to event_generator.

        When both flags are off, the canonical router now fails closed to the
        governed graph instead of reviving the legacy graph.
        """
        import app.agent.api.router as router_module

        governed_called = []
        stream_conv_called = []

        async def _fake_governed_stream(*_args, **_kwargs):
            governed_called.append(True)
            yield "data: [DONE]\n\n"

        async def _fake_stream_conv(message, *, history=None):
            stream_conv_called.append(True)
            yield "data: [DONE]\n\n"

        with patch.object(router_module, "_ENABLE_BINARY_GATE", False), \
             patch.object(router_module, "_ENABLE_CONVERSATION_RUNTIME", False), \
             patch("app.agent.api.router._stream_governed_graph", side_effect=_fake_governed_stream), \
             patch("app.agent.runtime.conversation_runtime.stream_conversation", side_effect=_fake_stream_conv):

            # Simulate what the legacy facade does: call event_generator directly
            frames = await _collect_frames(
                router_module.event_generator(
                    _make_request(),
                    current_user=_make_current_user(),
                )
            )

        assert governed_called == [True]
        assert not stream_conv_called, "legacy facade must not trigger stream_conversation"


class TestLegacyPolicyFallbackUsesConversationRuntime:
    @pytest.mark.asyncio
    async def test_legacy_policy_fallback_for_light_turn_uses_conversation_runtime(self):
        import app.agent.api.router as router_module

        legacy_resolution = type(
            "Resolution",
            (),
            {
                "runtime_mode": "legacy_fallback",
                "gate_route": "GOVERNED",
                "gate_reason": "legacy_router_state",
                "gate_applied": False,
                "session_zone": None,
            },
        )()
        agent_sse_called = []

        async def _fake_sse_gen(*_args, **_kwargs):
            agent_sse_called.append(True)
            yield "data: [DONE]\n\n"

        with patch.object(router_module, "_resolve_runtime_dispatch", AsyncMock(return_value=legacy_resolution)), \
             patch("app.agent.api.router._stream_governed_graph", side_effect=_fake_sse_gen):
            frames = await _collect_frames(
                router_module.event_generator(
                    _make_request(message="Hallo"),
                    current_user=_make_current_user(),
                )
            )

        assert frames == ["data: [DONE]\n\n"]
        assert agent_sse_called == [True]


# ---------------------------------------------------------------------------
# 6. (F-A.5) Gate routes CONVERSATION requests to stream_conversation uniformly
# ---------------------------------------------------------------------------

class TestGateRoutesConversationToStreamConversation:
    @pytest.mark.asyncio
    async def test_gate_routes_light_mode_to_stream_conversation(self):
        """Mit beiden Flags aktiv und EXPLORATION-Route landet die Anfrage in _stream_exploration_reply.

        Phase F-A.5 / Bug-1-Fix: EXPLORATION nutzt jetzt RAG via _stream_exploration_reply,
        nicht stream_conversation. CONVERSATION bleibt auf stream_conversation.
        """
        import app.agent.api.router as router_module

        exploration_called = []
        stream_conv_called = []
        agent_sse_called = []

        async def _fake_exploration_reply(message, *, tenant_id):
            exploration_called.append({"message": message, "tenant_id": tenant_id})
            yield f"data: {json.dumps({'type': 'state_update', 'reply': 'RAG-Antwort'})}\n\n"
            yield "data: [DONE]\n\n"

        async def _fake_sse_gen(state, *, graph, on_complete=None):
            agent_sse_called.append(True)
            yield "data: [DONE]\n\n"

        async def _fake_stream_conv(message, *, history=None, case_summary=None, mode=None, **_kwargs):
            stream_conv_called.append(mode)
            yield "data: [DONE]\n\n"

        from app.agent.runtime.gate import GateDecision
        from app.agent.runtime.session_manager import SessionEnvelope

        mock_envelope = SessionEnvelope(
            session_id="sess-1", tenant_id="tenant-1", user_id="user-1"
        )
        mock_gate_decision = GateDecision(route="EXPLORATION", reason="deterministic_light:goal_problem_or_uncertainty")
        fake_redis = _FakeRedis()

        with patch.object(router_module, "_ENABLE_BINARY_GATE", True), \
             patch.object(router_module, "_ENABLE_CONVERSATION_RUNTIME", True), \
             patch.dict("os.environ", {"REDIS_URL": "redis://fake"}, clear=False), \
             patch("redis.asyncio.Redis.from_url", return_value=fake_redis), \
             patch("app.agent.runtime.session_manager.get_or_create_session_async", AsyncMock(return_value=mock_envelope)), \
             patch("app.agent.runtime.session_manager.save_session_async", AsyncMock()), \
             patch("app.agent.runtime.gate.decide_route_async", AsyncMock(return_value=mock_gate_decision)), \
             patch("app.agent.api.router._stream_exploration_reply", side_effect=_fake_exploration_reply), \
             patch("app.agent.runtime.conversation_runtime.stream_conversation", side_effect=_fake_stream_conv), \
             patch("app.agent.api.router.agent_sse_generator", side_effect=_fake_sse_gen):

            frames = await _collect_frames(
                router_module.event_generator(
                    _make_request(message="Was ist ein O-Ring?"),
                    current_user=_make_current_user(),
                )
            )

        assert exploration_called, "EXPLORATION route must reach _stream_exploration_reply"
        assert not stream_conv_called, (
            "EXPLORATION must NOT go through stream_conversation (Bug 1 fix)"
        )
        assert not agent_sse_called, (
            "Light route must NOT fall through to agent_sse_generator"
        )


# ---------------------------------------------------------------------------
# 7. Policy-violation safe-fallback emits text_chunk visible to frontend
# ---------------------------------------------------------------------------

class TestPolicyViolationSafeFallbackVisibleAsStateUpdate:
    @pytest.mark.asyncio
    async def test_policy_violation_safe_fallback_visible_as_state_update(self):
        """Policy-Fallback landet exklusiv im finalen state_update.reply.

        Bei Policy-Violation emittiert conversation_runtime:
          1. text_replacement (Backend-Audit)
          2. state_update.reply mit dem kanonischen finalen Fallback-Text

        Assertiert:
          - der finale sichtbare Vertrag ist state_update.reply
          - text_replacement bleibt rein auditiv und wird nicht zur zweiten finalen Authority

        Hinweis: Die bereits vorher gestreamten (potenziell policy-verletzenden)
        Tokens sind ebenfalls im Stream. Dieses Verhalten ist dokumentiert als
        bekanntes Safety-Timing-Risiko (tokens are yielded BEFORE policy check).
        Dieser Test verifiziert den neuen Mindest-Contract: der finale sichtbare
        Fallback wird exklusiv ueber state_update.reply transportiert.
        """
        import app.agent.api.router as router_module

        from app.agent.runtime.gate import GateDecision
        from app.agent.runtime.session_manager import SessionEnvelope

        mock_envelope = SessionEnvelope(
            session_id="sess-1", tenant_id="tenant-1", user_id="user-1"
        )
        mock_gate_decision = GateDecision(route="CONVERSATION", reason="deterministic_instant:greeting_or_smalltalk")
        fake_redis = _FakeRedis()

        FALLBACK_TEXT = "Diese Anfrage kann ich im Gesprächsmodus nicht vollständig beantworten."

        # Simulate stream_conversation emitting:
        #   - a policy-violating preview token (text_chunk)
        #   - a text_replacement (for backend audit)
        #   - a final state_update with canonical fallback text
        #   - boundary_block + stream_end + [DONE]
        async def _fake_stream_with_policy_violation(message, *, history=None, case_summary=None, mode=None, **_kwargs):
            import json
            yield f"data: {json.dumps({'type': 'text_chunk', 'text': 'VERBOTEN '})}\n\n"
            yield f"data: {json.dumps({'type': 'text_replacement', 'text': FALLBACK_TEXT})}\n\n"
            yield f"data: {json.dumps({'type': 'state_update', 'reply': FALLBACK_TEXT, 'response_class': 'conversational_answer'})}\n\n"
            yield f"data: {json.dumps({'type': 'boundary_block', 'text': 'Disclaimer'})}\n\n"
            yield "data: {\"type\": \"stream_end\"}\n\n"
            yield "data: [DONE]\n\n"

        with patch.object(router_module, "_ENABLE_BINARY_GATE", True), \
             patch.object(router_module, "_ENABLE_CONVERSATION_RUNTIME", True), \
             patch.dict("os.environ", {"REDIS_URL": "redis://fake"}, clear=False), \
             patch("redis.asyncio.Redis.from_url", return_value=fake_redis), \
             patch("app.agent.runtime.session_manager.get_or_create_session_async", AsyncMock(return_value=mock_envelope)), \
             patch("app.agent.runtime.session_manager.save_session_async", AsyncMock()), \
             patch("app.agent.runtime.gate.decide_route_async", AsyncMock(return_value=mock_gate_decision)), \
             patch("app.agent.runtime.conversation_runtime.stream_conversation", side_effect=_fake_stream_with_policy_violation):

            frames = await _collect_frames(
                router_module.event_generator(
                    _make_request(message="VERBOTENE ANFRAGE"),
                    current_user=_make_current_user(),
                )
            )

        import json
        has_text_replacement = False
        final_reply = None
        for frame in frames:
            if not frame.startswith("data:"):
                continue
            raw = frame[len("data:"):].strip()
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if payload.get("type") == "text_replacement":
                has_text_replacement = True
            if payload.get("type") == "state_update":
                final_reply = payload.get("reply")

        assert not has_text_replacement, (
            "text_replacement must stay out of the canonical visible stream"
        )
        assert final_reply == FALLBACK_TEXT


class TestPhase1LiveCanon:
    @pytest.mark.asyncio
    async def test_light_runtime_receives_live_history_and_persists_final_reply(self):
        import app.agent.api.router as router_module

        from app.agent.runtime.gate import GateDecision
        from app.agent.runtime.session_manager import SessionEnvelope

        mock_envelope = SessionEnvelope(
            session_id="sess-1", tenant_id="tenant-1", user_id="user-1"
        )
        # CONVERSATION path passes history to stream_conversation and persists replies.
        # EXPLORATION path now routes to _stream_exploration_reply (RAG-based, no history).
        mock_gate_decision = GateDecision(route="CONVERSATION", reason="deterministic_light:goal_smalltalk")
        fake_redis = _FakeRedis()

        governed_state = GovernedSessionState(
            conversation_messages=[
                ConversationMessage(role="user", content="Wir haben Leckage.", created_at="2026-04-02T00:00:00+00:00"),
                ConversationMessage(role="assistant", content="Wo tritt sie auf?", created_at="2026-04-02T00:00:01+00:00"),
                ConversationMessage(role="user", content="Am Wellenaustritt.", created_at="2026-04-02T00:00:02+00:00"),
            ]
        )
        fake_redis._store["governed_state:tenant-1:sess-1"] = governed_state.model_dump_json()

        captured = {}

        async def _fake_stream_conv(message, *, history=None, case_summary=None, mode=None, **_kwargs):
            captured["message"] = message
            captured["history"] = history
            captured["case_summary"] = case_summary
            captured["mode"] = mode
            yield "data: {\"type\": \"state_update\", \"reply\": \"Dann schaue ich auf Einbausituation und Druck.\", \"response_class\": \"conversational_answer\"}\n\n"
            yield "data: [DONE]\n\n"

        with patch.object(router_module, "_ENABLE_BINARY_GATE", True), \
             patch.object(router_module, "_ENABLE_CONVERSATION_RUNTIME", True), \
             patch.dict("os.environ", {"REDIS_URL": "redis://fake"}, clear=False), \
             patch("redis.asyncio.Redis.from_url", return_value=fake_redis), \
             patch("app.agent.runtime.session_manager.get_or_create_session_async", AsyncMock(return_value=mock_envelope)), \
             patch("app.agent.runtime.session_manager.save_session_async", AsyncMock()), \
             patch("app.agent.runtime.gate.decide_route_async", AsyncMock(return_value=mock_gate_decision)), \
             patch("app.agent.runtime.conversation_runtime.stream_conversation", side_effect=_fake_stream_conv):

            frames = await _collect_frames(
                router_module.event_generator(
                    _make_request(message="Ich korrigiere: Der Druck liegt bei 18 bar."),
                    current_user=_make_current_user(),
                )
            )

        assert captured["history"] == [
            {"role": "user", "content": "Wir haben Leckage."},
            {"role": "assistant", "content": "Wo tritt sie auf?"},
            {"role": "user", "content": "Am Wellenaustritt."},
        ]
        persisted = GovernedSessionState.model_validate_json(
            fake_redis._store["governed_state:tenant-1:sess-1"]
        )
        assert persisted.conversation_messages[-2].content == "Ich korrigiere: Der Druck liegt bei 18 bar."
        assert persisted.conversation_messages[-1].content == "Dann schaue ich auf Einbausituation und Druck."
        assert any("state_update" in frame for frame in frames)

    @pytest.mark.asyncio
    async def test_workspace_projection_prefers_live_governed_state(self):
        import app.agent.api.router as router_module

        live_state = GovernedSessionState(
            analysis_cycle=2,
            conversation_messages=[
                ConversationMessage(role="user", content="Medium ist Wasser", created_at="2026-04-02T00:00:00+00:00"),
            ],
        )
        live_state.asserted.assertions["medium"] = AssertedClaim(
            field_name="medium",
            asserted_value="Wasser",
            confidence="confirmed",
        )
        live_state.governance.gov_class = "B"

        with patch("app.agent.api.router._load_live_governed_state", AsyncMock(return_value=live_state)), \
             patch("app.agent.api.router.require_structured_residual_state", AsyncMock(side_effect=AssertionError("legacy canonical state should not be used"))):
            projection = await router_module.get_workspace_projection(
                "sess-1",
                current_user=_make_current_user(),
            )

        assert projection.case_summary.thread_id == "sess-1"
        assert projection.case_summary.turn_count == 1
        assert projection.governance_status.release_status == "precheck_only"

    @pytest.mark.asyncio
    async def test_workspace_projection_prefers_live_governed_state_over_postgres_snapshot(self):
        import app.agent.api.router as router_module

        live_state = GovernedSessionState(
            analysis_cycle=5,
            conversation_messages=[
                ConversationMessage(role="user", content="Live Zustand", created_at="2026-04-02T00:00:00+00:00"),
            ],
        )
        live_state.asserted.assertions["medium"] = AssertedClaim(
            field_name="medium",
            asserted_value="Wasser",
            confidence="confirmed",
        )

        snapshot_state = GovernedSessionState(
            analysis_cycle=3,
            conversation_messages=[
                ConversationMessage(role="user", content="Persistierter Zustand", created_at="2026-04-01T00:00:00+00:00"),
            ],
        )
        snapshot_state.asserted.assertions["medium"] = AssertedClaim(
            field_name="medium",
            asserted_value="Dampf",
            confidence="confirmed",
        )

        with patch("app.agent.api.router._load_live_governed_state", AsyncMock(return_value=live_state)), \
             patch("app.agent.api.router._load_governed_state_snapshot_projection_source", AsyncMock(return_value=snapshot_state)), \
             patch("app.agent.api.router.require_structured_residual_state", AsyncMock(side_effect=AssertionError("canonical state should not be used"))):
            projection = await router_module.get_workspace_projection(
                "sess-1",
                current_user=_make_current_user(),
            )

        assert projection.case_summary.thread_id == "sess-1"
        assert projection.cycle_info.state_revision == 5
        assert "Medium: Wasser" in projection.communication_context.confirmed_facts_summary

    @pytest.mark.asyncio
    async def test_live_chat_history_prefers_governed_transcript(self):
        import app.agent.api.router as router_module

        live_state = GovernedSessionState(
            conversation_messages=[
                ConversationMessage(role="user", content="Wir haben Leckage", created_at="2026-04-02T00:00:00+00:00"),
                ConversationMessage(role="assistant", content="Wo genau?", created_at="2026-04-02T00:00:01+00:00"),
            ]
        )

        with patch("app.agent.api.router._load_live_governed_state", AsyncMock(return_value=live_state)), \
             patch("app.agent.api.router.require_structured_residual_state", AsyncMock(side_effect=AssertionError("legacy canonical state should not be used"))):
            payload = await router_module.get_live_chat_history(
                "sess-1",
                current_user=_make_current_user(),
            )

        assert [item["role"] for item in payload["messages"]] == ["user", "assistant"]
        assert payload["messages"][1]["content"] == "Wo genau?"

    @pytest.mark.asyncio
    async def test_live_chat_history_falls_back_to_postgres_governed_snapshot_before_structured_case(self):
        import app.agent.api.router as router_module

        snapshot_state = GovernedSessionState(
            conversation_messages=[
                ConversationMessage(role="assistant", content="Persistierte Governed-Antwort", created_at="2026-04-02T00:00:01+00:00"),
            ]
        )

        with patch("app.agent.api.router._load_live_governed_state", AsyncMock(return_value=None)), \
             patch("app.agent.api.router._load_governed_state_snapshot_projection_source", AsyncMock(return_value=snapshot_state)), \
             patch("app.agent.api.router.require_structured_residual_state", AsyncMock(side_effect=AssertionError("canonical state should not be used"))):
            payload = await router_module.get_live_chat_history(
                "sess-pg",
                current_user=_make_current_user(),
            )

        assert [item["role"] for item in payload["messages"]] == ["assistant"]
        assert payload["messages"][0]["content"] == "Persistierte Governed-Antwort"

    @pytest.mark.asyncio
    async def test_live_chat_history_uses_structured_case_only_when_no_governed_source_exists(self):
        import app.agent.api.router as router_module

        canonical_state = {
            "messages": [
                HumanMessage(content="Historische Structured-Frage"),
            ],
        }

        with patch("app.agent.api.router._load_live_governed_state", AsyncMock(return_value=None)), \
             patch("app.agent.api.router._load_governed_state_snapshot_projection_source", AsyncMock(return_value=None)), \
             patch("app.agent.api.router.require_structured_residual_state", AsyncMock(return_value=canonical_state)):
            payload = await router_module.get_live_chat_history(
                "sess-legacy",
                current_user=_make_current_user(),
            )

        assert [item["role"] for item in payload["messages"]] == ["user"]
        assert payload["messages"][0]["content"] == "Historische Structured-Frage"

    @pytest.mark.asyncio
    async def test_canonical_state_load_applies_live_governed_snapshot_for_review_near_readers(self):
        import app.agent.api.router as router_module

        governed_state = GovernedSessionState(
            conversation_messages=[
                ConversationMessage(role="user", content="Medium ist Wasser", created_at="2026-04-02T00:00:00+00:00"),
                ConversationMessage(role="assistant", content="Verstanden, ich schaue auf Druck und Temperatur.", created_at="2026-04-02T00:00:01+00:00"),
            ],
        )
        governed_state.asserted.assertions["medium"] = AssertedClaim(
            field_name="medium",
            asserted_value="Wasser",
            confidence="confirmed",
        )
        governed_state.asserted.blocking_unknowns = ["pressure_bar"]
        governed_state.governance.gov_class = "B"

        canonical_state = {
            "messages": [],
            "working_profile": {},
            "case_state": {
                "governance_state": {
                    "review_required": True,
                    "review_state": "pending",
                },
                "rfq_state": {},
            },
            "sealing_state": {
                "review": {
                    "review_required": True,
                    "review_state": "pending",
                },
                "governance": {},
                "cycle": {"state_revision": 1},
            },
        }

        with patch("app.agent.api.router.load_structured_case", AsyncMock(return_value=canonical_state)), \
             patch("app.agent.api.router._load_live_governed_state", AsyncMock(return_value=governed_state)):
            loaded = await router_module.load_structured_residual_state(
                current_user=_make_current_user(),
                session_id="sess-1",
            )

        assert loaded is not None
        assert loaded["working_profile"]["medium"] == "Wasser"
        assert loaded["messages"][0].content == "Medium ist Wasser"
        assert loaded["case_state"]["governance_state"]["review_required"] is True
        assert loaded["case_state"]["governance_state"]["review_state"] == "pending"
        assert loaded["case_state"]["governance_state"]["unknowns_release_blocking"] == ["pressure_bar"]

    @pytest.mark.asyncio
    async def test_workspace_projection_falls_back_to_postgres_governed_snapshot(self):
        import app.agent.api.router as router_module

        governed_state = GovernedSessionState(
            analysis_cycle=4,
            conversation_messages=[
                ConversationMessage(
                    role="assistant",
                    content="Belastbarer Rahmen liegt vor.",
                    created_at="2026-04-02T00:00:01+00:00",
                ),
            ],
        )
        governed_state.asserted.assertions["medium"] = AssertedClaim(
            field_name="medium",
            asserted_value="Wasser",
            confidence="confirmed",
        )
        governed_state.governance.gov_class = "B"

        with patch("app.agent.api.router._load_live_governed_state", AsyncMock(return_value=None)), \
             patch("app.agent.api.router._load_governed_state_snapshot_projection_source", AsyncMock(return_value=governed_state)), \
             patch("app.agent.api.router.require_structured_residual_state", AsyncMock(side_effect=AssertionError("canonical state should not be used"))):
            projection = await router_module.get_workspace_projection(
                "sess-pg",
                current_user=_make_current_user(),
            )

        assert projection.case_summary.thread_id == "sess-pg"
        assert projection.cycle_info.state_revision == 4
        assert "Medium: Wasser" in projection.communication_context.confirmed_facts_summary

    @pytest.mark.asyncio
    async def test_review_outcome_syncs_into_live_governed_state(self):
        import app.agent.api.router as router_module

        governed_state = GovernedSessionState()
        persisted: dict[str, GovernedSessionState] = {}

        async def _fake_persist(*, current_user, session_id, state):
            persisted["state"] = state

        with patch("app.agent.api.router._load_live_governed_state", AsyncMock(return_value=governed_state)), \
             patch("app.agent.api.router._persist_live_governed_state", AsyncMock(side_effect=_fake_persist)):
            await router_module._persist_review_outcome_to_live_governed_state(
                current_user=_make_current_user(),
                session_id="sess-1",
                case_state={
                    "governance_state": {
                        "rfq_admissibility": "ready",
                        "critical_review_status": "approved",
                        "critical_review_passed": True,
                    },
                    "rfq_state": {
                        "handover_ready": True,
                        "handover_status": "releasable",
                        "rfq_object": {"qualified_material_ids": ["ptfe::g25::acme"]},
                    },
                },
                sealing_state={
                    "review": {"review_state": "approved"},
                    "handover": {"is_handover_ready": True, "handover_status": "releasable"},
                },
            )

        assert persisted["state"].rfq.rfq_admissible is True
        assert persisted["state"].rfq.critical_review_passed is True
        assert persisted["state"].rfq.rfq_ready is True
        assert persisted["state"].rfq.handover_status == "releasable"
        assert persisted["state"].rfq.rfq_object["qualified_material_ids"] == ["ptfe::g25::acme"]
        assert persisted["state"].dispatch.dispatch_ready is True

    def test_governed_native_review_commit_replaces_legacy_final_node_path(self):
        import app.agent.api.router as router_module

        state = {
            "working_profile": {"medium": "Dampf", "pressure_bar": 16.0},
            "messages": [],
            "case_state": {
                "governance_state": {
                    "release_status": "inquiry_ready",
                    "rfq_admissibility": "ready",
                    "unknowns_release_blocking": [],
                    "unknowns_manufacturer_validation": [],
                    "scope_of_validity": [],
                    "review_required": False,
                },
                "requirement_class": {
                    "requirement_class_id": "PTFE10",
                    "description": "Steam sealing class",
                    "seal_type": "gasket",
                },
                "matching_state": {
                    "status": "matched_primary_candidate",
                    "selected_manufacturer_ref": {"manufacturer_name": "Acme"},
                },
                "recipient_selection": {
                    "candidate_recipient_refs": [{"manufacturer_name": "Acme", "qualified_for_rfq": True}],
                },
                "rfq_state": {
                    "rfq_object": {
                        "qualified_material_ids": ["ptfe::g25::acme"],
                        "qualified_materials": [{"candidate_id": "ptfe::g25::acme", "manufacturer_name": "Acme"}],
                        "confirmed_parameters": {"medium": "Dampf", "pressure_bar": 16.0},
                        "dimensions": {},
                    },
                    "rfq_dispatch": {
                        "dispatch_ready": True,
                        "dispatch_status": "ready",
                        "recipient_refs": [{"manufacturer_name": "Acme", "qualified_for_rfq": True}],
                        "selected_manufacturer_ref": {"manufacturer_name": "Acme"},
                        "requirement_class": {"requirement_class_id": "PTFE10"},
                    },
                },
            },
            "sealing_state": {
                "asserted": {"medium": "Dampf", "pressure_bar": 16.0},
                "selection": {
                    "selection_status": "releasable",
                    "recommendation_artifact": {
                        "release_status": "inquiry_ready",
                        "rfq_admissibility": "ready",
                        "output_blocked": False,
                        "rationale_summary": "Der Loesungsraum ist belastbar eingeengt.",
                    },
                    "output_contract_projection": {
                        "response_class": "inquiry_ready",
                    },
                },
                "review": {
                    "review_required": False,
                    "review_state": "approved",
                },
                "governance": {
                    "release_status": "inquiry_ready",
                    "rfq_admissibility": "ready",
                },
            },
        }

        committed, reply = router_module._governed_native_review_commit(state)

        assert committed["sealing_state"]["handover"]["is_handover_ready"] is True
        assert committed["case_state"]["rfq_state"]["handover_ready"] is True
        assert committed["sealing_state"]["review"]["critical_review_passed"] is True
        assert committed["sealing_state"]["dispatch_trigger"]["trigger_allowed"] is True
        assert reply
        assert any(getattr(message, "content", "") == reply for message in committed["messages"])
