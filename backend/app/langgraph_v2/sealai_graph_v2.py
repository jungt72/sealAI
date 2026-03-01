"""Rebuilt LangGraph v2 Definition for SealAI with new frontdoor/supervisor topology."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
import uuid
from typing import Any, Dict, List
import json

import structlog
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableParallel
from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from langgraph.types import Command

from app.core.memory import get_postgres_store
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.checkpointer import make_v2_checkpointer_async
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.llm_factory import LazyChatOpenAI
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.threading import stable_thread_key
from app.langgraph_v2.utils.state_debug import log_state_debug
from app.mcp.knowledge_tool import discover_tools_for_scopes

logger = structlog.get_logger("langgraph_v2.graph")


# ---------------------------------------------------------------------------
# Node Imports
# ---------------------------------------------------------------------------

from app.langgraph_v2.nodes.profile_loader import profile_loader_node
from app.langgraph_v2.nodes.node_router import node_router
from app.services.rag.nodes.p1_context import node_p1_context
from app.services.rag.nodes.p2_rag_lookup import node_p2_rag_lookup
from app.services.rag.nodes.p3_gap_detection import node_p3_gap_detection
from app.services.rag.nodes.p3_5_merge import node_p3_5_merge
from app.services.rag.nodes.p4a_extract import node_p4a_extract
from app.services.rag.nodes.p4b_calc_render import node_p4b_calc_render
from app.services.rag.nodes.p4_live_calc import node_p4_live_calc
from app.services.rag.nodes.p4_5_quality_gate import node_p4_5_qgate
from app.services.rag.nodes.p5_procurement import node_p5_procurement
from app.services.rag.nodes.p6_generate_pdf import node_p6_generate_pdf
from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node
from app.langgraph_v2.nodes.nodes_confirm import confirm_checkpoint_node, confirm_recommendation_node
from app.langgraph_v2.nodes.nodes_supervisor import (
    aggregator_node,
    calculator_agent_node,
    panel_calculator_node,
    panel_material_node,
    pricing_agent_node,
    safety_agent_node,
    supervisor_policy_node,
)
from app.langgraph_v2.nodes.reducer import reducer_node
from app.langgraph_v2.nodes.response_node import response_node
from app.langgraph_v2.nodes.nodes_resume import (
    confirm_reject_node,
    confirm_resume_node,
    resume_router_node,
)
from app.langgraph_v2.nodes.nodes_error import smalltalk_node, turn_limit_node
from app.langgraph_v2.nodes.orchestrator import orchestrator_node
from app.langgraph_v2.nodes.factcard_lookup import node_factcard_lookup
from app.langgraph_v2.nodes.compound_filter import node_compound_filter
from app.langgraph_v2.nodes.merge_deterministic import node_merge_deterministic
from app.langgraph_v2.nodes.route_after_frontdoor import route_after_frontdoor_node
from app.langgraph_v2.nodes.safety_synonym_guard_node import safety_synonym_guard_node
from app.langgraph_v2.nodes.combinatorial_chemistry_guard import combinatorial_chemistry_guard_node
from app.langgraph_v2.nodes.reasoning_core_node import reasoning_core_node
from app.langgraph_v2.nodes.p4_6_number_verification import node_p4_6_number_verification
from app.langgraph_v2.nodes.request_clarification import request_clarification_node
from app.langgraph_v2.nodes.rfq_validator import rfq_validator_node
from app.langgraph_v2.nodes.answer_subgraph.subgraph_builder import (
    answer_subgraph_node,
    answer_subgraph_node_async,
)
from app.langgraph_v2.nodes.conversational_rag import conversational_rag_node
from app.langgraph_v2.nodes.troubleshooting_wizard import troubleshooting_wizard_node
from app.langgraph_v2.nodes.hitl_triage_node import hitl_triage_node
from app.langgraph_v2.nodes.worm_evidence_node import worm_evidence_node
from app.langgraph_v2.nodes.nodes_flows import (
    build_final_answer_context,
    map_final_answer_to_state,
    material_agent_node,
    material_comparison_node,
    calculator_node,
    critical_review_node,
    discovery_schema_node,
    leakage_troubleshooting_node,
    parameter_check_node,
    product_explainer_node,
    product_match_node,
    profile_agent_node,
    rag_support_node,
    render_final_answer_draft,
    prepare_final_answer_llm_payload,
    troubleshooting_explainer_node,
    troubleshooting_pattern_node,
    validation_agent_node,
)


# ---------------------------------------------------------------------------
# State Helper
# ---------------------------------------------------------------------------


def _ensure_state_model(state: Any) -> SealAIState:
    """Akzeptiert dict/SealAIState und gibt garantiert ein SealAIState-Objekt zurück."""
    if isinstance(state, SealAIState):
        return state
    return SealAIState.model_validate(state or {})


# ---------------------------------------------------------------------------
# Final-Answer: Jinja-Templates & Context
# ---------------------------------------------------------------------------

SMALLTALK_TEMPLATE = "final_answer_smalltalk_v2.j2"
DISCOVERY_TEMPLATE = "final_answer_discovery_v2.j2"
RECOMMENDATION_TEMPLATE = "final_answer_recommendation_v2.j2"
EXPLANATION_TEMPLATE = "final_answer_explanation_v2.j2"
TROUBLESHOOTING_TEMPLATE = "final_answer_troubleshooting_v2.j2"
OUT_OF_SCOPE_TEMPLATE = "final_answer_out_of_scope_v2.j2"
SAFETY_CHECK_TEMPLATE = "check_1.1.0.j2"
SAFETY_CHECK_VERSION = "check_1.1.0"
CONVERSATIONAL_RAG_NODE_KEY = "conversational_rag_node"
LANGSMITH_RUN_NAME = "sealai_langgraph_v2"
LANGSMITH_TRACE_TAGS: List[str] = [
    "sealai",
    "langgraph_v2",
    "phase_0_observability",
    "audit_schema_v1",
]


def _select_final_answer_template(goal: str | None, recommendation_go: bool) -> str:
    if goal == "smalltalk":
        return SMALLTALK_TEMPLATE
    if goal == "design_recommendation":
        return RECOMMENDATION_TEMPLATE if recommendation_go else DISCOVERY_TEMPLATE
    if goal == "explanation_or_comparison":
        return EXPLANATION_TEMPLATE
    if goal == "troubleshooting_leakage":
        return TROUBLESHOOTING_TEMPLATE
    if goal == "out_of_scope":
        return OUT_OF_SCOPE_TEMPLATE
    return DISCOVERY_TEMPLATE


def _build_final_answer_template_context(
    state: SealAIState,
    base_context: Dict[str, Any],
    *,
    draft: str,
    goal: str,
    coverage_score: float,
    coverage_gaps: List[str],
    coverage_gaps_text: str,
    recommendation_ready: bool,
    recommendation_go: bool,
    latest_user_text: str | None,
    is_micro_smalltalk: bool,
) -> Dict[str, Any]:
    parameters = state.parameters.as_dict()
    extracted_params = dict(state.extracted_params or {})
    if extracted_params:
        for key, value in extracted_params.items():
            if value is not None:
                parameters.setdefault(key, value)
    if parameters.get("speed_rpm") is None and parameters.get("rpm") is not None:
        parameters["speed_rpm"] = parameters.get("rpm")
    if parameters.get("shaft_diameter") is None:
        shaft_d = parameters.get("shaft_d1_mm") or parameters.get("shaft_d1") or parameters.get("d1")
        if shaft_d is not None:
            parameters["shaft_diameter"] = shaft_d
    if parameters.get("pressure_bar") is None:
        pressure_bar = parameters.get("pressure_max_bar") or parameters.get("p_max")
        if pressure_bar is not None:
            parameters["pressure_bar"] = pressure_bar
    if parameters.get("temperature_C") is None:
        temperature_c = parameters.get("temperature_max_c") or parameters.get("temp_max") or parameters.get("temperature_max")
        if temperature_c is not None:
            parameters["temperature_C"] = temperature_c
    profile_snapshot = {}
    if state.working_profile is not None:
        profile_snapshot = state.working_profile.model_dump(exclude_none=True)
    for key, value in parameters.items():
        if value is not None:
            profile_snapshot.setdefault(key, value)
    calc_results = state.calc_results.model_dump(exclude_none=True) if state.calc_results else {}
    recommendation = state.recommendation.model_dump(exclude_none=True) if state.recommendation else {}
    working_memory = state.working_memory.model_dump(exclude_none=True) if state.working_memory else {}
    sources = [src.model_dump(exclude_none=True) for src in (state.sources or [])]
    template_context = dict(base_context or {})
    available_mcp_tools = discover_mcp_tools_for_state(state)
    template_context.update(
        {
            "draft": draft,
            "goal": goal,
            "coverage_score": coverage_score,
            "coverage_gaps": coverage_gaps,
            "coverage_gaps_text": coverage_gaps_text,
            "recommendation_ready": recommendation_ready,
            "recommendation_go": recommendation_go,
            "user_text": latest_user_text,
            "latest_user_text": latest_user_text,
            "is_micro_smalltalk": is_micro_smalltalk,
            "discovery_summary": state.discovery_summary,
            "discovery_missing": state.discovery_missing or [],
            "discovery_coverage": state.discovery_coverage,
            "application_category": state.application_category,
            "motion_type": state.motion_type,
            "seal_family": state.seal_family,
            "plan": state.plan or {},
            "working_memory": working_memory,
            "sources": sources,
            "recommendation": recommendation,
            "calc_results": calc_results,
            "intent_high_impact_gaps": getattr(state.intent, "high_impact_gaps", []),
            "parameters": parameters,
            "profile": profile_snapshot,
            "extracted_params": extracted_params,
            "flags": state.flags or {},
            "user_context": getattr(state, "user_context", {}) or {}, # INJECTED
            "available_mcp_tools": available_mcp_tools,
        }
    )
    return template_context


def _normalize_smalltalk_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = text.strip().lower()
    normalized = re.sub(r"[!?.]+$", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


_ROTARY_QUERY_MARKERS = (
    "rotary",
    "rotierend",
    "welle",
    "wellen",
    "ruehrwerk",
    "rührwerk",
    "agitator",
    "mischer",
    "mixer",
)


def _is_rotary_query_text(user_text: str | None) -> bool:
    text = str(user_text or "").strip().lower()
    return any(marker in text for marker in _ROTARY_QUERY_MARKERS)


def _needs_rotary_insufficient_data_fallback(template_context: Dict[str, Any]) -> bool:
    if not _is_rotary_query_text(template_context.get("user_text") or template_context.get("latest_user_text")):
        return False

    recommendation_ready = bool(template_context.get("recommendation_ready"))
    coverage_score = float(template_context.get("coverage_score") or 0.0)
    coverage_gaps = [str(item).strip().lower() for item in (template_context.get("coverage_gaps") or []) if str(item).strip()]
    gap_blob = " ".join(coverage_gaps)
    parameters = template_context.get("parameters") if isinstance(template_context.get("parameters"), dict) else {}

    has_hardness = bool(parameters.get("shaft_hardness") or parameters.get("hardness"))
    has_runout = bool(parameters.get("shaft_runout") or parameters.get("runout") or parameters.get("dynamic_runout"))

    if not has_hardness or not has_runout:
        return True
    if not recommendation_ready or coverage_score < 0.99:
        return True
    return ("hardness" in gap_blob) or ("runout" in gap_blob) or ("wellenschlag" in gap_blob)


def _collect_retrieved_facts(template_context: Dict[str, Any]) -> str:
    blocks: List[str] = []
    seen: set[str] = set()

    def _append(value: Any) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        blocks.append(text)

    _append(template_context.get("context"))
    _append(template_context.get("material_retrieved_context"))

    working_memory = template_context.get("working_memory")
    if isinstance(working_memory, dict):
        panel_material = working_memory.get("panel_material")
        if isinstance(panel_material, dict):
            _append(panel_material.get("rag_context"))
            _append(panel_material.get("reducer_context"))
        comparison_notes = working_memory.get("comparison_notes")
        if isinstance(comparison_notes, dict):
            _append(comparison_notes.get("rag_context"))

    return "\n\n".join(blocks).strip()


def _render_final_prompt_package(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build system prompt + metadata package for final answer generation.
    """
    goal = payload["template_context"].get("goal")
    template_name = _select_final_answer_template(
        goal,
        payload["template_context"].get("recommendation_go", False),
    )
    payload["template_context"].setdefault("is_micro_smalltalk", False)
    plan = payload["template_context"].get("plan") or {}
    style_profile = (plan.get("style_profile") or "senior_sealing_engineer_de") if isinstance(plan, dict) else "senior_sealing_engineer_de"
    include_policy = str(style_profile).strip().lower() not in {"off", "none", "disabled", "disable"}

    prompt_text = render_template(template_name, payload["template_context"])
    try:
        safety_check_text = render_template(SAFETY_CHECK_TEMPLATE, {})
    except FileNotFoundError:
        safety_check_text = ""
    safety_check_text = (safety_check_text or "").strip()
    if safety_check_text:
        prompt_text = f"{safety_check_text}\n\n{(prompt_text or '').strip()}"
    if include_policy:
        policy_text = render_template("senior_policy_de.j2", {})
        policy_text = (policy_text or "").strip()
        if policy_text:
            prompt_text = f"{policy_text}\n\n{(prompt_text or '').strip()}"
    plan = payload["template_context"].get("plan") or {}
    if isinstance(plan, dict):
        raw_system_instructions = plan.get("system_instructions")
        if isinstance(raw_system_instructions, list):
            cleaned = [str(item).strip() for item in raw_system_instructions if str(item).strip()]
            if cleaned:
                prompt_text = f"{prompt_text}\n\n" + "\n".join(cleaned)

    if _needs_rotary_insufficient_data_fallback(payload.get("template_context") or {}):
        prompt_text = (
            f"{prompt_text}\n\n"
            "ROTARY INSUFFICIENT-DATA FAILSAFE:\n"
            "- Gib keine Materialempfehlung ab, solange wesentliche Daten fehlen.\n"
            "- Erklaere explizit: \"Dichtungstechnik SYSTEMTECHNIK ist\".\n"
            "- Nenne die Umfangsgeschwindigkeit mit Formel: v = (pi * d * n) / 60000 (d in mm, n in rpm, Ergebnis in m/s).\n"
            "- Fordere zwingend Wellenhaerte (mindestens 58 HRC fuer PTFE-Compounds) und dynamischen Wellenschlag (Run-out) ein."
        )

    state: Dict[str, str] = {}
    retrieved_chunks = _collect_retrieved_facts(payload["template_context"])
    if retrieved_chunks:
        state["context"] = retrieved_chunks
    logger.debug(
        "final_answer.llm_context_payload",
        has_context=bool(state.get("context")),
        context_chars=len(state.get("context") or ""),
    )
    prompt_text = (
        f"{prompt_text}\n\n"
        "### BEANTWORTUNGS-REGELN (Blueprint v4.1):\n"
        "1. Beantworte die Anfrage basierend auf dem bereitgestellten RAG-KONTEXT.\n"
        "2. GROUNDED REASONING: Du darfst technische Schlussfolgerungen ziehen und Informationen aus verschiedenen Chunks kombinieren, "
        "sofern sie sich logisch aus dem Text ableiten lassen.\n"
        "3. KEINE HALLUZINATIONEN: Erfinde niemals Spezifikationen, Werte oder Materialeigenschaften, die nicht im Kontext erwähnt werden.\n"
        "4. Falls der Kontext absolut keine relevanten Informationen enthält, sage: 'Ich habe in der Datenbank derzeit keine spezifischen Details dazu gefunden.'"
    )
    if state.get("context"):
        prompt_text = f"{prompt_text}\n\nRETRIEVED KNOWLEDGE BASE FACTS:\n{state['context']}"
    else:
        # We still explicitly label empty context but the reasoning logic handles the "no info" message
        prompt_text = f"{prompt_text}\n\nRETRIEVED KNOWLEDGE BASE FACTS:\n[EMPTY]"

    # BaseStore User Context Injection
    user_context = payload["template_context"].get("user_context")
    if user_context:
        context_str = json.dumps(user_context, indent=2, ensure_ascii=False)
        prompt_text = f"{prompt_text}\n\nUSER CONTEXT (LONG-TERM MEMORY):\n{context_str}"

    available_tools = payload["template_context"].get("available_mcp_tools") or []
    if isinstance(available_tools, list) and available_tools:
        lines = ["MCP TOOLS AVAILABLE TO THIS USER:"]
        for item in available_tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            description = str(item.get("description") or "").strip()
            lines.append(f"- {name}: {description}")
        if len(lines) > 1:
            prompt_text = f"{prompt_text}\n\n" + "\n".join(lines)

    meta = payload.get("meta") if isinstance(payload, dict) else None
    if isinstance(meta, dict):
        logger.info(
            "final_prompt_selected",
            goal=goal,
            selected_template_name=template_name,
            safety_check_version=SAFETY_CHECK_VERSION,
            senior_policy_enabled=bool(include_policy),
            phase=meta.get("phase"),
            last_node=meta.get("last_node"),
            run_id=meta.get("run_id"),
            thread_id=meta.get("thread_id"),
        )
    messages: List[BaseMessage] = [SystemMessage(content=prompt_text)]
    messages.extend(list(payload.get("messages") or []))
    return {
        "state": payload.get("state"),
        "messages": messages,
        "prompt_text": prompt_text,
        "prompt_metadata": {
            "selected_template_name": template_name,
            "prompt_version": SAFETY_CHECK_VERSION,
            "safety_check_template": SAFETY_CHECK_TEMPLATE,
            "senior_policy_enabled": bool(include_policy),
        },
    }


