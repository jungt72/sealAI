from __future__ import annotations

from typing import Any, Dict, cast

from langchain_core.messages import AIMessage

from app.agent.agent.state import RWDRFlowState, RWDRSelectorState, RWDRStage, SealingAIState
from app.agent.agent.rwdr_patch_parser import next_rwdr_question, parse_rwdr_patch_for_field
from app.agent.domain.rwdr import (
    RWDRConfidenceField,
    RWDRSelectorInputDTO,
    RWDRSelectorInputPatchDTO,
    build_default_rwdr_selector_config,
)
from app.agent.domain.rwdr_core import derive_rwdr_core
from app.agent.domain.rwdr_decision import decide_rwdr_output

STAGE_1_FIELDS: tuple[RWDRConfidenceField, ...] = (
    "motion_type",
    "shaft_diameter_mm",
    "max_speed_rpm",
    "pressure_profile",
    "inner_lip_medium_scenario",
    "maintenance_mode",
)


def _get_rwdr_state(sealing_state: SealingAIState) -> RWDRSelectorState:
    """Return the active RWDR runtime slice.

    Flow control lives here, not in `router.py` and not in generic `logic.py`.
    Core engineering stays in `domain/rwdr_core.py`; final deterministic
    classification stays in `domain/rwdr_decision.py`.
    """
    rwdr_state = sealing_state.setdefault("rwdr", {})
    return cast(RWDRSelectorState, rwdr_state)


def _normalize_collected_fields(rwdr_state: RWDRSelectorState) -> Dict[str, Any]:
    flow = cast(RWDRFlowState, rwdr_state.setdefault("flow", {}))
    collected = dict(flow.get("collected_fields", {}))
    if rwdr_state.get("draft") is not None:
        collected.update(_patch_payload(rwdr_state["draft"]))
    if rwdr_state.get("input") is not None:
        collected.update(rwdr_state["input"].model_dump(exclude_none=True))
    flow["collected_fields"] = collected
    return collected


def _patch_payload(rwdr_patch: RWDRSelectorInputPatchDTO) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for field_name in rwdr_patch.model_fields_set:
        value = getattr(rwdr_patch, field_name)
        if field_name == "confidence":
            if value:
                payload["confidence"] = dict(value)
            continue
        if value is not None:
            payload[field_name] = value
    return payload


def merge_rwdr_patch(
    sealing_state: SealingAIState,
    rwdr_input: RWDRSelectorInputDTO | None = None,
    rwdr_input_patch: RWDRSelectorInputPatchDTO | None = None,
) -> RWDRSelectorState:
    """Merge explicit structured RWDR input into the active flow state.

    Only explicitly set structured values may overwrite previous values.
    Missing fields and `None` never clear valid state implicitly.
    """
    rwdr_state = _get_rwdr_state(sealing_state)
    flow = cast(RWDRFlowState, rwdr_state.setdefault("flow", {}))
    flow["active"] = True

    merged_fields = dict(flow.get("collected_fields", {}))
    if rwdr_state.get("draft") is not None:
        merged_fields.update(_patch_payload(rwdr_state["draft"]))
    if rwdr_state.get("input") is not None:
        merged_fields.update(rwdr_state["input"].model_dump(exclude_none=True))

    merged_confidence = dict(merged_fields.get("confidence", {}))

    if rwdr_input is not None:
        full_payload = rwdr_input.model_dump(exclude_none=True)
        merged_fields.update({key: value for key, value in full_payload.items() if key != "confidence"})
        merged_confidence.update(full_payload.get("confidence", {}))

    if rwdr_input_patch is not None:
        patch_payload = _patch_payload(rwdr_input_patch)
        merged_fields.update({key: value for key, value in patch_payload.items() if key != "confidence"})
        merged_confidence.update(patch_payload.get("confidence", {}))

    if merged_confidence:
        merged_fields["confidence"] = merged_confidence
    else:
        merged_fields.pop("confidence", None)

    rwdr_state["draft"] = RWDRSelectorInputPatchDTO.model_validate(merged_fields)
    flow["collected_fields"] = merged_fields
    rwdr_state.pop("input", None)
    rwdr_state.pop("derived", None)
    rwdr_state.pop("output", None)
    flow["ready_for_decision"] = False
    flow["decision_executed"] = False
    return rwdr_state


