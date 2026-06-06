"""Tenant-scoped persistence for V1.8 §6.5 Outcome-Records (the moat).

Raw outcomes are strictly tenant-scoped (§4.3/§8): ``tenant_id`` is a mandatory
parameter on every read and write — there is no API without it (mirrors the
``CaseService._require_tenant_id`` discipline, SEC-01). Cross-tenant reads return
nothing; they never leak another tenant's field data.

Thin SQL repository over the ``outcome_records`` table (migration d1e2f3a4b5c6).
Aggregation into anonymized global richtwerte (§8) is a later patch and is the
*only* path by which outcomes leave the tenant scope.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.agent.state.models import OutcomeRecord


class OutcomeRecordPersistenceError(ValueError):
    """Raised when a required tenant scope is missing."""


def _require_tenant_id(tenant_id: str | None) -> str:
    value = str(tenant_id or "").strip()
    if not value:
        raise OutcomeRecordPersistenceError("tenant_id is required")
    return value


_INSERT = text(
    """
    INSERT INTO outcome_records (
        outcome_id, case_id, tenant_id, position_id, solution_ref, event,
        installed_at, runtime_hours_estimate, outcome_pattern, suspected_cause,
        evidence_refs, confidence
    ) VALUES (
        :outcome_id, :case_id, :tenant_id, :position_id, :solution_ref, :event,
        :installed_at, :runtime_hours_estimate, :outcome_pattern,
        :suspected_cause, CAST(:evidence_refs AS jsonb), :confidence
    )
    """
)

_SELECT_BY_TENANT = text(
    """
    SELECT case_id, tenant_id, position_id, solution_ref, event, installed_at,
           runtime_hours_estimate, outcome_pattern, suspected_cause,
           evidence_refs, confidence
    FROM outcome_records
    WHERE tenant_id = :tenant_id
    ORDER BY created_at
    """
)


def save_outcome_record(
    conn: Connection, *, tenant_id: str, record: OutcomeRecord
) -> str:
    """Persist one outcome under the given tenant. Returns the new outcome_id.

    The ``tenant_id`` parameter is authoritative — it overrides any tenant_id on
    the record, so a caller can never write into another tenant's scope.
    """
    tid = _require_tenant_id(tenant_id)
    outcome_id = str(uuid.uuid4())
    conn.execute(
        _INSERT,
        {
            "outcome_id": outcome_id,
            "case_id": record.case_id or None,
            "tenant_id": tid,
            "position_id": record.position_id,
            "solution_ref": record.solution_ref,
            "event": record.event,
            "installed_at": record.installed_at,
            "runtime_hours_estimate": record.runtime_hours_estimate,
            "outcome_pattern": record.outcome_pattern,
            "suspected_cause": record.suspected_cause,
            "evidence_refs": json.dumps(list(record.evidence_refs or [])),
            "confidence": record.confidence,
        },
    )
    return outcome_id


def list_outcome_records_for_tenant(
    conn: Connection, *, tenant_id: str
) -> list[OutcomeRecord]:
    """All outcomes owned by ``tenant_id`` (never another tenant's)."""
    tid = _require_tenant_id(tenant_id)
    rows = conn.execute(_SELECT_BY_TENANT, {"tenant_id": tid}).mappings().all()
    return [_row_to_record(row) for row in rows]


def _row_to_record(row: Any) -> OutcomeRecord:
    evidence = row["evidence_refs"]
    if isinstance(evidence, str):
        evidence = json.loads(evidence or "[]")
    return OutcomeRecord(
        case_id=row["case_id"] or "",
        tenant_id=row["tenant_id"],
        position_id=row["position_id"],
        solution_ref=row["solution_ref"],
        event=row["event"],
        installed_at=row["installed_at"],
        runtime_hours_estimate=row["runtime_hours_estimate"],
        outcome_pattern=row["outcome_pattern"],
        suspected_cause=row["suspected_cause"],
        evidence_refs=list(evidence or []),
        confidence=row["confidence"],
    )
