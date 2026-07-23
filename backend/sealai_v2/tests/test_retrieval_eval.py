from __future__ import annotations

from sealai_v2.core.contracts import GroundingFact, RetrievalResult
from sealai_v2.eval.retrieval_eval import (
    evaluate_live_gates,
    live_exit_code,
    ranked_card_ids,
    recall_at_k,
    reciprocal_rank,
    summarize,
    summarize_live,
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


def test_live_summary_and_gate_pass_are_explicit():
    rows = [
        {
            "r@1": 1,
            "r@3": 1,
            "r@5": 1,
            "rr": 1.0,
            "reviewed_fact_count": 2,
            "provisional_fact_count": 0,
            "public_exception": "",
            "latency_ms": 100.0,
        },
        {
            "r@1": 0,
            "r@3": 1,
            "r@5": 1,
            "rr": 0.5,
            "reviewed_fact_count": 1,
            "provisional_fact_count": 0,
            "public_exception": "",
            "latency_ms": 200.0,
        },
    ]
    summary = summarize_live(rows)
    gate = evaluate_live_gates(summary)

    assert summary["latency_ms"] == {"p50": 150.0, "p95": 200.0, "max": 200.0}
    assert gate["status"] == "PASS"
    assert all(gate["checks"].values())


def test_live_gate_fails_on_empty_result_or_latency():
    summary = {
        "recall@3": 1.0,
        "recall@5": 1.0,
        "grounded_query_rate": 1.0,
        "empty_result_count": 1,
        "latency_ms": {"p95": 251.0},
    }
    gate = evaluate_live_gates(summary)

    assert gate["status"] == "FAIL"
    assert gate["checks"]["empty_result_count"] is False
    assert gate["checks"]["retrieval_latency_p95_ms_max"] is False


def test_live_exit_code_never_treats_provisional_quality_pass_as_release_success():
    provisional = {
        "retrieval_quality_gate": {"status": "PASS"},
        "release_eligible": False,
    }
    failed = {
        "retrieval_quality_gate": {"status": "FAIL"},
        "release_eligible": False,
    }
    eligible = {
        "retrieval_quality_gate": {"status": "PASS"},
        "release_eligible": True,
    }

    assert live_exit_code(provisional) == 3
    assert live_exit_code(failed) == 2
    assert live_exit_code(eligible) == 0
