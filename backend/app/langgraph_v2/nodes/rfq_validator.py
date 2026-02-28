from __future__ import annotations

import re
from typing import Any, Dict, List

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.llm_factory import get_model_tier
from app.langgraph_v2.utils.messages import latest_user_text

logger = structlog.get_logger("langgraph_v2.nodes.rfq_validator")


_MANDATORY_FIELDS: Dict[str, str] = {
    "bauform_typ": "Bauform/Typ",
    "nennweite_masse": "Nennweite/Maße",
    "stueckzahl": "Stückzahl",
}


class _RFQPresenceCheck(BaseModel):
    bauform_typ: bool = False
    nennweite_masse: bool = False
    stueckzahl: bool = False

    model_config = ConfigDict(extra="ignore")


def _build_rfq_context(state: SealAIState, user_text: str) -> Dict[str, Any]:
    working_memory = state.working_memory or {}
    technical_profile = getattr(working_memory, "technical_profile", {}) or {}
    working_profile = state.working_profile.model_dump(exclude_none=True) if state.working_profile else {}

    return {
        "latest_user_message": user_text,
        "technical_profile": technical_profile,
        "working_profile": working_profile,
        "parameters": state.parameters.as_dict() if state.parameters else {},
        "extracted_params": state.extracted_params or {},
        "seal_family": state.seal_family,
        "plan": state.plan or {},
    }


async def _invoke_llm_presence_check(context_payload: Dict[str, Any]) -> _RFQPresenceCheck:
    model_name = get_model_tier("nano")
    llm = ChatOpenAI(model=model_name, temperature=0.0, max_retries=2)
    structured_llm = llm.with_structured_output(_RFQPresenceCheck, method="json_schema", strict=True)

    system_prompt = (
        "Du prüfst, ob RFQ-Pflichtfelder im Kontext vorhanden sind. "
        "Markiere ein Feld nur als true, wenn es explizit genannt oder klar angegeben ist.\n\n"
        "Pflichtfelder:\n"
        "- bauform_typ: Bauform oder Typ der Dichtung\n"
        "- nennweite_masse: Nennweite (DN) oder konkrete Maße\n"
        "- stueckzahl: gewünschte Menge/Anzahl"
    )
    user_prompt = f"KONTEXT (JSON):\n{context_payload}"
    response = await structured_llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    if isinstance(response, _RFQPresenceCheck):
        return response
    return _RFQPresenceCheck.model_validate(response)


def _fallback_presence_check(context_payload: Dict[str, Any]) -> _RFQPresenceCheck:
    user_text = str(context_payload.get("latest_user_message") or "")
    lower_user = user_text.lower()
    technical_profile = context_payload.get("technical_profile") or {}
    working_profile = context_payload.get("working_profile") or {}
    params = context_payload.get("parameters") or {}
    extracted = context_payload.get("extracted_params") or {}
    plan = context_payload.get("plan") or {}
    seal_family = str(context_payload.get("seal_family") or "")

    has_bauform = bool(
        seal_family
        or technical_profile.get("bauform")
        or technical_profile.get("typ")
        or technical_profile.get("seal_family")
        or params.get("seal_type")
        or extracted.get("seal_family")
        or re.search(r"\b(o-?ring|spiral|spiraldichtung|kammprofil|flachdichtung|ptfe)\b", lower_user)
    )
    has_nennweite = bool(
        working_profile.get("flange_dn")
        or technical_profile.get("nennweite")
        or technical_profile.get("dn")
        or technical_profile.get("masse")
        or params.get("d_shaft_nominal")
        or params.get("shaft_diameter")
        or params.get("housing_diameter")
        or extracted.get("flange_dn")
        or re.search(r"\b(dn\s*\d+|\d+\s*mm)\b", lower_user)
    )
    has_stueckzahl = bool(
        technical_profile.get("stueckzahl")
        or technical_profile.get("quantity")
        or params.get("quantity")
        or extracted.get("quantity")
        or plan.get("quantity")
        or re.search(r"\b\d+\s*(stück|stueck|pcs|pieces|x)\b", lower_user)
    )

    return _RFQPresenceCheck(
        bauform_typ=has_bauform,
        nennweite_masse=has_nennweite,
        stueckzahl=has_stueckzahl,
    )


def _build_missing_data_message(missing_fields: List[str]) -> str:
    if not missing_fields:
        return ""
    if len(missing_fields) == 1:
        tail = missing_fields[0]
    elif len(missing_fields) == 2:
        tail = f"{missing_fields[0]} und {missing_fields[1]}"
    else:
        tail = ", ".join(missing_fields[:-1]) + f" und {missing_fields[-1]}"
    return (
        "Gerne erstelle ich ein Angebot! Damit die Dichtung perfekt passt, "
        f"benötige ich noch {tail}."
    )


async def rfq_validator_node(state: SealAIState) -> Dict[str, Any]:
    # FIX 3: Turn limit and knowledge coverage guard
    turn_count = int(getattr(state, "turn_count", 0) or 0)
    coverage_ready = getattr(state, "coverage_disclosure_ready", False)
    if not coverage_ready and turn_count >= 12:
        block_reason = "Turn limit reached without full knowledge coverage. RFQ blocked for safety."
        logger.warning("rfq_blocked_by_turn_limit", turn_count=turn_count)
        return {
            "rfq_ready": False,
            "rfq_blocked": True,
            "block_reason": block_reason,
            "final_text": block_reason,
            "final_answer": block_reason,
            "phase": PHASE.PROCUREMENT,
            "last_node": "rfq_validator_node",
        }

    user_text = (latest_user_text(state.messages or []) or "").strip()
    context_payload = _build_rfq_context(state, user_text)

    try:
        presence = await _invoke_llm_presence_check(context_payload)
    except Exception as exc:
        logger.warning("rfq_validator_llm_failed_fallback", error=str(exc), run_id=state.run_id)
        presence = _fallback_presence_check(context_payload)

    missing_fields = [
        label
        for key, label in _MANDATORY_FIELDS.items()
        if not bool(getattr(presence, key, False))
    ]

    if not missing_fields:
        return {
            "rfq_ready": True,
            "missing_fields": [],
            "phase": PHASE.PROCUREMENT,
            "last_node": "rfq_validator_node",
        }

    prompt_text = _build_missing_data_message(missing_fields)
    return {
        "rfq_ready": False,
        "missing_fields": missing_fields,
        "final_text": prompt_text,
        "final_answer": prompt_text,
        "phase": PHASE.PROCUREMENT,
        "last_node": "rfq_validator_node",
    }


__all__ = ["rfq_validator_node"]
