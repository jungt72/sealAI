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
from typing import Any, Dict, List, Optional

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from langgraph.types import Command, Send

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.messages import latest_user_text
from app.services.rag.state import WorkingProfile

logger = structlog.get_logger("rag.nodes.p1_context")

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Du bist ein technischer Datenextraktionsassistent für Flanschdichtungsanwendungen.

Analysiere die Benutzeranfrage und extrahiere alle genannten technischen Parameter.
Gib NUR Felder zurück, die explizit oder klar implizit im Text genannt werden.
Fehlende Felder bleiben null.

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
- material: Erwähnter Dichtungswerkstoff (z.B. "NBR", "FKM", "PTFE", "Kyrolon")
- product_name: Produkt- oder Handelsname (z.B. "Gylon", "Sigraflex")

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
    material: Optional[str] = None
    product_name: Optional[str] = None

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

    for field_name, value in extracted.model_dump().items():
        if value is not None:
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

    extracted: Optional[_P1Extraction] = None
    error_hint: Optional[str] = None

    try:
        extracted = _invoke_extraction(user_text, list(state.messages or []))
    except Exception as exc:
        error_hint = f"p1_extraction_failed: {exc}"
        logger.warning(
            "p1_context_llm_failed",
            error=str(exc),
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

    result: Dict[str, Any] = {
        "working_profile": merged_profile,
        "phase": PHASE.FRONTDOOR,  # reuse existing FRONTDOOR phase; P1 is pre-frontdoor in v4
        "last_node": "node_p1_context",
    }
    if error_hint:
        result["error"] = error_hint

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
