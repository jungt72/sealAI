"""P1-2 TEIL B: fail-closed Tier-0 retrieval guard at the rag funnel.

RED-before-green: under a declared Tier-0 turn, ``hybrid_retrieve`` must raise
``TierViolation`` BEFORE any retrieval I/O. Today (no guard) it returns results —
that is the hole (S2).
"""

from __future__ import annotations

import pytest

from app.agent.runtime.turn_tier import (
    TIER_0,
    TierViolation,
    clear_declared_tier,
    declared_tier_for_classification,
    set_declared_tier,
)


@pytest.fixture
def _mocked_rag(monkeypatch):
    # Make retrieval otherwise succeed (no real I/O) so the ONLY thing that can
    # stop it is the tier guard.
    monkeypatch.setattr(
        "app.services.rag.rag_orchestrator._embed", lambda x: [[0.1] * 128]
    )
    monkeypatch.setattr(
        "app.services.rag.rag_orchestrator._embed_sparse_query", lambda x: None
    )
    monkeypatch.setattr(
        "app.services.rag.rag_orchestrator._build_qdrant_filter", lambda f: None
    )
    monkeypatch.setattr(
        "app.services.rag.rag_orchestrator._qdrant_search_with_retry",
        lambda *a, **k: ([], {}),
    )
    yield
    clear_declared_tier()


def test_tier0_classifications_map_to_tier_0():
    for cls in ("GREETING", "META_QUESTION", "BLOCKED"):
        assert declared_tier_for_classification(cls) == TIER_0
    for cls in ("KNOWLEDGE_QUERY", "DOMAIN_INQUIRY"):
        assert declared_tier_for_classification(cls) != TIER_0


def test_tier0_turn_retrieval_is_blocked(_mocked_rag):
    from app.services.rag.rag_orchestrator import hybrid_retrieve

    set_declared_tier(TIER_0)
    with pytest.raises(TierViolation):
        hybrid_retrieve(query="hallo", tenant="sealai")


def test_non_tier0_turn_retrieval_is_allowed(_mocked_rag):
    from app.services.rag.rag_orchestrator import hybrid_retrieve

    set_declared_tier(1)  # e.g. KNOWLEDGE_QUERY / DOMAIN_INQUIRY
    # Must NOT raise — legitimate retrieval path.
    assert hybrid_retrieve(query="welches Medium?", tenant="sealai") == []


def test_undeclared_tier_retrieval_is_allowed(_mocked_rag):
    from app.services.rag.rag_orchestrator import hybrid_retrieve

    clear_declared_tier()  # tier unknown → allowed (only Tier-0 blocks)
    assert hybrid_retrieve(query="x", tenant="sealai") == []


def test_kill_switch_off_allows_tier0_retrieval(_mocked_rag, monkeypatch):
    from app.services.rag.rag_orchestrator import hybrid_retrieve

    monkeypatch.setenv("SEALAI_TIER0_RETRIEVAL_GUARD", "0")
    set_declared_tier(TIER_0)
    # Incident kill-switch: guard bypassed (logged), retrieval proceeds.
    assert hybrid_retrieve(query="x", tenant="sealai") == []


# ── Scope B / B1+B2: the 3-tier cascade (real_rag.retrieve_with_tenant) ──────────
# RED-before-green: a Tier-0 turn that enters the cascade must be blocked BEFORE any
# retrieval I/O. The hole (B1): hybrid_retrieve's guard runs in a run_in_executor
# worker thread, where the declared-tier contextvar does not propagate, so it never
# fires; and even if it did, the Tier-1 `except Exception` swallows the TierViolation
# and falls through to the UNGUARDED BM25 Tier-2 (bm25_repo.search). The fix guards
# the cascade entry, which runs in the awaiting coroutine's context.


async def test_tier0_cascade_blocks_before_bm25(monkeypatch):
    """Tier-0 + retrieve_with_tenant ⇒ TierViolation, BM25 never reached (B1)."""
    from app.agent.services import real_rag
    from app.services.rag import bm25_store, rag_orchestrator

    bm25_calls: list = []

    def _fake_bm25(*a, **k):
        bm25_calls.append((a, k))
        return []

    monkeypatch.setattr(bm25_store.bm25_repo, "search", _fake_bm25)
    # Tier-1 yields no hits → without the entry guard the cascade reaches Tier-2 BM25.
    monkeypatch.setattr(rag_orchestrator, "hybrid_retrieve", lambda **k: [])

    set_declared_tier(TIER_0)
    try:
        with pytest.raises(TierViolation):
            await real_rag.retrieve_with_tenant("hallo", "sealai")
        assert bm25_calls == [], "Tier-0 turn must not reach BM25 retrieval"
    finally:
        clear_declared_tier()


async def test_non_tier0_cascade_allowed(monkeypatch):
    """A legitimate Tier-1 turn cascades normally — no false trip (AC8 boundary)."""
    from app.agent.services import real_rag
    from app.services.rag import bm25_store, rag_orchestrator

    monkeypatch.setattr(rag_orchestrator, "hybrid_retrieve", lambda **k: [])
    monkeypatch.setattr(bm25_store.bm25_repo, "search", lambda *a, **k: [])

    set_declared_tier(1)
    try:
        assert await real_rag.retrieve_with_tenant("welches medium", "sealai") == []
    finally:
        clear_declared_tier()


async def test_undeclared_cascade_allowed(monkeypatch):
    """Undeclared tier (None) is allowed through the cascade — only Tier-0 blocks."""
    from app.agent.services import real_rag
    from app.services.rag import bm25_store, rag_orchestrator

    monkeypatch.setattr(rag_orchestrator, "hybrid_retrieve", lambda **k: [])
    monkeypatch.setattr(bm25_store.bm25_repo, "search", lambda *a, **k: [])

    clear_declared_tier()
    assert await real_rag.retrieve_with_tenant("x", "sealai") == []


def test_retrieval_entrypoints_call_the_guard():
    """B2: every public retrieval funnel calls the tier guard — the 'single funnel'
    claim made true and pinned, so a future entry can't silently skip it."""
    import inspect

    from app.agent.services.real_rag import retrieve_with_tenant
    from app.services.rag.rag_orchestrator import hybrid_retrieve

    for fn in (retrieve_with_tenant, hybrid_retrieve):
        assert "enforce_retrieval_allowed" in inspect.getsource(fn), (
            f"{fn.__name__} must call enforce_retrieval_allowed (tier-0 guard)"
        )
