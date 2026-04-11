from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi.encoders import jsonable_encoder
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.agent.state import AgentState
from app.agent.state.case_state import ensure_case_state
from app.services.chat.conversations import upsert_conversation
from app.services.jobs.queue import enqueue_job

logger = logging.getLogger("app.history.persist")
QUEUE_NAME = "jobs:chat_transcripts"
STRUCTURED_CASE_RECORD_TYPE = "agent_structured_case_v1"
CANONICAL_STATE_AUTHORITY = "case_state"


class PersistedStructuredCasePayload(BaseModel):
    case_id: str
    session_id: str
    owner_id: str
    runtime_path: str
    binding_level: str
    canonical_state_authority: str = Field(default=CANONICAL_STATE_AUTHORITY)
    record_type: str = Field(default=STRUCTURED_CASE_RECORD_TYPE)
    sealing_state: Dict[str, Any]
    case_state: Optional[Dict[str, Any]] = None
    persisted_lifecycle: Optional[Dict[str, Any]] = None
    persisted_concurrency_token: Optional[Dict[str, Any]] = None
    working_profile: Dict[str, Any] = Field(default_factory=dict)
    relevant_fact_cards: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    tenant_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


def build_structured_case_storage_key(tenant_id: str, owner_id: str, case_id: str) -> str:
    return f"agent_case:{tenant_id}:{owner_id}:{case_id}"


def _build_legacy_storage_key(owner_id: str, case_id: str) -> str:
    return f"agent_case:{owner_id}:{case_id}"


