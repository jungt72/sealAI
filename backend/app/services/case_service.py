from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.mutation_events import ActorType, MutationEventType
from app.domain.critical_field_contract import (
    PRESSURE_FIELDS,
    is_critical_technical_field,
)
from app.domain.derived_dependency_contract import mark_stale_snapshot_derived_values
from app.models.case_record import CaseRecord
from app.models.case_state_snapshot import CaseStateSnapshot
from app.models.mutation_event_model import MutationEventModel
from app.models.outbox_model import OutboxModel
from app.services.conflict_detection_service import (
    ConflictCandidate,
    ConflictDetectionService,
)


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
            await self._validate_acceptance_against_latest_snapshot(
                case_id=str(case_row.id),
                payload=payload,
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
        case_updates: dict[str, Any] | None = None,
    ) -> CaseRecord:
        """Create a case through the same audit/snapshot/outbox write path."""

        if not case_number:
            raise InvalidMutationError("case_number is required")
        if not user_id:
            raise InvalidMutationError("user_id is required")
        if not actor:
            raise InvalidMutationError("actor is required")
        if state_json is not None and not isinstance(state_json, dict):
            raise InvalidMutationError("state_json must be a dict")
        tenant_id = self._require_tenant_id(tenant_id)
        normalized_case_updates = case_updates if case_updates is not None else {}
        self._validate_case_updates(normalized_case_updates)

        actor_type = self._coerce_actor_type(actor_type)
        base_case_updates: dict[str, Any] = {
            "case_number": case_number,
            "session_id": session_id,
            "user_id": user_id,
            "subsegment": subsegment,
            "status": status,
            "tenant_id": tenant_id,
        }
        payload = {
            "case_updates": {
                **base_case_updates,
                **normalized_case_updates,
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
            self._apply_case_updates(case_row, normalized_case_updates)
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
        normalized_case_updates = case_updates if case_updates is not None else {}
        self._validate_case_updates(normalized_case_updates)

        case_row = await self._load_case(case_id)
        if case_row is None:
            raise InvalidMutationError(f"case not found: {case_id}")

        latest = await self._latest_snapshot(case_id)
        if (
            latest is not None
            and latest.basis_hash == basis_hash
            and latest.state_json == state_json
            and not normalized_case_updates
        ):
            return latest

        payload = {
            "case_updates": normalized_case_updates,
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

    async def get_latest_snapshot_for_case_number(
        self,
        *,
        case_number: str,
        tenant_id: str,
        user_id: str,
    ) -> tuple[CaseRecord, CaseStateSnapshot] | None:
        """Return the latest persisted snapshot for a case-number read path."""

        return await self.get_snapshot_by_revision_for_case_number(
            case_number=case_number,
            revision=None,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    async def get_snapshot_by_revision_for_case_number(
        self,
        *,
        case_number: str,
        revision: int | None,
        tenant_id: str,
        user_id: str,
    ) -> tuple[CaseRecord, CaseStateSnapshot] | None:
        """Return a specific or latest snapshot with a required owner guard."""

        self._validate_snapshot_read_scope(case_number=case_number, user_id=user_id)
        tenant_id = self._require_tenant_id(tenant_id)
        if revision is not None and revision < 0:
            raise InvalidMutationError("revision must be non-negative")
        case_query = select(CaseRecord).where(CaseRecord.case_number == case_number).limit(1)
        case_query = case_query.where(CaseRecord.tenant_id == tenant_id)
        case_query = case_query.where(CaseRecord.user_id == user_id)
        case_result = await self._session.execute(case_query)
        case_row = case_result.scalar_one_or_none()
        if case_row is None:
            return None

        snapshot_query = select(CaseStateSnapshot).where(CaseStateSnapshot.case_id == case_row.id)
        if revision is not None:
            snapshot_query = snapshot_query.where(CaseStateSnapshot.revision == revision)
        else:
            snapshot_query = snapshot_query.order_by(CaseStateSnapshot.revision.desc())
        snapshot_query = snapshot_query.limit(1)

        snapshot_result = await self._session.execute(snapshot_query)
        snapshot_row = snapshot_result.scalar_one_or_none()
        if snapshot_row is None:
            return None
        return case_row, snapshot_row

    async def list_snapshot_revisions_for_case_number(
        self,
        *,
        case_number: str,
        tenant_id: str,
        user_id: str,
        limit: int = 50,
    ) -> list[CaseStateSnapshot]:
        """List snapshot revisions newest first for a case-number read path."""

        self._validate_snapshot_read_scope(case_number=case_number, user_id=user_id)
        tenant_id = self._require_tenant_id(tenant_id)
        if limit < 1:
            raise InvalidMutationError("limit must be positive")
        case_query = select(CaseRecord).where(CaseRecord.case_number == case_number).limit(1)
        case_query = case_query.where(CaseRecord.tenant_id == tenant_id)
        case_query = case_query.where(CaseRecord.user_id == user_id)
        case_result = await self._session.execute(case_query)
        case_row = case_result.scalar_one_or_none()
        if case_row is None:
            return []

        snapshot_result = await self._session.execute(
            select(CaseStateSnapshot)
            .where(CaseStateSnapshot.case_id == case_row.id)
            .order_by(CaseStateSnapshot.revision.desc())
            .limit(limit)
        )
        return list(snapshot_result.scalars().all())

    async def get_latest_snapshot_revision_for_case_id(self, case_id: str) -> int | None:
        """Return the latest snapshot revision for a case row, if one exists."""

        latest = await self._latest_snapshot(case_id)
        if latest is None:
            return None
        return int(latest.revision)

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
        audit_fields = _extract_mutation_audit_fields(payload)
        return MutationEventModel(
            mutation_id=str(uuid.uuid4()),
            case_id=str(case_row.id),
            tenant_id=self._require_tenant_id(tenant_id),
            event_type=event_type.value,
            payload=payload,
            source_turn_id=audit_fields["source_turn_id"],
            source_document_id=audit_fields["source_document_id"],
            proposed_delta=audit_fields["proposed_delta"],
            accepted_delta=audit_fields["accepted_delta"],
            rejected_delta=audit_fields["rejected_delta"],
            rejection_reasons=audit_fields["rejection_reasons"],
            ruleset_version=audit_fields["ruleset_version"],
            model_id=audit_fields["model_id"],
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
        state_json = self._snapshot_state_with_stale_derived_values(
            snapshot_payload["state_json"],
            payload=payload,
            revision=revision,
        )
        return CaseStateSnapshot(
            case_id=case_id,
            revision=revision,
            state_json=state_json,
            basis_hash=snapshot_payload.get("basis_hash"),
            ontology_version=snapshot_payload.get("ontology_version"),
            prompt_version=snapshot_payload.get("prompt_version"),
            model_version=snapshot_payload.get("model_version"),
        )

    def _snapshot_state_with_stale_derived_values(
        self,
        state_json: dict[str, Any],
        *,
        payload: dict[str, Any],
        revision: int,
    ) -> dict[str, Any]:
        accepted_delta = _dict_or_empty(payload.get("accepted_delta"))
        changed_fields = [
            field_name
            for field_name in accepted_delta
            if is_critical_technical_field(field_name)
        ]
        if not changed_fields:
            return state_json
        return mark_stale_snapshot_derived_values(
            state_json,
            changed_fields=changed_fields,
            new_revision=revision,
            reason="accepted_case_delta_changed_inputs",
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
        self._validate_case_updates(case_updates)
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
        }
        for field_name, value in case_updates.items():
            if field_name not in allowed_fields:
                raise InvalidMutationError(f"unsupported case update: {field_name}")
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
        self._validate_case_updates(case_updates, payload_key="payload.case_updates")
        self._validate_delta_audit_contract(payload)

    def _validate_delta_audit_contract(self, payload: dict[str, Any]) -> None:
        proposed_delta = _dict_or_empty(
            payload.get("proposed_delta") or payload.get("proposed_case_delta")
        )
        accepted_delta = _dict_or_empty(payload.get("accepted_delta"))
        rejected_delta = _dict_or_empty(payload.get("rejected_delta"))

        if not accepted_delta and not rejected_delta:
            return
        if not proposed_delta:
            raise InvalidMutationError(
                "accepted_delta/rejected_delta require proposed_delta"
            )
        proposed_fields = _delta_field_names(proposed_delta)
        decided_fields = set(accepted_delta) | set(rejected_delta)
        unknown_decisions = sorted(decided_fields.difference(proposed_fields))
        if unknown_decisions:
            raise InvalidMutationError(
                "accepted_delta/rejected_delta fields must exist in proposed_delta: "
                f"{', '.join(unknown_decisions)}"
            )

        overlap = set(accepted_delta).intersection(rejected_delta)
        if overlap:
            field_list = ", ".join(sorted(overlap))
            raise InvalidMutationError(
                f"fields cannot be both accepted and rejected: {field_list}"
            )

        for field_name, field_payload in accepted_delta.items():
            self._validate_delta_field_payload(
                field_name=field_name,
                field_payload=field_payload,
                expected_status="accepted",
                require_provenance=True,
            )
        for field_name, field_payload in rejected_delta.items():
            self._validate_delta_field_payload(
                field_name=field_name,
                field_payload=field_payload,
                expected_status="rejected",
                require_provenance=False,
            )

    def _validate_delta_field_payload(
        self,
        *,
        field_name: str,
        field_payload: Any,
        expected_status: str,
        require_provenance: bool,
    ) -> None:
        if not isinstance(field_name, str) or not field_name.strip():
            raise InvalidMutationError("delta field names must be non-empty strings")
        if not isinstance(field_payload, dict):
            raise InvalidMutationError(f"{expected_status}_delta.{field_name} must be a dict")
        if field_payload.get("status") != expected_status:
            raise InvalidMutationError(
                f"{expected_status}_delta.{field_name}.status must be {expected_status}"
            )
        if require_provenance and not str(field_payload.get("provenance") or "").strip():
            raise InvalidMutationError(
                f"{expected_status}_delta.{field_name}.provenance is required"
            )
        if not any(
            key in field_payload
            for key in ("proposed_value", "value", "raw_value", "canonical_value")
        ):
            raise InvalidMutationError(
                f"{expected_status}_delta.{field_name} must include a value"
            )
        if expected_status == "accepted":
            self._validate_accepted_critical_field_contract(field_name, field_payload)

    def _validate_accepted_critical_field_contract(
        self,
        field_name: str,
        field_payload: dict[str, Any],
    ) -> None:
        if not is_critical_technical_field(field_name):
            return
        engineering_value = field_payload.get("engineering_value")
        if not isinstance(engineering_value, dict):
            raise InvalidMutationError(
                f"accepted_delta.{field_name}.engineering_value is required for critical technical fields"
            )
        required_keys = {"raw_value", "canonical_value", "unit", "quantity_kind"}
        missing = sorted(
            key
            for key in required_keys
            if engineering_value.get(key) in (None, "")
        )
        if missing:
            raise InvalidMutationError(
                f"accepted_delta.{field_name}.engineering_value missing: {', '.join(missing)}"
            )
        if field_name in PRESSURE_FIELDS:
            payload_interpretation = str(
                engineering_value.get("interpretation") or ""
            ).strip()
            if payload_interpretation in {"", "unknown"}:
                raise InvalidMutationError(
                    f"accepted_delta.{field_name}.engineering_value.interpretation requires confirmation"
                )

    async def _validate_acceptance_against_latest_snapshot(
        self,
        *,
        case_id: str,
        payload: dict[str, Any],
    ) -> None:
        accepted_delta = _dict_or_empty(payload.get("accepted_delta"))
        if not accepted_delta:
            return

        latest = await self._latest_snapshot(case_id)
        if latest is None or not isinstance(latest.state_json, dict):
            return

        candidates = [
            ConflictCandidate(
                field_name=field_name,
                value=_delta_payload_value(field_payload),
                provenance=str(field_payload.get("provenance") or "unknown"),
                source_ref=_optional_string(field_payload.get("source_event_id")),
            )
            for field_name, field_payload in accepted_delta.items()
            if isinstance(field_payload, dict)
        ]
        result = ConflictDetectionService().detect(
            _conflict_detection_state_view(latest.state_json),
            candidates,
        )
        blocking_fields = {
            conflict.field_name
            for conflict in result.conflicts
            if conflict.severity == "blocking"
        }
        if not blocking_fields:
            return

        resolution = payload.get("conflict_resolution")
        resolved_fields: set[str] = set()
        if isinstance(resolution, dict):
            # Payload-local override for this mutation only: callers must list
            # blocking fields they intentionally accept despite the snapshot.
            raw_fields = resolution.get("accepted_fields")
            if isinstance(raw_fields, list):
                resolved_fields = {
                    str(field).strip()
                    for field in raw_fields
                    if str(field).strip()
                }

        unresolved = sorted(blocking_fields.difference(resolved_fields))
        if unresolved:
            raise InvalidMutationError(
                "accepted_delta conflicts with current case state; "
                f"explicit conflict_resolution.accepted_fields required for: {', '.join(unresolved)}"
            )

    def _validate_case_updates(
        self,
        case_updates: Any,
        *,
        payload_key: str = "case_updates",
    ) -> None:
        if not isinstance(case_updates, dict):
            raise InvalidMutationError(f"{payload_key} must be a dict")
        immutable_fields = {"case_number", "tenant_id", "user_id"}
        for field_name, value in case_updates.items():
            if field_name in immutable_fields:
                raise InvalidMutationError(
                    f"{field_name} cannot be changed through case_updates"
                )
            if value is None:
                raise InvalidMutationError(
                    f"{payload_key}.{field_name} cannot be None"
                )

    def _validate_snapshot_read_scope(self, *, case_number: str, user_id: str) -> None:
        if not case_number:
            raise InvalidMutationError("case_number is required")
        if not user_id:
            raise InvalidMutationError("user_id is required")

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


def _extract_mutation_audit_fields(payload: dict[str, Any]) -> dict[str, Any]:
    run_meta = payload.get("run_meta") if isinstance(payload.get("run_meta"), dict) else {}
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    return {
        "source_turn_id": _optional_string(payload.get("source_turn_id") or payload.get("turn_id")),
        "source_document_id": _optional_string(payload.get("source_document_id") or payload.get("document_id")),
        "proposed_delta": _dict_or_empty(payload.get("proposed_delta") or payload.get("proposed_case_delta")),
        "accepted_delta": _dict_or_empty(payload.get("accepted_delta")),
        "rejected_delta": _dict_or_empty(payload.get("rejected_delta")),
        "rejection_reasons": _dict_or_empty(payload.get("rejection_reasons")),
        "ruleset_version": _optional_string(
            payload.get("ruleset_version")
            or run_meta.get("ruleset_version")
            or snapshot.get("ruleset_version")
        ),
        "model_id": _optional_string(
            payload.get("model_id")
            or run_meta.get("model_id")
            or snapshot.get("model_id")
            or snapshot.get("model_version")
        ),
    }


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _conflict_detection_state_view(state_json: dict[str, Any]) -> dict[str, Any]:
    view = dict(state_json)

    normalized = state_json.get("normalized")
    if isinstance(normalized, dict):
        normalized_parameters = normalized.get("parameters")
        if isinstance(normalized_parameters, dict):
            view["parameters"] = {
                **normalized_parameters,
                **_dict_or_empty(view.get("parameters")),
            }

    asserted = state_json.get("asserted")
    if isinstance(asserted, dict):
        asserted_assertions = asserted.get("assertions")
        if isinstance(asserted_assertions, dict):
            view["assertions"] = {
                **asserted_assertions,
                **_dict_or_empty(view.get("assertions")),
            }

    return view


def _delta_payload_value(value: dict[str, Any]) -> Any:
    for key in ("proposed_value", "value", "raw_value", "canonical_value"):
        if key in value:
            return value[key]
    return None


def _delta_field_names(delta: dict[str, Any]) -> set[str]:
    fields = delta.get("fields")
    if isinstance(fields, list):
        return {
            str(item.get("field_name")).strip()
            for item in fields
            if isinstance(item, dict) and str(item.get("field_name")).strip()
        }
    return {str(field).strip() for field in delta if str(field).strip()}


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
