from __future__ import annotations

from typing import Any, Dict

import structlog

from app.langgraph_v2.state.sealai_state import SealAIState

logger = structlog.get_logger("langgraph_v2.answer_subgraph.targeted_patch")


def node_targeted_patch(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    report = state.verification_report
    draft_text = str(state.draft_text or "")

    if report is None:
        logger.warning("targeted_patch.no_report")
        return {"last_node": "node_targeted_patch"}
    if report.status == "pass":
        logger.info("targeted_patch.skip_already_pass")
        return {"last_node": "node_targeted_patch"}

    patched = draft_text
    for span in list(report.failed_claim_spans or []):
        wrong_span = str(span.get("wrong_span") or "")
        expected_value = str(span.get("expected_value") or "")
        reason = str(span.get("reason") or "")

        if wrong_span:
            patched = patched.replace(wrong_span, expected_value)
            continue
        if reason == "missing_disclaimer" and expected_value and expected_value not in patched:
            patched = f"{patched.rstrip()}\n{expected_value}".strip()
            continue
        if reason == "missing_number" and expected_value and expected_value not in patched:
            patched = f"{patched.rstrip()}\nValue: {expected_value}".strip()

    flags = dict(state.flags or {})
    attempts = int(flags.get("answer_subgraph_patch_attempts") or 0)
    flags["answer_subgraph_patch_attempts"] = attempts + 1

    logger.info(
        "targeted_patch.done",
        attempts=flags["answer_subgraph_patch_attempts"],
        changed=patched != draft_text,
    )
    return {
        "draft_text": patched,
        "flags": flags,
        "last_node": "node_targeted_patch",
    }


__all__ = ["node_targeted_patch"]

