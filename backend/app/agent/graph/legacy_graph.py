"""
Residual Legacy Agent Graph — compat-only, non-productive for structured runtime.

Structured productive authority lives in `app.agent.graph.topology.GOVERNED_GRAPH`.
This module remains only for residual compat/helper seams and review-related
legacy integration. Do not wire it back into the authenticated standard chat
runtime for structured turns.

Agent Graph — Phase 0D+: Five-Path Runtime Architecture

Topology:

    START
      │
      ▼ route_by_policy (conditional edge — reads state["policy_path"])
      │
      ├─── "meta_response_node" ──────────────────────────────────────────► END
      │       (META_PATH: deterministic state-status reply, no LLM)
      │
      ├─── "blocked_node" ─────────────────────────────────────────────────► END
      │       (BLOCKED_PATH: deterministic safe refusal, no LLM)
      │
      ├─── "greeting_node" ───────────────────────────────────────────────► END
      │       (GREETING_PATH: deterministic greeting, no LLM, no RAG)
      │
      ├─── "fast_guidance_node" ───────────────────────────────────────────► END
      │       (FAST_PATH: DIRECT_ANSWER, LLM + output guard, conditional RAG)
      │
      └─── "reasoning_node"  ──► [tool_router]
               (STRUCTURED_PATH)       │
                                       ├─── "evidence_tool_node" ──► "reasoning_node"
                                       └─── "selection_node" ──► "final_response_node" ──► END

Rules:
- meta_response_node:  no LLM, reads ONLY asserted_state, never working_profile
- blocked_node:        no LLM, no pipeline, deterministic safe refusal
- greeting_node:       no LLM, no RAG, deterministic greeting response
- fast_guidance_node:  LLM + output_guard, conditional RAG, no sealing_state writes
- reasoning_node:      full structured path with tool loop, sealing_state writes, governance

state["policy_path"] is injected by the API router before graph invocation.
Defaults to "reasoning_node" (structured) when policy_path is absent or unknown.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, List, Literal, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agent.domain.logic import evaluate_claim_conflicts, extract_parameters, process_cycle_update
from app.agent.prompts import (
    FAST_GUIDANCE_PROMPT_HASH,
    FAST_GUIDANCE_PROMPT_VERSION,
    REASONING_PROMPT_HASH,
    REASONING_PROMPT_VERSION,
    build_fast_guidance_prompt,
)
from prompts.builder import PromptBuilder as _PromptBuilderCls

_builder = _PromptBuilderCls()
from app.agent.runtime.policy import INTERACTION_POLICY_VERSION
from app.agent.runtime.boundaries import build_boundary_block
from app.agent.runtime.output_guard import FAST_PATH_GUARD_FALLBACK, check_fast_path_output
from app.agent.manufacturers.commercial import (
    build_dispatch_bridge,
    build_dispatch_dry_run,
    build_dispatch_event,
    build_dispatch_handoff,
    build_dispatch_transport_envelope,
    build_dispatch_trigger,
    build_handover_payload,
)
from app.agent.case_state import build_dispatch_intent, ensure_case_state
from app.agent.domain.review import evaluate_review_trigger
from app.agent.domain.critical_review import (
    CriticalReviewGovernanceSummary,
    CriticalReviewMatchingPackage,
    CriticalReviewRecommendationPackage,
    CriticalReviewRfqBasis,
    CriticalReviewSpecialistInput,
    critical_review_result_to_dict,
    run_critical_review_specialist,
)
from app.agent.domain.manufacturer_rfq import (
    build_manufacturer_match_result_from_runtime_state,
)
from app.agent.material_core import REGISTRY_IS_DEMO_ONLY
from app.agent.runtime.selection import build_final_reply, build_selection_state
from app.agent.state.agent_state import AgentState, SealingAIState
from app.agent.graph.tools import submit_claim, calculate_rwdr_specifications
from app.agent.evidence.models import Claim, ClaimType

load_dotenv()

logger = logging.getLogger(__name__)

_GRAPH_MODEL_ID = "gpt-4o-mini"

# Phase 0D+: RAG eligibility gate for fast_guidance_node (module-level constant)
_RAG_ELIGIBLE_PATTERN = re.compile(
    r"\b(\d+\s*(?:mm|bar|°?\s*[cCfF]|rpm|u/?min)"
    r"|dicht|seal|RWDR|PTFE|FKM|NBR|EPDM|medium|werkstoff|material"
    r"|temperatur|druck|welle|drehzahl|geschwindigkeit"
    r"|hydraul|pneumat|öl|wasser|dampf|chemik)\b",
    re.IGNORECASE,
)
_VISIBLE_REPLY_SYSTEM_PROMPT = (
    "Du bist SealAI, der sichtbare Kommunikationslayer eines erfahrenen Dichtungsingenieurs.\n"
    "Formuliere die technische Antwort natürlich, klar und auf den Punkt.\n"
    "Beziehe dich IMMER zuerst auf das, was der User gerade gesagt hat — niemals ignorieren.\n"
    "Kein Formularjargon, keine unnötigen Disclaimers."
)
VISIBLE_REPLY_PROMPT_VERSION = "visible_reply_prompt_v2"
VISIBLE_REPLY_PROMPT_HASH = hashlib.sha256(_VISIBLE_REPLY_SYSTEM_PROMPT.encode()).hexdigest()[:12]
_NON_BINDING_ASSIST_INSTRUCTION = (
    "Du darfst nur explizit genannte Beobachtungen als nicht-bindende Rohclaims erfassen. "
    "Keine Release-Entscheidung, keine RFQ-Admissibility, keine Governance-Wertung, "
    "keine Compound- oder Materialfreigabe ableiten."
)

# ---------------------------------------------------------------------------
# Prompt-Formatierungshelfer — working_profile → _base_thomas.j2-Format
# ---------------------------------------------------------------------------
# _base_thomas.j2 erwartet: {"key": {"value": "...", "unit": "..."}}
# extract_parameters() speichert flache Skalare: {"key": scalar}
# Nur kanonische Anzeigeschlüssel werden übergeben — interne Aliase
# (temperature, pressure, ...) und berechnete Werte (live_calc_tile, ...) bleiben aus.
_PROMPT_PARAM_DISPLAY: tuple[tuple[str, str], ...] = (
    ("medium",            ""),
    ("temperature_max_c", "°C"),
    ("pressure_bar",      "bar"),
    ("shaft_diameter_mm", "mm"),
    ("speed_rpm",         "rpm"),
    ("material",          ""),
)


def _format_profile_for_prompt(profile: dict[str, Any]) -> dict[str, Any]:
    """Flat working_profile → {value, unit}-Dict für _base_thomas.j2."""
    result: dict[str, Any] = {}
    for key, unit in _PROMPT_PARAM_DISPLAY:
        val = profile.get(key)
        if val is not None and str(val).strip():
            result[key] = {"value": str(val), "unit": unit}
    return result

def _derive_case_context(state: AgentState) -> tuple[str, str, str]:
    existing_case_state = dict(state.get("case_state") or {})
    case_meta = dict(existing_case_state.get("case_meta") or {})
    result_contract = dict(existing_case_state.get("result_contract") or {})
    session_id = str(
        state.get("inquiry_id")
        or state.get("session_id")
        or case_meta.get("case_id")
        or case_meta.get("session_id")
        or ((state.get("sealing_state") or {}).get("cycle") or {}).get("analysis_cycle_id")
        or "unknown"
    )
    runtime_path = str(case_meta.get("runtime_path") or "STRUCTURED_QUALIFICATION")
    binding_level = str(
        case_meta.get("binding_level")
        or result_contract.get("binding_level")
        or "ORIENTATION"
    )
    return session_id, runtime_path, binding_level


def _canonicalize_runtime_case_state(
    state: AgentState,
    *,
    sealing_state: dict[str, Any],
    case_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provisional_state = dict(state)
    provisional_state["sealing_state"] = sealing_state
    if case_state is not None:
        provisional_state["case_state"] = case_state
    session_id, runtime_path, binding_level = _derive_case_context(provisional_state)
    canonical_state = ensure_case_state(
        provisional_state,
        session_id=session_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )
    return dict(canonical_state.get("case_state") or {})


def _merge_dispatch_lifecycle_slice(
    *,
    case_surface: dict[str, Any] | None,
    sealing_surface: dict[str, Any] | None,
    lifecycle_keys: tuple[str, ...],
) -> dict[str, Any]:
    merged = dict(sealing_surface or {})
    case_surface = dict(case_surface or {})
    for key in lifecycle_keys:
        if case_surface.get(key) is not None:
            merged[key] = case_surface.get(key)
    return merged


def _merge_dispatch_basis_slice(
    *,
    case_surface: dict[str, Any] | None,
    sealing_surface: dict[str, Any] | None,
    basis_keys: tuple[str, ...],
) -> dict[str, Any]:
    merged = dict(sealing_surface or {})
    case_surface = dict(case_surface or {})
    for key in basis_keys:
        value = case_surface.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            merged[key] = dict(value)
        elif isinstance(value, list):
            merged[key] = list(value)
        else:
            merged[key] = value
    return merged


def _without_dispatch_surface(
    case_state: dict[str, Any] | None,
    *surface_keys: str,
) -> dict[str, Any]:
    state = dict(case_state or {})
    for key in surface_keys:
        state.pop(key, None)
    return state


def _align_runtime_cycle_token_case_meta_first(
    state: AgentState,
    *,
    sealing_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated_case_state = dict(state.get("case_state") or {})
    case_meta = dict(updated_case_state.get("case_meta") or {})
    updated_sealing_state = dict(sealing_state or {})
    cycle = dict(updated_sealing_state.get("cycle") or {})

    if cycle.get("state_revision") is not None:
        case_meta["state_revision"] = int(cycle.get("state_revision", 0) or 0)
        case_meta["version"] = int(cycle.get("state_revision", 0) or 0)
    if cycle.get("snapshot_parent_revision") is not None:
        case_meta["snapshot_parent_revision"] = cycle.get("snapshot_parent_revision")
    if cycle.get("analysis_cycle_id") is not None:
        case_meta["analysis_cycle_id"] = cycle.get("analysis_cycle_id")

    if case_meta:
        updated_case_state["case_meta"] = case_meta

    if case_meta.get("state_revision") is not None:
        cycle["state_revision"] = case_meta.get("state_revision")
    if case_meta.get("snapshot_parent_revision") is not None:
        cycle["snapshot_parent_revision"] = case_meta.get("snapshot_parent_revision")
    if case_meta.get("analysis_cycle_id") is not None:
        cycle["analysis_cycle_id"] = case_meta.get("analysis_cycle_id")
    updated_sealing_state["cycle"] = cycle

    return updated_case_state, updated_sealing_state

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    class ChatOpenAI:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def bind_tools(self, tools: list[Any]) -> "ChatOpenAI":
            return self

        async def ainvoke(self, messages: list[Any]) -> AIMessage:
            return AIMessage(content="stub")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def retrieve_rag_context(query: str, tenant_id: str | None) -> list[Any]:
    """Phase 0A.1: tenant_id is preserved and forwarded to the real Qdrant retrieval."""
    from app.agent.services.real_rag import retrieve_with_tenant
    return await retrieve_with_tenant(query, tenant_id)


def get_llm(config: Optional[RunnableConfig] = None) -> ChatOpenAI:
    return ChatOpenAI(model=_GRAPH_MODEL_ID, temperature=0)


def _last_human_query(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


async def _fetch_rag_cards(query: str, tenant_id: str | None) -> tuple[list[Any], str]:
    """Fetch tenant-safe RAG cards. Returns (cards_data, path_used)."""
    path_used = "real_rag"
    try:
        relevant_cards = await retrieve_rag_context(query, tenant_id)
    except Exception as exc:
        logger.error("[RAG] Real-RAG error, returning empty tenant-safe evidence set: %s", exc, exc_info=True)
        relevant_cards = []
        path_used = "real_rag_error_empty"

    if not relevant_cards:
        path_used = "real_rag_empty" if path_used == "real_rag" else path_used

    logger.info("[RAG] Path: %s, Hits: %d, Tenant: %s", path_used, len(relevant_cards), tenant_id)

    cards_data: list[Any] = []
    for c in relevant_cards:
        if isinstance(c, dict):
            cards_data.append(c)

    cards_data = sorted(
        cards_data,
        key=lambda card: (
            str(card.get("evidence_id") or card.get("id") or ""),
            str(card.get("topic") or ""),
        ),
    )
    return cards_data, path_used


_CONTEXT_MAX_CHARS_PER_CARD = 1500
_CONTEXT_MAX_CARDS = 8


def _format_context(cards_data: list[Any]) -> str:
    """Format RAG cards into a context string with per-card truncation."""
    truncated = cards_data[:_CONTEXT_MAX_CARDS]
    parts: list[str] = []
    for c in truncated:
        content = str(c.get("content", ""))
        if len(content) > _CONTEXT_MAX_CHARS_PER_CARD:
            content = content[:_CONTEXT_MAX_CHARS_PER_CARD] + " [...]"
        parts.append(f"Topic: {c.get('topic', '')}\nContent: {content}")
    ctx = "\n---\n".join(parts)
    return ctx or "Keine relevanten Informationen in der Wissensdatenbank gefunden."


def _extract_profile_derived_engineering_values(working_profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = working_profile or {}
    derived: dict[str, Any] = {}
    for key in ("v_surface_m_s", "pv_value_mpa_m_s", "pv_value", "v_m_s"):
        value = profile.get(key)
        if value is not None:
            derived[key] = value
    live_calc_tile = profile.get("live_calc_tile")
    if isinstance(live_calc_tile, dict) and live_calc_tile:
        derived["live_calc_tile"] = dict(live_calc_tile)
    return derived


def _extract_observed_tool_derived_values(sealing_state: dict[str, Any] | None) -> dict[str, Any]:
    observed_layer = dict((sealing_state or {}).get("observed") or {})
    raw_parameters = dict(observed_layer.get("raw_parameters") or {})
    derived: dict[str, Any] = {}
    rwdr_tool_runs = raw_parameters.get("rwdr_tool_runs")
    if isinstance(rwdr_tool_runs, list) and rwdr_tool_runs:
        derived["rwdr_tool_runs"] = [dict(run) for run in rwdr_tool_runs if isinstance(run, dict)]
    return derived


def _record_observed_tool_runs(
    sealing_state: dict[str, Any],
    *,
    rwdr_tool_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    updated_sealing_state = dict(sealing_state or {})
    observed_layer = dict(updated_sealing_state.get("observed") or {})
    raw_parameters = dict(observed_layer.get("raw_parameters") or {})
    existing_runs = list(raw_parameters.get("rwdr_tool_runs") or [])
    raw_parameters["rwdr_tool_runs"] = existing_runs + [dict(run) for run in rwdr_tool_runs]
    observed_inputs = list(observed_layer.get("observed_inputs") or [])
    for run in rwdr_tool_runs:
        observed_inputs.append(
            {
                "source": "tool_rwdr_calculation",
                "raw_text": json.dumps(dict(run.get("inputs") or {}), ensure_ascii=False, sort_keys=True),
                "claim_type": "tool_observation",
                "certainty": "deterministic_tool_result",
                "confirmed": False,
                "source_fact_ids": [],
            }
        )
    observed_layer["raw_parameters"] = raw_parameters
    observed_layer["observed_inputs"] = observed_inputs
    updated_sealing_state["observed"] = observed_layer
    return updated_sealing_state


def _sync_case_state_runtime_buckets(
    state: AgentState,
    *,
    sealing_state: dict[str, Any] | None = None,
    working_profile: dict[str, Any] | None = None,
    derived_engineering_values: dict[str, Any] | None = None,
    run_meta: dict[str, Any] | None = None,
    relevant_fact_cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    existing_case_state = dict(state.get("case_state") or {})
    current_sealing_state = sealing_state or dict(state.get("sealing_state") or {})
    cycle = dict(current_sealing_state.get("cycle") or {})
    normalized_layer = dict(current_sealing_state.get("normalized") or {})
    governance_layer = dict(current_sealing_state.get("governance") or {})
    review_layer = dict(current_sealing_state.get("review") or {})
    cards = list(relevant_fact_cards if relevant_fact_cards is not None else (state.get("relevant_fact_cards") or []))
    current_run_meta = dict(run_meta if run_meta is not None else (state.get("run_meta") or {}))

    case_state = dict(existing_case_state)
    case_meta = dict(existing_case_state.get("case_meta") or {})
    if cycle.get("state_revision") is not None:
        case_meta["state_revision"] = int(cycle.get("state_revision", 0) or 0)
        case_meta["version"] = int(cycle.get("state_revision", 0) or 0)
    if cycle.get("snapshot_parent_revision") is not None:
        case_meta["snapshot_parent_revision"] = cycle.get("snapshot_parent_revision")
    if cycle.get("analysis_cycle_id") is not None:
        case_meta["analysis_cycle_id"] = cycle.get("analysis_cycle_id")
    if case_meta:
        case_state["case_meta"] = case_meta

    case_state["normalized_parameters"] = dict(
        normalized_layer.get("normalized_parameters")
        or existing_case_state.get("normalized_parameters")
        or {}
    )
    case_state["parameter_meta"] = dict(
        normalized_layer.get("identity_records")
        or existing_case_state.get("parameter_meta")
        or {}
    )

    governance_state = dict(existing_case_state.get("governance_state") or {})
    governance_state.update(
        {
            "release_status": governance_layer.get("release_status", governance_state.get("release_status", "inadmissible")),
            "rfq_admissibility": governance_layer.get("rfq_admissibility", governance_state.get("rfq_admissibility", "inadmissible")),
            "specificity_level": governance_layer.get("specificity_level", governance_state.get("specificity_level", "family_only")),
            "scope_of_validity": list(governance_layer.get("scope_of_validity") or governance_state.get("scope_of_validity") or []),
            "unknowns_release_blocking": list(governance_layer.get("unknowns_release_blocking") or governance_state.get("unknowns_release_blocking") or []),
            "unknowns_manufacturer_validation": list(governance_layer.get("unknowns_manufacturer_validation") or governance_state.get("unknowns_manufacturer_validation") or []),
            "conflicts": list(governance_layer.get("conflicts") or governance_state.get("conflicts") or []),
            "review_required": bool(review_layer.get("review_required", governance_state.get("review_required", False))),
            "review_state": review_layer.get("review_state") or governance_state.get("review_state"),
        }
    )
    case_state["governance_state"] = governance_state

    evidence_refs = [
        str(card.get("evidence_id") or card.get("id") or "")
        for card in cards
        if card.get("evidence_id") or card.get("id")
    ]
    evidence_state = dict(existing_case_state.get("evidence_state") or {})
    evidence_state.update(
        {
            "evidence_available": bool(current_run_meta.get("evidence_available", bool(cards))),
            "evidence_ref_count": len(evidence_refs),
            "evidence_refs": evidence_refs,
            "retrieval_refs": evidence_refs,
        }
    )
    if current_run_meta.get("rag_path"):
        evidence_state["rag_path"] = current_run_meta["rag_path"]
    case_state["evidence_state"] = evidence_state

    merged_derived = dict(existing_case_state.get("derived_engineering_values") or {})
    profile_derived = _extract_profile_derived_engineering_values(working_profile)
    if profile_derived:
        merged_derived.update(profile_derived)
    observed_tool_derived = _extract_observed_tool_derived_values(current_sealing_state)
    if observed_tool_derived:
        merged_derived.update(observed_tool_derived)
    if derived_engineering_values:
        merged_derived.update(derived_engineering_values)
    if merged_derived:
        case_state["derived_engineering_values"] = merged_derived
        legacy_derived = dict(existing_case_state.get("derived_calculations") or {})
        legacy_derived.update(merged_derived)
        case_state["derived_calculations"] = legacy_derived

    return case_state


# ---------------------------------------------------------------------------
# Entry router — Phase 0A.3
# ---------------------------------------------------------------------------

def route_by_policy(
    state: AgentState,
) -> Literal["fast_guidance_node", "reasoning_node", "meta_response_node", "blocked_node", "greeting_node"]:
    """
    Conditional entry edge: dispatches to fast / structured / meta / blocked / greeting path.

    Reads state["policy_path"] injected by the API router before graph invocation.
    Defaults to "reasoning_node" (structured) when policy_path is absent or unknown.

    Path priorities (Phase 0D+):
      "meta"     → meta_response_node (deterministic state-status reply)
      "blocked"  → blocked_node (deterministic safe refusal)
      "greeting" → greeting_node (deterministic greeting, no LLM, no RAG)
      "fast"     → fast_guidance_node (lightweight LLM guidance)
      any other  → reasoning_node (full structured pipeline)
    """
    policy_path = state.get("policy_path") or "structured"
    if policy_path == "meta":
        return "meta_response_node"
    if policy_path == "blocked":
        return "blocked_node"
    if policy_path == "greeting":
        return "greeting_node"
    if policy_path == "fast":
        return "fast_guidance_node"
    return "reasoning_node"


# ---------------------------------------------------------------------------
# Fast-path node — DIRECT_ANSWER only (Phase 0D: GUIDED_RECOMMENDATION removed)
# ---------------------------------------------------------------------------

async def fast_guidance_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Lightweight guidance node for FAST_PATH interactions.

    Differences from reasoning_node (all intentional):
    - No submit_claim tool — LLM cannot mutate sealing_state
    - No extract_parameters — no heuristic working_profile updates
    - No sealing_state writes — governance layer stays untouched
    - Adapted system prompt based on result_form
    - Direct → END (no selection_node, no final_response_node)
    """
    query = _last_human_query(state)
    tenant_id = state.get("tenant_id")
    result_form = state.get("result_form") or "direct_answer"

    # Phase 0D+: skip RAG for non-technical fast-path queries
    rag_eligible = bool(query and _RAG_ELIGIBLE_PATTERN.search(query))

    if rag_eligible:
        cards_data, _ = await _fetch_rag_cards(query, tenant_id)
    else:
        cards_data = []
        logger.debug("[fast_guidance_node] RAG skipped — non-technical query")
    context_str = _format_context(cards_data)

    # Build current_params summary from working_profile so the "DO NOT ASK AGAIN"
    # rule in the prompt template has actual data to enforce.
    _working_profile: dict[str, Any] = dict(state.get("working_profile") or {})
    _param_lines: list[str] = []
    _PARAM_LABELS_FAST: dict[str, tuple[str, str]] = {
        "medium":            ("Medium",        ""),
        "temperature_max_c": ("Temperatur",     "°C"),
        "pressure_bar":      ("Druck",          "bar"),
        "shaft_diameter_mm": ("Wellen-Ø",       "mm"),
        "speed_rpm":         ("Drehzahl",       "rpm"),
        "motion_type":       ("Bewegungsart",   ""),
        "material":          ("Material",       ""),
    }
    for _k, (_label, _unit) in _PARAM_LABELS_FAST.items():
        _v = _working_profile.get(_k)
        if _v is not None and str(_v).strip():
            _param_lines.append(f"  • {_label}: {_v}{(' ' + _unit) if _unit else ''} ✓")
    current_params_str = (
        "\n".join(_param_lines) if _param_lines else "Noch keine Parameter erfasst."
    )

    # Build a compact history summary from the message list for the prompt.
    _FAST_PATH_MSG_WINDOW = 20
    all_messages = list(state.get("messages", []))
    _history_window = all_messages[-_FAST_PATH_MSG_WINDOW:]
    _history_lines: list[str] = []
    for _m in _history_window:
        _role = getattr(_m, "type", None) or getattr(_m, "role", "")
        _content = str(getattr(_m, "content", "") or "").strip()
        if not _content:
            continue
        if _role in {"human", "user"}:
            _history_lines.append(f"User: {_content[:200]}")
        elif _role in {"ai", "assistant"}:
            _history_lines.append(f"SealAI: {_content[:200]}")
    history_str = "\n".join(_history_lines[-12:]) if _history_lines else ""

    system_prompt = build_fast_guidance_prompt(
        context_str,
        result_form,
        history=history_str,
        current_params=current_params_str,
    )
    system_msg = SystemMessage(content=system_prompt)

    llm = get_llm(config)
    # No tools bound — LLM answers in plain text only.
    # Use full window (already sliced above for the prompt summary).
    recent_messages = all_messages[-_FAST_PATH_MSG_WINDOW:]
    response = await llm.ainvoke([system_msg] + recent_messages)

    # Phase 0C.1: output guard — block policy violations before boundary append
    safe, _violation = check_fast_path_output(response.content)
    final_text = response.content.rstrip() if safe else FAST_PATH_GUARD_FALLBACK

    # Phase 0B.2: deterministically append boundary disclaimer (never LLM-generated)
    boundary = build_boundary_block("fast")
    bounded_content = f"{final_text}\n\n{boundary}"
    bounded_response = AIMessage(content=bounded_content)

    return {
        "messages": [bounded_response],
        "relevant_fact_cards": cards_data,
        "run_meta": {
            "model_id": _GRAPH_MODEL_ID,
            "prompt_version": FAST_GUIDANCE_PROMPT_VERSION,
            "prompt_hash": FAST_GUIDANCE_PROMPT_HASH,
            "policy_version": INTERACTION_POLICY_VERSION,
            "path": "fast",
        },
        # working_profile and sealing_state intentionally NOT modified
    }


