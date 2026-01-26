"""Centralized response node for Supervisor-controlled user messages."""

from __future__ import annotations

import os
from typing import Dict, Any, Iterable, List, Tuple

from langchain_core.messages import AIMessage

from app.langgraph_v2.state import Intent, SealAIState, Source, TechnicalParameters, WorkingMemory
from app.langgraph_v2.utils.jinja_renderer import render_template


def _looks_like_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _normalize_sources(raw_sources: Iterable[Source | Dict[str, Any]]) -> List[Source]:
    max_sources = int(os.getenv("MAX_SOURCES", "5"))
    seen: set[Tuple[str, str, str, str]] = set()
    normalized: List[Source] = []

    for item in raw_sources:
        src = item if isinstance(item, Source) else Source.model_validate(item)
        metadata = src.metadata or {}
        url = str(metadata.get("url") or "") or (src.source or "")
        title = str(metadata.get("title") or "") or ""
        page = str(metadata.get("page") or "") or ""
        source_id = str(metadata.get("source_id") or metadata.get("id") or "")

        if not title and not url:
            if src.source and not _looks_like_url(src.source):
                title = src.source
            elif _looks_like_url(src.source or ""):
                url = src.source or ""

        if not title and not url:
            continue

        if source_id:
            key = ("id", source_id, "", "")
        else:
            key = (url, title, page, src.source or "")

        if key in seen:
            continue
        seen.add(key)
        normalized.append(src)
        if len(normalized) >= max_sources:
            break

    return normalized


def _sources_fallback_text() -> str:
    return (
        "Ich kann das aktuell nicht mit belastbaren Quellen aus der Wissensdatenbank belegen. "
        "Bitte nenne die konkrete Norm (z.B. DIN/ISO), lade ein Dokument hoch oder gib Kategorie/Produktdaten an."
    )


def _is_knowledge_intent(intent: Intent | None) -> bool:
    if not intent:
        return False
    key = str(getattr(intent, "key", "") or "")
    if key.startswith("knowledge_") or key == "generic_sealing_qa":
        return True
    return getattr(intent, "knowledge_type", None) in {"material", "lifetime", "norms"}


def _missing_critical_facts(state: SealAIState) -> list[str]:
    params = state.parameters if isinstance(state.parameters, TechnicalParameters) else TechnicalParameters()

    has_temp = any(
        value is not None
        for value in (
            params.temperature_C,
            params.temperature_min,
            params.temperature_max,
            params.T_medium_min,
            params.T_medium_max,
        )
    )
    has_pressure = any(value is not None for value in (params.pressure_bar, params.p_max, params.p_min))
    has_rpm = any(value is not None for value in (params.speed_rpm, params.n_max, params.n_min))
    has_medium = any(value for value in (params.medium, params.medium_type))
    has_shaft = any(value is not None for value in (params.shaft_diameter, params.d_shaft_nominal))
    has_housing = any(
        value is not None for value in (params.housing_diameter, params.d_bore_nominal, params.bore_diameter)
    )

    missing: list[str] = []
    if not has_temp:
        missing.append("temperature")
    if not has_pressure:
        missing.append("pressure")
    if not has_rpm:
        missing.append("rpm")
    if not has_medium:
        missing.append("medium")
    if not has_shaft:
        missing.append("shaft_diameter")
    if not has_housing:
        missing.append("housing_bore")
    return missing


def _build_clarifying_questions(missing: list[str]) -> list[str]:
    questions = {
        "temperature": "Welche Temperatur (°C) liegt an der Dichtung an?",
        "pressure": "Welcher Druck (bar) liegt an?",
        "rpm": "Welche Drehzahl (U/min) hat die Welle?",
        "medium": "Welches Medium wird abgedichtet (z.B. Motoröl, Getriebeöl, Wasser, Chemikalie)?",
        "shaft_diameter": "Welchen Wellendurchmesser (mm) hat die Welle?",
        "housing_bore": "Welchen Gehäusebohrungs-Durchmesser (mm) hat die Aufnahme?",
    }
    ordered = ["temperature", "pressure", "rpm", "medium", "shaft_diameter", "housing_bore"]
    picked: list[str] = []
    for key in ordered:
        if key in missing:
            picked.append(questions[key])
        if len(picked) >= 4:
            break
    return picked


def response_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, object]:
    """
    Single point that turns structured state into a user-facing message.

    Responsibility:
    - select appropriate template based on response_kind/ask_missing/knowledge/error
    - append exactly one AIMessage
    - set final_text
    """
    wm: WorkingMemory = state.working_memory or WorkingMemory()
    ask_missing = state.ask_missing_request
    context = {
        "ask_missing_request": ask_missing,
        "response_kind": wm.response_kind,
        "response_text": wm.response_text,
        "knowledge_material": wm.knowledge_material,
        "knowledge_lifetime": wm.knowledge_lifetime,
        "knowledge_generic": wm.knowledge_generic,
        "error": state.error,
        "phase": state.phase or "final",
    }

    text = render_template("response_router.j2", context)
    clarify_missing = _missing_critical_facts(state)
    wants_clarify = (
        getattr(state.intent, "goal", None) == "design_recommendation"
        and not _is_knowledge_intent(state.intent)
        and bool(clarify_missing)
        and int(getattr(state, "clarify_round_count", 0) or 0) < 1
    )
    if wants_clarify:
        questions = _build_clarifying_questions(clarify_missing)
        if questions:
            block = "Kurzfragen:\n" + "\n".join(f"- {q}" for q in questions)
            text = f"{text}\n\n{block}"
    sources = list(state.sources or [])
    normalized_sources: List[Source] = []

    if getattr(state, "needs_sources", False):
        normalized_sources = _normalize_sources(sources)
        if getattr(state, "sources_status", None) == "missing" or not normalized_sources:
            text = f"{text}\n\n{_sources_fallback_text()}"
            normalized_sources = []
    messages = list(state.messages or [])
    messages.append(AIMessage(content=[{"type": "text", "text": text}]))

    output_sources: List[Source] = sources
    if getattr(state, "needs_sources", False):
        output_sources = normalized_sources

    patch: Dict[str, object] = {
        "messages": messages,
        "phase": state.phase or "final",
        "last_node": "response_node",
        "final_text": text,
        "sources": output_sources,
    }
    if wants_clarify:
        patch["clarify_round_count"] = 1
        patch["clarify_missing_facts"] = clarify_missing
    return patch


__all__ = [
    "response_node",
    "_normalize_sources",
    "_sources_fallback_text",
    "_missing_critical_facts",
    "_build_clarifying_questions",
]
