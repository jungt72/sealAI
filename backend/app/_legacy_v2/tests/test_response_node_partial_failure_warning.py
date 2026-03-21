from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app._legacy_v2.nodes.response_node import response_node
from app._legacy_v2.state import SealAIState


def test_response_node_prefixes_partial_expert_failure_warning() -> None:
    state = SealAIState(
        conversation={"intent": {"goal": "design_recommendation"}},
        working_profile={
            "engineering_profile": {"pressure_max_bar": 16.0, "rpm": 1500.0},
            "calc_results": {"v_surface_m_s": 2.5},
        },
        reasoning={"phase": "final"},
        system={"error": "partial_expert_failure"},
    )

    patch = response_node(state)
    text = patch["system"]["final_text"]

    assert text.startswith(
        "Ein Teil der Experten-Analyse ist fehlgeschlagen, bitte Ergebnisse kritisch pruefen."
    )


def test_response_node_preserves_existing_final_answer_from_subgraph() -> None:
    final_text = "Kyrolon ist ein PTFE-Compound fuer verschleisskritische Anwendungen."
    state = SealAIState(
        conversation={
            "messages": [
                HumanMessage(content="Was kannst du mir ueber Kyrolon sagen?"),
                AIMessage(content=final_text),
            ]
        },
        reasoning={"phase": "final"},
        system={
            "final_text": final_text,
            "final_answer": final_text,
        },
    )

    patch = response_node(state)

    assert patch["system"]["final_text"] == final_text
    assert patch["system"]["final_answer"] == final_text
    assert patch["reasoning"]["last_node"] == "response_node"
    assert "conversation" not in patch
