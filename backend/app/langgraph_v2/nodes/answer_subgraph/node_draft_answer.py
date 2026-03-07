from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Dict, List

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.langgraph_v2.nodes.answer_subgraph.state import AnswerSubgraphState
from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.prompt_blocks import render_challenger_gate
from app.langgraph_v2.utils.redaction import redact_operating_context

logger = structlog.get_logger("langgraph_v2.answer_subgraph.draft_answer")
_DRAFT_LLM: Any | None = None
_LOW_QUALITY_RAG_FALLBACK_TEXT = (
    "Dazu habe ich in meinen technischen Datenblaettern gerade keinen exakten Treffer gefunden. "
    "Wenn du mir spezifische Einsatzbedingungen (wie Medium, Temperatur und Druck) nennst, "
    "kann ich gezielter fuer dich suchen!"
)
_GENERIC_MATERIAL_LABELS = frozenset({"technical datasheet", "technical document", "datenblatt", "werkstoff"})
_PATH_PATTERN = re.compile(r"(?:^|[\s(])(?:[a-zA-Z]:\\|/)[^\s)]+")


def _render_block(title: str, entries: List[str]) -> List[str]:
    lines = [title]
    if entries:
        lines.extend(entries)
    else:
        lines.append("- none")
    return lines


def _render_fact_sheet(contract: AnswerContract) -> str:
    lines: List[str] = []
    # Redact resolved parameters for text generation consistency
    redacted_params = redact_operating_context(contract.resolved_parameters)
    lines.extend(
        _render_block(
            "Resolved Parameters:",
            [f"- {key}: {value}" for key, value in sorted(redacted_params.items())],
        )
    )
    lines.append("")
    lines.extend(
        _render_block(
            "Calculation Results:",
            [f"- {key}: {value}" for key, value in sorted(contract.calc_results.items())],
        )
    )
    lines.append("")
    lines.extend(
        _render_block(
            "Selected Fact IDs:",
            [f"- {fact_id}" for fact_id in contract.selected_fact_ids],
        )
    )
    lines.append("")
    lines.extend(
        _render_block(
            "Required Disclaimers:",
            [f"- {item}" for item in contract.required_disclaimers],
        )
    )
    lines.append("")
    lines.append(f"Respond With Uncertainty: {contract.respond_with_uncertainty}")
    return "\n".join(lines).strip()


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


def _extract_langgraph_config(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Any | None:
    config = kwargs.get("config")
    if config is not None:
        return config
    if args:
        candidate = args[0]
        if isinstance(candidate, dict):
            return candidate
    return None


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def _working_profile_get(state: SealAIState, field: str, default: Any = None) -> Any:
    working_profile = getattr(state, "working_profile", None)
    if working_profile is None:
        return default
    if isinstance(working_profile, dict):
        return working_profile.get(field, default)
    return getattr(working_profile, field, default)


def _sanitize_evidence_snippet(value: Any) -> str:
    lines: List[str] = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("- dokument:"):
            continue
        if lower.startswith("quelle:"):
            continue
        if lower.startswith("[authority="):
            continue
        if "| abschnitt:" in lower or "| section:" in lower or "| score:" in lower:
            continue
        line = _PATH_PATTERN.sub(" ", line)
        line = re.sub(r"\s+", " ", line).strip(" -")
        if line:
            lines.append(line)
    return " ".join(lines).strip()


def _extract_best_effort_snippet(state: SealAIState) -> str:
    for source in list(getattr(state.system, "sources", []) or []):
        snippet = _as_dict(source).get("snippet") or _as_dict(source).get("text")
        cleaned = _sanitize_evidence_snippet(snippet)
        if cleaned:
            return cleaned

    panel_material = _as_dict(getattr(getattr(state.reasoning, "working_memory", None), "panel_material", {}) or {})
    for hit in list(panel_material.get("technical_docs") or []):
        if not isinstance(hit, dict):
            continue
        cleaned = _sanitize_evidence_snippet(hit.get("snippet") or hit.get("text"))
        if cleaned:
            return cleaned
    return ""


def _compress_evidence_hint(text: str, max_chars: int = 220) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if not compact:
        return ""
    sentence_match = re.match(r"(.{1,%d}?[.!?])(?:\s|$)" % max_chars, compact)
    if sentence_match:
        return sentence_match.group(1).strip()
    if len(compact) <= max_chars:
        return compact
    truncated = compact[:max_chars].rsplit(" ", 1)[0].strip()
    return f"{truncated}..." if truncated else compact[:max_chars].strip()


def _extract_requested_subject(state: SealAIState) -> str:
    user_text = ""
    for msg in reversed(list(state.conversation.messages or [])):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("human", "user"):
            user_text = _chunk_to_text(msg).strip()
            break

    try:
        from app.langgraph_v2.nodes.nodes_frontdoor import extract_trade_name_candidate
    except Exception:
        extract_trade_name_candidate = None

    if callable(extract_trade_name_candidate):
        candidate = extract_trade_name_candidate(user_text)
        if candidate:
            return candidate

    material_choice = _working_profile_get(state, "material_choice", {}) or {}
    if isinstance(material_choice, dict):
        material = str(material_choice.get("material") or "").strip()
        if material and material.lower() not in _GENERIC_MATERIAL_LABELS:
            return material
    return ""


def build_low_quality_rag_fallback_text(state: SealAIState) -> str:
    subject = _extract_requested_subject(state)
    evidence_hint = _compress_evidence_hint(_extract_best_effort_snippet(state))
    lead = (
        f"Zu {subject} habe ich in den verfuegbaren technischen Unterlagen gerade keinen belastbaren Volltreffer gefunden."
        if subject
        else "Ich habe in den verfuegbaren technischen Unterlagen gerade keinen belastbaren Volltreffer gefunden."
    )
    if evidence_hint:
        return (
            f"{lead} Die vorhandenen Hinweise deuten am ehesten auf Folgendes hin: {evidence_hint} "
            "Fuer eine belastbare technische Einordnung brauche ich das konkrete Datenblatt oder die genaue Werkstoffbezeichnung."
        )
    return (
        f"{lead} Ich moechte deshalb keine ungesicherten Eigenschaften behaupten. "
        "Fuer eine belastbare Einordnung brauche ich das konkrete Datenblatt oder die genaue Werkstoffbezeichnung."
    )


def _build_deterministic_constraints(state: SealAIState) -> str:
    tile_obj = _working_profile_get(state, "live_calc_tile")
    if tile_obj is None:
        return ""
    if not _as_dict(tile_obj):
        return ""
    return render_challenger_gate(tile=tile_obj)


def _should_use_detached_knowledge_instruction(state: SealAIState) -> bool:
    flags = _as_dict(getattr(state.reasoning, "flags", {}) or {})
    intent_category = str(
        getattr(state.reasoning, "intent_category", None) or flags.get("frontdoor_intent_category") or ""
    ).strip().upper()
    if intent_category == "MATERIAL_RESEARCH":
        return True

    intent_goal = str(getattr(getattr(state.conversation, "intent", None), "goal", "") or "").strip().lower()
    if intent_goal in {"explanation_or_comparison", "smalltalk"}:
        return True
    return False


def _get_draft_llm() -> Any:
    global _DRAFT_LLM
    if _DRAFT_LLM is None:
        from app.langgraph_v2.utils.llm_factory import LazyChatOpenAI

        _DRAFT_LLM = LazyChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0,
            cache=False,
            max_tokens=800,
            streaming=True,
        )
    return _DRAFT_LLM


