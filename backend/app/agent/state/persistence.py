"""
Governed State Persistence — Phase F-B.4

Single Responsibility:
  Load and save GovernedSessionState to Redis (volatile, session-scoped)
  and expose the contract for Postgres long-term snapshots (Phase G).

Storage split (Umbauplan F-B.4):
  Redis   — session-volatile: GovernedSessionState JSON, SessionEnvelope
  Postgres — long-term truth: GovernedState snapshots, Audit trail (Phase G)

Key schema:
  governed_state:{tenant_id}:{session_id}   → GovernedSessionState JSON
  TTL: 86400 s (same as SessionEnvelope)

Architecture rule:
  No direct writes to NormalizedState / AssertedState / GovernanceState here.
  This module is pure I/O — it stores and retrieves what the reducers produce.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.agent.state.models import GovernedSessionState

log = logging.getLogger(__name__)

_GOVERNED_STATE_TTL_SECONDS: int = 86_400  # 24 h


# ---------------------------------------------------------------------------
# Redis key helper
# ---------------------------------------------------------------------------

def _governed_state_key(tenant_id: str, session_id: str) -> str:
    return f"governed_state:{tenant_id}:{session_id}"


# ---------------------------------------------------------------------------
# Sync helpers (used by tests and sync callers)
# ---------------------------------------------------------------------------

def save_governed_state(
    state: GovernedSessionState,
    *,
    tenant_id: str,
    session_id: str,
    redis_client: object,
) -> None:
    """Persist GovernedSessionState to Redis (sync).

    Args:
        state: The current GovernedSessionState to persist.
        tenant_id: Tenant identifier for key namespacing.
        session_id: Session identifier.
        redis_client: A sync redis.Redis instance.
    """
    key = _governed_state_key(tenant_id, session_id)
    payload = state.model_dump_json()
    redis_client.set(key, payload, ex=_GOVERNED_STATE_TTL_SECONDS)  # type: ignore[union-attr]
    log.debug("[persistence] saved governed_state tenant=%s session=%s", tenant_id, session_id)


def load_governed_state(
    *,
    tenant_id: str,
    session_id: str,
    redis_client: object,
) -> Optional[GovernedSessionState]:
    """Load GovernedSessionState from Redis (sync).

    Returns None if no state exists for the given key.
    """
    key = _governed_state_key(tenant_id, session_id)
    raw = redis_client.get(key)  # type: ignore[union-attr]
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return GovernedSessionState.model_validate(data)
    except Exception:
        log.warning(
            "[persistence] failed to deserialize governed_state tenant=%s session=%s",
            tenant_id,
            session_id,
            exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Async helpers (used by FastAPI endpoints)
# ---------------------------------------------------------------------------

async def save_governed_state_async(
    state: GovernedSessionState,
    *,
    tenant_id: str,
    session_id: str,
    redis_client: object,
) -> None:
    """Persist GovernedSessionState to Redis (async).

    redis_client must be an aioredis-compatible async client.
    """
    key = _governed_state_key(tenant_id, session_id)
    payload = state.model_dump_json()
    await redis_client.set(key, payload, ex=_GOVERNED_STATE_TTL_SECONDS)  # type: ignore[union-attr]
    log.debug(
        "[persistence] async saved governed_state tenant=%s session=%s", tenant_id, session_id
    )


async def load_governed_state_async(
    *,
    tenant_id: str,
    session_id: str,
    redis_client: object,
) -> Optional[GovernedSessionState]:
    """Load GovernedSessionState from Redis (async).

    Returns None if no state exists for the given key.
    redis_client must be an aioredis-compatible async client.
    """
    key = _governed_state_key(tenant_id, session_id)
    raw = await redis_client.get(key)  # type: ignore[union-attr]
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return GovernedSessionState.model_validate(data)
    except Exception:
        log.warning(
            "[persistence] async failed to deserialize governed_state tenant=%s session=%s",
            tenant_id,
            session_id,
            exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# get_or_create helper
# ---------------------------------------------------------------------------

async def get_or_create_governed_state_async(
    *,
    tenant_id: str,
    session_id: str,
    redis_client: object,
) -> GovernedSessionState:
    """Load existing or create a fresh GovernedSessionState (async)."""
    existing = await load_governed_state_async(
        tenant_id=tenant_id,
        session_id=session_id,
        redis_client=redis_client,
    )
    if existing is not None:
        return existing
    fresh = GovernedSessionState()
    log.debug(
        "[persistence] new governed_state tenant=%s session=%s", tenant_id, session_id
    )
    return fresh
