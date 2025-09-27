# backend/app/services/langgraph/graph/consult/build.py
from __future__ import annotations

import logging
from typing import Any, Dict, List
from langgraph.graph import StateGraph, END  # END aktuell ungenutzt, bleibt für spätere Flows

from .state import ConsultState
from .utils import normalize_messages, missing_by_domain
from .domain_router import detect_domain
from .domain_runtime import compute_domain

from .nodes.intake import intake_node
from .nodes.ask_missing import ask_missing_node
from .nodes.validate import validate_node
from .nodes.recommend import recommend_node
from .nodes.explain import explain_node
from .nodes.calc_agent import calc_agent_node
from .nodes.rag import run_rag_node
from .nodes.validate_answer import validate_answer

# NEU
from .nodes.smalltalk import smalltalk_node
from .nodes.lite_router import lite_router_node
from .nodes.deterministic_calc import deterministic_calc_node  # NEW

from .heuristic_extract import pre_extract_params
from .extract import extract_params_with_llm
from .config import create_llm  # ggf. später genutzt
from ..logging_utils import wrap_node_with_logging, log_branch_decision

log = logging.getLogger("uvicorn.error")
_GRAPH_NAME = "ConsultGraph"


def _join_user_text(msgs: List) -> str:
    out: List[str] = []
    for m in msgs:
        role = (getattr(m, "type", "") or getattr(m, "role", "")).lower()
        content = getattr(m, "content", "")
        if isinstance(m, dict):
            role = (m.get("type") or m.get("role") or "").lower()
            content = m.get("content")
        if role in ("human", "user") and isinstance(content, str) and content.strip():
            out.append(content.strip())
    return "\n".join(out)


