"""
Phase 0E — Patch 4: Regression tests for working_profile / asserted drift.

Covers:
1. Unauthenticated chat_endpoint now injects policy_path (Phase 0E fix).
   Meta/blocked paths must fire consistently regardless of auth state.
2. sync_working_profile_to_state does NOT write wp values into asserted_state
   (the Wave-1 protection remains intact).
3. working_profile keys appearing in the meta response only via asserted_state,
   not directly from wp (already covered in E2E, but unit-level regression here).
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# 1. Unauthenticated path policy injection
# ---------------------------------------------------------------------------

class TestAnonPathPolicyInjection:
    """The unauthenticated chat_endpoint must apply gate routing (W3.4)."""

    @pytest.mark.asyncio
    async def test_anon_meta_query_sets_conversation_policy_path(self):
        """A meta/status query on the unauthenticated path must route to CONVERSATION."""
        from app.agent.api.router import chat_endpoint, SESSION_STORE
        from app.agent.api.models import ChatRequest

        session_id = "test-anon-meta-001"
        SESSION_STORE.pop(session_id, None)

        captured_state = {}

        async def mock_execute(state):
            captured_state.update(state)
            from langchain_core.messages import AIMessage
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content="Status: Noch keine Angaben.")],
            }

        request = ChatRequest(message="Was fehlt noch?", session_id=session_id)

        with patch("app.agent.api.router.execute_agent", side_effect=mock_execute):
            await chat_endpoint(request, current_user=None)

        assert captured_state.get("policy_path") == "conversation", (
            "Unauthenticated meta query must inject policy_path='conversation' (gate: CONVERSATION)"
        )

    @pytest.mark.asyncio
    async def test_anon_recommendation_request_is_blocked_as_governed(self):
        """Explicit recommendation requests go to GOVERNED → 401 on the unauthenticated path."""
        from app.agent.api.router import chat_endpoint, SESSION_STORE
        from app.agent.api.models import ChatRequest

        session_id = "test-anon-blocked-001"
        SESSION_STORE.pop(session_id, None)

        request = ChatRequest(message="Welchen Hersteller empfiehlst du?", session_id=session_id)

        with patch("app.agent.api.router.execute_agent", AsyncMock()) as mock_execute:
            with pytest.raises(HTTPException) as exc_info:
                await chat_endpoint(request, current_user=None)

        assert exc_info.value.status_code == 401
        mock_execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_anon_governed_turn_is_blocked_as_compat_only(self):
        """Technical governed turns must not use the unauthenticated legacy helper path."""
        from app.agent.api.router import chat_endpoint, SESSION_STORE
        from app.agent.api.models import ChatRequest
        from app.agent.runtime.gate import GateDecision

        session_id = "test-anon-structured-block-001"
        SESSION_STORE.pop(session_id, None)

        request = ChatRequest(message="Berechne RWDR fuer 50mm Welle bei 3000rpm", session_id=session_id)

        with (
            patch("app.agent.runtime.gate.decide_route_async", AsyncMock(return_value=GateDecision(route="GOVERNED", reason="hard_override:numeric_unit"))),
            patch("app.agent.api.router.execute_agent", AsyncMock()) as mock_execute,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await chat_endpoint(request, current_user=None)

        assert exc_info.value.status_code == 401
        assert "compat-only" in str(exc_info.value.detail)
        mock_execute.assert_not_awaited()


class TestLightRuntimeStateWrite:
    @pytest.mark.asyncio
    async def test_exploration_turn_persists_lightweight_case_progress(self):
        """EXPLORATION-Turns persistieren Exploration-Progress in GovernedSessionState.

        Bug-1-Fix: EXPLORATION nutzt jetzt _stream_exploration_reply (RAG-basiert),
        nicht mehr stream_conversation. Die Persistenz (last_route, observed_topic,
        conversation_messages) muss trotzdem funktionieren.
        next_best_question_candidate wird bei RAG-basiertem EXPLORATION nicht gesetzt
        (keine conversation_strategy), deshalb wird dies hier nicht mehr geprüft.
        """
        from app.agent.api.models import ChatRequest
        from app.agent.api.router import _stream_light_runtime
        from app.agent.state.models import GovernedSessionState
        from app.services.auth.dependencies import RequestUser

        async def _fake_exploration_reply(message, *, tenant_id):
            payload = {
                "type": "state_update",
                "reply": "SiC und FKM sind typisch für Pumpenanwendungen mit Leckage.",
                "response_class": "conversational_answer",
            }
            yield f"data: {json.dumps(payload)}\n\n"
            yield "data: [DONE]\n\n"

        persisted = {}

        async def _capture_persist(*, current_user, session_id, state, redis_client=None):
            persisted["state"] = state

        request = ChatRequest(
            message="Wir haben Leckage an einer Pumpe und muessen die Dichtstelle erst eingrenzen.",
            session_id="case-light-001",
        )
        current_user = RequestUser(
            user_id="u1",
            username="thorsten",
            sub="u1",
            roles=["user"],
            tenant_id="tenant-a",
        )
        governed_state = GovernedSessionState()

        with (
            patch("app.agent.api.router._stream_exploration_reply", side_effect=_fake_exploration_reply),
            patch("app.agent.api.router._persist_live_governed_state", side_effect=_capture_persist),
        ):
            frames = []
            async for frame in _stream_light_runtime(
                message=request.message,
                request=request,
                current_user=current_user,
                mode="EXPLORATION",
                governed_state_override=governed_state,
            ):
                frames.append(frame)

        saved = persisted["state"]
        assert saved.exploration_progress.last_route == "EXPLORATION"
        assert saved.exploration_progress.case_active is True
        assert saved.exploration_progress.observed_topic is not None
        assert "Leckage" in saved.exploration_progress.observed_topic
        assert saved.conversation_messages[-2].role == "user"
        assert saved.conversation_messages[-1].role == "assistant"
        state_update = json.loads(frames[0][6:].strip())
        assert state_update["structured_state"]["last_route"] == "EXPLORATION"


# ---------------------------------------------------------------------------
# 2. sync_working_profile_to_state does NOT write wp→asserted
# ---------------------------------------------------------------------------

class TestSyncWpToStateProtection:
    """Wave-1 protection: wp values must never be written into asserted_state."""

    def test_sync_does_not_propagate_wp_medium_to_asserted(self):
        from app.agent.agent.sync import sync_working_profile_to_state

        state = {
            "working_profile": {"medium": "Hydrauliköl", "pressure_bar": 10.0},
            "sealing_state": {
                "asserted": {
                    "medium_profile": {},
                    "operating_conditions": {},
                },
            },
        }
        result = sync_working_profile_to_state(state)

        # asserted must remain empty — wp values do not flow into asserted
        asserted = (result.get("sealing_state") or state["sealing_state"]).get("asserted", {})
        assert not (asserted.get("medium_profile") or {}).get("name"), (
            "sync_working_profile_to_state must NOT copy wp.medium into asserted.medium_profile"
        )
        assert not (asserted.get("operating_conditions") or {}).get("pressure"), (
            "sync_working_profile_to_state must NOT copy wp.pressure_bar into asserted"
        )

    def test_sync_preserves_existing_asserted_state(self):
        """If asserted already has data, sync must not overwrite it."""
        from app.agent.agent.sync import sync_working_profile_to_state

        state = {
            "working_profile": {"medium": "Wasser"},
            "sealing_state": {
                "asserted": {
                    "medium_profile": {"name": "Hydrauliköl"},  # already confirmed
                    "operating_conditions": {},
                },
            },
        }
        result = sync_working_profile_to_state(state)
        ss = result.get("sealing_state") or state["sealing_state"]
        # The existing confirmed medium must remain unchanged
        assert (ss.get("asserted") or {}).get("medium_profile", {}).get("name") == "Hydrauliköl"


# ---------------------------------------------------------------------------
# 3. Unit: _build_missing_inputs_text pending never bleeds into missing section
# ---------------------------------------------------------------------------

class TestMissingInputsPendingBoundary:
    """Regression: wp-pending values must stay in pending section, not missing section."""

    def test_wp_pressure_not_in_missing_section(self):
        from app.agent.agent.selection import _build_missing_inputs_text

        wp = {"pressure_bar": 6.0}
        text = _build_missing_inputs_text(None, wp)

        # The pressure value must be in the pending section, not in the "benötige ich noch" section
        assert "6.0" in text, "Pending pressure must appear somewhere in the text"
        if "Für eine Auslegungsempfehlung benötige ich noch" in text:
            missing_section = text.split("Ausstehende Bestätigung")[0]
            assert "6.0" not in missing_section, (
                "Pending pressure value must not appear in the 'missing' section"
            )

    def test_wp_medium_not_mixed_into_missing_when_it_is_pending(self):
        from app.agent.agent.selection import _build_missing_inputs_text

        wp = {"medium": "Testöl-99"}
        text = _build_missing_inputs_text(None, wp)

        assert "Testöl-99" in text, "Pending medium must appear in the text"
        # Once pending, it must not re-appear as a required-input
        if "Für eine Auslegungsempfehlung benötige ich noch" in text:
            missing_section = text.split("Ausstehende Bestätigung")[0]
            assert "Testöl-99" not in missing_section, (
                "Pending medium must not appear in the missing-inputs section"
            )
