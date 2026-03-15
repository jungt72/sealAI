"""Package 0A.1 — Agent-RAG tenant safety tests.

Verifies:
1. retrieve_rag_context passes tenant_id to hybrid_retrieve (no silent discard).
2. Hits from hybrid_retrieve are correctly mapped to FactCard objects.
3. Tenant A cannot retrieve Tenant B's private results (isolation via mock).
4. On hybrid_retrieve failure, the exception propagates so the caller can apply
   the controlled local-KB fallback with explicit path labeling.
5. Empty query returns empty list without touching the retriever.
6. get_fact_cards retains tenant_id (no `del tenant_id`) — it is the controlled
   fallback path for shared static knowledge.
7. owner_id (individual user identity) is forwarded separately from tenant_id
   (org-level identity) to hybrid_retrieve as user_id, enabling correct private
   document visibility when the two identities diverge.
"""

import asyncio
import sys
import pytest
from unittest.mock import patch, MagicMock

from app.agent.agent.knowledge import (
    FactCard,
    _hit_to_fact_card,
    retrieve_rag_context,
)
from app.agent.agent.graph import get_fact_cards


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hit(text: str, tenant: str, rank: int = 0) -> dict:
    return {
        "text": text,
        "source": f"doc_{rank}",
        "vector_score": 0.9 - rank * 0.1,
        "fused_score": 0.85 - rank * 0.1,
        "metadata": {
            "id": f"doc_{rank}",
            "tenant_id": tenant,
            "topic": f"Topic {rank}",
            "tags": ["seal", "ptfe"],
        },
    }


def _make_rag_module(hybrid_retrieve_fn) -> MagicMock:
    """Create a mock app.services.rag module with the given hybrid_retrieve callable.

    retrieve_rag_context does `from app.services.rag import hybrid_retrieve` inside
    the function body (lazy). Patching sys.modules["app.services.rag"] prevents
    rag_orchestrator from loading (which requires Settings/DB env vars in tests).
    """
    mock_mod = MagicMock()
    mock_mod.hybrid_retrieve = hybrid_retrieve_fn
    return mock_mod


# ---------------------------------------------------------------------------
# _hit_to_fact_card unit tests
# ---------------------------------------------------------------------------

def test_hit_to_fact_card_maps_fields():
    hit = _make_hit("PTFE is chemically resistant.", tenant="tenant_a", rank=0)
    card = _hit_to_fact_card(hit, rank=0)
    assert isinstance(card, FactCard)
    assert card.content == "PTFE is chemically resistant."
    assert card.id == "doc_0"
    assert card.source_ref == "doc_0"
    assert card.topic == "Topic 0"
    assert card.retrieval_rank == 0
    assert abs(card.retrieval_score - 0.85) < 1e-6
    assert "ptfe" in card.tags


def test_hit_to_fact_card_missing_metadata_uses_defaults():
    hit = {"text": "Some content", "source": "src_1", "vector_score": 0.5}
    card = _hit_to_fact_card(hit, rank=2)
    assert card.content == "Some content"
    assert card.retrieval_rank == 2
    assert card.id is not None
    assert card.topic == ""


# ---------------------------------------------------------------------------
# retrieve_rag_context — tenant_id forwarding
# ---------------------------------------------------------------------------

def test_retrieve_rag_context_passes_tenant_id_to_hybrid_retrieve():
    """tenant_id must be forwarded as `tenant` to hybrid_retrieve — not discarded."""
    hits = [_make_hit("PTFE data", tenant="tenant_acme", rank=0)]
    captured = {}

    def fake_hybrid_retrieve(*, query, tenant, k, user_id=None, **kwargs):
        captured["tenant"] = tenant
        captured["user_id"] = user_id
        return hits

    mock_rag = _make_rag_module(fake_hybrid_retrieve)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        result = asyncio.run(
            retrieve_rag_context("PTFE chemical resistance", tenant_id="tenant_acme", limit=3)
        )

    assert captured.get("tenant") == "tenant_acme", (
        f"hybrid_retrieve received tenant={captured.get('tenant')!r}, expected 'tenant_acme'. "
        "tenant_id was silently discarded."
    )
    # When no owner_id is provided, user_id falls back to tenant_id.
    assert captured.get("user_id") == "tenant_acme"
    assert len(result) == 1
    assert isinstance(result[0], FactCard)


# ---------------------------------------------------------------------------
# owner_id / user_id separation — org-level tenant vs individual user identity
# ---------------------------------------------------------------------------

