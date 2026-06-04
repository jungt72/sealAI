"""
Session-Zonenbindung — Phase F-A.2

SessionEnvelope is the authoritative session object for Phase F routing.
It carries the zone binding (conversation | governed) which is sticky:
once governed, always governed for the lifetime of a session.

Persistence:
- Primary: Redis hash with TTL (default 24h)
- Key: session_envelope:{tenant_id}:{session_id}

Harte Regel (Umbauplan F-A.2):
  session_zone = "governed" is a routing invariant, not a UX mode.
  It can only be reset by creating a new session.
  No call-site may downgrade a governed session to conversation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 86_400  # 24 hours
_KEY_PREFIX = "session_envelope"


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

class SessionEnvelope(BaseModel):
    """Authoritative session object for Phase F gate and runtime routing.

    Satisfies the HasSessionZone protocol expected by gate.decide_route().
    """

    session_id: str
    tenant_id: str
    user_id: str
    session_zone: Literal["conversation", "governed"] = "conversation"
    entered_governed_at_turn: Optional[int] = None
    last_gate_decision: Optional[str] = None
    turn_count: int = 0
    conversation_history_ref: Optional[str] = None
    governed_state_ref: Optional[str] = None

    model_config = {"frozen": True}

    def escalate_to_governed(
        self,
        *,
        turn: int,
        gate_decision_reason: str,
    ) -> "SessionEnvelope":
        """Return a new envelope with session_zone = 'governed'.

        Calling this on an already-governed session is a no-op (returns self).
        The original envelope is never mutated — Pydantic frozen model.
        """
        if self.session_zone == "governed":
            return self

        return self.model_copy(
            update={
                "session_zone": "governed",
                "entered_governed_at_turn": turn,
                "last_gate_decision": gate_decision_reason,
            }
        )

    def with_gate_decision(self, reason: str) -> "SessionEnvelope":
        """Record the latest gate decision reason without changing zone."""
        return self.model_copy(update={"last_gate_decision": reason})


# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------

def _redis_key(tenant_id: str, session_id: str) -> str:
    return f"{_KEY_PREFIX}:{tenant_id}:{session_id}"


# ---------------------------------------------------------------------------
# Persistence — synchronous (for tests and CLI)
# ---------------------------------------------------------------------------

def save_session(envelope: SessionEnvelope, *, redis_client: object) -> None:
    """Persist envelope to Redis with TTL.

    Args:
        envelope: The session envelope to persist.
        redis_client: A sync redis.Redis instance.
    """
    key = _redis_key(envelope.tenant_id, envelope.session_id)
    payload = envelope.model_dump_json()
    redis_client.set(key, payload, ex=_SESSION_TTL_SECONDS)  # type: ignore[union-attr]
    log.debug("[session] saved key=%s zone=%s", key, envelope.session_zone)


def load_session(
    tenant_id: str,
    session_id: str,
    *,
    redis_client: object,
) -> Optional[SessionEnvelope]:
    """Load envelope from Redis. Returns None if not found or expired.

    Args:
        tenant_id: Tenant scope.
        session_id: Session identifier.
        redis_client: A sync redis.Redis instance.
    """
    key = _redis_key(tenant_id, session_id)
    raw = redis_client.get(key)  # type: ignore[union-attr]
    if raw is None:
        return None
    try:
        return SessionEnvelope.model_validate_json(raw)
    except Exception as exc:
        log.warning("[session] failed to deserialize key=%s (%s)", key, exc)
        return None


# ---------------------------------------------------------------------------
# Persistence — async
# ---------------------------------------------------------------------------

async def save_session_async(
    envelope: SessionEnvelope,
    *,
    redis_client: object,
) -> None:
    """Async persist — redis_client must be an aioredis-compatible async client."""
    key = _redis_key(envelope.tenant_id, envelope.session_id)
    payload = envelope.model_dump_json()
    await redis_client.set(key, payload, ex=_SESSION_TTL_SECONDS)  # type: ignore[union-attr]
    log.debug("[session] saved async key=%s zone=%s", key, envelope.session_zone)


async def load_session_async(
    tenant_id: str,
    session_id: str,
    *,
    redis_client: object,
) -> Optional[SessionEnvelope]:
    """Async load — redis_client must be an aioredis-compatible async client."""
    key = _redis_key(tenant_id, session_id)
    raw = await redis_client.get(key)  # type: ignore[union-attr]
    if raw is None:
        return None
    try:
        return SessionEnvelope.model_validate_json(raw)
    except Exception as exc:
        log.warning("[session] failed to deserialize key=%s (%s)", key, exc)
        return None


# ---------------------------------------------------------------------------
# Session lifecycle helpers
# ---------------------------------------------------------------------------

def get_or_create_session(
    tenant_id: str,
    session_id: str,
    user_id: str,
    *,
    redis_client: object,
) -> SessionEnvelope:
    """Load an existing session or create a fresh conversation-zone envelope.

    Never downgrades a governed session. Safe to call on every request.
    """
    existing = load_session(tenant_id, session_id, redis_client=redis_client)
    if existing is not None:
        log.debug(
            "[session] loaded session_id=%s zone=%s",
            session_id,
            existing.session_zone,
        )
        return existing

    fresh = SessionEnvelope(
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    save_session(fresh, redis_client=redis_client)
    log.debug("[session] created fresh session_id=%s", session_id)
    return fresh


async def get_or_create_session_async(
    tenant_id: str,
    session_id: str,
    user_id: str,
    *,
    redis_client: object,
) -> SessionEnvelope:
    """Async variant of get_or_create_session."""
    existing = await load_session_async(
        tenant_id, session_id, redis_client=redis_client
    )
    if existing is not None:
        log.debug(
            "[session] loaded session_id=%s zone=%s",
            session_id,
            existing.session_zone,
        )
        return existing

    fresh = SessionEnvelope(
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    await save_session_async(fresh, redis_client=redis_client)
    log.debug("[session] created fresh session_id=%s", session_id)
    return fresh


async def apply_gate_decision_and_persist_async(
    envelope: SessionEnvelope,
    *,
    gate_route: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"],
    gate_reason: str,
    turn: int = 0,  # kept for API compatibility; internal turn_count is used instead
    redis_client: object,
) -> SessionEnvelope:
    """Async variant of apply_gate_decision_and_persist.

    Fix 1 — audit log: the original escalation reason (e.g.
    "hard_override:numeric_unit") is preserved for the lifetime of a governed
    session. Subsequent "sticky_governed_session" reasons do NOT overwrite it.

    Fix 2 — turn tracking: turn_count is incremented on every call so that
    entered_governed_at_turn reflects the actual turn, not a hardcoded 0.
    """
    current_turn = envelope.turn_count + 1

    if gate_route == "GOVERNED" and envelope.session_zone != "governed":
        # Fresh escalation: record origin reason + accurate turn
        updated = envelope.escalate_to_governed(
            turn=current_turn,
            gate_decision_reason=gate_reason,
        ).model_copy(update={"turn_count": current_turn})
        await save_session_async(updated, redis_client=redis_client)
        return updated

    if envelope.session_zone == "governed":
        # Session already governed.
        # Never downgrade zone. Never overwrite the original escalation reason.
        # Only increment the turn counter and refresh the Redis TTL.
        updated = envelope.model_copy(update={"turn_count": current_turn})
        await save_session_async(updated, redis_client=redis_client)
        return updated

    # Light-mode gate in conversation session — record reason + increment turn
    updated = (
        envelope
        .with_gate_decision(gate_reason)
        .model_copy(update={"turn_count": current_turn})
    )
    await save_session_async(updated, redis_client=redis_client)
    return updated


def apply_gate_decision_and_persist(
    envelope: SessionEnvelope,
    *,
    gate_route: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"],
    gate_reason: str,
    turn: int = 0,  # kept for API compatibility; internal turn_count is used instead
    redis_client: object,
) -> SessionEnvelope:
    """Update session zone based on gate decision and persist.

    Escalates to governed if gate says GOVERNED. Zone can never be downgraded.

    Fix 1 — audit log: original escalation reason preserved for governed sessions.
    Fix 2 — turn tracking: turn_count incremented on every call.

    Returns the (possibly updated) envelope.
    """
    current_turn = envelope.turn_count + 1

    if gate_route == "GOVERNED" and envelope.session_zone != "governed":
        updated = envelope.escalate_to_governed(
            turn=current_turn,
            gate_decision_reason=gate_reason,
        ).model_copy(update={"turn_count": current_turn})
        save_session(updated, redis_client=redis_client)
        return updated

    if envelope.session_zone == "governed":
        # Session already governed — preserve escalation reason, increment turn only
        updated = envelope.model_copy(update={"turn_count": current_turn})
        save_session(updated, redis_client=redis_client)
        return updated

    # Light-mode gate in conversation session
    updated = (
        envelope
        .with_gate_decision(gate_reason)
        .model_copy(update={"turn_count": current_turn})
    )
    save_session(updated, redis_client=redis_client)
    return updated
