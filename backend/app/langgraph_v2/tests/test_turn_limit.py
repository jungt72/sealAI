"""Tests for the turn_limit_node (12-turn hard limit)."""
from __future__ import annotations

import pytest

from app.langgraph_v2.state import SealAIState


def test_turn_limit_node_returns_reply():
    state = SealAIState(
        max_turns=12,
        medium=None,
        pressure_bar=None,
        temperature_c=None,
        dynamic_type=None,
    )
    from app.langgraph_v2.nodes.nodes_error import turn_limit_node

    patch = turn_limit_node(state)
    assert "12 Runden" in patch["final_text"]
    assert "medium" in patch["final_text"]
    assert patch["last_node"] == "turn_limit_node"


def test_turn_limit_node_partial_missing():
    """Only fields that are None appear in the missing list."""
    state = SealAIState(
        max_turns=12,
        medium="Hydrauliköl",
        pressure_bar=None,
        temperature_c=None,
        dynamic_type="rotierend",
    )
    from app.langgraph_v2.nodes.nodes_error import turn_limit_node

    patch = turn_limit_node(state)
    text = patch["final_text"]
    assert "pressure_bar" in text
    assert "temperature_c" in text
    assert "medium" not in text
    assert "dynamic_type" not in text


def test_turn_limit_node_all_filled():
    """When all critical fields are set, missing list shows –."""
    state = SealAIState(
        max_turns=12,
        medium="Wasser",
        pressure_bar=10.0,
        temperature_c=80.0,
        dynamic_type="rotierend",
    )
    from app.langgraph_v2.nodes.nodes_error import turn_limit_node

    patch = turn_limit_node(state)
    assert "–" in patch["final_text"]


def test_turn_limit_node_final_answer_set():
    """final_answer and final_text must both be set."""
    state = SealAIState(max_turns=5)
    from app.langgraph_v2.nodes.nodes_error import turn_limit_node

    patch = turn_limit_node(state)
    assert patch["final_answer"] == patch["final_text"]
    assert "5 Runden" in patch["final_text"]
