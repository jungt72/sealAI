"""Action-chip selection → State Gate binding (Blueprint §4.5, §11.4, §27.5).

An action-chip selection is a deliberate user input, equivalent to a tile
override. This applies it through the **existing** deterministic State Gate
(``reduce_observed_to_normalized`` → ``reduce_normalized_to_asserted``) and tags
the resulting field provenance as ``action_chip_answer``. Pure and deterministic:
no RAG, no LLM, no full graph — a Tier-0 fast-path mutation.
"""

from __future__ import annotations

from typing import Any

from app.agent.state.models import GovernedSessionState, UserOverride
from app.agent.state.reducers import (
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)

ACTION_CHIP_PROVENANCE = "action_chip_answer"


def _stamp_provenance(container: Any, field: str) -> None:
    """Tag the field's provenance as action-chip on a normalized/asserted map."""
    params = getattr(container, "parameters", None)
    if isinstance(params, dict) and field in params:
        param = params[field]
        case_field = getattr(param, "case_field", None)
        if case_field is not None:
            case_field.provenance = ACTION_CHIP_PROVENANCE
        try:
            param.provenance = ACTION_CHIP_PROVENANCE
        except (AttributeError, ValueError):  # pragma: no cover - defensive
            pass
    assertions = getattr(container, "assertions", None)
    if isinstance(assertions, dict) and field in assertions:
        claim = assertions[field]
        case_field = getattr(claim, "case_field", None)
        if case_field is not None:
            case_field.provenance = ACTION_CHIP_PROVENANCE
        try:
            claim.provenance = ACTION_CHIP_PROVENANCE
        except (AttributeError, ValueError):  # pragma: no cover - defensive
            pass


def bind_action_chip_selection(
    state: GovernedSessionState,
    *,
    field: str,
    value: Any,
    unit: str | None = None,
    turn_index: int = 0,
) -> GovernedSessionState:
    """Mutate ``state`` for an action-chip selection via the State Gate.

    Records the selection as a :class:`UserOverride`, re-derives normalized and
    asserted state through the deterministic reducers (the State Gate decides
    value and conflicts), then tags provenance ``action_chip_answer``.
    """
    field_name = str(field or "").strip()
    if not field_name:
        return state

    override = UserOverride(
        field_name=field_name,
        override_value=value,
        override_unit=unit,
        turn_index=turn_index,
    )
    observed = state.observed.with_override(override)
    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)

    _stamp_provenance(normalized, field_name)
    _stamp_provenance(asserted, field_name)

    return state.model_copy(
        update={
            "observed": observed,
            "normalized": normalized,
            "asserted": asserted,
        }
    )