def _render_final_prompt_messages(payload: Dict[str, Any]) -> List[BaseMessage]:
    package = _render_final_prompt_package(payload)
    return list(package.get("messages") or [])


def _extract_auth_scopes_from_state(state: SealAIState) -> List[str]:
    user_context = getattr(state, "user_context", {}) or {}
    raw_scopes = user_context.get("auth_scopes")
    if raw_scopes is None:
        return []
    if isinstance(raw_scopes, str):
        return [token for token in raw_scopes.replace(",", " ").split() if token]
    if isinstance(raw_scopes, list):
        return [str(token).strip() for token in raw_scopes if str(token).strip()]
    return []


def discover_mcp_tools_for_state(state: SealAIState) -> List[Dict[str, Any]]:
    auth_scopes = _extract_auth_scopes_from_state(state)
    tools = discover_tools_for_scopes(auth_scopes)
    logger.info(
        "mcp_tool_discovery",
        scope_count=len(auth_scopes),
        scopes=sorted(set(auth_scopes)),
        matched_scope_count=len(set(auth_scopes) & {"mcp:pim:read", "mcp:knowledge:read"}),
        tool_count=len(tools),
        tools=[str(tool.get("name") or "") for tool in tools if isinstance(tool, dict)],
    )
    return tools


def _build_final_answer_chain() -> Any:
    llm = LazyChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
        cache=False,
        max_tokens=1000,
        streaming=True,
    )

    output_parser = StrOutputParser()

    def _prepare_inputs(state: Any) -> Dict[str, Any]:
        s = _ensure_state_model(state)
        messages = list(s.messages or [])
        log_state_debug("final_answer_node", s)

        context = build_final_answer_context(s)
        draft = render_final_answer_draft(context)

        goal = getattr(s.intent, "goal", "smalltalk") if s.intent else "smalltalk"
        ready = bool(getattr(s, "recommendation_ready", False))
        go = bool(getattr(s, "recommendation_go", False))

        coverage_score = (getattr(s, "coverage_score", 0.0) or 0.0)
        coverage_gaps = getattr(s, "coverage_gaps", []) or []
        coverage_gaps_text = ", ".join(str(item) for item in coverage_gaps if item)
        coverage_gaps_text = coverage_gaps_text or "keine"

        user_text = latest_user_text(messages)
        user_text_norm = _normalize_smalltalk_text(user_text)
        micro_greetings = {
            "hallo",
            "hi",
            "hey",
            "moin",
            "guten morgen",
            "guten tag",
            "guten abend",
            "servus",
        }
        is_micro_smalltalk = bool(
            goal == "smalltalk"
            and (len(user_text_norm) <= 12 or user_text_norm in micro_greetings)
        )

        template_context = _build_final_answer_template_context(
            state=s,
            base_context=context,
            draft=draft,
            goal=goal,
            coverage_score=coverage_score,
            coverage_gaps=coverage_gaps,
            coverage_gaps_text=coverage_gaps_text,
            recommendation_ready=ready,
            recommendation_go=go,
            latest_user_text=user_text,
            is_micro_smalltalk=is_micro_smalltalk,
        )
        template_context["user_text_norm"] = user_text_norm
        template_context["is_micro_smalltalk"] = is_micro_smalltalk
        return {
            "state": s,
            "messages": messages,
            "template_context": template_context,
        }

    async def _call_llm_async(d: dict) -> str:
        if d.get("forced_text"):
            return d["forced_text"]
        response = await llm.ainvoke(d.get("messages") or [])
        return output_parser.invoke(response)

    chain = (
        RunnableLambda(_prepare_inputs)
        | RunnableParallel(
            state=RunnableLambda(lambda d: d["state"]),
            draft=(
                RunnableLambda(
                    lambda d: {
                        "state": d["state"],
                        "messages": d["messages"],
                        "template_context": d["template_context"],
                        "meta": {
                            "phase": getattr(d["state"], "phase", None),
                            "last_node": getattr(d["state"], "last_node", None),
                            "run_id": getattr(d["state"], "run_id", None),
                            "thread_id": getattr(d["state"], "thread_id", None),
                        },
                    }
                )
                | RunnableLambda(_render_final_prompt_package)
                | RunnableLambda(
                    lambda d: prepare_final_answer_llm_payload(
                        _ensure_state_model(d.get("state")),
                        system_prompt=d.get("prompt_text") or "",
                        rendered_messages=list(d.get("messages") or []),
                        user_messages=list(getattr(d.get("state"), "messages", []) or []),
                        prompt_metadata=d.get("prompt_metadata") or {},
                    )
                )
                | RunnableParallel(
                    text=RunnableLambda(_call_llm_async),
                    prompt_text=RunnableLambda(lambda d: d.get("prompt_text") or ""),
                    prompt_metadata=RunnableLambda(lambda d: d.get("prompt_metadata") or {}),
                )
            ),
        )
        | RunnableLambda(
            lambda d: {
                **map_final_answer_to_state(
                    _ensure_state_model(d["state"]),
                    d["draft"].get("text") or "",
                    final_prompt=d["draft"].get("prompt_text") or "",
                    final_prompt_metadata=d["draft"].get("prompt_metadata") or {},
                ),
                "final_answer": (d["draft"].get("text") or "").strip()
            }
        )
    )

    return chain


