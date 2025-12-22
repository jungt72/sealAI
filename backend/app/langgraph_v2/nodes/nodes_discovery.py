# backend/app/langgraph_v2/nodes/nodes_discovery.py
"""Discovery layer nodes for LangGraph v2."""

from __future__ import annotations

import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.langgraph_v2.tools.parameter_tools import set_parameters
from app.langgraph_v2.utils.llm_factory import get_model_tier

from typing import Dict, List, Optional

import structlog

from langchain_core.messages import BaseMessage  # nur für Typing, keine direkte Nutzung

from app.langgraph.io import AskMissingRequest
from app.langgraph_v2.constants import MODEL_NANO
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.json_sanitizer import extract_json_obj
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text

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


def frontdoor_discovery_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Einstieg: Discovery / Smalltalk, aber OHNE sichtbare Chat-Nachricht.

    - Liest die letzte User-Message
    - Fragt ein kleines Nano-Modell nach einer internen Kurz-Zusammenfassung
    - Extrahiert ggf. einfache numerische Parameter aus dem Freitext
    - Schreibt NUR ins WorkingMemory + ui_state, NICHT in `messages`
    """
    user_text = latest_user_text(state.get("messages"))
    prompt = (
        "Du bist ein präziser Discovery-Agent für SealAI. "
        "Verstehe, worum es dem Nutzer geht, erkenne drei technische Stichworte "
        "und gib eine kurze, freundliche Zusammenfassung (max. zwei Sätze). "
        "Die Antwort wird NUR intern verwendet, nicht direkt angezeigt."
    )
    model = get_model_tier("nano")

    try:
        greeting = run_llm(
            model=model,
            prompt=user_text,
            system=prompt,
            temperature=0.3,
            max_tokens=220,
            metadata={
                "run_id": state.run_id,
                "thread_id": state.thread_id,
                "user_id": state.user_id,
                "node": "frontdoor_discovery_node",
            },
        )
    except Exception:
        # Fallback: nur interner Text, wird nicht direkt angezeigt
        greeting = (
            "Interne Kurz-Zusammenfassung des Nutzeranliegens. "
            "Dieser Text ist nur für die interne Discovery gedacht."
        )

    
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
            "Extrahiere alle technischen Parameter (Druck, Temperatur, Durchmesser, Drehzahl, Medium) aus der Eingabe. "
            "Nutze dazu das Tool 'set_parameters'. Wenn keine neuen Werte genannt werden, rufe das Tool nicht auf."
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
    parameters = dict(state.parameters or {})
    logger.info("frontdoor_before_merge", old_parameters=parameters, extracted_params=extracted_params)
    parameters.update(extracted_params)
    logger.info("frontdoor_after_merge", merged_parameters=parameters)


    # WorkingMemory um interne Discovery-Infos erweitern (bleibt „unsichtbar“ für den User)
    wm = state.working_memory or WorkingMemory()
    try:
        wm = wm.model_copy(
            update={
                "summary_raw": greeting,
            }
        )
    except Exception:
        # Falls das Modell die Felder nicht kennt (extra=ignore/forbid), ignorieren wir das still.
        pass

    return {
        # KEINE messages-Änderung -> keine zusätzliche Chat-Bubble
        "working_memory": wm,
        "parameters": parameters,
        "phase": PHASE.ENTRY,
        "last_node": "frontdoor_discovery_node",
        **_ui_state_payload(
            state,
            "discovery",
            "Ich versuche Ihr Anliegen und den Kontext zu verstehen.",
        ),
    }


def discovery_summarize_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Fasst die Discovery-Informationen zusammen und schätzt Coverage/Missing ein."""
    wk = state.working_memory or WorkingMemory()

    # Wenn summary_raw aus der Frontdoor-Discovery existiert, nutze sie,
    # sonst direkt den letzten User-Text.
    summary_source = getattr(wk, "summary_raw", None) or latest_user_text(
        state.get("messages")
    )

    model = get_model_tier("nano")
    system = render_template("discovery_summarize.j2", {})
    reply_text = run_llm(
        model=model,
        prompt=summary_source or "",
        system=system,
        temperature=0.35,
        max_tokens=260,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "discovery_summarize_node",
        },
    )
    data, ok = extract_json_obj(reply_text, default={})
    summary = str(data.get("summary") or "").strip()
    try:
        coverage = float(data.get("coverage") or 0.0)
    except (TypeError, ValueError):
        coverage = 0.0
    raw_missing = data.get("missing") or []
    missing: List[str] = []
    if isinstance(raw_missing, list):
        missing = [str(item).strip() for item in raw_missing if str(item).strip()]
    elif raw_missing:
        missing = [str(raw_missing).strip()]

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


def confirm_gate_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Entscheidet, ob noch Infos fehlen und baut ggf. eine Ask-Missing-Anfrage."""
    model = get_model_tier("nano")
    summary = (state.get("discovery_summary") or "").strip()
    coverage = state.get("discovery_coverage") or 0.0
    missing = state.get("discovery_missing") or []

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

    # Nur wenn Coverage < 0.85 wirklich eine Ask-Missing-Runde starten
    if coverage < 0.85:
        question = (
            "Ich benötige noch ein paar Details zu Ihrem Anwendungsfall, um präzise weiterarbeiten zu können. "
            f"Fehlende Werte: {missing_text}."
        )
        ask_missing_request = AskMissingRequest(
            missing_fields=missing,
            question=question,
        )
        ask_missing_scope = "discovery"

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

    intent = dict(state.intent or {})
    if not intent.get("goal"):
        intent["goal"] = "design_recommendation"

    return {
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


def discovery_intake_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """Alias: aktueller Entry-Point für Discovery."""
    return frontdoor_discovery_node(state, *_args, **_kwargs)


__all__ = [
    "discovery_intake_node",
    "frontdoor_discovery_node",
    "discovery_summarize_node",
    "confirm_gate_node",
]
