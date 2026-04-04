from __future__ import annotations

from app.agent.domain.medium_registry import (
    classify_medium_text,
    classify_medium_value,
)
from app.agent.state.models import (
    MediumCaptureState,
    MediumClassificationState,
    NormalizedState,
    ObservedState,
)


def derive_medium_capture(
    *,
    message: str,
    observed: ObservedState,
    previous: MediumCaptureState | None = None,
) -> MediumCaptureState:
    capture, _ = classify_medium_text(message)
    existing = previous if isinstance(previous, MediumCaptureState) else MediumCaptureState()

    merged_mentions: list[str] = list(existing.raw_mentions)
    seen = {item.casefold() for item in merged_mentions}
    for mention in capture.raw_mentions:
        if mention.casefold() in seen:
            continue
        seen.add(mention.casefold())
        merged_mentions.append(mention)

    if capture.primary_raw_text:
        primary_raw_text = capture.primary_raw_text
        source_turn_index = max(observed.source_turns) if observed.source_turns else 0
        source_turn_ref = f"turn:{source_turn_index}"
    else:
        primary_raw_text = existing.primary_raw_text
        source_turn_index = existing.source_turn_index
        source_turn_ref = existing.source_turn_ref

    return MediumCaptureState(
        raw_mentions=merged_mentions,
        primary_raw_text=primary_raw_text,
        source_turn_ref=source_turn_ref,
        source_turn_index=source_turn_index,
    )


def derive_medium_classification(
    *,
    capture: MediumCaptureState,
    normalized: NormalizedState,
    previous: MediumClassificationState | None = None,
) -> MediumClassificationState:
    normalized_medium = normalized.parameters.get("medium")
    seed_value = None
    if normalized_medium is not None and normalized_medium.value is not None:
        seed_value = str(normalized_medium.value).strip()
    elif capture.primary_raw_text:
        seed_value = capture.primary_raw_text

    decision = classify_medium_value(seed_value)
    if decision.status == "unavailable" and isinstance(previous, MediumClassificationState):
        return previous

    return MediumClassificationState(
        canonical_label=decision.canonical_label,
        family=decision.family,
        confidence=decision.confidence,
        status=decision.status,
        normalization_source=decision.normalization_source,
        mapping_confidence=decision.mapping_confidence,
        matched_alias=decision.matched_alias,
        source_registry_key=decision.registry_key,
        followup_question=decision.followup_question,
    )