# ---------------------------------------------------------------------------
# Router-Helpers
# ---------------------------------------------------------------------------


def _critical_review_router(state: SealAIState) -> str:
    critical = state.critical or {}
    status = str(critical.get("status") or "").lower()
    if status == "needs_refinement":
        return "refine"
    if status == "reject":
        return "reject"
    return "continue"


def _product_router(state: SealAIState) -> str:
    wants_products = bool(state.plan.get("want_product_recommendation"))
    return "include" if wants_products else "skip"


def _resolve_coverage_for_material(state: SealAIState) -> Dict[str, Any]:
    profile = getattr(state, "working_profile", None)
    raw = getattr(profile, "knowledge_coverage_check", {}) if profile is not None else {}
    if not isinstance(raw, dict):
        return {}

    material = str(
        (getattr(profile, "material", None) if profile is not None else None)
        or (state.material_choice or {}).get("material")
        or ""
    ).strip().upper()
    if not material:
        return raw

    material_keys = (material, material.lower(), material.upper())
    for key in material_keys:
        value = raw.get(key)
        if isinstance(value, dict):
            return value

    by_material = raw.get("by_material")
    if isinstance(by_material, dict):
        for key in material_keys:
            value = by_material.get(key)
            if isinstance(value, dict):
                return value

    return raw