# ---------------------------------------------------------------------------
# Meta-path node — Phase 0D.3
# ---------------------------------------------------------------------------

def meta_response_node(state: AgentState) -> dict:
    """Deterministic meta-response: reads ONLY asserted state.

    Answers state-status questions ("Was fehlt?", "Wie ist der Stand?")
    without any LLM call. working_profile is intentionally NOT read here
    to avoid presenting pending heuristic values as confirmed facts.
    """
    sealing_state = state.get("sealing_state") or {}
    asserted = sealing_state.get("asserted") or {}
    oc = asserted.get("operating_conditions") or {}
    machine = asserted.get("machine_profile") or {}
    medium_name = (asserted.get("medium_profile") or {}).get("name")

    confirmed: list[str] = []
    missing_labels: list[str] = []

    if medium_name:
        confirmed.append(f"Medium: {medium_name}")
    else:
        missing_labels.append("Medium (z. B. Wasser, Öl, Kraftstoff)")

    pressure = oc.get("pressure")
    if pressure is not None:
        confirmed.append(f"Betriebsdruck: {pressure} bar")
    else:
        missing_labels.append("Betriebsdruck (bar)")

    temperature = oc.get("temperature")
    if temperature is not None:
        confirmed.append(f"Betriebstemperatur: {temperature} °C")
    else:
        missing_labels.append("Betriebstemperatur (°C)")

    diameter = machine.get("shaft_diameter")
    if diameter is not None:
        confirmed.append(f"Wellendurchmesser: {diameter} mm")
    else:
        missing_labels.append("Wellendurchmesser (mm)")

    speed = machine.get("speed_rpm")
    if speed is not None:
        confirmed.append(f"Drehzahl: {speed} rpm")
    else:
        missing_labels.append("Drehzahl (rpm)")

    lines: list[str] = []
    if confirmed:
        lines.append("Bestätigte Angaben:\n" + "\n".join(f"• {c}" for c in confirmed))
    else:
        lines.append("Noch keine technischen Angaben bestätigt.")

    if missing_labels:
        lines.append("Noch fehlend:\n" + "\n".join(f"• {m}" for m in missing_labels))

    lines.append(
        "Hinweis: Nur in der Sitzung bestätigte Werte sind hier aufgeführt. "
        "Vorläufig erfasste (nicht bestätigte) Werte werden nicht gezeigt."
    )

    response_text = "\n\n".join(lines)
    boundary = build_boundary_block("fast")
    return {
        "messages": [AIMessage(content=f"{response_text}\n\n{boundary}")],
        # sealing_state and working_profile intentionally NOT modified
    }


