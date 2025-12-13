from __future__ import annotations

from typing import Any, Dict

from app.langgraph_v2.state import SealAIState


def build_confirm_checkpoint_payload(state: SealAIState) -> Dict[str, Any]:
    coverage_score = float(getattr(state, "coverage_score", 0.0) or 0.0)
    coverage_score = max(0.0, min(1.0, coverage_score))
    coverage_gaps = list(getattr(state, "coverage_gaps", None) or [])
    return {
        "type": "confirm_checkpoint",
        "phase": state.phase or "confirm",
        "recommendation_go": bool(getattr(state, "recommendation_go", False)),
        "coverage_score": coverage_score,
        "coverage_gaps": coverage_gaps,
        "text": state.final_text or "",
    }


__all__ = ["build_confirm_checkpoint_payload"]