def _all_mandatory_coverage_true(state: SealAIState) -> bool:
    coverage = _resolve_coverage_for_material(state)
    if not coverage:
        return False

    mandatory_seen = False
    for key, value in coverage.items():
        if str(key).startswith("_"):
            continue

        is_mandatory = True
        covered = False
        if isinstance(value, bool):
            covered = bool(value)
        elif isinstance(value, dict):
            is_mandatory = bool(value.get("mandatory", True))
            covered = bool(
                value.get("value") is True
                or value.get("covered") is True
                or value.get("ok") is True
            )
        else:
            # Unknown shapes are treated as uncovered when mandatory.
            covered = False

        if not is_mandatory:
            continue
        mandatory_seen = True
        if not covered:
            return False

    return mandatory_seen


def _has_unhandled_blocker_conflicts(state: SealAIState) -> bool:
    profile = getattr(state, "working_profile", None)
    conflicts = list(getattr(profile, "conflicts_detected", []) or []) if profile is not None else []
    for conflict in conflicts:
        if isinstance(conflict, dict):
            severity = str(conflict.get("severity") or "").upper()
            handled = bool(conflict.get("handled") or conflict.get("resolved"))
        else:
            severity = str(getattr(conflict, "severity", "") or "").upper()
            handled = bool(getattr(conflict, "handled", False) or getattr(conflict, "resolved", False))
        if severity == "BLOCKER" and not handled:
            return True
    return False


def _reasoning_turn_count(state: SealAIState) -> int:
    critical_iter = int((state.critical or {}).get("iteration_count") or 0)
    round_index = int(getattr(state, "round_index", 0) or 0)
    decision_rounds = len(getattr(state, "decision_log", []) or [])
    return max(critical_iter, round_index, decision_rounds)


def _has_sufficient_dynamic_parameters(state: SealAIState) -> bool:
    DYNAMIC_FIELDS = [
        "dp_dt_bar_per_s",
        "side_load_kn",
        "aed_required",
        "medium_additives",
        "fluid_contamination_iso",
        "surface_hardness_hrc",
        "pressure_spike_factor",
    ]
    profile = getattr(state, "working_profile", None)
    if profile is None:
        return False
    filled = sum(
        1 for f in DYNAMIC_FIELDS
        if getattr(profile, f, None) is not None
    )
    # Require at least 3 of 7 to be known before Reasoning Core
    return filled >= 3