def _merge_seed_first(seed: Dict[str, Any], llm_out: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(llm_out or {})
    for k, v in (seed or {}).items():
        if v not in (None, "", []):
            out[k] = v
    return out


def _compact_param_summary(domain: str, params: Dict[str, Any]) -> str:
    p = params or {}
    parts: List[str] = []

    if domain == "rwdr":
        parts.append("RWDR")
        if p.get("abmessung"):
            parts.append(str(p["abmessung"]))
        elif p.get("wellen_mm") and p.get("gehause_mm") and p.get("breite_mm"):
            parts.append(f'{p["wellen_mm"]}x{p["gehause_mm"]}x{p["breite_mm"]}')
    elif domain == "hydraulics_rod":
        parts.append("Hydraulik Stangendichtung")

    if p.get("medium"):
        parts.append(str(p["medium"]))
    if p.get("temp_max_c") or p.get("tmax_c"):
        parts.append(f'Tmax {int(p.get("temp_max_c") or p.get("tmax_c"))} °C')
    if p.get("druck_bar"):
        parts.append(f'Druck {p["druck_bar"]} bar')
    if p.get("drehzahl_u_min"):
        parts.append(f'{int(p["drehzahl_u_min"])} U/min')
    if p.get("relativgeschwindigkeit_ms") or p.get("geschwindigkeit_m_s"):
        v = p.get("relativgeschwindigkeit_ms") or p.get("geschwindigkeit_m_s")
        parts.append(f'v≈{float(v):.2f} m/s')

    bl = p.get("material_blacklist") or p.get("vermeide_materialien")
    wl = p.get("material_whitelist") or p.get("bevorzugte_materialien")
    if bl:
        parts.append(f'Vermeide: {bl}')
    if wl:
        parts.append(f'Bevorzugt: {wl}')

    return ", ".join(parts)


def _extract_node(state: Dict[str, Any]) -> Dict[str, Any]:
    msgs = normalize_messages(state.get("messages", []))
    params = dict(state.get("params") or {})
    user_text = _join_user_text(msgs)

    heur = pre_extract_params(user_text)
    seed = {**params, **{k: v for k, v in heur.items() if v not in (None, "", [])}}

    llm_params = extract_params_with_llm(user_text)
    final_params = _merge_seed_first(seed, llm_params)
    return {**state, "params": final_params, "phase": "extract"}


def _domain_router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    msgs = normalize_messages(state.get("messages", []))
    params = dict(state.get("params") or {})
    try:
        domain = detect_domain(None, msgs, params) or "rwdr"
        domain = domain.strip().lower()
    except Exception:
        domain = "rwdr"
    return {**state, "domain": domain, "phase": "domain_router"}


def _compute_node(state: Dict[str, Any]) -> Dict[str, Any]:
    domain = (state.get("domain") or "rwdr").strip().lower()
    params = dict(state.get("params") or {})
    derived = compute_domain(domain, params) or {}

    alias_map = {
        "tmax_c": params.get("temp_max_c"),
        "temp_c": params.get("temp_max_c"),
        "druck": params.get("druck_bar"),
        "pressure_bar": params.get("druck_bar"),
        "n_u_min": params.get("drehzahl_u_min"),
        "rpm": params.get("drehzahl_u_min"),
        "v_ms": params.get("relativgeschwindigkeit_ms") or params.get("geschwindigkeit_m_s"),
    }
    for k, v in alias_map.items():
        if k not in params and v not in (None, "", []):
            params[k] = v

    return {**state, "params": params, "derived": derived, "phase": "compute"}


def _prepare_query_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if (state.get("query") or "").strip():
        return {**state, "phase": "prepare_query"}

    params = dict(state.get("params") or {})
    domain = (state.get("domain") or "rwdr").strip().lower()

    user_text = ""  # Query ist rein technisch – daher kompakter Param-String
    param_str = _compact_param_summary(domain, params)
    prefix = "RWDR" if domain == "rwdr" else "Hydraulik"
    query = ", ".join([s for s in [prefix, user_text, param_str] if s])

    new_state = dict(state)
    new_state["query"] = query
    return {**new_state, "phase": "prepare_query"}


def _respond_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return {**state, "phase": "respond"}


# ---- Conditional helpers ----
def _route_key(state: Dict[str, Any]) -> str:
    branch = (state.get("route") or "default").strip().lower() or "default"
    log_branch_decision(_GRAPH_NAME, "lite_router", "route", branch, state)
    return branch


def _ask_or_ok(state: Dict[str, Any]) -> str:
    domain = (state.get("domain") or "rwdr").strip().lower()
    params = dict(state.get("params") or {})
    missing_required = missing_by_domain(domain, params)

    ui_event = state.get("ui_event") if isinstance(state.get("ui_event"), dict) else None
    needs_user_action = bool(missing_required)
    if not needs_user_action and ui_event:
        needs_user_action = ui_event.get("ui_action") == "open_form"

    branch = "ask" if needs_user_action else "ok"
    log_branch_decision(_GRAPH_NAME, "ask_missing", "ask_or_ok", branch, state)
    return branch


def _need_gate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Frühe Pflichtfeld-Prüfung vor Berechnungen."""
    result = dict(ask_missing_node(state) or {})
    result.setdefault("missing_fields", [])
    result.setdefault("messages", [])
    result["phase"] = "need_gate"
    return result


def _need_gate_branch(state: Dict[str, Any]) -> str:
    missing = state.get("missing_fields") or []
    branch = "ask" if missing else "ok"
    log_branch_decision(_GRAPH_NAME, "need_gate", "required_params", branch, state)
    return branch


def _after_rag(state: Dict[str, Any]) -> str:
    p = state.get("params") or {}

    def has(v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, (list, dict)) and not v:
            return False
        if isinstance(v, str) and not v.strip():
            return False
        return True

    base_ok = has(p.get("temp_max_c")) and has(p.get("druck_bar"))
    rel_ok = has(p.get("relativgeschwindigkeit_ms") or p.get("geschwindigkeit_m_s")) or (
        has(p.get("wellen_mm")) and has(p.get("drehzahl_u_min"))
    )
    docs = state.get("retrieved_docs") or state.get("docs") or []
    ctx_ok = bool(docs) or bool(state.get("context"))

    branch = "recommend" if (base_ok and rel_ok and ctx_ok) else "explain"
    log_branch_decision(_GRAPH_NAME, "rag", "after_rag", branch, state)
    return branch


def build_graph() -> StateGraph:
    log.info("[ConsultGraph] Initialisierung…")
    g = StateGraph(ConsultState)

    # --- Nodes ---
    g.add_node("lite_router", wrap_node_with_logging(_GRAPH_NAME, "lite_router", lite_router_node))   # NEU
    g.add_node("smalltalk", wrap_node_with_logging(_GRAPH_NAME, "smalltalk", smalltalk_node))       # NEU

    g.add_node("intake", wrap_node_with_logging(_GRAPH_NAME, "intake", intake_node))
    g.add_node("extract", wrap_node_with_logging(_GRAPH_NAME, "extract", _extract_node))
    g.add_node("domain_router", wrap_node_with_logging(_GRAPH_NAME, "domain_router", _domain_router_node))
    g.add_node("need_gate", wrap_node_with_logging(_GRAPH_NAME, "need_gate", _need_gate_node))
    g.add_node("compute", wrap_node_with_logging(_GRAPH_NAME, "compute", _compute_node))

    # NEW: deterministische Physik vor dem LLM-Calc-Agent
    g.add_node(
        "deterministic_calc",
        wrap_node_with_logging(_GRAPH_NAME, "deterministic_calc", deterministic_calc_node),
    )

    g.add_node("calc_agent", wrap_node_with_logging(_GRAPH_NAME, "calc_agent", calc_agent_node))
    g.add_node("ask_missing", wrap_node_with_logging(_GRAPH_NAME, "ask_missing", ask_missing_node))
    g.add_node("validate", wrap_node_with_logging(_GRAPH_NAME, "validate", validate_node))
    g.add_node(
        "prepare_query",
        wrap_node_with_logging(_GRAPH_NAME, "prepare_query", _prepare_query_node),
    )
    g.add_node("rag", wrap_node_with_logging(_GRAPH_NAME, "rag", run_rag_node))
    g.add_node("recommend", wrap_node_with_logging(_GRAPH_NAME, "recommend", recommend_node))
    g.add_node(
        "validate_answer",
        wrap_node_with_logging(_GRAPH_NAME, "validate_answer", validate_answer),
    )
    g.add_node("explain", wrap_node_with_logging(_GRAPH_NAME, "explain", explain_node))
    g.add_node("respond", wrap_node_with_logging(_GRAPH_NAME, "respond", _respond_node))

    # --- Entry & Routing ---
    g.set_entry_point("lite_router")
    g.add_conditional_edges("lite_router", _route_key, {
        "smalltalk": "smalltalk",
        "default": "intake",
    })

    # Smalltalk direkt abschließen
    g.add_edge("smalltalk", "respond")

    # --- Main flow ---
    g.add_edge("intake", "extract")
    g.add_edge("extract", "domain_router")
    g.add_edge("domain_router", "need_gate")

    g.add_conditional_edges("need_gate", _need_gate_branch, {
        "ask": "respond",
        "ok": "compute",
    })

    g.add_edge("compute", "deterministic_calc")
    g.add_edge("deterministic_calc", "calc_agent")
    g.add_edge("calc_agent", "ask_missing")

    g.add_conditional_edges("ask_missing", _ask_or_ok, {
        "ask": "respond",
        "ok": "validate",
    })

    g.add_edge("validate", "prepare_query")
    g.add_edge("prepare_query", "rag")

    g.add_conditional_edges("rag", _after_rag, {
        "recommend": "recommend",
        "explain": "explain",
    })

    g.add_edge("recommend", "validate_answer")
    g.add_edge("validate_answer", "respond")
    g.add_edge("explain", "respond")

    return g


# ---- Alias für io.py (erwartet build_consult_graph) ----
def build_consult_graph() -> StateGraph:
    """Kompatibilitäts-Alias – liefert denselben StateGraph wie build_graph()."""
    return build_graph()


__all__ = ["build_graph", "build_consult_graph"]
