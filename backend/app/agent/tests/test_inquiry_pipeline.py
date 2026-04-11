"""
Tests for H1.3-H1.5 — Case management, Inquiry-Versand, Audit-Log.

Covers:
  - get_or_create_case()
  - _generate_case_number()
  - write_state_snapshot()
  - send_inquiry_payload() + IdempotencyError
"""
from __future__ import annotations

import re
import sys
import types
import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub heavy DB/ORM dependencies so unit tests don't need asyncpg
# ---------------------------------------------------------------------------

def _ensure_stubs() -> None:
    """Pre-populate sys.modules with minimal SQLAlchemy stub models.

    Only stubs the modules that transitively import asyncpg via app.database.
    sqlalchemy itself is real (installed) — only app.database is bypassed.
    """
    import sqlalchemy as _sa
    import sqlalchemy.orm as _orm

    # app.database stub — prevents asyncpg import error from create_async_engine
    if "app.database" not in sys.modules:
        _db_stub = types.ModuleType("app.database")
        _Base = _orm.declarative_base()
        _db_stub.Base = _Base  # type: ignore[attr-defined]
        _db_stub.AsyncSessionLocal = None  # type: ignore[attr-defined]
        sys.modules["app.database"] = _db_stub

    _Base = sys.modules["app.database"].Base  # type: ignore[attr-defined]

    if "app.models.case_record" not in sys.modules:
        class _CaseRecord(_Base):  # type: ignore[misc, valid-type]
            __tablename__ = "cases_stub"
            id = _sa.Column(_sa.String(36), primary_key=True)
            case_number = _sa.Column(_sa.String(50))
            session_id = _sa.Column(_sa.String(255))
            user_id = _sa.Column(_sa.String(255))
            status = _sa.Column(_sa.String(50))
            subsegment = _sa.Column(_sa.String(100), nullable=True)

        _stub = types.ModuleType("app.models.case_record")
        _stub.CaseRecord = _CaseRecord  # type: ignore[attr-defined]
        sys.modules["app.models.case_record"] = _stub

    if "app.models.case_state_snapshot" not in sys.modules:
        class _CaseStateSnapshot(_Base):  # type: ignore[misc, valid-type]
            __tablename__ = "case_state_snapshots_stub"
            id = _sa.Column(_sa.String(36), primary_key=True)
            case_id = _sa.Column(_sa.String(36))
            revision = _sa.Column(_sa.Integer())
            basis_hash = _sa.Column(_sa.String(32))
            state_json = _sa.Column(_sa.JSON())
            ontology_version = _sa.Column(_sa.String(100))
            prompt_version = _sa.Column(_sa.String(100))
            model_version = _sa.Column(_sa.String(100))

        _stub2 = types.ModuleType("app.models.case_state_snapshot")
        _stub2.CaseStateSnapshot = _CaseStateSnapshot  # type: ignore[attr-defined]
        sys.modules["app.models.case_state_snapshot"] = _stub2

    if "app.models.inquiry_delivery" not in sys.modules:
        class _InquiryDelivery(_Base):  # type: ignore[misc, valid-type]
            __tablename__ = "inquiry_deliveries_stub"
            id = _sa.Column(_sa.String(36), primary_key=True)
            case_id = _sa.Column(_sa.String(36))
            manufacturer_id = _sa.Column(_sa.String(100))
            payload_json = _sa.Column(_sa.JSON())
            idempotency_key = _sa.Column(_sa.String(255), unique=True)
            status = _sa.Column(_sa.String(50))
            delivered_at = _sa.Column(_sa.DateTime(timezone=True))
            created_at = _sa.Column(_sa.DateTime(timezone=True))

        _stub3 = types.ModuleType("app.models.inquiry_delivery")
        _stub3.InquiryDelivery = _InquiryDelivery  # type: ignore[attr-defined]
        sys.modules["app.models.inquiry_delivery"] = _stub3

    if "app.models.inquiry_audit" not in sys.modules:
        class _InquiryAudit(_Base):  # type: ignore[misc, valid-type]
            __tablename__ = "inquiry_audit_stub"
            id = _sa.Column(_sa.String(36), primary_key=True)
            case_id = _sa.Column(_sa.String(36))
            idempotency_key = _sa.Column(_sa.String(255), unique=True)
            decision_basis_hash = _sa.Column(_sa.String(32))
            pdf_url = _sa.Column(_sa.String(500))
            disclaimer_text = _sa.Column(_sa.String(1000))
            payload_json = _sa.Column(_sa.JSON())
            created_at = _sa.Column(_sa.DateTime(timezone=True))

        _stub4 = types.ModuleType("app.models.inquiry_audit")
        _stub4.InquiryAudit = _InquiryAudit  # type: ignore[attr-defined]
        sys.modules["app.models.inquiry_audit"] = _stub4