# ---------------------------------------------------------------------------
# Blocked-path node — Phase 0D.1
# ---------------------------------------------------------------------------

_BLOCKED_REFUSAL = (
    "Diese Anfrage kann von SealAI nicht beantwortet werden. "
    "SealAI darf weder Hersteller nennen noch Materialien empfehlen "
    "noch Eignungsaussagen treffen — das sind die sieben unverhandelbaren Regeln.\n\n"
    "Was SealAI tun kann: Wenn Sie Ihre Betriebsparameter nennen "
    "(Medium, Druck, Temperatur, Wellendurchmesser, Drehzahl), "
    "führt SealAI eine strukturierte technische Vorbeurteilung durch."
)


def blocked_node(state: AgentState) -> dict:
    """Deterministic policy-block response — no LLM, no pipeline.

    Returned when the input explicitly requests content that SealAI is
    forbidden to provide (manufacturer names, material recommendations,
    fitness assertions). Phase 0D.1.
    """
    boundary = build_boundary_block("fast")
    return {
        "messages": [AIMessage(content=f"{_BLOCKED_REFUSAL}\n\n{boundary}")],
    }


# ---------------------------------------------------------------------------
# Greeting node — deterministic, no LLM, no RAG (Phase 0D+)
# ---------------------------------------------------------------------------

