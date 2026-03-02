"""P1 Context Node for SEALAI v4.4.0 (Sprint 4).

Migrates WorkingProfile extraction from frontdoor_discovery_node /
supervisor_policy_node into a dedicated, clearly bounded node.

Responsibilities:
- Extract WorkingProfile fields from user messages via LLM structured output
- Support two modes via router_classification:
    new_case   → fresh extraction, creates a new WorkingProfile
    follow_up  → merges extracted fields onto the existing working_profile
- No RAG, no material/type research (those are P2/P3)
- Tolerates LLM failure gracefully (keeps existing profile, sets error hint)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from langgraph.types import Command, Send

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.messages import latest_user_text
from app.services.rag.state import WorkingProfile
from app.langgraph_v2.nodes.persona_detection import update_persona_in_state

logger = structlog.get_logger("rag.nodes.p1_context")

_SEAL_MATERIAL_TOKENS = frozenset(
    {
        "ptfe",
        "nbr",
        "hnbr",
        "fkm",
        "ffkm",
        "epdm",
        "vmq",
        "fvmq",
        "pu",
        "pur",
        "tpu",
        "peek",
        "elastomer",
        "elastomeric",
    }
)
_OPTION_A_PATTERN = re.compile(r"\boption\s*a\b", re.IGNORECASE)
_OPTION_B_PATTERN = re.compile(r"\boption\s*b\b", re.IGNORECASE)
_OPTION_SELECTION_MARKERS = (
    "wir nehmen",
    "ich nehme",
    "nehmen wir",
    "nehme ich",
    "wir waehlen",
    "ich waehle",
    "wir wählen",
    "ich wähle",
    "entscheide",
    "entscheidung",
    "akzept",
    "passt",
    "einverstanden",
    "go with",
    "choose",
    "chosen",
)
_HRC_PATTERN = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*hrc\b", re.IGNORECASE)
_OPTION_BLOCK_PATTERN = r"(?is)(option\s*{letter}\b.*?)(?=option\s*[a-z]\b|$)"
_MIN_ACCEPTED_HRC = 58.0


def _to_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().replace(",", ".")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _normalize_material_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text)


def _looks_like_seal_material(value: Any) -> bool:
    token = _normalize_material_token(value)
    if not token:
        return False
    return token in _SEAL_MATERIAL_TOKENS

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Du bist ein technischer Datenextraktionsassistent für Flanschdichtungsanwendungen.

Analysiere die Benutzeranfrage und extrahiere alle genannten technischen Parameter.
Gib NUR Felder zurück, die explizit oder klar implizit im Text genannt werden.
Fehlende Felder bleiben null.

CRITICAL INSTRUCTION: You are a strict data extractor. If the user mentions ANY numbers related to diameter
(e.g., "50mm Welle"), speed ("1500 U/min"), pressure ("300 bar"), temperature, or hardness ("40 HRC"),
you MUST extract them IMMEDIATELY into the schema on this very first turn.
Do NOT wait for a follow-up confirmation to extract data that is already present in the text.

Bei aktiven Resume/HITL-Dialogen gilt zusaetzlich:
- Wenn der User eine zuvor vom Assistenten angebotene Option annimmt ("Option A/B"), werte das als verbindliche Parameterentscheidung.
- Übernimm die daraus resultierenden technischen Werte in die Extraktion (z. B. "Option A = 58 HRC" => hrc_value=58).
- Ein explizites "Wir nehmen Option A" ist ausreichend, auch wenn der Wert nur in der vorherigen Assistenten-Nachricht stand.

Felder:
- medium: Prozessmedium (z.B. "Dampf", "Erdgas", "H2SO4")
- medium_detail: Genauere Spezifikation (z.B. "gesättigter Dampf", "H2 99,9%")
- pressure_max_bar: Maximaler Betriebsdruck in bar (Zahl, kein Einheitensuffix)
- pressure_min_bar: Minimaler Betriebsdruck in bar
- temperature_max_c: Maximale Betriebstemperatur in °C
- temperature_min_c: Minimale Betriebstemperatur in °C
- flange_standard: Flanschnorm (z.B. "EN 1092-1", "ASME B16.5", "JIS B2220")
- flange_dn: Nennweite DN als Ganzzahl (z.B. 100 für DN100)
- flange_pn: Nenndruck PN als Ganzzahl (z.B. 40 für PN40)
- flange_class: ASME-Class als Ganzzahl (150, 300, 600, 900, 1500 oder 2500)
- bolt_count: Anzahl Schrauben als gerade Ganzzahl
- bolt_size: Schraubengröße (z.B. "M20", "3/4\"")
- cyclic_load: true wenn zyklische/schwellende Belastung erwähnt wird, sonst false
- emission_class: Emissionsklasse (z.B. "TA-Luft", "VDI 2440", "EPA Method 21")
- industry_sector: Branche (z.B. "Petrochemie", "Pharma", "Kraftwerk")
- material: Material der Welle/Gegenlauffläche (z.B. "Stahl", "Edelstahl", "1.4404"); niemals Dichtungswerkstoff
- seal_material: Dichtungswerkstoff (z.B. "PTFE", "NBR", "FKM")
- product_name: Produkt- oder Handelsname (z.B. "Gylon", "Sigraflex")
- shaft_d1_mm: Wellendurchmesser d1 in mm (Zahl)
- shaft_diameter: Wellendurchmesser in mm (Zahl)
- rpm: Drehzahl in U/min (Zahl)
- speed_rpm: Drehzahl in U/min (Zahl)
- n: Drehzahl in U/min (Zahl)
- d1: Wellendurchmesser in mm (Zahl)
- elastomer_material: Elastomerwerkstoff (z.B. "NBR", "FKM")
- hrc_value: Härtewert in HRC (Zahl)
- clearance_gap_mm: Spaltmaß in mm (Zahl)

Antworte ausschließlich mit dem JSON-Objekt. Keine Erklärungen.
"""


