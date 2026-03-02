from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.llm_factory import LazyChatOpenAI, get_model_tier

_WIZARD_LLM: Any | None = None


def _extract_langgraph_config(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Any | None:
    config = kwargs.get("config")
    if config is not None:
        return config
    if args:
        candidate = args[0]
        if isinstance(candidate, dict):
            return candidate
    return None


def _chunk_to_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if text is not None:
                    parts.append(str(text))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content or "")


def _response_to_text(response: Any) -> str:
    return _chunk_to_text(response).strip()


def _get_wizard_llm(model_name: str) -> Any:
    global _WIZARD_LLM
    if _WIZARD_LLM is None:
        _WIZARD_LLM = LazyChatOpenAI(
            model=model_name,
            temperature=0,
            cache=False,
            max_tokens=520,
            streaming=False,
        )
    return _WIZARD_LLM


def _coerce_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _merge_diagnostic_data(state: SealAIState, extracted: Dict[str, Any]) -> Dict[str, Any]:
    merged = _coerce_dict(getattr(state, "diagnostic_data", None))
    wm = state.working_memory or WorkingMemory()
    merged.update(_coerce_dict(getattr(wm, "diagnostic_data", None)))
    for key, value in extracted.items():
        if value is not None and str(value).strip():
            merged[key] = value

    params = getattr(state, "parameters", None)
    if params is not None:
        medium = getattr(params, "medium", None)
        if medium:
            merged.setdefault("medium", medium)
        temp = getattr(params, "temperature_C", None)
        if temp is not None:
            merged.setdefault("temperature_C", temp)
        pressure = getattr(params, "pressure_bar", None)
        if pressure is not None:
            merged.setdefault("pressure_bar", pressure)
    return merged


def _missing_dimensions(diagnostic_data: Dict[str, Any]) -> List[str]:
    missing: List[str] = []

    if not str(diagnostic_data.get("leak_location") or "").strip():
        missing.append("location")

    if not str(diagnostic_data.get("damage_pattern") or "").strip():
        missing.append("pattern")

    has_medium = bool(str(diagnostic_data.get("medium") or "").strip())
    has_temp = diagnostic_data.get("temperature_C") is not None or bool(
        str(diagnostic_data.get("temperature_note") or "").strip()
    )
    has_pressure = diagnostic_data.get("pressure_bar") is not None or bool(
        str(diagnostic_data.get("pressure_note") or "").strip()
    )
    if not (has_medium or has_temp or has_pressure):
        missing.append("context")

    return missing


def _default_question_for_dimension(dimension: str) -> str:
    if dimension == "location":
        return "Um die Ursache sauber einzugrenzen: Wo tritt die Leckage genau auf (statisch, dynamisch, Flansch, Welle)?"
    if dimension == "pattern":
        return (
            "Um die Ursache genau einzugrenzen: Sieht die Dichtung eher verbrannt/verkohlt aus "
            "oder ist sie mechanisch eingerissen, versprödet oder aufgequollen?"
        )
    return "Damit ich die Ursache belastbar bewerten kann: Kennen Sie Medium sowie Temperatur- oder Druckbereich im Betrieb?"


def _fallback_summary(diagnostic_data: Dict[str, Any]) -> str:
    location = diagnostic_data.get("leak_location") or "nicht spezifiziert"
    pattern = diagnostic_data.get("damage_pattern") or "nicht spezifiziert"
    medium = diagnostic_data.get("medium") or "nicht spezifiziert"
    temp = diagnostic_data.get("temperature_C")
    pressure = diagnostic_data.get("pressure_bar")
    temp_text = f"{temp} °C" if temp is not None else str(diagnostic_data.get("temperature_note") or "nicht spezifiziert")
    pressure_text = f"{pressure} bar" if pressure is not None else str(diagnostic_data.get("pressure_note") or "nicht spezifiziert")
    return (
        "Zusammenfassung der Diagnosebasis: "
        f"Leckage-Ort: {location}; Schadensbild: {pattern}; "
        f"Medium: {medium}; Temperatur: {temp_text}; Druck: {pressure_text}."
    )


