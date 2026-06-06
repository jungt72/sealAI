"""Stage A1 — observability-in-logs acceptance (audit §5 Rang 5 / W6 / Guard-Alert).

Asserts the *new* structured signals introduced by Stage A1. None of the event
names below existed before this PR (red-before-green: grep the base for
``turn_timing`` / ``rag_tier1_hybrid`` / ``tier0_retrieval_blocked`` → 0 hits),
so each test fails on the pre-A1 tree and passes after.

The test env stubs ``structlog`` to a no-op (``backend/conftest.py``), so we swap
each module's logger for a recording ``MagicMock`` and assert on the emitted
event name + kwargs. Using ``.warning`` vs ``.info`` also pins the level.

The changes are observability-only: no guard control-flow is altered and
``turn_tier.py`` is untouched. We therefore also pin that a Tier-0 turn still
raises ``TierViolation`` (behaviour unchanged) while now *also* logging it.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.agent.runtime.turn_tier import (
    TierViolation,
    clear_declared_tier,
    set_declared_tier,
)
from app.agent.runtime.turn_timing import start_turn_timer
from app.agent.api import sse_contract
from app.agent.api import dispatch as dispatch_mod
from app.agent.services import real_rag


def _call(mock_method, event_name: str):
    """Return the single recorded call whose first positional arg == event_name."""
    matches = [
        c for c in mock_method.call_args_list if c.args and c.args[0] == event_name
    ]
    assert len(matches) == 1, f"expected one {event_name!r} call, got {matches}"
    return matches[0]


# ── Item 1: server-side persistence of first_progress_ms / latency_ms ──────────


def test_final_state_update_emits_turn_timing(monkeypatch):
    rec = MagicMock()
    monkeypatch.setattr(sse_contract, "_slog", rec)
    start_turn_timer()
    builder = sse_contract.SSEEventBuilder(turn_id="turn:test-a1")
    builder.event(
        {"type": "state_update", "policy_path": "engineering_case_update"},
        event_type="state_update",
        is_final=True,
    )
    call = _call(rec.info, "turn_timing")
    assert call.kwargs["turn_id"] == "turn:test-a1"
    assert call.kwargs["route"] == "engineering_case_update"
    assert call.kwargs["latency_ms"] is not None
    assert "first_progress_ms" in call.kwargs


def test_turn_timing_not_emitted_for_non_final(monkeypatch):
    rec = MagicMock()
    monkeypatch.setattr(sse_contract, "_slog", rec)
    start_turn_timer()
    builder = sse_contract.SSEEventBuilder(turn_id="turn:test-a1b")
    builder.event({"type": "delta", "text": "x"}, event_type="delta")
    assert not any(
        c.args and c.args[0] == "turn_timing" for c in rec.info.call_args_list
    )


# ── Item 2: RAG tier timings on structlog (prod-visible) ───────────────────────


def test_tier1_hybrid_timing_emitted(monkeypatch):
    rec = MagicMock()
    monkeypatch.setattr(real_rag, "slog", rec)
    import app.services.rag.rag_orchestrator as orch

    hits = [
        {"text": "a", "metadata": {"id": "1"}, "fused_score": 0.9},
        {"text": "b", "metadata": {"id": "2"}, "fused_score": 0.8},
    ]
    monkeypatch.setattr(orch, "hybrid_retrieve", lambda **kw: hits)

    cards = asyncio.run(real_rag.retrieve_with_tenant("seal query", "tenant-x", k=5))
    assert len(cards) == 2
    call = _call(rec.info, "rag_tier1_hybrid")
    assert call.kwargs["hits"] == 2
    assert isinstance(call.kwargs["duration_ms"], int)
    assert call.kwargs["tenant"] == "tenant-x"


# ── Item 3: Tier-0 backstop is logged, never silent (turn_tier.py untouched) ───


def test_cascade_tier0_violation_warns_and_reraises(monkeypatch):
    rec = MagicMock()
    monkeypatch.setattr(real_rag, "slog", rec)
    set_declared_tier(0)
    try:
        with pytest.raises(TierViolation):
            asyncio.run(real_rag.retrieve_with_tenant("seal query", "tenant-x", k=5))
    finally:
        clear_declared_tier()
    call = _call(rec.warning, "tier0_retrieval_blocked")
    assert call.kwargs["retrieval_kind"] == "rag_cascade"
    assert call.kwargs["declared_tier"] == 0
    # cascade entry guard fires before any retrieval I/O → info timing never logged
    assert not any(
        c.args and c.args[0] == "rag_tier1_hybrid" for c in rec.info.call_args_list
    )


def test_knowledge_dispatch_tier0_violation_warns_and_reraises(monkeypatch):
    rec = MagicMock()
    monkeypatch.setattr(dispatch_mod, "_slog", rec)
    set_declared_tier(0)
    try:
        with pytest.raises(TierViolation):
            dispatch_mod._knowledge_rag_retriever(query="what is FKM", max_results=3)
    finally:
        clear_declared_tier()
    call = _call(rec.warning, "tier0_retrieval_blocked")
    assert call.kwargs["retrieval_kind"] == "knowledge_rag"
    assert call.kwargs["declared_tier"] == 0