def _deterministic_termination_router(state: SealAIState) -> str:
    log = structlog.get_logger()
    log.info("termination_router_called", turn=getattr(state, "turn_count", "MISSING"))
    
    # FIX 1 & 3: Primary Stop and Blocker Enforcement
    final_answer = str(getattr(state, "final_answer", "") or "")
    if "?" in final_answer:
        return "needs_data"

    if _has_unhandled_blocker_conflicts(state):
        log.warning("chemistry_blocker_enforced", thread_id=state.thread_id)
        return "request_clarification_node"

    # FIX 4: Reasoning Core Gate for Missing Mandatory Fields
    if not _has_sufficient_dynamic_parameters(state):
        log.info("reasoning_core_gated", reason="insufficient_dynamic_params")
        return "request_clarification_node"

    profile = getattr(state, "working_profile", None)
    risk_mitigated = bool(getattr(profile, "risk_mitigated", False)) if profile is not None else False
    coverage_ok = _all_mandatory_coverage_true(state)
    has_blockers = _has_unhandled_blocker_conflicts(state)
    turn_count = _reasoning_turn_count(state)
    awaiting_user_input = bool(getattr(state, "awaiting_user_input", False))
    turn = int(getattr(state, "turn_count", 0) or 0)
    validation = getattr(state, "validation", {}) or {}
    has_validation_issues = bool(validation.get("issues"))

    # Hard stop to prevent infinite reasoning loops.
    if turn >= 3:
        log.warning("loop_breaker_triggered", turn=turn)
        return "needs_data"

    if turn_count > 3:
        return "needs_data"

    # If we have gaps or issues after the first turn, stop and ask the user.
    if turn >= 1 and (awaiting_user_input or not coverage_ok or has_validation_issues):
        log.info("termination_router_stopping_on_gaps", turn=turn)
        return "needs_data"

    # If reasoning core just emitted a follow-up question, wait for user input.
    last_message = (getattr(state, "messages", None) or [None])[-1]
    last_message_type = str(getattr(last_message, "type", "") or "").lower()
    last_node = str(getattr(state, "last_node", "") or "")
    final_answer_text = str(getattr(state, "final_answer", "") or "")
    if (
        last_node == "reasoning_core_node"
        and last_message_type in {"ai", "assistant"}
        and "?" in final_answer_text
    ):
        return "needs_data"

    if coverage_ok and risk_mitigated and not has_blockers and not has_validation_issues:
        return "contract_first_output_node"
    if turn_count >= 3:
        return "human_review_node"
    if awaiting_user_input or not coverage_ok or has_validation_issues:
        return "needs_data"
    return "reasoning_core_node"


def _parameter_check_router(state: SealAIState) -> str:
    ready = bool(getattr(state, "recommendation_ready", False))
    go = bool(getattr(state, "recommendation_go", False))
    goal = getattr(getattr(state, "intent", None), "goal", None)
    if ready and go:
        return "calculator_node"
    if goal == "design_recommendation" and not ready:
        return "conversational_rag_node"
    return "supervisor_policy_node"


def _supervisor_policy_router(state: SealAIState) -> str:
    return str(getattr(state, "next_action", "FINALIZE") or "FINALIZE")


def _node_router_dispatch(state: SealAIState) -> str:
    turn = int(getattr(state, "turn_count", 0) or 0)
    if turn >= 3:
        return "clarification"

    classification = getattr(state, "router_classification", None) or "new_case"
    if classification in ("new_case", "follow_up"):
        return "frontdoor"
    if classification == "resume":
        return "resume_router"
    if classification == "clarification":
        return "clarification"
    if classification == "rfq_trigger":
        return "rfq_trigger"
    if classification == "turn_limit_exceeded":
        return "turn_limit_exceeded"
    return "frontdoor"


def _resume_router(state: SealAIState) -> str:
    if state.awaiting_user_confirmation and (state.confirm_decision or "").strip():
        decision = (state.confirm_decision or "").strip().lower()
        return "reject" if decision == "reject" else "resume"
    return "frontdoor"


def _frontdoor_router(state: SealAIState) -> str:
    flags = state.flags or {}
    task_intents_raw = flags.get("frontdoor_task_intents") or []
    task_intents = (
        [str(intent).strip() for intent in task_intents_raw]
        if isinstance(task_intents_raw, list)
        else []
    )
    has_task_intents = any(task_intents)
    social_opening = bool(flags.get("frontdoor_social_opening"))
    intent_category = str(flags.get("frontdoor_intent_category") or "").strip().upper()

    if has_task_intents:
        return "supervisor"
    if social_opening:
        return "smalltalk"
    if intent_category == "CHIT_CHAT":
        return "smalltalk"
    if bool(flags.get("frontdoor_technical_cue_veto")):
        return "supervisor"
    if bool(flags.get("frontdoor_bypass_supervisor")):
        return "smalltalk"
    return "supervisor"


def _reducer_router(state: SealAIState) -> str:
    if bool(getattr(state, "requires_human_review", False)):
        return "human_review"
    if state.intent and state.intent.goal == "explanation_or_comparison":
        return "conversational_rag"
    return "standard"


def _qgate_router(state: SealAIState) -> str:
    if bool(getattr(state, "qgate_has_blockers", False)):
        return "has_blockers"
    return "no_blockers"


def _number_verification_router(state: SealAIState) -> str:
    s = _ensure_state_model(state)
    goal = getattr(getattr(s, "intent", None), "goal", None)
    recommendation_ready = bool(getattr(s, "recommendation_ready", False))
    verification_passed = bool(getattr(s, "verification_passed", True))
    if goal == "design_recommendation" and not recommendation_ready:
        return "fallback_rag"
    return "pass" if verification_passed else "fail"


def _rfq_validator_router(state: SealAIState) -> str:
    return "ready" if bool(getattr(state, "rfq_ready", False)) else "missing"


def _troubleshooting_wizard_router(state: SealAIState) -> str:
    return "complete" if bool(getattr(state, "diagnostic_complete", False)) else "incomplete"


async def _qgate_router_async(state: SealAIState) -> str:
    return _qgate_router(state)


async def _rfq_validator_router_async(state: SealAIState) -> str:
    return _rfq_validator_router(state)


async def _number_verification_router_async(state: SealAIState) -> str:
    return _number_verification_router(state)


async def _troubleshooting_wizard_router_async(state: SealAIState) -> str:
    return _troubleshooting_wizard_router(state)


async def _node_router_dispatch_async(state: SealAIState) -> str:
    return _node_router_dispatch(state)


async def _parameter_check_router_async(state: SealAIState) -> str:
    return _parameter_check_router(state)


async def _critical_review_router_async(state: SealAIState) -> str:
    return _critical_review_router(state)


async def _deterministic_termination_router_async(state: SealAIState) -> str:
    return _deterministic_termination_router(state)


