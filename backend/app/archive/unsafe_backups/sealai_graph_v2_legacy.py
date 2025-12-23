# backend/app/langgraph_v2/sealai_graph_v2.py
"""
LangGraph v2 Definition for SealAI.
"""
from __future__ import annotations

import os
import re
import uuid
from typing import Dict, Any, Optional

import structlog

from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph

from app.langgraph_v2.state import SealAIState
from app.langgraph.io import CoverageAnalysis
from app.langgraph_v2.constants import CHECKPOINTER_NAMESPACE_V2
from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer
from app.langgraph_v2.utils.messages import latest_user_text

# Import Nodes
from app.langgraph_v2.nodes.nodes_resume import (
    resume_router_node,
    await_user_input_node,
)
from app.langgraph_v2.nodes.nodes_discovery import (
    discovery_intake_node,
    discovery_summarize_node,
    confirm_gate_node,
)
from app.langgraph_v2.nodes.nodes_intent import (
    entry_router_node,
    intent_projector_node,
)
from app.langgraph_v2.nodes.nodes_preflight import (
    preflight_use_case_node,
    seal_family_selector_node,
    parameter_profile_builder_node,
    ingest_missing_user_input_node,
    coverage_analysis_node,
    ask_missing_node,
    calc_node,
    analysis_gate_node,
)
from app.langgraph_v2.nodes.nodes_consulting import (
    consulting_supervisor_node,
    material_requirements_node,
    material_candidate_generation_node,
    material_candidate_ranking_node,
    material_exit_node,
)
from app.langgraph_v2.nodes.response_node import response_node
from app.langgraph_v2.nodes.nodes_validation import (
    answer_synthesizer_node,
)
from app.langgraph_v2.nodes.nodes_knowledge import (
    knowledge_router_node,
    knowledge_material_node,
    knowledge_lifetime_node,
    generic_sealing_qa_node,
)
from app.langgraph_v2.nodes.nodes_error import (
    smalltalk_node,
    out_of_scope_node,
)

logger = structlog.get_logger("langgraph_v2.graph")


# ---------------------------------------------------------------------------
# Smalltalk-Heuristik (Fast-Path vor Discovery/Preflight)
# ---------------------------------------------------------------------------


def _looks_like_smalltalk(text: str | None) -> bool:
    """
    Sehr gezielte Heuristik für kurze Grüße/Dank/Smalltalk.

    Wichtig:
    - bewusst schmal gehalten, damit technische Anfragen nicht „geschluckt“ werden
    - alles andere läuft normal durch Discovery/Intent/Consulting
    """
    if not text:
        return False

    normalized = re.sub(r"[!?.]+$", "", text or "").strip().lower()
    normalized = normalized.translate(
        str.maketrans(
            {
                "ß": "ss",
                "ü": "u",
                "ä": "a",
                "ö": "o",
            }
        )
    )
    normalized = re.sub(r"\s+", " ", normalized)

    SMALLTALK_PATTERNS = [
        r"^(hallo|hi|hey)$",
        r"^(servus|moin)$",
        r"^(gruss dich|grues dich|gruezi|gruss gott|grussgott)$",
        r"^(guten (morgen|tag|abend))$",
        r"^(danke|dankeschoen|danke dir|thx)$",
    ]
    return any(re.match(pat, normalized) for pat in SMALLTALK_PATTERNS)