# ---------------------------------------------------------------------------
# Extraction schema (lenient — accepts nulls freely)
# ---------------------------------------------------------------------------


class _P1Extraction(BaseModel):
    """LLM output schema for P1 WorkingProfile extraction."""

    medium: Optional[str] = None
    medium_detail: Optional[str] = None
    pressure_max_bar: Optional[float] = None
    pressure_min_bar: Optional[float] = None
    temperature_max_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    flange_standard: Optional[str] = None
    flange_dn: Optional[int] = None
    flange_pn: Optional[int] = None
    flange_class: Optional[int] = None
    bolt_count: Optional[int] = None
    bolt_size: Optional[str] = None
    cyclic_load: Optional[bool] = None
    emission_class: Optional[str] = None
    industry_sector: Optional[str] = None
    material: Optional[str] = Field(
        default=None,
        description=(
            "The material of the shaft/counter-surface (e.g., steel, stainless steel, 1.4404). "
            "STRICT RULE: NEVER extract the seal material (e.g., PTFE, elastomer) into this field. "
            "This is ONLY for the hardware/shaft."
        ),
    )
    seal_material: Optional[str] = None
    product_name: Optional[str] = None
    shaft_d1_mm: Optional[float] = None
    shaft_diameter: Optional[float] = None
    rpm: Optional[float] = None
    speed_rpm: Optional[float] = None
    n: Optional[float] = None
    d1: Optional[float] = None
    elastomer_material: Optional[str] = None
    hrc_value: Optional[float] = None
    clearance_gap_mm: Optional[float] = None

    model_config = ConfigDict(extra="ignore")



# ---------------------------------------------------------------------------
# LLM extraction helpers
# ---------------------------------------------------------------------------


def _build_messages(user_text: str, history: List[Any]) -> List[Any]:
    """Build LLM message list from user text and optional prior messages."""
    msgs: List[Any] = [SystemMessage(content=_SYSTEM_PROMPT)]
    # Include at most the last 4 history messages for context (avoid token bloat)
    for msg in list(history or [])[-4:]:
        msgs.append(msg)
    if not history or not isinstance(history[-1], HumanMessage):
        if user_text.strip():
            msgs.append(HumanMessage(content=user_text.strip()))
    return msgs


def _message_to_text(msg: Any) -> str:
    content = getattr(msg, "content", "")
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


def _latest_assistant_text(history: List[Any]) -> str:
    for msg in reversed(list(history or [])):
        if isinstance(msg, AIMessage):
            return _message_to_text(msg).strip()
        if isinstance(msg, dict):
            role = str(msg.get("role") or msg.get("type") or "").strip().lower()
            if role in {"assistant", "ai"}:
                return str(msg.get("content") or "").strip()
    return ""


def _is_active_resume_session(state: SealAIState) -> bool:
    classification = str(getattr(state, "router_classification", "") or "").strip().lower()
    if classification == "resume":
        return True
    if bool(getattr(state, "awaiting_user_confirmation", False)):
        return True
    if bool((getattr(state, "pending_action", "") or "").strip()):
        return True
    return bool(getattr(state, "qgate_has_blockers", False))