_GREETING_RESPONSE = (
    "Hallo! Ich bin SealAI, Ihr technischer Assistent für Dichtungstechnik. "
    "Nennen Sie mir Ihre Betriebsparameter (Medium, Druck, Temperatur, "
    "Wellendurchmesser, Drehzahl), und ich führe eine technische Vorbeurteilung durch."
)


def greeting_node(state: AgentState) -> dict:
    """Deterministic greeting response — no LLM, no RAG, no pipeline.

    Returns a fixed greeting text. No sealing_state modification,
    no working_profile update, no tool calls.
    """
    return {
        "messages": [AIMessage(content=_GREETING_RESPONSE)],
    }


# ---------------------------------------------------------------------------
# Structured-path nodes — UNCHANGED (Preserve P2)
# ---------------------------------------------------------------------------

async def reasoning_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Reasoning Node (Phase D1 - RAG Injection).
    Full structured path: claim submission, sealing_state updates, governance.
    UNCHANGED from original — Preserve P2.
    """
    messages = state.get("messages", [])
    current_profile = state.get("working_profile", {})
    tenant_id = state.get("tenant_id")

    query = _last_human_query(state)

    cards_data, path_used = await _fetch_rag_cards(query, tenant_id)
    # Phase 0D.4: evidence status is explicit — never silently absent
    evidence_available: bool = bool(cards_data)
    logger.debug(
        "[reasoning_node] RAG path=%s hits=%d tenant=%s evidence_available=%s",
        path_used, len(cards_data), tenant_id, evidence_available,
    )

    new_profile = extract_parameters(query, current_profile, cards_data) if query else current_profile

    _fact_cards = [
        {"title": c.get("topic", ""), "specificity": 3, "content": c.get("content", "")}
        for c in cards_data[:10]
    ]
    system_prompt = _builder.governed(
        _format_profile_for_prompt(new_profile), [], _fact_cards, include_tools=True
    )
    system_prompt = f"{_NON_BINDING_ASSIST_INSTRUCTION}\n\n{system_prompt}"

    llm = get_llm(config)
    llm_with_tools = llm.bind_tools([submit_claim, calculate_rwdr_specifications])

    response = await llm_with_tools.ainvoke([SystemMessage(content=system_prompt)] + list(messages))

    return {
        "messages": [response],
        "relevant_fact_cards": cards_data,
        "working_profile": new_profile,
        "case_state": _sync_case_state_runtime_buckets(
            state,
            working_profile=new_profile,
            derived_engineering_values=_extract_profile_derived_engineering_values(new_profile),
            run_meta={
                **(state.get("run_meta") or {}),
                "evidence_available": evidence_available,
                "rag_path": path_used,
            },
            relevant_fact_cards=cards_data,
        ),
        "run_meta": {
            **(state.get("run_meta") or {}),
            "evidence_available": evidence_available,
            "rag_path": path_used,
        },
    }


def evidence_tool_node(state: AgentState) -> dict:
    """
    Evidence Tool Node (Phase C4/H5) — full dispatcher loop.

    Processes ALL tool_calls in last_message so the OpenAI message contract
    is never broken (every tool_call_id must have a matching ToolMessage).

    Dispatch table:
    - submit_claim                  → observed claim intake + deterministic firewall transition
    - calculate_rwdr_specifications → observed tool intake + deterministic calc result
    - unknown tools                 → safe error ToolMessage (safety net)
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return {}

    # --- Partition tool calls by name ---
    new_claims: List[Claim] = []
    claim_to_tool_id: dict[str, str] = {}
    rwdr_calls: List[dict] = []
    unknown_calls: List[dict] = []

    for tc in tool_calls:
        if tc["name"] == "submit_claim":
            args = tc["args"]
            claim = Claim(
                claim_type=args["claim_type"],
                statement=args["statement"],
                confidence=args["confidence"],
                source_fact_ids=args.get("source_fact_ids", []),
            )
            new_claims.append(claim)
            claim_to_tool_id[claim.statement] = tc["id"]
        elif tc["name"] == "calculate_rwdr_specifications":
            rwdr_calls.append(tc)
        else:
            unknown_calls.append(tc)

    from app.agent.services.compound import validate_claim_against_matrix

    tool_outputs: List[ToolMessage] = []
    result: dict = {}
    working_profile = state.get("working_profile") or {}

    # Accumulate ALL domain conflicts across both dispatch paths so they are
    # written into governance.conflicts via process_cycle_update at the end.
    all_domain_conflicts: List[dict] = []
    rwdr_domain_conflicts: List[dict] = []
    rwdr_tool_runs: List[dict[str, Any]] = []

    # --- submit_claim path: observed claim intake + deterministic transition ---
    if new_claims:
        old_sealing_state = state["sealing_state"]
        current_revision = old_sealing_state["cycle"]["state_revision"]

        intelligence_conflicts, validated_params = evaluate_claim_conflicts(
            claims=new_claims,
            asserted_state=old_sealing_state["asserted"],
            relevant_fact_cards=state.get("relevant_fact_cards", []),
            working_profile=working_profile,
        )
        all_domain_conflicts.extend(intelligence_conflicts)

        raw_claims = [
            {
                "statement": claim.statement,
                "claim_type": claim.claim_type,
                "confidence": claim.confidence,
                "source_fact_ids": claim.source_fact_ids,
                "source": "llm_submit_claim",
            }
            for claim in new_claims
        ]

        new_sealing_state = process_cycle_update(
            old_state=old_sealing_state,
            intelligence_conflicts=intelligence_conflicts,
            expected_revision=current_revision,
            validated_params={},
            raw_claims=raw_claims,
            relevant_fact_cards=state.get("relevant_fact_cards", []),
        )
        aligned_case_state, new_sealing_state = _align_runtime_cycle_token_case_meta_first(
            state,
            sealing_state=new_sealing_state,
        )
        if aligned_case_state:
            result["case_state"] = aligned_case_state
        result["sealing_state"] = new_sealing_state

        conflicts_by_statement: dict[str, list] = {}
        for c in intelligence_conflicts:
            conflicts_by_statement.setdefault(c["claim_statement"], []).append(c)

        for claim in new_claims:
            tool_id = claim_to_tool_id[claim.statement]
            claim_conflicts = conflicts_by_statement.get(claim.statement, [])
            if claim_conflicts:
                error_msgs = []
                for c in claim_conflicts:
                    if c["type"] == "DOMAIN_LIMIT_VIOLATION":
                        error_msgs.append(f"DOMAIN_LIMIT_VIOLATION: {c['message']}")
                    else:
                        error_msgs.append(f"CONFLICT ({c['severity']}): {c['message']}")
                content = "Fehler bei der Claim-Verarbeitung:\n" + "\n".join(error_msgs)
            else:
                content = f"Claim erfolgreich verarbeitet: {claim.statement}"
            tool_outputs.append(ToolMessage(content=content, tool_call_id=tool_id))

    # --- calculate_rwdr_specifications path: deterministic calc ---
    # Phase 0B.1: after the RWDR tool runs, validate its output against the
    # compound matrix.  This catches domain violations even when the LLM
    # submits NO submit_claim calls (pure calc path).
    for tc in rwdr_calls:
        try:
            calc_result = calculate_rwdr_specifications.invoke(tc["args"])
        except Exception as exc:
            calc_result = json.dumps({"status": "error", "notes": [str(exc)]})

        # Parse v_surface and pv_value from calc result for compound validation
        try:
            calc_data = json.loads(calc_result) if isinstance(calc_result, str) else calc_result
        except Exception:
            calc_data = {}
        args = tc.get("args") or {}
        rwdr_tool_runs.append(
            {
                "inputs": dict(args),
                "result": calc_data if isinstance(calc_data, dict) else {"raw_result": calc_data},
            }
        )

        # Build a synthetic claim-like statement from the tool args so the
        # compound validator can extract rpm / diameter from it
        synthetic_stmt = (
            f"Welle {args.get('shaft_diameter_mm', '')}mm "
            f"{args.get('rpm', '')} rpm "
            f"{args.get('pressure_bar', '') or ''} bar"
        ).strip()

        # Merge working_profile with calculated values so compound validator
        # has the most accurate context
        enriched_wp = dict(working_profile)
        if calc_data.get("v_surface_m_s"):
            enriched_wp["v_m_s"] = calc_data["v_surface_m_s"]

        rwdr_conflicts = validate_claim_against_matrix(
            synthetic_stmt,
            candidate_materials=None,  # check absolute limits only
            working_profile=enriched_wp,
        )
        all_domain_conflicts.extend(rwdr_conflicts)
        rwdr_domain_conflicts.extend(rwdr_conflicts)

        tool_outputs.append(ToolMessage(
            content=str(calc_result),
            name=tc["name"],
            tool_call_id=tc["id"],
        ))

    # Write all accumulated domain conflicts into sealing_state governance
    # so the state_update event carries them to the frontend.
    if rwdr_domain_conflicts and "sealing_state" not in result:
        old_sealing_state = state["sealing_state"]
        current_revision = old_sealing_state["cycle"]["state_revision"]
        new_sealing_state = process_cycle_update(
            old_state=old_sealing_state,
            intelligence_conflicts=rwdr_domain_conflicts,
            expected_revision=current_revision,
            validated_params={},
            raw_claims=[],
            relevant_fact_cards=state.get("relevant_fact_cards", []),
        )
        aligned_case_state, new_sealing_state = _align_runtime_cycle_token_case_meta_first(
            state,
            sealing_state=new_sealing_state,
        )
        if aligned_case_state:
            result["case_state"] = aligned_case_state
        result["sealing_state"] = new_sealing_state
    elif rwdr_domain_conflicts and "sealing_state" in result:
        # submit_claim already advanced the state revision; only apply RWDR-derived conflicts here
        old_sealing_state = result["sealing_state"]
        current_revision = old_sealing_state["cycle"]["state_revision"]
        new_sealing_state = process_cycle_update(
            old_state=old_sealing_state,
            intelligence_conflicts=rwdr_domain_conflicts,
            expected_revision=current_revision,
            validated_params={},
            raw_claims=[],
            relevant_fact_cards=state.get("relevant_fact_cards", []),
        )
        aligned_case_state, new_sealing_state = _align_runtime_cycle_token_case_meta_first(
            {**state, "case_state": result.get("case_state") or state.get("case_state")},
            sealing_state=new_sealing_state,
        )
        if aligned_case_state:
            result["case_state"] = aligned_case_state
        result["sealing_state"] = new_sealing_state

    if rwdr_tool_runs:
        base_sealing_state = result.get("sealing_state") or state.get("sealing_state") or {}
        result["sealing_state"] = _record_observed_tool_runs(
            base_sealing_state,
            rwdr_tool_runs=rwdr_tool_runs,
        )

    if "sealing_state" in result:
        sync_source_state = dict(state)
        if result.get("case_state") is not None:
            sync_source_state["case_state"] = result["case_state"]
        result["case_state"] = _sync_case_state_runtime_buckets(
            sync_source_state,
            sealing_state=result.get("sealing_state") or state.get("sealing_state") or {},
            working_profile=working_profile,
            run_meta=state.get("run_meta") or {},
            relevant_fact_cards=state.get("relevant_fact_cards") or [],
        )

    # --- safety net: unknown tools must still get a ToolMessage ---
    for tc in unknown_calls:
        tool_outputs.append(ToolMessage(
            content=f"Tool '{tc['name']}' ist nicht verfügbar.",
            name=tc["name"],
            tool_call_id=tc["id"],
        ))

    result["messages"] = tool_outputs
    return result


