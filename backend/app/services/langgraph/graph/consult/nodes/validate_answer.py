# backend/app/services/langgraph/graph/consult/nodes/validate_answer.py
from __future__ import annotations

import math
from typing import Any, Dict, List
import structlog

from ..state import ConsultState

log = structlog.get_logger(__name__)

def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except Exception:
        return 0.5

def _confidence_from_docs(docs: List[Dict[str, Any]]) -> float:
    """
    Grobe Konfidenzabschätzung aus RAG-Scores.
    Nutzt fused_score, sonst max(vector_score, keyword_score/100).
    Falls Score bereits [0..1], direkt verwenden – sonst sigmoid.
    """
    if not docs:
        return 0.15

    vals: List[float] = []
    for d in docs[:6]:
        vs = d.get("vector_score")
        ks = d.get("keyword_score")
        fs = d.get("fused_score")
        try:
            base = float(fs if fs is not None else max(float(vs or 0.0), float(ks or 0.0) / 100.0))
        except Exception:
            base = 0.0

        if 0.0 <= base <= 1.0:
            vals.append(base)
        else:
            vals.append(_sigmoid(base))

    conf = sum(vals) / max(1, len(vals))
    return max(0.05, min(0.98, conf))

def _top_source(d: Dict[str, Any]) -> str:
    return (d.get("source")
            or (d.get("metadata") or {}).get("source")
            or "")

def validate_answer(state: ConsultState) -> ConsultState:
    """
    Bewertet die Antwortqualität (Konfidenz/Quellen) und MERGT den State,
    ohne RAG-Felder zu verlieren.
    """
    retrieved_docs: List[Dict[str, Any]] = state.get("retrieved_docs") or state.get("docs") or []
    context: str = state.get("context") or ""

    conf = _confidence_from_docs(retrieved_docs)
    needs_more = bool(state.get("needs_more_params")) or conf < 0.35

    validation: Dict[str, Any] = {
        "n_docs": len(retrieved_docs),
        "confidence": round(conf, 3),
        "top_source": _top_source(retrieved_docs[0]) if retrieved_docs else "",
    }

    log.info(
        "validate_answer",
        confidence=validation["confidence"],
        needs_more_params=needs_more,
        n_docs=validation["n_docs"],
        top_source=validation["top_source"],
    )

    return {
        **state,
        "phase": "validate_answer",
        "validation": validation,
        "confidence": conf,
        "needs_more_params": needs_more,
        # explizit erhalten
        "retrieved_docs": retrieved_docs,
        "docs": retrieved_docs,
        "context": context,
    }
