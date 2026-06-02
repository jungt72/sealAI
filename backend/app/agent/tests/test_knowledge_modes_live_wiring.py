"""AC8 + AC9 — §8 knowledge_modes live wiring at the dispatch boundary.

These tests assert that the previously dead §8 machinery
(``resolve_knowledge_mode`` + ``mode_mutates``) is now wired into the live
runtime dispatch:

- AC8: a knowledge turn resolves to its §8 mode and that mode is propagated to
  the answer composition context (so the composer can shape the answer).
- AC9: a pure (fact-free) knowledge turn stays read-only (CONVERSATION, no case),
  and a knowledge-shaped turn that *does* carry new technical facts is promoted
  to the governed State Gate instead of being answered (and the facts lost).
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from app.agent.api.models import ChatRequest
from app.agent.api.router import _resolve_runtime_dispatch
from app.agent.communication.knowledge_modes import resolve_knowledge_mode
from app.domain.pre_gate_classification import PreGateClassification
from app.services.auth.dependencies import RequestUser


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


def _patch_knowledge_io(monkeypatch) -> None:
    """Isolate dispatch from persistence/session I/O for the knowledge path."""
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_governed_state",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context",
        AsyncMock(),
    )


# --- AC8: §8 mode resolved and propagated to answer composition -------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_mode"),
    [
        ("Was ist FFKM?", "knowledge_general"),
        ("Was bedeutet WRAS bei einem RWDR?", "norm_documentation_knowledge"),
    ],
)
async def test_knowledge_turn_propagates_section8_mode_to_composer(
    monkeypatch,
    message: str,
    expected_mode: str,
) -> None:
    _patch_knowledge_io(monkeypatch)

    captured: dict[str, object] = {}

    async def _capture_compose(*, knowledge_response, knowledge_mode=None, **_kwargs):
        captured["knowledge_mode"] = knowledge_mode
        return knowledge_response

    monkeypatch.setattr(
        "app.agent.api.dispatch._compose_knowledge_answer_if_enabled",
        _capture_compose,
    )

    # Sanity: the §8 sub-classifier produces the expected mode for this message.
    assert resolve_knowledge_mode(message, has_active_case=False) == expected_mode

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message=message, session_id="knowledge-mode-propagation"),
        current_user=_user(),
    )

    assert (
        dispatch.pre_gate_classification == PreGateClassification.KNOWLEDGE_QUERY.value
    )
    assert dispatch.runtime_mode == "CONVERSATION"
    # The fine §8 mode (not the coarse pre-gate class) reaches composition.
    assert captured["knowledge_mode"] == expected_mode


# --- AC9: pure knowledge turn stays read-only -------------------------------


@pytest.mark.asyncio
async def test_pure_knowledge_turn_does_not_create_or_mutate_case(monkeypatch) -> None:
    _patch_knowledge_io(monkeypatch)

    async def _fail_governed(*_args, **_kwargs):
        raise AssertionError("pure knowledge turn must not invoke the governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", _fail_governed
    )

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Was ist FFKM?", session_id="pure-knowledge-readonly"),
        current_user=_user(),
    )

    # CONVERSATION route => governed graph (the only case-mutation site) never runs.
    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.gate_route == "CONVERSATION"
    assert dispatch.knowledge_response is not None
    assert dispatch.knowledge_response.no_case_created is True
    assert dispatch.governed_state is None


# --- AC9 / design (b): a fact-bearing knowledge turn stays read-only ---------


@pytest.mark.asyncio
async def test_fact_bearing_knowledge_turn_stays_readonly_and_keeps_facts(
    monkeypatch,
) -> None:
    load_context = AsyncMock(return_value=None)
    save_context = AsyncMock()
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_governed_state",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context", load_context
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context", save_context
    )

    async def _fail_governed(*_args, **_kwargs):
        raise AssertionError("knowledge turn must not invoke the governed graph")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", _fail_governed
    )

    # "Was ist FKM bei 100 °C?" is question-shaped (pre-gate -> KNOWLEDGE_QUERY)
    # yet carries an operating fact (100 °C). The §8 sub-classifier flags it as
    # mutating, but AC9 is preserved by the existing bridge seam: the governed
    # CaseState is NOT mutated; the fact is kept in the transient bridge context
    # and bridged later on case intent (design b: facts are not lost).
    assert (
        resolve_knowledge_mode("Was ist FKM bei 100 °C?", has_active_case=False)
        == "knowledge_case_mutating"
    )

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message="Was ist FKM bei 100 °C?",
            session_id="knowledge-fact-readonly",
        ),
        current_user=_user(),
    )

    assert (
        dispatch.pre_gate_classification == PreGateClassification.KNOWLEDGE_QUERY.value
    )
    # Read-only: no governed case is created or mutated.
    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.gate_route == "CONVERSATION"
    assert dispatch.knowledge_response is not None
    assert dispatch.knowledge_response.no_case_created is True
    assert dispatch.governed_state is None
    # Facts are not lost — they are stashed in the transient bridge context.
    saved_context = save_context.await_args.kwargs["context"]
    assert saved_context.mentioned_parameters["temperature_c"].raw_value == 100.0


# --- Case-building input still goes governed (not swallowed by knowledge) ----


@pytest.mark.asyncio
async def test_case_building_input_still_routes_governed(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_governed_state",
        AsyncMock(return_value=None),
    )

    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(
            message=(
                "Wir brauchen eine PTFE-Dichtung fuer eine Pumpe bei 12 bar und 180 C."
            ),
            session_id="case-building-governed",
        ),
        current_user=_user(),
    )

    assert (
        dispatch.pre_gate_classification == PreGateClassification.DOMAIN_INQUIRY.value
    )
    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.gate_route == "GOVERNED"
    assert dispatch.knowledge_response is None