async def _product_router_async(state: SealAIState) -> str:
    return _product_router(state)


async def _supervisor_policy_router_async(state: SealAIState) -> str:
    return _supervisor_policy_router(state)


async def _resume_router_async(state: SealAIState) -> str:
    return _resume_router(state)


async def _frontdoor_router_async(state: SealAIState) -> str:
    return _frontdoor_router(state)


_RFQ_OR_LASTENHEFT_PATTERN = re.compile(
    r"\b("
    r"rfq"
    r"|request\s+for\s+quotation"
    r"|angebot"
    r"|quote"
    r"|lastenheft"
    r"|ausschreibung"
    r")\b",
    re.IGNORECASE,
)


def _is_rfq_or_spec_request(state: SealAIState) -> bool:
    user_text = latest_user_text(state.messages or []) or ""
    return bool(_RFQ_OR_LASTENHEFT_PATTERN.search(user_text))


def _merge_deterministic_router(state: SealAIState) -> str:
    """Route after parallel deterministic KB worker merge.

    - ``deterministic`` → response_node (pre-computed KB answer)
    - otherwise         → supervisor_policy_node
    """
    kb_result = state.kb_factcard_result or {}
    if _is_rfq_or_spec_request(state):
        logger.info("merge_deterministic.force_supervisor_for_rfq_context")
        return "supervisor"
    if kb_result.get("deterministic"):
        return "deterministic"
    return "supervisor"


async def _merge_deterministic_router_async(state: SealAIState) -> str:
    return _merge_deterministic_router(state)


def _frontdoor_parallel_fanout_node(_state: SealAIState) -> Dict[str, Any]:
    """No-op node to fan out into deterministic parallel workers."""
    return {}


async def _node_factcard_lookup_parallel(state: SealAIState) -> Dict[str, Any]:
    """Run FactCard lookup in parallel branch without conflicting last_node writes."""
    result = node_factcard_lookup(state)
    if asyncio.iscoroutine(result):
        result = await result
    updates = dict(result or {})
    updates.pop("last_node", None)
    return updates


async def _node_compound_filter_parallel(state: SealAIState) -> Dict[str, Any]:
    """Run compound filter in parallel branch without conflicting last_node writes."""
    result = node_compound_filter(state)
    if asyncio.iscoroutine(result):
        result = await result
    updates = dict(result or {})
    updates.pop("last_node", None)
    return updates


async def _reducer_router_async(state: SealAIState) -> str:
    return _reducer_router(state)


def human_review_node(state: SealAIState) -> Command:
    reviewer_signature = ""
    if isinstance(state.confirm_edits, dict):
        reviewer_signature = str(state.confirm_edits.get("reviewer_signature") or "").strip()
    if not reviewer_signature and isinstance(state.user_context, dict):
        reviewer_signature = str(state.user_context.get("reviewer_signature") or "").strip()

    requires_signature = str(state.safety_class or "").strip().upper() in {"SEV-1", "SEV-2"} or bool(
        (state.flags or {}).get("hitl_pause_required")
    )
    if requires_signature and not reviewer_signature:
        return Command(
            update={
                "phase": PHASE.CONFIRM,
                "last_node": "human_review_node",
                "awaiting_user_confirmation": True,
                "pending_action": "hitl_signature_required",
                "confirm_status": "pending",
                "error": "Reviewer signature required to resume SEV-1/SEV-2 case.",
            },
            goto="human_review_node",
        )

    confirmed_actions = list(state.confirmed_actions or [])
    if reviewer_signature and "hitl_review_signed" not in confirmed_actions:
        confirmed_actions.append("hitl_review_signed")
    flags = dict(state.flags or {})
    if reviewer_signature:
        flags["hitl_reviewer_signature"] = reviewer_signature

    return Command(
        update={
            "phase": PHASE.CONFIRM,
            "last_node": "human_review_node",
            "awaiting_user_confirmation": False,
            "pending_action": None,
            "confirm_status": "resolved",
            "confirm_resolved_at": datetime.now(timezone.utc).isoformat(),
            "confirmed_actions": confirmed_actions,
            "flags": flags,
            "error": None,
        },
        goto="worm_evidence_node",
    )


# ---------------------------------------------------------------------------
# Graph-Definition
# ---------------------------------------------------------------------------


