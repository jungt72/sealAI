"""Redis helpers for per-tenant conversation metadata with TTL-backed cleanup.

Data model:
- Sorted set `chat:conversations:{tenant_id}:{owner_id}` keeps conversation IDs ordered by `updated_at`.
- Hash `chat:conversation:{tenant_id}:{owner_id}:{conversation_id}` stores id/title/updated_at/last_preview
  and expires (default 30 days) so stale entries drop off before the sorted set is cleaned lazily.
"""

from dataclasses import dataclass
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List

from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_CONVERSATIONS_SET_PREFIX = "chat:conversations"
_CONVERSATION_HASH_PREFIX = "chat:conversation"
_TITLE_FLAG_FIELD = "is_title_user_defined"
_PREVIEW_FIELD = "last_preview"
_DEFAULT_CONVERSATION_TITLE = "Neue Unterhaltung"
_TITLE_CHAR_LIMIT = 80
_PREVIEW_CHAR_LIMIT = 160
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


def _sorted_set_key(tenant_id: str, owner_id: str) -> str:
    return f"{_CONVERSATIONS_SET_PREFIX}:{tenant_id}:{owner_id}"


def _hash_key(tenant_id: str, owner_id: str, conversation_id: str) -> str:
    return f"{_CONVERSATION_HASH_PREFIX}:{tenant_id}:{owner_id}:{conversation_id}"


def _legacy_sorted_set_key(owner_id: str) -> str:
    return f"{_CONVERSATIONS_SET_PREFIX}:{owner_id}"


def _legacy_hash_key(owner_id: str, conversation_id: str) -> str:
    return f"{_CONVERSATION_HASH_PREFIX}:{owner_id}:{conversation_id}"


def _ttl_seconds() -> int:
    days = settings.chat_history_ttl_days or 30
    return max(1, days) * 86400


@dataclass
class ConversationMeta:
    id: str
    owner_id: str
    title: str | None
    updated_at: datetime
    last_preview: str | None


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