def _message_preview(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", "") if isinstance(message, BaseMessage) else ""
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def _latest_assistant_preview(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai":
            preview = _message_preview(message)
            if preview:
                return preview
    return "Structured case"


def _first_user_message(messages: list[BaseMessage]) -> str | None:
    for message in messages:
        if getattr(message, "type", "") == "human":
            preview = _message_preview(message)
            if preview:
                return preview
    return None


def _build_persisted_lifecycle(case_state: Dict[str, Any]) -> Dict[str, Any]:
    case_meta = dict(case_state.get("case_meta") or {})
    governance_state = dict(case_state.get("governance_state") or {})
    recipient_selection = dict(case_state.get("recipient_selection") or {})
    rfq_state = dict(case_state.get("rfq_state") or {})

    return {
        "phase": case_meta.get("phase"),
        "release_status": governance_state.get("release_status"),
        "review_state": governance_state.get("review_state"),
        "review_required": governance_state.get("review_required"),
        "selected_partner_id": recipient_selection.get("selected_partner_id"),
        "rfq_admissibility": rfq_state.get("rfq_admissibility"),
        "rfq_status": rfq_state.get("status"),
        "handover_ready": rfq_state.get("handover_ready"),
        "handover_status": rfq_state.get("handover_status"),
        "rfq_confirmed": rfq_state.get("rfq_confirmed"),
        "rfq_handover_initiated": rfq_state.get("rfq_handover_initiated"),
        "rfq_html_report_present": rfq_state.get("rfq_html_report_present"),
    }


def _build_case_meta_concurrency_token(case_state: Dict[str, Any]) -> Dict[str, Any]:
    case_meta = dict(case_state.get("case_meta") or {})
    return {
        "state_revision": case_meta.get("state_revision"),
        "snapshot_parent_revision": case_meta.get("snapshot_parent_revision"),
        "analysis_cycle_id": case_meta.get("analysis_cycle_id"),
    }


def _coalesce_persisted_lifecycle(*sources: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value
    return merged


def _coalesce_persisted_concurrency_token(*sources: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if value is None:
                continue
            merged[key] = value
    return merged


def _apply_persisted_lifecycle(
    state: AgentState,
    persisted_lifecycle: Dict[str, Any] | None,
) -> AgentState:
    if not persisted_lifecycle:
        return state

    case_state = dict(state.get("case_state") or {})
    case_meta = dict(case_state.get("case_meta") or {})
    governance_state = dict(case_state.get("governance_state") or {})
    recipient_selection = dict(case_state.get("recipient_selection") or {})
    rfq_state = dict(case_state.get("rfq_state") or {})
    sealing_state = dict(state.get("sealing_state") or {})
    sealing_cycle = dict(sealing_state.get("cycle") or {})
    sealing_governance = dict(sealing_state.get("governance") or {})
    sealing_review = dict(sealing_state.get("review") or {})
    sealing_selection = dict(sealing_state.get("selection") or {})
    sealing_handover = dict(sealing_state.get("handover") or {})

    if persisted_lifecycle.get("phase"):
        case_meta["phase"] = persisted_lifecycle.get("phase")
    elif sealing_cycle.get("phase"):
        case_meta["phase"] = sealing_cycle.get("phase")

    if persisted_lifecycle.get("release_status") is not None:
        governance_state["release_status"] = persisted_lifecycle.get("release_status")
    elif sealing_governance.get("release_status") is not None:
        governance_state["release_status"] = sealing_governance.get("release_status")

    if persisted_lifecycle.get("review_state") is not None:
        governance_state["review_state"] = persisted_lifecycle.get("review_state")
    elif sealing_review.get("review_state") is not None:
        governance_state["review_state"] = sealing_review.get("review_state")

    if persisted_lifecycle.get("review_required") is not None:
        governance_state["review_required"] = bool(persisted_lifecycle.get("review_required"))
    elif sealing_review.get("review_required") is not None:
        governance_state["review_required"] = bool(sealing_review.get("review_required"))

    if persisted_lifecycle.get("selected_partner_id"):
        recipient_selection["selected_partner_id"] = persisted_lifecycle.get("selected_partner_id")
    elif sealing_selection.get("selected_partner_id"):
        recipient_selection["selected_partner_id"] = sealing_selection.get("selected_partner_id")

    if persisted_lifecycle.get("rfq_admissibility") is not None:
        rfq_state["rfq_admissibility"] = persisted_lifecycle.get("rfq_admissibility")
    elif sealing_governance.get("rfq_admissibility") is not None:
        rfq_state["rfq_admissibility"] = sealing_governance.get("rfq_admissibility")

    if persisted_lifecycle.get("rfq_status") is not None:
        rfq_state["status"] = persisted_lifecycle.get("rfq_status")
    if persisted_lifecycle.get("handover_status") is not None:
        rfq_state["handover_status"] = persisted_lifecycle.get("handover_status")
    elif sealing_handover.get("handover_status") is not None:
        rfq_state["handover_status"] = sealing_handover.get("handover_status")

    if persisted_lifecycle.get("handover_ready") is not None:
        rfq_state["handover_ready"] = bool(persisted_lifecycle.get("handover_ready"))
    elif sealing_handover.get("is_handover_ready") is not None:
        rfq_state["handover_ready"] = bool(sealing_handover.get("is_handover_ready"))

    if persisted_lifecycle.get("rfq_confirmed") is not None:
        rfq_state["rfq_confirmed"] = bool(persisted_lifecycle.get("rfq_confirmed"))
    elif sealing_handover.get("rfq_confirmed") is not None:
        rfq_state["rfq_confirmed"] = bool(sealing_handover.get("rfq_confirmed"))

    if persisted_lifecycle.get("rfq_handover_initiated") is not None:
        rfq_state["rfq_handover_initiated"] = bool(persisted_lifecycle.get("rfq_handover_initiated"))
    elif sealing_handover.get("handover_completed") is not None:
        rfq_state["rfq_handover_initiated"] = bool(sealing_handover.get("handover_completed"))

    if persisted_lifecycle.get("rfq_html_report_present") is not None:
        rfq_state["rfq_html_report_present"] = bool(persisted_lifecycle.get("rfq_html_report_present"))
    elif sealing_handover.get("rfq_html_report") is not None:
        rfq_state["rfq_html_report_present"] = bool(sealing_handover.get("rfq_html_report"))

    case_state["case_meta"] = case_meta
    case_state["governance_state"] = governance_state
    case_state["recipient_selection"] = recipient_selection
    case_state["rfq_state"] = rfq_state
    state["case_state"] = case_state
    return state


def _apply_persisted_concurrency_token(
    state: AgentState,
    persisted_concurrency_token: Dict[str, Any] | None,
) -> AgentState:
    if not persisted_concurrency_token:
        return state

    case_state = dict(state.get("case_state") or {})
    case_meta = dict(case_state.get("case_meta") or {})
    sealing_state = dict(state.get("sealing_state") or {})
    sealing_cycle = dict(sealing_state.get("cycle") or {})

    if persisted_concurrency_token.get("state_revision") is not None:
        case_meta["state_revision"] = persisted_concurrency_token.get("state_revision")
    elif sealing_cycle.get("state_revision") is not None:
        case_meta["state_revision"] = sealing_cycle.get("state_revision")

    if persisted_concurrency_token.get("snapshot_parent_revision") is not None:
        case_meta["snapshot_parent_revision"] = persisted_concurrency_token.get("snapshot_parent_revision")
    elif sealing_cycle.get("snapshot_parent_revision") is not None:
        case_meta["snapshot_parent_revision"] = sealing_cycle.get("snapshot_parent_revision")

    if persisted_concurrency_token.get("analysis_cycle_id") is not None:
        case_meta["analysis_cycle_id"] = persisted_concurrency_token.get("analysis_cycle_id")
    elif sealing_cycle.get("analysis_cycle_id") is not None:
        case_meta["analysis_cycle_id"] = sealing_cycle.get("analysis_cycle_id")

    if case_meta.get("state_revision") is not None:
        case_meta["version"] = case_meta.get("state_revision")

    case_state["case_meta"] = case_meta
    state["case_state"] = case_state
    return state


def _apply_persisted_case_state_reload_overlay(
    state: AgentState,
    persisted_case_state: Dict[str, Any] | None,
) -> AgentState:
    if not persisted_case_state:
        return state

    case_state = dict(state.get("case_state") or {})
    persisted_case_state = dict(persisted_case_state or {})

    persisted_case_meta = dict(persisted_case_state.get("case_meta") or {})
    case_meta = dict(case_state.get("case_meta") or {})
    for key in ("phase", "state_revision", "snapshot_parent_revision", "analysis_cycle_id", "version"):
        if persisted_case_meta.get(key) is not None:
            case_meta[key] = persisted_case_meta.get(key)
    if case_meta:
        case_state["case_meta"] = case_meta

    persisted_governance_state = dict(persisted_case_state.get("governance_state") or {})
    governance_state = dict(case_state.get("governance_state") or {})
    for key in ("release_status", "rfq_admissibility", "review_state", "review_required"):
        if persisted_governance_state.get(key) is not None:
            governance_state[key] = persisted_governance_state.get(key)
    if governance_state:
        case_state["governance_state"] = governance_state

    persisted_recipient_selection = dict(persisted_case_state.get("recipient_selection") or {})
    recipient_selection = dict(case_state.get("recipient_selection") or {})
    if persisted_recipient_selection.get("selected_partner_id"):
        recipient_selection["selected_partner_id"] = persisted_recipient_selection.get("selected_partner_id")
    if recipient_selection:
        case_state["recipient_selection"] = recipient_selection

    persisted_rfq_state = dict(persisted_case_state.get("rfq_state") or {})
    rfq_state = dict(case_state.get("rfq_state") or {})
    for key in (
        "rfq_admissibility",
        "status",
        "handover_ready",
        "handover_status",
        "rfq_confirmed",
        "rfq_handover_initiated",
        "rfq_html_report_present",
    ):
        if persisted_rfq_state.get(key) is not None:
            rfq_state[key] = persisted_rfq_state.get(key)
    if persisted_rfq_state.get("rfq_object"):
        rfq_state["rfq_object"] = dict(persisted_rfq_state.get("rfq_object") or {})
    if rfq_state:
        case_state["rfq_state"] = rfq_state

    state["case_state"] = case_state
    return state


def _apply_persisted_canonical_bounded_slices(
    state: AgentState,
    persisted_case_state: Dict[str, Any] | None,
) -> AgentState:
    if not persisted_case_state:
        return state

    case_state = dict(state.get("case_state") or {})
    persisted_case_state = dict(persisted_case_state or {})

    persisted_rfq_state = dict(persisted_case_state.get("rfq_state") or {})
    rfq_state = dict(case_state.get("rfq_state") or {})
    persisted_rfq_object = dict(persisted_rfq_state.get("rfq_object") or {})
    if persisted_rfq_object:
        rfq_state["rfq_object"] = persisted_rfq_object
    if rfq_state:
        case_state["rfq_state"] = rfq_state

    dispatch_surface_keys: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
        "dispatch_intent": (
            ("dispatch_status", "dispatch_ready"),
            (
            "dispatch_blockers",
            "recipient_refs",
            "selected_manufacturer_ref",
            "recipient_selection",
            "requirement_class",
            "recommendation_identity",
            "rfq_object_basis",
            ),
        ),
        "dispatch_trigger": (
            ("trigger_status", "trigger_allowed"),
            (
            "trigger_blockers",
            "recipient_refs",
            "selected_manufacturer_ref",
            "requirement_class",
            "recommendation_identity",
            ),
        ),
        "dispatch_dry_run": (
            ("dry_run_status", "would_dispatch"),
            (
            "dry_run_blockers",
            "recipient_refs",
            "selected_manufacturer_ref",
            "requirement_class",
            "recommendation_identity",
            "trigger_source",
            ),
        ),
        "dispatch_event": (
            ("event_status", "would_dispatch", "dry_run_status"),
            (
            "event_blockers",
            "recipient_refs",
            "selected_manufacturer_ref",
            "requirement_class",
            "recommendation_identity",
            "trigger_source",
            ),
        ),
        "dispatch_bridge": (
            ("bridge_status", "dry_run_status"),
            (
            "bridge_blockers",
            "recipient_refs",
            "selected_manufacturer_ref",
            "requirement_class",
            "recommendation_identity",
            "bridge_payload_summary",
            ),
        ),
        "dispatch_handoff": (
            ("handoff_status", "bridge_status"),
            (
            "handoff_blockers",
            "recipient_refs",
            "selected_manufacturer_ref",
            "requirement_class",
            "recommendation_identity",
            "payload_summary",
            ),
        ),
        "dispatch_transport_envelope": (
            ("envelope_status", "handoff_status"),
            (
            "envelope_blockers",
            "recipient_refs",
            "selected_manufacturer_ref",
            "requirement_class",
            "recommendation_identity",
            "payload_summary",
            ),
        ),
    }

    for surface_key, (lifecycle_keys, basis_keys) in dispatch_surface_keys.items():
        persisted_surface = dict(persisted_case_state.get(surface_key) or {})
        if not persisted_surface:
            continue
        surface = dict(case_state.get(surface_key) or {})
        for lifecycle_key in lifecycle_keys:
            value = persisted_surface.get(lifecycle_key)
            if value is not None:
                surface[lifecycle_key] = value
        for basis_key in basis_keys:
            value = persisted_surface.get(basis_key)
            if value is None:
                continue
            if isinstance(value, dict):
                surface[basis_key] = dict(value)
            elif isinstance(value, list):
                surface[basis_key] = list(value)
            else:
                surface[basis_key] = value
        if surface:
            case_state[surface_key] = surface

    state["case_state"] = case_state
    return state


def _build_structured_case_payload(
    *,
    tenant_id: str,
    owner_id: str,
    case_id: str,
    state: AgentState,
    runtime_path: str,
    binding_level: str,
) -> PersistedStructuredCasePayload:
    """Build the persisted case payload with case_state as canonical authority.

    sealing_state and working_profile are intentionally still stored for
    orchestration/compat during the migration, but the productive long-term
    truth slices are derived from canonical case_state.
    """
    canonical_state = ensure_case_state(
        state,
        session_id=case_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )
    case_state = jsonable_encoder(canonical_state.get("case_state"))
    persisted_lifecycle = _build_persisted_lifecycle(case_state or {})
    persisted_concurrency_token = _build_case_meta_concurrency_token(case_state or {})
    return PersistedStructuredCasePayload(
        case_id=case_id,
        session_id=case_id,
        owner_id=owner_id,
        runtime_path=runtime_path,
        binding_level=binding_level,
        canonical_state_authority=CANONICAL_STATE_AUTHORITY,
        sealing_state=jsonable_encoder(canonical_state.get("sealing_state", {})),
        case_state=case_state,
        persisted_lifecycle=persisted_lifecycle,
        persisted_concurrency_token=persisted_concurrency_token,
        working_profile=jsonable_encoder(canonical_state.get("working_profile", {})),
        relevant_fact_cards=jsonable_encoder(canonical_state.get("relevant_fact_cards", [])),
        messages=messages_to_dict(canonical_state.get("messages", [])),
        tenant_id=tenant_id,
    )


class ConcurrencyConflictError(Exception):
    pass


def _extract_sealing_cycle_concurrency_token(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    root = dict(payload or {})
    sealing_state = dict(root.get("sealing_state") or {})
    cycle = dict(sealing_state.get("cycle") or {})
    return {
        "state_revision": cycle.get("state_revision"),
        "snapshot_parent_revision": cycle.get("snapshot_parent_revision"),
        "analysis_cycle_id": cycle.get("analysis_cycle_id"),
    }


def _extract_case_meta_concurrency_token(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    root = dict(payload or {})
    case_state = dict(root.get("case_state") or {})
    case_meta = dict(case_state.get("case_meta") or {})
    return {
        "state_revision": case_meta.get("state_revision"),
        "snapshot_parent_revision": case_meta.get("snapshot_parent_revision"),
        "analysis_cycle_id": case_meta.get("analysis_cycle_id"),
    }


def _extract_persisted_concurrency_token(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    root = dict(payload or {})
    token = dict(root.get("persisted_concurrency_token") or {})
    return {
        "state_revision": token.get("state_revision"),
        "snapshot_parent_revision": token.get("snapshot_parent_revision"),
        "analysis_cycle_id": token.get("analysis_cycle_id"),
    }


def _resolve_preferred_concurrency_token(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    for token in (
        _extract_case_meta_concurrency_token(payload),
        _extract_persisted_concurrency_token(payload),
        _extract_sealing_cycle_concurrency_token(payload),
    ):
        if any(value is not None for value in token.values()):
            return token
    return {
        "state_revision": None,
        "snapshot_parent_revision": None,
        "analysis_cycle_id": None,
    }


def _verify_concurrency_token_parity(payload: Dict[str, Any] | None, *, source_label: str) -> Dict[str, Any]:
    sealing_token = _extract_sealing_cycle_concurrency_token(payload)
    preferred_token = _resolve_preferred_concurrency_token(payload)
    if preferred_token != sealing_token:
        logger.warning(
            "Concurrency token parity mismatch for %s: preferred=%s sealing_cycle=%s",
            source_label,
            preferred_token,
            sealing_token,
        )
    return preferred_token


def _resolve_lock_comparison_token(payload: Dict[str, Any] | None, *, source_label: str) -> Dict[str, Any]:
    preferred_token = _verify_concurrency_token_parity(payload, source_label=source_label)
    if all(preferred_token.get(key) is not None for key in ("state_revision", "snapshot_parent_revision", "analysis_cycle_id")):
        return preferred_token
    return _extract_sealing_cycle_concurrency_token(payload)


def _legacy_payload_matches_tenant(
    payload: PersistedStructuredCasePayload,
    *,
    tenant_id: str | None,
) -> bool:
    if tenant_id is None:
        return True
    return payload.tenant_id is not None and payload.tenant_id == tenant_id


async def save_structured_case(
    *,
    tenant_id: str,
    owner_id: str,
    case_id: str,
    state: AgentState,
    runtime_path: str,
    binding_level: str,
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    payload = _build_structured_case_payload(
        tenant_id=tenant_id,
        owner_id=owner_id,
        case_id=case_id,
        state=state,
        runtime_path=runtime_path,
        binding_level=binding_level,
    )
    storage_key = build_structured_case_storage_key(tenant_id, owner_id, case_id)
    messages = state.get("messages", [])
    summary = _latest_assistant_preview(messages)

    incoming_token = _resolve_lock_comparison_token(state, source_label=f"incoming_state:{case_id}")
    incoming_rev = incoming_token.get("state_revision")
    incoming_parent_rev = incoming_token.get("snapshot_parent_revision")
    incoming_cycle_id = incoming_token.get("analysis_cycle_id")

    async with AsyncSessionLocal() as session:
        existing = await session.get(ChatTranscript, storage_key, with_for_update=True)
        if existing:
            existing_token = _resolve_lock_comparison_token(
                existing.metadata_json or {},
                source_label=f"persisted_record:{case_id}",
            )
            db_rev = existing_token.get("state_revision")
            db_cycle_id = existing_token.get("analysis_cycle_id")
            if db_rev is not None and incoming_rev is not None:
                is_valid = incoming_parent_rev == db_rev if incoming_cycle_id != db_cycle_id else incoming_rev == db_rev
                if not is_valid:
                    raise ConcurrencyConflictError(
                        f"State revision conflict on case {case_id}: DB is at revision {db_rev}, but incoming state expects parent {incoming_parent_rev} or same rev {incoming_rev}."
                    )
            existing.user_id = owner_id
            existing.summary = summary
            existing.contributors = {"runtime_path": runtime_path, "binding_level": binding_level}
            existing.metadata_json = payload.model_dump(mode="python")
        else:
            session.add(
                ChatTranscript(
                    chat_id=storage_key,
                    user_id=owner_id,
                    summary=summary,
                    contributors={"runtime_path": runtime_path, "binding_level": binding_level},
                    metadata_json=payload.model_dump(mode="python"),
                )
            )
        await session.commit()

    upsert_conversation(
        owner_id=owner_id,
        conversation_id=case_id,
        tenant_id=tenant_id,
        first_user_message=_first_user_message(messages),
        last_preview=summary,
    )


async def load_structured_case(*, tenant_id: str, owner_id: str, case_id: str) -> AgentState | None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    storage_key = build_structured_case_storage_key(tenant_id, owner_id, case_id)
    loaded_from_legacy = False
    async with AsyncSessionLocal() as session:
        transcript = await session.get(ChatTranscript, storage_key)
        if transcript is None:
            legacy_key = _build_legacy_storage_key(owner_id, case_id)
            transcript = await session.get(ChatTranscript, legacy_key)
            loaded_from_legacy = transcript is not None
        if transcript is None or transcript.user_id != owner_id:
            return None
        metadata = transcript.metadata_json or {}
        if metadata.get("record_type") != STRUCTURED_CASE_RECORD_TYPE:
            return None
        try:
            payload = PersistedStructuredCasePayload.model_validate(metadata)
        except ValidationError as exc:
            logger.warning("Failed to validate structured case payload: %s", exc)
            return None

    if loaded_from_legacy and not _legacy_payload_matches_tenant(payload, tenant_id=tenant_id):
        return None
    if payload.tenant_id is not None and payload.tenant_id != tenant_id:
        return None

    state: AgentState = {
        "messages": messages_from_dict(payload.messages),
        "sealing_state": payload.sealing_state,
        "working_profile": payload.working_profile,
        "relevant_fact_cards": payload.relevant_fact_cards,
    }
    if payload.tenant_id is not None:
        state["tenant_id"] = payload.tenant_id
    if payload.case_state is not None:
        state["case_state"] = payload.case_state
    hydrated_state = ensure_case_state(
        state,
        session_id=payload.case_id,
        runtime_path=payload.runtime_path,
        binding_level=payload.binding_level,
    )
    if payload.canonical_state_authority != CANONICAL_STATE_AUTHORITY:
        logger.warning(
            "Structured case payload for %s uses unexpected canonical_state_authority=%s",
            payload.case_id,
            payload.canonical_state_authority,
        )
    reload_lifecycle = _coalesce_persisted_lifecycle(
        payload.persisted_lifecycle or {},
        _build_persisted_lifecycle(payload.case_state or {}),
    )
    reload_concurrency_token = _coalesce_persisted_concurrency_token(
        payload.persisted_concurrency_token or {},
        _build_case_meta_concurrency_token(payload.case_state or {}),
    )
    hydrated_state = _apply_persisted_case_state_reload_overlay(hydrated_state, payload.case_state or {})
    hydrated_state = _apply_persisted_concurrency_token(hydrated_state, reload_concurrency_token)
    hydrated_state = _apply_persisted_lifecycle(hydrated_state, reload_lifecycle)
    return _apply_persisted_canonical_bounded_slices(hydrated_state, payload.case_state or {})


async def delete_structured_case(*, tenant_id: str, owner_id: str, case_id: str) -> None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    storage_key = build_structured_case_storage_key(tenant_id, owner_id, case_id)
    async with AsyncSessionLocal() as session:
        transcript = await session.get(ChatTranscript, storage_key)
        if transcript is None:
            legacy_key = _build_legacy_storage_key(owner_id, case_id)
            transcript = await session.get(ChatTranscript, legacy_key)
            if transcript is not None:
                metadata = transcript.metadata_json or {}
                if metadata.get("record_type") != STRUCTURED_CASE_RECORD_TYPE:
                    return
                try:
                    payload = PersistedStructuredCasePayload.model_validate(metadata)
                except ValidationError:
                    return
                if not _legacy_payload_matches_tenant(payload, tenant_id=tenant_id):
                    return
        if transcript is None or transcript.user_id != owner_id:
            return
        await session.delete(transcript)
        await session.commit()


async def persist_chat_result(
    *,
    chat_id: str,
    user_id: str,
    summary: str,
    contributors: Any,
    metadata: Dict[str, Any],
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.chat_transcript import ChatTranscript

    if not chat_id or not summary:
        return

    job_payload = {
        "chat_id": chat_id,
        "user_id": user_id,
        "summary": summary,
        "contributors": contributors,
        "metadata": metadata,
    }
    try:
        await enqueue_job(QUEUE_NAME, job_payload)
    except Exception as exc:
        logger.warning("Failed to enqueue transcript job: %s", exc)

    async def _store() -> None:
        try:
            async with AsyncSessionLocal() as session:
                existing = await session.get(ChatTranscript, chat_id)
                if existing:
                    existing.summary = summary
                    existing.contributors = contributors
                    existing.metadata_json = metadata
                else:
                    session.add(
                        ChatTranscript(
                            chat_id=chat_id,
                            user_id=user_id,
                            summary=summary,
                            contributors=contributors,
                            metadata_json=metadata,
                        )
                    )
                await session.commit()
        except Exception as exc:
            logger.error("Persisting chat transcript failed: %s", exc)

    asyncio.create_task(_store())
