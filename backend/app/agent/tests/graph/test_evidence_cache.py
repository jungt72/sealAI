"""Stage C — evidence re-retrieval cache (audit §5 Rang 1 / O1).

Acceptance is twofold and BOTH are pinned here:

1. Latency: re-retrieval is skipped when the EvidenceQuery is unchanged since the
   last successful retrieval (cycle re-runs + follow-up turns with an active case).
2. Correctness (MUST regression): any case/query mutation re-fires evidence — there
   is no cache hit with stale evidence. The cache key covers every retrieval-relevant
   input via the deterministic EvidenceQuery, so a changed query → changed key → miss.

Fail-open is preserved: a failed retrieval clears query_hash, so a failure is never
a cache hit (and a later revert to a previously-cached query re-retrieves fresh).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.agent.graph.nodes.evidence_node as en
from app.agent.graph import GraphState
from app.agent.graph.nodes.evidence_node import evidence_node
from app.agent.state.models import AssertedClaim, AssertedState

_PATCH = "app.agent.graph.nodes.evidence_node.retrieve_evidence"
_CARDS = [
    {
        "id": "c1",
        "content": "PTFE bis 260°C.",
        "retrieval_rank": 0,
        "metadata": {"checksum": "a"},
    },
    {
        "id": "c2",
        "content": "FKM bis 20 bar.",
        "retrieval_rank": 1,
        "metadata": {"doc_version": "v2"},
    },
]


def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _state(**kwargs) -> GraphState:
    assertions = {f: _claim(f, v) for f, v in kwargs.items()}
    return GraphState(
        asserted=AssertedState(assertions=assertions), tenant_id="tenant_abc"
    )


def _run(state):
    return asyncio.run(evidence_node(state))


def test_cache_hit_skips_re_retrieval():
    state = _state(medium="Öl")
    with patch(_PATCH, new_callable=AsyncMock) as rag:
        rag.return_value = (_CARDS, {})
        out1 = _run(state)
        assert rag.call_count == 1
        assert out1.evidence.query_hash is not None
        assert out1.rag_evidence == _CARDS

        # same query → cache hit, retrieval NOT called again, cards repopulated
        out2 = _run(out1)
        assert rag.call_count == 1
        assert out2.rag_evidence == _CARDS


def test_cache_invalidates_on_query_mutation():
    """MUST regression: a mutated case re-fires evidence — no stale cache hit."""
    state = _state(medium="Öl")
    with patch(_PATCH, new_callable=AsyncMock) as rag:
        rag.return_value = (_CARDS, {})
        out1 = _run(state)
        assert rag.call_count == 1
        first_hash = out1.evidence.query_hash

        # mutate the case: add a new asserted parameter (carry the cached evidence)
        mutated = out1.model_copy(
            update={
                "asserted": AssertedState(
                    assertions={
                        **out1.asserted.assertions,
                        "pressure_bar": _claim("pressure_bar", 5.0),
                    }
                )
            }
        )
        new_cards = [
            {"id": "c3", "content": "neu", "retrieval_rank": 0, "metadata": {}}
        ]
        rag.return_value = (new_cards, {})
        out2 = _run(mutated)

        # evidence re-fired (no stale hit) and the cache key changed
        assert (
            rag.call_count == 2
        ), "mutation must re-fire evidence (no stale cache hit)"
        assert out2.evidence.query_hash != first_hash
        assert out2.rag_evidence == new_cards


def test_failed_retrieval_is_not_cached():
    """Fail-open: a failure clears query_hash so it is never a cache hit; next retries."""
    state = _state(medium="Öl")
    with patch(_PATCH, new_callable=AsyncMock) as rag:
        rag.side_effect = RuntimeError("qdrant down")
        out1 = _run(state)
        assert rag.call_count == 1
        assert out1.rag_evidence == []
        assert out1.evidence.query_hash is None  # failure not cached

        # same query, retrieval now recovers → must retry (not a cache hit)
        rag.side_effect = None
        rag.return_value = (_CARDS, {})
        out2 = _run(out1)
        assert rag.call_count == 2
        assert out2.evidence.query_hash is not None
        assert out2.rag_evidence == _CARDS


def test_cache_hit_re_derives_classification(monkeypatch):
    """A cache hit skips only the retrieval I/O — the evidence projection is
    re-derived fresh from the cached cards (no frozen/stale classification)."""
    state = _state(medium="Öl")
    with patch(_PATCH, new_callable=AsyncMock) as rag:
        rag.return_value = (_CARDS, {})
        out1 = _run(state)  # miss → query_hash set
        assert rag.call_count == 1

        spy = MagicMock(wraps=en._build_evidence_classification)
        monkeypatch.setattr(en, "_build_evidence_classification", spy)
        out2 = _run(out1)  # cache hit

        assert rag.call_count == 1, "cache hit must skip retrieval I/O"
        assert spy.called, "cache hit must re-derive the evidence classification fresh"
        assert out2.rag_evidence == _CARDS