def selection_node(state: AgentState) -> dict:
    """Builds selection state and evaluates deterministic HITL review trigger (Phase A3)."""
    sealing_state = state["sealing_state"]
    governance_state = sealing_state.get("governance", {})
    _contract_demo_flag: bool = bool(
        (sealing_state.get("result_contract") or {}).get("demo_data_in_scope", False)
    )
    demo_data_in_scope: bool = REGISTRY_IS_DEMO_ONLY or _contract_demo_flag
    review_state = evaluate_review_trigger(
        governance_state=governance_state,
        demo_data_in_scope=demo_data_in_scope,
    )
    run_meta: dict = state.get("run_meta") or {}
    evidence_available: bool = run_meta.get("evidence_available", True)
    selection_state = build_selection_state(
        relevant_fact_cards=state.get("relevant_fact_cards", []),
        cycle_state=sealing_state.get("cycle", {}),
        governance_state=governance_state,
        asserted_state=sealing_state.get("asserted", {}),
        review_state=review_state,
        evidence_available=evidence_available,
        demo_data_present=demo_data_in_scope,
        working_profile=state.get("working_profile"),
        observed_state=sealing_state.get("observed"),
        normalized_state=sealing_state.get("normalized"),
    )
    new_sealing_state = dict(sealing_state)
    new_sealing_state["selection"] = selection_state
    new_sealing_state["review"] = review_state

    session_id, runtime_path, binding_level = _derive_case_context(state)

    provisional_state = dict(state)
    provisional_state["sealing_state"] = new_sealing_state
    provisional_state = ensure_case_state(
        provisional_state,
        session_id=session_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )

    matching_outcome = build_manufacturer_match_result_from_runtime_state(provisional_state)
    new_sealing_state["matching_outcome"] = matching_outcome
    provisional_state["sealing_state"] = new_sealing_state
    canonical_state = ensure_case_state(
        provisional_state,
        session_id=session_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )

    canonical_case_state = dict(canonical_state.get("case_state") or {})
    recipient_selection = dict(canonical_case_state.get("recipient_selection") or {})
    selected_partner_id = recipient_selection.get("selected_partner_id")
    if isinstance(selected_partner_id, str) and selected_partner_id.strip():
        recipient_selection["selected_partner_id"] = selected_partner_id.strip()
        canonical_case_state["recipient_selection"] = recipient_selection
        selection_state = dict(new_sealing_state.get("selection") or {})
        selection_state["selected_partner_id"] = selected_partner_id.strip()
        new_sealing_state["selection"] = selection_state

    dispatch_intent = build_dispatch_intent(
        (canonical_case_state.get("rfq_state") or {}).get("rfq_dispatch")
    )
    canonical_case_state["dispatch_intent"] = dispatch_intent
    dispatch_trigger = build_dispatch_trigger(
        {
            "case_state": canonical_case_state,
            "sealing_state": new_sealing_state,
        }
    )
    canonical_case_state["dispatch_trigger"] = dispatch_trigger
    dispatch_dry_run = build_dispatch_dry_run(
        {
            "case_state": canonical_case_state,
            "sealing_state": new_sealing_state,
        }
    )
    canonical_case_state["dispatch_dry_run"] = dispatch_dry_run
    dispatch_event = build_dispatch_event(
        {
            "case_state": canonical_case_state,
            "sealing_state": new_sealing_state,
        }
    )
    canonical_case_state["dispatch_event"] = dispatch_event
    dispatch_bridge = build_dispatch_bridge(
        {
            "case_state": canonical_case_state,
            "sealing_state": new_sealing_state,
        }
    )
    canonical_case_state["dispatch_bridge"] = dispatch_bridge
    dispatch_handoff = build_dispatch_handoff(
        {
            "case_state": canonical_case_state,
            "sealing_state": new_sealing_state,
        }
    )
    canonical_case_state["dispatch_handoff"] = dispatch_handoff
    dispatch_transport_envelope = build_dispatch_transport_envelope(
        {
            "case_state": canonical_case_state,
            "sealing_state": new_sealing_state,
        }
    )
    canonical_case_state["dispatch_transport_envelope"] = dispatch_transport_envelope
    canonical_state["case_state"] = canonical_case_state
    new_sealing_state["dispatch_intent"] = dispatch_intent
    new_sealing_state["dispatch_trigger"] = dispatch_trigger
    new_sealing_state["dispatch_dry_run"] = dispatch_dry_run
    new_sealing_state["dispatch_event"] = dispatch_event
    new_sealing_state["dispatch_bridge"] = dispatch_bridge
    new_sealing_state["dispatch_handoff"] = dispatch_handoff
    new_sealing_state["dispatch_transport_envelope"] = dispatch_transport_envelope

    return {
        "sealing_state": new_sealing_state,
        "case_state": canonical_state.get("case_state"),
    }