_ensure_stubs()


# ---------------------------------------------------------------------------
# DB session helpers
# ---------------------------------------------------------------------------

def _scalar_result(value: Any) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=value)
    r.scalar = MagicMock(return_value=value)
    return r


def _make_db_sequence(*results) -> MagicMock:
    """Async DB mock that returns given scalar values in sequence."""
    db = MagicMock()
    result_iter = iter(results)

    async def _execute(query):  # noqa: ARG001
        try:
            val = next(result_iter)
        except StopIteration:
            val = None
        return _scalar_result(val)

    db.execute = _execute
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


def _make_case(
    *,
    id: str | None = None,
    case_number: str = "STS-INQ-2026-04-001",
    session_id: str = "sess-123",
    user_id: str = "user-abc",
) -> MagicMock:
    case = MagicMock()
    case.id = id or str(uuid.uuid4())
    case.case_number = case_number
    case.session_id = session_id
    case.user_id = user_id
    case.status = "active"
    return case


def _make_snapshot(
    *,
    case_id: str = "case-1",
    revision: int = 1,
    basis_hash: str = "abc123def456789a",
    state_json: dict | None = None,
) -> MagicMock:
    snap = MagicMock()
    snap.case_id = case_id
    snap.revision = revision
    snap.basis_hash = basis_hash
    snap.state_json = state_json or {}
    return snap


def _make_delivery(
    *,
    case_id: str = "case-1",
    idempotency_key: str = "inquiry:case-1:mfr-1",
) -> MagicMock:
    d = MagicMock()
    d.case_id = case_id
    d.idempotency_key = idempotency_key
    d.status = "logged"
    return d


def _make_manufacturer(*, id: str = "mfr-1", slug: str = "testmaker") -> dict:
    return {
        "id": id,
        "slug": slug,
        "name": "Test Maker GmbH",
        "inquiry_config": {"contact": "info@testmaker.example"},
    }


def _make_state_for_payload() -> dict:
    return {
        "action_readiness": {
            "case_number": "STS-INQ-2026-04-001",
            "idempotency_key": "idem-test-123",
            "pdf_url": None,
        },
        "decision": {
            "decision_basis_hash": "abcd1234efgh5678",
            "preselection": {
                "material_combination": ["STS-MAT-FKM-A1"],
                "fit_score": 0.82,
            },
            "open_points": [],
            "assumptions": [],
        },
        "normalized": {
            "sealing_type": "STS-TYPE-RDGS-A1",
            "shaft_diameter_mm": 45.0,
            "temperature_max_c": 120.0,
            "pressure_max_bar": 6.0,
            "medium_canonical": "STS-MED-HYD-MINERAL",
        },
        "derived": {
            "requirement_class": "B",
            "applicable_norms": ["DIN3760"],
        },
    }


# ---------------------------------------------------------------------------
# H1.3 — get_or_create_case
# ---------------------------------------------------------------------------

