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

import hashlib
import json
import logging
from typing import Any, Optional

from app.agent.agent.prompts import REASONING_PROMPT_VERSION
from app.agent.state.models import GovernedSessionState

log = logging.getLogger(__name__)

_GOVERNED_STATE_TTL_SECONDS: int = 86_400  # 24 h
_DEFAULT_ONTOLOGY_VERSION = "sealai_norm_v1"


# ---------------------------------------------------------------------------
# Redis key helper
# ---------------------------------------------------------------------------

def _governed_state_key(tenant_id: str, session_id: str) -> str:
    return f"governed_state:{tenant_id}:{session_id}"


def compute_decision_basis_hash(state: GovernedSessionState) -> str:
    """Return a compact deterministic hash for the current decision basis."""

    relevant = {
        "normalized": state.normalized.model_dump(mode="json"),
        "derived": state.derived.model_dump(mode="json"),
        "evidence_versions": dict(state.evidence.source_versions),
        "ontology_version": (
            str(state.sealai_norm.identity.norm_version).strip()
            if state.sealai_norm.identity.norm_version
            else _DEFAULT_ONTOLOGY_VERSION
        ),
        "prompt_version": REASONING_PROMPT_VERSION,
    }
    payload = json.dumps(relevant, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _ontology_version(state: GovernedSessionState) -> str:
    if state.sealai_norm.identity.norm_version:
        return str(state.sealai_norm.identity.norm_version).strip()
    return _DEFAULT_ONTOLOGY_VERSION


def _with_decision_basis_hash(state: GovernedSessionState) -> GovernedSessionState:
    decision_basis_hash = compute_decision_basis_hash(state)
    return state.model_copy(
        update={
            "decision": state.decision.model_copy(
                update={"decision_basis_hash": decision_basis_hash}
            )
        }
    )


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
    state = _with_decision_basis_hash(state)
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
        state = GovernedSessionState.model_validate(data)
        return _with_decision_basis_hash(state)
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
    state = _with_decision_basis_hash(state)
    key = _governed_state_key(tenant_id, session_id)
    payload = state.model_dump_json()
    await redis_client.set(key, payload, ex=_GOVERNED_STATE_TTL_SECONDS)  # type: ignore[union-attr]
    log.debug(
        "[persistence] async saved governed_state tenant=%s session=%s", tenant_id, session_id
    )


async def save_governed_state_snapshot_async(
    state: GovernedSessionState,
    *,
    case_number: str,
    user_id: str,
    subsegment: str | None = None,
    status: str = "active",
) -> None:
    """Persist a governed case row and additive Postgres state snapshot."""

    from sqlalchemy import select  # noqa: PLC0415

    try:
        from app.agent.agent.graph import _GRAPH_MODEL_ID  # noqa: PLC0415
        from app.database import AsyncSessionLocal  # noqa: PLC0415
        from app.models.case_record import CaseRecord  # noqa: PLC0415
        from app.models.case_state_snapshot import CaseStateSnapshot  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        log.warning(
            "[persistence] Postgres snapshot persistence unavailable for case=%s: %s",
            case_number,
            exc,
        )
        return

    persisted_state = _with_decision_basis_hash(state)
    basis_hash = persisted_state.decision.decision_basis_hash
    desired_revision = int(persisted_state.analysis_cycle or 0)
    snapshot_payload: dict[str, Any] = persisted_state.model_dump(mode="json")

    async with AsyncSessionLocal() as session:
        case_result = await session.execute(
            select(CaseRecord).where(CaseRecord.case_number == case_number).limit(1)
        )
        case_row = case_result.scalar_one_or_none()
        if case_row is None:
            case_row = CaseRecord(
                case_number=case_number,
                user_id=user_id,
                subsegment=subsegment,
                status=status,
            )
            session.add(case_row)
            await session.flush()
        else:
            case_row.user_id = user_id
            case_row.status = status or case_row.status
            if subsegment is not None:
                case_row.subsegment = subsegment

        latest_result = await session.execute(
            select(CaseStateSnapshot)
            .where(CaseStateSnapshot.case_id == case_row.id)
            .order_by(CaseStateSnapshot.revision.desc())
            .limit(1)
        )
        latest_snapshot = latest_result.scalar_one_or_none()
        if (
            latest_snapshot is not None
            and latest_snapshot.basis_hash == basis_hash
            and latest_snapshot.state_json == snapshot_payload
        ):
            await session.commit()
            return

        next_revision = desired_revision if desired_revision > 0 else 1
        if latest_snapshot is not None and next_revision <= int(latest_snapshot.revision):
            next_revision = int(latest_snapshot.revision) + 1

        session.add(
            CaseStateSnapshot(
                case_id=case_row.id,
                revision=next_revision,
                state_json=snapshot_payload,
                basis_hash=basis_hash,
                ontology_version=_ontology_version(persisted_state),
                prompt_version=REASONING_PROMPT_VERSION,
                model_version=_GRAPH_MODEL_ID,
            )
        )
        await session.commit()


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
        state = GovernedSessionState.model_validate(data)
        return _with_decision_basis_hash(state)
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
        return _with_decision_basis_hash(existing)
    fresh = _with_decision_basis_hash(GovernedSessionState())
    log.debug(
        "[persistence] new governed_state tenant=%s session=%s", tenant_id, session_id
    )
    return fresh
