from __future__ import annotations

import os
import json
from typing import List, Dict, Literal, TypedDict

from redis import Redis
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AnyMessage


def _redis() -> Redis:
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return Redis.from_url(url, decode_responses=True)

def _conv_key(thread_id: str) -> str:
    # Gleicher Key wie im SSE: chat:stm:{thread_id}:messages
    return f"chat:stm:{thread_id}:messages"


def write_message(*, thread_id: str, role: Literal["user", "assistant", "system"], content: str) -> None:
    if not content:
        return
    r = _redis()
    key = _conv_key(thread_id)
    item = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.lpush(key, item)
    pipe.ltrim(key, 0, int(os.getenv("STM_MAX_ITEMS", "200")) - 1)
    pipe.expire(key, int(os.getenv("STM_TTL_SEC", "604800")))  # 7 Tage
    pipe.execute()


def read_history_raw(thread_id: str, limit: int = 80) -> List[Dict[str, str]]:
    """Rohdaten (älteste -> neueste)."""
    r = _redis()
    key = _conv_key(thread_id)
    items = r.lrange(key, 0, limit - 1) or []
    out: List[Dict[str, str]] = []
    for s in reversed(items):  # Redis speichert neueste zuerst
        try:
            obj = json.loads(s)
            role = (obj.get("role") or "").lower()
            content = obj.get("content") or ""
            if role and content:
                out.append({"role": role, "content": content})
        except Exception:
            continue
    return out


def read_history(thread_id: str, limit: int = 80) -> List[AnyMessage]:
    """LangChain-Messages (älteste -> neueste)."""
    msgs: List[AnyMessage] = []
    for item in read_history_raw(thread_id, limit=limit):
        role = item["role"]
        content = item["content"]
        if role in ("user", "human"):
            msgs.append(HumanMessage(content=content))
        elif role in ("assistant", "ai"):
            msgs.append(AIMessage(content=content))
        elif role == "system":
            msgs.append(SystemMessage(content=content))
    return msgs