class TestGetOrCreateCase:
    """Tests for get_or_create_case()."""

    @pytest.mark.asyncio
    async def test_returns_existing_case_when_found(self):
        """If a case with matching session_id exists, returns it without creating."""
        existing = _make_case(session_id="sess-abc")
        db = _make_db_sequence(existing)

        from app.agent.state.persistence import get_or_create_case

        result = await get_or_create_case("sess-abc", "user-1", db)

        assert result is existing
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_new_case_when_not_found(self):
        """When no case exists for session_id, a new CaseRecord is created."""
        db = _make_db_sequence(None, 0)

        from app.agent.state.persistence import get_or_create_case

        result = await get_or_create_case("sess-new", "user-42", db)

        assert result is not None
        assert hasattr(result, "case_number")
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_new_case_has_sts_inq_case_number(self):
        """Auto-generated case_number matches STS-INQ-YYYY-MM-NNN format."""
        db = _make_db_sequence(None, 0)

        from app.agent.state.persistence import get_or_create_case

        result = await get_or_create_case("sess-x", "u1", db)

        assert re.match(r"^STS-INQ-\d{4}-\d{2}-\d{3}$", result.case_number), (
            f"Bad case_number: {result.case_number}"
        )

    @pytest.mark.asyncio
    async def test_case_has_correct_session_and_user(self):
        """Created case carries the given session_id and user_id."""
        db = _make_db_sequence(None, 0)

        from app.agent.state.persistence import get_or_create_case

        result = await get_or_create_case("sess-unique", "user-xyz", db)

        assert result.session_id == "sess-unique"
        assert result.user_id == "user-xyz"

    @pytest.mark.asyncio
    async def test_idempotent_second_call_returns_existing(self):
        """Second call with same session_id returns the existing case."""
        existing = _make_case(session_id="sess-dup")
        db1 = _make_db_sequence(None, 0)
        db2 = _make_db_sequence(existing)

        from app.agent.state.persistence import get_or_create_case

        first = await get_or_create_case("sess-dup", "user-1", db1)
        second = await get_or_create_case("sess-dup", "user-1", db2)

        assert hasattr(first, "case_number")
        assert second is existing


# ---------------------------------------------------------------------------
# H1.3 — _generate_case_number
# ---------------------------------------------------------------------------

class TestGenerateCaseNumber:
    """Tests for _generate_case_number()."""

    @pytest.mark.asyncio
    async def test_first_case_in_month_is_001(self):
        """When no cases exist for current month, returns NNN=001."""
        db = _make_db_sequence(0)

        from app.agent.state.persistence import _generate_case_number

        result = await _generate_case_number(db)

        today = date.today()
        expected_prefix = f"STS-INQ-{today.year}-{today.month:02d}"
        assert result.startswith(expected_prefix)
        assert result.endswith("-001")

    @pytest.mark.asyncio
    async def test_sequential_numbering(self):
        """When 5 cases already exist this month, returns NNN=006."""
        db = _make_db_sequence(5)

        from app.agent.state.persistence import _generate_case_number

        result = await _generate_case_number(db)

        assert result.endswith("-006")

    @pytest.mark.asyncio
    async def test_format_is_stable(self):
        """Generated case_number always matches STS-INQ-YYYY-MM-NNN."""
        for n in (0, 1, 99):
            db = _make_db_sequence(n)

            from app.agent.state.persistence import _generate_case_number

            result = await _generate_case_number(db)

            assert re.match(r"^STS-INQ-\d{4}-\d{2}-\d{3}$", result), (
                f"Bad format for n={n}: {result}"
            )

    @pytest.mark.asyncio
    async def test_year_and_month_match_today(self):
        """Prefix uses today's year and zero-padded month."""
        db = _make_db_sequence(0)

        from app.agent.state.persistence import _generate_case_number

        result = await _generate_case_number(db)

        today = date.today()
        assert f"{today.year}-{today.month:02d}" in result


# ---------------------------------------------------------------------------
# H1.3 — write_state_snapshot
# ---------------------------------------------------------------------------

