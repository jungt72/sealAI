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
