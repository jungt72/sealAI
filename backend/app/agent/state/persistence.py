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
from dataclasses import dataclass
from typing import Any, Optional

from app.agent.prompts import REASONING_PROMPT_VERSION
from app.agent.state.models import GovernedSessionState

log = logging.getLogger(__name__)

_GOVERNED_STATE_TTL_SECONDS: int = 86_400  # 24 h
_DEFAULT_ONTOLOGY_VERSION = "sealai_norm_v1"


@dataclass(frozen=True)
class GovernedCaseSnapshotRead:
    case_id: str
    case_number: str
    user_id: str
    revision: int
    state_json: dict[str, Any]
    basis_hash: str | None
    ontology_version: str | None
    prompt_version: str | None
    model_version: str | None
    created_at: Any


@dataclass(frozen=True)
class GovernedCaseSnapshotRevisionRead:
    revision: int
    basis_hash: str | None
    ontology_version: str | None
    prompt_version: str | None
    model_version: str | None
    created_at: Any


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
        from app.agent.graph.legacy_graph import _GRAPH_MODEL_ID  # noqa: PLC0415
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


async def get_case_by_number_async(
    *,
    case_number: str,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    """Load a case row by productive case number with optional owner guard."""

    from sqlalchemy import select  # noqa: PLC0415

    try:
        from app.database import AsyncSessionLocal  # noqa: PLC0415
        from app.models.case_record import CaseRecord  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        log.warning(
            "[persistence] Postgres case read unavailable for case=%s: %s",
            case_number,
            exc,
        )
        return None

    async with AsyncSessionLocal() as session:
        query = select(CaseRecord).where(CaseRecord.case_number == case_number).limit(1)
        if user_id is not None:
            query = query.where(CaseRecord.user_id == user_id)
        result = await session.execute(query)
        case_row = result.scalar_one_or_none()
        if case_row is None:
            return None
        return {
            "id": str(case_row.id),
            "case_number": str(case_row.case_number),
            "user_id": str(case_row.user_id),
            "subsegment": case_row.subsegment,
            "status": str(case_row.status),
            "created_at": getattr(case_row, "created_at", None),
            "updated_at": getattr(case_row, "updated_at", None),
        }


async def list_cases_async(
    *,
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List owned governed case rows newest first with latest snapshot revision when available."""

    from sqlalchemy import select  # noqa: PLC0415

    try:
        from app.database import AsyncSessionLocal  # noqa: PLC0415
        from app.models.case_record import CaseRecord  # noqa: PLC0415
        from app.models.case_state_snapshot import CaseStateSnapshot  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        log.warning(
            "[persistence] Postgres case list unavailable for user=%s: %s",
            user_id,
            exc,
        )
        return []

    async with AsyncSessionLocal() as session:
        case_result = await session.execute(
            select(CaseRecord)
            .where(CaseRecord.user_id == user_id)
            .order_by(CaseRecord.updated_at.desc())
            .limit(limit)
        )
        case_rows = list(case_result.scalars().all())
        items: list[dict[str, Any]] = []
        for case_row in case_rows:
            latest_result = await session.execute(
                select(CaseStateSnapshot)
                .where(CaseStateSnapshot.case_id == case_row.id)
                .order_by(CaseStateSnapshot.revision.desc())
                .limit(1)
            )
            latest_snapshot = latest_result.scalar_one_or_none()
            items.append(
                {
                    "id": str(case_row.id),
                    "case_number": str(case_row.case_number),
                    "status": str(case_row.status),
                    "subsegment": case_row.subsegment,
                    "updated_at": getattr(case_row, "updated_at", None),
                    "latest_revision": (
                        int(latest_snapshot.revision)
                        if latest_snapshot is not None
                        else None
                    ),
                }
            )
        return items


async def get_latest_governed_case_snapshot_async(
    *,
    case_number: str,
    user_id: str | None = None,
) -> GovernedCaseSnapshotRead | None:
    return await get_governed_case_snapshot_by_revision_async(
        case_number=case_number,
        revision=None,
        user_id=user_id,
    )


async def get_governed_case_snapshot_by_revision_async(
    *,
    case_number: str,
    revision: int | None,
    user_id: str | None = None,
) -> GovernedCaseSnapshotRead | None:
    """Load the latest or a targeted governed Postgres snapshot for a case."""

    from sqlalchemy import select  # noqa: PLC0415

    try:
        from app.database import AsyncSessionLocal  # noqa: PLC0415
        from app.models.case_record import CaseRecord  # noqa: PLC0415
        from app.models.case_state_snapshot import CaseStateSnapshot  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        log.warning(
            "[persistence] Postgres snapshot read unavailable for case=%s: %s",
            case_number,
            exc,
        )
        return None

    async with AsyncSessionLocal() as session:
        case_query = select(CaseRecord).where(CaseRecord.case_number == case_number).limit(1)
        if user_id is not None:
            case_query = case_query.where(CaseRecord.user_id == user_id)
        case_result = await session.execute(case_query)
        case_row = case_result.scalar_one_or_none()
        if case_row is None:
            return None

        snapshot_query = select(CaseStateSnapshot).where(CaseStateSnapshot.case_id == case_row.id)
        if revision is not None:
            snapshot_query = snapshot_query.where(CaseStateSnapshot.revision == revision)
        else:
            snapshot_query = snapshot_query.order_by(CaseStateSnapshot.revision.desc())
        snapshot_query = snapshot_query.limit(1)

        snapshot_result = await session.execute(snapshot_query)
        snapshot_row = snapshot_result.scalar_one_or_none()
        if snapshot_row is None:
            return None

        state_json = dict(snapshot_row.state_json or {})
        return GovernedCaseSnapshotRead(
            case_id=str(case_row.id),
            case_number=str(case_row.case_number),
            user_id=str(case_row.user_id),
            revision=int(snapshot_row.revision),
            state_json=state_json,
            basis_hash=snapshot_row.basis_hash,
            ontology_version=snapshot_row.ontology_version,
            prompt_version=snapshot_row.prompt_version,
            model_version=snapshot_row.model_version,
            created_at=getattr(snapshot_row, "created_at", None),
        )


async def list_governed_case_snapshots_async(
    *,
    case_number: str,
    user_id: str | None = None,
    limit: int = 50,
) -> list[GovernedCaseSnapshotRevisionRead]:
    """List governed snapshot revisions for a case newest first."""

    from sqlalchemy import select  # noqa: PLC0415

    try:
        from app.database import AsyncSessionLocal  # noqa: PLC0415
        from app.models.case_record import CaseRecord  # noqa: PLC0415
        from app.models.case_state_snapshot import CaseStateSnapshot  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        log.warning(
            "[persistence] Postgres snapshot list unavailable for case=%s: %s",
            case_number,
            exc,
        )
        return []

    async with AsyncSessionLocal() as session:
        case_query = select(CaseRecord).where(CaseRecord.case_number == case_number).limit(1)
        if user_id is not None:
            case_query = case_query.where(CaseRecord.user_id == user_id)
        case_result = await session.execute(case_query)
        case_row = case_result.scalar_one_or_none()
        if case_row is None:
            return []

        snapshot_result = await session.execute(
            select(CaseStateSnapshot)
            .where(CaseStateSnapshot.case_id == case_row.id)
            .order_by(CaseStateSnapshot.revision.desc())
            .limit(limit)
        )
        snapshot_rows = list(snapshot_result.scalars().all())
        return [
            GovernedCaseSnapshotRevisionRead(
                revision=int(snapshot_row.revision),
                basis_hash=snapshot_row.basis_hash,
                ontology_version=snapshot_row.ontology_version,
                prompt_version=snapshot_row.prompt_version,
                model_version=snapshot_row.model_version,
                created_at=getattr(snapshot_row, "created_at", None),
            )
            for snapshot_row in snapshot_rows
        ]


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