async def troubleshooting_wizard_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    config = _extract_langgraph_config(_args, _kwargs)
    existing_data = _coerce_dict(getattr(state, "diagnostic_data", None))

    history_lines: List[str] = []
    for msg in list(state.messages or [])[-12:]:
        role = "assistant"
        if isinstance(msg, HumanMessage):
            role = "user"
        elif isinstance(msg, SystemMessage):
            role = "system"

        content = getattr(msg, "content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    part_text = item.get("text")
                    if part_text is not None:
                        parts.append(str(part_text))
                elif isinstance(item, str):
                    parts.append(item)
            text = "".join(parts)
        else:
            text = str(content or "")
        if text.strip():
            history_lines.append(f"{role}: {text.strip()}")

    transcript = "\n".join(history_lines) if history_lines else ""
    model_name = get_model_tier("mini")
    llm = _get_wizard_llm(model_name)
    system_prompt = (
        "Du bist SealAI-Diagnoseexperte fuer Dichtungsausfaelle. "
        "Analysiere den Dialog und extrahiere Diagnoseinformationen praezise. "
        "Antworte ausnahmslos auf Deutsch, auch bei englischen Feldnamen oder technischen JSON-Schluesseln. "
        "Liefere IMMER gueltiges JSON ohne Markdown mit diesem Schema: "
        '{"extracted":{"leak_location":"", "damage_pattern":"", "medium":"", '
        '"temperature_note":"", "pressure_note":""}, '
        '"missing_dimensions":["location|pattern|context"], '
        '"next_question":"", "summary":""}. '
        "Waehle bei fehlenden Informationen genau EINE konkrete empathische Rueckfrage auf Deutsch. "
        "Falls alle drei Dimensionen belegt sind (location, pattern, context), setze next_question leer und schreibe eine kurze summary."
    )
    user_prompt = (
        f"Bisher bekannte Diagnosedaten: {json.dumps(existing_data, ensure_ascii=False)}\n"
        f"Chatverlauf:\n{transcript}\n"
        "Pruefe fehlende Dimensionen (location, pattern, context) und antworte nur als JSON."
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    raw = ""
    if hasattr(llm, "ainvoke"):
        try:
            response = await llm.ainvoke(messages, config=config)
            raw = _response_to_text(response)
        except Exception:
            raw = ""
    if not raw:
        chunks: List[str] = []
        async for chunk in llm.astream(messages, config=config):
            text = _chunk_to_text(chunk)
            if text:
                chunks.append(text)
        raw = "".join(chunks).strip()
    parsed: Dict[str, Any] = {}
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {}

    extracted = _coerce_dict(parsed.get("extracted"))
    merged_data = _merge_diagnostic_data(state, extracted)

    missing = parsed.get("missing_dimensions")
    if not isinstance(missing, list) or not missing:
        missing = _missing_dimensions(merged_data)
    missing = [str(item).strip().lower() for item in missing if str(item).strip()]

    next_question = str(parsed.get("next_question") or "").strip()
    if missing:
        if not next_question:
            next_question = _default_question_for_dimension(missing[0])
        final_text = next_question
        diagnostic_complete = False
    else:
        summary = str(parsed.get("summary") or "").strip()
        final_text = summary or _fallback_summary(merged_data)
        diagnostic_complete = True

    updated_messages = list(state.messages or [])
    updated_messages.append(AIMessage(content=[{"type": "text", "text": final_text}]))

    wm_raw = state.working_memory or WorkingMemory()
    if isinstance(wm_raw, WorkingMemory):
        wm = wm_raw
    elif isinstance(wm_raw, dict):
        wm = WorkingMemory.model_validate(wm_raw)
    else:
        wm = WorkingMemory.model_validate(getattr(wm_raw, "__dict__", {}))
    wm_update = wm.model_copy(update={"diagnostic_data": merged_data})

    return {
        "messages": updated_messages,
        "diagnostic_data": merged_data,
        "diagnostic_complete": diagnostic_complete,
        "working_memory": wm_update,
        "final_text": final_text,
        "phase": PHASE.CONSULTING,
        "last_node": "troubleshooting_wizard_node",
    }


__all__ = ["troubleshooting_wizard_node"]