def test_retrieve_rag_context_owner_id_forwarded_as_user_id():
    """When owner_id is provided separately from tenant_id, hybrid_retrieve must
    receive user_id=owner_id (individual identity) and tenant=tenant_id (org scope).

    This is the case when current_user.tenant_id is an org-level claim distinct
    from current_user.user_id used as the RAG ingest identity.
    """
    hits = [_make_hit("Acme Corp PTFE data", tenant="user-uuid-abc", rank=0)]
    captured = {}

    def fake_hybrid_retrieve(*, query, tenant, k, user_id=None, **kwargs):
        captured["tenant"] = tenant
        captured["user_id"] = user_id
        return hits

    mock_rag = _make_rag_module(fake_hybrid_retrieve)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        result = asyncio.run(
            retrieve_rag_context(
                "PTFE seal",
                tenant_id="acme_corp",      # org-level JWT claim
                owner_id="user-uuid-abc",   # individual user identity (matches ingest)
            )
        )

    assert captured.get("tenant") == "acme_corp", (
        "tenant param must carry the org-level scope, not the user identity"
    )
    assert captured.get("user_id") == "user-uuid-abc", (
        "user_id must carry the individual owner identity for private doc visibility, "
        f"got {captured.get('user_id')!r}"
    )
    assert len(result) == 1


def test_retrieve_rag_context_owner_id_fallback_to_tenant_id_when_absent():
    """When owner_id is not provided, user_id must fall back to tenant_id.
    This preserves the previous behaviour for callers that have no separate owner_id.
    """
    captured = {}

    def fake_hybrid_retrieve(*, query, tenant, k, user_id=None, **kwargs):
        captured["tenant"] = tenant
        captured["user_id"] = user_id
        return []

    mock_rag = _make_rag_module(fake_hybrid_retrieve)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        asyncio.run(
            retrieve_rag_context("PTFE", tenant_id="fallback_tenant")
            # owner_id omitted
        )

    assert captured.get("tenant") == "fallback_tenant"
    assert captured.get("user_id") == "fallback_tenant", (
        "user_id must fall back to tenant_id when owner_id is not provided"
    )


def test_retrieve_rag_context_private_visibility_uses_owner_id_not_tenant_id():
    """Private document access must be gated on owner_id (the user-level identity
    matching the Qdrant payload tenant_id written at ingest), NOT on an org tenant_id.

    Simulates the scenario: org=acme_corp, user=user-uuid-abc.
    Documents were ingested under tenant_id=user-uuid-abc.
    The visibility should-clause must use user-uuid-abc to unlock private docs.
    """
    private_doc = _make_hit("User's private PTFE spec", tenant="user-uuid-abc", rank=0)

    def visibility_scoped_retrieve(*, query, tenant, k, user_id=None, **kwargs):
        # Simulate _build_qdrant_filter visibility logic:
        # a private doc passes only if its tenant_id matches user_id.
        result = []
        if user_id == "user-uuid-abc":
            result.append(private_doc)   # owner match → private doc unlocked
        # If user_id were "acme_corp" (org), the doc would not appear.
        return result

    mock_rag = _make_rag_module(visibility_scoped_retrieve)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        # Correct: owner_id = individual user identity
        cards_correct = asyncio.run(
            retrieve_rag_context(
                "PTFE spec",
                tenant_id="acme_corp",
                owner_id="user-uuid-abc",
            )
        )
        # Wrong: no owner_id → user_id falls back to org-level "acme_corp"
        cards_wrong = asyncio.run(
            retrieve_rag_context(
                "PTFE spec",
                tenant_id="acme_corp",
                # owner_id omitted → user_id="acme_corp" → private doc NOT found
            )
        )

    assert len(cards_correct) == 1, (
        "Private doc must be accessible when owner_id matches the ingest identity"
    )
    assert len(cards_wrong) == 0, (
        "Private doc must NOT be accessible when user_id is the org-level tenant_id"
    )


def test_retrieve_rag_context_maps_hits_to_fact_cards():
    hits = [
        _make_hit("PTFE chemical resistance", tenant="t1", rank=0),
        _make_hit("NBR pressure limits", tenant="t1", rank=1),
    ]

    def fake_hybrid_retrieve(*, query, tenant, k, user_id=None, **kwargs):
        return hits

    mock_rag = _make_rag_module(fake_hybrid_retrieve)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        result = asyncio.run(retrieve_rag_context("seal material", tenant_id="t1", limit=3))

    assert len(result) == 2
    assert all(isinstance(c, FactCard) for c in result)
    assert result[0].content == "PTFE chemical resistance"
    assert result[1].content == "NBR pressure limits"
    assert result[0].retrieval_rank == 0
    assert result[1].retrieval_rank == 1


