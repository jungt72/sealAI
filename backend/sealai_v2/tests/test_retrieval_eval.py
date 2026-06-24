from __future__ import annotations

from sealai_v2.core.contracts import GroundingFact, RetrievalResult
from sealai_v2.eval.retrieval_eval import (
    ranked_card_ids,
    recall_at_k,
    reciprocal_rank,
    summarize,
)


def test_recall_at_k():
    ranked = ["FK-A", "FK-B", "FK-C"]
    assert recall_at_k(ranked, "FK-A", 1) == 1
    assert recall_at_k(ranked, "FK-C", 1) == 0
    assert recall_at_k(ranked, "FK-C", 3) == 1
    assert recall_at_k(ranked, "FK-X", 5) == 0


def test_reciprocal_rank():
    ranked = ["FK-A", "FK-B", "FK-C"]
    assert reciprocal_rank(ranked, "FK-A") == 1.0
    assert reciprocal_rank(ranked, "FK-B") == 0.5
    assert reciprocal_rank(ranked, "FK-X") == 0.0


def test_ranked_card_ids_dedups_in_rank_order():
    res = RetrievalResult(
        grounding_facts=(
            GroundingFact(text="x", quelle="q", card_id="FK-A"),
            GroundingFact(text="y", quelle="q", card_id="FK-A"),  # same card, 2nd claim
            GroundingFact(text="z", quelle="q", card_id="FK-B"),
        ),
        provisional=(GroundingFact(text="w", quelle="q", card_id="FK-C"),),
    )
    assert ranked_card_ids(res) == ["FK-A", "FK-B", "FK-C"]


def test_summarize():
    rows = [
        {"r@1": 1, "r@3": 1, "r@5": 1, "rr": 1.0},
        {"r@1": 0, "r@3": 1, "r@5": 1, "rr": 0.5},
    ]
    s = summarize(rows)
    assert s["recall@1"] == 0.5
    assert s["recall@3"] == 1.0
    assert s["mrr"] == 0.75
    assert s["n"] == 2
