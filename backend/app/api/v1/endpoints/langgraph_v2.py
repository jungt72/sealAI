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

from app.common.errors import error_detail
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user
from app.services.chat.conversations import upsert_conversation
from app.services.sse_broadcast import sse_broadcast

# Fast-Brain Runtime orchestration — extracted to app.api.v1.fast_brain_runtime
from app.api.v1.fast_brain_runtime import (  # noqa: E402
    PARAMETERS_PATCH_AS_NODE,
    PARAM_SYNC_DEBUG,
    _coerce_fast_brain_state_patch,
    _extract_fast_brain_history,
    _fast_brain_profile_mirrors,
    _fast_brain_sse_stream,
    _get_fast_brain_router,
    _get_graph_state_values_for_stream,
    _normalize_fast_brain_status,
    _sync_fast_brain_checkpoint_state,
)

try:
    from sse_starlette.sse import EventSourceResponse as NativeEventSourceResponse
except Exception:  # pragma: no cover - optional dependency
    NativeEventSourceResponse = None

router = APIRouter()
logger = logging.getLogger(__name__)
SSE_DEBUG = os.getenv("SEALAI_SSE_DEBUG") == "1"
DEDUP_TTL_SEC = int(os.getenv("LANGGRAPH_V2_DEDUP_TTL_SEC", "900"))
SSE_RETRY_MS = int(os.getenv("SEALAI_SSE_RETRY_MS", "3000"))
SSE_HEARTBEAT_SEC = float(os.getenv("SEALAI_SSE_HEARTBEAT_SEC", "10"))
SSE_QUEUE_MAXSIZE = int(os.getenv("SEALAI_SSE_QUEUE_MAXSIZE", "200"))
SSE_SLOW_NOTICE_SEC = float(os.getenv("SEALAI_SSE_SLOW_NOTICE_SEC", "5"))
REQUIRE_PARAM_SNAPSHOT = os.getenv("SEALAI_REQUIRE_PARAM_SNAPSHOT") == "1"
WARN_STALE_PARAM_SNAPSHOT = os.getenv("SEALAI_WARN_STALE_PARAM_SNAPSHOT", "1") == "1"
# Residual compat ingress. Disabled by default so the canonical /api/agent
# runtime remains the productive standard authority.
ENABLE_COMPAT_CHAT = os.getenv("SEALAI_ENABLE_LANGGRAPH_V2_COMPAT_CHAT", "false").lower() == "true"
DEFAULT_GRAPH_RECURSION_LIMIT = 25
_STREAM_NODE_BLOCKLIST = frozenset()


# ---------------------------------------------------------------------------
# Inline stubs for symbols that were in app._legacy_v2 (now deleted).
# ---------------------------------------------------------------------------

class ParametersPatchRequest(BaseModel):
    """Request body for /parameters/patch."""
    model_config = ConfigDict(extra="ignore")
    chat_id: str = Field(default="")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    base_versions: Optional[Dict[str, int]] = None


class ConfirmGoRequest(BaseModel):
    """Request body for /confirm/go (stub — endpoint returns 501)."""
    model_config = ConfigDict(extra="ignore")
    chat_id: str = Field(default="")
    decision: str = Field(default="")
    checkpoint_id: Optional[str] = None
    edits: Optional[Any] = None


class HITLResumeRequest(BaseModel):
    """Request body for /chat/v2/threads/.../runs/resume (stub — endpoint returns 501)."""
    model_config = ConfigDict(extra="ignore")
    chat_id: Optional[str] = None


