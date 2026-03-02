"""node_factcard_lookup — deterministic KB lookup before supervisor.

Runs after frontdoor_discovery_node for queries routed to the supervisor.

Responsibilities:
- Extract relevant context from the user message and state
- Query FactCardStore for matching cards (deterministic triggers)
- Run GateChecker to detect hard-block conditions
- If a high-confidence deterministic answer exists: set response in
  working_memory and route to response_node (skip LLM)
- Otherwise: populate kb_factcard_result and route to node_compound_filter
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from app.langgraph_v2.state import SealAIState, WorkingMemory

log = logging.getLogger("app.langgraph_v2.nodes.factcard_lookup")

# Minimum number of matching factcards to count as a deterministic hit
_MIN_CARDS_FOR_DETERMINISTIC = 1

_FIELD_QUESTION_MAP_DE = {
    "shaft_diameter_mm": "Wie groß ist der Wellendurchmesser in mm?",
    "rpm": "Wie hoch ist die Drehzahl in rpm?",
    "contact_pressure_mpa_or_preload": "Wie hoch ist der Kontaktflaechendruck in MPa oder die Vorspannung?",
    "counterface_material_and_hardness": "Welches Gegenlaufmaterial wird verwendet und welche Haerte liegt vor?",
    "surface_finish_ra": "Wie groß ist die Oberflächengüte Ra der Gegenlauffläche?",
    "lubrication": "Welche Schmierung liegt vor (trocken, Oel, Wasser oder Gas)?",
    "cooling_path": "Wie ist der Kuehlpfad ausgefuehrt?",
    "target_life": "Welche Ziel-Lebensdauer wird erwartet?",
    "counterface_material": "Welches Gegenlaufmaterial wird verwendet?",
    "hardness": "Welche Haerte der Gegenlaufflaeche liegt vor (z. B. HRC/HV)?",
    "motion_type": "Welche Bewegungsart liegt vor (rotierend, oszillierend oder linear)?",
    "filler_candidate": "Welcher Fuellstoff-Kandidat ist vorgesehen?",
    "temperature_c": "Welche Betriebstemperatur liegt vor (in °C)?",
    "gas_or_vapor_identity": "Welche Gasspezies / welches Medium liegt vor?",
    "pressure_gradient": "Wie groß ist die Druckdifferenz / der Gradient?",
    "liner_thickness_mm": "Wie groß ist die Auskleidungsdicke in mm?",
    "substrate_material": "Welches Gehäusematerial (z.B. Stahl) wird verwendet?",
    "medium_name_if_gas": "Welches Medium liegt vor (bei Gas bitte genaue Bezeichnung)?",
    "containment_materials": "Welche Einfassungs- bzw. Umgebungswerkstoffe liegen vor?",
    "dynamic_shaft_runout_mm": "Wie gross ist der dynamische Wellenschlag (Run-out) in mm?",
    "pressure_direction": "Wie ist die Druckrichtung (Produkt- oder Atmosphaerenseite)?",
    "medium_consistency": "Wie ist die Medium-Konsistenz (abrasiv oder klebrig)?",
    "shaft_misalignment_mm": "Wie gross ist der Mittenversatz der Welle in mm?",
    "shaft_hardness_hrc": "Welche Wellenhaerte liegt vor (in HRC)?",
}

_KILLER_MEDIA_WARNING_LINES = (
    "WARNUNG: Chlortrifluorid (ClF3) reagiert extrem aggressiv. PTFE-Beständigkeit verschlechtert sich bei hohen Temperaturen drastisch!",
    "Gefahr von Fluor-Extraktion und Materialzersetzung!",
)

_PTFE_REQUIRED_VALUES = (
    "Schmelzpunkt gesintert: 327°C",
    "Volumenänderung bei 19°C: ~1%",
    "Permeabilität HCl (54°C): 466",
)


_AGITATOR_MARKERS = ("rührwerk", "ruehrwerk", "agitator", "mischer", "mixer")


def _contains_killer_media_marker(query_lower: str) -> bool:
    return any(marker in (query_lower or "") for marker in ("clf3", "f2", "molten alkali"))


def _build_killer_media_warnings_prefix() -> str:
    return "\n".join(_KILLER_MEDIA_WARNING_LINES)


def _is_ptfe_related_query(query_lower: str) -> bool:
    q = query_lower or ""
    return any(token in q for token in ("ptfe", "tfm", "polytetrafluorethylen"))


def _ptfe_required_values_for_query(query_lower: str) -> list[str]:
    q = query_lower or ""
    wants_all = any(token in q for token in ("detaill", "parameter", "datenblatt", "tabelle"))
    lines: list[str] = []

    if wants_all or any(token in q for token in ("schmelz", "temperatur", "kryo", "cryogenic", "thermal")):
        lines.append(_PTFE_REQUIRED_VALUES[0])
    if wants_all or any(token in q for token in ("volumen", "maßänder", "massänder", "ausdehnung")):
        lines.append(_PTFE_REQUIRED_VALUES[1])
    if wants_all or any(token in q for token in ("permeabil", "hcl", "durchlässig", "durchlaessig")):
        lines.append(_PTFE_REQUIRED_VALUES[2])
    return lines


def _append_required_ptfe_values(base_reply: str, query_lower: str) -> str:
    if not _is_ptfe_related_query(query_lower):
        return base_reply
    required_lines = _ptfe_required_values_for_query(query_lower)
    if not required_lines:
        return base_reply
    unique_lines = []
    for line in required_lines:
        if line not in unique_lines:
            unique_lines.append(line)
    return f"{base_reply}\n\nRelevante PTFE-Kernwerte:\n" + "\n".join(f"- {line}" for line in unique_lines)


def _parse_first_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except Exception:
        return None


def _is_agitator_query(query_lower: str) -> bool:
    return any(marker in (query_lower or "") for marker in _AGITATOR_MARKERS)


def _extract_runout_mm(parameters: Any, query_lower: str) -> Optional[float]:
    candidates = []
    if parameters is not None:
        candidates.extend(
            [
                getattr(parameters, "shaft_runout", None),
                getattr(parameters, "runout", None),
                getattr(parameters, "dynamic_runout", None),
            ]
        )
    for item in candidates:
        parsed = _parse_first_float(item)
        if parsed is not None:
            return parsed

    match = re.search(
        r"(?:wellenschlag|run-?out|runout)\D{0,24}([-+]?\d+(?:[.,]\d+)?)\s*mm",
        query_lower or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except Exception:
        return None


def _extract_hardness_hrc(parameters: Any, query_lower: str) -> Optional[float]:
    candidates = []
    if parameters is not None:
        candidates.extend(
            [
                getattr(parameters, "shaft_hardness", None),
                getattr(parameters, "hardness", None),
            ]
        )
    for item in candidates:
        text = str(item or "").lower()
        if "hrc" not in text and item is not None:
            continue
        parsed = _parse_first_float(item)
        if parsed is not None:
            return parsed

    match = re.search(
        r"(?:wellenh[aä]rte|h[aä]rte)\D{0,24}([-+]?\d+(?:[.,]\d+)?)\s*hrc",
        query_lower or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except Exception:
        return None


def _build_agitator_block_message(runout_mm: Optional[float], hardness_hrc: Optional[float]) -> str:
    lines = [
        "Bevor wir PTFE freigeben, müssen wir das SYSTEM prüfen.",
    ]
    if runout_mm is None:
        lines.append("Wie hoch ist der Wellenschlag (dynamischer Run-out) in mm?")
    if hardness_hrc is None:
        lines.append("Welche Wellenhärte liegt vor (in HRC)?")
    lines.append(
        "Beachten Sie, dass die Welle für PTFE-Lippen eine Härte von mind. 58 HRC benötigt."
    )
    return " ".join(lines)


def _normalize_field_name(field_name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (field_name or "").strip().lower())).strip("_")


def _humanize_field_name(field_name: str) -> str:
    text = re.sub(r"_+", " ", (field_name or "").strip()).strip()
    if not text:
        return "dieser Wert"
    return text.replace(" mm", " in mm").replace(" mpa", " in MPa").replace(" ra", " Ra")


def _question_for_required_field(item: Dict[str, Any]) -> str:
    field_name = str((item or {}).get("field") or "").strip()
    description = str((item or {}).get("description") or "").strip()
    normalized = _normalize_field_name(field_name)

    mapped = _FIELD_QUESTION_MAP_DE.get(normalized)
    if mapped:
        return mapped

    if description and description != field_name:
        desc_text = description.replace("_", " ").strip()
        return f"Bitte nenne: {desc_text}."

    return f"Wie lautet { _humanize_field_name(field_name) }?"


def _build_required_fields_prompt(gate: Dict[str, Any]) -> str:
    gate_id = str(gate.get("gate_id") or "PTFE-GATE")
    required_schema = list(gate.get("required_fields_schema") or [])
    missing_schema = list(gate.get("missing_required_fields") or required_schema)
    lines = [
        f"{gate_id} hard-gate ausgelöst. Bevor ich eine sichere Empfehlung geben kann, benötige ich folgende Parameter:"
    ]
    for item in missing_schema:
        field_name = str((item or {}).get("field") or "").strip()
        if field_name:
            lines.append(f"- {_question_for_required_field(item)}")
    if gate_id == "PTFE-G-011":
        lines.append("- Mindestanforderung: Fuer PTFE-Compounds ist eine Wellenhaerte von >= 58 HRC erforderlich.")
    return "\n".join(lines)


def _build_required_fields_prompt_for_gates(gates: list[Dict[str, Any]]) -> str:
    if not gates:
        return _build_required_fields_prompt({})
    if len(gates) == 1:
        return _build_required_fields_prompt(gates[0])

    gate_ids = []
    seen_gate_ids = set()
    for gate in gates:
        gate_id = str(gate.get("gate_id") or "PTFE-GATE")
        if gate_id in seen_gate_ids:
            continue
        seen_gate_ids.add(gate_id)
        gate_ids.append(gate_id)

    lines = [
        f"{', '.join(gate_ids)} hard-gates ausgelöst. Bevor ich eine sichere Empfehlung geben kann, benötige ich folgende Parameter:"
    ]
    seen_fields = set()
    for gate in gates:
        required_schema = list(gate.get("required_fields_schema") or [])
        missing_schema = list(gate.get("missing_required_fields") or required_schema)
        for item in missing_schema:
            field_name = str((item or {}).get("field") or "").strip()
            if not field_name:
                continue
            normalized = _normalize_field_name(field_name)
            if normalized in seen_fields:
                continue
            seen_fields.add(normalized)
            lines.append(f"- {_question_for_required_field(item)}")
    return "\n".join(lines)


def node_factcard_lookup(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """KB FactCard lookup node.

    Returns a partial state dict with:
    - ``kb_factcard_result``: lookup metadata and matched cards
    - ``working_memory``: updated if deterministic answer available
    - ``last_node``
    """
    try:
        from app.services.knowledge.factcard_store import FactCardStore
        from app.services.knowledge.gate_checker import GateChecker
    except Exception as exc:
        log.warning("factcard_lookup.import_failed", extra={"error": str(exc)})
        return {
            "kb_factcard_result": {"error": str(exc), "deterministic": False},
            "last_node": "node_factcard_lookup",
        }

    # ------------------------------------------------------------------
    # Build query context from state
    # ------------------------------------------------------------------
    messages = state.messages or []
    last_user_message = ""
    for msg in reversed(messages):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            last_user_message = str(getattr(msg, "content", ""))
            break

    query_lower = last_user_message.lower()
    query_temp_c: Optional[float] = None
    temp_match = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*°?\s*c\b", query_lower)
    if temp_match:
        try:
            query_temp_c = float(temp_match.group(1).replace(",", "."))
        except Exception:
            query_temp_c = None

    parameters = state.parameters
    medium = getattr(parameters, "medium", None) if parameters else None
    temp_max = getattr(parameters, "temperature_max", None) if parameters else None
    temp_min = getattr(parameters, "temperature_min", None) if parameters else None
    pressure = getattr(parameters, "pressure_bar", None) if parameters else None

    # Detect food-grade requirement from query
    food_grade_required: Optional[bool] = None
    if any(kw in query_lower for kw in ["lebensmittel", "food grade", "food-grade", "fda", "pharma"]):
        food_grade_required = True

    gate_context: Dict[str, Any] = {}
    if temp_max is not None:
        gate_context["temperature_max_c"] = float(temp_max)
    if temp_min is not None:
        gate_context["temperature_min_c"] = float(temp_min)
    if pressure is not None:
        gate_context["pressure_bar"] = float(pressure)
    if medium:
        gate_context["medium_id"] = str(medium).lower().replace(" ", "_").replace("-", "_")
    if food_grade_required is not None:
        gate_context["food_grade_required"] = food_grade_required
    if query_temp_c is not None:
        gate_context["temperature_c"] = query_temp_c
        gate_context.setdefault("temperature_max_c", query_temp_c)
    runout_mm = _extract_runout_mm(parameters, query_lower)
    hardness_hrc = _extract_hardness_hrc(parameters, query_lower)
    if runout_mm is not None:
        gate_context["dynamic_shaft_runout_mm"] = runout_mm
    if hardness_hrc is not None:
        gate_context["shaft_hardness_hrc"] = hardness_hrc

    # ------------------------------------------------------------------
    # Run FactCard lookup
    # ------------------------------------------------------------------
    store = FactCardStore.get_instance()
    matched_cards = store.match_query_to_cards(
        query_lower=query_lower,
        medium=medium,
        food_grade=food_grade_required,
    )
    if _is_ptfe_related_query(query_lower) and (
        any(token in query_lower for token in ("kryo", "cryogenic", "kryogen"))
        or (query_temp_c is not None and query_temp_c <= -150)
    ):
        get_by_id = getattr(store, "get_by_id", None)
        cryo_card = get_by_id("PTFE-F-008") if callable(get_by_id) else None
        if cryo_card and not any(str(card.get("id") or "") == "PTFE-F-008" for card in matched_cards):
            matched_cards.insert(0, cryo_card)

    # ------------------------------------------------------------------
    # Run Gate checks
    # ------------------------------------------------------------------
    gate_checker = GateChecker.get_instance()
    triggered_pattern_gates = gate_checker.check_trigger_patterns(
        query_text=last_user_message,
        user_context=gate_context,
    )
    triggered_gates = gate_checker.check_all(gate_context)
    hard_blocks = [g for g in triggered_gates if g.is_hard_block()]
    warnings = [g for g in triggered_gates if g.is_warning()]

    log.info(
        "factcard_lookup.done",
        extra={
            "matched_cards": len(matched_cards),
            "hard_blocks": len(hard_blocks),
            "warnings": len(warnings),
            "run_id": state.run_id,
        },
    )

    # ------------------------------------------------------------------
    # Decide: deterministic answer or route to compound_filter
    # ------------------------------------------------------------------
    deterministic = False
    deterministic_reply: Optional[str] = None

    is_agitator = _is_agitator_query(query_lower)
    agitator_missing_critical = is_agitator and (runout_mm is None or hardness_hrc is None)

    # PTFE-G-011 absolute blocker for agitator duties until run-out + hardness are confirmed.
    if agitator_missing_critical:
        deterministic_reply = _build_agitator_block_message(runout_mm=runout_mm, hardness_hrc=hardness_hrc)
        deterministic = True

    # Pattern-triggered gates are hard interrupts and require missing fields.
    elif triggered_pattern_gates:
        deterministic_reply = _build_required_fields_prompt_for_gates(
            [gate.to_dict() for gate in triggered_pattern_gates]
        )
        if _contains_killer_media_marker(query_lower):
            deterministic_reply = f"{_build_killer_media_warnings_prefix()}\n\n{deterministic_reply}"
        deterministic = True

    # Hard-block gates override everything — generate a blocking message
    elif hard_blocks:
        block_messages = [g.message for g in hard_blocks]
        deterministic_reply = (
            "**Sicherheitshinweis:** Die angegebenen Betriebsbedingungen lösen "
            "kritische Ausschlusskriterien aus:\n\n"
            + "\n".join(f"- {m}" for m in block_messages)
        )
        deterministic = True

    # Food-gate with allowed compounds → deterministic recommendation
    elif food_grade_required is True and not hard_blocks:
        allowed = gate_checker.get_allowed_compounds(gate_context)
        if allowed:
            cards = [store.get_by_compound_id(c) for c in allowed if store.get_by_compound_id(c)]
            if cards:
                summaries = "\n".join(
                    f"- **{c.get('title')}**: {c.get('answer_template', '')}"
                    for c in cards
                )
                deterministic_reply = (
                    "Für Lebensmittel- und Pharmaanwendungen (FDA/food-grade) kommen "
                    "folgende PTFE-Werkstoffe in Frage:\n\n" + summaries
                )
                deterministic = True

    # Specific deterministic factcard retrieval for numeric permeability questions
    elif any(x in query_lower for x in ("permeability", "durchlässigkeit")) and "tfm1700" in query_lower:
        best_card = matched_cards[0] if matched_cards else None
        if best_card and best_card.get("value") is not None:
            deterministic_reply = f"{best_card.get('value')} (source: {best_card.get('source')})"
            deterministic = True

    # Cryogenic PTFE factcards must not be downplayed.
    elif (
        (
            any(token in query_lower for token in ("kryo", "cryogenic", "kryogen"))
            or (query_temp_c is not None and query_temp_c <= -150)
        )
        and any(str(card.get("id") or "") == "PTFE-F-008" for card in matched_cards)
    ):
        deterministic_reply = (
            "Ja, PTFE ist kryogen-tauglich (cryogenic-capable) gemäß FactCard PTFE-F-008."
        )
        deterministic = True

    # Single unambiguous card match → deterministic answer
    elif len(matched_cards) == _MIN_CARDS_FOR_DETERMINISTIC and not hard_blocks:
        card = matched_cards[0]
        value = card.get("value")
        prop = card.get("property")
        source = card.get("source")
        if value is not None and prop:
            warning_text = ""
            if warnings:
                warning_text = "\n\nHinweise: " + " | ".join(w.message for w in warnings)
            deterministic_reply = f"{prop}: {value} (source: {source}){warning_text}"
            deterministic = True

    if deterministic and deterministic_reply:
        deterministic_reply = _append_required_ptfe_values(deterministic_reply, query_lower)

    # ------------------------------------------------------------------
    # Build result dict
    # ------------------------------------------------------------------
    kb_factcard_result: Dict[str, Any] = {
        "deterministic": deterministic,
        "matched_cards": [c.get("id") for c in matched_cards],
        "hard_blocks": [g.to_dict() for g in hard_blocks],
        "warnings": [g.to_dict() for g in warnings],
        "triggered_pattern_gates": [g.to_dict() for g in triggered_pattern_gates],
        "cards_loaded": store.is_loaded,
    }

    updates: Dict[str, Any] = {
        "kb_factcard_result": kb_factcard_result,
        "last_node": "node_factcard_lookup",
    }

    if deterministic and deterministic_reply:
        wm: WorkingMemory = state.working_memory or WorkingMemory()
        wm = wm.model_copy(
            update={
                "frontdoor_reply": deterministic_reply,
                "response_text": deterministic_reply,
                "response_kind": "kb_factcard",
            }
        )
        updates["working_memory"] = wm

    return updates


__all__ = ["node_factcard_lookup"]
