"""Counter-test for the gated, PII-free per-turn routing/identity diagnostic log.

- flag off  -> no [routing_debug] line
- flag on   -> decision + knowledge_mode lines with routing/identity fields,
               and NO raw sub / email / message body (PII-free, owner hashed)
- _routing_debug_enabled() default (no flag) is False
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.agent.api.dispatch import _routing_debug_enabled
from app.agent.api.models import ChatRequest
from app.agent.api.routes.chat import chat_endpoint
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
    async def fail_governed(*_a: Any, **_k: Any) -> None:
        raise AssertionError("routing debug test must not invoke governed runtime")

    async def fail_persist(*_a: Any, **_k: Any) -> None:
        raise AssertionError("routing debug test must not persist governed state")

    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_light_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.routes.chat._run_governed_chat_response", fail_governed
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state", fail_persist
    )


def _no_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agent.api.dispatch._load_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.agent.api.dispatch._persist_live_knowledge_session_context",
        AsyncMock(return_value=None),
    )


def _common_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_KNOWLEDGE_ANSWER_COMPOSER", "false")
    monkeypatch.setenv("SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER", "false")
    _block_case_mutation(monkeypatch)
    _no_bridge(monkeypatch)


def _routing_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage() for r in caplog.records if "[routing_debug]" in r.getMessage()
    ]


def test_routing_debug_enabled_default_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEALAI_ROUTING_DEBUG", raising=False)
    assert _routing_debug_enabled() is False


@pytest.mark.asyncio
async def test_routing_debug_off_emits_no_line(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _common_env(monkeypatch)
    monkeypatch.delenv("SEALAI_ROUTING_DEBUG", raising=False)
    with caplog.at_level(logging.INFO, logger="app.agent.api.dispatch"):
        await chat_endpoint(
            ChatRequest(message="Was ist PTFE?", session_id="rd-off"),
            current_user=_user(),
        )
    assert _routing_lines(caplog) == []


@pytest.mark.asyncio
async def test_routing_debug_on_emits_pii_free_line(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _common_env(monkeypatch)
    monkeypatch.setenv("SEALAI_ROUTING_DEBUG", "true")
    with caplog.at_level(logging.INFO, logger="app.agent.api.dispatch"):
        await chat_endpoint(
            ChatRequest(message="Was ist PTFE?", session_id="rd-on-7e1c"),
            current_user=_user(),
        )
    lines = _routing_lines(caplog)
    blob = "\n".join(lines)

    # decision (every turn) + knowledge_mode (knowledge turn) lines present
    assert any("phase=decision" in line for line in lines), lines
    assert any("phase=knowledge_mode" in line for line in lines), lines
    # required routing + identity fields
    for token in (
        "pre_gate_class=",
        "pre_gate_conf=",
        "semantic_applied=",
        "knowledge_mode=",
        "session_id=rd-on-7e1c",
        "checkpointer_key=sealai:",
        "knowledge_session_key=knowledge_session:",
        "owner_hash=h_",
    ):
        assert token in blob, f"missing token: {token}"

    # HARD PII rules: owner sub hashed (not raw), no emails, no message body
    assert "user-1" not in blob, "raw owner sub must be hashed"
    assert "@" not in blob, "no emails in routing debug log"
    assert "Was ist PTFE" not in blob, "no message body in routing debug log"