async def final_response_node(state: AgentState) -> dict:
    """Structured-path final reply — boundary block, run_meta, handover, and audit (Phase 0B.2 / 0A.5 / A3 / A6 / 1B).

    Converted to async def so asyncio.create_task() inside AuditLogger.append()
    fires correctly from within the running event loop (Blueprint Section 15).
    """
    sealing_state = state["sealing_state"]
    selection_state = sealing_state.get("selection", {})
    governance_state = sealing_state.get("governance", {})
    review_state: dict = sealing_state.get("review") or {}
    known_unknowns: list[str] = list(governance_state.get("unknowns_release_blocking") or [])

    # Phase 0D.4: evidence availability is an explicit governance signal
    run_meta: dict = state.get("run_meta") or {}
    evidence_available: bool = run_meta.get("evidence_available", True)

    # Phase 1B PATCH 4: pass full review_state dict so build_final_reply() can use
    # REVIEW_PENDING_REPLY when review is pending, and evaluate demo_data_present
    # from the same source used by selection_node().
    _contract_demo_flag_final: bool = bool(
        (sealing_state.get("result_contract") or {}).get("demo_data_in_scope", False)
    )
    demo_data_present: bool = REGISTRY_IS_DEMO_ONLY or _contract_demo_flag_final

    new_sealing_state = dict(sealing_state)
    case_state = state.get("case_state")
    incoming_case_state = dict(case_state or {})
    incoming_rfq_state = dict(incoming_case_state.get("rfq_state") or {})
    incoming_rfq_object = dict(incoming_rfq_state.get("rfq_object") or {})

    provisional_case_state = _canonicalize_runtime_case_state(
        state,
        sealing_state=new_sealing_state,
        case_state=dict(case_state or {}),
    )
    provisional_case_state = dict(provisional_case_state or {})
    if "matching_outcome" not in new_sealing_state:
        matching_input = dict(state)
        matching_input["sealing_state"] = new_sealing_state
        matching_input["case_state"] = provisional_case_state
        new_sealing_state["matching_outcome"] = build_manufacturer_match_result_from_runtime_state(matching_input)
        provisional_case_state = _canonicalize_runtime_case_state(
            state,
            sealing_state=new_sealing_state,
            case_state=provisional_case_state,
        )
        provisional_case_state = dict(provisional_case_state or {})
    provisional_rfq_state = dict(provisional_case_state.get("rfq_state") or {})
    provisional_review_state = dict(review_state or {})
    critical_review = run_critical_review_specialist(
        CriticalReviewSpecialistInput(
            governance_summary=CriticalReviewGovernanceSummary(
                release_status=str(governance_state.get("release_status") or "inadmissible"),
                rfq_admissibility=str(governance_state.get("rfq_admissibility") or "inadmissible"),
                unknowns_release_blocking=tuple(
                    str(item)
                    for item in list(governance_state.get("unknowns_release_blocking") or [])
                    if item is not None
                ),
                unknowns_manufacturer_validation=tuple(
                    str(item)
                    for item in list(governance_state.get("unknowns_manufacturer_validation") or [])
                    if item is not None
                ),
                scope_of_validity=tuple(
                    str(item)
                    for item in list(governance_state.get("scope_of_validity") or [])
                    if item is not None
                ),
                conflicts=tuple(
                    str(item)
                    for item in list(governance_state.get("conflicts") or [])
                    if item is not None
                ),
                review_required=bool(provisional_review_state.get("review_required", False)),
            ),
            recommendation_package=CriticalReviewRecommendationPackage(
                requirement_class=(
                    dict(provisional_case_state.get("requirement_class") or {})
                    or dict(provisional_rfq_state.get("requirement_class") or {})
                    or None
                ),
            ),
            matching_package=CriticalReviewMatchingPackage(
                status=str((new_sealing_state.get("matching_outcome") or {}).get("status") or ""),
                selected_manufacturer_ref=dict(
                    ((new_sealing_state.get("matching_outcome") or {}).get("selected_manufacturer_ref") or {})
                )
                or None,
            ),
            rfq_basis=CriticalReviewRfqBasis(
                rfq_object=dict(provisional_rfq_state.get("rfq_object") or {}) or None,
                recipient_refs=tuple(
                    dict(ref)
                    for ref in list(
                        (provisional_case_state.get("recipient_selection") or {}).get("candidate_recipient_refs")
                        or (provisional_rfq_state.get("recipient_selection") or {}).get("candidate_recipient_refs")
                        or (provisional_case_state.get("manufacturer_state") or {}).get("manufacturer_refs")
                        or []
                    )
                    if isinstance(ref, dict) and ref
                ),
            ),
        )
    )
    provisional_review_state.update(critical_review_result_to_dict(critical_review))
    new_sealing_state["review"] = provisional_review_state

    handover = build_handover_payload(
        new_sealing_state,
        canonical_case_state=provisional_case_state or None,
        canonical_rfq_object=dict(provisional_rfq_state.get("rfq_object") or {}) or None,
        rfq_admissibility=provisional_rfq_state.get("rfq_admissibility") or governance_state.get("rfq_admissibility"),
    )
    new_sealing_state["handover"] = handover
    review_state = dict(new_sealing_state.get("review") or {})

    case_state = _canonicalize_runtime_case_state(
        state,
        sealing_state=new_sealing_state,
        case_state=provisional_case_state,
    )
    case_state = dict(case_state or {})
    rfq_state = dict(case_state.get("rfq_state") or {})
    handover = dict(new_sealing_state.get("handover") or {})
    rfq_admissibility = governance_state.get(
        "rfq_admissibility",
        rfq_state.get("rfq_admissibility", "inadmissible"),
    )
    rfq_state["rfq_admissibility"] = rfq_admissibility
    rfq_state["status"] = "ready" if rfq_admissibility == "ready" else rfq_admissibility
    if handover.get("handover_status") is not None:
        rfq_state["handover_status"] = handover.get("handover_status")
    if handover.get("is_handover_ready") is not None:
        rfq_state["handover_ready"] = bool(handover.get("is_handover_ready"))
    if incoming_rfq_state.get("rfq_confirmed") is not None:
        rfq_state["rfq_confirmed"] = bool(incoming_rfq_state.get("rfq_confirmed"))
    elif handover.get("rfq_confirmed") is not None:
        rfq_state["rfq_confirmed"] = bool(handover.get("rfq_confirmed"))
    if incoming_rfq_state.get("rfq_handover_initiated") is not None:
        rfq_state["rfq_handover_initiated"] = bool(incoming_rfq_state.get("rfq_handover_initiated"))
    elif handover.get("handover_completed") is not None:
        rfq_state["rfq_handover_initiated"] = bool(handover.get("handover_completed"))
    if incoming_rfq_state.get("rfq_html_report_present") is not None:
        rfq_state["rfq_html_report_present"] = bool(incoming_rfq_state.get("rfq_html_report_present"))
    elif rfq_state.get("rfq_html_report_present") is None:
        if handover.get("rfq_html_report_present") is not None:
            rfq_state["rfq_html_report_present"] = bool(handover.get("rfq_html_report_present"))
        elif handover.get("rfq_html_report") is not None:
            rfq_state["rfq_html_report_present"] = bool(handover.get("rfq_html_report"))

    rfq_object = dict(rfq_state.get("rfq_object") or {})
    preferred_rfq_object = incoming_rfq_object or rfq_object
    if preferred_rfq_object:
        rfq_state["rfq_object"] = preferred_rfq_object

    case_state["rfq_state"] = rfq_state
    handover = build_handover_payload(
        new_sealing_state,
        canonical_case_state=case_state,
        canonical_rfq_object=preferred_rfq_object or None,
        rfq_admissibility=rfq_state.get("rfq_admissibility"),
    )
    new_sealing_state["handover"] = handover
    case_state = _canonicalize_runtime_case_state(
        state,
        sealing_state=new_sealing_state,
        case_state=case_state,
    )
    case_state = dict(case_state or {})
    rfq_state = dict(case_state.get("rfq_state") or {})

    dispatch_intent = (
        dict(new_sealing_state.get("dispatch_intent") or {})
        or dict(case_state.get("dispatch_intent") or {})
        or build_dispatch_intent((case_state.get("rfq_state") or {}).get("rfq_dispatch"))
    )
    if dispatch_intent is not None:
        dispatch_intent = _merge_dispatch_lifecycle_slice(
            case_surface=dict(incoming_case_state.get("dispatch_intent") or {}),
            sealing_surface=dispatch_intent,
            lifecycle_keys=("dispatch_status", "dispatch_ready"),
        )
        dispatch_intent = _merge_dispatch_basis_slice(
            case_surface=dict(incoming_case_state.get("dispatch_intent") or {}),
            sealing_surface=dispatch_intent,
            basis_keys=(
                "dispatch_blockers",
                "recipient_refs",
                "selected_manufacturer_ref",
                "recipient_selection",
                "requirement_class",
                "recommendation_identity",
                "rfq_object_basis",
            ),
        )
        new_sealing_state["dispatch_intent"] = dispatch_intent
        case_state = dict(case_state)
        case_state["dispatch_intent"] = dispatch_intent

    if "dispatch_trigger" not in new_sealing_state:
        dispatch_trigger_input = {
            "case_state": case_state or {},
            "sealing_state": new_sealing_state,
        }
        dispatch_trigger = build_dispatch_trigger(dispatch_trigger_input)
        new_sealing_state["dispatch_trigger"] = dispatch_trigger
    if "dispatch_trigger" in new_sealing_state and case_state is not None:
        dispatch_trigger = _merge_dispatch_lifecycle_slice(
            case_surface=dict(incoming_case_state.get("dispatch_trigger") or {}),
            sealing_surface=dict(new_sealing_state["dispatch_trigger"]),
            lifecycle_keys=("trigger_status", "trigger_allowed"),
        )
        dispatch_trigger = _merge_dispatch_basis_slice(
            case_surface=dict(incoming_case_state.get("dispatch_trigger") or {}),
            sealing_surface=dispatch_trigger,
            basis_keys=(
                "trigger_blockers",
                "recipient_refs",
                "selected_manufacturer_ref",
                "requirement_class",
                "recommendation_identity",
            ),
        )
        new_sealing_state["dispatch_trigger"] = dispatch_trigger
        case_state = dict(case_state)
        case_state["dispatch_trigger"] = dispatch_trigger

    if "dispatch_dry_run" not in new_sealing_state:
        dispatch_dry_run_input = {
            "case_state": case_state or {},
            "sealing_state": new_sealing_state,
        }
        dispatch_dry_run = build_dispatch_dry_run(dispatch_dry_run_input)
        new_sealing_state["dispatch_dry_run"] = dispatch_dry_run
    if "dispatch_dry_run" in new_sealing_state and case_state is not None:
        dispatch_dry_run = _merge_dispatch_lifecycle_slice(
            case_surface=dict(incoming_case_state.get("dispatch_dry_run") or {}),
            sealing_surface=dict(new_sealing_state["dispatch_dry_run"]),
            lifecycle_keys=("dry_run_status", "would_dispatch"),
        )
        dispatch_dry_run = _merge_dispatch_basis_slice(
            case_surface=dict(incoming_case_state.get("dispatch_dry_run") or {}),
            sealing_surface=dispatch_dry_run,
            basis_keys=(
                "dry_run_blockers",
                "recipient_refs",
                "selected_manufacturer_ref",
                "requirement_class",
                "recommendation_identity",
                "trigger_source",
            ),
        )
        new_sealing_state["dispatch_dry_run"] = dispatch_dry_run
        case_state = dict(case_state)
        case_state["dispatch_dry_run"] = dispatch_dry_run

    dispatch_event_input = {
        "case_state": _without_dispatch_surface(case_state, "dispatch_event", "dispatch_bridge", "dispatch_handoff", "dispatch_transport_envelope"),
        "sealing_state": new_sealing_state,
    }
    dispatch_event = build_dispatch_event(dispatch_event_input)
    if case_state is not None:
        dispatch_event = _merge_dispatch_lifecycle_slice(
            case_surface=dict(incoming_case_state.get("dispatch_event") or {}),
            sealing_surface=dispatch_event,
            lifecycle_keys=("event_status", "would_dispatch", "dry_run_status"),
        )
        dispatch_event = _merge_dispatch_basis_slice(
            case_surface=dict(incoming_case_state.get("dispatch_event") or {}),
            sealing_surface=dispatch_event,
            basis_keys=(
                "event_blockers",
                "recipient_refs",
                "selected_manufacturer_ref",
                "requirement_class",
                "recommendation_identity",
                "trigger_source",
            ),
        )
        case_state = dict(case_state)
        case_state["dispatch_event"] = dispatch_event
    new_sealing_state["dispatch_event"] = dispatch_event

    dispatch_bridge_input = {
        "case_state": _without_dispatch_surface(case_state, "dispatch_bridge", "dispatch_handoff", "dispatch_transport_envelope"),
        "sealing_state": new_sealing_state,
    }
    dispatch_bridge = build_dispatch_bridge(dispatch_bridge_input)
    if case_state is not None:
        dispatch_bridge = _merge_dispatch_lifecycle_slice(
            case_surface=dict(incoming_case_state.get("dispatch_bridge") or {}),
            sealing_surface=dispatch_bridge,
            lifecycle_keys=("bridge_status", "dry_run_status"),
        )
        dispatch_bridge = _merge_dispatch_basis_slice(
            case_surface=dict(incoming_case_state.get("dispatch_bridge") or {}),
            sealing_surface=dispatch_bridge,
            basis_keys=(
                "bridge_blockers",
                "recipient_refs",
                "selected_manufacturer_ref",
                "requirement_class",
                "recommendation_identity",
                "bridge_payload_summary",
            ),
        )
        case_state = dict(case_state)
        case_state["dispatch_bridge"] = dispatch_bridge
    new_sealing_state["dispatch_bridge"] = dispatch_bridge

    dispatch_handoff_input = {
        "case_state": _without_dispatch_surface(case_state, "dispatch_handoff", "dispatch_transport_envelope"),
        "sealing_state": new_sealing_state,
    }
    dispatch_handoff = build_dispatch_handoff(dispatch_handoff_input)
    if case_state is not None:
        dispatch_handoff = _merge_dispatch_lifecycle_slice(
            case_surface=dict(incoming_case_state.get("dispatch_handoff") or {}),
            sealing_surface=dispatch_handoff,
            lifecycle_keys=("handoff_status", "bridge_status"),
        )
        dispatch_handoff = _merge_dispatch_basis_slice(
            case_surface=dict(incoming_case_state.get("dispatch_handoff") or {}),
            sealing_surface=dispatch_handoff,
            basis_keys=(
                "handoff_blockers",
                "recipient_refs",
                "selected_manufacturer_ref",
                "requirement_class",
                "recommendation_identity",
                "payload_summary",
            ),
        )
        case_state = dict(case_state)
        case_state["dispatch_handoff"] = dispatch_handoff
    new_sealing_state["dispatch_handoff"] = dispatch_handoff

    dispatch_transport_envelope_input = {
        "case_state": _without_dispatch_surface(case_state, "dispatch_transport_envelope"),
        "sealing_state": new_sealing_state,
    }
    dispatch_transport_envelope = build_dispatch_transport_envelope(dispatch_transport_envelope_input)
    if case_state is not None:
        dispatch_transport_envelope = _merge_dispatch_lifecycle_slice(
            case_surface=dict(incoming_case_state.get("dispatch_transport_envelope") or {}),
            sealing_surface=dispatch_transport_envelope,
            lifecycle_keys=("envelope_status", "handoff_status"),
        )
        dispatch_transport_envelope = _merge_dispatch_basis_slice(
            case_surface=dict(incoming_case_state.get("dispatch_transport_envelope") or {}),
            sealing_surface=dispatch_transport_envelope,
            basis_keys=(
                "envelope_blockers",
                "recipient_refs",
                "selected_manufacturer_ref",
                "requirement_class",
                "recommendation_identity",
                "payload_summary",
            ),
        )
        case_state = dict(case_state)
        case_state["dispatch_transport_envelope"] = dispatch_transport_envelope
    new_sealing_state["dispatch_transport_envelope"] = dispatch_transport_envelope

    reply = build_final_reply(
        selection_state,
        known_unknowns=known_unknowns or None,
        review_required=bool(review_state.get("review_required", False)),
        review_reason=str(review_state.get("review_reason", "")),
        review_state=review_state or None,
        demo_data_present=demo_data_present,
        asserted_state=sealing_state.get("asserted"),
        working_profile=state.get("working_profile"),
        evidence_available=evidence_available,
        case_state=case_state,
    )

    # ── Phase 1B: Audit log — Blueprint Section 15 ───────────────────────────
    # Fire-and-forget via asyncio.create_task (AuditLogger.append internals).
    # Works here because we are in an async def — the event loop IS running.
    # final_response_node is ONLY reached on the structured (qualification) path.
    try:
        from app.services.audit.audit_logger import get_global_audit_logger

        audit_logger = get_global_audit_logger()
        if audit_logger is not None:
            session_id: str = (
                state.get("inquiry_id")
                or state.get("session_id")
                or sealing_state.get("cycle", {}).get("analysis_cycle_id")
                or "unknown"
            )
            tenant_id: str | None = (
                state.get("tenant_id")
                or sealing_state.get("cycle", {}).get("tenant_id")
            )
            critique_log = {
                "release_status": governance_state.get("release_status"),
                "rfq_admissibility": governance_state.get("rfq_admissibility"),
                "conflicts": governance_state.get("conflicts") or [],
                "unknowns_release_blocking": governance_state.get("unknowns_release_blocking") or [],
                "state_revision": sealing_state.get("cycle", {}).get("state_revision"),
                "node": "final_response_node",
            }
            audit_logger.append(
                session_id=session_id,
                tenant_id=tenant_id,
                state={
                    "working_profile": state.get("working_profile") or {},
                    "critique_log": critique_log,
                    "phase": "final_response_node:structured",
                },
            )
            logger.info(
                "[audit] scheduled: session=%s tenant=%s release=%s conflicts=%d",
                session_id,
                tenant_id,
                critique_log.get("release_status"),
                len(critique_log["conflicts"]),
            )
        else:
            logger.debug("[audit] global AuditLogger not initialised — skipping")
    except Exception as exc:
        logger.error("[audit] fire_audit failed (non-fatal): %s", exc)

    return {
        "messages": [AIMessage(content=reply)],
        "sealing_state": new_sealing_state,
        "case_state": case_state,
    }