def is_rwdr_flow_active(state: Dict[str, Any]) -> bool:
    sealing_state = state.get("sealing_state", {})
    rwdr_state = sealing_state.get("rwdr", {})
    flow = rwdr_state.get("flow", {})
    return bool(flow.get("active")) and bool(flow.get("collected_fields") or rwdr_state.get("draft") or rwdr_state.get("input"))


def required_stage_2_fields(collected_fields: Dict[str, Any]) -> list[RWDRConfidenceField]:
    required: list[RWDRConfidenceField] = []
    medium_scenario = collected_fields.get("inner_lip_medium_scenario")
    contamination = collected_fields.get("external_contamination_class")
    vertical_flag = collected_fields.get("vertical_shaft_flag")

    if medium_scenario in {"oil_bath", "splash_oil", "grease", "water_or_aqueous"}:
        required.append("external_contamination_class")

    if contamination == "mud_high_pressure_abrasive":
        required.append("available_width_mm")

    if collected_fields.get("motion_type") != "linear_stroke":
        required.append("installation_over_edges_flag")

    if medium_scenario == "oil_bath":
        required.append("vertical_shaft_flag")

    if vertical_flag is True and medium_scenario == "oil_bath":
        required.append("medium_level_relative_to_seal")

    seen: set[RWDRConfidenceField] = set()
    ordered: list[RWDRConfidenceField] = []
    for field in required:
        if field not in seen:
            ordered.append(field)
            seen.add(field)
    return ordered


def evaluate_rwdr_flow(sealing_state: SealingAIState) -> RWDRSelectorState:
    """Advance the typed RWDR flow until the next required field or decision."""
    rwdr_state = _get_rwdr_state(sealing_state)
    config = rwdr_state.setdefault("config", build_default_rwdr_selector_config())
    rwdr_state["config_version"] = config.config_version
    flow = cast(RWDRFlowState, rwdr_state.setdefault("flow", {}))
    flow["active"] = True

    collected_fields = _normalize_collected_fields(rwdr_state)
    required_stage1_fields = list(STAGE_1_FIELDS)
    missing_stage1 = [field for field in required_stage1_fields if collected_fields.get(field) is None]

    flow["required_stage1_fields"] = required_stage1_fields
    flow["decision_executed"] = False

    if missing_stage1:
        flow["stage"] = cast(RWDRStage, "stage_1")
        flow["required_stage2_fields"] = []
        flow["missing_fields"] = missing_stage1
        flow["next_field"] = missing_stage1[0]
        flow["ready_for_decision"] = False
        rwdr_state.pop("derived", None)
        rwdr_state.pop("output", None)
        return rwdr_state

    provisional_input = RWDRSelectorInputDTO.model_validate(collected_fields)
    provisional_derived = derive_rwdr_core(provisional_input, config)
    provisional_output = decide_rwdr_output(provisional_input, provisional_derived, config)
    if provisional_output.hard_stop is not None:
        flow["stage"] = cast(RWDRStage, "stage_3")
        flow["required_stage2_fields"] = []
        flow["missing_fields"] = []
        flow["next_field"] = None
        flow["ready_for_decision"] = True
        flow["decision_executed"] = True
        rwdr_state["draft"] = RWDRSelectorInputPatchDTO.model_validate(collected_fields)
        rwdr_state["input"] = provisional_input
        rwdr_state["derived"] = provisional_derived
        rwdr_state["output"] = provisional_output
        return rwdr_state

    stage2_fields = required_stage_2_fields(collected_fields)
    missing_stage2 = [field for field in stage2_fields if collected_fields.get(field) is None]
    flow["required_stage2_fields"] = stage2_fields

    if missing_stage2:
        flow["stage"] = cast(RWDRStage, "stage_2")
        flow["missing_fields"] = missing_stage2
        flow["next_field"] = missing_stage2[0]
        flow["ready_for_decision"] = False
        rwdr_state.pop("derived", None)
        rwdr_state.pop("output", None)
        return rwdr_state

    flow["stage"] = cast(RWDRStage, "stage_3")
    flow["missing_fields"] = []
    flow["next_field"] = None
    flow["ready_for_decision"] = True

    rwdr_input = provisional_input
    rwdr_state["draft"] = RWDRSelectorInputPatchDTO.model_validate(collected_fields)
    rwdr_state["input"] = rwdr_input
    rwdr_state["derived"] = derive_rwdr_core(rwdr_input, config)
    rwdr_state["output"] = decide_rwdr_output(rwdr_input, rwdr_state["derived"], config)
    flow["decision_executed"] = True
    return rwdr_state


