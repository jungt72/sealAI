from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.types import RunnableConfig

from app.core.config import settings
from app.langgraph.state import RwdRequirements, compute_requirements_coverage, missing_requirement_fields
from app.langgraph.types import interrupt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Du extrahierst strukturierte Anforderungen aus dem Gespräch. Antworte immer als JSON mit den Feldern "
    "{requirements, context_hint, fallback_reason}. Wenn dir Informationen fehlen, setze fallback_reason und "
    "formuliere eine freundliche Rückfrage im Feld requirements."
)


def _find_last_user_message(messages: List[BaseMessage]) -> Optional[HumanMessage]:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg
    return None


def _flatten_history(messages: List[BaseMessage]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = getattr(msg, "type", getattr(msg, "role", "unknown"))
        content = getattr(msg, "content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def _use_offline_mode() -> bool:
    forced = os.getenv("LANGGRAPH_USE_FAKE_LLM", "")
    if forced.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    api_key = os.getenv("OPENAI_API_KEY", "").strip().lower()
    return not api_key or api_key in {"dummy", "test"}


def _resolved_requirements(state: Dict[str, Any]) -> RwdRequirements:
    resolved: RwdRequirements = RwdRequirements()
    candidates = [state.get("rwd_requirements"), (state.get("slots") or {}).get("rwd_requirements")]
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key, value in candidate.items():
                if value not in (None, ""):
                    resolved[key] = value  # type: ignore[index]
    return resolved


def _fmt_range(min_value: Any, max_value: Any, unit: str) -> Optional[str]:
    min_txt = _fmt_value(min_value, unit)
    max_txt = _fmt_value(max_value, unit)
    if min_txt and max_txt and min_txt != max_txt:
        return f"{min_txt} – {max_txt}"
    return min_txt or max_txt


def _fmt_value(value: Any, unit: str | None = None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        suffix = f" {unit}" if unit else ""
        return f"{float(value):.3f}".rstrip("0").rstrip(".") + suffix
    text = str(value).strip()
    return f"{text}{f' {unit}' if unit and text else ''}" if text else None


def _offline_analysis(state: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    requirements = _resolved_requirements(state)
    coverage = compute_requirements_coverage(requirements)
    missing = missing_requirement_fields(requirements)

    machine = str(requirements.get("machine") or "").strip()
    application = str(requirements.get("application") or "").strip()
    einbau_parts = [part for part in (machine, application) if part]
    einbausituation = " / ".join(einbau_parts) or user_message.strip() or "Einbausituation noch offen."

    druck_text = None
    if requirements.get("pressure_inner") is not None:
        inner = _fmt_value(requirements.get("pressure_inner"), "bar")
        outer = _fmt_value(requirements.get("pressure_outer"), "bar")
        druck_text = inner or None
        if outer:
            druck_text = f"Innen {inner}, Außen {outer}" if inner else outer

    temperatur_text = _fmt_range(requirements.get("temperature_min"), requirements.get("temperature_max"), "°C")
    drehzahl_text = _fmt_value(requirements.get("speed_rpm"), "rpm")
    medium_text = str(requirements.get("medium") or requirements.get("sealing_goal") or "").strip() or None

    weitere: List[str] = []
    for key, label in (
        ("norms", "Normen"),
        ("target_lifetime", "Ziel-Lebensdauer"),
        ("surface_roughness", "Oberfläche"),
        ("shaft_material", "Wellenmaterial"),
        ("housing_material", "Gehäusematerial"),
    ):
        value = str(requirements.get(key) or "").strip()
        if value:
            weitere.append(f"{label}: {value}")

    offene = [f"{field.replace('_', ' ')} fehlt noch." for field in missing[:4]]
    if not offene:
        offene = ["Bitte bestätige Medium, Temperatur und Druck für die Berechnung."]

    failure = str(requirements.get("failure_modes") or "").strip()
    history = str(requirements.get("history") or "").strip()
    problem = failure or history or (user_message.strip() or "Problem wurde noch nicht beschrieben.")

    confidence = round(min(1.0, 0.25 + coverage * 0.75), 3)

    return {
        "einbausituation": einbausituation,
        "rahmenbedingungen": {
            "druck": druck_text or "nicht genannt",
            "temperatur": temperatur_text or "nicht genannt",
            "drehzahl": drehzahl_text or "nicht genannt",
            "medium": medium_text or "nicht genannt",
            "weitere": weitere,
        },
        "problem": problem,
        "offene_punkte": offene,
        "confidence": confidence,
    }


def _resolve_llm(config: RunnableConfig):
    cfg = (config.get("configurable") or {}) if isinstance(config, dict) else {}
    candidate = cfg.get("bedarfsanalyse_llm")
    if candidate and hasattr(candidate, "invoke"):
        return candidate
    model_name = getattr(settings, "openai_model", "gpt-5-mini")
    return ChatOpenAI(model=model_name, temperature=0.2, streaming=False)


def _build_prompt(state: Dict[str, Any]) -> str:
    messages = list(state.get("messages") or [])
    history = _flatten_history(messages)
    last_user = _find_last_user_message(messages)
    latest = last_user.content if last_user else str(state.get("message_in") or "")
    slots = state.get("slots") or {}
    existing_requirements = slots.get("requirements")

    lines = ["Bitte analysiere folgende Informationen:"]
    if history:
        lines.append("Verlauf:")
        lines.append(history)
    if existing_requirements:
        lines.append(f"Bisherige Anforderungen: {existing_requirements}")
    if latest:
        lines.append(f"Letzte Nutzereingabe: {latest}")
    return "\n".join(lines)


def _offline_payload(state: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    analysis = _offline_analysis(state, user_message)
    rb = analysis["rahmenbedingungen"]
    requirement_lines = [
        f"Einbausituation: {analysis['einbausituation']}",
        f"Problemstellung: {analysis['problem']}",
        f"Rahmenbedingungen: Druck {rb['druck']}, Temperatur {rb['temperatur']}, Drehzahl {rb['drehzahl']}, Medium {rb['medium']}",
        "Weitere Hinweise: " + ("; ".join(rb["weitere"]) or "keine genannt"),
        "Offene Punkte: " + "; ".join(analysis["offene_punkte"]),
    ]
    requirements_text = "\n".join(requirement_lines)
    message = requirements_text + "\n\nGibt es weitere technische Details, die ich kennen sollte?"
    return {
        "requirements": requirements_text,
        "context_hint": analysis["problem"],
        "fallback_reason": "",
        "message": message,
    }


def _normalize_payload(data: Dict[str, Any]) -> Dict[str, str]:
    requirements = str(data.get("requirements") or "").strip()
    context_hint = str(data.get("context_hint") or "").strip()
    fallback_reason = str(data.get("fallback_reason") or "").strip()
    message = str(data.get("message") or requirements or "" ).strip()
    if not message:
        message = "Ich benötige weitere Angaben zur Einbausituation."
    return {
        "requirements": requirements or message,
        "context_hint": context_hint,
        "fallback_reason": fallback_reason,
        "message": message,
    }


def bedarfsanalyse_node(state: Dict[str, Any], *, config: RunnableConfig) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        logger.info("bedarfsanalyse_node: keine Nachrichten vorhanden, breche ab.")
        return {}

    use_offline = _use_offline_mode()
    cfg_payload: Dict[str, Any]
    if use_offline:
        last_user = _find_last_user_message(messages)
        last_text = last_user.content if last_user else str(state.get("message_in") or "")
        cfg_payload = _offline_payload(state, last_text)
    else:
        llm = _resolve_llm(config)
        prompt = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=_build_prompt(state))]
        try:
            response = llm.invoke(prompt)
            raw_text = getattr(response, "content", None)
            raw_text = raw_text if isinstance(raw_text, str) else str(response)
            cfg_payload = json.loads(raw_text)
            if not isinstance(cfg_payload, dict):
                raise ValueError("LLM output is not a JSON object")
        except Exception:
            logger.exception("bedarfsanalyse_node: LLM-Antwort ungültig, nutze Offline-Fallback.")
            last_user = _find_last_user_message(messages)
            last_text = last_user.content if last_user else str(state.get("message_in") or "")
            cfg_payload = _offline_payload(state, last_text)

    normalized = _normalize_payload(cfg_payload)

    slots = dict(state.get("slots") or {})
    meta = dict(state.get("meta") or {})
    slots["requirements"] = normalized["requirements"]
    meta["requirements"] = normalized.get("context_hint") or meta.get("requirements")

    ai_message = AIMessage(content=normalized["message"], additional_kwargs={"phase": "bedarfsanalyse"})
    messages.append(ai_message)

    updates: Dict[str, Any] = {
        "messages": messages,
        "slots": slots,
        "meta": meta,
        "message_out": normalized["message"],
        "msg_type": "msg-bedarfsanalyse",
        "phase": "bedarfsanalyse",
    }

    fallback_reason = normalized.get("fallback_reason") or ""
    if fallback_reason:
        state["message_out"] = normalized["message"]
        state["msg_type"] = "msg-bedarfsanalyse"
        interrupt({"prompt": normalized["message"], "reason": fallback_reason})

    return updates
