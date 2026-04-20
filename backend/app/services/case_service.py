from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.mutation_events import ActorType, MutationEventType
from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.models.mutation_event_model import MutationEventModel
from app.models.outbox_model import OutboxModel


class CaseMutationError(Exception):
    """Base error for case mutation failures."""


class OptimisticLockError(CaseMutationError):
    """Raised when the caller's expected revision is stale."""


class InvalidMutationError(CaseMutationError):
    """Raised when a mutation cannot be applied deterministically."""


class CaseService:
    """Single write path for case mutations and their durable side effects."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply_mutation(
        self,
        *,
        case_id: str,
        expected_revision: int,
        event_type: MutationEventType | str,
        payload: dict[str, Any],
        actor: str,
        actor_type: ActorType | str,
    ) -> MutationEventModel:
        """Apply one deterministic case mutation and persist all side effects."""

        event_type = self._coerce_event_type(event_type)
        actor_type = self._coerce_actor_type(actor_type)
        self._validate_payload(payload)
        if not case_id:
            raise InvalidMutationError("case_id is required")
        if expected_revision < 0:
            raise InvalidMutationError("expected_revision must be non-negative")
        if not actor:
            raise InvalidMutationError("actor is required")

        try:
            case_row = await self._load_case_for_update(case_id)
            if case_row is None:
                raise InvalidMutationError(f"case not found: {case_id}")
            tenant_id = self._require_tenant_id(case_row.tenant_id)

            old_revision = int(case_row.case_revision or 0)
            if old_revision != expected_revision:
                raise OptimisticLockError(
                    f"case {case_id} revision mismatch: expected "
                    f"{expected_revision}, got {old_revision}"
                )

            new_revision = old_revision + 1
            self._apply_case_updates(case_row, payload.get("case_updates", {}))
            tenant_id = self._require_tenant_id(case_row.tenant_id)
            mutation_row = self._build_mutation_event(
                case_row=case_row,
                tenant_id=tenant_id,
                event_type=event_type,
                payload=payload,
                old_revision=old_revision,
                new_revision=new_revision,
                actor=actor,
                actor_type=actor_type,
            )
            case_row.case_revision = new_revision

            snapshot_row = self._build_snapshot(
                case_id=str(case_row.id),
                revision=new_revision,
                payload=payload,
            )
            outbox_row = self._build_outbox(
                case_row=case_row,
                mutation_row=mutation_row,
                tenant_id=tenant_id,
                event_type=event_type,
            )

            self._session.add(mutation_row)
            self._session.add(snapshot_row)
            self._session.add(outbox_row)
            await self._session.commit()
            return mutation_row
        except CaseMutationError:
            await self._session.rollback()
            raise
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise InvalidMutationError("case mutation failed") from exc
        except Exception:
            await self._session.rollback()
            raise

    async def create_case(
        self,
        *,
        case_number: str,
        user_id: str,
        tenant_id: str,
        actor: str,
        actor_type: ActorType | str = ActorType.SYSTEM,
        session_id: str | None = None,
        subsegment: str | None = None,
        status: str = "active",
        state_json: dict[str, Any] | None = None,
        basis_hash: str | None = None,
        ontology_version: str | None = None,
        prompt_version: str | None = None,
        model_version: str | None = None,
    ) -> CaseRecord:
        """Create a case through the same audit/snapshot/outbox write path."""

        if not case_number:
            raise InvalidMutationError("case_number is required")
        if not user_id:
            raise InvalidMutationError("user_id is required")
        tenant_id = self._require_tenant_id(tenant_id)

        actor_type = self._coerce_actor_type(actor_type)
        payload = {
            "case_updates": {
                "case_number": case_number,
                "session_id": session_id,
                "user_id": user_id,
                "subsegment": subsegment,
                "status": status,
                "tenant_id": tenant_id,
            },
            "snapshot": {
                "state_json": state_json if state_json is not None else {},
                "basis_hash": basis_hash,
                "ontology_version": ontology_version,
                "prompt_version": prompt_version,
                "model_version": model_version,
            },
        }

        try:
            case_row = CaseRecord(
                case_number=case_number,
                session_id=session_id,
                user_id=user_id,
                subsegment=subsegment,
                status=status,
                tenant_id=tenant_id,
                case_revision=0,
            )
            self._session.add(case_row)
            await self._session.flush()

            mutation_row = self._build_mutation_event(
                case_row=case_row,
                tenant_id=tenant_id,
                event_type=MutationEventType.CASE_CREATED,
                payload=payload,
                old_revision=0,
                new_revision=1,
                actor=actor,
                actor_type=actor_type,
            )
            case_row.case_revision = 1
            snapshot_row = self._build_snapshot(
                case_id=str(case_row.id),
                revision=1,
                payload=payload,
            )
            outbox_row = self._build_outbox(
                case_row=case_row,
                mutation_row=mutation_row,
                tenant_id=tenant_id,
                event_type=MutationEventType.CASE_CREATED,
            )
            self._session.add(mutation_row)
            self._session.add(snapshot_row)
            self._session.add(outbox_row)
            await self._session.commit()
            await self._session.refresh(case_row)
            return case_row
        except CaseMutationError:
            await self._session.rollback()
            raise
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise InvalidMutationError("case creation failed") from exc
        except Exception:
            await self._session.rollback()
            raise

    async def write_snapshot(
        self,
        *,
        case_id: str,
        state_json: dict[str, Any],
        actor: str,
        actor_type: ActorType | str = ActorType.SYSTEM,
        basis_hash: str | None = None,
        ontology_version: str | None = None,
        prompt_version: str | None = None,
        model_version: str | None = None,
        case_updates: dict[str, Any] | None = None,
    ) -> CaseStateSnapshot:
        """Append a state snapshot unless the latest snapshot is identical."""

        if not isinstance(state_json, dict):
            raise InvalidMutationError("state_json must be a dict")

        case_row = await self._load_case(case_id)
        if case_row is None:
            raise InvalidMutationError(f"case not found: {case_id}")

        latest = await self._latest_snapshot(case_id)
        if (
            latest is not None
            and latest.basis_hash == basis_hash
            and latest.state_json == state_json
        ):
            return latest

        payload = {
            "case_updates": case_updates or {},
            "snapshot": {
                "state_json": state_json,
                "basis_hash": basis_hash,
                "ontology_version": ontology_version,
                "prompt_version": prompt_version,
                "model_version": model_version,
            },
        }
        expected_revision = int(case_row.case_revision or 0)
        await self.apply_mutation(
            case_id=case_id,
            expected_revision=expected_revision,
            event_type=MutationEventType.FIELD_UPDATED,
            payload=payload,
            actor=actor,
            actor_type=actor_type,
        )
        latest = await self._latest_snapshot(case_id)
        if latest is None:  # pragma: no cover - defensive guard
            raise InvalidMutationError("snapshot write did not produce a snapshot")
        return latest

    async def _load_case_for_update(self, case_id: str) -> CaseRecord | None:
        result = await self._session.execute(
            select(CaseRecord)
            .where(CaseRecord.id == case_id)
            .with_for_update()
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _load_case(self, case_id: str) -> CaseRecord | None:
        result = await self._session.execute(
            select(CaseRecord).where(CaseRecord.id == case_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_snapshot(self, case_id: str) -> CaseStateSnapshot | None:
        result = await self._session.execute(
            select(CaseStateSnapshot)
            .where(CaseStateSnapshot.case_id == case_id)
            .order_by(CaseStateSnapshot.revision.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _build_mutation_event(
        self,
        *,
        case_row: CaseRecord,
        tenant_id: str,
        event_type: MutationEventType,
        payload: dict[str, Any],
        old_revision: int,
        new_revision: int,
        actor: str,
        actor_type: ActorType,
    ) -> MutationEventModel:
        return MutationEventModel(
            mutation_id=str(uuid.uuid4()),
            case_id=str(case_row.id),
            tenant_id=self._require_tenant_id(tenant_id),
            event_type=event_type.value,
            payload=payload,
            case_revision_before=old_revision,
            case_revision_after=new_revision,
            actor=actor,
            actor_type=actor_type.value,
        )

    def _build_snapshot(
        self,
        *,
        case_id: str,
        revision: int,
        payload: dict[str, Any],
    ) -> CaseStateSnapshot:
        snapshot_payload = payload["snapshot"]
        return CaseStateSnapshot(
            case_id=case_id,
            revision=revision,
            state_json=snapshot_payload["state_json"],
            basis_hash=snapshot_payload.get("basis_hash"),
            ontology_version=snapshot_payload.get("ontology_version"),
            prompt_version=snapshot_payload.get("prompt_version"),
            model_version=snapshot_payload.get("model_version"),
        )

    def _build_outbox(
        self,
        *,
        case_row: CaseRecord,
        mutation_row: MutationEventModel,
        tenant_id: str,
        event_type: MutationEventType,
    ) -> OutboxModel:
        return OutboxModel(
            outbox_id=str(uuid.uuid4()),
            case_id=str(case_row.id),
            mutation_id=mutation_row.mutation_id,
            tenant_id=self._require_tenant_id(tenant_id),
            task_type=self._outbox_task_for_event(event_type),
            payload={
                "case_id": str(case_row.id),
                "mutation_id": mutation_row.mutation_id,
                "event_type": event_type.value,
            },
            status="pending",
        )

    def _apply_case_updates(
        self,
        case_row: CaseRecord,
        case_updates: Any,
    ) -> None:
        if not isinstance(case_updates, dict):
            raise InvalidMutationError("case_updates must be a dict")

        allowed_fields = {
            "application_pattern_id",
            "calc_library_version",
            "engineering_path",
            "inquiry_admissible",
            "payload",
            "phase",
            "pre_gate_classification",
            "request_type",
            "rfq_ready",
            "risk_engine_version",
            "ruleset_version",
            "schema_version",
            "sealing_material_family",
            "session_id",
            "status",
            "subsegment",
            "tenant_id",
            "user_id",
        }
        for field_name, value in case_updates.items():
            if field_name == "case_number":
                continue
            if value is None:
                continue
            if field_name not in allowed_fields:
                raise InvalidMutationError(f"unsupported case update: {field_name}")
            if field_name == "tenant_id":
                value = self._require_tenant_id(value)
            setattr(case_row, field_name, value)

    def _validate_payload(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise InvalidMutationError("payload must be a dict")
        snapshot_payload = payload.get("snapshot")
        if not isinstance(snapshot_payload, dict):
            raise InvalidMutationError("payload.snapshot must be a dict")
        state_json = snapshot_payload.get("state_json")
        if not isinstance(state_json, dict):
            raise InvalidMutationError("payload.snapshot.state_json must be a dict")
        case_updates = payload.get("case_updates", {})
        if not isinstance(case_updates, dict):
            raise InvalidMutationError("payload.case_updates must be a dict")

    def _coerce_event_type(self, event_type: MutationEventType | str) -> MutationEventType:
        try:
            return (
                event_type
                if isinstance(event_type, MutationEventType)
                else MutationEventType(event_type)
            )
        except ValueError as exc:
            raise InvalidMutationError(f"unsupported event_type: {event_type}") from exc

    def _coerce_actor_type(self, actor_type: ActorType | str) -> ActorType:
        try:
            return actor_type if isinstance(actor_type, ActorType) else ActorType(actor_type)
        except ValueError as exc:
            raise InvalidMutationError(f"unsupported actor_type: {actor_type}") from exc

    def _outbox_task_for_event(self, event_type: MutationEventType) -> str:
        if event_type in {
            MutationEventType.CALCULATION_RESULT,
            MutationEventType.NORM_CHECK_RESULT,
            MutationEventType.READINESS_CHANGED,
        }:
            return "risk_score_recompute"
        if event_type in {
            MutationEventType.CASE_CREATED,
            MutationEventType.FIELD_UPDATED,
        }:
            return "project_case_snapshot"
        return "notify_audit_log"

    def _require_tenant_id(self, tenant_id: Any) -> str:
        if tenant_id is None:
            raise InvalidMutationError("tenant_id is required")
        normalized = str(tenant_id).strip()
        if not normalized:
            raise InvalidMutationError("tenant_id is required")
        return normalized