def sanitize_v2_parameter_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Strip None and empty-string values from a UI parameter patch dict."""
    return {k: v for k, v in (patch or {}).items() if v is not None and v != ""}


def rfq_contract_is_ready(rfq_admissibility: Any) -> bool:
    """Stub: always False when legacy graph is absent."""
    if not isinstance(rfq_admissibility, dict):
        return False
    return rfq_admissibility.get("status") == "ready"


def _lg_trace_enabled() -> bool:
    return os.getenv("SEALAI_LG_TRACE") == "1"


# Shared state-access helpers — definitions live in app.api.v1.utils.state_access
# to avoid duplication with state.py. Pillar-value readers and payload builders
# are centralised there to allow sse_runtime.py to import them without cycles.
from app.api.v1.utils.state_access import (  # noqa: E402
    _pillar_dict,
    _state_values_to_dict,
    _conversation_value,
    _reasoning_value,
    _system_value,
    _working_profile_value,
    _rfq_admissibility_value,
    _looks_like_nested_working_profile_payload,
    _engineering_profile_payload,
    _system_model_payload,
    _candidate_semantics_payload,
    _governance_metadata_payload,
    _flatten_message_content,
    _is_structured_payload_text,
    _resolve_governed_output_text,
    _resolve_final_text,
    _merge_state_like,
    _is_meaningful_live_calc_tile,
    _normalize_live_calc_tile,
    _inject_live_calc_tile,
    _latest_ai_text,
    _extract_final_text_from_patch,
)
from app.api.v1.sse_runtime import (  # noqa: E402
    event_multiplexer,
    _format_sse,
    _format_sse_text,
    _eventsource_event,
    _build_state_update_payload,
    _resolve_stream_node_name,
    _normalize_stream_node_name,
    _human_node_label,
    _extract_chunk_text_from_stream_event,
    _extract_state_update_source,
    _looks_like_state_payload,
    _extract_stream_nodes_from_tags,
    _event_belongs_to_current_run,
    _extract_working_profile_payload,
    _extract_blocker_conflicts,
    _extract_terminal_text_candidate,
)


def _reasoning_working_memory(values: Dict[str, Any]) -> Dict[str, Any]:
    memory = _reasoning_value(values, "working_memory")
    if hasattr(memory, "model_dump"):
        memory = memory.model_dump(exclude_none=True)
    if isinstance(memory, dict):
        return dict(memory)
    return {}


def _short_user_id(user_id: str | None) -> str:
    if not user_id:
        return ""
    return f"{user_id[:8]}..." if len(user_id) > 8 else user_id

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional dependency
    Redis = None

CONFIRM_GO_AS_NODE = "confirm_checkpoint_node"


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
    return f"{user_id}:{thread_id}"


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


def _parse_last_event_id(last_event_id: str | None, *, chat_id: str) -> int | None:
    return sse_broadcast.parse_last_event_id(chat_id, last_event_id)


def _get_dict_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _is_allowed_stream_source(token: Any, *, stream_node: str | None, state: Any = None) -> bool:
    is_rfq = False
    if state:
        sv = _state_values_to_dict(state)
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


def _is_message_chunk(token: BaseMessage) -> bool:
    if isinstance(token, AIMessageChunk):
        return True
    return token.__class__.__name__.endswith("Chunk")


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


# _event_stream_v2 was removed from production code (never called by any endpoint).
# Tests that reference it must import from:
#   app.api.tests.helpers.langgraph_v2_test_stream_helpers


def _extract_agent_sse_payload(frame: Any) -> Dict[str, Any] | None:
    text = frame.decode("utf-8") if isinstance(frame, (bytes, bytearray)) else str(frame)
    payload_line = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("data: "):
            payload_line = line.removeprefix("data: ").strip()
            break
    if not payload_line or payload_line == "[DONE]":
        return None
    try:
        payload = json.loads(payload_line)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _legacy_state_update_from_canonical_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    case_state_out = dict(payload.get("case_state") or {})
    sealing_state_out = dict(payload.get("sealing_state") or {})
    governance_state_out = dict(case_state_out.get("governance_state") or {})
    rfq_state_out = dict(case_state_out.get("rfq_state") or {})
    case_meta_out = dict(case_state_out.get("case_meta") or {})
    governance_out = dict(sealing_state_out.get("governance") or {})
    cycle_out = dict(sealing_state_out.get("cycle") or {})

    release_status = (
        governance_state_out.get("release_status")
        or governance_out.get("release_status")
    )
    rfq_admissibility = (
        rfq_state_out.get("rfq_admissibility")
        or governance_state_out.get("rfq_admissibility")
        or governance_out.get("rfq_admissibility")
    )
    state_revision = (
        case_meta_out.get("state_revision")
        if case_meta_out.get("state_revision") is not None
        else cycle_out.get("state_revision")
    )
    conflicts = (
        governance_state_out.get("conflicts")
        or governance_out.get("conflicts")
        or []
    )

    su_payload: Dict[str, Any] = {
        "type": "state_update",
        "streaming_complete": True,
    }
    working_profile_out = payload.get("working_profile") or {}
    if working_profile_out:
        su_payload["working_profile"] = working_profile_out
    if any(
        value is not None
        for value in (release_status, rfq_admissibility, state_revision)
    ) or conflicts:
        su_payload["governance_metadata"] = {
            "conflicts": conflicts,
            "release_status": release_status,
            "rfq_admissibility": rfq_admissibility,
            "state_revision": state_revision,
        }
        if rfq_admissibility is not None:
            su_payload["rfq_admissibility"] = rfq_admissibility
        su_payload["governed_output_ready"] = release_status == "approved"
    return su_payload


async def _ssot_to_legacy_sse_stream(
    user_input: str,
    chat_id: str,
    *,
    current_user: RequestUser,
    request_id: str | None = None,
) -> AsyncIterator[Any]:
    """Compatibility SSE facade over the canonical /api/agent runtime.

    The v1 endpoint no longer orchestrates LangGraph execution or persistence
    directly. It delegates to the canonical agent SSE generator and only
    translates canonical frames to the legacy SSE event contract.
    """
    from app.agent.api.models import ChatRequest  # type: ignore[import]
    from app.agent.api.router import event_generator as agent_event_generator  # type: ignore[import]

    streamed_text = False

    try:
        async for frame in agent_event_generator(
            ChatRequest(message=user_input, session_id=chat_id),
            current_user=current_user,
        ):
            payload = _extract_agent_sse_payload(frame)
            if not payload:
                continue

            payload_type = str(payload.get("type") or "")
            if payload_type == "text_chunk":
                text = str(payload.get("text") or "").strip()
                if not text:
                    continue
                streamed_text = True
                yield _eventsource_event("text_chunk", {"type": "text_chunk", "text": text})
                yield _eventsource_event("token", {"type": "token", "text": text})
                continue

            if payload_type == "state_update":
                reply_text = str(payload.get("reply") or "").strip()

                if reply_text and not streamed_text:
                    streamed_text = True
                    yield _eventsource_event("text_chunk", {"type": "text_chunk", "text": reply_text})
                    yield _eventsource_event("token", {"type": "token", "text": reply_text})

                su_payload = _legacy_state_update_from_canonical_payload(payload)
                yield _eventsource_event("state_update", su_payload)
                continue

            if payload_type == "error":
                yield _eventsource_event(
                    "error",
                    {"type": "error", "message": "internal_error", "request_id": request_id},
                )
                yield _eventsource_event("turn_complete", {"type": "turn_complete"})
                yield _eventsource_event("done", {"type": "done"})
                return

    except Exception:
        logger.exception("langgraph_v2_compat_stream_failed", extra={"chat_id": chat_id})
        yield _eventsource_event(
            "error",
            {"type": "error", "message": "internal_error", "request_id": request_id},
        )
        yield _eventsource_event("turn_complete", {"type": "turn_complete"})
        yield _eventsource_event("done", {"type": "done"})
        return

    yield _eventsource_event("turn_complete", {"type": "turn_complete"})
    yield _eventsource_event("done", {"type": "done"})


@router.post("/chat/v2")
async def langgraph_chat_v2_endpoint(
    request: LangGraphV2Request,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> StreamingResponse:
    """Residual compatibility SSE ingress.

    This route is no longer a productive default chat entrypoint. It remains
    available only as an explicit opt-in compatibility facade and otherwise
    instructs callers to use the canonical /api/agent runtime.
    """
    if not ENABLE_COMPAT_CHAT:
        request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
        raise HTTPException(
            status_code=410,
            detail=error_detail(
                "compat_chat_disabled",
                request_id=request_id,
                message="Compatibility chat facade disabled. Use /api/agent/chat/stream.",
            ),
        )

    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    logger.warning(
        "langgraph_v2_compat_chat_invoked request_id=%s chat_id=%s user=%s",
        request_id,
        request.chat_id,
        _short_user_id(canonical_user_id(user)),
    )
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

    # SSoT is the sole execution path — release the LangGraph thread lock
    # (the SSoT pipeline manages its own in-memory session concurrency).
    await _release_thread_lock(request.chat_id)
    headers: Dict[str, str] = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    if request_id:
        headers["X-Request-Id"] = request_id
    return EventSourceResponse(
        _ssot_to_legacy_sse_stream(
            request.input,
            request.chat_id,
            current_user=user,
            request_id=request_id,
        ),
        headers=headers,
    )


@router.post("/confirm/go")
async def confirm_go(
    body: ConfirmGoRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="This HITL endpoint is no longer available in the SSoT architecture.",
        ),
    )


@router.post("/chat/v2/threads/{thread_id}/runs/resume")
async def resume_run(
    thread_id: str,
    body: HITLResumeRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="This resume endpoint is no longer available in the SSoT architecture.",
        ),
    )


@router.post("/parameters/patch")
async def patch_parameters(
    body: ParametersPatchRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    raise HTTPException(
        status_code=501,
        detail=error_detail(
            "endpoint_removed",
            request_id=request_id,
            message="Parameter patching is only supported on the canonical /api/agent runtime path.",
        ),
    )


__all__ = ["LangGraphV2Request"]