class TestWriteStateSnapshot:
    """Tests for write_state_snapshot()."""

    def _simple_state(self):
        from app.agent.state.models import GovernedSessionState

        return GovernedSessionState()

    @pytest.mark.asyncio
    async def test_creates_first_snapshot(self):
        """When no snapshot exists, creates revision 1."""
        state = self._simple_state()
        db = _make_db_sequence(None)

        _added = []
        orig_add = db.add

        def _track_add(obj):
            _added.append(obj)
            return orig_add(obj)

        db.add = _track_add

        from app.agent.state.persistence import write_state_snapshot

        await write_state_snapshot("case-xyz", state, db)

        assert len(_added) == 1
        assert _added[0].revision == 1
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dedup_skips_identical_snapshot(self):
        """If latest snapshot has same basis_hash and state_json, no new row is written."""
        from app.agent.state.persistence import (
            _with_decision_basis_hash,
            compute_decision_basis_hash,
        )

        state = self._simple_state()
        persisted = _with_decision_basis_hash(state)
        basis_hash = compute_decision_basis_hash(persisted)
        state_json = persisted.model_dump(mode="json")

        existing_snap = _make_snapshot(basis_hash=basis_hash, state_json=state_json)
        db = _make_db_sequence(existing_snap)

        from app.agent.state.persistence import write_state_snapshot

        result = await write_state_snapshot("case-xyz", state, db)

        db.add.assert_not_called()
        db.commit.assert_not_awaited()
        assert result is existing_snap

    @pytest.mark.asyncio
    async def test_increments_revision(self):
        """When a snapshot already exists with different content, next revision = existing + 1."""
        state = self._simple_state()
        existing_snap = _make_snapshot(revision=3, basis_hash="old_hash_different_zzz")
        db = _make_db_sequence(existing_snap)

        _added = []
        orig_add = db.add

        def _track_add(obj):
            _added.append(obj)

        db.add = _track_add

        from app.agent.state.persistence import write_state_snapshot

        await write_state_snapshot("case-xyz", state, db)

        assert len(_added) == 1
        assert _added[0].revision == 4

    @pytest.mark.asyncio
    async def test_snapshot_carries_basis_hash(self):
        """Written snapshot includes computed basis_hash."""
        from app.agent.state.persistence import compute_decision_basis_hash

        state = self._simple_state()
        expected_hash = compute_decision_basis_hash(state)
        db = _make_db_sequence(None)

        _added = []
        db.add = MagicMock(side_effect=_added.append)

        from app.agent.state.persistence import write_state_snapshot

        await write_state_snapshot("case-abc", state, db)

        assert _added[0].basis_hash == expected_hash


# ---------------------------------------------------------------------------
# H1.4 — send_inquiry_payload
# ---------------------------------------------------------------------------

