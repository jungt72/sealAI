from __future__ import annotations

from typing import Any, Dict, List
import json
import re
import structlog

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.llm_factory import LazyChatOpenAI, get_model_tier
from app.langgraph_v2.utils.messages import latest_user_text

logger = structlog.get_logger("langgraph_v2.conversational_rag")
_FALLBACK_TEXT = (
    "Ich habe allgemeine Informationen zu PTFE-Dichtungen gefunden, benötige aber für eine präzise "
    "Auslegung Ihres Rührwerks noch folgende Daten: Material/Handelsname, Medium, Temperatur und Druck."
)
_NO_DOCS_TEXT = "Ich konnte keine passenden Dokumente in der Wissensdatenbank finden."
_RAG_LLM: Any | None = None


def _extract_rag_context(state: SealAIState) -> str:
    panel_material = {}
    if state.working_memory and isinstance(state.working_memory.panel_material, dict):
        panel_material = state.working_memory.panel_material
    rag_context = str(panel_material.get("rag_context") or "").strip()
    if rag_context:
        return rag_context
    return str(state.context or "").strip()


def _extract_langgraph_config(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Any | None:
    config = kwargs.get("config")
    if config is not None:
        return config
    if args:
        candidate = args[0]
        if isinstance(candidate, dict):
            return candidate
    return None


def _extract_live_calc_tile(state: SealAIState) -> Dict[str, Any]:
    raw = getattr(state, "live_calc_tile", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    model_dump = getattr(raw, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    return {}


def _build_profile_snapshot(state: SealAIState) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    working_profile = getattr(state, "working_profile", None)
    model_dump = getattr(working_profile, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            snapshot.update(dumped)

    params = getattr(state, "parameters", None)
    as_dict = getattr(params, "as_dict", None)
    if callable(as_dict):
        for key, value in (as_dict() or {}).items():
            if value is not None:
                snapshot.setdefault(key, value)
    elif isinstance(params, dict):
        for key, value in params.items():
            if value is not None:
                snapshot.setdefault(key, value)

    extracted = getattr(state, "extracted_params", None)
    if isinstance(extracted, dict):
        for key, value in extracted.items():
            if value is not None:
                snapshot.setdefault(key, value)

    # Canonical aliases used by downstream prompts and checks.
    if snapshot.get("speed_rpm") is None and snapshot.get("rpm") is not None:
        snapshot["speed_rpm"] = snapshot.get("rpm")
    if snapshot.get("shaft_diameter") is None:
        shaft_d = snapshot.get("shaft_d1_mm") or snapshot.get("shaft_d1") or snapshot.get("d1")
        if shaft_d is not None:
            snapshot["shaft_diameter"] = shaft_d

    return snapshot


def _build_engineering_physics_report(tile: Dict[str, Any]) -> tuple[str, bool]:
    if not tile:
        return "ENGINEERING PHYSICS REPORT: Keine berechneten Physikdaten verfuegbar.", False

    lines: List[str] = [
        "### ZWINGENDE COMPLIANCE-REGELN (ZERO TOLERANCE) ###",
        "Du hast Zugriff auf den aktuellen Zustand der deterministischen Berechnungsmaschine (System State). Dieser Zustand steht ÜBER allem RAG-Wissen!",
        "1. WENN das System eine chemische Warnung meldet (z.B. NBR nicht beständig gegen HEES), MUSS deine Empfehlung lauten: 'Aufgrund der Systemprüfung ist Werkstoff X für dieses Medium strikt AUSGESCHLOSSEN.' Verwende keine weichen Formulierungen wie 'fraglich' oder 'kritisch'.",
        "2. Du darfst physikalische Grenzwerte NICHT selbst beurteilen. Wenn der System State Warnungen zu PV-Wert, Geschwindigkeit oder Temperatur enthält, MUSS deine Empfehlung lauten: 'Aufgrund der Systemprüfung ist Werkstoff X für diese Parameter strikt AUSGESCHLOSSEN.' Zitiere die Warnmeldung exakt aus dem System State.",
        "3. Du darfst das RAG-Wissen NUR nutzen, um Werkstoffe zu vergleichen, die laut System State noch zulässig sind, oder um zu erklären, WARUM das vom User gewählte Material laut System versagt.",
        "WICHTIG: Wenn du die Systemwarnungen zitierst, MUSST du ausnahmslos JEDE Zahl (z.B. 15.7, 12.0, 3.14, 2.0) exakt so in deinen Antworttext übernehmen, wie sie im State steht! Lasse keine Vergleichswerte weg und runde nicht. Wenn im State steht '15.7 m/s > 12.0 m/s', müssen exakt diese beiden Zahlen im Text auftauchen, sonst schlägt unsere interne QA-Prüfung fehl!",
        f"\n- status: {tile.get('status')}",
    ]
    for key in (
        "friction_power_watts",
        "compression_ratio_pct",
        "groove_fill_pct",
        "stretch_pct",
        "thermal_expansion_mm",
        "clearance_gap_mm",
    ):
        if tile.get(key) is not None:
            lines.append(f"- {key}: {tile.get(key)}")

    risk_flags = (
        "hrc_warning",
        "runout_warning",
        "pv_warning",
        "dry_running_risk",
        "extrusion_risk",
        "requires_backup_ring",
        "geometry_warning",
        "shrinkage_risk",
        "chem_warning",
    )
    has_risk = any(bool(tile.get(flag)) for flag in risk_flags)

    if tile.get("pv_value_mpa_m_s") is not None:
        pv = tile.get("pv_value_mpa_m_s")
        lines.append(f"Aktueller PV-Wert: {pv} MPa*m/s.")
        lines.append("Berechne NIEMALS physikalische Werte (wie PV-Werte) selbst aus! Nutze AUSSCHLIESSLICH diesen bereitgestellten PV-Wert.")
    
    if tile.get("v_surface_m_s") is not None:
        v = tile.get("v_surface_m_s")
        lines.append(f"Aktuelle Gleitgeschwindigkeit: {v} m/s.")
    
    if tile.get("chem_warning"):
        msg = tile.get("chem_message", "Inkompatibilitaet festgestellt.")
        lines.append(f"CRITICAL WARNING: {msg}. Du darfst dieses Material unter KEINEN UMSTÄNDEN als 'geeignet' oder 'sicher' empfehlen!")

    if tile.get("requires_backup_ring") or tile.get("extrusion_risk"):
        lines.append(
            "CRITICAL PHYSICS RULE: The system calculated an extrusion risk. "
            "You MUST explicitly recommend adding a Back-up Ring (Stuetzring) to the solution."
        )
    if tile.get("hrc_warning"):
        lines.append(
            "CRITICAL PHYSICS RULE: The shaft is too soft (< 58 HRC). "
            "You MUST propose a trade-off: Option A (Harden the shaft) vs. "
            "Option B (Use a mechanical seal instead of a lip seal)."
        )
    if tile.get("shrinkage_risk"):
        lines.append(
            "CRITICAL PHYSICS RULE: Cryogenic temperatures detected. "
            "You MUST recommend a spring-energized seal (Elastil) to compensate for thermal shrinkage."
        )

    # Conflict Resolution is now integrated into the Zero Tolerance rules above.
    return "\n".join(lines), has_risk


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


def _extract_shaft_hardness_hrc(state: SealAIState, user_query: str) -> float | None:
    params = getattr(state, "parameters", None)
    for value in (
        getattr(params, "shaft_hardness", None) if params is not None else None,
        getattr(params, "hardness", None) if params is not None else None,
    ):
        if value is None:
            continue
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value))
        if match and "hrc" in str(value).lower():
            try:
                return float(match.group(0).replace(",", "."))
            except ValueError:
                pass
    query_match = re.search(
        r"(?:wellenh[aä]rte|h[aä]rte)\D{0,20}([-+]?\d+(?:[.,]\d+)?)\s*hrc",
        user_query or "",
        re.IGNORECASE,
    )
    if query_match:
        try:
            return float(query_match.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def _get_rag_llm(model_name: str) -> Any:
    global _RAG_LLM
    if _RAG_LLM is None:
        _RAG_LLM = LazyChatOpenAI(
            model=model_name,
            temperature=0,
            cache=False,
            max_tokens=1000,
            streaming=True,
        )
    return _RAG_LLM


async def conversational_rag_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    user_query = (latest_user_text(state.messages or []) or "").strip()
    rag_context = _extract_rag_context(state)
    live_calc_tile = _extract_live_calc_tile(state)
    profile_snapshot = _build_profile_snapshot(state)
    physics_report, has_physics_risk = _build_engineering_physics_report(live_calc_tile)
    calc_notes = list((state.calc_results.notes if state.calc_results else []) or [])
    if calc_notes:
        notes_block = "\n".join(f"- {note}" for note in calc_notes)
        physics_report = f"{physics_report}\n\nSYSTEM WARNMELDUNGEN (WÖRTLICH ZITIEREN):\n{notes_block}"
    if physics_report:
        logger.info("material_agent.deterministic_constraints_injected", physics_report_len=len(physics_report))
    flags = state.flags or {}
    low_quality = bool(flags.get("rag_low_quality_results"))
    rag_turn_count = int(getattr(state, "rag_turn_count", 0) or 0)
    config = _extract_langgraph_config(_args, _kwargs)

    if not rag_context or low_quality:
        if rag_turn_count >= 3 or flags.get("rag_limit_reached"):
            final_text = _NO_DOCS_TEXT
        else:
            final_text = _FALLBACK_TEXT
    else:
        model_name = get_model_tier("mini")
        hardness_hrc = _extract_shaft_hardness_hrc(state, user_query)
        hardness_warning = ""
        if hardness_hrc is not None and hardness_hrc < 58.0:
            hardness_warning = (
                f"\nAKUTE WARNUNG: Angegebene Wellenhaerte {hardness_hrc:.1f} HRC liegt unter 58 HRC. "
                "Warne explizit vor moeglichem Versagen der PTFE-Loesung durch Abrasivitaet."
            )
        tradeoff_instruction = ""
        if has_physics_risk:
            tradeoff_instruction = (
                "\nRISIKO-MODUS AKTIV: Wenn Risiken/Warnungen bestehen, praesentierst du IMMER 2 "
                "konkrete Loesungswege (Trade-offs) und erklaerst kurz, warum die berechnete Physik "
                "(z. B. PV-Wert, Extrusion oder Geometrie) gefaehrlich ist."
            )
        system_prompt = (
            "Du bist ein Solution Architect fuer Dichtungstechnik. "
            "Nutze die physikalischen Berechnungen aus dem Engineering Physics Report als verbindliche Grundlage. "
            "Antworte wie ein Senior-Berater: erst kurze Machbarkeits-Einschaetzung, dann konkrete Loesung. "
            "Knuepfe Empfehlungen explizit an Systemparameter und Berechnungen. "
            "Wenn Risiken/Warnungen bestehen, präsentiere immer 2 Loesungswege (Trade-offs). "
            "Erklaere dem User kurz, warum die Berechnung (z. B. PV-Wert oder Extrusion) gefaehrlich ist. "
            "Erinnere den Kunden daran: Dichtungstechnik ist SYSTEMTECHNIK. "
            "Wenn FactCards (IDs PTFE-F-xxx) im Kontext vorhanden sind, "
            "haben diese ABSOLUTE Priorität vor deinem Allgemeinwissen. "
            "Wenn eine FactCard besagt, dass PTFE kryogen-tauglich ist, darfst du es nicht als "
            "'normalerweise nicht empfohlen' bezeichnen. Nutze die exakten Begriffe aus den FactCards. "
            "Beantworte die Frage des Nutzers fliessend und natuerlich basierend auf dem folgenden Kontext. "
            "Antworte immer auf Deutsch, auch wenn Feldnamen, Quellen oder Nutzereingaben teilweise auf Englisch sind. "
            "Erfinde keine Fakten. "
            "Wenn im PROFIL Parameter vorhanden sind (z. B. rpm, shaft_d1_mm), behandle sie als vorhanden "
            "und behaupte nicht, dass diese fehlen."
            f"{tradeoff_instruction}"
            f"{hardness_warning}\n\n"
            f"{physics_report}\n\n"
            f"PROFIL (Parameter-Snapshot):\n{json.dumps(profile_snapshot, ensure_ascii=False, indent=2)}\n\n"
            f"KONTEXT:\n{rag_context}"
        )
        user_prompt = user_query or "Bitte gib eine kurze, hilfreiche technische Erklärung."
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        chunks: List[str] = []
        llm = _get_rag_llm(model_name)
        async for chunk in llm.astream(messages, config=config):
            text = _chunk_to_text(chunk)
            if text:
                chunks.append(text)
        final_text = "".join(chunks).strip()
        if not final_text:
            final_text = _FALLBACK_TEXT

    messages = list(state.messages or [])
    messages.append(AIMessage(content=[{"type": "text", "text": final_text}]))
    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"response_text": final_text})

    return {
        "messages": messages,
        "working_memory": wm,
        "final_text": final_text,
        "final_answer": final_text,
        "phase": PHASE.KNOWLEDGE,
        "last_node": "conversational_rag_node",
    }


__all__ = ["conversational_rag_node"]