def router(state: AgentState) -> Literal["evidence_tool_node", "selection_node"]:
    """
    Internal structured-path router: tool-call vs no-tool-call.
    UNCHANGED — deterministic Blueprint Section 03.
    """
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "evidence_tool_node"
    return "selection_node"


# ---------------------------------------------------------------------------
# Graph topology
# ---------------------------------------------------------------------------

graph_builder = StateGraph(AgentState)

graph_builder.add_node("fast_guidance_node", fast_guidance_node)
graph_builder.add_node("meta_response_node", meta_response_node)
graph_builder.add_node("blocked_node", blocked_node)
graph_builder.add_node("greeting_node", greeting_node)
graph_builder.add_node("reasoning_node", reasoning_node)
graph_builder.add_node("evidence_tool_node", evidence_tool_node)
graph_builder.add_node("selection_node", selection_node)
graph_builder.add_node("final_response_node", final_response_node)

# Entry switch (Phase 0A.3 / 0D)
graph_builder.add_conditional_edges(
    START,
    route_by_policy,
    {
        "fast_guidance_node": "fast_guidance_node",
        "meta_response_node": "meta_response_node",
        "blocked_node": "blocked_node",
        "greeting_node": "greeting_node",
        "reasoning_node": "reasoning_node",
    },
)

# Fast / meta / blocked / greeting paths: direct to END
graph_builder.add_edge("fast_guidance_node", END)
graph_builder.add_edge("meta_response_node", END)
graph_builder.add_edge("blocked_node", END)
graph_builder.add_edge("greeting_node", END)

# Structured path: full pipeline (UNCHANGED)
graph_builder.add_conditional_edges(
    "reasoning_node",
    router,
    {
        "evidence_tool_node": "evidence_tool_node",
        "selection_node": "selection_node",
    },
)
graph_builder.add_edge("evidence_tool_node", "reasoning_node")
graph_builder.add_edge("selection_node", "final_response_node")
graph_builder.add_edge("final_response_node", END)

app = graph_builder.compile()
