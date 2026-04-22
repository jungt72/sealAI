import logging
import os
from typing import Dict, Literal, Optional, Any

from fastapi import Depends
from app.agent.state.agent_state import AgentState
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user

_log = logging.getLogger(__name__)

SESSION_STORE: Dict[str, AgentState] = {}

# --- Legacy Constants (Inlined from legacy_graph) ---
_GRAPH_MODEL_ID = "gpt-4o-mini"
VISIBLE_REPLY_PROMPT_VERSION = "visible_reply_prompt_v2"
VISIBLE_REPLY_PROMPT_HASH = "12c09ed4061d"  # sha256 of VISIBLE_REPLY_SYSTEM_PROMPT[:12]
# ----------------------------------------------------

def _case_cache_key(tenant_id: str, owner_id: str, case_id: str) -> str:
    return f"{tenant_id}:{owner_id}:{case_id}"

def _canonical_scope(current_user: RequestUser, *, case_id: str) -> tuple[str, str, str]:
    owner_id = canonical_user_id(current_user)
    tenant_id = current_user.tenant_id or "default"
    return tenant_id, owner_id, _case_cache_key(tenant_id, owner_id, case_id)

def _canonical_case_token(state: AgentState) -> dict[str, Any]:
    case_meta = dict(((state.get("case_state") or {}).get("case_meta") or {}))
    return {
        "case_id": case_meta.get("case_id"),
        "state_revision": case_meta.get("state_revision"),
        "analysis_cycle_id": case_meta.get("analysis_cycle_id"),
        "phase": case_meta.get("phase"),
        "runtime_path": case_meta.get("runtime_path"),
        "binding_level": case_meta.get("binding_level"),
        "lifecycle_status": case_meta.get("lifecycle_status"),
    }

def _canonical_state_revision(state: AgentState) -> int:
    token = _canonical_case_token(state)
    return int(token.get("state_revision") or 0)

def _cache_loaded_state(
    *,
    tenant_id: str,
    owner_id: str,
    case_id: str,
    state: AgentState,
) -> None:
    key = _case_cache_key(tenant_id, owner_id, case_id)
    SESSION_STORE[key] = state

def _resolve_payload_binding_level(default_binding_level: str, *, case_state: Optional[Dict[str, Any]]) -> str:
    if not case_state:
        return default_binding_level
    case_meta = case_state.get("case_meta") or {}
    return str(case_meta.get("binding_level") or default_binding_level)

def _runtime_mode_for_pre_gate(classification: str) -> Literal["CONVERSATION", "EXPLORATION", "GOVERNED"]:
    if classification == "KNOWLEDGE_QUERY":
        return "EXPLORATION"
    if classification in {"GREETING", "META_QUESTION", "BLOCKED"}:
        return "CONVERSATION"
    return "GOVERNED"

def _lg_trace_enabled() -> bool:
    return os.getenv("SEALAI_LG_TRACE") == "1"

def _is_light_runtime_mode(runtime_mode: Optional[str]) -> bool:
    return runtime_mode in {"CONVERSATION", "EXPLORATION"}

_RESIDUAL_LEGACY_RUNTIME_LABEL = "residual_legacy_compat_only"
_LIGHT_HISTORY_MESSAGES = 20