def _detect_selected_option(user_text: str) -> str:
    text = (user_text or "").strip().lower()
    if not text:
        return ""
    selected = ""
    if _OPTION_A_PATTERN.search(text):
        selected = "a"
    elif _OPTION_B_PATTERN.search(text):
        selected = "b"
    if not selected:
        return ""
    if any(marker in text for marker in _OPTION_SELECTION_MARKERS):
        return selected
    if text.startswith(f"option {selected}"):
        return selected
    return ""


def _extract_option_block(text: str, option_letter: str) -> str:
    if not text or option_letter not in {"a", "b"}:
        return ""
    match = re.search(_OPTION_BLOCK_PATTERN.format(letter=option_letter), text, re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _extract_hrc_value(*texts: str) -> Optional[float]:
    for text in texts:
        if not text:
            continue
        match = _HRC_PATTERN.search(text)
        if not match:
            continue
        value = _to_float_or_none(match.group(1))
        if value is not None:
            return value
    return None


def _derive_resume_overrides(state: SealAIState, user_text: str, history: List[Any]) -> Dict[str, Any]:
    if not _is_active_resume_session(state):
        return {}
    selected_option = _detect_selected_option(user_text)
    if not selected_option:
        return {}

    assistant_text = _latest_assistant_text(history)
    selected_block = _extract_option_block(assistant_text, selected_option)
    hrc_value = _extract_hrc_value(user_text, selected_block, assistant_text)

    # Option-A fallback for hardness blockers when no explicit HRC number is repeated.
    if hrc_value is None and selected_option == "a":
        lower_ctx = f"{user_text}\n{selected_block}\n{assistant_text}".lower()
        mentions_hardness = any(token in lower_ctx for token in ("hrc", "härte", "haerte", "harden", "haerten"))
        if mentions_hardness:
            hrc_value = _MIN_ACCEPTED_HRC

    if hrc_value is None:
        return {}
    return {"hrc_value": hrc_value}


def _invoke_extraction(user_text: str, history: List[Any]) -> _P1Extraction:
    """Call the LLM and return a validated _P1Extraction."""
    model_name = os.getenv("OPENAI_MODEL_MINI", "gpt-4.1-mini")
    llm = ChatOpenAI(model=model_name, temperature=0.0, max_retries=2)
    structured = llm.with_structured_output(_P1Extraction, method="json_schema", strict=True)
    result = structured.invoke(_build_messages(user_text, history))
    if isinstance(result, _P1Extraction):
        return result
    return _P1Extraction.model_validate(result)


# ---------------------------------------------------------------------------
# Profile merging
# ---------------------------------------------------------------------------


def _merge_extraction_into_profile(
    existing: Optional[WorkingProfile],
    extracted: _P1Extraction,
) -> WorkingProfile:
    """Merge non-None extracted fields onto an existing WorkingProfile.

    For `new_case`: `existing` is None → create fresh.
    For `follow_up`: `existing` is not None → update only provided fields.
    """
    base: Dict[str, Any] = existing.model_dump() if existing else {}

    profile_fields = set(getattr(WorkingProfile, "model_fields", {}).keys())
    for field_name, value in extracted.model_dump().items():
        if field_name == "material" and _looks_like_seal_material(value):
            # Protect shaft/counterface material from seal-material cross-talk.
            continue
        if value is not None and field_name in profile_fields:
            base[field_name] = value

    # Pydantic validates cross-field consistency (min ≤ max, bolt_count even, etc.)
    try:
        return WorkingProfile.model_validate(base)
    except ValidationError as exc:
        # If merged data violates constraints (e.g. follow-up reverses min/max),
        # fall back to only the extraction result — never silently corrupt the profile.
        logger.warning(
            "p1_context_merge_validation_error",
            error=str(exc),
            base_keys=list(base.keys()),
        )
        try:
            return WorkingProfile.model_validate(extracted.model_dump(exclude_none=True))
        except ValidationError:
            return existing or WorkingProfile()


def _merge_extraction_into_extracted_params(
    existing: Optional[Dict[str, Any]],
    extracted: _P1Extraction,
) -> Dict[str, Any]:
    """Merge P1 extraction into state.extracted_params with physics-friendly aliases."""
    merged: Dict[str, Any] = dict(existing or {})
    payload = extracted.model_dump(exclude_none=True)

    # Direct values that downstream deterministic nodes consume.
    for key in ("pressure_max_bar", "temperature_max_c", "rpm", "hrc_value", "clearance_gap_mm"):
        if key in payload:
            numeric_value = _to_float_or_none(payload.get(key))
            if numeric_value is not None:
                merged[key] = numeric_value

    # Diameter aliases for robust lookup in node_p4_live_calc.
    shaft_d1_mm = _to_float_or_none(payload.get("shaft_d1_mm"))
    if shaft_d1_mm is not None:
        merged["shaft_d1_mm"] = shaft_d1_mm
        merged["shaft_d1"] = shaft_d1_mm
        merged["d1"] = shaft_d1_mm

    # Hardness alias for existing consumers that read "hrc".
    if "hrc_value" in payload and "hrc_value" in merged:
        merged["hrc"] = merged["hrc_value"]

    # Keep selected seal material explicitly separate from shaft material.
    seal_material = payload.get("seal_material")
    if isinstance(seal_material, str) and seal_material.strip():
        merged["seal_material"] = seal_material.strip()

    # If the model still emitted a seal token in `material`, remap it safely.
    raw_material = payload.get("material")
    if _looks_like_seal_material(raw_material):
        text = str(raw_material or "").strip()
        if text:
            merged.setdefault("seal_material", text)
            if str(merged.get("material") or "").strip().lower() == text.lower():
                merged.pop("material", None)

    return merged


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_p1_context(state: SealAIState, *_args: Any, **_kwargs: Any) -> Command:
    """P1 Context Node — extract/update WorkingProfile from user messages.

    Wired after node_router for 'new_case' and 'follow_up' paths.
    Fans out to P2 (RAG Material-Lookup) and P3 (Gap-Detection) in parallel.
    Does NOT touch RAG retrieval, material research, or intent classification.
    """
    user_text = latest_user_text(state.messages) or ""
    classification = getattr(state, "router_classification", None) or "new_case"
    existing_profile = getattr(state, "working_profile", None)

    logger.info(
        "p1_context_start",
        classification=classification,
        has_existing_profile=existing_profile is not None,
        user_text_len=len(user_text),
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    history = list(state.messages or [])
    extracted: Optional[_P1Extraction] = None
    error_hint: Optional[str] = None

    try:
        extracted = _invoke_extraction(user_text, history)
    except Exception as exc:
        error_hint = f"p1_extraction_failed: {exc}"
        logger.warning(
            "p1_context_llm_failed",
            error=str(exc),
            classification=classification,
            run_id=state.run_id,
        )

    resume_overrides = _derive_resume_overrides(state, user_text, history)
    if resume_overrides:
        extracted = (
            extracted.model_copy(update=resume_overrides)
            if extracted is not None
            else _P1Extraction.model_validate(resume_overrides)
        )
        logger.info(
            "p1_context_resume_overrides_applied",
            overrides=resume_overrides,
            classification=classification,
            run_id=state.run_id,
        )

    if extracted is not None:
        merged_profile = _merge_extraction_into_profile(
            existing_profile if classification == "follow_up" else None,
            extracted,
        )
    else:
        # LLM failed — preserve existing profile unchanged
        merged_profile = existing_profile or WorkingProfile()

    coverage = merged_profile.coverage_ratio()

    logger.info(
        "p1_context_done",
        classification=classification,
        profile_coverage=round(coverage, 3),
        extracted_fields=(
            [k for k, v in extracted.model_dump().items() if v is not None]
            if extracted
            else []
        ),
        run_id=state.run_id,
    )

    merged_extracted_params = (
        _merge_extraction_into_extracted_params(state.extracted_params, extracted)
        if extracted is not None
        else dict(state.extracted_params or {})
    )

    result: Dict[str, Any] = {
        "working_profile": merged_profile,
        "extracted_params": merged_extracted_params,
        "phase": PHASE.FRONTDOOR,  # reuse existing FRONTDOOR phase; P1 is pre-frontdoor in v4
        "last_node": "node_p1_context",
        "turn_count": int(getattr(state, "turn_count", 0) or 0) + 1,
    }
    persona_patch = update_persona_in_state(state)
    result.update(persona_patch)

    if error_hint:
        result["error"] = error_hint

    if bool((state.flags or {}).get("use_reasoning_core_r3")):
        return Command(
            update=result,
            goto="combinatorial_chemistry_guard_node",
        )

    # Fan out to P2 (RAG Material-Lookup) and P3 (Gap-Detection) in parallel
    updated_state = state.model_copy(update=result)
    return Command(
        update=result,
        goto=[
            Send("node_p2_rag_lookup", updated_state),
            Send("node_p3_gap_detection", updated_state),
        ],
    )


__all__ = [
    "node_p1_context",
    "_merge_extraction_into_profile",
    "_P1Extraction",
]
