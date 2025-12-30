"""Redis helpers for per-user conversation metadata with TTL-backed cleanup.

Data model:
- Sorted set `chat:conversations:{user_id}` keeps conversation IDs ordered by `updated_at`.
- Hash `chat:conversation:{user_id}:{conversation_id}` stores id/title/updated_at and expires (default 30 days) so stale entries drop out before the sorted set is cleaned lazily.
"""

from dataclasses import dataclass
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_CONVERSATIONS_SET_PREFIX = "chat:conversations"
_CONVERSATION_HASH_PREFIX = "chat:conversation"
_TITLE_FLAG_FIELD = "is_title_user_defined"
_DEFAULT_CONVERSATION_TITLE = "Neue Unterhaltung"
_TITLE_CHAR_LIMIT = 80
_GREETING_PREFIXES = (
    "hallo",
    "hi",
    "hey",
    "guten morgen",
    "guten tag",
    "guten abend",
    "servus",
    "moin",
    "grüß dich",
)


def _redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def _sorted_set_key(user_id: str) -> str:
    return f"{_CONVERSATIONS_SET_PREFIX}:{user_id}"


def _hash_key(user_id: str, conversation_id: str) -> str:
    return f"{_CONVERSATION_HASH_PREFIX}:{user_id}:{conversation_id}"


def _ttl_seconds() -> int:
    days = settings.chat_history_ttl_days or 30
    return max(1, days) * 86400


@dataclass
class ConversationMeta:
    id: str
    user_id: str
    title: str | None
    updated_at: datetime


def derive_conversation_title(first_user_message: str | None) -> str:
    """Try to build a short title from the very first prompt."""
    if not first_user_message:
        return _DEFAULT_CONVERSATION_TITLE
    text = " ".join(first_user_message.splitlines())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return _DEFAULT_CONVERSATION_TITLE
    lowered = text.lower()
    for prefix in _GREETING_PREFIXES:
        if lowered.startswith(prefix):
            remainder = text[len(prefix) :].lstrip(" ,.!?;:-")
            if remainder:
                text = remainder
                lowered = text.lower()
                break
    if len(text) <= _TITLE_CHAR_LIMIT:
        return text.rstrip(".,;:!?")
    truncated = text[:_TITLE_CHAR_LIMIT]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    truncated = truncated.rstrip(".,;:!?")
    return truncated or _DEFAULT_CONVERSATION_TITLE


def _normalize_title(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _cleanup_excess_conversations(r: Redis, user_id: str, key_set: str) -> None:
    limit = settings.chat_max_conversations_per_user
    if not limit or limit <= 0:
        return
    try:
        count = r.zcard(key_set)
        overflow = count - limit
        if overflow <= 0:
            return
        oldest = r.zrange(key_set, 0, overflow - 1)
        for conversation_id in oldest:
            delete_conversation(user_id, conversation_id, reason="limit")
    except Exception as exc:
        logger.warning(
            "Failed to enforce conversation limit: %s",
            exc,
            extra={"user_id": user_id, "conversation_limit": limit},
        )


def upsert_conversation(
    user_id: str,
    conversation_id: str,
    *,
    title: str | None = None,
    first_user_message: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    """Create or refresh metadata for a conversation and refresh its TTL."""
    if not user_id or not conversation_id:
        return
    updated = (updated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        r = _redis_client()
        key_set = _sorted_set_key(user_id)
        key_hash = _hash_key(user_id, conversation_id)
        existing = r.hgetall(key_hash)
        is_new = not bool(existing)
        current_title = existing.get("title")
        current_flag = existing.get(_TITLE_FLAG_FIELD, "0")
        candidate_title = _normalize_title(title)
        if candidate_title:
            final_title = candidate_title
            final_flag = "1"
        elif current_title:
            final_title = current_title
            final_flag = "1" if current_flag == "1" else "0"
        else:
            final_title = derive_conversation_title(first_user_message)
            final_flag = "0"
        mapping = {
            "id": conversation_id,
            "user_id": user_id,
            "updated_at": updated.isoformat(),
            "title": final_title,
            _TITLE_FLAG_FIELD: final_flag,
        }
        pipe = r.pipeline()
        pipe.hset(key_hash, mapping=mapping)
        pipe.expire(key_hash, _ttl_seconds())
        pipe.zadd(key_set, {conversation_id: updated.timestamp()})
        pipe.execute()
        if is_new:
            logger.info(
                "Created conversation metadata",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                },
            )
        _cleanup_excess_conversations(r, user_id, key_set)
    except Exception as exc:
        logger.warning(
            "Failed to upsert conversation metadata: %s",
            exc,
            extra={"user_id": user_id, "conversation_id": conversation_id},
        )


def list_conversations(user_id: str) -> List[ConversationMeta]:
    """Return all known conversations for a user, removing stale sorted-set entries."""
    if not user_id:
        return []
    try:
        r = _redis_client()
        set_key = _sorted_set_key(user_id)
        members = r.zrevrange(set_key, 0, -1)
        stale: List[str] = []
        result: List[ConversationMeta] = []
        for conv_id in members:
            key_hash = _hash_key(user_id, conv_id)
            data = r.hgetall(key_hash)
            if not data:
                stale.append(conv_id)
                continue
            updated_raw = data.get("updated_at")
            try:
                updated = (
                    datetime.fromisoformat(updated_raw)
                    if updated_raw
                    else datetime.now(timezone.utc)
                )
            except ValueError:
                updated = datetime.now(timezone.utc)
            result.append(
                ConversationMeta(
                    id=data.get("id") or conv_id,
                    user_id=data.get("user_id") or user_id,
                    title=data.get("title"),
                    updated_at=updated,
                )
            )
        if stale:
            r.zrem(set_key, *stale)
        return result
    except Exception as exc:
        logger.warning(
            "Failed to list conversation metadata: %s",
            exc,
            extra={"user_id": user_id},
        )
        return []


def delete_conversation(user_id: str, conversation_id: str, *, reason: str = "manual") -> None:
    """Remove the hash + sorted-set member for a conversation so it no longer surfaces in the UI."""
    if not user_id or not conversation_id:
        return
    try:
        r = _redis_client()
        set_key = _sorted_set_key(user_id)
        key_hash = _hash_key(user_id, conversation_id)
        pipe = r.pipeline()
        pipe.delete(key_hash)
        pipe.zrem(set_key, conversation_id)
        pipe.execute()
        logger.info(
            "Deleted conversation metadata",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "reason": reason,
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to delete conversation metadata: %s",
            exc,
            extra={"user_id": user_id, "conversation_id": conversation_id},
        )