class TestSendInquiryPayload:
    """Tests for send_inquiry_payload()."""

    @pytest.mark.asyncio
    async def test_writes_delivery_and_audit_on_success(self):
        """Happy path: InquiryDelivery + InquiryAudit both written."""
        state = _make_state_for_payload()
        manufacturer = _make_manufacturer()
        db = _make_db_sequence(None)

        _added = []
        db.add = MagicMock(side_effect=_added.append)

        from app.agent.manufacturers.payload_builder import send_inquiry_payload

        await send_inquiry_payload(state, manufacturer, "case-1", db)

        assert db.add.call_count == 2
        assert hasattr(_added[0], "idempotency_key")    # InquiryDelivery
        assert hasattr(_added[1], "decision_basis_hash")  # InquiryAudit
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_idempotency_error_if_delivery_exists(self):
        """If DB has existing delivery with same idempotency_key, raises IdempotencyError."""
        state = _make_state_for_payload()
        manufacturer = _make_manufacturer()
        existing_delivery = _make_delivery(case_id="case-1")
        db = _make_db_sequence(existing_delivery)

        from app.agent.manufacturers.payload_builder import IdempotencyError, send_inquiry_payload

        with pytest.raises(IdempotencyError):
            await send_inquiry_payload(state, manufacturer, "case-1", db)

    @pytest.mark.asyncio
    async def test_raises_idempotency_error_if_redis_key_exists(self):
        """If Redis has existing key, raises IdempotencyError before DB check."""
        state = _make_state_for_payload()
        manufacturer = _make_manufacturer()
        db = _make_db_sequence(None)

        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=b"sent")

        from app.agent.manufacturers.payload_builder import IdempotencyError, send_inquiry_payload

        with pytest.raises(IdempotencyError):
            await send_inquiry_payload(state, manufacturer, "case-1", db, redis_client)

    @pytest.mark.asyncio
    async def test_sets_redis_key_on_success(self):
        """After successful send, Redis key is set with 7-day TTL."""
        state = _make_state_for_payload()
        manufacturer = _make_manufacturer()
        db = _make_db_sequence(None)

        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)
        redis_client.setex = AsyncMock()

        from app.agent.manufacturers.payload_builder import send_inquiry_payload

        await send_inquiry_payload(state, manufacturer, "case-1", db, redis_client)

        redis_client.setex.assert_awaited_once()
        call_args = redis_client.setex.call_args[0]
        ttl = call_args[1]
        assert ttl == 86400 * 7

    @pytest.mark.asyncio
    async def test_proceeds_when_redis_unavailable(self):
        """If Redis raises on get(), falls through to DB check without error."""
        state = _make_state_for_payload()
        manufacturer = _make_manufacturer()
        db = _make_db_sequence(None)

        redis_client = AsyncMock()
        redis_client.get = AsyncMock(side_effect=ConnectionError("redis down"))
        redis_client.setex = AsyncMock(side_effect=ConnectionError("redis down"))

        from app.agent.manufacturers.payload_builder import send_inquiry_payload

        await send_inquiry_payload(state, manufacturer, "case-1", db, redis_client)

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_idempotency_key_format(self):
        """Idempotency key is 'inquiry:{case_id}:{manufacturer_id}'."""
        state = _make_state_for_payload()
        manufacturer = _make_manufacturer(id="mfr-42")
        db = _make_db_sequence(None)

        _setex_calls: list[tuple] = []

        redis_client = AsyncMock()
        redis_client.get = AsyncMock(return_value=None)

        async def _setex(*args):
            _setex_calls.append(args)

        redis_client.setex = _setex

        from app.agent.manufacturers.payload_builder import send_inquiry_payload

        await send_inquiry_payload(state, manufacturer, "case-7", db, redis_client)

        assert len(_setex_calls) == 1
        key = _setex_calls[0][0]
        assert key == "inquiry:case-7:mfr-42"

    @pytest.mark.asyncio
    async def test_delivery_has_logged_status(self):
        """Created InquiryDelivery gets status='logged' (pilot logging-only mode)."""
        state = _make_state_for_payload()
        manufacturer = _make_manufacturer()
        db = _make_db_sequence(None)

        _added = []
        db.add = MagicMock(side_effect=_added.append)

        from app.agent.manufacturers.payload_builder import send_inquiry_payload

        await send_inquiry_payload(state, manufacturer, "case-1", db)

        delivery = _added[0]
        assert delivery.status == "logged"

    @pytest.mark.asyncio
    async def test_audit_carries_disclaimer(self):
        """Created InquiryAudit has disclaimer_text from INQUIRY_DISCLAIMER."""
        state = _make_state_for_payload()
        manufacturer = _make_manufacturer()
        db = _make_db_sequence(None)

        _added = []
        db.add = MagicMock(side_effect=_added.append)

        from app.agent.manufacturers.payload_builder import INQUIRY_DISCLAIMER, send_inquiry_payload

        await send_inquiry_payload(state, manufacturer, "case-1", db)

        audit = _added[1]
        assert audit.disclaimer_text == INQUIRY_DISCLAIMER


# ---------------------------------------------------------------------------
# H1.4 — IdempotencyError
# ---------------------------------------------------------------------------

class TestIdempotencyError:
    """IdempotencyError is a distinct exception type."""

    def test_is_exception(self):
        from app.agent.manufacturers.payload_builder import IdempotencyError

        assert issubclass(IdempotencyError, Exception)

    def test_carries_message(self):
        from app.agent.manufacturers.payload_builder import IdempotencyError

        err = IdempotencyError("duplicate key xyz")
        assert "duplicate key xyz" in str(err)

    def test_caught_by_idempotency_error_handler(self):
        from app.agent.manufacturers.payload_builder import IdempotencyError

        caught = False
        try:
            raise IdempotencyError("test")
        except IdempotencyError:
            caught = True
        assert caught

    def test_not_subclass_of_value_error(self):
        from app.agent.manufacturers.payload_builder import IdempotencyError

        assert not issubclass(IdempotencyError, ValueError)


