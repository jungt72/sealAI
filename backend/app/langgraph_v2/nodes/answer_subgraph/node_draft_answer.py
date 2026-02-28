from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Dict, List

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState

logger = structlog.get_logger("langgraph_v2.answer_subgraph.draft_answer")
_DRAFT_LLM: Any | None = None
_LOW_QUALITY_RAG_FALLBACK_TEXT = (
    "Dazu habe ich in meinen technischen Datenblaettern gerade keinen exakten Treffer gefunden. "
    "Wenn du mir spezifische Einsatzbedingungen (wie Medium, Temperatur und Druck) nennst, "
    "kann ich gezielter fuer dich suchen!"
)


def _render_block(title: str, entries: List[str]) -> List[str]:
    lines = [title]
    if entries:
        lines.extend(entries)
    else:
        lines.append("- none")
    return lines


def _render_fact_sheet(contract: AnswerContract) -> str:
    lines: List[str] = []
    lines.extend(
        _render_block(
            "Resolved Parameters:",
            [f"- {key}: {value}" for key, value in sorted(contract.resolved_parameters.items())],
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


def _should_use_detached_knowledge_instruction(state: SealAIState) -> bool:
    flags = _as_dict(getattr(state, "flags", {}) or {})
    intent_category = str(
        getattr(state, "intent_category", None) or flags.get("frontdoor_intent_category") or ""
    ).strip().upper()
    if intent_category == "MATERIAL_RESEARCH":
        return True

    intent_goal = str(getattr(getattr(state, "intent", None), "goal", "") or "").strip().lower()
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


async def node_draft_answer(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    contract = state.answer_contract
    if contract is None:
        logger.error("draft_answer.missing_contract")
        return {
            "draft_text": "",
            "draft_base_hash": None,
            "last_node": "node_draft_answer",
            "error": "AnswerContract missing in node_draft_answer",
        }

    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    flags = deepcopy(state.flags or {})
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
        sidekick_message = _LOW_QUALITY_RAG_FALLBACK_TEXT
        return {
            "draft_text": sidekick_message,
            "final_answer": sidekick_message,
            "draft_base_hash": contract_hash,
            "flags": flags,
            "last_node": "node_draft_answer",
        }

    fact_sheet_text = _render_fact_sheet(contract)
    config = _extract_langgraph_config(_args, _kwargs)
    system_prompt = (
        "Du bist SealAI, ein hilfreicher technischer Sidekick fuer Dichtungstechnik. "
        "Antworte kurz, klar und natuerlich auf Deutsch. "
        "Nutze ausschliesslich die verifizierten Fakten aus dem Fact Sheet. "
        "Uebernimm alle numerischen Werte und alle Required Disclaimers woertlich. "
        "Erfinde keine zusaetzlichen Zahlen oder Fakten. "
        "Schreibe NIEMALS einen rechtlichen Vertrag. "
        "Verwende keine Begriffe wie 'Vertragsparteien', 'Vertragsgegenstand' oder 'Alpha GmbH'. "
        "Wenn das Fact Sheet leer ist oder keine relevanten Daten enthaelt, antworte freundlich, "
        "dass du dazu gerade keine Daten hast, und frage nach konkreten Parametern "
        "(Temperatur, Druck, Medium)."
    )
    if _should_use_detached_knowledge_instruction(state):
        system_prompt += (
            " The user is asking a general knowledge or material research question. "
            "Provide a comprehensive, general overview based ONLY on the provided RAG context. "
            "DO NOT evaluate, validate, or cross-reference the material against the user's active technical "
            "parameters (e.g., pressure, temperature from the working profile) unless explicitly asked. "
            "Treat this as a detached encyclopedia entry. Ignore previous calculation reports."
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
        "draft_text": draft_text,
        "draft_base_hash": contract_hash,
        "flags": flags,
        "last_node": "node_draft_answer",
    }


__all__ = ["node_draft_answer"]
