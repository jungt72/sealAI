"""State curator node for Golden Parameters."""

from __future__ import annotations

from typing import Any, Dict

import structlog

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, TechnicalParameters, WorkingMemory
from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance

logger = structlog.get_logger("langgraph_v2.nodes_curator")

try:  # Optional integration (may be stubbed in tests)
    from app.services.langgraph.tools import long_term_memory as ltm
except Exception:  # pragma: no cover
    ltm = None


def _collect_rag_context(state: SealAIState) -> str:
    wm = state.working_memory or WorkingMemory()
    fragments = []
    for key in ("panel_norms_rag", "comparison_notes"):
        block = getattr(wm, key, None)
        if isinstance(block, dict):
            text = block.get("rag_context") or block.get("context")
            if isinstance(text, str) and text.strip():
                fragments.append(text.strip())
    return "\n".join(fragments)


def _load_ltm_parameters(state: SealAIState) -> Dict[str, Any]:
    if not ltm:
        return {}
    try:
        return ltm.fetch_latest_parameters(
            user_id=state.user_id,
            tenant_id=state.tenant_id,
            chat_id=state.thread_id,
        ) or {}
    except Exception as exc:  # pragma: no cover
        logger.warning("ltm_fetch_failed", error=str(exc))
        return {}


def _persist_golden_parameters(state: SealAIState, params: Dict[str, Any]) -> None:
    if not ltm or not params:
        return
    try:
        ltm.upsert_parameters(
            user_id=state.user_id,
            tenant_id=state.tenant_id,
            chat_id=state.thread_id,
            parameters=params,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("ltm_upsert_failed", error=str(exc))


def state_curator_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, Any]:
    """
    Curate "Golden Parameters" by merging:
    - Long-term memory (Postgres)
    - RAG context (Qdrant)
    - Current session parameters (user wins)
    """
    params = state.parameters.as_dict() if state.parameters else {}
    provenance = state.parameter_provenance or {}

    ltm_params = _load_ltm_parameters(state)
    rag_text = _collect_rag_context(state)
    rag_params = extract_parameters_from_text(rag_text) if rag_text else {}

    merged, prov = apply_parameter_patch_with_provenance(
        params,
        ltm_params,
        provenance,
        source="ltm",
    )
    merged, prov = apply_parameter_patch_with_provenance(
        merged,
        rag_params,
        prov,
        source="rag",
    )

    golden = dict(merged)
    _persist_golden_parameters(state, golden)

    wm = state.working_memory or WorkingMemory()
    try:
        wm = wm.model_copy(
            update={
                "curator_notes": {
                    "ltm_used": bool(ltm_params),
                    "rag_used": bool(rag_params),
                    "golden_param_count": len(golden),
                }
            }
        )
    except Exception:
        pass

    logger.info(
        "state_curator_node_exit",
        run_id=state.run_id,
        thread_id=state.thread_id,
        ltm_params=len(ltm_params or {}),
        rag_params=len(rag_params or {}),
    )

    return {
        "parameters": TechnicalParameters.model_validate(merged),
        "parameter_provenance": prov,
        "golden_parameters": golden,
        "golden_parameter_sources": prov,
        "working_memory": wm,
        "phase": PHASE.PREFLIGHT_PARAMETERS,
        "last_node": "state_curator_node",
    }


__all__ = ["state_curator_node"]