def _normalize_preview(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(value.splitlines())
    cleaned = text.strip()
    if not cleaned:
        return None
    if len(cleaned) <= _PREVIEW_CHAR_LIMIT:
        return cleaned
    truncated = cleaned[:_PREVIEW_CHAR_LIMIT]
    trimmed = truncated.rstrip()
    last_space = trimmed.rfind(" ")
    if last_space > 0:
        trimmed = trimmed[:last_space]
    return trimmed.rstrip(".,;:!?")


def _cleanup_excess_conversations(r: Redis, tenant_id: str, owner_id: str, key_set: str) -> None:
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
            delete_conversation(tenant_id, owner_id, conversation_id, reason="limit")
    except Exception as exc:
        logger.warning(
            "Failed to enforce conversation limit: %s",
            exc,
            extra={"tenant_id": tenant_id, "owner_id": owner_id, "conversation_limit": limit},
        )


def upsert_conversation(
    tenant_id: str,
    owner_id: str,
    conversation_id: str,
    *,
    title: str | None = None,
    first_user_message: str | None = None,
    last_preview: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    """Create or refresh metadata for a conversation and refresh its TTL."""
    if not tenant_id or not owner_id or not conversation_id:
        return
    updated = (updated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        r = _redis_client()
        key_set = _sorted_set_key(tenant_id, owner_id)
        key_hash = _hash_key(tenant_id, owner_id, conversation_id)
        existing = r.hgetall(key_hash)
        is_new = not bool(existing)
        current_title = existing.get("title")
        current_flag = existing.get(_TITLE_FLAG_FIELD, "0")
        current_preview = existing.get(_PREVIEW_FIELD)
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
        preview_value = (
            _normalize_preview(last_preview)
            or _normalize_preview(first_user_message)
            or _normalize_preview(current_preview)
        )
        mapping = {
            "id": conversation_id,
            "user_id": owner_id,
            "tenant_id": tenant_id,
            "updated_at": updated.isoformat(),
            "title": final_title,
            _TITLE_FLAG_FIELD: final_flag,
            _PREVIEW_FIELD: preview_value or "",
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
                    "tenant_id": tenant_id,
                    "owner_id": owner_id,
                    "conversation_id": conversation_id,
                },
            )
        _cleanup_excess_conversations(r, tenant_id, owner_id, key_set)
    except Exception as exc:
        logger.warning(
            "Failed to upsert conversation metadata: %s",
            exc,
            extra={"tenant_id": tenant_id, "owner_id": owner_id, "conversation_id": conversation_id},
        )


def _migrate_legacy_conversations(r: Redis, tenant_id: str, owner_id: str, target_set_key: str) -> None:
    legacy_set_key = _legacy_sorted_set_key(owner_id)
    members = r.zrevrange(legacy_set_key, 0, -1)
    if not members:
        return
    pipe = r.pipeline()
    for conv_id in members:
        legacy_hash = _legacy_hash_key(owner_id, conv_id)
        data = r.hgetall(legacy_hash)
        if not data:
            continue
        key_hash = _hash_key(tenant_id, owner_id, conv_id)
        if r.hgetall(key_hash):
            continue
        data = dict(data)
        data["user_id"] = owner_id
        data["tenant_id"] = tenant_id
        pipe.hset(key_hash, mapping=data)
        pipe.expire(key_hash, _ttl_seconds())
        score = r.zscore(legacy_set_key, conv_id)
        if score is None:
            updated_raw = data.get("updated_at")
            try:
                score = datetime.fromisoformat(updated_raw).timestamp() if updated_raw else None
            except Exception:
                score = None
        pipe.zadd(target_set_key, {conv_id: score or datetime.now(timezone.utc).timestamp()})
    pipe.execute()


def _collect_for_owner(
    tenant_id: str,
    owner_id: str,
    *,
    allow_legacy_migration: bool = True,
) -> List[ConversationMeta]:
    result: List[ConversationMeta] = []
    if not tenant_id or not owner_id:
        return result
    try:
        r = _redis_client()
        set_key = _sorted_set_key(tenant_id, owner_id)
        if allow_legacy_migration and r.zcard(set_key) == 0:
            _migrate_legacy_conversations(r, tenant_id, owner_id, set_key)
        members = r.zrevrange(set_key, 0, -1)
        stale: List[str] = []
        for conv_id in members:
            key_hash = _hash_key(tenant_id, owner_id, conv_id)
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
                    owner_id=owner_id,
                    title=data.get("title"),
                    updated_at=updated,
                    last_preview=data.get(_PREVIEW_FIELD) or None,
                )
            )
        if stale:
            r.zrem(set_key, *stale)
    except Exception as exc:
        logger.warning(
            "Failed to collect conversation metadata: %s",
            exc,
            extra={"tenant_id": tenant_id, "owner_id": owner_id},
        )
    return result


def list_conversations(
    tenant_id: str,
    owner_id: str,
    *,
    legacy_owner_id: str | None = None,
    allow_legacy_migration: bool = True,
) -> List[ConversationMeta]:
    """Return all known conversations for the canonical owner, optionally merging legacy IDs."""
    merged: Dict[str, ConversationMeta] = {}
    for candidate in (owner_id, legacy_owner_id):
        if not candidate:
            continue
        for entry in _collect_for_owner(
            tenant_id,
            candidate,
            allow_legacy_migration=allow_legacy_migration,
        ):
            existing = merged.get(entry.id)
            if not existing or entry.updated_at > existing.updated_at:
                merged[entry.id] = entry
    return sorted(merged.values(), key=lambda entry: entry.updated_at, reverse=True)


def delete_conversation(
    tenant_id: str,
    owner_id: str,
    conversation_id: str,
    *,
    reason: str = "manual",
) -> None:
    """Remove the hash + sorted-set member for a conversation so it no longer surfaces in the UI."""
    if not tenant_id or not owner_id or not conversation_id:
        return
    try:
        r = _redis_client()
        set_key = _sorted_set_key(tenant_id, owner_id)
        key_hash = _hash_key(tenant_id, owner_id, conversation_id)
        pipe = r.pipeline()
        pipe.delete(key_hash)
        pipe.zrem(set_key, conversation_id)
        pipe.execute()
        logger.info(
            "Deleted conversation metadata",
            extra={
                "tenant_id": tenant_id,
                "owner_id": owner_id,
                "conversation_id": conversation_id,
                "reason": reason,
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to delete conversation metadata: %s",
            exc,
            extra={"tenant_id": tenant_id, "owner_id": owner_id, "conversation_id": conversation_id},
        )
