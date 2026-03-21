from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app._legacy_v2.nodes import nodes_flows
from app._legacy_v2.sealai_graph_v2 import create_sealai_graph_v2
from app._legacy_v2.utils import context_manager
from app._legacy_v2.utils.jinja import render_template


def test_response_router_prefers_synthesized_text_for_tangential_intent() -> None:
    rendered = render_template(
        "response_router.j2",
        {
            "intent_goal": "material_research",
            "ask_missing_request": None,
            "response_text": "",
            "knowledge_material": "",
            "knowledge_lifetime": "",
            "knowledge_generic": "",
            "error": None,
            "rag_response_text": "Kyrolon ist ein PTFE-basierter Werkstoff mit hoher Medienbestaendigkeit.",
            "rag_context": "[1] /tmp/kyrolon.pdf page 2 (score 0.89) ...",
            "context": "raw chunk dump",
        },
    )
    assert "Kyrolon ist ein PTFE-basierter Werkstoff" in rendered
    assert "raw chunk dump" not in rendered


def test_response_router_does_not_fallback_to_raw_context_for_tangential_intent() -> None:
    rendered = render_template(
        "response_router.j2",
        {
            "intent_goal": "material_research",
            "ask_missing_request": None,
            "response_text": "",
            "knowledge_material": "",
            "knowledge_lifetime": "",
            "knowledge_generic": "",
            "error": None,
            "rag_response_text": "",
            "rag_context": "[1] /tmp/kyrolon.pdf page 2 (score 0.89) ...",
            "context": "raw chunk dump",
        },
    )
    assert "raw chunk dump" not in rendered
    assert "/tmp/kyrolon.pdf" not in rendered


def test_response_router_prefers_grounded_rag_text_even_for_final_engineering_response() -> None:
    rendered = render_template(
        "response_router.j2",
        {
            "intent_goal": "design_recommendation",
            "intent_category": "ENGINEERING_CALCULATION",
            "response_kind": "final",
            "requires_rag": True,
            "ask_missing_request": None,
            "calc_results": {"v_surface_m_s": 12.5},
            "response_text": "",
            "knowledge_material": "",
            "knowledge_lifetime": "",
            "knowledge_generic": "",
            "error": None,
            "rag_response_text": "Kyrolon ist ein PTFE-basierter Werkstoff mit hoher Medienbestaendigkeit.",
            "panel_rag_context": "[1] /tmp/kyrolon.pdf page 2 (score 0.89) ...",
            "rag_context": "[1] /tmp/kyrolon.pdf page 2 (score 0.89) ...",
            "context": "raw chunk dump",
            "engineering_profile": {"pressure_bar": 5, "speed_rpm": 3000},
            "extracted_params": {},
        },
    )
    assert "Kyrolon ist ein PTFE-basierter Werkstoff" in rendered
    assert "Status-Update:" not in rendered


def test_response_router_uses_panel_rag_context_when_grounded_text_exists_only_as_context() -> None:
    rendered = render_template(
        "response_router.j2",
        {
            "intent_goal": "design_recommendation",
            "intent_category": "ENGINEERING_CALCULATION",
            "response_kind": "final",
            "requires_rag": True,
            "ask_missing_request": None,
            "calc_results": {},
            "response_text": "",
            "knowledge_material": "",
            "knowledge_lifetime": "",
            "knowledge_generic": "",
            "error": None,
            "rag_response_text": "",
            "panel_rag_context": "Kyrolon 79X ist eine Marke der RBS Dichtungstechnik GmbH.",
            "rag_context": "raw chunk dump",
            "context": "raw chunk dump",
            "engineering_profile": {},
            "extracted_params": {},
        },
    )
    assert "Kyrolon 79X ist eine Marke" in rendered
    assert "Status-Update:" not in rendered


def test_graph_routes_p2_lookup_through_rag_synthesis_node() -> None:
    builder = create_sealai_graph_v2(
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
        return_builder=True,
    )
    edges = {(source, target) for source, target in builder.edges}
    assert ("node_p2_rag_lookup", "node_p2_rag_synthesize") in edges
    assert ("node_p2_rag_synthesize", "node_p4a_extract") in edges


def test_material_retrieved_context_strips_render_scaffolding() -> None:
    payload = {
        "context": (
            "**Gefundene Informationen aus der Wissensdatenbank:**\n"
            "- Dokument: **kyrolon.pdf** | Abschnitt: *Overview* | Score: 0.91\n"
            "Kyrolon ist ein PTFE-Compound fuer verschleisskritische Anwendungen.\n"
            "Quelle: /tmp/kyrolon.pdf"
        )
    }
    hits = [
        {
            "snippet": "Kyrolon ist ein PTFE-Compound fuer verschleisskritische Anwendungen.",
            "metadata": {},
        }
    ]

    rendered = nodes_flows._build_material_retrieved_context(payload, hits)

    assert "Kyrolon ist ein PTFE-Compound" in rendered
    assert "Dokument:" not in rendered
    assert "Score:" not in rendered
    assert "/tmp/kyrolon.pdf" not in rendered


def test_context_manager_rag_block_hides_trace_metadata() -> None:
    rendered = context_manager._render_rag_context_block(
        [
            {
                "authority_score": 0.9,
                "retrieval_score": 0.88,
                "source": "/tmp/kyrolon.pdf",
                "text": "Kyrolon ist ein PTFE-Compound fuer verschleisskritische Anwendungen.",
            }
        ],
        rag_budget_tokens=120,
    )

    assert "Kyrolon ist ein PTFE-Compound" in rendered
    assert "authority=" not in rendered
    assert "score=" not in rendered
    assert "/tmp/kyrolon.pdf" not in rendered


def test_context_manager_build_final_context_strips_retrieval_scaffolding_from_state_context() -> None:
    rendered = context_manager.build_final_context(
        {
            "context": (
                "**Gefundene Informationen aus der Wissensdatenbank:**\n"
                "- Dokument: **kyrolon.pdf** | Abschnitt: *Overview* | Score: 0.91\n"
                "Kyrolon ist ein PTFE-Compound fuer verschleisskritische Anwendungen.\n"
                "Quelle: /tmp/kyrolon.pdf"
            )
        },
        max_tokens=3000,
    )

    assert "Kyrolon ist ein PTFE-Compound" in rendered
    assert "Dokument:" not in rendered
    assert "Score:" not in rendered
    assert "/tmp/kyrolon.pdf" not in rendered
