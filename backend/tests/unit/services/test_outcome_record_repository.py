"""Tenant-scoping tests for the OutcomeRecord repository (V1.8 §6.5 / AC16)."""

import pytest

from app.agent.state.models import OutcomeRecord
from app.services.outcome_record_repository import (
    OutcomeRecordPersistenceError,
    list_outcome_records_for_tenant,
    save_outcome_record,
)


def _record(**kw) -> OutcomeRecord:
    base = dict(
        case_id="case_1",
        position_id="pos_1",
        solution_ref="sol_01",
        event="incident",
        outcome_pattern="lip_hardening_thermal",
        suspected_cause="temp_peaks_above_continuous_limit",
        evidence_refs=["photo_88"],
        confidence="medium",
    )
    base.update(kw)
    return OutcomeRecord(**base)


def test_save_and_list_round_trip(test_db_engine_at_head):
    with test_db_engine_at_head.begin() as conn:
        save_outcome_record(conn, tenant_id="tenant-a", record=_record())
        records = list_outcome_records_for_tenant(conn, tenant_id="tenant-a")
        conn.execute(_cleanup())
    assert len(records) == 1
    got = records[0]
    assert got.tenant_id == "tenant-a"
    assert got.outcome_pattern == "lip_hardening_thermal"
    assert got.evidence_refs == ["photo_88"]
    assert got.suspected_cause == "temp_peaks_above_continuous_limit"


def test_tenant_isolation_no_cross_tenant_leak(test_db_engine_at_head):
    with test_db_engine_at_head.begin() as conn:
        save_outcome_record(conn, tenant_id="tenant-a", record=_record())
        # another tenant sees nothing
        other = list_outcome_records_for_tenant(conn, tenant_id="tenant-b")
        own = list_outcome_records_for_tenant(conn, tenant_id="tenant-a")
        conn.execute(_cleanup())
    assert other == []
    assert len(own) == 1


def test_tenant_id_param_overrides_record_tenant(test_db_engine_at_head):
    # a record claiming another tenant is still written under the authoritative arg
    with test_db_engine_at_head.begin() as conn:
        save_outcome_record(
            conn, tenant_id="tenant-a", record=_record(tenant_id="tenant-evil")
        )
        leaked = list_outcome_records_for_tenant(conn, tenant_id="tenant-evil")
        own = list_outcome_records_for_tenant(conn, tenant_id="tenant-a")
        conn.execute(_cleanup())
    assert leaked == []
    assert len(own) == 1


def test_requires_tenant_id(test_db_engine_at_head):
    with test_db_engine_at_head.begin() as conn:
        with pytest.raises(OutcomeRecordPersistenceError):
            save_outcome_record(conn, tenant_id="", record=_record())
        with pytest.raises(OutcomeRecordPersistenceError):
            list_outcome_records_for_tenant(conn, tenant_id="  ")


def _cleanup():
    from sqlalchemy import text

    return text("DELETE FROM outcome_records WHERE tenant_id LIKE 'tenant-%'")