def create_sealai_graph_v2(checkpointer: BaseCheckpointSaver, store: BaseStore, *, require_async: bool = True) -> CompiledStateGraph:
    builder = StateGraph(SealAIState)
    logger.debug("create_sealai_graph_v2_start")
    node_router_dispatch = _node_router_dispatch_async if require_async else _node_router_dispatch
    resume_router = _resume_router_async if require_async else _resume_router
    supervisor_router = _supervisor_policy_router_async if require_async else _supervisor_policy_router
    parameter_router = _parameter_check_router_async if require_async else _parameter_check_router
    critical_router = _critical_review_router_async if require_async else _critical_review_router
    deterministic_termination_router = (
        _deterministic_termination_router_async if require_async else _deterministic_termination_router
    )
    product_router = _product_router_async if require_async else _product_router
    merge_deterministic_router = _merge_deterministic_router_async if require_async else _merge_deterministic_router
    reducer_router = _reducer_router_async if require_async else _reducer_router
    qgate_router = _qgate_router_async if require_async else _qgate_router
    number_verification_router = _number_verification_router_async if require_async else _number_verification_router
    rfq_validator_router = _rfq_validator_router_async if require_async else _rfq_validator_router
    troubleshooting_wizard_router = (
        _troubleshooting_wizard_router_async if require_async else _troubleshooting_wizard_router
    )

    # Node registration
    builder.add_node("profile_loader_node", profile_loader_node) # Long-term Memory
    builder.add_node("safety_synonym_guard_node", safety_synonym_guard_node)  # deterministic pre-router guard
    builder.add_node("combinatorial_chemistry_guard_node", combinatorial_chemistry_guard_node)  # deterministic profile guard
    builder.add_node("node_router", node_router)          # v4.4.0 Sprint 3: Router Node
    builder.add_node("node_p1_context", node_p1_context)  # v4.4.0 Sprint 4: P1 Context Node
    builder.add_node("node_p2_rag_lookup", node_p2_rag_lookup)    # v4.4.0 Sprint 5: P2 RAG Material-Lookup
    builder.add_node("node_p3_gap_detection", node_p3_gap_detection)  # v4.4.0 Sprint 5: P3 Gap-Detection
    builder.add_node("node_p3_5_merge", node_p3_5_merge)          # v4.4.0 Sprint 5: P3.5 Merge
    builder.add_node("node_p4a_extract", node_p4a_extract)       # v4.4.0 Sprint 6: P4a Parameter-Extraction
    builder.add_node("node_p4b_calc_render", node_p4b_calc_render)  # v4.4.0 Sprint 6: P4b MCP Calc + Render
    builder.add_node("node_p4_live_calc", node_p4_live_calc)    # v5.0 foundation: deterministic live tile
    builder.add_node("node_p4_5_qgate", node_p4_5_qgate)          # v4.4.0 Sprint 7: P4.5 Quality Gate
    builder.add_node("p4_6_number_verification", node_p4_6_number_verification)
    builder.add_node("request_clarification_node", request_clarification_node)
    builder.add_node("rfq_validator_node", rfq_validator_node)
    builder.add_node("node_p5_procurement", node_p5_procurement)   # v4.4.0 Sprint 8: P5 Procurement Engine
    builder.add_node("node_p6_generate_pdf", node_p6_generate_pdf)  # v5.0: RFQ HTML/PDF generation
    builder.add_node("resume_router_node", resume_router_node)
    builder.add_node("frontdoor_discovery_node", frontdoor_discovery_node)
    builder.add_node("route_after_frontdoor", route_after_frontdoor_node)
    builder.add_node("frontdoor_parallel_fanout_node", _frontdoor_parallel_fanout_node)
    builder.add_node("node_factcard_lookup_parallel", _node_factcard_lookup_parallel)    # KB Integration
    builder.add_node("node_compound_filter_parallel", _node_compound_filter_parallel)    # KB Integration
    builder.add_node("node_merge_deterministic", node_merge_deterministic)
    builder.add_node("smalltalk_node", smalltalk_node)
    builder.add_node("turn_limit_node", turn_limit_node)
    builder.add_node("supervisor_policy_node", orchestrator_node)
    builder.add_node("supervisor_logic_node", supervisor_policy_node)
    builder.add_node("aggregator_node", aggregator_node)
    builder.add_node("reducer_node", reducer_node)
    builder.add_node("human_review_node", human_review_node)
    builder.add_node("hitl_triage_node", hitl_triage_node)
    builder.add_node("worm_evidence_node", worm_evidence_node)
    builder.add_node(CONVERSATIONAL_RAG_NODE_KEY, conversational_rag_node)
    builder.add_node("troubleshooting_wizard_node", troubleshooting_wizard_node)
    
    builder.add_node("panel_calculator_node", panel_calculator_node)
    builder.add_node("panel_material_node", panel_material_node)
    builder.add_node("calculator_agent", calculator_agent_node)
    builder.add_node("pricing_agent", pricing_agent_node)
    builder.add_node("safety_agent", safety_agent_node)
    builder.add_node("discovery_schema_node", discovery_schema_node)
    builder.add_node("reasoning_core_node", reasoning_core_node)
    builder.add_node("parameter_check_node", parameter_check_node)
    builder.add_node("calculator_node", calculator_node)
    builder.add_node("material_agent_node", material_agent_node)
    builder.add_node("material_agent", material_agent_node)
    builder.add_node("profile_agent_node", profile_agent_node)
    builder.add_node("validation_agent_node", validation_agent_node)
    builder.add_node("critical_review_node", critical_review_node)
    builder.add_node("product_match_node", product_match_node)
    builder.add_node("product_explainer_node", product_explainer_node)
    builder.add_node("material_comparison_node", material_comparison_node)
    builder.add_node("rag_support_node", rag_support_node)
    builder.add_node("leakage_troubleshooting_node", leakage_troubleshooting_node)
    builder.add_node("troubleshooting_pattern_node", troubleshooting_pattern_node)
    builder.add_node("troubleshooting_explainer_node", troubleshooting_explainer_node)
    builder.add_node("confirm_checkpoint_node", confirm_checkpoint_node)
    builder.add_node("confirm_resume_node", confirm_resume_node)
    builder.add_node("confirm_reject_node", confirm_reject_node)
    builder.add_node("confirm_recommendation_node", confirm_recommendation_node)
    builder.add_node(
        "final_answer_node",
        answer_subgraph_node_async if require_async else answer_subgraph_node,
    )
    builder.add_node(
        "contract_first_output_node",
        answer_subgraph_node_async if require_async else answer_subgraph_node,
    )
    builder.add_node("response_node", response_node)

    # Entrypoint: START -> profile_loader -> safety_synonym_guard -> combinatorial_chemistry_guard -> node_router
    builder.add_edge(START, "profile_loader_node")
    builder.add_edge("profile_loader_node", "safety_synonym_guard_node")
    builder.add_edge("combinatorial_chemistry_guard_node", "node_router")

    # v4.4.0 Router dispatch (Sprint 3/4)
    builder.add_conditional_edges(
        "node_router",
        node_router_dispatch,
        {
            "frontdoor":           "frontdoor_discovery_node",
            "resume_router":       "resume_router_node",
            "clarification":       "smalltalk_node",
            "rfq_trigger":         "rfq_validator_node",
            "turn_limit_exceeded": "turn_limit_node",
        },
    )
    # Sprint 5: P1 fans out to P2/P3 via Command/Send (no direct edge needed).
    # P2/P3 workers → P3.5 merge → existing flow
    builder.add_edge("node_p2_rag_lookup", "node_p3_5_merge")
    builder.add_edge("node_p3_gap_detection", "node_p3_5_merge")
    builder.add_edge("node_p3_5_merge", "node_p4a_extract")       # Sprint 6: P3.5 → P4a
    builder.add_edge("node_p4a_extract", "node_p4b_calc_render")  # Sprint 6: P4a → P4b
    builder.add_edge("node_p4b_calc_render", "node_p4_live_calc") # v5.0 foundation: P4b -> live tile
    builder.add_edge("node_p4_live_calc", "node_p4_5_qgate")      # keep existing Q-Gate behavior
    builder.add_conditional_edges(                                    # Sprint 7: Q-Gate routing
        "node_p4_5_qgate",
        qgate_router,
        {
            "no_blockers": "p4_6_number_verification",
            "has_blockers": CONVERSATIONAL_RAG_NODE_KEY,
        },
    )
    builder.add_conditional_edges(
        "p4_6_number_verification",
        number_verification_router,
        {
            "pass": "final_answer_node",
            "fail": "request_clarification_node",
            "fallback_rag": "conversational_rag_node",
        }
    )
    builder.add_edge("request_clarification_node", END)
    builder.add_conditional_edges(
        "rfq_validator_node",
        rfq_validator_router,
        {
            "ready": "node_p5_procurement",
            "missing": END,
        },
    )
    builder.add_edge("node_p5_procurement", "node_p6_generate_pdf")   # v5.0: P5 -> P6
    builder.add_edge("node_p6_generate_pdf", "response_node")         # v5.0: P6 -> response

    builder.add_conditional_edges(
        "resume_router_node",
        resume_router,
        {
            "reject": "confirm_reject_node",
            "resume": "confirm_resume_node",
            "frontdoor": "frontdoor_discovery_node",
            "default": "response_node",
        },
    )
    builder.add_edge("frontdoor_discovery_node", "route_after_frontdoor")
    builder.add_edge("frontdoor_parallel_fanout_node", "node_factcard_lookup_parallel")
    builder.add_edge("frontdoor_parallel_fanout_node", "node_compound_filter_parallel")
    builder.add_edge("node_factcard_lookup_parallel", "node_merge_deterministic")
    builder.add_edge("node_compound_filter_parallel", "node_merge_deterministic")
    builder.add_conditional_edges(
        "node_merge_deterministic",
        merge_deterministic_router,
        {
            "deterministic": "response_node",
            "supervisor": "supervisor_policy_node",
        },
    )
    builder.add_edge("smalltalk_node", "response_node")

    # Map-Reduce Flow
    # Workers route to Reducer
    builder.add_edge("panel_calculator_node", "reducer_node")
    builder.add_edge("panel_material_node", "reducer_node")
    builder.add_edge("material_agent", "reducer_node")
    builder.add_edge("calculator_agent", "reducer_node")
    builder.add_edge("pricing_agent", "reducer_node")
    builder.add_edge("safety_agent", "reducer_node")
    # Reducer routes either through HITL gate or to normal finalization.
    builder.add_conditional_edges(
        "reducer_node",
        reducer_router,
        {
            "human_review": "human_review_node",
            "conversational_rag": "conversational_rag_node",
            "standard": "final_answer_node",
        },
    )
    builder.add_edge("human_review_node", "worm_evidence_node")

    # Back-links
    builder.add_edge("rag_support_node", "supervisor_policy_node")
    builder.add_edge("material_comparison_node", "supervisor_policy_node")
    builder.add_edge("confirm_resume_node", "supervisor_policy_node")

    # Design flow
    builder.add_edge("discovery_schema_node", "parameter_check_node")
    builder.add_conditional_edges(
        "parameter_check_node",
        parameter_router,
        {
            "calculator_node": "calculator_node",
            "conversational_rag_node": "conversational_rag_node",
            "supervisor_policy_node": "supervisor_policy_node",
            "__else__": "supervisor_policy_node",
        },
    )
    builder.add_edge("calculator_node", "material_agent_node")
    builder.add_edge("material_agent_node", "profile_agent_node")
    builder.add_edge("profile_agent_node", "validation_agent_node")
    builder.add_edge("validation_agent_node", "critical_review_node")

    # R3 recursive reasoning loop: parameter extraction -> chemistry guard -> reasoning core -> deterministic router
    builder.add_conditional_edges(
        "reasoning_core_node",
        deterministic_termination_router,
        {
            "contract_first_output_node": "contract_first_output_node",
            "reasoning_core_node": "reasoning_core_node",
            "human_review_node": "human_review_node",
            "request_clarification_node": "request_clarification_node",
            "needs_data": END,
            "__else__": END,
        },
    )

    builder.add_conditional_edges(
        "critical_review_node",
        deterministic_termination_router,
        {
            "contract_first_output_node": "contract_first_output_node",
            "reasoning_core_node": "reasoning_core_node",
            "human_review_node": "human_review_node",
            "request_clarification_node": "request_clarification_node",
            "needs_data": END,
            "__else__": "reasoning_core_node",
        },
    )

    builder.add_conditional_edges(
        "product_match_node",
        product_router,
        {
            "include": "product_explainer_node",
            "skip": "final_answer_node",
            "__else__": "final_answer_node",
        },
    )

    builder.add_edge("product_explainer_node", "final_answer_node")

    # Troubleshooting flow
    builder.add_conditional_edges(
        "troubleshooting_wizard_node",
        troubleshooting_wizard_router,
        {
            "incomplete": END,
            "complete": "conversational_rag_node",
        },
    )

    builder.add_edge("confirm_recommendation_node", "hitl_triage_node")
    builder.add_edge("confirm_checkpoint_node", "hitl_triage_node")
    builder.add_edge("confirm_reject_node", "hitl_triage_node")

    builder.add_edge(CONVERSATIONAL_RAG_NODE_KEY, "hitl_triage_node")
    builder.add_edge("contract_first_output_node", "hitl_triage_node")
    builder.add_edge("final_answer_node", "hitl_triage_node")
    builder.add_edge("response_node", "hitl_triage_node")
    builder.add_edge("hitl_triage_node", "worm_evidence_node")
    builder.add_edge("worm_evidence_node", END)

    compiled = builder.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=["human_review_node"],
        name=LANGSMITH_RUN_NAME,
    )
    return compiled.with_config(
        {
            "run_name": LANGSMITH_RUN_NAME,
            "tags": list(LANGSMITH_TRACE_TAGS),
            "metadata": {
                "observability_phase": "phase_0",
                "audit_schema": "evidence_bundle_v1",
            },
        }
    )