def build_rwdr_reply(rwdr_state: RWDRSelectorState) -> str:
    flow = cast(RWDRFlowState, rwdr_state.get("flow", {}))
    if not flow.get("ready_for_decision"):
        stage = flow.get("stage", "stage_1")
        missing_fields = ", ".join(flow.get("missing_fields", []))
        next_field = flow.get("next_field")
        question = next_rwdr_question(next_field)
        return f"RWDR {stage} pending. Missing fields: {missing_fields}. Next field: {next_field}. {question}"

    output = rwdr_state.get("output")
    if output is None:
        return "RWDR evaluation pending."

    if output.hard_stop is not None:
        return f"RWDR hard stop: {output.hard_stop}. Type class: {output.type_class}."
    if output.review_flags:
        review_flags = ", ".join(output.review_flags)
        return f"RWDR review required. Type class: {output.type_class}. Review flags: {review_flags}."
    return f"RWDR preselection ready. Type class: {output.type_class}."


def run_rwdr_orchestration(
    sealing_state: SealingAIState,
    latest_user_message: str | None = None,
) -> tuple[SealingAIState, AIMessage]:
    """Run the active RWDR turn.

    The orchestration layer may ask for the next typed field and may attempt a
    bounded single-field patch parse from the latest user message. It must not
    invent values when parsing is unsafe.
    """
    new_sealing_state = dict(sealing_state)
    previous_next_field = new_sealing_state.get("rwdr", {}).get("flow", {}).get("next_field")
    rwdr_state = evaluate_rwdr_flow(new_sealing_state)
    accepted_field: RWDRConfidenceField | None = None
    parse_failed = False

    if latest_user_message and previous_next_field is not None and not rwdr_state["flow"].get("ready_for_decision"):
        parsed_patch = parse_rwdr_patch_for_field(previous_next_field, latest_user_message)
        if parsed_patch is not None:
            merge_rwdr_patch(new_sealing_state, rwdr_input_patch=parsed_patch)
            rwdr_state = evaluate_rwdr_flow(new_sealing_state)
            accepted_field = previous_next_field
        else:
            parse_failed = True

    reply = build_rwdr_reply(rwdr_state)
    if accepted_field is not None and not rwdr_state["flow"].get("ready_for_decision"):
        reply = f"RWDR field accepted: {accepted_field}. {reply}"
    elif accepted_field is not None and rwdr_state["flow"].get("ready_for_decision"):
        reply = f"RWDR field accepted: {accepted_field}. {reply}"
    elif parse_failed and previous_next_field is not None:
        reply = (
            f"RWDR field still missing: {previous_next_field}. "
            f"Input could not be safely structured. {next_rwdr_question(previous_next_field)}"
        )
    return new_sealing_state, AIMessage(content=reply)
