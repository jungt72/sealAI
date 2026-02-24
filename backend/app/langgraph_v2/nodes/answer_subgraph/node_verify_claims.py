from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Set

import structlog

from app.langgraph_v2.state.sealai_state import SealAIState, VerificationReport

logger = structlog.get_logger("langgraph_v2.answer_subgraph.verify_claims")

_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _numbers_from_text(text: str) -> Set[str]:
    return set(_NUMBER_PATTERN.findall(text or ""))


def _build_failure_span(
    *,
    reason: str,
    expected_value: str,
    wrong_span: str = "",
) -> Dict[str, str]:
    return {
        "reason": reason,
        "expected_value": expected_value,
        "wrong_span": wrong_span,
    }


def node_verify_claims(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    draft_text = str(state.draft_text or "")
    draft_hash = hashlib.sha256(draft_text.encode()).hexdigest()

    # CRITICAL GUARD
    if state.answer_contract is None or hashlib.sha256(state.answer_contract.model_dump_json().encode()).hexdigest() != state.draft_base_hash:
        contract_hash = (
            hashlib.sha256(state.answer_contract.model_dump_json().encode()).hexdigest()
            if state.answer_contract is not None
            else ""
        )
        report = VerificationReport(
            contract_hash=contract_hash,
            draft_hash=draft_hash,
            status="fail",
            failure_type="state_race_condition",
            failed_claim_spans=[
                _build_failure_span(
                    reason="state_race_condition",
                    expected_value=state.draft_base_hash or "",
                    wrong_span=contract_hash,
                )
            ],
        )
        logger.error(
            "verify_claims.state_race_condition",
            contract_hash=contract_hash,
            draft_base_hash=state.draft_base_hash,
        )
        return {"verification_report": report, "last_node": "node_verify_claims"}

    if not draft_text.strip():
        report = VerificationReport(
            contract_hash=state.draft_base_hash or "",
            draft_hash=draft_hash,
            status="fail",
            failure_type="abort",
            failed_claim_spans=[_build_failure_span(reason="empty_draft", expected_value="non_empty_draft")],
        )
        logger.error("verify_claims.empty_draft")
        return {"verification_report": report, "last_node": "node_verify_claims"}

    contract = state.answer_contract
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    expected_numbers = _numbers_from_text(contract.model_dump_json())
    rendered_numbers = _numbers_from_text(draft_text)

    missing_numbers = sorted(expected_numbers - rendered_numbers)
    unexpected_numbers = sorted(rendered_numbers - expected_numbers)
    missing_disclaimers = [text for text in contract.required_disclaimers if text not in draft_text]

    failed_claim_spans: List[Dict[str, str]] = []
    for number in missing_numbers:
        failed_claim_spans.append(_build_failure_span(reason="missing_number", expected_value=number))
    for number in unexpected_numbers:
        failed_claim_spans.append(
            _build_failure_span(reason="unexpected_number", expected_value="", wrong_span=number)
        )
    for disclaimer in missing_disclaimers:
        failed_claim_spans.append(
            _build_failure_span(reason="missing_disclaimer", expected_value=disclaimer)
        )

    status = "pass" if not failed_claim_spans else "fail"
    failure_type = None if status == "pass" else "render_mismatch"
    report = VerificationReport(
        contract_hash=contract_hash,
        draft_hash=draft_hash,
        status=status,
        failure_type=failure_type,
        failed_claim_spans=failed_claim_spans,
    )
    logger.info(
        "verify_claims.done",
        status=status,
        missing_numbers=len(missing_numbers),
        unexpected_numbers=len(unexpected_numbers),
        missing_disclaimers=len(missing_disclaimers),
    )
    return {"verification_report": report, "last_node": "node_verify_claims"}


__all__ = ["node_verify_claims"]