# ---------------------------------------------------------------------------
# Graph Cache & Config
# ---------------------------------------------------------------------------

_GRAPH_CACHE: CompiledStateGraph | None = None
_GRAPH_LOCK = asyncio.Lock()


async def _build_graph(require_async: bool = True) -> CompiledStateGraph:
    # Initialize Checkpointer & Store (Async)
    checkpointer = await make_v2_checkpointer_async(require_async=require_async)
    store = await get_postgres_store()
    return create_sealai_graph_v2(checkpointer=checkpointer, store=store, require_async=require_async)


async def get_sealai_graph_v2() -> CompiledStateGraph:
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        async with _GRAPH_LOCK:
            if _GRAPH_CACHE is None:
                _GRAPH_CACHE = await _build_graph(require_async=True)
    return _GRAPH_CACHE


def build_v2_config(*, thread_id: str, user_id: str) -> Dict[str, Any]:
    """
    Common LangGraph config for v2 (includes run_id for observability).

    + recursion_limit explizit hochsetzen, damit komplexe Flows nicht bereits
      bei 25 Schritten abgebrochen werden.
    + Die harte Begrenzung erfolgt weiterhin über den 45s-Timeout im SSE-Endpoint.
    """
    run_id = str(uuid.uuid4())
    # Checkpointer identity must be stable per (user_id, thread_id) so that state
    # can be recovered reliably and isolated across users.
    checkpoint_thread_id = stable_thread_key(user_id, thread_id)
    configurable: Dict[str, Any] = {
        "thread_id": checkpoint_thread_id,
    }
    metadata: Dict[str, Any] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "run_id": run_id,
    }
    return {
        "configurable": configurable,
        "metadata": metadata,
        "tags": list(LANGSMITH_TRACE_TAGS),
        "run_name": LANGSMITH_RUN_NAME,
        "recursion_limit": 80,
    }
