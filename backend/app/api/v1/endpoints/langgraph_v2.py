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
from app.langgraph_v2.utils.rfq_admissibility import rfq_contract_is_ready
from app.langgraph_v2.utils.parameter_patch import (
    ParametersPatchRequest,
    apply_parameter_patch_to_state_layers,
    sanitize_v2_parameter_patch,
    stage_extracted_parameter_patch,
)
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
DEFAULT_GRAPH_RECURSION_LIMIT = 25
_STREAM_NODE_BLOCKLIST = frozenset()


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
    return scope_v2_thread_id(thread_id=thread_id, user_id=user_id)


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


# _run_graph_to_state was removed from production code (never called by any endpoint).
# Tests that reference it must import from:
#   app.api.tests.helpers.langgraph_v2_test_stream_helpers


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

        as_node_candidate = str(_reasoning_value(state_values, "last_node") or CONFIRM_GO_AS_NODE).strip()
        as_node = pick_existing_node(graph, as_node_candidate, fallback=CONFIRM_GO_AS_NODE)

        assert_node_exists(
            graph,
            as_node,
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
            as_node=as_node,
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
        existing_normalized = {}
        existing_normalized_provenance = {}
        existing_identity = {}
        existing_observed_inputs = {}
        existing_versions: Dict[str, int] = {}
        existing_updated_at: Dict[str, float] = {}
        if isinstance(state_values, dict):
            existing_provenance = _reasoning_value(state_values, "parameter_provenance") or {}
            existing_normalized = (
                _working_profile_value(state_values, "normalized_profile")
                or _working_profile_value(state_values, "extracted_params")
                or {}
            )
            existing_normalized_provenance = _reasoning_value(state_values, "extracted_parameter_provenance") or {}
            existing_identity = _reasoning_value(state_values, "extracted_parameter_identity") or {}
            existing_observed_inputs = _reasoning_value(state_values, "observed_inputs") or {}
            existing_versions = _reasoning_value(state_values, "parameter_versions") or {}
            existing_updated_at = _reasoning_value(state_values, "parameter_updated_at") or {}
        (
            merged,
            merged_provenance,
            merged_versions,
            merged_updated_at,
            merged_normalized,
            merged_normalized_provenance,
            merged_identity,
            merged_observed_inputs,
            staged_fields,
            asserted_fields,
            rejected_fields,
        ) = apply_parameter_patch_to_state_layers(
            existing_params,
            existing_normalized,
            patch,
            existing_provenance,
            existing_normalized_provenance,
            existing_identity,
            existing_observed_inputs,
            source="user",
            parameter_versions=existing_versions,
            parameter_updated_at=existing_updated_at,
            base_versions=body.base_versions,
        )
        cycle_update = build_assertion_cycle_update(state_values, applied_fields=asserted_fields)

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
                "normalized_profile": merged_normalized,
                "engineering_profile": merged,
                "extracted_params": merged_normalized,
            },
            "reasoning": {
                "parameter_provenance": merged_provenance,
                "extracted_parameter_provenance": merged_normalized_provenance,
                "extracted_parameter_identity": merged_identity,
                "observed_inputs": merged_observed_inputs,
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
            "applied_fields": staged_fields,
            "asserted_fields": asserted_fields,
            "rejected_fields": rejected_fields,
            "versions": {field: merged_versions.get(field, 0) for field in response_fields},
            "updated_at": {field: merged_updated_at.get(field) for field in response_fields},
        }
        ack_payload = {
            "chat_id": body.chat_id,
            "patch": patch,
            "applied_fields": staged_fields,
            "asserted_fields": asserted_fields,
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