async def node_draft_answer(state: AnswerSubgraphState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    # STEP 3: Debugging Logging
    if not _working_profile_get(state, "live_calc_tile"):
        logger.warning("DRAFT_ANSWER_BLIND_SPOT: live_calc_tile is missing in subgraph state!")
    if not _working_profile_get(state, "engineering_profile"):
        logger.warning("DRAFT_ANSWER_BLIND_SPOT: working_profile is missing in subgraph state!")

    contract = state.system.answer_contract
    if contract is None or contract.obsolete:
        logger.error("draft_answer.missing_or_obsolete_contract")
        return {
                   "system": {
                       "draft_text": "",
                       "draft_base_hash": None,
                       "error": "AnswerContract missing or obsolete in node_draft_answer",
                   },
                   "reasoning": {
                       "last_node": "node_draft_answer",
                   },
               }

    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    flags = deepcopy(state.reasoning.flags or {})
    flags["answer_contract_hash"] = contract_hash
    is_low_quality_rag = bool(flags.get("rag_low_quality_results", False))
    is_contract_empty = not bool(contract.selected_fact_ids or contract.calc_results or contract.resolved_parameters)
    if is_low_quality_rag or is_contract_empty:
        logger.warning(
            "Bypassing draft LLM due to missing factual grounding",
            rag_low_quality_results=is_low_quality_rag,
            is_contract_empty=is_contract_empty,
        )
        logger.info(
            "draft_answer.fallback_short_circuit",
            contract_hash=contract_hash,
            rag_low_quality_results=is_low_quality_rag,
            is_contract_empty=is_contract_empty,
        )
        sidekick_message = build_low_quality_rag_fallback_text(state)
        return {
                   "system": {
                       "draft_text": sidekick_message,
                       "draft_base_hash": contract_hash,
                   },
                   "reasoning": {
                       "flags": flags,
                       "last_node": "node_draft_answer",
                   },
               }

    fact_sheet_text = _render_fact_sheet(contract)
    config = _extract_langgraph_config(_args, _kwargs)

    constraints = _build_deterministic_constraints(state)
    if constraints:
        logger.info("draft_answer.deterministic_constraints_injected", constraints_len=len(constraints))

    system_prompt = render_template(
        "final_answer_composer.j2",
        {
            "challenger_gate_text": constraints,
            "working_profile_json": json.dumps(redact_operating_context(_as_dict(_working_profile_get(state, "engineering_profile"))), ensure_ascii=False),
            "calculation_results_json": json.dumps(_as_dict(_working_profile_get(state, "calc_results")), ensure_ascii=False),
            "rag_context": getattr(state.reasoning, "context", "") or "",
            "detached_knowledge_mode": _should_use_detached_knowledge_instruction(state),
        },
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"VERIFIED FACT SHEET:\n{fact_sheet_text}"),
    ]
    chunks: List[str] = []
    llm = _get_draft_llm()
    async for chunk in llm.astream(messages, config=config):
        text = _chunk_to_text(chunk)
        if text:
            chunks.append(text)
    draft_text = "".join(chunks).strip()
    if not draft_text:
        draft_text = fact_sheet_text

    logger.info(
        "draft_answer.done",
        contract_hash=contract_hash,
        draft_len=len(draft_text),
    )
    return {
               "system": {
                   "draft_text": draft_text,
                   "draft_base_hash": contract_hash,
               },
               "reasoning": {
                   "flags": flags,
                   "last_node": "node_draft_answer",
               },
           }


__all__ = ["build_low_quality_rag_fallback_text", "node_draft_answer"]