# ---------------------------------------------------------------------------
# E2E smoke test
# ---------------------------------------------------------------------------

class TestInquiryPipelineSmoke:
    """Lightweight E2E smoke test: admissibility → payload → idempotency."""

    def test_admissibility_then_payload_round_trip(self):
        """Verified state passes admissibility and produces a valid payload."""
        from app.agent.domain.admissibility import check_inquiry_admissibility
        from app.agent.manufacturers.payload_builder import build_inquiry_payload
        from app.agent.state.models import (
            DecisionState,
            DerivedState,
            GovernedSessionState,
            NormalizedParameter,
            NormalizedState,
        )

        manufacturer = _make_manufacturer()
        params = {
            "sealing_type": NormalizedParameter(field_name="sealing_type", value="STS-TYPE-RDGS-A1"),
            "shaft_diameter_mm": NormalizedParameter(
                field_name="shaft_diameter_mm", value=45.0, unit="mm"
            ),
            "temperature_max_c": NormalizedParameter(
                field_name="temperature_max_c", value=120.0, unit="°C"
            ),
            "pressure_max_bar": NormalizedParameter(
                field_name="pressure_max_bar", value=6.0, unit="bar"
            ),
            "medium": NormalizedParameter(
                field_name="medium", value="STS-MED-HYD-MINERAL"
            ),
        }
        normalized = NormalizedState(parameters=params)
        derived = DerivedState()
        decision = DecisionState(
            preselection={"material_combination": ["STS-MAT-FKM-A1"], "fit_score": 0.82},
            decision_basis_hash="abcd1234efgh5678",
        )
        state = GovernedSessionState(normalized=normalized, derived=derived, decision=decision)

        result = check_inquiry_admissibility(state)
        assert result.admissible, f"Expected admissible=True, got: {result.blocking_reasons}"

        payload = build_inquiry_payload(state, manufacturer)
        assert payload["sealai_version"] == "sealai_inquiry_v1"
        assert payload["basis_hash"]
        assert payload["recipient"]["manufacturer_id"] == "mfr-1"
        assert payload["fit_score"] == 0.82

    def test_incomplete_state_fails_admissibility(self):
        """State missing mandatory fields → not admissible."""
        from app.agent.domain.admissibility import check_inquiry_admissibility
        from app.agent.state.models import GovernedSessionState, NormalizedState

        state = GovernedSessionState(normalized=NormalizedState())
        result = check_inquiry_admissibility(state)
        assert not result.admissible
        assert len(result.blocking_reasons) > 0

    def test_build_inquiry_payload_from_flat(self):
        """build_inquiry_payload_from_flat() returns a well-formed payload."""
        from app.agent.manufacturers.payload_builder import build_inquiry_payload_from_flat

        payload = build_inquiry_payload_from_flat(
            case_number="STS-INQ-2026-04-001",
            basis_hash="abc123",
            sealing_type="STS-TYPE-RDGS-A1",
            material_combination=["STS-MAT-FKM-A1"],
            shaft_diameter_mm=45.0,
            temperature_max_c=120.0,
            pressure_max_bar=6.0,
            medium_canonical="STS-MED-HYD-MINERAL",
            fit_score=0.85,
            applicable_norms=["DIN3760"],
            manufacturer=_make_manufacturer(),
        )
        assert payload["sealai_version"] == "sealai_inquiry_v1"
        assert payload["case_number"] == "STS-INQ-2026-04-001"
        assert payload["basis_hash"] == "abc123"
        assert payload["requirements"]["sealing_type"] == "STS-TYPE-RDGS-A1"
        assert payload["requirements"]["shaft_diameter_mm"] == 45.0
        assert payload["fit_score"] == 0.85
        assert "disclaimer" in payload
