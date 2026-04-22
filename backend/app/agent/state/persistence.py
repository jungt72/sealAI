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
from app.agent.state.models import GovernedPersistenceMarker, GovernedSessionState

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


@dataclass(frozen=True)
class GovernedStateSnapshotPersistenceResult:
    case_id: str
    case_number: str
    postgres_snapshot_revision: int
    postgres_case_revision: int
    basis_hash: str | None


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


def with_snapshot_persistence_marker(
    state: GovernedSessionState,
    result: GovernedStateSnapshotPersistenceResult,
) -> GovernedSessionState:
    """Return state marked comparable to the successfully persisted snapshot."""

    return state.model_copy(
        update={
            "persistence_marker": GovernedPersistenceMarker(
                snapshot_comparable=True,
                postgres_snapshot_revision=result.postgres_snapshot_revision,
                postgres_case_revision=result.postgres_case_revision,
            )
        }
    )


def _without_persistence_marker(state: GovernedSessionState) -> GovernedSessionState:
    return state.model_copy(update={"persistence_marker": None})


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
    tenant_id: str,
    pre_gate_classification: str | None = None,
    subsegment: str | None = None,
    status: str = "active",
) -> GovernedStateSnapshotPersistenceResult | None:
    """Persist a governed case row and additive Postgres state snapshot."""

    from sqlalchemy import select  # noqa: PLC0415

    try:
        _GRAPH_MODEL_ID = "gpt-4o-mini"
        from app.database import AsyncSessionLocal  # noqa: PLC0415
        from app.domain.engineering_path import AUTHORITY_ENGINEERING_PATHS  # noqa: PLC0415
        from app.domain.pre_gate_classification import PreGateClassification  # noqa: PLC0415
        from app.domain.sealing_material_family import AUTHORITY_SEALING_MATERIAL_FAMILIES  # noqa: PLC0415
        from app.models.case_record import CaseRecord  # noqa: PLC0415
        from app.services.case_service import CaseService  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        log.warning(
            "[persistence] Postgres snapshot persistence unavailable for case=%s: %s",
            case_number,
            exc,
        )
        return None

    persisted_state = _without_persistence_marker(_with_decision_basis_hash(state))
    basis_hash = persisted_state.decision.decision_basis_hash
    snapshot_payload: dict[str, Any] = persisted_state.model_dump(mode="json")
    readiness_case_updates: dict[str, Any] = {
        "inquiry_admissible": bool(persisted_state.governance.rfq_admissible),
        "rfq_ready": bool(persisted_state.rfq.rfq_ready),
    }
    explicit_pre_gate_classification = (
        PreGateClassification(pre_gate_classification).value
        if pre_gate_classification is not None
        else None
    )
    case_updates_from_runtime: dict[str, Any] = {}
    if explicit_pre_gate_classification is not None:
        case_updates_from_runtime["pre_gate_classification"] = explicit_pre_gate_classification
    case_updates_from_governed_state: dict[str, Any] = {}
    sealing_material_family = str(
        persisted_state.sealai_norm.material.sealing_material_family or ""
    ).strip()
    if sealing_material_family in AUTHORITY_SEALING_MATERIAL_FAMILIES:
        case_updates_from_governed_state["sealing_material_family"] = sealing_material_family
    engineering_path = persisted_state.sealai_norm.identity.engineering_path
    if (
        isinstance(engineering_path, str)
        and engineering_path
        and engineering_path in AUTHORITY_ENGINEERING_PATHS
    ):
        case_updates_from_governed_state["engineering_path"] = engineering_path

    async with AsyncSessionLocal() as session:
        service = CaseService(session)
        case_result = await session.execute(
            select(CaseRecord).where(CaseRecord.case_number == case_number).limit(1)
        )
        case_row = case_result.scalar_one_or_none()
        if case_row is None:
            created_case = await service.create_case(
                case_number=case_number,
                user_id=user_id,
                tenant_id=tenant_id,
                subsegment=subsegment,
                status=status,
                actor="governed_state_persistence",
                state_json=snapshot_payload,
                basis_hash=basis_hash,
                ontology_version=_ontology_version(persisted_state),
                prompt_version=REASONING_PROMPT_VERSION,
                model_version=_GRAPH_MODEL_ID,
                case_updates={
                    **readiness_case_updates,
                    **case_updates_from_runtime,
                    **case_updates_from_governed_state,
                },
            )
            case_revision = int(created_case.case_revision or 1)
            return GovernedStateSnapshotPersistenceResult(
                case_id=str(created_case.id),
                case_number=str(created_case.case_number),
                postgres_snapshot_revision=case_revision,
                postgres_case_revision=case_revision,
                basis_hash=basis_hash,
            )

        case_updates: dict[str, Any] = {
            "status": status or case_row.status,
            **readiness_case_updates,
            **case_updates_from_runtime,
            **case_updates_from_governed_state,
        }
        if subsegment is not None:
            case_updates["subsegment"] = subsegment
        snapshot_row = await service.write_snapshot(
            case_id=str(case_row.id),
            state_json=snapshot_payload,
            basis_hash=basis_hash,
            ontology_version=_ontology_version(persisted_state),
            prompt_version=REASONING_PROMPT_VERSION,
            model_version=_GRAPH_MODEL_ID,
            case_updates=case_updates,
            actor="governed_state_persistence",
        )
        case_revision = int(
            getattr(case_row, "case_revision", snapshot_row.revision)
            or snapshot_row.revision
        )
        return GovernedStateSnapshotPersistenceResult(
            case_id=str(case_row.id),
            case_number=str(case_row.case_number),
            postgres_snapshot_revision=int(snapshot_row.revision),
            postgres_case_revision=case_revision,
            basis_hash=basis_hash,
        )


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
        from app.services.case_service import CaseService  # noqa: PLC0415
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
        service = CaseService(session)
        items: list[dict[str, Any]] = []
        for case_row in case_rows:
            latest_revision = await service.get_latest_snapshot_revision_for_case_id(
                str(case_row.id)
            )
            items.append(
                {
                    "id": str(case_row.id),
                    "case_number": str(case_row.case_number),
                    "status": str(case_row.status),
                    "subsegment": case_row.subsegment,
                    "updated_at": getattr(case_row, "updated_at", None),
                    "latest_revision": latest_revision,
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

    try:
        from app.database import AsyncSessionLocal  # noqa: PLC0415
        from app.services.case_service import CaseService  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        log.warning(
            "[persistence] Postgres snapshot read unavailable for case=%s: %s",
            case_number,
            exc,
        )
        return None

    async with AsyncSessionLocal() as session:
        result = await CaseService(session).get_snapshot_by_revision_for_case_number(
            case_number=case_number,
            revision=revision,
            user_id=user_id,
        )
        if result is None:
            return None
        case_row, snapshot_row = result

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

    try:
        from app.database import AsyncSessionLocal  # noqa: PLC0415
        from app.services.case_service import CaseService  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        log.warning(
            "[persistence] Postgres snapshot list unavailable for case=%s: %s",
            case_number,
            exc,
        )
        return []

    async with AsyncSessionLocal() as session:
        snapshot_rows = await CaseService(session).list_snapshot_revisions_for_case_number(
            case_number=case_number,
            user_id=user_id,
            limit=limit,
        )
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

# ---------------------------------------------------------------------------
# H1.3 — Case management (session-scoped)
# ---------------------------------------------------------------------------

async def get_or_create_case(
    session_id: str,
    user_id: str,
    tenant_id: str,
    db: Any,  # AsyncSession
    *,
    subsegment: str | None = None,
) -> Any:  # CaseRecord
    """Get or create a governed cases row keyed by session_id.

    One session → one case.  case_number is auto-generated in STS-INQ format.
    """
    from sqlalchemy import func, select  # noqa: PLC0415

    try:
        from app.models.case_record import CaseRecord  # noqa: PLC0415
        from app.services.case_service import CaseService  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover
        log.warning("[persistence] CaseRecord unavailable: %s", exc)
        raise

    # Fast path — existing case
    result = await db.execute(
        select(CaseRecord).where(CaseRecord.session_id == session_id).limit(1)
    )
    case = result.scalar_one_or_none()
    if case is not None:
        return case

    # Create new case with sequential case_number
    case_number = await _generate_case_number(db)
    case = await CaseService(db).create_case(
        case_number=case_number,
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        subsegment=subsegment,
        status="active",
        actor="case_persistence",
        state_json={},
    )
    log.info(
        "[persistence] created case case_number=%s session=%s user=%s",
        case_number,
        session_id,
        user_id,
    )
    return case


async def _generate_case_number(db: Any) -> str:  # AsyncSession
    """Generate next sequential case number: STS-INQ-YYYY-MM-NNN."""
    from datetime import date  # noqa: PLC0415

    from sqlalchemy import func, select  # noqa: PLC0415

    from app.models.case_record import CaseRecord  # noqa: PLC0415

    today = date.today()
    prefix = f"STS-INQ-{today.year}-{today.month:02d}"
    result = await db.execute(
        select(func.count()).select_from(CaseRecord).where(
            CaseRecord.case_number.like(f"{prefix}-%")
        )
    )
    n = (result.scalar() or 0) + 1
    return f"{prefix}-{n:03d}"


async def write_state_snapshot(
    case_id: str,
    state: GovernedSessionState,
    db: Any,  # AsyncSession
) -> Any:
    """Append a new state snapshot revision for a case.

    Skips write if the latest snapshot has the same basis_hash and state_json.
    """
    try:
        _GRAPH_MODEL_ID = "gpt-4o-mini"
    except Exception:
        _GRAPH_MODEL_ID = "unknown"

    try:
        from app.services.case_service import CaseService  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover
        log.warning("[persistence] CaseService unavailable: %s", exc)
        raise

    persisted = _with_decision_basis_hash(state)
    basis_hash = persisted.decision.decision_basis_hash
    snapshot_payload = persisted.model_dump(mode="json")

    snapshot = await CaseService(db).write_snapshot(
        case_id=case_id,
        state_json=snapshot_payload,
        basis_hash=basis_hash,
        ontology_version=_ontology_version(persisted),
        prompt_version=REASONING_PROMPT_VERSION,
        model_version=_GRAPH_MODEL_ID,
        actor="state_snapshot_persistence",
    )
    log.debug(
        "[persistence] wrote state snapshot case_id=%s revision=%d basis_hash=%s",
        case_id,
        int(snapshot.revision),
        basis_hash,
    )
    return snapshot


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