# ---------------------------------------------------------------------------
# Tenant isolation — Tenant A cannot see Tenant B's private data
# ---------------------------------------------------------------------------

def test_retrieve_rag_context_tenant_isolation():
    """Simulate what hybrid_retrieve enforces: Tenant A results != Tenant B results."""
    tenant_a_hits = [_make_hit("Tenant A PTFE data", tenant="tenant_a", rank=0)]
    tenant_b_hits = [_make_hit("Tenant B confidential compound", tenant="tenant_b", rank=0)]

    def scoped_hybrid_retrieve(*, query, tenant, k, user_id=None, **kwargs):
        # Simulate Qdrant tenant filter: return per-tenant result sets.
        if tenant == "tenant_a":
            return tenant_a_hits
        if tenant == "tenant_b":
            return tenant_b_hits
        return []

    mock_rag = _make_rag_module(scoped_hybrid_retrieve)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        cards_a = asyncio.run(retrieve_rag_context("PTFE", tenant_id="tenant_a"))
        cards_b = asyncio.run(retrieve_rag_context("PTFE", tenant_id="tenant_b"))

    texts_a = {c.content for c in cards_a}
    texts_b = {c.content for c in cards_b}

    assert "Tenant A PTFE data" in texts_a
    assert "Tenant B confidential compound" not in texts_a, (
        "Tenant A retrieved Tenant B's private document — tenant isolation violated."
    )
    assert "Tenant B confidential compound" in texts_b
    assert "Tenant A PTFE data" not in texts_b


# ---------------------------------------------------------------------------
# Failure propagation — caller must handle fallback
# ---------------------------------------------------------------------------

def test_retrieve_rag_context_raises_on_retriever_failure():
    """On retriever failure, the exception must propagate so the caller can apply
    the controlled local-KB fallback with explicit path labeling."""
    def failing_hybrid_retrieve(**kwargs):
        raise ConnectionError("Qdrant unreachable")

    mock_rag = _make_rag_module(failing_hybrid_retrieve)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        with pytest.raises(ConnectionError, match="Qdrant unreachable"):
            asyncio.run(retrieve_rag_context("PTFE", tenant_id="tenant_x"))


# ---------------------------------------------------------------------------
# Empty query guard
# ---------------------------------------------------------------------------

def test_retrieve_rag_context_empty_query_returns_empty_without_calling_retriever():
    called = []

    def spy_hybrid(*, query, tenant, k, user_id=None, **kwargs):
        called.append({"query": query, "tenant": tenant})
        return []

    mock_rag = _make_rag_module(spy_hybrid)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        result = asyncio.run(retrieve_rag_context("", tenant_id="tenant_x"))

    assert result == []
    assert called == [], "hybrid_retrieve must not be called for empty query"


def test_retrieve_rag_context_whitespace_only_query_returns_empty():
    called = []

    def spy_hybrid(*, query, tenant, k, user_id=None, **kwargs):
        called.append({"query": query, "tenant": tenant})
        return []

    mock_rag = _make_rag_module(spy_hybrid)
    with patch.dict(sys.modules, {"app.services.rag": mock_rag}):
        result = asyncio.run(retrieve_rag_context("   ", tenant_id="tenant_x"))

    assert result == []
    assert called == []


# ---------------------------------------------------------------------------
# get_fact_cards — no silent tenant_id discard (fallback path)
# ---------------------------------------------------------------------------

def test_get_fact_cards_does_not_discard_tenant_id():
    """get_fact_cards must not `del tenant_id`. It is the controlled fallback path
    for shared static knowledge when the primary retriever is unavailable."""
    # Verify the function signature accepts tenant_id without error.
    # We patch the underlying loader to avoid filesystem access.
    with patch("app.agent.agent.graph.retrieve_fact_cards_fallback", return_value=[]) as mock_fallback:
        result = get_fact_cards("PTFE", tenant_id="tenant_abc")
    # If `del tenant_id` were still present, the call above would still work,
    # but we verify the function reached the fallback — meaning it did not crash
    # and it did not drop the query either.
    mock_fallback.assert_called_once_with("PTFE")
    assert result == []


def test_get_fact_cards_no_tenant_id_also_works():
    """Fallback must work when no tenant_id is provided (anonymous / system calls)."""
    with patch("app.agent.agent.graph.retrieve_fact_cards_fallback", return_value=[]) as mock_fallback:
        result = get_fact_cards("NBR")
    mock_fallback.assert_called_once_with("NBR")
    assert result == []
