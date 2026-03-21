from __future__ import annotations

from typing import Any, Dict

from langgraph.store.base import BaseStore

from app._legacy_v2.state import SealAIState, WorkingMemory


def _merge_user_context(
    existing: Dict[str, Any] | None,
    loaded: Dict[str, Any] | None,
) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    if isinstance(loaded, dict):
        merged.update(loaded)
    return merged


def _resolve_user_id(state: SealAIState) -> str:
    conversation = state.conversation
    if isinstance(conversation.user_id, str) and conversation.user_id.strip():
        return conversation.user_id.strip()
    context = conversation.user_context if isinstance(conversation.user_context, dict) else {}
    metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
    for candidate in (
        context.get("user_id"),
        metadata.get("user_id"),
        metadata.get("sub"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return "default_user"


def _normalize_profile_payload(item: Any) -> Dict[str, Any]:
    if item is None:
        return {}
    value = getattr(item, "value", item)
    if isinstance(value, dict):
        return dict(value)
    return {}


async def _load_technical_context(store: BaseStore, namespace: tuple[str, str]) -> Dict[str, Any]:
    aget = getattr(store, "aget", None)
    if callable(aget):
        return _normalize_profile_payload(await aget(namespace, "technical_context"))
    get = getattr(store, "get", None)
    if callable(get):
        return _normalize_profile_payload(get(namespace, "technical_context"))
    return {}


async def profile_loader_node(state: SealAIState, store: BaseStore) -> Dict[str, Any]:
    """Load cross-session user profile from BaseStore and project into state."""
    user_id = _resolve_user_id(state)
    namespace = ("user_prefs", user_id)
    existing_context = (
        state.conversation.user_context
        if isinstance(state.conversation.user_context, dict)
        else {}
    )

    try:
        loaded_profile = await _load_technical_context(store, namespace)
    except Exception:
        loaded_profile = {}

    merged_context = _merge_user_context(dict(existing_context), loaded_profile)

    wm = state.reasoning.working_memory or WorkingMemory()
    design_notes = dict(wm.design_notes or {})
    design_notes["user_profile"] = loaded_profile
    if isinstance(loaded_profile.get("domains"), list):
        domains = [str(item).strip() for item in loaded_profile.get("domains", []) if str(item).strip()]
        if domains:
            design_notes["user_domains"] = domains
    preferred_norms = loaded_profile.get("preferred_standards")
    if preferred_norms is not None:
        design_notes["preferred_standards"] = preferred_norms
    wm = wm.model_copy(update={"design_notes": design_notes})

    return {
        "conversation": {"user_context": merged_context},
        "reasoning": {
            "working_memory": wm,
            "last_node": "profile_loader_node",
        },
    }
