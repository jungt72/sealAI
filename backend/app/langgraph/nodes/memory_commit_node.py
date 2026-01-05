from __future__ import annotations

from typing import Any, Dict, List

from app.langgraph.state import SealAIState


class _Settings:
    ltm_enable = True


settings = _Settings()


class _MemoryCore:
    def commit_summary(self, *_args, **_kwargs):
        return None


memory_core = _MemoryCore()


async def _store_ltm_entry(_user_id: str, _key: str, _value: str) -> int:
    return 0


async def memory_commit_node(state: SealAIState) -> Dict[str, Any]:
    if not getattr(settings, "ltm_enable", False):
        return {}

    meta = state.get("meta") or {}
    user_id = str(meta.get("user_id") or "").strip()
    chat_id = str(meta.get("thread_id") or "").strip()
    if not user_id:
        return {}

    summary_parts: List[str] = []
    if state.get("rapport_summary"):
        summary_parts.append(str(state.get("rapport_summary")))
    if state.get("discovery_summary"):
        summary_parts.append(str(state.get("discovery_summary")))
    slots = state.get("slots") or {}
    if slots.get("final_recommendation"):
        summary_parts.append(str(slots.get("final_recommendation")))
    if slots.get("requirements"):
        summary_parts.append(str(slots.get("requirements")))
    if slots.get("candidate_answer"):
        summary_parts.append(str(slots.get("candidate_answer")))

    summary_text = "\n".join(summary_parts).strip()
    if not summary_text:
        summary_text = "Summary not available."

    payload = {
        "summary": summary_text,
        "slots": slots,
        "meta": meta,
    }
    memory_core.commit_summary(user_id, chat_id, payload)

    entry_id = await _store_ltm_entry(user_id, "summary", summary_text)

    return {
        "long_term_memory_refs": [{"storage": "qdrant", "id": str(entry_id), "summary": summary_text}],
    }


__all__ = ["memory_commit_node", "_store_ltm_entry", "memory_core", "settings"]
