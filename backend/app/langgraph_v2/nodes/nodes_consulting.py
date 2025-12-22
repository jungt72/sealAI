"""Consulting subgraph nodes for LangGraph v2."""

from __future__ import annotations

from typing import Dict, List
import structlog

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import Recommendation, SealAIState, TechnicalParameters, WorkingMemory
from app.langgraph_v2.utils.llm_factory import run_llm, get_model_tier
from app.langgraph_v2.constants import MODEL_PRO
from app.langgraph_v2.utils.json_sanitizer import extract_json_obj

logger = structlog.get_logger("langgraph_v2.nodes_consulting")

ALLOWED_DECISIONS = {"NEXT", "RETRY", "ESCALATE", "END_WITH_MESSAGE"}
MAX_RETRIES = 2


def consulting_supervisor_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Agentic Supervisor: Decides the next step in the consulting process.
    """
    params_obj = state.parameters or TechnicalParameters()
    parameters = params_obj.as_dict()
    wm: WorkingMemory = state.working_memory or WorkingMemory()
    working_memory = wm.as_dict()
    retries = working_memory.get("retries") or 0
    coverage_score = state.coverage_score or 0.0
    calc_ok = bool(state.get("calc_results_ok"))

    # Construct a summary of the current state for the LLM
    state_summary = f"""
    Current Phase: Consulting
    Parameters Collected: {parameters}
    Working Memory: {working_memory}
    Coverage Score: {coverage_score}
    Calc OK: {calc_ok}
    Retries: {retries}
    """

    prompt = f"""
    Du bist der Supervisor für einen Dichtungstechnik-Beratungsprozess.
    Deine Aufgabe ist es, den nächsten Schritt zu bestimmen.
    
    Aktueller Status:
    {state_summary}
    
    Mögliche nächste Schritte:
    - NEXT: Alle notwendigen Informationen scheinen vorhanden oder der Prozess soll normal weiterlaufen (Materialauswahl).
    - RETRY: Es fehlen kritische Informationen oder es gibt Unklarheiten, die den User gefragt werden müssen.
    - ESCALATE: Abbruch mit höflicher Fehlermeldung, wenn Daten inkonsistent oder unvollständig sind.
    - END_WITH_MESSAGE: Sofort beenden und eine kurze hilfreiche Nachricht an den User schicken.
    
    Entscheide basierend auf dem Fortschritt. Wenn wir Parameter haben, gehen wir meistens weiter zur Materialauswahl.
    
    Antworte NUR mit dem JSON-Format:
    {
        "decision": "NEXT" | "RETRY" | "ESCALATE" | "END_WITH_MESSAGE",
        "reason": "Kurze Begründung oder User-Nachricht bei END_WITH_MESSAGE"
    }
    """

    try:
        model_name = get_model_tier("pro") or MODEL_PRO
        response_text = run_llm(
            model=model_name,
            prompt=prompt,
            system="Du bist ein strategischer Supervisor. Antworte nur mit JSON.",
            temperature=0.0,
            metadata={
                "run_id": state.run_id,
                "thread_id": state.thread_id,
                "user_id": state.user_id,
                "node": "consulting_supervisor_node",
            },  # PATCH/FIX: Observability – LLM metadata
        )

        data, ok = extract_json_obj(response_text, default={})
        decision = str(data.get("decision") or "NEXT").upper()
        reason = str(data.get("reason") or "").strip()

        if decision not in ALLOWED_DECISIONS:
            decision = "NEXT"

        if decision == "RETRY":
            retries = min(retries + 1, MAX_RETRIES)

        if decision == "END_WITH_MESSAGE" and reason:
            working_memory["response_text"] = reason  # PATCH/FIX: Supervisor END_WITH_MESSAGE surface
            working_memory["response_kind"] = "supervisor_end"

        working_memory["retries"] = retries
        working_memory["supervisor_decision"] = decision

    except Exception as e:
        logger.error(
            "consulting_supervisor_node_failed",  # PATCH/FIX: Observability – structured logging
            run_id=state.run_id,
            thread_id=state.thread_id,
            error=str(e),
        )
        working_memory["supervisor_decision"] = "NEXT"
        working_memory["retries"] = retries

    wm_next = wm.model_copy(update=working_memory)

    logger.info(
        "consulting_supervisor_node_exit",  # PATCH/FIX: Observability – node exit
        run_id=state.run_id,
        thread_id=state.thread_id,
        decision=working_memory.get("supervisor_decision"),
        retries=working_memory.get("retries"),
    )

    return {
        "working_memory": wm_next,
        "phase": PHASE.CONSULTING,
        "last_node": "consulting_supervisor_node",
    }


def material_requirements_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    params_obj = state.parameters or TechnicalParameters()
    parameters = params_obj.as_dict()
    wm: WorkingMemory = state.working_memory or WorkingMemory()

    material_requirements = {
        "seal_family": state.get("seal_family"),
        "medium": parameters.get("medium"),
        "temperature_max": parameters.get("temperature_max"),
        "pressure_bar": parameters.get("pressure_bar") or parameters.get("pressure"),
        "use_case": state.get("use_case_raw"),
    }
    wm_next = wm.model_copy(update={"material_requirements": material_requirements})

    return {
        "working_memory": wm_next,
        "phase": PHASE.CONSULTING,
        "last_node": "material_requirements_node",
    }


def material_candidate_generation_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    params_obj = state.parameters or TechnicalParameters()
    parameters = params_obj.as_dict()
    wm: WorkingMemory = state.working_memory or WorkingMemory()

    medium = str(parameters.get("medium") or "").lower()
    temperature_max = parameters.get("temperature_max")
    pressure = parameters.get("pressure_bar") or parameters.get("pressure")

    candidates: List[Dict[str, object]] = []

    if "öl" in medium or "oil" in medium:
        candidates = [
            {"name": "NBR", "score": 0.7, "notes": ["Standard für Mineralöle"]},
            {"name": "FKM", "score": 0.9, "notes": ["Bessere Temperaturbeständigkeit"]},
        ]
    elif isinstance(temperature_max, (int, float)) and temperature_max > 150:
        candidates = [
            {"name": "FKM", "score": 0.85, "notes": ["Hohe Temperaturbeständigkeit"]},
            {"name": "FFKM", "score": 0.9, "notes": ["Sehr hohe Temperaturbeständigkeit"]},
            {"name": "PTFE-basiert", "score": 0.8, "notes": ["Thermische Reserve, chemisch inert"]},
        ]
    else:
        candidates = [
            {"name": "NBR", "score": 0.6, "notes": ["Allround, gut bei Ölen und Fetten"]},
            {"name": "EPDM", "score": 0.65, "notes": ["Gut bei Wasser/Medien ohne Öl"]},
        ]

    # Light pressure heuristic
    if isinstance(pressure, (int, float)) and pressure > 20:
        candidates.append({"name": "HNBR", "score": 0.7, "notes": ["Erhöhte Festigkeit bei höherem Druck"]})

    wm_next = wm.model_copy(update={"material_candidates": candidates})

    return {
        "working_memory": wm_next,
        "phase": PHASE.CONSULTING,
        "last_node": "material_candidate_generation_node",
    }


def material_candidate_ranking_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    wm: WorkingMemory = state.working_memory or WorkingMemory()
    working_memory = wm.as_dict()
    candidates: List[Dict[str, object]] = working_memory.get("material_candidates") or []

    selected = None
    if candidates:
        selected = max(candidates, key=lambda c: c.get("score", 0))
    else:
        selected = {"name": "NBR", "score": 0.5, "notes": ["Fallback-Kandidat"]}

    material_name = selected.get("name") or "NBR"

    raw_recommendation = state.get("recommendation")
    if isinstance(raw_recommendation, Recommendation):
        recommendation_data: Dict[str, object] = raw_recommendation.model_dump()
    elif isinstance(raw_recommendation, dict):
        recommendation_data = dict(raw_recommendation)
    else:
        recommendation_data = {}

    recommendation_rationale = recommendation_data.get("rationale") or ""
    recommendation_data.setdefault("risk_hints", [])
    recommendation_data["material"] = material_name
    recommendation_data["summary"] = recommendation_data.get("summary") or ""
    recommendation_data["rationale"] = recommendation_data.get("rationale") or recommendation_rationale

    working_memory["material_recommendation"] = recommendation_data
    wm_next = wm.model_copy(update=working_memory)

    return {
        "recommendation": recommendation_data,
        "working_memory": wm_next,
        "phase": PHASE.CONSULTING,
        "last_node": "material_candidate_ranking_node",
    }


def material_exit_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    return {
        "phase": PHASE.CONSULTING,
        "last_node": "material_exit_node",
    }


__all__ = [
    "consulting_supervisor_node",
    "material_requirements_node",
    "material_candidate_generation_node",
    "material_candidate_ranking_node",
    "material_exit_node",
]
