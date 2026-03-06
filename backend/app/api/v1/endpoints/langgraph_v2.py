from __future__ import annotations

"""LangGraph v2 chat endpoint implementing the v13 "Two-Speed Architecture".

Blueprint v13 splits request handling into two coordinated execution tiers:

1. Fast Brain
   A low-latency GPT-4o-mini interceptor that runs before the LangGraph.
   It handles the majority of conversational turns directly:
   greetings, short follow-ups, discovery questions, and immediate deterministic
   calculations via the physics tool. Its primary goal is to keep UX latency in
   the 1-2 second range and update the live digital twin as soon as new
   parameters are known.

2. Slow Brain
   The LangGraph "Expert Council" for heavyweight engineering reasoning. It is
   activated only when the Fast Brain explicitly hands off, typically once the
   conversation has enough technical context for deeper analysis or the user
   requests a full engineering evaluation.

The endpoint therefore has two valid outcomes for the same REST call:

- `chat_continue`: the request is fully answered by the Fast Brain and streamed
  back immediately as SSE without starting the graph.
- `handoff_to_langgraph`: the Fast Brain first syncs extracted parameters and
  deterministic tool outputs into the checkpoint state, then the request
  continues through the LangGraph event multiplexer.

State is organized as four pillars:

- `conversation`: transcript, thread identity, and user-facing message history.
- `working_profile`: the digital twin / engineering profile plus deterministic
  calculator outputs such as `live_calc_tile` and `calc_results`.
- `reasoning`: orchestration metadata, parameter provenance, versions, and flow
  control flags used by the graph.
- `system`: outputs, audit metadata, and operational control state.

The Fast Brain deliberately writes only to the pillars that must survive the
handoff:
- `conversation` when a fast-path answer should be persisted in the transcript.
- `working_profile` for extracted engineering parameters and live physics data.
- `reasoning` for provenance/version bookkeeping of parameter writes.
- never directly to `system`, because final graph outputs and control metadata
  remain the responsibility of the Slow Brain.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.messages.ai import AIMessageChunk
from langgraph.types import Command
from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator
from pydantic.config import ConfigDict

from langgraph._internal._constants import CONFIG_KEY_CHECKPOINTER
from langgraph.errors import InvalidUpdateError

from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2, scope_v2_thread_id
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.contracts import (
    HITLResumeRequest,
    assert_node_exists,
    error_detail,
    is_dependency_unavailable_error,
)
from app.langgraph_v2.utils.confirm_go import ConfirmGoRequest
from app.langgraph_v2.utils.assertion_cycle import build_assertion_cycle_update
from app.langgraph_v2.utils.candidate_semantics import annotate_material_choice
from app.langgraph_v2.utils.rfq_admissibility import normalize_rfq_admissibility_contract, rfq_contract_is_ready
from app.langgraph_v2.utils.parameter_patch import (
    ParametersPatchRequest,
    promote_parameter_patch_to_asserted,
    sanitize_v2_parameter_patch,
    stage_extracted_parameter_patch,
)
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user
from app.services.chat.conversations import upsert_conversation
from app.services.fast_brain.router import FastBrainRouter
from app.services.sse_broadcast import sse_broadcast

try:
    from sse_starlette.sse import EventSourceResponse as NativeEventSourceResponse
except Exception:  # pragma: no cover - optional dependency
    NativeEventSourceResponse = None

router = APIRouter()
logger = logging.getLogger(__name__)
SSE_DEBUG = os.getenv("SEALAI_SSE_DEBUG") == "1"
PARAM_SYNC_DEBUG = os.getenv("SEALAI_PARAM_SYNC_DEBUG") == "1"
DEDUP_TTL_SEC = int(os.getenv("LANGGRAPH_V2_DEDUP_TTL_SEC", "900"))
SSE_RETRY_MS = int(os.getenv("SEALAI_SSE_RETRY_MS", "3000"))
SSE_HEARTBEAT_SEC = float(os.getenv("SEALAI_SSE_HEARTBEAT_SEC", "10"))
SSE_QUEUE_MAXSIZE = int(os.getenv("SEALAI_SSE_QUEUE_MAXSIZE", "200"))
SSE_SLOW_NOTICE_SEC = float(os.getenv("SEALAI_SSE_SLOW_NOTICE_SEC", "5"))
REQUIRE_PARAM_SNAPSHOT = os.getenv("SEALAI_REQUIRE_PARAM_SNAPSHOT") == "1"
WARN_STALE_PARAM_SNAPSHOT = os.getenv("SEALAI_WARN_STALE_PARAM_SNAPSHOT", "1") == "1"
DEFAULT_GRAPH_RECURSION_LIMIT = 25
_STREAM_NODE_BLOCKLIST = frozenset()


def _lg_trace_enabled() -> bool:
    return os.getenv("SEALAI_LG_TRACE") == "1"


def _state_values_to_dict(values: Any) -> Dict[str, Any]:
    if values is None:
        return {}
    if isinstance(values, SealAIState):
        return values.model_dump(exclude_none=True)
    if isinstance(values, dict):
        return dict(values)
    try:
        return dict(values)
    except Exception:
        return {}


def _pillar_dict(values: Dict[str, Any], pillar: str) -> Dict[str, Any]:
    candidate = values.get(pillar)
    if hasattr(candidate, "model_dump"):
        candidate = candidate.model_dump(exclude_none=True)
    if isinstance(candidate, dict):
        return dict(candidate)
    return {}


def _conversation_value(values: Dict[str, Any], key: str) -> Any:
    """Read from pillar 1 (`conversation`) with backward-compatible fallback."""
    pillar = _pillar_dict(values, "conversation")
    if key in pillar:
        return pillar.get(key)
    return values.get(key)


def _reasoning_value(values: Dict[str, Any], key: str) -> Any:
    """Read from pillar 3 (`reasoning`) with backward-compatible fallback."""
    pillar = _pillar_dict(values, "reasoning")
    if key in pillar:
        return pillar.get(key)
    return values.get(key)


def _system_value(values: Dict[str, Any], key: str) -> Any:
    """Read from pillar 4 (`system`) with backward-compatible fallback."""
    pillar = _pillar_dict(values, "system")
    if key in pillar:
        return pillar.get(key)
    return values.get(key)


def _working_profile_value(values: Dict[str, Any], key: str) -> Any:
    """Read from pillar 2 (`working_profile`) with backward-compatible fallback."""
    pillar = _pillar_dict(values, "working_profile")
    if key in pillar:
        return pillar.get(key)
    return values.get(key)


def _rfq_admissibility_value(values: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_rfq_admissibility_contract(values)


def _engineering_profile_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    """Return the canonical engineering profile stored inside pillar 2.

    `working_profile.engineering_profile` is the long-lived single source of
    truth for technical parameters that both the Fast Brain and the Slow Brain
    can share. The helper also tolerates older state layouts where
    `working_profile` itself was used as the engineering payload.
    """
    pillar = _pillar_dict(values, "working_profile")
    profile = pillar.get("engineering_profile")
    if hasattr(profile, "model_dump"):
        profile = profile.model_dump(exclude_none=True)
    if isinstance(profile, dict):
        return dict(profile)
    legacy = values.get("working_profile")
    if hasattr(legacy, "model_dump"):
        legacy = legacy.model_dump(exclude_none=True)
    if isinstance(legacy, dict):
        return dict(legacy)
    return {}


def _reasoning_working_memory(values: Dict[str, Any]) -> Dict[str, Any]:
    memory = _reasoning_value(values, "working_memory")
    if hasattr(memory, "model_dump"):
        memory = memory.model_dump(exclude_none=True)
    if isinstance(memory, dict):
        return dict(memory)
    return {}


def _candidate_semantics_payload(values: Dict[str, Any]) -> list[Dict[str, Any]]:
    system_candidate_semantics = _system_value(values, "candidate_semantics")
    if isinstance(system_candidate_semantics, list):
        return [dict(item) for item in system_candidate_semantics if isinstance(item, dict)]

    contract = _system_value(values, "answer_contract")
    if hasattr(contract, "model_dump"):
        contract = contract.model_dump(exclude_none=True)
    if isinstance(contract, dict):
        candidate_semantics = contract.get("candidate_semantics")
        if isinstance(candidate_semantics, list):
            return [dict(item) for item in candidate_semantics if isinstance(item, dict)]

    pillar = _pillar_dict(values, "working_profile")
    material_choice = pillar.get("material_choice")
    if hasattr(material_choice, "model_dump"):
        material_choice = material_choice.model_dump(exclude_none=True)
    if isinstance(material_choice, dict):
        reasoning = _pillar_dict(values, "reasoning")
        identity_map = reasoning.get("extracted_parameter_identity")
        if hasattr(identity_map, "model_dump"):
            identity_map = identity_map.model_dump(exclude_none=True)
        annotated = annotate_material_choice(material_choice, identity_map=identity_map if isinstance(identity_map, dict) else {})
        material = str(annotated.get("material") or "").strip()
        if material:
            return [
                {
                    "kind": "material",
                    "value": material,
                    "rationale": str(annotated.get("details") or ""),
                    "confidence": 0.6,
                    "specificity": str(annotated.get("specificity") or "unresolved"),
                    "source_kind": str(annotated.get("source_kind") or "unknown"),
                    "governed": bool(annotated.get("governed")),
                }
            ]
    return []


def _governance_metadata_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    governance = _system_value(values, "governance_metadata")
    if hasattr(governance, "model_dump"):
        governance = governance.model_dump(exclude_none=True)
    if isinstance(governance, dict):
        return dict(governance)

    contract = _system_value(values, "answer_contract")
    if hasattr(contract, "model_dump"):
        contract = contract.model_dump(exclude_none=True)
    if isinstance(contract, dict):
        candidate = contract.get("governance_metadata")
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


def _confirm_action_requires_rfq_ready(action: Any) -> bool:
    text = str(action or "").strip().lower()
    if not text:
        return False
    return any(token in text for token in ("rfq", "spec", "procurement", "approve_specification"))


def _release_blockers_from_state(state_like: SealAIState | Dict[str, Any]) -> list[str]:
    values = _state_values_to_dict(state_like)
    governance = _governance_metadata_payload(values)
    blockers = governance.get("unknowns_release_blocking")
    if not isinstance(blockers, list):
        return []
    return [str(item).strip() for item in blockers if str(item).strip()]


def _build_release_response(state_like: SealAIState | Dict[str, Any], *, thread_id: str) -> Dict[str, Any]:
    values = _state_values_to_dict(state_like)
    return {
        "chat_id": thread_id,
        "final_text": _resolve_final_text(values),
        "governed_output_text": _system_value(values, "governed_output_text") or _resolve_final_text(values),
        "governed_output_ready": bool(_system_value(values, "governed_output_ready")),
        "governance_metadata": _governance_metadata_payload(values),
        "rfq_admissibility": _rfq_admissibility_value(values),
        "candidate_semantics": _candidate_semantics_payload(values),
        "phase": _reasoning_value(values, "phase"),
        "last_node": _reasoning_value(values, "last_node"),
        "requires_human_review": bool(_system_value(values, "requires_human_review")),
    }


def _is_meaningful_live_calc_tile(tile: Any) -> bool:
    if hasattr(tile, "model_dump"):
        tile = tile.model_dump(exclude_none=True)
    if not isinstance(tile, dict) or not tile:
        return False

    status = tile.get("status")
    if isinstance(status, str) and status in {"ok", "warning", "critical"}:
        return True

    numeric_keys = (
        "v_surface_m_s",
        "pv_value_mpa_m_s",
        "friction_power_watts",
        "compression_ratio_pct",
        "groove_fill_pct",
        "stretch_pct",
        "thermal_expansion_mm",
    )
    for key in numeric_keys:
        if tile.get(key) is not None:
            return True

    warning_flags = (
        "hrc_warning",
        "runout_warning",
        "pv_warning",
        "extrusion_risk",
        "requires_backup_ring",
        "shrinkage_risk",
        "dry_running_risk",
        "geometry_warning",
    )
    if any(bool(tile.get(key)) for key in warning_flags):
        return True

    parameters = tile.get("parameters")
    if isinstance(parameters, dict):
        for value in parameters.values():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return True

    return False


def _normalize_live_calc_tile(tile: Any) -> Dict[str, Any] | None:
    if hasattr(tile, "model_dump"):
        tile = tile.model_dump(exclude_none=True)
    if not _is_meaningful_live_calc_tile(tile):
        return None
    if not isinstance(tile, dict):
        return None
    return dict(tile)


def _inject_live_calc_tile(payload: Dict[str, Any], *, live_calc_tile: Dict[str, Any] | None) -> None:
    tile = _normalize_live_calc_tile(live_calc_tile)
    if tile is None:
        return
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
        payload["data"] = data
    current_tile = _normalize_live_calc_tile(data.get("live_calc_tile"))
    if current_tile is None:
        data["live_calc_tile"] = dict(tile)
    payload["live_calc_tile"] = data.get("live_calc_tile")


async def _get_graph_state_values_for_stream(graph: Any, config: Any) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    try:
        snapshot = await graph.aget_state(config)
        if hasattr(snapshot, "values"):
            values = _state_values_to_dict(snapshot.values)
    except Exception:
        logger.exception("langgraph_v2_stream_aget_state_failed")
    return values


def _short_user_id(user_id: str | None) -> str:
    if not user_id:
        return ""
    return f"{user_id[:8]}..." if len(user_id) > 8 else user_id

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional dependency
    Redis = None

CONFIRM_GO_AS_NODE = "confirm_recommendation_node"
PARAMETERS_PATCH_AS_NODE = "node_p1_context"


class LangGraphV2Request(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: str = Field(
        default="",
        validation_alias=AliasChoices("input", "message", "text"),
        description="User prompt",
    )
    chat_id: str = Field(
        default="default",
        validation_alias=AliasChoices("chat_id", "chatId", "thread_id", "threadId", "session_id", "sessionId"),
        description="Conversation/thread id",
    )
    client_msg_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("client_msg_id", "clientMsgId"),
        description="Client message id for tracing",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata", "meta"),
        description="Optional client metadata",
    )
    client_context: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("client_context", "clientContext"),
        description="Optional client context",
    )

    @field_validator("input", mode="before")
    @classmethod
    def _coerce_input(cls, value: Any) -> str:
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)

    @field_validator("chat_id", mode="before")
    @classmethod
    def _coerce_chat_id(cls, value: Any) -> str:
        if value is None:
            return "default"
        return value if isinstance(value, str) else str(value)

    @field_validator("client_msg_id", mode="before")
    @classmethod
    def _coerce_client_msg_id(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        return value if isinstance(value, str) else str(value)

    @field_validator("metadata", "client_context", mode="before")
    @classmethod
    def _coerce_mapping_fields(cls, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        return value if isinstance(value, dict) else {}

    @model_validator(mode="after")
    def _normalize_fields(self) -> "LangGraphV2Request":
        self.input = (self.input or "").strip()
        chat_id = (self.chat_id or "").strip()
        if not chat_id or chat_id == "default":
            self.chat_id = uuid.uuid4().hex
        else:
            self.chat_id = chat_id

        if self.client_msg_id is not None:
            client_msg_id = self.client_msg_id.strip()
            self.client_msg_id = client_msg_id or None
        return self


def _scope_thread_id_for_user(*, user_id: str, thread_id: str) -> str:
    """Apply the canonical user-scoped checkpoint key format.

    API callers may send a bare `chat_id`, while the checkpoint layer must
    always use the user-scoped form. This helper is called at the API boundary
    so Fast Brain, Slow Brain, thread locks, dedup keys, and checkpoint lookup
    all address the same namespace.
    """
    return scope_v2_thread_id(thread_id=thread_id, user_id=user_id)


def _format_sse(event: str, payload: Dict[str, Any], *, event_id: str | None = None) -> bytes:
    safe_event = str(event).replace("\r", "").replace("\n", "")
    safe_event_id = str(event_id).replace("\r", "").replace("\n", "") if event_id else None
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Guarantee a single data line per SSE event even if payload serialization ever changes.
    payload_json = payload_json.replace("\r", "\\r").replace("\n", "\\n")
    prefix = f"id: {safe_event_id}\n" if safe_event_id else ""
    return (prefix + f"event: {safe_event}\n" + f"data: {payload_json}\n\n").encode("utf-8")


def _format_sse_text(event: str, payload: Dict[str, Any], *, event_id: str | None = None) -> str:
    return _format_sse(event, payload, event_id=event_id).decode("utf-8")


class _CompatEventSourceResponse(StreamingResponse):
    def __init__(self, content: AsyncIterator[Any], **kwargs: Any) -> None:
        async def _serialize() -> AsyncIterator[bytes]:
            async for item in content:
                if isinstance(item, (bytes, bytearray)):
                    yield bytes(item)
                    continue
                if isinstance(item, str):
                    yield item.encode("utf-8")
                    continue
                if isinstance(item, dict):
                    event_name = str(item.get("event") or "message")
                    data = item.get("data")
                    if isinstance(data, (dict, list)):
                        data = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                    elif data is None:
                        data = ""
                    else:
                        data = str(data)
                    event_id = item.get("id")
                    retry = item.get("retry")
                    lines: list[str] = []
                    if retry is not None:
                        lines.append(f"retry: {int(retry)}")
                    if event_id is not None:
                        lines.append(f"id: {str(event_id).replace(chr(10), '').replace(chr(13), '')}")
                    lines.append(f"event: {event_name.replace(chr(10), '').replace(chr(13), '')}")
                    for line in data.replace("\r", "\\r").split("\n"):
                        lines.append(f"data: {line}")
                    lines.append("")
                    yield ("\n".join(lines) + "\n").encode("utf-8")
                    continue
                yield str(item).encode("utf-8")

        super().__init__(_serialize(), media_type="text/event-stream", **kwargs)


EventSourceResponse = NativeEventSourceResponse or _CompatEventSourceResponse


def _eventsource_event(event: str, payload: Dict[str, Any], *, event_id: str | None = None) -> Dict[str, Any]:
    event_payload = {
        "event": event,
        "data": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }
    if event_id:
        event_payload["id"] = event_id
    return event_payload


def _chunk_text(text: str, *, max_len: int = 700) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks


def _config_user_id(config: Dict[str, Any], fallback: str) -> str:
    metadata = config.get("metadata") if isinstance(config, dict) else {}
    if isinstance(metadata, dict):
        value = metadata.get("user_id")
        if isinstance(value, str) and value:
            return value
    return fallback


def _has_checkpoint_state(snapshot: Any) -> bool:
    values = _state_values_to_dict(getattr(snapshot, "values", None))
    return bool(values)


def _snapshot_waiting_on_human_review(snapshot: Any) -> bool:
    next_nodes = getattr(snapshot, "next", None)
    if not isinstance(next_nodes, (list, tuple, set)):
        return False
    for node in next_nodes:
        if isinstance(node, str) and node == "human_review_node":
            return True
        if isinstance(node, (list, tuple)):
            if any(isinstance(item, str) and item == "human_review_node" for item in node):
                return True
    return False


def _extract_snapshot_checkpoint_id(snapshot: Any, state_values: Dict[str, Any], *, fallback: str) -> str:
    from_state = _system_value(state_values, "confirm_checkpoint_id")
    if isinstance(from_state, str) and from_state.strip():
        return from_state.strip()

    snapshot_config = getattr(snapshot, "config", None)
    if isinstance(snapshot_config, dict):
        configurable = snapshot_config.get("configurable")
        if isinstance(configurable, dict):
            for key in ("checkpoint_id", "checkpoint_ns", "thread_id"):
                value = configurable.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        for key in ("checkpoint_id", "checkpoint_ns"):
            value = snapshot_config.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return fallback


async def _build_graph_config(
    *,
    thread_id: str,
    user_id: str,
    username: str | None = None,
    auth_scopes: list[str] | None = None,
    legacy_user_id: str | None = None,
    request_id: str | None = None,
    allow_legacy_fallback: bool = True,
) -> tuple[Any, Dict[str, Any]]:
    graph = await get_sealai_graph_v2()

    def _with_default_recursion_limit(base_config: Dict[str, Any]) -> Dict[str, Any]:
        config = dict(base_config or {})
        config["recursion_limit"] = DEFAULT_GRAPH_RECURSION_LIMIT
        return config

    def _attach_config(base_config: Dict[str, Any], *, scoped_user_id: str) -> Dict[str, Any]:
        configurable = base_config.setdefault("configurable", {})
        metadata = base_config.setdefault("metadata", {})
        if hasattr(graph, "checkpointer"):
            configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
        if username:
            metadata["username"] = username
            metadata["user_sub"] = scoped_user_id
        if auth_scopes:
            metadata["auth_scopes"] = list(auth_scopes)
        if request_id:
            metadata["run_id"] = request_id
        return base_config

    config = _with_default_recursion_limit(
        _attach_config(build_v2_config(thread_id=thread_id, user_id=user_id), scoped_user_id=user_id)
    )
    if not allow_legacy_fallback or not legacy_user_id or legacy_user_id == user_id:
        return graph, config

    try:
        snapshot = await graph.aget_state(config)
        if _has_checkpoint_state(snapshot):
            return graph, config

        legacy_config = _with_default_recursion_limit(
            _attach_config(
                build_v2_config(thread_id=thread_id, user_id=legacy_user_id),
                scoped_user_id=legacy_user_id,
            )
        )
        legacy_snapshot = await graph.aget_state(legacy_config)
        if _has_checkpoint_state(legacy_snapshot):
            if SSE_DEBUG or PARAM_SYNC_DEBUG or _lg_trace_enabled():
                logger.warning(
                    "langgraph_v2_legacy_thread_fallback",
                    extra={
                        "request_id": request_id,
                        "chat_id": thread_id,
                        "user_id": user_id,
                        "legacy_user_id": legacy_user_id,
                    },
                )
            return graph, legacy_config
    except Exception:
        logger.exception(
            "langgraph_v2_legacy_fallback_failed",
            extra={
                "request_id": request_id,
                "chat_id": thread_id,
                "user_id": user_id,
                "legacy_user_id": legacy_user_id,
            },
        )

    return graph, config


@lru_cache(maxsize=1)
def _get_fast_brain_router() -> FastBrainRouter:
    model = os.getenv("SEALAI_FAST_BRAIN_MODEL", "gpt-4o-mini")
    try:
        temperature = float(os.getenv("SEALAI_FAST_BRAIN_TEMPERATURE", "0"))
    except ValueError:
        temperature = 0.0
    return FastBrainRouter(model=model, temperature=temperature)


def _extract_fast_brain_history(state_values: Dict[str, Any]) -> list[Any]:
    history = _conversation_value(state_values, "messages")
    return list(history) if isinstance(history, list) else []


def _normalize_fast_brain_status(result: Dict[str, Any]) -> str:
    status = str(result.get("status") or "").strip()
    if status in {"chat_continue", "handoff_to_langgraph"}:
        return status
    if result.get("handoff_to_slow_brain"):
        return "handoff_to_langgraph"
    return "chat_continue"


def _coerce_fast_brain_state_patch(result: Dict[str, Any]) -> Dict[str, Any]:
    raw_patch = result.get("state_patch")
    if not isinstance(raw_patch, dict):
        return {}

    patch: Dict[str, Any] = {}
    raw_parameters = raw_patch.get("parameters")
    if isinstance(raw_parameters, dict):
        try:
            parameters = sanitize_v2_parameter_patch(raw_parameters)
        except ValueError:
            logger.exception("fast_brain_state_patch_invalid_parameters", extra={"parameters": raw_parameters})
        else:
            if parameters:
                patch["parameters"] = parameters

    raw_working_profile = raw_patch.get("working_profile")
    if isinstance(raw_working_profile, dict):
        working_profile_patch: Dict[str, Any] = {}
        live_calc_tile = raw_working_profile.get("live_calc_tile")
        if isinstance(live_calc_tile, dict):
            working_profile_patch["live_calc_tile"] = dict(live_calc_tile)
        calc_results = raw_working_profile.get("calc_results")
        if isinstance(calc_results, dict):
            working_profile_patch["calc_results"] = dict(calc_results)
        if working_profile_patch:
            patch["working_profile"] = working_profile_patch

    return patch


def _fast_brain_profile_mirrors(parameters: Dict[str, Any]) -> Dict[str, Any]:
    mirrors: Dict[str, Any] = {}
    if "medium" in parameters:
        mirrors["medium"] = parameters.get("medium")
    if "pressure_bar" in parameters:
        mirrors["pressure_bar"] = parameters.get("pressure_bar")
    temperature_value = parameters.get("temperature_c")
    if temperature_value is None:
        temperature_value = parameters.get("temperature_C")
    if temperature_value is not None:
        mirrors["temperature_c"] = temperature_value
    return mirrors


async def _sync_fast_brain_checkpoint_state(
    *,
    graph: Any,
    config: Dict[str, Any],
    user_input: str,
    fast_brain_result: Dict[str, Any],
    request_id: str | None,
    persist_transcript: bool,
) -> Dict[str, Any]:
    """Merge Fast-Brain discoveries into the LangGraph checkpoint before handoff.

    This is the state bridge between the two execution speeds.

    Mapping rules:

    - Fast-Brain extracted parameters are staged into
      `working_profile.extracted_params` and are not asserted automatically.
    - Extracted-parameter provenance is written into the `reasoning` pillar so
      later graph nodes can distinguish staged input from asserted state.
    - Physics-tool outputs are copied into pillar 2:
      - `working_profile.live_calc_tile` for the live digital twin / UI stream.
      - `working_profile.calc_results` for deterministic downstream graph use.
    - No automatic promotion into `working_profile.engineering_profile` happens
      in this bridge.
    - On the pure fast path (`persist_transcript=True`), the user turn and the
      Fast-Brain assistant answer are appended to pillar 1 (`conversation`) so
      the chat history remains checkpoint-consistent even though the graph never
      ran.

    The helper intentionally does not write to pillar 4 (`system`): Fast-Brain
    interception is a frontdoor optimization, not a replacement for the graph's
    authoritative final-output pipeline.
    """
    state_values = await _get_graph_state_values_for_stream(graph, config)
    patch = _coerce_fast_brain_state_patch(fast_brain_result)
    parameter_patch = patch.get("parameters") if isinstance(patch.get("parameters"), dict) else {}
    existing_extracted = _working_profile_value(state_values, "extracted_params") or {}
    existing_extracted_provenance = _reasoning_value(state_values, "extracted_parameter_provenance") or {}
    existing_extracted_identity = _reasoning_value(state_values, "extracted_parameter_identity") or {}

    merged_extracted = dict(existing_extracted)
    merged_extracted_provenance = dict(existing_extracted_provenance)
    merged_extracted_identity = dict(existing_extracted_identity)
    applied_fields: list[str] = []
    rejected_fields: list[Dict[str, Any]] = []

    if parameter_patch:
        (
            merged_extracted,
            merged_extracted_provenance,
            merged_extracted_identity,
            applied_fields,
        ) = stage_extracted_parameter_patch(
            existing_extracted,
            parameter_patch,
            existing_extracted_provenance,
            existing_extracted_identity,
            source="fast_brain_extracted",
        )

    updates: Dict[str, Any] = {}
    working_profile_patch = patch.get("working_profile") if isinstance(patch.get("working_profile"), dict) else {}
    working_profile_update: Dict[str, Any] = {}
    if parameter_patch:
        working_profile_update["extracted_params"] = merged_extracted
    if isinstance(working_profile_patch.get("live_calc_tile"), dict):
        # `live_calc_tile` is optimized for immediate UI rendering and
        # conversational access to deterministic tool outputs.
        working_profile_update["live_calc_tile"] = dict(working_profile_patch["live_calc_tile"])
    if isinstance(working_profile_patch.get("calc_results"), dict):
        # `calc_results` is the graph-facing deterministic calculation payload.
        working_profile_update["calc_results"] = dict(working_profile_patch["calc_results"])
    if working_profile_update:
        updates["working_profile"] = working_profile_update
    if parameter_patch:
        updates["reasoning"] = {
            "extracted_parameter_provenance": merged_extracted_provenance,
            "extracted_parameter_identity": merged_extracted_identity,
        }

    if persist_transcript:
        transcript_messages: list[BaseMessage] = []
        user_text = str(user_input or "").strip()
        if user_text:
            transcript_messages.append(HumanMessage(content=user_text))
        assistant_text = str(fast_brain_result.get("content") or "").strip()
        if assistant_text:
            transcript_messages.append(AIMessage(content=assistant_text))
        if transcript_messages:
            updates["conversation"] = {"messages": transcript_messages}

    if not updates:
        return state_values

    assert_node_exists(graph, PARAMETERS_PATCH_AS_NODE, request_id=request_id)
    await graph.aupdate_state(config, updates, as_node=PARAMETERS_PATCH_AS_NODE)

    if parameter_patch and (PARAM_SYNC_DEBUG or SSE_DEBUG):
        configurable = config.get("configurable") if isinstance(config, dict) else {}
        logger.info(
            "fast_brain_checkpoint_sync",
            extra={
                "request_id": request_id,
                "thread_id": configurable.get("thread_id") if isinstance(configurable, dict) else None,
                "applied_fields": applied_fields,
                "rejected_fields": rejected_fields,
            },
        )

    merged_state = _merge_state_like(state_values, updates)
    return _state_values_to_dict(merged_state)


async def _fast_brain_sse_stream(
    *,
    request: Request,
    thread_id: str,
    fast_brain_result: Dict[str, Any],
    state_values: Dict[str, Any],
) -> AsyncIterator[Dict[str, Any]]:
    """Stream a completed Fast-Brain answer as SSE without activating LangGraph.

    The event contract mirrors the normal graph stream closely enough that the
    frontend can treat both paths as one chat API:

    1. optional `state_update` when the Fast Brain produced digital-twin data
    2. one or more legacy `text_chunk` plus canonical `token` events
    3. terminal legacy `turn_complete` plus canonical `done`
    """
    try:
        payload = _build_state_update_payload(state_values)
        payload_data = payload.get("data") if isinstance(payload, dict) else None
        should_emit_state = False
        if isinstance(payload_data, dict):
            should_emit_state = bool(
                payload_data.get("working_profile")
                or payload_data.get("live_calc_tile")
                or payload_data.get("calc_results")
            )
        if should_emit_state and not await request.is_disconnected():
            yield _eventsource_event("state_update", payload)

        text = str(fast_brain_result.get("content") or "").strip()
        if not await request.is_disconnected():
            yield _eventsource_event("turn_complete", {"type": "turn_complete"})
            done_payload = {"type": "done", "chat_id": thread_id}
            if text:
                done_payload["final_text"] = text
                done_payload["final_answer"] = text
            yield _eventsource_event("done", done_payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("fast_brain_sse_stream_failed", extra={"thread_id": thread_id})
        if not await request.is_disconnected():
            yield _eventsource_event("error", {"type": "error", "message": "internal_error"})
            yield _eventsource_event("turn_complete", {"type": "turn_complete"})
            yield _eventsource_event("done", {"type": "done", "chat_id": thread_id})
    finally:
        await _release_thread_lock(thread_id)


async def _run_graph_to_state(
    req: LangGraphV2Request,
    *,
    user_id: str,
    username: str | None = None,
    auth_scopes: list[str] | None = None,
    tenant_id: str | None = None,
) -> SealAIState:
    scoped_thread_id = _scope_thread_id_for_user(user_id=user_id, thread_id=req.chat_id)
    graph, config = await _build_graph_config(
        thread_id=scoped_thread_id,
        user_id=user_id,
        username=username,
        auth_scopes=auth_scopes,
    )
    initial_state = SealAIState(
        conversation={
            "user_id": user_id,
            "thread_id": scoped_thread_id,
            "messages": [HumanMessage(content=req.input)],
            "user_context": {"auth_scopes": list(auth_scopes or []), "tenant_id": tenant_id},
        },
        system={"tenant_id": tenant_id},
    )
    result = await graph.ainvoke(initial_state, config=config)
    if isinstance(result, SealAIState):
        return result
    if isinstance(result, dict):
        return SealAIState(**result)
    raise TypeError(f"Unexpected graph result type: {type(result).__name__}")


def _should_emit_confirm_checkpoint(state: SealAIState) -> bool:
    if state.system.awaiting_user_confirmation:
        return True
    if state.system.confirm_checkpoint:
        return True
    if (state.reasoning.phase or "") == "confirm":
        return True
    if (state.reasoning.last_node or "") == "confirm_recommendation_node":
        return True
    return False


def _build_state_update_payload(state: SealAIState | Dict[str, Any]) -> Dict[str, Any]:
    values = _state_values_to_dict(state)
    working_profile = _engineering_profile_payload(values) if isinstance(values, dict) else {}
    prompt_meta = _system_value(values, "final_prompt_metadata") if isinstance(values, dict) else None
    live_calc_tile = _working_profile_value(values, "live_calc_tile") if isinstance(values, dict) else None
    calc_results = _working_profile_value(values, "calc_results") if isinstance(values, dict) else None
    has_live_calc_tile = _is_meaningful_live_calc_tile(live_calc_tile)
    if not has_live_calc_tile and live_calc_tile:
        # User Directive: "Stelle sicher, dass live_calc_tile NICHT gefiltert wird, wenn es vorhanden ist."
        has_live_calc_tile = True
    if isinstance(state, dict) and "live_calc_tile" not in state and "working_profile" not in state and not has_live_calc_tile:
        has_live_calc_tile = False
    rfq_pdf_base64 = _system_value(values, "rfq_pdf_base64") if isinstance(values, dict) else None
    rfq_pdf_url = _system_value(values, "rfq_pdf_url") if isinstance(values, dict) else None
    rfq_html_report = _system_value(values, "rfq_html_report") if isinstance(values, dict) else None
    rfq_admissibility = _rfq_admissibility_value(values)
    candidate_semantics = _candidate_semantics_payload(values)
    governance_metadata = _governance_metadata_payload(values)
    if hasattr(working_profile, "model_dump"):
        working_profile = working_profile.model_dump(exclude_none=True)
    if hasattr(live_calc_tile, "model_dump"):
        live_calc_tile = live_calc_tile.model_dump(exclude_none=True)
    if hasattr(calc_results, "model_dump"):
        calc_results = calc_results.model_dump(exclude_none=True)
    data_working_profile = working_profile if isinstance(working_profile, dict) else {}
    if calc_results is not None:
        data_working_profile["calc_results"] = calc_results
    if has_live_calc_tile and isinstance(live_calc_tile, dict):
        data_working_profile["live_calc_tile"] = live_calc_tile
    rfq_document = {
        "ready": rfq_contract_is_ready(rfq_admissibility),
        "has_pdf_base64": bool(isinstance(rfq_pdf_base64, str) and rfq_pdf_base64.strip()),
        "has_pdf_url": bool(isinstance(rfq_pdf_url, str) and rfq_pdf_url.strip()),
        "has_html_report": bool(isinstance(rfq_html_report, str) and rfq_html_report.strip()),
    }

    governed_text = _resolve_governed_output_text(values)
    data = {
        "phase": _reasoning_value(values, "phase"),
        "last_node": _reasoning_value(values, "last_node"),
        "preview_text": _system_value(values, "preview_text"),
        "governed_output_text": _system_value(values, "governed_output_text"),
        "governed_output_status": _system_value(values, "governed_output_status"),
        "governed_output_ready": bool(_system_value(values, "governed_output_ready")),
        "governance_metadata": governance_metadata if governance_metadata else None,
        "final_text": governed_text or None,
        "final_answer": governed_text or None,
        "awaiting_user_input": _reasoning_value(values, "awaiting_user_input"),
        "streaming_complete": _reasoning_value(values, "streaming_complete"),
        "awaiting_user_confirmation": _system_value(values, "awaiting_user_confirmation"),
        "recommendation_ready": _reasoning_value(values, "recommendation_ready"),
        "recommendation_go": _reasoning_value(values, "recommendation_go"),
        "coverage_score": _reasoning_value(values, "coverage_score"),
        "coverage_gaps": _reasoning_value(values, "coverage_gaps"),
        "missing_params": _reasoning_value(values, "missing_params"),
        "working_profile": data_working_profile,
        "calc_results": calc_results,
        "compliance_results": _working_profile_value(values, "compliance_results"),
        "delta": {"working_profile": data_working_profile},
        "pending_action": _system_value(values, "pending_action"),
        "confirm_checkpoint_id": _system_value(values, "confirm_checkpoint_id"),
        "final_prompt_metadata": prompt_meta if isinstance(prompt_meta, dict) and prompt_meta else None,
        "rfq_admissibility": rfq_admissibility,
        "rfq_ready": rfq_contract_is_ready(rfq_admissibility),
        "rfq_document": rfq_document,
    }
    if candidate_semantics:
        data["candidate_semantics"] = candidate_semantics
    if has_live_calc_tile and isinstance(live_calc_tile, dict):
        data["live_calc_tile"] = live_calc_tile
    data = {key: value for key, value in data.items() if value is not None}
    payload = {
        "type": "state_update",
        "data": data,
        # Legacy top-level mirrors kept for compatibility with existing clients.
        "phase": data.get("phase"),
        "last_node": data.get("last_node"),
        "preview_text": data.get("preview_text"),
        "governed_output_text": data.get("governed_output_text"),
        "governed_output_status": data.get("governed_output_status"),
        "governed_output_ready": data.get("governed_output_ready"),
        "governance_metadata": data.get("governance_metadata"),
        "final_text": data.get("final_text"),
        "final_answer": data.get("final_answer"),
        "awaiting_user_input": data.get("awaiting_user_input"),
        "streaming_complete": data.get("streaming_complete"),
        "awaiting_user_confirmation": data.get("awaiting_user_confirmation"),
        "recommendation_ready": data.get("recommendation_ready"),
        "recommendation_go": data.get("recommendation_go"),
        "coverage_score": data.get("coverage_score"),
        "coverage_gaps": data.get("coverage_gaps"),
        "missing_params": data.get("missing_params"),
        "working_profile": data.get("working_profile"),
        "live_calc_tile": data.get("live_calc_tile"),
        "calc_results": data.get("calc_results"),
        "compliance_results": data.get("compliance_results"),
        "delta": data.get("delta"),
        "pending_action": data.get("pending_action"),
        "confirm_checkpoint_id": data.get("confirm_checkpoint_id"),
        "final_prompt_metadata": data.get("final_prompt_metadata"),
        "rfq_admissibility": data.get("rfq_admissibility"),
        "candidate_semantics": data.get("candidate_semantics"),
        "rfq_ready": data.get("rfq_ready"),
        "rfq_document": data.get("rfq_document"),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _flatten_message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                text_value = chunk.get("text") or chunk.get("content")
                nested = _flatten_message_content(text_value)
                if nested:
                    parts.append(nested)
            else:
                nested = _flatten_message_content(chunk)
                if nested:
                    parts.append(nested)
        return "".join(parts)
    if isinstance(content, dict):
        text_value = content.get("text") or content.get("content")
        return _flatten_message_content(text_value)
    if content is None:
        return ""
    if isinstance(content, (int, float)):
        return str(content)
    return ""


def _is_structured_payload_text(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or stripped[0] not in {"{", "["}:
        return False
    try:
        parsed = json.loads(stripped)
    except Exception:
        return False
    return isinstance(parsed, (dict, list))


def _normalize_stream_node_name(node_name: Any) -> str | None:
    if isinstance(node_name, str):
        candidate = node_name.strip()
        if candidate:
            return candidate
    return None


def _resolve_stream_node_name(*, node_name: Any = None, meta: Any = None) -> str | None:
    candidates: list[Any] = []
    if isinstance(meta, dict):
        candidates.extend([meta.get("langgraph_node"), meta.get("node"), meta.get("name")])
        nested_meta = meta.get("metadata")
        if isinstance(nested_meta, dict):
            candidates.extend([nested_meta.get("langgraph_node"), nested_meta.get("node"), nested_meta.get("name")])
    candidates.append(node_name)
    for candidate in candidates:
        resolved = _normalize_stream_node_name(candidate)
        if resolved:
            return resolved
    return None


_LEGACY_GOVERNED_NODES = {
    "answer_subgraph_node",
    "final_answer_node",
    "response_node",
    "node_finalize",
    "node_safe_fallback",
    "smalltalk_node",
    "out_of_scope_node",
    "confirm_recommendation_node",
}


def _resolve_governed_output_text(state: SealAIState | Dict[str, Any]) -> str:
    values = _state_values_to_dict(state)
    governed = _system_value(values, "governed_output_text")
    if isinstance(governed, str) and governed.strip():
        return governed.strip()

    ready = bool(_system_value(values, "governed_output_ready"))
    last_node = str(_reasoning_value(values, "last_node") or values.get("last_node") or "").strip()
    if ready or last_node in _LEGACY_GOVERNED_NODES:
        legacy = _system_value(values, "final_text")
        if not isinstance(legacy, str):
            legacy = _system_value(values, "final_answer")
        return str(legacy or "").strip()
    return ""


def _is_allowed_stream_source(token: Any, *, stream_node: str | None, state: Any = None) -> bool:
    is_rfq = False
    if state:
        sv = _state_values_to_dict(state)
        # Commercial/RFQ intents often have rfq_ready or procurement phase markers.
        if rfq_contract_is_ready(_rfq_admissibility_value(sv)) or _reasoning_value(sv, "rfq_ready") or _reasoning_value(sv, "phase") == "procurement":
            is_rfq = True

    if stream_node and stream_node in _STREAM_NODE_BLOCKLIST:
        if not is_rfq:
            return False
    if not stream_node:
        return False
    allowed_nodes = {"response_node", "contract_first_output_node", "node_finalize", "final_answer_node"}
    if is_rfq:
        allowed_nodes.update({"node_p4b_calc_render", "p4b_calc_render"})
    if stream_node not in allowed_nodes:
        return False
    return isinstance(token, (AIMessage, AIMessageChunk))


def _is_safe_preview_stream_state(state: Any) -> bool:
    values = _state_values_to_dict(state)
    raw_intent = _conversation_value(values, "intent")
    flags = _reasoning_value(values, "flags") or {}
    intent_goal = (
        str(raw_intent or "").strip().lower()
        if isinstance(raw_intent, str)
        else str((raw_intent or {}).get("goal") or getattr(raw_intent, "goal", "") or "").strip().lower()
    )
    intent_category = (
        str(
            (raw_intent or {}).get("intent_category")
            if isinstance(raw_intent, dict)
            else getattr(raw_intent, "intent_category", "")
        ).strip().upper()
        or str(flags.get("frontdoor_intent_category") or "").strip().upper()
    )
    return intent_category == "MATERIAL_RESEARCH" or intent_goal in {"material_research", "explanation_or_comparison"}


def _extract_stream_nodes_from_tags(tags: Any) -> set[str]:
    nodes: set[str] = set()
    if not isinstance(tags, (list, tuple, set)):
        return nodes
    prefix = "langsmith:graph:node:"
    for tag in tags:
        if not isinstance(tag, str) or not tag.startswith(prefix):
            continue
        node_name = tag[len(prefix):].strip()
        if node_name:
            nodes.add(node_name)
    return nodes


def _extract_stream_token_text(token: Any, *, stream_node: str | None = None, state: Any = None) -> str | None:
    if token is None:
        return None
    if not isinstance(token, (AIMessage, AIMessageChunk)):
        return None
    if isinstance(token, dict):
        return None
    if isinstance(token, BaseMessage) and not (_is_message_chunk(token) or isinstance(token, AIMessage)):
        return None
    if not _is_allowed_stream_source(token, stream_node=stream_node, state=state):
        return None
    text_attr = getattr(token, "text", None)
    if isinstance(text_attr, str) and text_attr:
        return None if _is_structured_payload_text(text_attr) else text_attr
    content_attr = getattr(token, "content", None)
    if isinstance(content_attr, str) and content_attr:
        return None if _is_structured_payload_text(content_attr) else content_attr
    text = _flatten_message_content(token)
    if not text or _is_structured_payload_text(text):
        return None
    return text


def _event_belongs_to_current_run(raw_event: Any, expected_run_id: str | None) -> bool:
    if not expected_run_id or not isinstance(raw_event, dict):
        return True
    event_ids: set[str] = set()
    metadata = raw_event.get("metadata") if isinstance(raw_event.get("metadata"), dict) else {}
    for source in (raw_event, metadata):
        if not isinstance(source, dict):
            continue
        run_id = source.get("run_id")
        if isinstance(run_id, str) and run_id:
            event_ids.add(run_id)
        parent_run_id = source.get("parent_run_id")
        if isinstance(parent_run_id, str) and parent_run_id:
            event_ids.add(parent_run_id)
        parent_ids = source.get("parent_ids")
        if isinstance(parent_ids, (list, tuple, set)):
            for parent_id in parent_ids:
                if isinstance(parent_id, str) and parent_id:
                    event_ids.add(parent_id)
    if not event_ids:
        return True
    return expected_run_id in event_ids


def _is_message_chunk(token: BaseMessage) -> bool:
    if isinstance(token, AIMessageChunk):
        return True
    return token.__class__.__name__.endswith("Chunk")


def _parse_last_event_id(last_event_id: str | None, *, chat_id: str) -> int | None:
    return sse_broadcast.parse_last_event_id(chat_id, last_event_id)


def _get_dict_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _extract_param_snapshot(req: LangGraphV2Request) -> Dict[str, Any] | None:
    if not isinstance(req.client_context, dict):
        return None
    snapshot = req.client_context.get("param_snapshot")
    return snapshot if isinstance(snapshot, dict) else None


def _snapshot_stats(snapshot: Dict[str, Any] | None) -> tuple[int, float | None]:
    if not snapshot:
        return 0, None
    versions = snapshot.get("versions") if isinstance(snapshot, dict) else None
    updated_at = snapshot.get("updated_at") if isinstance(snapshot, dict) else None
    version_count = len(versions) if isinstance(versions, dict) else 0
    updated_values = []
    if isinstance(updated_at, dict):
        for value in updated_at.values():
            if isinstance(value, (int, float)):
                updated_values.append(float(value))
    return version_count, (max(updated_values) if updated_values else None)


def _snapshot_versions(snapshot: Dict[str, Any] | None) -> Dict[str, int]:
    if not snapshot:
        return {}
    raw = snapshot.get("versions") if isinstance(snapshot, dict) else None
    if not isinstance(raw, dict):
        return {}
    versions: Dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(value, (int, float)):
            versions[str(key)] = int(value)
    return versions


def _extract_trace_node(*, meta: Any = None, data: Any = None, state: Any = None) -> str | None:
    for source in (meta, data):
        node_value = _get_dict_value(source, "node") or _get_dict_value(source, "name")
        if isinstance(node_value, str) and node_value:
            return node_value
        metadata = _get_dict_value(source, "metadata")
        node_value = _get_dict_value(metadata, "node") or _get_dict_value(metadata, "name")
        if isinstance(node_value, str) and node_value:
            return node_value
    if isinstance(state, SealAIState):
        return state.reasoning.last_node
    if isinstance(state, dict):
        node_value = _reasoning_value(state, "last_node") or state.get("node") or state.get("name")
        return node_value if isinstance(node_value, str) else None
    return None


def _extract_trace_phase(*, data: Any = None, state: Any = None) -> str | None:
    phase_value = _get_dict_value(data, "phase")
    if isinstance(phase_value, str) and phase_value:
        return phase_value
    if isinstance(state, SealAIState):
        return state.reasoning.phase
    if isinstance(state, dict):
        phase_value = _reasoning_value(state, "phase")
        return phase_value if isinstance(phase_value, str) else None
    return None


def _extract_trace_action(*, data: Any = None, state: Any = None) -> str | None:
    for key in ("supervisor_action", "supervisor_decision", "action"):
        action_value = _get_dict_value(data, key)
        if isinstance(action_value, str) and action_value:
            return action_value
    working_memory = _get_dict_value(data, "working_memory")
    if not isinstance(working_memory, dict):
        reasoning_payload = _get_dict_value(data, "reasoning")
        working_memory = _get_dict_value(reasoning_payload, "working_memory")
    action_value = _get_dict_value(working_memory, "supervisor_decision")
    if isinstance(action_value, str) and action_value:
        return action_value
    if isinstance(state, SealAIState):
        action_value = getattr(state.reasoning.working_memory, "supervisor_decision", None)
        return action_value if isinstance(action_value, str) else None
    if isinstance(state, dict):
        working_memory = _reasoning_working_memory(state)
        action_value = _get_dict_value(working_memory, "supervisor_decision")
        return action_value if isinstance(action_value, str) else None
    return None


def _looks_like_state_payload(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    expected_keys = {
        "conversation",
        "reasoning",
        "working_profile",
        "system",
        "phase",
        "last_node",
        "messages",
        "final_text",
        "final_answer",
        "working_profile",
        "rfq_admissibility",
        "rfq_ready",
        "rfq_document",
        "awaiting_user_input",
        "awaiting_user_confirmation",
    }
    return any(key in data for key in expected_keys)


def _extract_state_update_source(data: Any) -> SealAIState | Dict[str, Any] | None:
    if isinstance(data, SealAIState):
        return data
    if not isinstance(data, dict):
        return None

    for key in ("output", "state", "final_state", "values", "result", "chunk", "patch", "update", "delta"):
        candidate = data.get(key)
        if isinstance(candidate, SealAIState):
            return candidate
        if isinstance(candidate, dict):
            nested_values = candidate.get("values")
            if isinstance(nested_values, (SealAIState, dict)):
                return nested_values
            if _looks_like_state_payload(candidate):
                return candidate

    if _looks_like_state_payload(data):
        return data
    return None


_NODE_LABELS: Dict[str, str] = {
    "profile_loader_node": "Profile Loader",
    "safety_synonym_guard_node": "Safety Synonym Guard",
    "combinatorial_chemistry_guard_node": "Combinatorial Chemistry Guard",
    "frontdoor_discovery_node": "Intent Discovery",
    "node_router": "Router",
    "node_p1_context": "Parameter Extraction",
    "reasoning_core_node": "Reasoning Core",
    "human_review_node": "Human Review",
    "contract_first_output_node": "Contract Output",
    "final_answer_node": "Final Answer",
    "node_draft_answer": "Drafting Answer",
    "node_finalize": "Finalizing",
    "worm_evidence_node": "WORM Evidence",
}


def _human_node_label(node_name: str | None) -> str:
    normalized = str(node_name or "").strip()
    if not normalized:
        return "Unknown Node"
    return _NODE_LABELS.get(normalized, normalized.replace("_", " ").title())


def _extract_chunk_text_from_stream_event(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        text = chunk
    elif isinstance(chunk, (AIMessage, AIMessageChunk, BaseMessage)):
        text = _flatten_message_content(chunk)
    elif isinstance(chunk, dict):
        text = _flatten_message_content(chunk.get("content") or chunk.get("text") or chunk)
    else:
        text = _flatten_message_content(chunk)
    if not text:
        return ""
    structured_probe = text.strip()
    if structured_probe and _is_structured_payload_text(structured_probe):
        return ""
    return text


def _extract_working_profile_payload(state_like: SealAIState | Dict[str, Any] | None) -> Dict[str, Any] | None:
    values = _state_values_to_dict(state_like)
    raw_profile = _engineering_profile_payload(values)
    if isinstance(raw_profile, dict) and raw_profile:
        return dict(raw_profile)
    return None


def _extract_blocker_conflicts(state_like: SealAIState | Dict[str, Any] | None) -> list[Dict[str, Any]]:
    profile = _extract_working_profile_payload(state_like)
    if not isinstance(profile, dict):
        return []
    conflicts = profile.get("conflicts_detected")
    if not isinstance(conflicts, list):
        return []
    blockers: list[Dict[str, Any]] = []
    for conflict in conflicts:
        if isinstance(conflict, dict):
            severity = str(conflict.get("severity") or "").upper()
            if severity == "BLOCKER":
                blockers.append(dict(conflict))
            continue
        severity = str(getattr(conflict, "severity", "") or "").upper()
        if severity != "BLOCKER":
            continue
        if hasattr(conflict, "model_dump"):
            blockers.append(conflict.model_dump(exclude_none=True))
        else:
            blockers.append(
                {
                    "rule_id": str(getattr(conflict, "rule_id", "") or ""),
                    "severity": severity,
                    "title": str(getattr(conflict, "title", "") or ""),
                    "reason": str(getattr(conflict, "reason", "") or ""),
                }
            )
    return blockers


async def event_multiplexer(
    graph: Any,
    state_input: SealAIState,
    config: Dict[str, Any],
    request: Request,
) -> AsyncIterator[str]:
    """Translate LangGraph firehose events into strict typed SSE events.

    Output format is always:
    `event: <type>\ndata: <json>\n\n`
    """
    metadata = config.get("metadata") if isinstance(config, dict) else {}
    expected_run_id = metadata.get("run_id") if isinstance(metadata, dict) else None
    thread_id = state_input.conversation.thread_id

    if not hasattr(graph, "astream_events"):
        yield _format_sse_text(
            "error",
            {"type": "error", "message": "astream_events_not_supported"},
        )
        yield _format_sse_text("turn_complete", {"type": "turn_complete"})
        if thread_id:
            await _release_thread_lock(thread_id)
        return

    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=max(32, SSE_QUEUE_MAXSIZE // 2))
    latest_state: SealAIState | Dict[str, Any] | None = state_input
    turn_complete_sent = False

    async def _queue_emit(event_name: str, payload: Dict[str, Any]) -> None:
        frame = _format_sse_text(event_name, payload)
        if queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
        queue.put_nowait(frame)

    async def _queue_done() -> None:
        final_text = _resolve_final_text(latest_state).strip() if isinstance(latest_state, (SealAIState, dict)) else ""
        payload = {
            "type": "done",
            "chat_id": thread_id,
        }
        if final_text:
            payload["final_text"] = final_text
            payload["final_answer"] = final_text
        await _queue_emit(
            "done",
            payload,
        )

    async def _producer() -> None:
        nonlocal latest_state, turn_complete_sent
        state_update_signature: str | None = None
        token_seen = False
        emitted_terminal_text: str | None = None

        async def _emit_terminal_token_if_available(source: SealAIState | Dict[str, Any] | None) -> None:
            nonlocal token_seen, emitted_terminal_text
            if token_seen or not isinstance(source, (SealAIState, dict)):
                return
            final_text = _extract_terminal_text_candidate(source).strip()
            if not final_text or final_text == emitted_terminal_text:
                return
            emitted_terminal_text = final_text
            token_seen = True
            await _queue_emit("token", {"type": "token", "text": final_text})

        async def _emit_state_update_if_available() -> None:
            nonlocal state_update_signature
            if not isinstance(latest_state, (SealAIState, dict)):
                return
            payload = _build_state_update_payload(latest_state)
            payload_data = payload.get("data")
            if not isinstance(payload_data, dict):
                return

            working_profile_payload = payload_data.get("working_profile")
            if not isinstance(working_profile_payload, dict):
                working_profile_payload = {}
                payload_data["working_profile"] = working_profile_payload

            # Ensure v10 nested structure is present for frontend consumers.
            wp_live_calc_tile = working_profile_payload.get("live_calc_tile")
            wp_calc_results = working_profile_payload.get("calc_results")
            if payload_data.get("live_calc_tile") is None and wp_live_calc_tile is not None:
                payload_data["live_calc_tile"] = wp_live_calc_tile
            if payload_data.get("calc_results") is None and wp_calc_results is not None:
                payload_data["calc_results"] = wp_calc_results

            if working_profile_payload.get("live_calc_tile") is None and payload_data.get("live_calc_tile") is not None:
                working_profile_payload["live_calc_tile"] = payload_data.get("live_calc_tile")
            if working_profile_payload.get("calc_results") is None and payload_data.get("calc_results") is not None:
                working_profile_payload["calc_results"] = payload_data.get("calc_results")

            if payload.get("live_calc_tile") is None and payload_data.get("live_calc_tile") is not None:
                payload["live_calc_tile"] = payload_data.get("live_calc_tile")
            if payload.get("calc_results") is None and payload_data.get("calc_results") is not None:
                payload["calc_results"] = payload_data.get("calc_results")
            if payload.get("working_profile") is None:
                payload["working_profile"] = working_profile_payload

            signature = json.dumps(
                {
                    "phase": payload_data.get("phase"),
                    "last_node": payload_data.get("last_node"),
                    "working_profile": payload_data.get("working_profile"),
                    "live_calc_tile": payload_data.get("live_calc_tile"),
                    "calc_results": payload_data.get("calc_results"),
                    "rfq_admissibility": payload_data.get("rfq_admissibility"),
                    "rfq_document": payload_data.get("rfq_document"),
                },
                sort_keys=True,
                default=str,
            )
            if signature == state_update_signature:
                return
            state_update_signature = signature
            await _queue_emit("state_update", payload)

        try:
            async for raw_event in graph.astream_events(state_input, config=config, version="v2"):
                if await request.is_disconnected():
                    raise asyncio.CancelledError()
                if not isinstance(raw_event, dict):
                    continue

                if not _event_belongs_to_current_run(raw_event, expected_run_id):
                    continue

                event_name = str(raw_event.get("event") or "")
                node_name = _resolve_stream_node_name(
                    node_name=raw_event.get("name"),
                    meta=raw_event.get("metadata"),
                )
                data = raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {}

                if event_name in {"on_node_start", "on_chain_start"}:
                    await _queue_emit(
                        "node_status",
                        {
                            "type": "node_status",
                            "node": _human_node_label(node_name),
                            "status": "running",
                        },
                    )
                    continue

                if event_name == "on_chat_model_stream":
                    tags = raw_event.get("tags") or []
                    tagged_nodes = _extract_stream_nodes_from_tags(tags)
                    speaking_nodes = set(tagged_nodes)
                    if node_name:
                        speaking_nodes.add(str(node_name))
                    allowed_speaking_nodes = {
                        "response_node",
                        "contract_first_output_node",
                        "node_finalize",
                        "final_answer_node",
                    }
                    is_speaking = any(node in allowed_speaking_nodes for node in speaking_nodes)
                    if is_speaking:
                        chunk_text = _extract_chunk_text_from_stream_event(data.get("chunk"))
                        if chunk_text:
                            token_seen = True
                            await _queue_emit("text_chunk", {"type": "text_chunk", "text": chunk_text})
                            await _queue_emit("token", {"type": "token", "text": chunk_text})
                    continue

                update_source = _extract_state_update_source(data)
                if isinstance(update_source, (SealAIState, dict)):
                    latest_state = _merge_state_like(latest_state, update_source)

                if event_name in {"on_custom_event", "on_node_end", "on_chain_end"}:
                    await _emit_state_update_if_available()
                    await _emit_terminal_token_if_available(latest_state)

                    profile_payload = _extract_working_profile_payload(latest_state)
                    if profile_payload and (
                        event_name == "on_custom_event"
                        or str(node_name or "") in {"combinatorial_chemistry_guard_node", "reasoning_core_node"}
                    ):
                        await _queue_emit(
                            "profile_update",
                            {
                                "type": "profile_update",
                                "node": _human_node_label(node_name),
                                "working_profile": profile_payload,
                            },
                        )

                    blockers = _extract_blocker_conflicts(latest_state)
                    if blockers:
                        await _queue_emit(
                            "safety_alert",
                            {
                                "type": "safety_alert",
                                "severity": "BLOCKER",
                                "blockers": blockers,
                            },
                        )

                if event_name in {"on_node_end", "on_chain_end"}:
                    await _queue_emit(
                        "node_status",
                        {
                            "type": "node_status",
                            "node": _human_node_label(node_name),
                            "status": "completed",
                        },
                    )

                if event_name == "on_chat_model_end" or (
                    event_name == "on_chain_end" and str(node_name or "") == "reasoning_core_node"
                ):
                    await _queue_emit("turn_complete", {"type": "turn_complete"})
                    await _queue_done()
                    turn_complete_sent = True

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("langgraph_v2_event_multiplexer_error")
            await _queue_emit(
                "error",
                {
                    "type": "error",
                    "message": "internal_error",
                },
            )
            await _queue_emit("turn_complete", {"type": "turn_complete"})
            await _queue_done()
            turn_complete_sent = True
        finally:
            if not turn_complete_sent:
                await _queue_emit("turn_complete", {"type": "turn_complete"})
                await _queue_done()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    producer = asyncio.create_task(_producer())
    try:
        while True:
            if await request.is_disconnected():
                producer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await producer
                return
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=max(0.25, SSE_HEARTBEAT_SEC))
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if frame is None:
                try:
                    if hasattr(graph, "aget_state"):
                        snapshot = await graph.aget_state(config)
                        vals = _state_values_to_dict(snapshot.values if snapshot else {})
                        final = str(_resolve_governed_output_text(vals) or "")
                        if final:
                            logger.info("hitl_final_answer_flushed", extra={"length": len(final)})
                            yield _format_sse_text("token", {"type": "token", "text": final})
                except Exception as _flush_err:
                    logger.warning("hitl_flush_error", extra={"error": str(_flush_err)})
                break
            yield frame
    except asyncio.CancelledError:
        producer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await producer
        return
    finally:
        if not producer.done():
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
        if thread_id:
            await _release_thread_lock(thread_id)


def _merge_state_like(
    current: SealAIState | Dict[str, Any] | None,
    update: SealAIState | Dict[str, Any] | None,
) -> SealAIState | Dict[str, Any] | None:
    def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            current_value = merged.get(key)
            if isinstance(current_value, dict) and isinstance(value, dict):
                merged[key] = _deep_merge(current_value, value)
            else:
                merged[key] = value
        return merged

    update_dict = _state_values_to_dict(update)
    if not update_dict:
        return current
    if isinstance(update_dict, dict) and "parameters" in update_dict:
        raw_parameters = update_dict.pop("parameters")
        if isinstance(raw_parameters, dict):
            working_profile_patch = update_dict.get("working_profile")
            if not isinstance(working_profile_patch, dict):
                working_profile_patch = {}
            extracted_patch = working_profile_patch.get("extracted_params")
            if not isinstance(extracted_patch, dict):
                extracted_patch = {}
            extracted_patch.update(dict(raw_parameters))
            working_profile_patch["extracted_params"] = extracted_patch
            update_dict["working_profile"] = working_profile_patch
    base = _state_values_to_dict(current)
    merged = _deep_merge(base, update_dict)
    update_tile = _working_profile_value(update_dict, "live_calc_tile")
    if not _is_meaningful_live_calc_tile(update_tile):
        current_tile = _working_profile_value(base, "live_calc_tile")
        if _is_meaningful_live_calc_tile(current_tile):
            merged.setdefault("working_profile", {})
            if isinstance(merged["working_profile"], dict):
                merged["working_profile"]["live_calc_tile"] = current_tile
    return merged


def _latest_ai_text(messages: Any, *, after_last_human: bool = False) -> str:
    if not isinstance(messages, list):
        return ""
    scan_from = 0
    if after_last_human:
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            role = getattr(msg, "type", None) or getattr(msg, "role", None)
            if role is None and isinstance(msg, dict):
                role = msg.get("type") or msg.get("role")
            if role in ("human", "user"):
                scan_from = idx + 1
                break
    for msg in reversed(messages[scan_from:]):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role is None and isinstance(msg, dict):
            role = msg.get("type") or msg.get("role")
        if role not in ("ai", "assistant"):
            continue
        text = _flatten_message_content(msg).strip()
        if text:
            return text
    return ""


def _resolve_final_text(state: SealAIState | Dict[str, Any]) -> str:
    if not isinstance(state, (SealAIState, dict)):
        return ""
    return _resolve_governed_output_text(state)


def _extract_terminal_text_candidate(state: SealAIState | Dict[str, Any] | None) -> str:
    if not isinstance(state, (SealAIState, dict)):
        return ""
    return _resolve_governed_output_text(state)


def _extract_final_text_from_patch(data: Any) -> str:
    stack: list[Any] = [data]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current is None:
            continue
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        if isinstance(current, SealAIState):
            text = _extract_terminal_text_candidate(current)
            if text:
                return text
            stack.append(current.model_dump(exclude_none=True))
            continue
        if isinstance(current, dict):
            value = _system_value(current, "governed_output_text")
            if isinstance(value, str) and value.strip():
                return value.strip()
            value = _system_value(current, "final_text")
            if isinstance(value, str) and value.strip():
                return value.strip()
            value = _system_value(current, "final_answer")
            if isinstance(value, str) and value.strip():
                return value.strip()
            chunk_type = current.get("chunk_type")
            if isinstance(chunk_type, str) and chunk_type.strip().lower() == "final_answer":
                for key in ("text", "content", "message", "delta"):
                    text = _flatten_message_content(current.get(key)).strip()
                    if text:
                        return text
            for key in ("output", "state", "final_state", "values", "result", "chunk", "patch", "update", "delta", "data"):
                nested = current.get(key)
                if nested is not None:
                    stack.append(nested)
            for nested in current.values():
                if isinstance(nested, (dict, list, tuple, SealAIState)):
                    stack.append(nested)
            continue
        if isinstance(current, (list, tuple)):
            stack.extend(current)
    return ""


def _extract_prompt_trace_metadata(*, data: Any = None, state: Any = None) -> tuple[str | None, str | None]:
    """Return (prompt_hash, prompt_version) from node output/state for trace events."""
    candidates: list[Any] = [data]
    if isinstance(state, SealAIState):
        candidates.append(state.model_dump(exclude_none=True))
    elif isinstance(state, dict):
        candidates.append(state)

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw_meta = _system_value(candidate, "final_prompt_metadata")
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        raw_hash = meta.get("prompt_hash") or meta.get("hash")
        prompt_hash = str(raw_hash).strip() if raw_hash else None
        raw_version = (
            meta.get("prompt_version")
            or meta.get("version")
            or meta.get("safety_check_version")
        )
        prompt_version = str(raw_version).strip() if raw_version else None

        if not prompt_hash:
            prompt_text = _system_value(candidate, "final_prompt")
            if isinstance(prompt_text, str) and prompt_text.strip():
                prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

        if prompt_hash or prompt_version:
            return prompt_hash, prompt_version

    return None, None


def _build_trace_payload(
    *,
    mode: str,
    data: Any,
    meta: Any,
    state: Any,
) -> Dict[str, str]:
    node_name = _extract_trace_node(meta=meta, data=data, state=state)
    phase = _extract_trace_phase(data=data, state=state)
    action = _extract_trace_action(data=data, state=state)
    prompt_hash, prompt_version = _extract_prompt_trace_metadata(data=data, state=state)
    payload = {
        "node": node_name,
        "type": mode,
        "phase": phase,
        "action": action,
        "prompt_hash": prompt_hash,
        "prompt_version": prompt_version,
    }
    return {key: value for key, value in payload.items() if value}


_DEDUP_REDIS: Redis | None = None


async def _get_dedup_redis() -> Redis | None:
    global _DEDUP_REDIS
    if _DEDUP_REDIS is not None:
        return _DEDUP_REDIS
    if Redis is None:
        return None
    conn_string = os.getenv("LANGGRAPH_V2_REDIS_URL") or os.getenv("REDIS_URL")
    if not conn_string:
        return None
    _DEDUP_REDIS = Redis.from_url(conn_string, decode_responses=True)
    return _DEDUP_REDIS


async def _claim_client_msg_id(*, user_id: str, chat_id: str, client_msg_id: str) -> bool:
    if not client_msg_id:
        return True
    client = await _get_dedup_redis()
    if client is None:
        return True
    key = f"langgraph_v2:dedup:{user_id}:{chat_id}:{client_msg_id}"
    try:
        claimed = await client.set(key, "1", nx=True, ex=DEDUP_TTL_SEC)
        return bool(claimed)
    except Exception:
        logger.exception("langgraph_v2_dedup_failed", extra={"chat_id": chat_id, "user": user_id})
        return True


async def _claim_thread_lock(thread_id: str, ttl: int = 120) -> bool:
    """Try to claim a concurrency lock for a thread_id. Return True if successful."""
    client = await _get_dedup_redis()
    if client is None:
        return True
    key = f"langgraph_v2:lock:{thread_id}"
    try:
        # Default 120s TTL to prevent permanent locks if a worker crashes.
        claimed = await client.set(key, "1", nx=True, ex=ttl)
        return bool(claimed)
    except Exception:
        logger.exception("langgraph_v2_lock_claim_failed", extra={"chat_id": thread_id})
        return True


async def _release_thread_lock(thread_id: str):
    """Release the concurrency lock for a thread_id."""
    client = await _get_dedup_redis()
    if client is None:
        return
    key = f"langgraph_v2:lock:{thread_id}"
    try:
        await client.delete(key)
    except Exception:
        logger.exception("langgraph_v2_lock_release_failed", extra={"chat_id": thread_id})


async def _event_stream_v2(
    req: LangGraphV2Request,
    *,
    user_id: str | None = None,
    username: str | None = None,
    auth_scopes: list[str] | None = None,
    tenant_id: str | None = None,
    legacy_user_id: str | None = None,
    request_id: str | None = None,
    last_event_id: str | None = None,
) -> AsyncIterator[bytes]:
    if user_id:
        req.chat_id = _scope_thread_id_for_user(user_id=user_id, thread_id=req.chat_id)
    stream_task: asyncio.Task[None] | None = None
    broadcast_task: asyncio.Task[None] | None = None
    broadcast_queue: asyncio.Queue[tuple[int, str, Dict[str, Any]]] | None = None
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=SSE_QUEUE_MAXSIZE)
    last_slow_notice = 0.0
    scoped_user_id = user_id or "anonymous"
    sticky_live_calc_tile: Dict[str, Any] | None = None
    initial_stream_values: Dict[str, Any] = {}
    try:
        resolved_user_id = user_id or "anonymous"
        scoped_user_id = resolved_user_id
        graph, config = await _build_graph_config(
            thread_id=req.chat_id,
            user_id=resolved_user_id,
            username=username,
            auth_scopes=auth_scopes,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        scoped_user_id = _config_user_id(config, resolved_user_id)
        initial_stream_values = await _get_graph_state_values_for_stream(graph, config)
        sticky_live_calc_tile = _normalize_live_calc_tile(_working_profile_value(initial_stream_values, "live_calc_tile"))

        async def _enqueue_frame(frame: bytes, *, allow_slow_notice: bool = True) -> None:
            nonlocal last_slow_notice
            if queue.maxsize <= 0:
                queue.put_nowait(frame)
                return

            send_slow_notice = False
            if queue.full():
                now = time.time()
                if allow_slow_notice and now - last_slow_notice >= SSE_SLOW_NOTICE_SEC:
                    send_slow_notice = True
                    last_slow_notice = now

                while queue.qsize() > queue.maxsize - 1:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

            if queue.qsize() <= queue.maxsize - 1:
                queue.put_nowait(frame)

            if send_slow_notice and queue.maxsize >= 2:
                while queue.qsize() > queue.maxsize - 1:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                if queue.qsize() <= queue.maxsize - 1:
                    slow_seq = await sse_broadcast.record_event(
                        user_id=scoped_user_id,
                        chat_id=req.chat_id,
                        event="slow_client",
                        data={"reason": "backpressure"},
                    )
                    slow_frame = _format_sse(
                        "slow_client",
                        {"reason": "backpressure"},
                        event_id=str(slow_seq),
                    )
                    queue.put_nowait(slow_frame)

        async def _emit_event(event_name: str, payload: Dict[str, Any]) -> None:
            nonlocal sticky_live_calc_tile
            if event_name == "state_update":
                payload_data = payload.get("data")
                candidate_tile = None
                if isinstance(payload_data, dict):
                    candidate_tile = _normalize_live_calc_tile(payload_data.get("live_calc_tile"))
                if candidate_tile is None:
                    candidate_tile = _normalize_live_calc_tile(payload.get("live_calc_tile"))
                if candidate_tile is not None:
                    sticky_live_calc_tile = candidate_tile
                _inject_live_calc_tile(payload, live_calc_tile=sticky_live_calc_tile)
            seq = await sse_broadcast.record_event(
                user_id=scoped_user_id,
                chat_id=req.chat_id,
                event=event_name,
                data=payload,
            )
            frame = _format_sse(event_name, payload, event_id=str(seq))
            await _enqueue_frame(frame)

        broadcast_queue = await sse_broadcast.subscribe(user_id=scoped_user_id, chat_id=req.chat_id)

        async def _broadcast_forwarder() -> None:
            nonlocal sticky_live_calc_tile
            if broadcast_queue is None:
                return
            try:
                while True:
                    item = await broadcast_queue.get()
                    if not item:
                        continue
                    seq, event_name, payload = item
                    if event_name == "state_update":
                        candidate_tile = None
                        payload_data = payload.get("data") if isinstance(payload, dict) else None
                        if isinstance(payload_data, dict):
                            candidate_tile = _normalize_live_calc_tile(payload_data.get("live_calc_tile"))
                        if candidate_tile is None and isinstance(payload, dict):
                            candidate_tile = _normalize_live_calc_tile(payload.get("live_calc_tile"))
                        if candidate_tile is not None:
                            sticky_live_calc_tile = candidate_tile
                        if isinstance(payload, dict):
                            _inject_live_calc_tile(payload, live_calc_tile=sticky_live_calc_tile)
                    frame = _format_sse(event_name, payload, event_id=str(seq))
                    await _enqueue_frame(frame)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception(
                    "langgraph_v2_sse_broadcast_error",
                    extra={"chat_id": req.chat_id, "user_id": scoped_user_id},
                )

        await _enqueue_frame(f"retry: {SSE_RETRY_MS}\n\n".encode("utf-8"), allow_slow_notice=False)

        last_seq = _parse_last_event_id(last_event_id, chat_id=req.chat_id)
        if last_seq is not None:
            replay, buffer_miss = await sse_broadcast.replay_after(
                user_id=scoped_user_id,
                chat_id=req.chat_id,
                last_seq=last_seq,
            )
            if buffer_miss:
                await _emit_event(
                    "resync_required",
                    {"reason": "buffer_miss"},
                )
            else:
                for item in replay:
                    frame = _format_sse(
                        item.get("event", ""),
                        item.get("data", {}),
                        event_id=str(item.get("seq", 0)),
                    )
                    await _enqueue_frame(frame)

        broadcast_task = asyncio.create_task(_broadcast_forwarder())
        snapshot = _extract_param_snapshot(req)
        snapshot_versions = _snapshot_versions(snapshot)
        if WARN_STALE_PARAM_SNAPSHOT and snapshot_versions:
            try:
                state_values = dict(initial_stream_values)
                if not state_values and hasattr(graph, "aget_state"):
                    server_snapshot = await graph.aget_state(config)
                    state_values = _state_values_to_dict(server_snapshot.values)
                server_versions = _reasoning_value(state_values, "parameter_versions") if isinstance(state_values, dict) else {}
                stale_count = 0
                if isinstance(server_versions, dict):
                    for key, snap_value in snapshot_versions.items():
                        server_value = server_versions.get(key)
                        if isinstance(server_value, (int, float)) and int(snap_value) < int(server_value):
                            stale_count += 1
                if stale_count:
                    logger.warning(
                        "stale_param_snapshot",
                        extra={
                            "request_id": request_id,
                            "chat_id": req.chat_id,
                            "user_id": scoped_user_id,
                            "stale_count": stale_count,
                            "snapshot_versions_count": len(snapshot_versions),
                        },
                    )
            except Exception:
                logger.exception(
                    "param_snapshot_compare_failed",
                    extra={
                        "request_id": request_id,
                        "chat_id": req.chat_id,
                        "user_id": scoped_user_id,
                    },
                )
        trace_enabled = _lg_trace_enabled()
        metadata = config.get("metadata") if isinstance(config, dict) else {}
        run_id = metadata.get("run_id") if isinstance(metadata, dict) else None
        prev_parameters: Dict[str, Any] = {}
        initial_state = SealAIState(
            conversation={
                "user_id": scoped_user_id,
                "thread_id": req.chat_id,
                "messages": [HumanMessage(content=req.input)],
                "user_context": {"auth_scopes": list(auth_scopes or []), "tenant_id": tenant_id},
            },
            system={"tenant_id": tenant_id},
        )

        token_count = 0
        done_sent = False
        latest_state: SealAIState | Dict[str, Any] = initial_state
        last_trace_signature: tuple[Any, Any, Any, Any] | None = None
        last_retrieval_signature: tuple[Any, Any] | None = None

        async def _emit_trace(mode: str, *, data: Any = None, meta: Any = None, state: Any = None) -> None:
            nonlocal last_trace_signature
            if not trace_enabled:
                return
            payload = _build_trace_payload(mode=mode, data=data, meta=meta, state=state)
            if not payload:
                return
            signature = (
                payload.get("node"),
                payload.get("type"),
                payload.get("phase"),
                payload.get("action"),
                payload.get("prompt_hash"),
                payload.get("prompt_version"),
            )
            if signature == last_trace_signature:
                return
            last_trace_signature = signature
            payload["ts"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            logger.info(
                "langgraph_v2_trace",
                    extra={
                        "thread_id": req.chat_id,
                        "chat_id": req.chat_id,
                        "user_id": scoped_user_id,
                        "run_id": run_id,
                        "request_id": request_id,
                        "node": payload.get("node"),
                    "event_type": payload.get("type"),
                    "phase": payload.get("phase"),
                    "supervisor_action": payload.get("action"),
                    "prompt_hash": payload.get("prompt_hash"),
                    "prompt_version": payload.get("prompt_version"),
                },
            )
            await _emit_event("trace", payload)

        async def _producer() -> None:
            nonlocal latest_state, token_count, done_sent, sticky_live_calc_tile
            live_tile_stream_signature: str | None = None
            rfq_document_stream_signature: str | None = None
            streamed_text_parts: list[str] = []
            terminal_final_text: str = ""
            latest_patch_final_text: str = ""
            terminal_nodes = {
                "node_finalize",
                "node_safe_fallback",
                "final_answer_node",
                "response_node",
                "node_p4b_calc_render",
                "p4b_calc_render",
            }

            async def _emit_state_update_if_changed(
                *,
                update_source: SealAIState | Dict[str, Any] | None,
                node_hint: str | None = None,
            ) -> None:
                nonlocal live_tile_stream_signature, rfq_document_stream_signature, sticky_live_calc_tile
                if not isinstance(update_source, (SealAIState, dict)):
                    return

                source_values = _state_values_to_dict(update_source)
                payload = _build_state_update_payload(update_source)
                source_tile = _normalize_live_calc_tile(_working_profile_value(source_values, "live_calc_tile"))
                if source_tile is not None:
                    sticky_live_calc_tile = source_tile
                _inject_live_calc_tile(payload, live_calc_tile=sticky_live_calc_tile)
                payload_data = payload.get("data")
                if not isinstance(payload_data, dict):
                    return

                should_emit = False
                has_live_calc_tile = _is_meaningful_live_calc_tile(payload_data.get("live_calc_tile"))
                should_emit_live_tile = has_live_calc_tile
                if should_emit_live_tile:
                    tile = payload_data.get("live_calc_tile", {})
                    tile_signature = json.dumps(tile, sort_keys=True, default=str)
                    if tile_signature != live_tile_stream_signature:
                        live_tile_stream_signature = tile_signature
                        should_emit = True

                rfq_admissibility = payload_data.get("rfq_admissibility")
                has_rfq_document = bool(
                    isinstance(rfq_admissibility, dict)
                    and (
                        rfq_admissibility.get("governed_ready")
                        or rfq_admissibility.get("status")
                        or rfq_admissibility.get("reason")
                    )
                )
                should_emit_rfq = bool(has_rfq_document)
                if should_emit_rfq:
                    rfq_document = payload_data.get("rfq_document", {})
                    rfq_signature = json.dumps(rfq_document, sort_keys=True, default=str)
                    if rfq_signature != rfq_document_stream_signature:
                        rfq_document_stream_signature = rfq_signature
                        should_emit = True

                if should_emit:
                    await _emit_event("state_update", payload)

            stream_error_emitted = False
            producer_cancelled = False
            try:
                if hasattr(graph, "astream_events"):
                    event_count = 0
                    if SSE_DEBUG or _lg_trace_enabled():
                        logger.info(
                            "langgraph_v2_stream_mode",
                            extra={
                                "request_id": request_id,
                                "chat_id": req.chat_id,
                                "user_id": scoped_user_id,
                                "mode": "astream_events",
                            },
                        )
                    async for raw_event in graph.astream_events(initial_state, config=config):
                        event = raw_event if isinstance(raw_event, dict) else {}
                        if not isinstance(raw_event, dict):
                            continue
                        event_count += 1
                        event_name = str(raw_event.get("event") or "")
                        node_name = str(raw_event.get("name") or "")
                        data = raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {}
                        if event_name in {
                            "on_node_end",
                            "on_chain_end",
                            "on_graph_end",
                            "on_chain_stream",
                            "on_graph_stream",
                        }:
                            patch_final_text = _extract_final_text_from_patch(data)
                            if patch_final_text:
                                latest_patch_final_text = patch_final_text
                                terminal_final_text = patch_final_text
                        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        if event_name == "on_node_start":
                            await _emit_event("node_start", {"node": node_name, "ts": ts})
                            await _emit_trace("node_start", data=data, meta=raw_event.get("metadata"), state=latest_state)
                        elif event_name == "on_chat_model_stream":
                            if not _event_belongs_to_current_run(raw_event, run_id):
                                continue
                            chunk = data.get("chunk") if isinstance(data, dict) else None
                            stream_node = _resolve_stream_node_name(
                                node_name=node_name,
                                meta=raw_event.get("metadata"),
                            )
                            text = _extract_stream_token_text(chunk, stream_node=stream_node, state=latest_state)
                            if isinstance(text, str) and text:
                                streamed_text_parts.append(text)
                                token_count += 1
                                await _emit_event("token", {"type": "token", "text": text})
                        elif event_name == "on_node_end":
                            await _emit_event("node_end", {"node": node_name, "ts": ts})
                            # Prometheus node counter — never raises
                            try:
                                from app.core.metrics import graph_node_runs_total
                                if node_name:
                                    graph_node_runs_total.labels(node=node_name).inc()
                            except Exception:
                                pass
                            output = data.get("output")
                            if isinstance(output, (SealAIState, dict)):
                                latest_state = _merge_state_like(latest_state, output)
                            update_source = _extract_state_update_source(data)
                            if isinstance(update_source, (SealAIState, dict)):
                                latest_state = _merge_state_like(latest_state, update_source)
                            else:
                                update_source = (
                                    output if isinstance(output, (SealAIState, dict)) else latest_state
                                )
                            if node_name in terminal_nodes:
                                terminal_candidate = _extract_terminal_text_candidate(update_source)
                                if not terminal_candidate and isinstance(output, (SealAIState, dict)):
                                    terminal_candidate = _extract_terminal_text_candidate(output)
                                if terminal_candidate:
                                    terminal_final_text = terminal_candidate
                            await _emit_state_update_if_changed(update_source=update_source, node_hint=node_name)
                            await _emit_trace(
                                "node_end",
                                data=(output if isinstance(output, (SealAIState, dict)) else data),
                                meta=raw_event.get("metadata"),
                                state=latest_state,
                            )
                        elif event_name in {"on_chain_end", "on_graph_end"}:
                            update_source = _extract_state_update_source(data)
                            if isinstance(update_source, (SealAIState, dict)):
                                latest_state = _merge_state_like(latest_state, update_source)
                                terminal_candidate = _extract_terminal_text_candidate(update_source)
                                if terminal_candidate:
                                    terminal_final_text = terminal_candidate
                            else:
                                update_source = latest_state
                            await _emit_state_update_if_changed(update_source=update_source, node_hint=node_name)

                            await _emit_trace(
                                event_name.replace("on_", ""),
                                data=(update_source if isinstance(update_source, (SealAIState, dict)) else data),
                                meta=raw_event.get("metadata"),
                                state=latest_state,
                            )
                        elif event_name == "on_error":
                            if not stream_error_emitted:
                                stream_error_emitted = True
                                await _emit_event(
                                    "error",
                                    {
                                        "type": "error",
                                        "message": "internal_error",
                                        "request_id": request_id,
                                    },
                                )
                    if SSE_DEBUG or _lg_trace_enabled():
                        logger.info(
                            "langgraph_v2_stream_mode_complete",
                            extra={
                                "request_id": request_id,
                                "chat_id": req.chat_id,
                                "user_id": scoped_user_id,
                                "mode": "astream_events",
                                "event_count": event_count,
                                "token_count": token_count,
                            },
                        )
                elif hasattr(graph, "astream"):
                    async for mode, data in graph.astream(initial_state, config=config, stream_mode=["messages", "values"]):
                        if mode == "messages":
                            token, meta = data if isinstance(data, tuple) and len(data) == 2 else (data, None)
                            stream_node = _resolve_stream_node_name(meta=meta)
                            text = _extract_stream_token_text(token, stream_node=stream_node, state=latest_state)
                            if isinstance(text, str) and text:
                                streamed_text_parts.append(text)
                                token_count += 1
                                await _emit_event("token", {"type": "token", "text": text})
                        elif mode == "values":
                            if isinstance(data, (SealAIState, dict)):
                                latest_state = _merge_state_like(latest_state, data)
                                terminal_candidate = _extract_terminal_text_candidate(data)
                                if terminal_candidate:
                                    terminal_final_text = terminal_candidate
                                    latest_patch_final_text = terminal_candidate
                                await _emit_trace("values", data=data, state=latest_state)
                                node_hint = None
                                if isinstance(data, SealAIState):
                                    node_hint = data.reasoning.last_node
                                elif isinstance(data, dict):
                                    last_node = _reasoning_value(data, "last_node")
                                    node_hint = last_node if isinstance(last_node, str) else None
                                await _emit_state_update_if_changed(update_source=data, node_hint=node_hint)

            except asyncio.CancelledError:
                producer_cancelled = True
                raise
            except Exception as exc:  # pragma: no cover
                logger.exception(
                    "langgraph_v2_sse_stream_error",
                    extra={
                        "request_id": request_id,
                        "chat_id": req.chat_id,
                        "client_msg_id": req.client_msg_id,
                        "thread_id": req.chat_id,
                        "user_id": scoped_user_id,
                        "supervisor_mode": os.getenv("LANGGRAPH_V2_SUPERVISOR_MODE"),
                    },
                )
                if not stream_error_emitted:
                    stream_error_emitted = True
                    message = "dependency_unavailable" if is_dependency_unavailable_error(exc) else "internal_error"
                    await _emit_event("error", {"type": "error", "message": message, "request_id": request_id})
            finally:
                try:
                    if not producer_cancelled:
                        result_state: SealAIState = latest_state if isinstance(latest_state, SealAIState) else initial_state
                        done_payload: Dict[str, Any] = {
                            "type": "done",
                            "chat_id": req.chat_id,
                            "request_id": request_id,
                            "client_msg_id": req.client_msg_id,
                        }
                        try:
                            snapshot = None
                            final_state = None
                            final_state_values: Dict[str, Any] = {}
                            final_state = await graph.aget_state(config)
                            snapshot = final_state
                            if hasattr(final_state, "values"):
                                final_state_values = _state_values_to_dict(final_state.values)
                                if final_state_values:
                                    latest_state = _merge_state_like(latest_state, final_state.values)

                            result_state = (
                                latest_state
                                if isinstance(latest_state, SealAIState)
                                else SealAIState.model_validate(latest_state or {})
                            )
                            state_values = _state_values_to_dict(result_state)
                            await _emit_state_update_if_changed(
                                update_source=result_state,
                                node_hint=result_state.reasoning.last_node,
                            )
                            interrupted = bool(snapshot is not None and _snapshot_waiting_on_human_review(snapshot))
                            if interrupted:
                                checkpoint_id = _extract_snapshot_checkpoint_id(
                                    snapshot,
                                    state_values,
                                    fallback=f"{req.chat_id}:{uuid.uuid4().hex}",
                                )
                                await _emit_event(
                                    "interrupt",
                                    {
                                        "thread_id": req.chat_id,
                                        "checkpoint_id": checkpoint_id,
                                        "reason": "Paused before human_review_node",
                                        "required_action": "approve_specification",
                                    },
                                )
                            if _should_emit_confirm_checkpoint(result_state):
                                checkpoint_payload = result_state.system.confirm_checkpoint or {
                                    "checkpoint_id": result_state.system.confirm_checkpoint_id,
                                    "action": str(result_state.system.pending_action or "human_review"),
                                    "risk": "med",
                                }
                                await _emit_event(
                                    "checkpoint_required",
                                    {
                                        "chat_id": req.chat_id,
                                        "checkpoint_id": checkpoint_payload.get("checkpoint_id"),
                                        "pending_action": checkpoint_payload.get("action"),
                                        "risk": checkpoint_payload.get("risk"),
                                    },
                                )
                            final_text = ""
                            if final_state_values:
                                state_final_text = _system_value(final_state_values, "final_text") or _system_value(final_state_values, "final_answer")
                                if isinstance(state_final_text, str) and state_final_text.strip():
                                    final_text = state_final_text.strip()
                                elif terminal_final_text or latest_patch_final_text:
                                    final_text = str(terminal_final_text or latest_patch_final_text).strip()
                                else:
                                    snapshot_message_text = _latest_ai_text(_conversation_value(final_state_values, "messages") or []).strip()
                                    if snapshot_message_text:
                                        final_text = snapshot_message_text
                            if not final_text:
                                if terminal_final_text:
                                    final_text = str(terminal_final_text).strip()
                                elif latest_patch_final_text:
                                    final_text = str(latest_patch_final_text).strip()
                                else:
                                    final_text = str(_resolve_final_text(result_state)).strip()
                            streamed_text = "".join(streamed_text_parts).strip()
                            should_emit_final_text = bool(final_text) and ((not streamed_text) or (streamed_text != final_text))
                            if final_text:
                                # Emit an authoritative terminal assistant payload from final state so clients
                                # can replace partial/stale content from token-only streaming paths.
                                await _emit_event(
                                    "message",
                                    {
                                        "type": "message",
                                        "text": final_text,
                                        "replace": True,
                                        "source": "final_state",
                                    },
                                )
                            if should_emit_final_text:
                                # Frontend appends only `type=token` + `text` payloads to the active assistant turn.
                                logger.info(f"Emitting final SSE text of length: {len(final_text)}")
                                await _emit_event("token", {"type": "token", "text": final_text})

                            done_payload.update(
                                {
                                    "phase": result_state.reasoning.phase,
                                    "last_node": result_state.reasoning.last_node,
                                    "awaiting_confirmation": bool(result_state.system.awaiting_user_confirmation),
                                    "checkpoint_id": result_state.system.confirm_checkpoint_id,
                                }
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            logger.exception(
                                "langgraph_v2_sse_finalize_error",
                                extra={
                                    "request_id": request_id,
                                    "chat_id": req.chat_id,
                                    "client_msg_id": req.client_msg_id,
                                    "thread_id": req.chat_id,
                                    "user_id": scoped_user_id,
                                },
                            )
                        finally:
                            if not done_sent:
                                try:
                                    await _emit_event("done", done_payload)
                                    done_sent = True
                                except Exception:
                                    logger.exception(
                                        "langgraph_v2_sse_done_emit_failed",
                                        extra={
                                            "request_id": request_id,
                                            "chat_id": req.chat_id,
                                            "client_msg_id": req.client_msg_id,
                                            "thread_id": req.chat_id,
                                            "user_id": scoped_user_id,
                                        },
                                    )

                            # Audit log — fire-and-forget, never blocks
                            try:
                                from app.services.audit.audit_logger import get_global_audit_logger
                                _al = get_global_audit_logger()
                                if _al is not None:
                                    _al.append(
                                        session_id=req.chat_id,
                                        tenant_id=tenant_id,
                                        state=_state_values_to_dict(result_state),
                                    )
                            except Exception:
                                pass
                finally:
                    await queue.put(None)

        stream_task = asyncio.create_task(_producer())

        while True:
            if SSE_HEARTBEAT_SEC > 0:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_SEC)
                except asyncio.TimeoutError:
                    # Keep proxy/browser SSE connections warm during long-running graph steps.
                    yield ": keep-alive\n\n"
                    continue
            else:
                item = await queue.get()
            if item is None:
                break
            yield item.decode("utf-8") if isinstance(item, bytes) else item
    except asyncio.CancelledError:
        done_payload = {
            "type": "done",
            "chat_id": req.chat_id,
            "request_id": request_id,
            "client_msg_id": req.client_msg_id,
        }
        seq = await sse_broadcast.record_event(
            user_id=scoped_user_id,
            chat_id=req.chat_id,
            event="done",
            data=done_payload,
        )
        yield _format_sse("done", done_payload, event_id=str(seq)).decode("utf-8")
        return
    except Exception as exc:  # pragma: no cover
        logger.exception(
            "langgraph_v2_sse_outer_error",
            extra={
                "request_id": request_id,
                "chat_id": req.chat_id,
                "client_msg_id": req.client_msg_id,
                "thread_id": req.chat_id,
                "user_id": scoped_user_id,
                "supervisor_mode": os.getenv("LANGGRAPH_V2_SUPERVISOR_MODE"),
            },
        )
        message = "dependency_unavailable" if is_dependency_unavailable_error(exc) else "internal_error"
        error_payload = {"type": "error", "message": message, "request_id": request_id}
        error_seq = await sse_broadcast.record_event(
            user_id=scoped_user_id,
            chat_id=req.chat_id,
            event="error",
            data=error_payload,
        )
        yield _format_sse("error", error_payload, event_id=str(error_seq)).decode("utf-8")
        done_payload = {
            "type": "done",
            "chat_id": req.chat_id,
            "request_id": request_id,
            "client_msg_id": req.client_msg_id,
        }
        done_seq = await sse_broadcast.record_event(
            user_id=scoped_user_id,
            chat_id=req.chat_id,
            event="done",
            data=done_payload,
        )
        yield _format_sse("done", done_payload, event_id=str(done_seq)).decode("utf-8")
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
        if broadcast_task and not broadcast_task.done():
            broadcast_task.cancel()
        if broadcast_queue is not None:
            await sse_broadcast.unsubscribe(
                user_id=scoped_user_id,
                chat_id=req.chat_id,
                queue=broadcast_queue,
            )


@router.post("/chat/v2")
async def langgraph_chat_v2_endpoint(
    request: LangGraphV2Request,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> StreamingResponse:
    """Primary chat endpoint for the v13 two-speed runtime.

    Interception workflow:

    1. Authenticate the request, deduplicate `client_msg_id`, and claim the
       thread lock exactly as before. Fast-Brain interception must remain
       invisible to auth and checkpoint semantics.
    2. Load the current checkpoint state and pass recent conversation history to
       the Fast Brain.
    3. Branch on the Fast-Brain status:

       - `chat_continue`
         The Fast Brain fully answers the turn. We sync any extracted
         parameters / live physics outputs into the checkpoint, persist the
         transcript for this turn, and stream the response directly as SSE
         (`state_update` -> `text_chunk` -> `turn_complete`). The LangGraph is
         not started.

       - `handoff_to_langgraph`
         The Fast Brain has gathered enough context to wake the Slow Brain. We
         first sync its state contributions into the checkpoint so the graph
         sees the same engineering profile and deterministic tool outputs, then
         start the existing `event_multiplexer` flow unchanged.

    The practical consequence is intentional: a simple chat request may return
    instantly without graph execution, while a sufficiently "engineering-heavy"
    request escalates into the LangGraph Expert Council using the same REST
    endpoint and thread state.
    """
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    last_event_id = raw_request.headers.get("Last-Event-ID")
    snapshot = _extract_param_snapshot(request)
    version_count, updated_max = _snapshot_stats(snapshot)
    if REQUIRE_PARAM_SNAPSHOT and not snapshot:
        raise HTTPException(
            status_code=400,
            detail=error_detail("missing_param_snapshot", request_id=request_id),
        )
    scoped_user_id = canonical_user_id(user)
    request.chat_id = _scope_thread_id_for_user(user_id=scoped_user_id, thread_id=request.chat_id)
    legacy_user_id = user.sub if user.sub and user.sub != scoped_user_id else None
    if request.client_msg_id:
        claimed = await _claim_client_msg_id(
            user_id=scoped_user_id,
            chat_id=request.chat_id,
            client_msg_id=request.client_msg_id,
        )
        if not claimed:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "duplicate_client_msg_id",
                    request_id=request_id,
                    client_msg_id=request.client_msg_id,
                ),
            )
    owner_id = user.sub
    if owner_id:
        try:
            upsert_conversation(
                owner_id=owner_id,
                conversation_id=request.chat_id,
                first_user_message=request.input,
                last_preview=request.input,
                updated_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist conversation metadata before streaming",
                exc_info=exc,
                extra={"user": owner_id, "chat_id": request.chat_id},
            )
    logger.info(
        "langgraph_v2_chat_request",
        extra={
            "request_id": request_id,
            "chat_id": request.chat_id,
            "user": user.user_id,
            "username": user.username,
            "client_msg_id": request.client_msg_id,
            "last_event_id": last_event_id,
            "param_snapshot_present": bool(snapshot),
            "param_snapshot_versions_count": version_count,
            "param_snapshot_updated_at_max": updated_max,
        },
    )
    scope_values = sorted({str(scope).strip() for scope in (user.scopes or []) if str(scope).strip()})
    has_mcp_pim_read = "mcp:pim:read" in scope_values
    has_mcp_knowledge_read = "mcp:knowledge:read" in scope_values
    logger.info(
        "langgraph_v2_auth_scopes",
        extra={
            "request_id": request_id,
            "chat_id": request.chat_id,
            "user": user.user_id,
            "username": user.username,
            "scope_count": len(scope_values),
            "scopes": scope_values,
            "has_mcp_pim_read": has_mcp_pim_read,
            "has_mcp_knowledge_read": has_mcp_knowledge_read,
        },
    )
    # Concurrency check: Ensure only one active run per thread_id.
    locked = await _claim_thread_lock(request.chat_id, ttl=300)
    if not locked:
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "thread_locked",
                request_id=request_id,
                message="Another request is already processing for this thread. Please wait.",
            ),
        )

    try:
        graph, config = await _build_graph_config(
            thread_id=request.chat_id,
            user_id=scoped_user_id,
            username=user.username,
            auth_scopes=user.scopes,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        state_values = await _get_graph_state_values_for_stream(graph, config)
        fast_brain_result: Dict[str, Any] | None = None
        try:
            fast_brain_result = await _get_fast_brain_router().chat(
                user_input=request.input,
                history=_extract_fast_brain_history(state_values),
            )
        except Exception:
            logger.exception(
                "fast_brain_router_failed",
                extra={
                    "request_id": request_id,
                    "chat_id": request.chat_id,
                    "user_id": scoped_user_id,
                },
            )

        headers = {
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        if request_id:
            headers["X-Request-Id"] = request_id

        if isinstance(fast_brain_result, dict):
            fast_status = _normalize_fast_brain_status(fast_brain_result)
            logger.info(
                "langgraph_v2_fast_brain_route",
                extra={
                    "request_id": request_id,
                    "chat_id": request.chat_id,
                    "user_id": scoped_user_id,
                    "status": fast_status,
                    "has_state_patch": bool(_coerce_fast_brain_state_patch(fast_brain_result)),
                },
            )
            if fast_status == "chat_continue":
                # Fast path: no graph run. Persist the reply and stream it back
                # with the SSE contract expected by the frontend.
                synced_state = await _sync_fast_brain_checkpoint_state(
                    graph=graph,
                    config=config,
                    user_input=request.input,
                    fast_brain_result=fast_brain_result,
                    request_id=request_id,
                    persist_transcript=True,
                )
                stream = _fast_brain_sse_stream(
                    request=raw_request,
                    thread_id=request.chat_id,
                    fast_brain_result=fast_brain_result,
                    state_values=synced_state,
                )
                return EventSourceResponse(stream, headers=headers)

            if fast_status == "handoff_to_langgraph":
                # Handoff path: checkpoint Fast-Brain discoveries first so the
                # LangGraph starts from the already-enriched digital twin.
                await _sync_fast_brain_checkpoint_state(
                    graph=graph,
                    config=config,
                    user_input=request.input,
                    fast_brain_result=fast_brain_result,
                    request_id=request_id,
                    persist_transcript=False,
                )

        state_input = SealAIState(
            conversation={
                "user_id": scoped_user_id,
                "thread_id": request.chat_id,
                "messages": [HumanMessage(content=request.input)],
                "user_context": {"auth_scopes": list(user.scopes or []), "tenant_id": user.tenant_id},
            },
            system={"tenant_id": user.tenant_id},
        )
        stream = event_multiplexer(graph, state_input, config, raw_request)
        return StreamingResponse(stream, media_type="text/event-stream", headers=headers)
    except Exception:
        # If we failed before returning the stream, release the lock immediately.
        await _release_thread_lock(request.chat_id)
        raise


@router.post("/confirm/go")
async def confirm_go(
    body: ConfirmGoRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    scoped_user_id = canonical_user_id(user)
    body.chat_id = _scope_thread_id_for_user(user_id=scoped_user_id, thread_id=body.chat_id)
    legacy_user_id = user.sub if user.sub and user.sub != scoped_user_id else None

    # Concurrency check: Ensure only one active run per thread_id.
    locked = await _claim_thread_lock(body.chat_id, ttl=300)
    if not locked:
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "thread_locked",
                request_id=request_id,
                message="Another request is already processing for this thread. Please wait.",
            ),
        )

    try:
        if not (body.chat_id or "").strip():
            raise HTTPException(status_code=400, detail=error_detail("missing_chat_id", request_id=request_id))
        if not body.decision:
            raise HTTPException(status_code=400, detail=error_detail("missing_decision", request_id=request_id))
        graph, config = await _build_graph_config(
            thread_id=body.chat_id,
            user_id=scoped_user_id,
            username=user.username,
            auth_scopes=user.scopes,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        snapshot = await graph.aget_state(config)
        state_values = _state_values_to_dict(snapshot.values)
        confirm_payload = _system_value(state_values, "confirm_checkpoint") if isinstance(state_values, dict) else {}
        if not isinstance(confirm_payload, dict):
            confirm_payload = {}
        confirm_status = _system_value(state_values, "confirm_status") if isinstance(state_values, dict) else None
        required_sub = ""
        if confirm_payload:
            required_sub = str(confirm_payload.get("required_user_sub") or "")
        pending_action = _system_value(state_values, "pending_action") if isinstance(state_values, dict) else None
        checkpoint_id = _system_value(state_values, "confirm_checkpoint_id") if isinstance(state_values, dict) else None
        if confirm_status == "resolved":
            raise HTTPException(
                status_code=409,
                detail=error_detail("checkpoint_already_resolved", request_id=request_id),
            )
        if not confirm_payload and not pending_action and not checkpoint_id:
            raise HTTPException(status_code=409, detail=error_detail("no_pending_checkpoint", request_id=request_id))
        # Legacy/test graphs may not expose explicit checkpoint payload fields; allow
        # confirm updates to proceed and let graph/update layer decide applicability.
        if confirm_payload:
            conversation_id = str(confirm_payload.get("conversation_id") or "")
            if conversation_id != body.chat_id:
                raise HTTPException(
                    status_code=403,
                    detail=error_detail("checkpoint_conversation_mismatch", request_id=request_id),
                )
        if required_sub and required_sub != scoped_user_id:
            raise HTTPException(status_code=403, detail=error_detail("forbidden", request_id=request_id))
        if body.checkpoint_id and checkpoint_id and body.checkpoint_id != checkpoint_id:
            raise HTTPException(status_code=409, detail=error_detail("checkpoint_mismatch", request_id=request_id))

        current_action = str((confirm_payload.get("action") if isinstance(confirm_payload, dict) else None) or pending_action or "").strip()
        current_release_blockers = _release_blockers_from_state(state_values)
        if body.decision == "approve" and current_release_blockers:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "release_blocked",
                    request_id=request_id,
                    blockers=current_release_blockers,
                ),
            )
        if body.decision == "approve" and _confirm_action_requires_rfq_ready(current_action):
            rfq_admissibility = _rfq_admissibility_value(state_values)
            if not rfq_contract_is_ready(rfq_admissibility):
                raise HTTPException(
                    status_code=409,
                    detail=error_detail(
                        "rfq_not_admissible",
                        request_id=request_id,
                        status=rfq_admissibility.get("status"),
                        reason=rfq_admissibility.get("reason"),
                    ),
                )

        edits_payload = body.edits.model_dump(exclude_none=True) if body.edits else {}
        edit_parameters = {}
        if edits_payload.get("working_profile") or edits_payload.get("parameters"):
            edit_parameters = sanitize_v2_parameter_patch(
                edits_payload.get("working_profile") or edits_payload.get("parameters") or {}
            )
        edits = {
            "working_profile": edit_parameters,
            "instructions": (edits_payload.get("instructions") or "").strip() or None,
        }

        assert_node_exists(
            graph,
            CONFIRM_GO_AS_NODE,
            request_id=request_id,
            status_code=500,
            code="server_misconfigured",
        )
        await graph.aupdate_state(
            config,
            {
                "system": {
                    "confirm_decision": body.decision,
                    "confirm_edits": edits,
                },
                # Backward-compatible mirrors for legacy test doubles/graphs.
                "confirm_decision": body.decision,
                "confirm_edits": edits,
            },
            as_node=CONFIRM_GO_AS_NODE,
        )

        result = await graph.ainvoke({}, config=config)
        state = result if isinstance(result, SealAIState) else SealAIState.model_validate(result or {})
        response = {
            "ok": True,
            "decision": body.decision,
        }
        response.update(_build_release_response(state, thread_id=body.chat_id))
        return response
    except HTTPException:
        raise
    except InvalidUpdateError as exc:
        raise HTTPException(
            status_code=400,
            detail=error_detail("invalid_as_node", request_id=request_id, message=str(exc)),
        ) from exc
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "langgraph_v2_confirm_go_error",
            extra={"request_id": request_id, "chat_id": body.chat_id, "user": user.user_id},
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc
    finally:
        await _release_thread_lock(body.chat_id)


@router.post("/chat/v2/threads/{thread_id}/runs/resume")
async def resume_run(
    thread_id: str,
    body: HITLResumeRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    scoped_user_id = canonical_user_id(user)
    thread_id = _scope_thread_id_for_user(user_id=scoped_user_id, thread_id=thread_id)
    legacy_user_id = user.sub if user.sub and user.sub != scoped_user_id else None

    # Concurrency check: Ensure only one active run per thread_id.
    locked = await _claim_thread_lock(thread_id, ttl=300)
    if not locked:
        raise HTTPException(
            status_code=409,
            detail=error_detail(
                "thread_locked",
                request_id=request_id,
                message="Another request is already processing for this thread. Please wait.",
            ),
        )

    try:
        thread_id = (thread_id or "").strip()
        if not thread_id:
            raise HTTPException(status_code=400, detail=error_detail("missing_thread_id", request_id=request_id))
        if not (body.checkpoint_id or "").strip():
            raise HTTPException(status_code=400, detail=error_detail("missing_checkpoint_id", request_id=request_id))

        graph, config = await _build_graph_config(
            thread_id=thread_id,
            user_id=scoped_user_id,
            username=user.username,
            auth_scopes=user.scopes,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        snapshot = await graph.aget_state(config)
        state_values = _state_values_to_dict(snapshot.values)
        state_checkpoint_id = _system_value(state_values, "confirm_checkpoint_id") if isinstance(state_values, dict) else None
        if (
            isinstance(state_checkpoint_id, str)
            and state_checkpoint_id.strip()
            and state_checkpoint_id.strip() != body.checkpoint_id.strip()
        ):
            raise HTTPException(status_code=409, detail=error_detail("checkpoint_mismatch", request_id=request_id))

        # Resume contract payload passed to graph runtime (LangGraph resume protocol).
        resume_payload = {
            "checkpoint_id": body.checkpoint_id,
            "action": body.command.action,
            "feedback": body.command.feedback,
            "override_params": body.command.override_params or {},
        }
        result = await graph.ainvoke(Command(resume=resume_payload), config=config)
        state = result if isinstance(result, SealAIState) else SealAIState.model_validate(result or {})
        response = {
            "ok": True,
            "thread_id": thread_id,
            "checkpoint_id": body.checkpoint_id,
            "action": body.command.action,
        }
        response.update(_build_release_response(state, thread_id=thread_id))
        return response
    except HTTPException:
        raise
    except InvalidUpdateError as exc:
        raise HTTPException(
            status_code=400,
            detail=error_detail("invalid_resume_command", request_id=request_id, message=str(exc)),
        ) from exc
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "langgraph_v2_resume_error",
            extra={
                "request_id": request_id,
                "thread_id": thread_id,
                "user": user.user_id,
            },
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc
    finally:
        await _release_thread_lock(thread_id)


@router.post("/parameters/patch")
async def patch_parameters(
    body: ParametersPatchRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    scoped_user_id = canonical_user_id(user)
    legacy_user_id = user.sub if user.sub and user.sub != scoped_user_id else None
    chat_id = _scope_thread_id_for_user(user_id=scoped_user_id, thread_id=body.chat_id)
    body.chat_id = chat_id
    patch: Dict[str, Any] = {}
    try:
        if PARAM_SYNC_DEBUG:
            logger.info(
                "langgraph_v2_parameters_patch_payload",
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "parameters": body.parameters,
                },
            )
        if not chat_id:
            raise HTTPException(status_code=400, detail=error_detail("missing_chat_id", request_id=request_id))
        patch = sanitize_v2_parameter_patch(body.parameters)
        if not patch:
            raise HTTPException(status_code=400, detail=error_detail("missing_parameters", request_id=request_id))

        graph, config = await _build_graph_config(
            thread_id=chat_id,
            user_id=scoped_user_id,
            username=user.username,
            auth_scopes=user.scopes,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        assert_node_exists(graph, PARAMETERS_PATCH_AS_NODE, request_id=request_id)
        snapshot = await graph.aget_state(config)
        state_values = _state_values_to_dict(snapshot.values)
        existing_params = _engineering_profile_payload(state_values) if isinstance(state_values, dict) else {}
        existing_provenance = {}
        existing_extracted = {}
        existing_extracted_provenance = {}
        existing_versions: Dict[str, int] = {}
        existing_updated_at: Dict[str, float] = {}
        if isinstance(state_values, dict):
            existing_provenance = _reasoning_value(state_values, "parameter_provenance") or {}
            existing_extracted = _working_profile_value(state_values, "extracted_params") or {}
            existing_extracted_provenance = _reasoning_value(state_values, "extracted_parameter_provenance") or {}
            existing_versions = _reasoning_value(state_values, "parameter_versions") or {}
            existing_updated_at = _reasoning_value(state_values, "parameter_updated_at") or {}
        (
            merged,
            merged_provenance,
            merged_versions,
            merged_updated_at,
            remaining_extracted,
            remaining_extracted_provenance,
            applied_fields,
            rejected_fields,
        ) = promote_parameter_patch_to_asserted(
            existing_params,
            patch,
            existing_provenance,
            source="user",
            existing_extracted=existing_extracted,
            extracted_provenance=existing_extracted_provenance,
            parameter_versions=existing_versions,
            parameter_updated_at=existing_updated_at,
            base_versions=body.base_versions,
        )
        cycle_update = build_assertion_cycle_update(state_values, applied_fields=applied_fields)

        if PARAM_SYNC_DEBUG:
            patch_keys = sorted(patch.keys())
            types = {key: type(patch.get(key)).__name__ for key in patch_keys}
            before = {}
            after = {}
            if isinstance(existing_params, dict):
                before = {key: existing_params.get(key) for key in patch_keys}
            if isinstance(merged, dict):
                after = {key: merged.get(key) for key in patch_keys}
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            logger.info(
                "langgraph_v2_parameters_patch_debug",
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "user": _short_user_id(user.user_id),
                    "patch_keys": patch_keys,
                    "patch_types": types,
                    "patch_before": before,
                    "patch_after": after,
                    "merged_keys": sorted(merged.keys()) if isinstance(merged, dict) else [],
                    "checkpoint_thread_id": configurable.get("thread_id"),
                    "checkpoint_ns": configurable.get("checkpoint_ns"),
                },
            )

        updates = {
            "working_profile": {
                "engineering_profile": merged,
                "extracted_params": remaining_extracted,
            },
            "reasoning": {
                "parameter_provenance": merged_provenance,
                "extracted_parameter_provenance": remaining_extracted_provenance,
                "parameter_versions": merged_versions,
                "parameter_updated_at": merged_updated_at,
            },
        }
        if cycle_update:
            updates = _merge_state_like(updates, cycle_update) or updates

        await graph.aupdate_state(
            config,
            updates,
            # LangGraph requires `as_node` to be an existing node in the compiled graph.
            # Parameter patches are UI-driven and should not advance the graph; we attach
            # the update to a stable, always-present node.
            as_node=PARAMETERS_PATCH_AS_NODE,
        )
        response_fields = sorted(patch.keys())
        response_payload = {
            "ok": True,
            "chat_id": body.chat_id,
            "applied_fields": applied_fields,
            "rejected_fields": rejected_fields,
            "versions": {field: merged_versions.get(field, 0) for field in response_fields},
            "updated_at": {field: merged_updated_at.get(field) for field in response_fields},
        }
        ack_payload = {
            "chat_id": body.chat_id,
            "patch": patch,
            "applied_fields": applied_fields,
            "rejected_fields": rejected_fields,
            "versions": response_payload["versions"],
            "updated_at": response_payload["updated_at"],
            "source": "patch_endpoint",
            "request_id": request_id,
        }
        await sse_broadcast.broadcast(
            user_id=scoped_user_id,
            chat_id=chat_id,
            event="parameter_patch_ack",
            data=ack_payload,
        )
        return response_payload
    except HTTPException:
        raise
    except ValueError as exc:
        if PARAM_SYNC_DEBUG:
            logger.warning(
                "langgraph_v2_parameters_patch_invalid_payload",
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "user": _short_user_id(user.user_id),
                    "error": str(exc),
                    "patch_keys": sorted(patch.keys()) if isinstance(patch, dict) else [],
                },
            )
        raise HTTPException(
            status_code=400,
            detail=error_detail("invalid_parameters", request_id=request_id, message=str(exc)),
        ) from exc
    except InvalidUpdateError as exc:
        if PARAM_SYNC_DEBUG:
            logger.warning(
                "langgraph_v2_parameters_patch_invalid_update",
                exc_info=exc,
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "patch_keys": sorted(patch.keys()) if isinstance(patch, dict) else [],
                },
            )
        raise HTTPException(
            status_code=400,
            detail=error_detail("invalid_as_node", request_id=request_id, message=str(exc)),
        ) from exc
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "langgraph_v2_parameters_patch_error",
            extra={
                "request_id": request_id,
                "chat_id": chat_id,
                "user": user.user_id,
                "patch_keys": sorted(patch.keys()),
            },
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc


__all__ = ["LangGraphV2Request"]
