from __future__ import annotations

"""Verify drafted answers against contract-level Evidence Authority.

This node enforces two guarantees:
1. State-Race-Condition Protection: the draft must be bound to the same
   contract hash that was active when drafting started.
2. Claim consistency: rendered numeric claims and mandatory disclaimers must
   match the ``AnswerContract``.

The verification result routes the subgraph into deterministic patching or
safe fallback paths.
"""

import hashlib
import re
from typing import Any, Dict, List, Set

import structlog

from app.langgraph_v2.state.sealai_state import SealAIState, VerificationReport

logger = structlog.get_logger("langgraph_v2.answer_subgraph.verify_claims")

_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")
# Match bracket references like [1], [2], or [1-3]. These are citation/list
# markers and not factual claims, so they are excluded from numeric evidence checks.
_BRACKET_REFERENCE_PATTERN = re.compile(r"\[\s*\d+(?:\s*[-,]\s*\d+)*\s*\]")
# Match ordered list prefixes at line start (e.g. "1. ", "12. ").
# These formatting ordinals are not technical measurements.
_LIST_PREFIX_PATTERN = re.compile(r"(?m)^\s*\d+\.\s+")
_SUSPICIOUS_HOMOGLYPH_BAR_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s*[^\x00-\x7f]ar\b")
_SUSPICIOUS_DEGREE_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s*˚\s*[cC]\b")


def _strip_formatting_numbers(text: str) -> str:
    """Remove formatting-only number markers from free text.

    Args:
        text: Candidate answer text.

    Returns:
        Text with citation/list numbering removed.
    """
    sanitized = _BRACKET_REFERENCE_PATTERN.sub(" ", text or "")
    sanitized = _LIST_PREFIX_PATTERN.sub("", sanitized)
    return sanitized


def _numbers_from_text(text: str, *, ignore_formatting_numbers: bool = False) -> Set[str]:
    """Extract normalized numeric tokens from text.

    Args:
        text: Source text for extraction.
        ignore_formatting_numbers: When ``True``, citation and ordered-list
            numbers are removed before extraction to prevent false positives.

    Returns:
        Set of numeric tokens found in text.
    """
    normalized = _strip_formatting_numbers(text) if ignore_formatting_numbers else (text or "")
    return set(_NUMBER_PATTERN.findall(normalized))


def _find_suspicious_unicode_spans(text: str) -> List[str]:
    spans: List[str] = []
    for pattern in (_SUSPICIOUS_HOMOGLYPH_BAR_PATTERN, _SUSPICIOUS_DEGREE_PATTERN):
        for match in pattern.finditer(text or ""):
            spans.append(match.group(0))
    return spans


def _build_failure_span(
    *,
    reason: str,
    expected_value: str,
    wrong_span: str = "",
) -> Dict[str, str]:
    """Create a structured verification failure span.

    Args:
        reason: Machine-readable failure reason.
        expected_value: Required value from contract/evidence.
        wrong_span: Observed mismatching value in draft text.

    Returns:
        Serializable failure span record.
    """
    return {
        "reason": reason,
        "expected_value": expected_value,
        "wrong_span": wrong_span,
    }


def node_verify_claims(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Validate drafted answer content against the answer contract.

    The check sequence is intentionally strict:
    - verify contract hash continuity (State-Race-Condition Protection),
    - reject empty drafts,
    - compare numeric claims against contract Evidence Authority,
    - ensure required disclaimers are present.

    Formatting-only numbers (e.g., ``[1]`` or ``1.`` list markers) are ignored
    during rendered-text extraction so they do not trigger
    ``unexpected_number`` failures.

    Args:
        state: Current graph state.
        *_args: Unused positional arguments for LangGraph compatibility.
        **_kwargs: Unused keyword arguments for LangGraph compatibility.

    Returns:
        State patch with ``verification_report`` and node marker.
    """
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
    rendered_numbers = _numbers_from_text(draft_text, ignore_formatting_numbers=True)

    missing_numbers = sorted(expected_numbers - rendered_numbers)
    unexpected_numbers = sorted(rendered_numbers - expected_numbers)
    missing_disclaimers = [text for text in contract.required_disclaimers if text not in draft_text]
    suspicious_unicode_spans = _find_suspicious_unicode_spans(draft_text)

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
    for span in suspicious_unicode_spans:
        failed_claim_spans.append(
            _build_failure_span(reason="suspicious_unicode", expected_value="", wrong_span=span)
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
        suspicious_unicode=len(suspicious_unicode_spans),
    )
    return {"verification_report": report, "last_node": "node_verify_claims"}


__all__ = ["node_verify_claims"]
