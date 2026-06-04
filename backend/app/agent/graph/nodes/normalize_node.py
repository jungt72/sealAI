"""
normalize_node — Phase F-C.1, Zone 2

Deterministic parameter normalization.

Responsibility:
    Derive NormalizedState from ObservedState by running the deterministic
    reducer. No LLM, no I/O, no side effects.

Architecture invariants enforced here:
    - NormalizedState is ONLY produced by reduce_observed_to_normalized().
      No direct NormalizedState construction.
    - ObservedState is read-only in this node.
    - AssertedState and GovernanceState remain unchanged.

Reducer semantics (see state/reducers.py for full spec):
    1. User overrides always win for the same field_name.
    2. Among LLM extractions for the same field: highest confidence wins.
       Ties broken by latest turn_index (most recent extraction).
    3. Multiple LLM extractions with different values → ConflictRef (warning).
    4. Confidence 'requires_confirmation' → AssumptionRef (not in parameters).
    5. Confidence confirmed/estimated/inferred → NormalizedParameter.
"""
from __future__ import annotations

import logging

from app.agent.graph import GraphState
from app.agent.state.context_hint_derivation import derive_application_hint, derive_motion_hint
from app.agent.state.medium_derivation import (
    derive_medium_capture,
    derive_medium_classification,
)
from app.agent.state.reducers import reduce_observed_to_normalized

log = logging.getLogger(__name__)


async def normalize_node(state: GraphState) -> GraphState:
    """Zone 2 — Derive NormalizedState from ObservedState.

    Purely deterministic. No LLM, no I/O.
    Calls reduce_observed_to_normalized() and stores the result.
    """
    normalized = reduce_observed_to_normalized(state.observed)
    medium_capture = derive_medium_capture(
        message=state.pending_message,
        observed=state.observed,
        previous=state.medium_capture,
    )
    medium_classification = derive_medium_classification(
        capture=medium_capture,
        normalized=normalized,
        previous=state.medium_classification,
    )
    application_hint = derive_application_hint(
        message=state.pending_message,
        observed=state.observed,
        previous=state.application_hint,
    )
    motion_hint = derive_motion_hint(
        message=state.pending_message,
        observed=state.observed,
        previous=state.motion_hint,
    )

    log.debug(
        "[normalize_node] params=%s conflicts=%d assumptions=%d application_hint=%s motion_hint=%s",
        sorted(normalized.parameters.keys()),
        len(normalized.conflicts),
        len(normalized.assumptions),
        application_hint.label,
        motion_hint.label,
    )

    return state.model_copy(
        update={
            "normalized": normalized,
            "medium_capture": medium_capture,
            "medium_classification": medium_classification,
            "application_hint": application_hint,
            "motion_hint": motion_hint,
        }
    )
