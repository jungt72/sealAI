"""Redis helpers for per-owner conversation metadata with TTL-backed cleanup.

Data model:
- Sorted set `chat:conversations:{owner_id}` keeps conversation IDs ordered by `updated_at`.
- Hash `chat:conversation:{owner_id}:{conversation_id}` stores id/title/updated_at/last_preview
  and expires (default 30 days) so stale entries drop off before the sorted set is cleaned lazily.
"""

from dataclasses import dataclass
from functools import lru_cache
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, TYPE_CHECKING

from redis import Redis

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_CONVERSATIONS_SET_PREFIX = "chat:conversations"
_CONVERSATION_HASH_PREFIX = "chat:conversation"
_CANONICAL_OWNER_PREFIX = "cid"
_TITLE_FLAG_FIELD = "is_title_user_defined"
_PREVIEW_FIELD = "last_preview"
_DEFAULT_CONVERSATION_TITLE = "Neue Unterhaltung"
_TITLE_CHAR_LIMIT = 80
_PREVIEW_CHAR_LIMIT = 160
MAX_CONVERSATIONS_PER_USER = 500
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


@lru_cache(maxsize=1)
def _settings() -> "Settings":
    from app.core.config import Settings
    return Settings()


def _redis_client() -> Redis:
    return Redis.from_url(_settings().redis_url, decode_responses=True)


def _sorted_set_key(owner_id: str) -> str:
    return f"{_CONVERSATIONS_SET_PREFIX}:{owner_id}"


def _hash_key(owner_id: str, conversation_id: str) -> str:
    return f"{_CONVERSATION_HASH_PREFIX}:{owner_id}:{conversation_id}"


def _ttl_seconds() -> int:
    days = _settings().chat_history_ttl_days or 30
    return max(1, days) * 86400


def _conversation_limit() -> int:
    configured = _settings().chat_max_conversations_per_user
    if not configured or configured <= 0:
        return MAX_CONVERSATIONS_PER_USER
    return min(configured, MAX_CONVERSATIONS_PER_USER)


@dataclass
class ConversationMeta:
    id: str
    owner_id: str
    title: str | None
    updated_at: datetime
    last_preview: str | None


@dataclass(frozen=True)
class OwnerIds:
    canonical: str
    legacy: str | None = None


def _canonical_owner_key(owner_id: str) -> str:
    return f"{_CANONICAL_OWNER_PREFIX}:{owner_id}"


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


def _cleanup_excess_conversations(r: Redis, owner_id: str, key_set: str) -> None:
    limit = _conversation_limit()
    if not limit or limit <= 0:
        return
    try:
        # Scores are updated_at timestamps; higher is newer, so trim oldest ranks.
        count = r.zcard(key_set)
        overflow = count - limit
        if overflow > 0:
            r.zremrangebyrank(key_set, 0, overflow - 1)
    except Exception as exc:
        logger.warning(
            "Failed to enforce conversation limit: %s",
            exc,
            extra={"owner_id": owner_id, "conversation_limit": limit},
        )


