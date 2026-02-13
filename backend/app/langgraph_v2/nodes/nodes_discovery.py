from __future__ import annotations
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.prompts.registry import PromptRegistry
from app.prompts.contexts import CollaborativeExtractionContext
# backend/app/langgraph_v2/nodes/nodes_discovery.py
"""Discovery layer nodes for LangGraph v2."""


import re

from typing import Dict, List, Optional

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage  # nur für Typing, keine direkte Nutzung
from langchain_openai import ChatOpenAI

from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, TechnicalParameters, WorkingMemory
from app.langgraph_v2.tools.parameter_tools import set_parameters
from app.langgraph_v2.utils.jinja_renderer import render_template
from app.langgraph_v2.utils.json_sanitizer import extract_json_obj
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance

logger = structlog.get_logger("langgraph_v2.nodes_discovery")


def _ui_state_payload(state: SealAIState, step: str, label: str) -> Dict[str, object]:
    ui_state = dict(state.ui_state or {})
    ui_state.update({"current_step": step, "current_label": label})
    return {"ui_state": ui_state}


def _extract_number(text: str, key: str) -> Optional[float]:
    pattern = re.compile(rf"{key}\s*[:=]\s*([\d\.]+)", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _has_pressure(params: Dict[str, object]) -> bool:
    for key in ("pressure_bar", "pressure", "pressure_max", "pressure_min", "p_max", "p_min"):
        if params.get(key) not in (None, ""):
            return True
    return False


def _has_temperature(params: Dict[str, object]) -> bool:
    for key in (
        "temperature_C",
        "temperature_max",
        "temperature_min",
        "temp_max",
        "temp_min",
        "T_medium_max",
        "T_medium_min",
    ):
        if params.get(key) not in (None, ""):
            return True
    return False


def _has_medium(params: Dict[str, object]) -> bool:
    for key in ("medium", "medium_type"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _has_application(state: SealAIState, params: Dict[str, object]) -> bool:
    if isinstance(getattr(state, "application_category", None), str) and state.application_category.strip():
        return True
    if isinstance(getattr(state, "use_case_raw", None), str) and state.use_case_raw.strip():
        return True
    value = params.get("application_type")
    return isinstance(value, str) and value.strip() != ""


def _strict_missing_fields(state: SealAIState, params: Dict[str, object]) -> List[str]:
    missing: List[str] = []
    if not _has_pressure(params):
        missing.append("pressure_bar")
    if not _has_temperature(params):
        missing.append("temperature_C")
    if not _has_medium(params):
        missing.append("medium")
    if not _has_application(state, params):
        missing.append("application_type")
    return missing


def _is_information_request(user_text: str) -> bool:
    text = (user_text or "").lower()
    info_markers = (
        "information",
        "informationen",
        "erkläre",
        "erklaere",
        "was ist",
        "eigenschaft",
        "stichpunkt",
        "vergleich",
    )
    design_markers = (
        "auslegen",
        "auslegung",
        "empfehlen",
        "empfehlung",
        "welche dichtung",
        "dimension",
        "auswahl",
        "din 3760",
    )
    return any(marker in text for marker in info_markers) and not any(
        marker in text for marker in design_markers
    )


def _get_intent_goal(state: SealAIState) -> str:
    intent = getattr(state, "intent", None)
    if isinstance(intent, dict):
        goal = intent.get("goal", "")
    else:
        goal = getattr(intent, "goal", "")
    return str(goal or "").lower()


def _should_skip_strict_missing_gate(state: SealAIState, user_text: str) -> bool:
    goal = _get_intent_goal(state)
    if goal in {"explanation_or_comparison", "generic_qa", "knowledge_only"}:
        return True
    return _is_information_request(user_text)


def frontdoor_discovery_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Einstieg: Discovery / Smalltalk, aber OHNE sichtbare Chat-Nachricht.

    - Liest die letzte User-Message
    - Fragt ein kleines Nano-Modell nach einer internen Kurz-Zusammenfassung
    - Extrahiert ggf. einfache numerische Parameter aus dem Freitext
    - Schreibt NUR ins WorkingMemory + ui_state, NICHT in `messages`
    """
    user_text = latest_user_text(state.get("messages"))

    # --- Parameter Extraction via Tool (Standardized) ---
    # Wir nutzen ein Tool-fähiges Modell (z.B. mini/fast), um Parameter sauber zu extrahieren.
    # Das ist robuster als Regex für Felder wie "Wellendurchmesser".
    
    try:
        extract_model = ChatOpenAI(
            model=get_model_tier("fast"), 
            temperature=0, 
            streaming=False
        )
        extract_model_bound = extract_model.bind_tools([set_parameters])
        
        extract_sys = (
            "Du bist ein Experte für Dichtungstechnik. "
            "Extrahiere alle technischen Parameter (Druck, Temperatur, Medium, Anwendung/Applikation, Durchmesser, Drehzahl) "
            "aus der Eingabe. Nutze dazu das Tool 'set_parameters'. "
            "Wenn keine neuen Werte genannt werden, rufe das Tool nicht auf."
        )
        
        # Invoke model
        tool_res = extract_model_bound.invoke([
            SystemMessage(content=extract_sys), 
            HumanMessage(content=user_text)
        ])
        
        tool_params = {}
        if tool_res.tool_calls:
            for tc in tool_res.tool_calls:
                if tc["name"] == "set_parameters":
                    # args sind bereits ein dict
                    tool_params.update(tc["args"])
                    logger.info("tool_extraction_success", tool_args=tc["args"])

    except Exception as e:
        logger.error("tool_extraction_failed", error=str(e))
        tool_params = {}

    # Fallback / Ergänzung: Regex (optional, falls Tool versagt oder für einfache Checks)
    regex_params = extract_parameters_from_text(user_text)
    
    # Merge: Tool > Regex > Existing
    extracted_params = {**regex_params, **tool_params}

    
    # Merge with existing parameters
    existing_params = state.parameters.as_dict() if state.parameters else {}
    logger.info("frontdoor_before_merge", old_parameters=existing_params, extracted_params=extracted_params)
    merged_params, merged_provenance = apply_parameter_patch_with_provenance(
        existing_params,
        extracted_params,
        state.parameter_provenance,
        source="user",
    )
    logger.info("frontdoor_after_merge", merged_parameters=merged_params)


    # Strict intake: only gate technical design/recommendation requests.
    missing_core = []
    if not _should_skip_strict_missing_gate(state, user_text):
        missing_core = _strict_missing_fields(state, merged_params)
    if missing_core:
        # PLATINUM REFACTOR: Strict Extraction via Registry
        registry = PromptRegistry()
        params_summary = ", ".join(f"{k}={v}" for k,v in (state.parameters.as_dict() if state.parameters else {}).items() if v)
        
        ctx = CollaborativeExtractionContext(
            trace_id=state.run_id or "unknown",
            session_id=state.thread_id or "unknown",
            language="de",
            missing_params_grouped=format_missing_params(missing_core),
            known_params_summary=params_summary,
            questions_asked_count=len(state.messages or []) // 2
        )
        
        prompt_content, fingerprint, version = registry.render("extraction/request_v1", ctx.to_dict())
        
        question = run_llm(
             model=get_model_tier("nano"),
             prompt=prompt_content,
             system="Du bist ein hilfreicher Vertriebsingenieur.",
             temperature=0.5,
             metadata={
                "prompt_id_used": "extraction/request",
                "prompt_fingerprint": fingerprint,
                "prompt_version": version
            }
        )
        
        ask_missing_request = AskMissingRequest(missing_fields=missing_core, question=question)
        wm = state.working_memory or WorkingMemory()
        try:
            wm = wm.model_copy(update={"response_text": question, "response_kind": "ask_missing"})
        except Exception:
            pass
            
        return {
            "ask_missing_request": ask_missing_request,
            "ask_missing_scope": "discovery",
            "awaiting_user_input": True,
            "missing_params": missing_core,
            "discovery_missing": missing_core,
            "phase": PHASE.INTENT,
            "last_node": "confirm_gate_node",
            "working_memory": wm,
            "prompt_id_used": "extraction/request",
            "prompt_fingerprint": fingerprint,
            "prompt_version_used": version,
            **_ui_state_payload(
                state,
                "discovery",
                "Es fehlen Basisparameter. Bitte ergänzen.",
            ),
        }




def discovery_summarize_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    "Zusammenfassung der bisherigen Parameter für die Coverage-Berechnung."
    
    # Check coverage only if we have params
    params = state.parameters
    if not params:
        return {"discovery_coverage": 0.0, "discovery_missing": ["pressure_bar", "temperature_C", "medium"]}
        
    # Wir nutzen ein Template zur Bewertung
    summary_source = state.working_memory.summary_clean if state.working_memory else ""
    
    context = {
        "summary_source": summary_source, 
        "params": params.as_dict()
    }
    
    # Legacy render (safe to keep for summarization or strictly update? User said "dead code extraction". 
    # But this is logic. We keep it for now to restore function.)
    # Wait, Step 971 log showed usage of render_template("discovery_summarize.j2").
    # For restoration, we assume we need to import render_template or it is already imported.
    # It is imported.
    
    full_text = render_template("discovery_summarize.j2", context)
    
    # Simple parsing of result
    # "SUMMARY: ... COVERAGE: 0.X MISSING: a,b,c"
    summary = ""
    coverage = 0.0
    missing = []
    
    # Mock/Simple logic for restoration if we don't have full body.
    # BETTER: We use the logic from Step 971 log strictly.
    
    # Re-reading Step 971 Output for discovery_summarize_node...
    # It called run_llm.
    
    prompt = full_text
    response = run_llm(
        model=get_model_tier("nano"),
        prompt=prompt,
        system="Du bist ein Analyst.",
        temperature=0.0,
        metadata={"node": "discovery_summarize_node"}
    )
    
    # Parse Extractor
    data, _ = extract_json_obj(response, default={})
    
    summary = data.get("summary")
    try:
        coverage = float(data.get("coverage") or 0.0)
    except (TypeError, ValueError):
        coverage = 0.0
    raw_missing = data.get("missing") or []
    missing = []
    if isinstance(raw_missing, list):
        missing = [str(item).strip() for item in raw_missing if str(item).strip()]
    elif raw_missing:
        missing = [str(raw_missing).strip()]

    wk = state.working_memory or WorkingMemory()
    wk_update = {
        "summary_clean": summary or summary_source or "",
        "coverage_notes": coverage,
    }
    try:
        wk = wk.model_copy(update=wk_update)
    except Exception:
        pass

    logger.info(
        "discovery_summarize_node_exit",
        run_id=state.run_id,
        thread_id=state.thread_id,
        coverage=coverage,
        missing=missing,
    )

    return {
        "discovery_summary": summary or None,
        "discovery_coverage": max(0.0, min(1.0, coverage)),
        "discovery_missing": missing[:3] or [],
        "working_memory": wk,
        "phase": PHASE.ENTRY,
        "last_node": "discovery_summarize_node",
        **_ui_state_payload(
            state,
            "discovery",
            "Ich prüfe, ob alle relevanten Informationen vorliegen.",
        ),
    }

def format_missing_params(missing: List[str]) -> str:
    labels = {
        "pressure_bar": "Druck (bar)",
        "temperature_C": "Temperatur (C)",
        "medium": "Medium",
        "application_type": "Anwendung",
        "speed_rpm": "Drehzahl",
        "shaft_diameter": "Wellen-Durchmesser"
    }
    return ", ".join(labels.get(k, k) for k in missing)



def confirm_gate_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    "Entscheidet, ob noch Infos fehlen und baut ggf. eine Ask-Missing-Anfrage."
    model = get_model_tier("nano")
    summary = (state.get("discovery_summary") or "").strip()
    coverage = state.get("discovery_coverage") or 0.0
    missing = state.get("discovery_missing") or []

    user_text = latest_user_text(state.get("messages"))
    skip_strict_missing_gate = _should_skip_strict_missing_gate(state, user_text)
    params_dict = state.parameters.as_dict() if state.parameters else {}
    missing_core = []
    if not skip_strict_missing_gate:
        missing_core = list(state.missing_params or []) or _strict_missing_fields(state, params_dict)

    if missing_core:
        # PLATINUM REFACTOR: Strict Extraction via Registry
        registry = PromptRegistry()
        params_summary = ", ".join(f"{k}={v}" for k,v in (state.parameters.as_dict() if state.parameters else {}).items() if v)
        
        ctx = CollaborativeExtractionContext(
            trace_id=state.run_id or "unknown",
            session_id=state.thread_id or "unknown",
            language="de",
            missing_params_grouped=format_missing_params(missing_core),
            known_params_summary=params_summary,
            questions_asked_count=len(state.messages or []) // 2
        )
        
        prompt_content, fingerprint, version = registry.render("extraction/request_v1", ctx.to_dict())
        
        question = run_llm(
             model=get_model_tier("nano"),
             prompt=prompt_content,
             system="Du bist ein hilfreicher Vertriebsingenieur.",
             temperature=0.5,
             metadata={
                "prompt_id_used": "extraction/request",
                "prompt_fingerprint": fingerprint,
                "prompt_version": version
            }
        )
        
        ask_missing_request = AskMissingRequest(missing_fields=missing_core, question=question)
        wm = state.working_memory or WorkingMemory()
        try:
            wm = wm.model_copy(update={"response_text": question, "response_kind": "ask_missing"})
        except Exception:
            pass
            
        return {
            "ask_missing_request": ask_missing_request,
            "ask_missing_scope": "discovery",
            "awaiting_user_input": True,
            "missing_params": missing_core,
            "discovery_missing": missing_core,
            "phase": PHASE.INTENT,
            "last_node": "confirm_gate_node",
            "working_memory": wm,
            "prompt_id_used": "extraction/request",
            "prompt_fingerprint": fingerprint,
            "prompt_version_used": version,
            **_ui_state_payload(
                state,
                "discovery",
                "Es fehlen Basisparameter. Bitte ergänzen.",
            ),
        }


    try:
        coverage = float(coverage)
    except (TypeError, ValueError):
        coverage = 0.0
    coverage = max(0.0, min(1.0, coverage))
    missing_text = "; ".join(str(item) for item in missing) if missing else "-"

    context = {
        "summary": summary,
        "coverage": coverage,
        "missing_text": missing_text,
    }
    
    full_text = render_template("confirm_gate.j2", context)
    parts = full_text.split("---", 1)
    if len(parts) == 2:
        system = parts[0].strip()
        prompt = parts[1].strip()
    else:
        system = "Du bist ein technischer Berater für Dichtungstechnik."
        prompt = full_text.strip()

    reply_text = run_llm(
        model=model,
        prompt=prompt,
        system=system,
        temperature=0.45,
        max_tokens=280,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "confirm_gate_node",
        },
    )

    ask_missing_request: AskMissingRequest | None = None
    ask_missing_scope = None

    # Nur wenn Coverage < 0.85 wirklich eine Ask-Missing-Runde starten    # PLATINUM REFACTOR: Collaborative Extraction
    if (not skip_strict_missing_gate) and coverage < 0.85:
        registry = PromptRegistry()
        params_summary = ", ".join(f"{k}={v}" for k,v in (state.parameters.as_dict() if state.parameters else {}).items() if v)
        
        ctx = CollaborativeExtractionContext(
            trace_id=state.run_id or "unknown",
            session_id=state.thread_id or "unknown",
            language="de",
            missing_params_grouped=format_missing_params(missing),
            known_params_summary=params_summary,
            questions_asked_count=len(state.messages or []) // 2
        )
        
        prompt_content, fingerprint, version = registry.render("extraction/request_v1", ctx.to_dict())
        
        question = run_llm(
            model=get_model_tier("nano"),
            prompt=prompt_content, 
            system="Du bist ein hilfreicher Vertriebsingenieur.", 
            temperature=0.7,
            metadata={
                "prompt_id_used": "extraction/request",
                "prompt_fingerprint": fingerprint,
                "prompt_version": version
            }
        )
        
        ask_missing_request = AskMissingRequest(
            missing_fields=missing,
            question=question,
        )
        ask_missing_scope = "discovery"
        trace_updates = {"prompt_id_used": "extraction/request", "prompt_fingerprint": fingerprint, "prompt_version_used": version} 

    wm = state.working_memory or WorkingMemory()
    try:
        wm = wm.model_copy(
            update={
                "response_text": reply_text,
                "response_kind": "confirm_gate",
                "coverage_summary": summary,
            }
        )
    except Exception:
        pass

    raw_intent = state.intent or {}
    if isinstance(raw_intent, dict):
        intent = dict(raw_intent)
    else:
        try:
            intent = dict(raw_intent)
        except Exception:
            intent = {}
    if not intent.get("goal"):
        intent["goal"] = "generic_qa" if skip_strict_missing_gate else "design_recommendation"

    patch: Dict[str, object] = {
        **(trace_updates if "trace_updates" in locals() else {}),
        "ask_missing_request": ask_missing_request,
        "ask_missing_scope": ask_missing_scope,
        "awaiting_user_input": bool(ask_missing_request),
        "phase": PHASE.INTENT,
        "last_node": "confirm_gate_node",
        "working_memory": wm,
        "intent": intent,
        **_ui_state_payload(
            state,
            "discovery",
            "Einige Details fehlen noch." if missing else "Alles klar, ich ordne den Intent ein.",
        ),
    }
    if skip_strict_missing_gate:
        patch.update(
            {
                "ask_missing_request": None,
                "ask_missing_scope": None,
                "awaiting_user_input": False,
                "missing_params": [],
                "discovery_missing": [],
            }
        )
    return patch


def discovery_intake_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Alias: aktueller Entry-Point für Discovery."""
    return frontdoor_discovery_node(state, *_args, **_kwargs)


__all__ = [
    "discovery_intake_node",
    "frontdoor_discovery_node",
    "discovery_summarize_node",
    "confirm_gate_node",
]
