from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Dict, List

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState

logger = structlog.get_logger("langgraph_v2.answer_subgraph.draft_answer")
_DRAFT_LLM: Any | None = None


def _render_block(title: str, entries: List[str]) -> List[str]:
    lines = [title]
    if entries:
        lines.extend(entries)
    else:
        lines.append("- none")
    return lines


def _render_contract_draft(contract: AnswerContract) -> str:
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
    contract_text = _render_contract_draft(contract)
    config = _extract_langgraph_config(_args, _kwargs)
    messages = [
        SystemMessage(
            content=(
                "Write a concise technical answer in German. "
                "Use only the provided contract facts. "
                "Include all numeric values and all required disclaimers verbatim. "
                "Do not invent additional numbers."
            )
        ),
        HumanMessage(content=f"ANSWER CONTRACT:\n{contract_text}"),
    ]
    chunks: List[str] = []
    llm = _get_draft_llm()
    async for chunk in llm.astream(messages, config=config):
        text = _chunk_to_text(chunk)
        if text:
            chunks.append(text)
    draft_text = "".join(chunks).strip()
    if not draft_text:
        draft_text = contract_text

    flags = deepcopy(state.flags or {})
    flags["answer_contract_hash"] = contract_hash

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