def upsert_conversation(
    owner_ids: OwnerIds,
    conversation_id: str,
    *,
    title: str | None = None,
    first_user_message: str | None = None,
    last_preview: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    """Create or refresh metadata for a conversation and refresh its TTL."""
    canonical_id = owner_ids.canonical
    legacy_id = owner_ids.legacy if owner_ids.legacy and owner_ids.legacy != canonical_id else None
    if not canonical_id or not conversation_id:
        return
    _upsert_for_owner(
        canonical_id,
        conversation_id,
        owner_key=_canonical_owner_key(canonical_id),
        title=title,
        first_user_message=first_user_message,
        last_preview=last_preview,
        updated_at=updated_at,
    )
    if legacy_id:
        _upsert_for_owner(
            legacy_id,
            conversation_id,
            owner_key=legacy_id,
            title=title,
            first_user_message=first_user_message,
            last_preview=last_preview,
            updated_at=updated_at,
        )


def _upsert_for_owner(
    owner_id: str,
    conversation_id: str,
    *,
    owner_key: str,
    title: str | None = None,
    first_user_message: str | None = None,
    last_preview: str | None = None,
    updated_at: datetime | None = None,
) -> None:
    if not owner_id or not conversation_id:
        return
    updated = (updated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        r = _redis_client()
        set_key = _sorted_set_key(owner_key)
        key_hash = _hash_key(owner_key, conversation_id)
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
            "updated_at": updated.isoformat(),
            "title": final_title,
            _TITLE_FLAG_FIELD: final_flag,
            _PREVIEW_FIELD: preview_value or "",
        }
        pipe = r.pipeline()
        pipe.hset(key_hash, mapping=mapping)
        pipe.expire(key_hash, _ttl_seconds())
        pipe.zadd(set_key, {conversation_id: updated.timestamp()})
        pipe.execute()
        if is_new:
            logger.info(
                "Created conversation metadata",
                extra={
                    "owner_id": owner_id,
                    "conversation_id": conversation_id,
                },
            )
        _cleanup_excess_conversations(r, owner_id, set_key)
    except Exception as exc:
        logger.warning(
            "Failed to upsert conversation metadata: %s",
            exc,
            extra={"owner_id": owner_id, "conversation_id": conversation_id},
        )


def _collect_for_owner(owner_id: str, *, owner_key: str | None = None) -> List[ConversationMeta]:
    result: List[ConversationMeta] = []
    if not owner_id:
        return result
    key_owner = owner_key or owner_id
    try:
        r = _redis_client()
        set_key = _sorted_set_key(key_owner)
        members = r.zrevrange(set_key, 0, -1)
        stale: List[str] = []
        for conv_id in members:
            key_hash = _hash_key(key_owner, conv_id)
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
            extra={"owner_id": owner_id},
        )
    return result


def list_conversations(owner_ids: OwnerIds) -> List[ConversationMeta]:
    """Return all known conversations for the canonical owner, optionally merging legacy IDs."""
    canonical_id = owner_ids.canonical
    legacy_id = owner_ids.legacy if owner_ids.legacy and owner_ids.legacy != canonical_id else None
    if not canonical_id:
        return []
    canonical_entries = _collect_for_owner(
        canonical_id,
        owner_key=_canonical_owner_key(canonical_id),
    )
    if not canonical_entries:
        if not legacy_id:
            return []
        return sorted(
            _collect_for_owner(legacy_id),
            key=lambda entry: entry.updated_at,
            reverse=True,
        )
    if not legacy_id:
        return sorted(
            canonical_entries,
            key=lambda entry: entry.updated_at,
            reverse=True,
        )
    legacy_entries = _collect_for_owner(legacy_id)
    merged: Dict[str, ConversationMeta] = {entry.id: entry for entry in canonical_entries}
    for entry in legacy_entries:
        if entry.id not in merged:
            merged[entry.id] = entry
    return sorted(merged.values(), key=lambda entry: entry.updated_at, reverse=True)


def delete_conversation(owner_ids: OwnerIds, conversation_id: str, *, reason: str = "manual") -> None:
    """Remove the hash + sorted-set member for a conversation so it no longer surfaces in the UI."""
    canonical_id = owner_ids.canonical
    legacy_id = owner_ids.legacy if owner_ids.legacy and owner_ids.legacy != canonical_id else None
    if not canonical_id or not conversation_id:
        return
    _delete_for_owner(
        canonical_id,
        conversation_id,
        owner_key=_canonical_owner_key(canonical_id),
        reason=reason,
    )
    if legacy_id:
        _delete_for_owner(
            legacy_id,
            conversation_id,
            owner_key=legacy_id,
            reason=reason,
        )


def _delete_for_owner(
    owner_id: str,
    conversation_id: str,
    *,
    owner_key: str,
    reason: str,
) -> None:
    try:
        r = _redis_client()
        set_key = _sorted_set_key(owner_key)
        key_hash = _hash_key(owner_key, conversation_id)
        pipe = r.pipeline()
        pipe.delete(key_hash)
        pipe.zrem(set_key, conversation_id)
        pipe.execute()
        logger.info(
            "Deleted conversation metadata",
            extra={
                "owner_id": owner_id,
                "conversation_id": conversation_id,
                "reason": reason,
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to delete conversation metadata: %s",
            exc,
            extra={"owner_id": owner_id, "conversation_id": conversation_id},
        )
