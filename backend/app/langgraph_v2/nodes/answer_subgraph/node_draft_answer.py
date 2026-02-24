from __future__ import annotations

import hashlib
from typing import Any, Dict, List

import structlog

from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState

logger = structlog.get_logger("langgraph_v2.answer_subgraph.draft_answer")


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


def node_draft_answer(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
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
    draft_text = _render_contract_draft(contract)

    flags = dict(state.flags or {})
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

