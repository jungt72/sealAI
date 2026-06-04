"""Doctrine guard: comparative material ranking must not pass, raises fail closed.

Covers the #4 + #1 + #3 patch set:
- #4 deterministic-preferred: material-vs-material answers stay on the neutral
  deterministic renderer; the LLM composer is skipped (no ranking surface).
- #1 prompt: the no-ranking / symmetry rule is unconditional in the composer
  system prompt, independent of any §8 knowledge_mode branch.
- #3 fail-closed: a composer doctrine raise ends in the hard guard fallback,
  while a depth/parse raise keeps the existing neutral base passthrough.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.agent.api.models import ChatRequest, ChatResponse
from app.agent.api.routes.chat import chat_endpoint
from app.agent.communication.answer_composer import (
    KnowledgeAnswerComposerError,
    KnowledgeAnswerComposerInput,
    KnowledgeAnswerComposerOutput,
)
from app.agent.prompts import prompts
from app.agent.runtime.output_guard import FAST_PATH_GUARD_FALLBACK
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


def _block_case_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_governed(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("doctrine guard test must not invoke governed case runtime")

    async def fail_persist(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("doctrine guard test must not persist governed case state")

    monkeypatch.setattr("app.agent.api.routes.chat._run_light_chat_response", fail_governed)
    monkeypatch.setattr("app.agent.api.routes.chat._run_governed_chat_response", fail_governed)
    monkeypatch.setattr("app.agent.api.loaders._persist_live_governed_state", fail_persist)


def _no_bridge_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )


def _knowledge_debug(response: ChatResponse) -> dict[str, Any]:
    assert response.run_meta is not None
    debug = response.run_meta.get("knowledge_debug")
    assert isinstance(debug, dict)
    return debug


def _common_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "true")
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_DEBUG_TRACE", "true")
    monkeypatch.setenv("SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER", "false")
    _block_case_mutation(monkeypatch)
    _no_bridge_context(monkeypatch)


# --- #1 PROMPT: unconditional no-ranking / symmetry rule --------------------


def test_answer_composer_prompt_always_forbids_comparative_ranking() -> None:
    rendered = prompts.render(
        "knowledge/answer_composer.j2",
        {"prompt_version": "test"},
    )
    lowered = rendered.casefold()
    # The symmetry / no-preference rule must always be present, independent of
    # any §8 knowledge_mode branch (which only fires for comparison_* modes).
    assert "symmetrisch" in lowered
    assert "besser" in lowered and "vorzuziehen" in lowered
    assert "keine präferenz" in lowered or "kein ranking" in lowered


# --- #4 DETERMINISTIC-PREFERRED: comparison skips the LLM composer ----------


@pytest.mark.asyncio
async def test_material_comparison_uses_deterministic_renderer_and_skips_composer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _common_env(monkeypatch)
    called = {"compose": False}

    async def compose(
        _self: object,
        _request: KnowledgeAnswerComposerInput,
    ) -> KnowledgeAnswerComposerOutput:
        called["compose"] = True
        return KnowledgeAnswerComposerOutput(
            answer_markdown=(
                "COMPOSER_RANKING_SENTINEL FKM ist besser geeignet fuer dynamische "
                "Anwendungen, PTFE fuer statische bevorzugt."
            ),
            confidence_note=None,
        )

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    response = await chat_endpoint(
        ChatRequest(message="Vergleiche FKM und PTFE", session_id="cmp-deterministic"),
        current_user=_user(),
    )

    # Root fix: material-vs-material never reaches the LLM rewrite.
    assert called["compose"] is False
    assert "COMPOSER_RANKING_SENTINEL" not in response.answer_markdown
    # Deterministic neutral renderer was used; no application ranking language.
    assert "Werkstoffvergleich" in response.answer_markdown
    low = response.answer_markdown.casefold()
    assert "besser geeignet" not in low
    assert "bevorzugt" not in low
    assert _knowledge_debug(response)["answer_markdown_source"] == "reply_passthrough"


# --- #3 FAIL-CLOSED: doctrine raise -> hard guard fallback ------------------


@pytest.mark.asyncio
async def test_doctrine_raise_fails_closed_to_guard_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _common_env(monkeypatch)

    async def compose(
        _self: object,
        _request: KnowledgeAnswerComposerInput,
    ) -> KnowledgeAnswerComposerOutput:
        raise KnowledgeAnswerComposerError("unsafe_material_suitability_claim")

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    response = await chat_endpoint(
        ChatRequest(
            message="Was bedeutet Shore A bei Dichtungswerkstoffen?",
            session_id="failclosed-doctrine",
        ),
        current_user=_user(),
    )

    # Doctrine raise must fail CLOSED: hard neutral guard fallback, never base.
    assert FAST_PATH_GUARD_FALLBACK in response.answer_markdown
    assert _knowledge_debug(response)["answer_markdown_source"] == "composer_safe_fallback"


@pytest.mark.asyncio
async def test_depth_raise_still_passes_through_base_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _common_env(monkeypatch)

    async def compose(
        _self: object,
        _request: KnowledgeAnswerComposerInput,
    ) -> KnowledgeAnswerComposerOutput:
        raise KnowledgeAnswerComposerError("material_comparison_too_broad")

    monkeypatch.setattr(
        "app.agent.communication.answer_composer.KnowledgeAnswerComposer.compose",
        compose,
    )

    response = await chat_endpoint(
        ChatRequest(
            message="Was bedeutet Shore A bei Dichtungswerkstoffen?",
            session_id="depth-fallback",
        ),
        current_user=_user(),
    )

    # Non-doctrine (depth/parse) raise keeps the existing neutral base passthrough.
    assert FAST_PATH_GUARD_FALLBACK not in response.answer_markdown
    assert _knowledge_debug(response)["answer_markdown_source"] == "composer_fallback"