def create_sealai_graph_v2(checkpointer=None, require_async=True) -> CompiledStateGraph:
    builder = StateGraph(SealAIState)

    # --- Add Nodes ---
    # Resume / Entry
    builder.add_node("resume_router_node", resume_router_node)
    builder.add_node("discovery_intake_node", discovery_intake_node)
    builder.add_node("discovery_summarize_node", discovery_summarize_node)
    builder.add_node("confirm_gate_node", confirm_gate_node)

    # Intent
    builder.add_node("entry_router_node", entry_router_node)
    builder.add_node("intent_projector_node", intent_projector_node)

    # Consulting Chain
    builder.add_node("preflight_use_case_node", preflight_use_case_node)
    builder.add_node("seal_family_selector_node", seal_family_selector_node)
    builder.add_node("parameter_profile_builder_node", parameter_profile_builder_node)
    builder.add_node("ingest_missing_user_input_node", ingest_missing_user_input_node)
    builder.add_node("coverage_analysis_node", coverage_analysis_node)
    builder.add_node("ask_missing_node", ask_missing_node)
    builder.add_node("await_user_input_node", await_user_input_node)
    builder.add_node("calc_node", calc_node)
    builder.add_node("analysis_gate_node", analysis_gate_node)
    builder.add_node("consulting_supervisor_node", consulting_supervisor_node)
    builder.add_node("material_requirements_node", material_requirements_node)
    builder.add_node("material_candidate_generation_node", material_candidate_generation_node)
    builder.add_node("material_candidate_ranking_node", material_candidate_ranking_node)
    builder.add_node("material_exit_node", material_exit_node)
    builder.add_node("answer_synthesizer_node", answer_synthesizer_node)
    builder.add_node("response_node", response_node)

    # Knowledge / FAQ
    builder.add_node("knowledge_router_node", knowledge_router_node)
    builder.add_node("knowledge_material_node", knowledge_material_node)
    builder.add_node("knowledge_lifetime_node", knowledge_lifetime_node)
    builder.add_node("generic_sealing_qa_node", generic_sealing_qa_node)

    # Smalltalk / Out-of-scope
    builder.add_node("smalltalk_node", smalltalk_node)
    builder.add_node("out_of_scope_node", out_of_scope_node)

    # --- Edges ---

    # Einstieg
    builder.add_edge(START, "resume_router_node")

    def _resume_router(state: SealAIState) -> str:
        """
        Erste Weiche nach START:

        1. Wenn wir auf eine Ask-Missing-Antwort warten → resume_technical / resume_discovery.
        2. Sonst: prüfe letzte User-Eingabe auf Smalltalk.
           - Bei klar erkennbarem Smalltalk → direkt smalltalk-Fast-Path
           - Sonst → frischer Discovery-Flow
        """
        if bool(state.get("awaiting_user_input")):
            scope = state.get("ask_missing_scope") or (
                "technical" if state.get("missing_params") else "discovery"
            )
            return f"resume_{scope}"

        # Fresh entry: prüfe Smalltalk, bevor Discovery/Preflight überhaupt starten
        last_user = latest_user_text(state.get("messages"))
        if _looks_like_smalltalk(last_user):
            logger.info(
                "resume_router_smalltalk_fastpath",
                last_user=last_user,
                thread_id=state.thread_id,
                user_id=state.user_id,
            )
            return "smalltalk"

        return "fresh"

    builder.add_conditional_edges(
        "resume_router_node",
        _resume_router,
        {
            "resume_technical": "ingest_missing_user_input_node",
            "resume_discovery": "discovery_summarize_node",
            "smalltalk": "smalltalk_node",
            "fresh": "discovery_intake_node",
            "__else__": "discovery_intake_node",
        },
    )

    builder.add_edge("discovery_intake_node", "discovery_summarize_node")
    builder.add_edge("discovery_summarize_node", "confirm_gate_node")

    # PATCH/FIX: Discovery ask-missing gating – route to ask_missing_node when needed
    def _confirm_gate_router(state: SealAIState) -> str:
        if state.ask_missing_request is not None:
            return "ask_missing"
        return "respond"

    builder.add_conditional_edges(
        "confirm_gate_node",
        _confirm_gate_router,
        {
            "ask_missing": "ask_missing_node",
            "respond": "response_node",
            "__else__": "response_node",
        },
    )

    builder.add_edge("entry_router_node", "intent_projector_node")

    def _intent_key_for_routing(state: SealAIState) -> str:
        intent_obj = state.get("intent")
        if hasattr(intent_obj, "key"):
            key = getattr(intent_obj, "key") or "generic_sealing_qa"
        elif isinstance(intent_obj, dict):
            key = intent_obj.get("key") or "generic_sealing_qa"
        else:
            key = "generic_sealing_qa"
        return str(key)

    # Consulting Parameter-Coverage-Router
    def _parameter_coverage_router(state: SealAIState) -> str:
        coverage = 0.0
        coverage_analysis = state.get("coverage_analysis")
        if isinstance(coverage_analysis, dict):
            coverage_analysis = CoverageAnalysis.model_validate(coverage_analysis)
        if isinstance(coverage_analysis, CoverageAnalysis):
            coverage = float(coverage_analysis.coverage_score)
        elif state.get("coverage_score") is not None:
            try:
                coverage = float(state.get("coverage_score") or 0.0)
            except Exception:
                coverage = 0.0

        if coverage >= 0.85:
            return "continue"
        return "ask"

    # Haupt-Routing nach Intent
    builder.add_conditional_edges(
        "intent_projector_node",
        _intent_key_for_routing,
        {
            "smalltalk": "smalltalk_node",
            "out_of_scope": "out_of_scope_node",
            "consulting_preflight": "preflight_use_case_node",
            "knowledge_material": "knowledge_router_node",
            "knowledge_lifetime": "knowledge_router_node",
            "knowledge_norms": "knowledge_router_node",
            "generic_sealing_qa": "knowledge_router_node",
            "__else__": "knowledge_router_node",
        },
    )

    # Consulting-Chain
    builder.add_edge("preflight_use_case_node", "seal_family_selector_node")
    builder.add_edge("seal_family_selector_node", "parameter_profile_builder_node")
    builder.add_edge("parameter_profile_builder_node", "ingest_missing_user_input_node")
    builder.add_edge("ingest_missing_user_input_node", "coverage_analysis_node")

    builder.add_conditional_edges(
        "coverage_analysis_node",
        _parameter_coverage_router,
        {
            "continue": "calc_node",
            "ask": "ask_missing_node",
        },
    )

    builder.add_edge("calc_node", "analysis_gate_node")

    # PATCH/FIX: Calc-Error branch routing – stop on error via responder
    def _analysis_gate_router(state: SealAIState) -> str:
        if str(state.phase or "").lower() == "error" or not bool(state.get("calc_results_ok")):
            return "error"
        return "ok"

    builder.add_conditional_edges(
        "analysis_gate_node",
        _analysis_gate_router,
        {
            "ok": "consulting_supervisor_node",
            "error": "response_node",
        },
    )

    # Supervisor Logic
    def _supervisor_router(state: SealAIState) -> str:
        working_memory = state.working_memory.as_dict() if state.working_memory else {}
        decision = str(working_memory.get("supervisor_decision", "NEXT") or "NEXT").upper()
        retries = int(working_memory.get("retries") or 0)
        if decision == "RETRY" and retries <= 2:
            return "retry"
        if decision == "ESCALATE":
            return "error"
        if decision == "END_WITH_MESSAGE":
            return "respond"
        return "next"

    builder.add_conditional_edges(
        "consulting_supervisor_node",
        _supervisor_router,
        {
            "next": "material_requirements_node",
            "retry": "ask_missing_node",
            "error": "out_of_scope_node",
            "respond": "response_node",
        },
    )

    builder.add_edge("material_requirements_node", "material_candidate_generation_node")
    builder.add_edge("material_candidate_generation_node", "material_candidate_ranking_node")
    builder.add_edge("material_candidate_ranking_node", "material_exit_node")
    builder.add_edge("material_exit_node", "answer_synthesizer_node")
    builder.add_edge("answer_synthesizer_node", END)
    builder.add_edge("ask_missing_node", "response_node")

    # Smalltalk / Out-of-scope laufen durch den Responder
    builder.add_edge("smalltalk_node", "response_node")
    builder.add_edge("out_of_scope_node", "response_node")

    # Knowledge-Routing
    def _intent_key_for_knowledge(state: SealAIState) -> str:
        intent_obj = state.get("intent")
        if hasattr(intent_obj, "key"):
            key = getattr(intent_obj, "key") or "generic_sealing_qa"
        elif isinstance(intent_obj, dict):
            key = intent_obj.get("key") or "generic_sealing_qa"
        else:
            key = "generic_sealing_qa"
        return str(key)

    builder.add_conditional_edges(
        "knowledge_router_node",
        _intent_key_for_knowledge,
        {
            "knowledge_material": "knowledge_material_node",
            "knowledge_lifetime": "knowledge_lifetime_node",
            "generic_sealing_qa": "generic_sealing_qa_node",
            "__else__": "generic_sealing_qa_node",
        },
    )

    # Knowledge-Nodes gehen durch den zentralen Responder
    builder.add_edge("knowledge_material_node", "response_node")
    builder.add_edge("knowledge_lifetime_node", "response_node")
    builder.add_edge("generic_sealing_qa_node", "response_node")

    # Responder-Router
    def _response_router(state: SealAIState) -> str:
        if bool(state.awaiting_user_input):
            return "await"
        if str(state.phase or "") == "intent":
            return "continue_intent"
        return "end"

    builder.add_conditional_edges(
        "response_node",
        _response_router,
        {
            "await": "await_user_input_node",
            "continue_intent": "entry_router_node",
            "end": END,
            "__else__": END,
        },
    )

    builder.add_edge("await_user_input_node", END)

    if checkpointer is None:
        checkpointer = make_v2_checkpointer(require_async=require_async)

    return builder.compile(checkpointer=checkpointer)


_GRAPH_CACHE: Optional[CompiledStateGraph] = None


def get_sealai_graph_v2() -> CompiledStateGraph:
    """Return cached compiled graph (async checkpointer ready)."""
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        _GRAPH_CACHE = create_sealai_graph_v2(require_async=True)
    return _GRAPH_CACHE


def build_v2_config(*, thread_id: str, user_id: str) -> Dict[str, Any]:
    """Common LangGraph config for v2 (includes run_id for observability)."""
    run_id = str(uuid.uuid4())
    return {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
            "checkpoint_ns": CHECKPOINTER_NAMESPACE_V2,
            "run_id": run_id,
        },
        "metadata": {
            "run_id": run_id,
            "thread_id": thread_id,
            "user_id": user_id,
        },
    }


__all__ = ["create_sealai_graph_v2", "get_sealai_graph_v2", "build_v2_config"]
