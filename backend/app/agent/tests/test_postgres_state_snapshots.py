from __future__ import annotations

import os
import sys
import types
import uuid
import json
from dataclasses import dataclass
from unittest.mock import patch

import pytest

for key, value in {
    "postgres_user": "test",
    "postgres_password": "test",
    "postgres_host": "localhost",
    "postgres_port": "5432",
    "postgres_db": "test",
    "database_url": "sqlite+aiosqlite:///tmp.db",
    "POSTGRES_SYNC_URL": "sqlite:///tmp.db",
    "openai_api_key": "test",
    "qdrant_url": "http://localhost",
    "redis_url": "redis://localhost:6379/0",
    "nextauth_url": "http://localhost",
    "nextauth_secret": "secret",
    "keycloak_issuer": "http://localhost",
    "keycloak_jwks_url": "http://localhost/jwks",
    "keycloak_client_id": "client",
    "keycloak_client_secret": "secret",
    "keycloak_expected_azp": "client",
}.items():
    os.environ.setdefault(key, value)

from app.agent.api import router as router_module
from app.agent.api import loaders as loaders_module
from app.agent.api.routes import workspace as workspace_routes
from app.agent.state.models import (
    DerivedState,
    EvidenceState,
    GovernanceState,
    GovernedPersistenceMarker,
    GovernedSessionState,
    NormalizedParameter,
    NormalizedState,
    RfqState,
    SealaiNormIdentity,
    SealaiNormMaterial,
    SealaiNormState,
)
from app.agent.state.persistence import (
    REASONING_PROMPT_VERSION,
    get_case_by_number_async,
    get_governed_case_snapshot_by_revision_async,
    get_latest_governed_case_snapshot_async,
    list_cases_async,
    list_governed_case_snapshots_async,
    save_governed_state_snapshot_async,
)
from app.services.auth.dependencies import RequestUser


def _state(
    *,
    analysis_cycle: int,
    medium: str = "Wasser",
    inquiry_admissible: bool = False,
    rfq_ready: bool = False,
    material_family: str | None = None,
    sealing_material_family: str | None = None,
    engineering_path: str | None = None,
) -> GovernedSessionState:
    return GovernedSessionState(
        normalized=NormalizedState.model_validate(
            {
                "parameters": {
                    "medium": NormalizedParameter(
                        field_name="medium",
                        value=medium,
                        confidence="confirmed",
                        source="llm",
                    )
                },
                "parameter_status": {"medium": "observed"},
            }
        ),
        derived=DerivedState(
            pv_value=0.39,
            velocity=2.5,
            field_status={"pv_value": "derived", "velocity": "derived"},
        ),
        evidence=EvidenceState(source_versions={"doc-1": "abc123"}),
        governance=GovernanceState(rfq_admissible=inquiry_admissible),
        rfq=RfqState(rfq_ready=rfq_ready),
        sealai_norm=SealaiNormState(
            identity=SealaiNormIdentity(engineering_path=engineering_path),
            material=SealaiNormMaterial(
                material_family=material_family,
                sealing_material_family=sealing_material_family,
            )
        ),
        analysis_cycle=analysis_cycle,
    )


class _Attr:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def desc(self):
        return ("desc", self.name)


class _Select:
    def __init__(self, target):
        self.target = target
        self.filters = []
        self.order = None
        self.limit_value = None

    def where(self, condition):
        self.filters.append(condition)
        return self

    def order_by(self, order):
        self.order = order
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self


class _ScalarProxy:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class _Result:
    def __init__(self, items):
        self._items = list(items)

    def scalar_one_or_none(self):
        if not self._items:
            return None
        return self._items[0]

    def scalar_one(self):
        if len(self._items) != 1:
            raise AssertionError(f"expected exactly one row, got {len(self._items)}")
        return self._items[0]

    def scalars(self):
        return _ScalarProxy(self._items)


@dataclass
class _Store:
    cases: list
    snapshots: list


class _FakeCaseRecord:
    case_number = _Attr("case_number")
    user_id = _Attr("user_id")
    updated_at = _Attr("updated_at")

    def __init__(
        self,
        *,
        case_number,
        user_id,
        subsegment=None,
        status="active",
        tenant_id=None,
        id=None,
        updated_at=None,
        case_revision=0,
        inquiry_admissible=False,
        rfq_ready=False,
    ):
        self.id = id or str(uuid.uuid4())
        self.case_number = case_number
        self.user_id = user_id
        self.subsegment = subsegment
        self.status = status
        self.tenant_id = tenant_id
        self.updated_at = updated_at or f"updated:{case_number}"
        self.case_revision = case_revision
        self.inquiry_admissible = inquiry_admissible
        self.rfq_ready = rfq_ready


class _FakeCaseStateSnapshot:
    case_id = _Attr("case_id")
    revision = _Attr("revision")

    def __init__(
        self,
        *,
        case_id,
        revision,
        state_json,
        basis_hash,
        ontology_version,
        prompt_version,
        model_version,
        id=None,
    ):
        self.id = id or str(uuid.uuid4())
        self.case_id = case_id
        self.revision = revision
        self.state_json = state_json
        self.basis_hash = basis_hash
        self.ontology_version = ontology_version
        self.prompt_version = prompt_version
        self.model_version = model_version


class _FakeSession:
    def __init__(self, store: _Store):
        self._store = store

    async def execute(self, query):
        if query.target is _FakeCaseRecord:
            items = list(self._store.cases)
        elif query.target is _FakeCaseStateSnapshot:
            items = list(self._store.snapshots)
        else:
            raise AssertionError(f"unexpected query target: {query.target}")

        for operator, field_name, expected in query.filters:
            if operator != "eq":
                raise AssertionError(f"unexpected operator: {operator}")
            items = [item for item in items if getattr(item, field_name) == expected]

        if query.order is not None:
            direction, field_name = query.order
            reverse = direction == "desc"
            items = sorted(items, key=lambda item: getattr(item, field_name), reverse=reverse)

        if query.limit_value is not None:
            items = items[: query.limit_value]

        return _Result(items)

    def add(self, item):
        if isinstance(item, _FakeCaseRecord):
            self._store.cases.append(item)
        elif isinstance(item, _FakeCaseStateSnapshot):
            self._store.snapshots.append(item)
        else:
            raise AssertionError(f"unexpected item type: {type(item)!r}")

    async def flush(self):
        return None

    async def commit(self):
        return None


class _FakeSessionContext:
    def __init__(self, store: _Store):
        self._store = store

    async def __aenter__(self):
        return _FakeSession(self._store)

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _fake_select(target):
    return _Select(target)


class _FakeCaseService:
    def __init__(self, session: _FakeSession):
        self._session = session

    async def create_case(
        self,
        *,
        case_number,
        user_id,
        actor,
        session_id=None,
        subsegment=None,
        status="active",
        tenant_id=None,
        state_json=None,
        basis_hash=None,
        ontology_version=None,
        prompt_version=None,
        model_version=None,
        case_updates=None,
    ):
        if tenant_id is None:
            raise AssertionError("tenant_id is required")
        case_row = _FakeCaseRecord(
            case_number=case_number,
            user_id=user_id,
            subsegment=subsegment,
            status=status,
            tenant_id=tenant_id,
            case_revision=1,
        )
        for field_name, value in (case_updates or {}).items():
            setattr(case_row, field_name, value)
        self._session._store.cases.append(case_row)
        self._session._store.snapshots.append(
            _FakeCaseStateSnapshot(
                case_id=case_row.id,
                revision=1,
                state_json=state_json or {},
                basis_hash=basis_hash,
                ontology_version=ontology_version,
                prompt_version=prompt_version,
                model_version=model_version,
            )
        )
        return case_row

    async def write_snapshot(
        self,
        *,
        case_id,
        state_json,
        actor,
        basis_hash=None,
        ontology_version=None,
        prompt_version=None,
        model_version=None,
        case_updates=None,
    ):
        immutable_fields = {"case_number", "tenant_id", "user_id"}
        forbidden = immutable_fields.intersection(case_updates or {})
        if forbidden:
            raise AssertionError(f"immutable case_updates passed: {sorted(forbidden)}")
        case_row = next(case for case in self._session._store.cases if case.id == case_id)
        latest = next(
            (
                snapshot
                for snapshot in sorted(
                    self._session._store.snapshots,
                    key=lambda item: item.revision,
                    reverse=True,
                )
                if snapshot.case_id == case_id
            ),
            None,
        )
        if latest is not None and latest.basis_hash == basis_hash and latest.state_json == state_json:
            return latest
        for field_name, value in (case_updates or {}).items():
            setattr(case_row, field_name, value)
        case_row.case_revision += 1
        snapshot = _FakeCaseStateSnapshot(
            case_id=case_id,
            revision=case_row.case_revision,
            state_json=state_json,
            basis_hash=basis_hash,
            ontology_version=ontology_version,
            prompt_version=prompt_version,
            model_version=model_version,
        )
        self._session._store.snapshots.append(snapshot)
        return snapshot

    async def get_snapshot_by_revision_for_case_number(
        self,
        *,
        case_number,
        revision,
        user_id=None,
    ):
        case_row = next(
            (
                case
                for case in self._session._store.cases
                if case.case_number == case_number
                and (user_id is None or case.user_id == user_id)
            ),
            None,
        )
        if case_row is None:
            return None
        snapshots = [
            snapshot
            for snapshot in self._session._store.snapshots
            if snapshot.case_id == case_row.id
        ]
        if revision is not None:
            snapshots = [snapshot for snapshot in snapshots if snapshot.revision == revision]
        else:
            snapshots = sorted(snapshots, key=lambda item: item.revision, reverse=True)
        if not snapshots:
            return None
        return case_row, snapshots[0]

    async def get_latest_snapshot_for_case_number(
        self,
        *,
        case_number,
        user_id=None,
    ):
        return await self.get_snapshot_by_revision_for_case_number(
            case_number=case_number,
            revision=None,
            user_id=user_id,
        )

    async def list_snapshot_revisions_for_case_number(
        self,
        *,
        case_number,
        user_id=None,
        limit=50,
    ):
        case_row = next(
            (
                case
                for case in self._session._store.cases
                if case.case_number == case_number
                and (user_id is None or case.user_id == user_id)
            ),
            None,
        )
        if case_row is None:
            return []
        snapshots = [
            snapshot
            for snapshot in self._session._store.snapshots
            if snapshot.case_id == case_row.id
        ]
        return sorted(snapshots, key=lambda item: item.revision, reverse=True)[:limit]

    async def get_latest_snapshot_revision_for_case_id(self, case_id):
        snapshots = [
            snapshot
            for snapshot in self._session._store.snapshots
            if snapshot.case_id == case_id
        ]
        if not snapshots:
            return None
        return int(max(snapshot.revision for snapshot in snapshots))


def _install_fake_snapshot_backend():
    store = _Store(cases=[], snapshots=[])
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: _FakeSessionContext(store))
    fake_case_models = types.SimpleNamespace(CaseRecord=_FakeCaseRecord)
    fake_snapshot_models = types.SimpleNamespace(CaseStateSnapshot=_FakeCaseStateSnapshot)
    fake_case_service = types.SimpleNamespace(CaseService=_FakeCaseService)
    return store, {
        "app.database": fake_db,
        "app.models.case_record": fake_case_models,
        "app.models.case_state_snapshot": fake_snapshot_models,
        "app.services.case_service": fake_case_service,
    }


def test_governed_state_can_carry_snapshot_persistence_marker() -> None:
    state = GovernedSessionState(
        persistence_marker=GovernedPersistenceMarker(
            snapshot_comparable=True,
            postgres_snapshot_revision=4,
            postgres_case_revision=4,
        )
    )

    payload = state.model_dump(mode="json")
    restored = GovernedSessionState.model_validate(payload)

    assert restored.persistence_marker is not None
    assert restored.persistence_marker.snapshot_comparable is True
    assert restored.persistence_marker.postgres_snapshot_revision == 4
    assert restored.persistence_marker.postgres_case_revision == 4


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_creates_case_and_snapshot() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        result = await save_governed_state_snapshot_async(
            _state(analysis_cycle=2),
            case_number="case-123",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert len(store.cases) == 1
    assert len(store.snapshots) == 1
    case_row = store.cases[0]
    snapshot = store.snapshots[0]
    assert case_row.case_number == "case-123"
    assert case_row.user_id == "user-1"
    assert case_row.tenant_id == "tenant-1"
    assert snapshot.revision == 1
    assert snapshot.case_id == case_row.id
    assert snapshot.state_json["analysis_cycle"] == 2
    assert snapshot.basis_hash
    assert snapshot.ontology_version == "sealai_norm_v1"
    assert snapshot.prompt_version == REASONING_PROMPT_VERSION
    assert snapshot.model_version == "gpt-4o-mini"
    assert result is not None
    assert result.case_id == case_row.id
    assert result.case_number == "case-123"
    assert result.postgres_snapshot_revision == 1
    assert result.postgres_case_revision == 1
    assert result.basis_hash == snapshot.basis_hash


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_is_idempotent_for_same_state() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        state = _state(analysis_cycle=1)
        first = await save_governed_state_snapshot_async(
            state,
            case_number="case-dup",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        second = await save_governed_state_snapshot_async(
            state,
            case_number="case-dup",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert len(store.cases) == 1
    assert len(store.snapshots) == 1
    assert first is not None
    assert second is not None
    assert first.postgres_snapshot_revision == 1
    assert second.postgres_snapshot_revision == 1


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_advances_revision_when_cycle_stalls() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-rev",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, medium="Dampf"),
            case_number="case-rev",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert [snapshot.revision for snapshot in store.snapshots] == [1, 2]


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_updates_case_readiness_fields() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-readiness",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=2, inquiry_admissible=True, rfq_ready=True),
            case_number="case-readiness",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    case_row = store.cases[0]
    assert case_row.inquiry_admissible is True
    assert case_row.rfq_ready is True


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_persists_false_readiness_fields() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, inquiry_admissible=True, rfq_ready=True),
            case_number="case-readiness-false",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=2, medium="Dampf", inquiry_admissible=False, rfq_ready=False),
            case_number="case-readiness-false",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    case_row = store.cases[0]
    assert case_row.inquiry_admissible is False
    assert case_row.rfq_ready is False


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_sets_explicit_pre_gate_on_new_case() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-pre-gate-new",
            user_id="user-1",
            tenant_id="tenant-1",
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    assert store.cases[0].pre_gate_classification == "DOMAIN_INQUIRY"


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_updates_explicit_pre_gate_on_existing_case() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-pre-gate-existing",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=2, medium="Dampf"),
            case_number="case-pre-gate-existing",
            user_id="user-1",
            tenant_id="tenant-1",
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    assert store.cases[0].pre_gate_classification == "DOMAIN_INQUIRY"


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_does_not_invent_pre_gate_without_source() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-no-pre-gate-source",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert "pre_gate_classification" not in vars(store.cases[0])


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_only_mirrors_explicit_pre_gate_field() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, inquiry_admissible=True, rfq_ready=True),
            case_number="case-pre-gate-only",
            user_id="user-1",
            tenant_id="tenant-1",
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    case_fields = vars(store.cases[0])
    assert case_fields["pre_gate_classification"] == "DOMAIN_INQUIRY"
    assert "inquiry_admissible" in case_fields
    assert "rfq_ready" in case_fields
    for field_name in (
        "request_type",
        "engineering_path",
        "sealing_material_family",
        "application_pattern_id",
        "payload",
    ):
        assert field_name not in case_fields


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_sets_authority_sealing_material_family_on_new_case() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, sealing_material_family="ptfe_glass_filled"),
            case_number="case-material-new",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert store.cases[0].sealing_material_family == "ptfe_glass_filled"


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_updates_authority_sealing_material_family_on_existing_case() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-material-existing",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=2, sealing_material_family="elastomer_fkm"),
            case_number="case-material-existing",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert store.cases[0].sealing_material_family == "elastomer_fkm"


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_does_not_write_empty_sealing_material_family() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, sealing_material_family=None),
            case_number="case-material-none",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert "sealing_material_family" not in vars(store.cases[0])


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_does_not_fallback_to_generic_material_hint() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, material_family="PTFE"),
            case_number="case-material-generic",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert "sealing_material_family" not in vars(store.cases[0])


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_keeps_readiness_mirror_with_sealing_material_family() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(
                analysis_cycle=1,
                inquiry_admissible=True,
                rfq_ready=True,
                sealing_material_family="ptfe_carbon_filled",
            ),
            case_number="case-material-readiness",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    case_row = store.cases[0]
    assert case_row.sealing_material_family == "ptfe_carbon_filled"
    assert case_row.inquiry_admissible is True
    assert case_row.rfq_ready is True


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_sets_authority_engineering_path_on_new_case() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, engineering_path="rwdr"),
            case_number="case-engineering-path-new",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert store.cases[0].engineering_path == "rwdr"


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_updates_authority_engineering_path_on_existing_case() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-engineering-path-existing",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=2, engineering_path="ms_pump"),
            case_number="case-engineering-path-existing",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert store.cases[0].engineering_path == "ms_pump"


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_does_not_write_empty_engineering_path() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, engineering_path=""),
            case_number="case-engineering-path-empty",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert "engineering_path" not in vars(store.cases[0])


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_does_not_write_non_authority_engineering_path() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, engineering_path="rotary"),
            case_number="case-engineering-path-invalid",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert "engineering_path" not in vars(store.cases[0])


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_does_not_trim_engineering_path_into_authority_value() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, engineering_path=" rwdr "),
            case_number="case-engineering-path-whitespace",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    assert "engineering_path" not in vars(store.cases[0])


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_does_not_mirror_unrequested_case_fields() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, inquiry_admissible=True, rfq_ready=True),
            case_number="case-readiness-only",
            user_id="user-1",
            tenant_id="tenant-1",
        )

    case_fields = vars(store.cases[0])
    assert "inquiry_admissible" in case_fields
    assert "rfq_ready" in case_fields
    for field_name in (
        "request_type",
        "engineering_path",
        "sealing_material_family",
        "application_pattern_id",
        "pre_gate_classification",
        "payload",
    ):
        assert field_name not in case_fields


@pytest.mark.asyncio
async def test_get_case_and_latest_snapshot_reads_latest_revision() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-read",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, medium="Dampf"),
            case_number="case-read",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        case_row = await get_case_by_number_async(case_number="case-read", user_id="user-1")
        snapshot = await get_latest_governed_case_snapshot_async(case_number="case-read", user_id="user-1")

    assert case_row is not None
    assert case_row["case_number"] == "case-read"
    assert case_row["user_id"] == "user-1"
    assert snapshot is not None
    assert snapshot.case_number == "case-read"
    assert snapshot.revision == 2
    assert snapshot.state_json["analysis_cycle"] == 1
    assert snapshot.state_json["normalized"]["parameters"]["medium"]["value"] == "Dampf"
    assert snapshot.basis_hash


@pytest.mark.asyncio
async def test_get_governed_snapshot_by_revision_reads_targeted_revision() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-rev-read",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, medium="Dampf"),
            case_number="case-rev-read",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        snapshot = await get_governed_case_snapshot_by_revision_async(
            case_number="case-rev-read",
            revision=1,
            user_id="user-1",
        )

    assert snapshot is not None
    assert snapshot.revision == 1
    assert snapshot.state_json["normalized"]["parameters"]["medium"]["value"] == "Wasser"


@pytest.mark.asyncio
async def test_workspace_revision_projection_loader_reads_snapshot_with_owner_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    @dataclass(frozen=True)
    class _SnapshotRead:
        state_json: dict

    class _RedisShouldNotBeUsed:
        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            raise AssertionError("revisioned workspace snapshot reads must not touch Redis")

    async def _fake_get_snapshot_by_revision(*, case_number, revision, user_id=None):
        captured["case_number"] = case_number
        captured["revision"] = revision
        captured["user_id"] = user_id
        return _SnapshotRead(state_json=_state(analysis_cycle=7).model_dump(mode="json"))

    monkeypatch.setattr(
        loaders_module,
        "get_governed_case_snapshot_by_revision_async",
        _fake_get_snapshot_by_revision,
    )

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_RedisShouldNotBeUsed)}):
        state = await loaders_module._load_governed_state_snapshot_projection_source(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="ignored-sub",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            case_id="case-rev-read",
            revision=3,
        )

    assert state is not None
    assert state.analysis_cycle == 7
    assert captured == {
        "case_number": "case-rev-read",
        "revision": 3,
        "user_id": "user-1",
    }


@pytest.mark.asyncio
async def test_guarded_workspace_projection_prefers_latest_snapshot_on_marker_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    @dataclass(frozen=True)
    class _SnapshotRead:
        revision: int
        state_json: dict

    class _FakeAsyncRedis:
        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            return cls()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, key):
            redis_state = _state(analysis_cycle=1).model_copy(
                update={
                    "persistence_marker": GovernedPersistenceMarker(
                        snapshot_comparable=True,
                        postgres_snapshot_revision=5,
                        postgres_case_revision=5,
                    )
                }
            )
            return redis_state.model_dump_json()

    async def _fake_get_latest_snapshot(*, case_number, user_id=None):
        captured["case_number"] = case_number
        captured["user_id"] = user_id
        return _SnapshotRead(
            revision=5,
            state_json=_state(analysis_cycle=9, medium="Dampf").model_dump(mode="json"),
        )

    monkeypatch.setenv("REDIS_URL", "redis://test/0")
    monkeypatch.setattr(loaders_module, "get_latest_governed_case_snapshot_async", _fake_get_latest_snapshot)

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_FakeAsyncRedis)}):
        state = await loaders_module._load_guarded_workspace_projection_source(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="ignored-sub",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            case_id="case-guarded",
        )

    assert state is not None
    assert state.analysis_cycle == 9
    assert captured == {"case_number": "case-guarded", "user_id": "user-1"}


@pytest.mark.asyncio
async def test_guarded_workspace_projection_marker_missing_keeps_redis_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeAsyncRedis:
        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            return cls()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, key):
            return _state(analysis_cycle=2).model_dump_json()

    async def _unexpected_latest_snapshot(*args, **kwargs):
        raise AssertionError("missing marker must keep Redis primary")

    monkeypatch.setenv("REDIS_URL", "redis://test/0")
    monkeypatch.setattr(loaders_module, "get_latest_governed_case_snapshot_async", _unexpected_latest_snapshot)

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_FakeAsyncRedis)}):
        state = await loaders_module._load_guarded_workspace_projection_source(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="ignored-sub",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            case_id="case-marker-missing",
        )

    assert state is not None
    assert state.analysis_cycle == 2


@pytest.mark.asyncio
async def test_guarded_workspace_projection_marker_mismatch_keeps_redis_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @dataclass(frozen=True)
    class _SnapshotRead:
        revision: int
        state_json: dict

    class _FakeAsyncRedis:
        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            return cls()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, key):
            redis_state = _state(analysis_cycle=3).model_copy(
                update={
                    "persistence_marker": GovernedPersistenceMarker(
                        snapshot_comparable=True,
                        postgres_snapshot_revision=5,
                        postgres_case_revision=5,
                    )
                }
            )
            return redis_state.model_dump_json()

    async def _fake_get_latest_snapshot(*, case_number, user_id=None):
        return _SnapshotRead(
            revision=6,
            state_json=_state(analysis_cycle=10, medium="Dampf").model_dump(mode="json"),
        )

    monkeypatch.setenv("REDIS_URL", "redis://test/0")
    monkeypatch.setattr(loaders_module, "get_latest_governed_case_snapshot_async", _fake_get_latest_snapshot)

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_FakeAsyncRedis)}):
        state = await loaders_module._load_guarded_workspace_projection_source(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="ignored-sub",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            case_id="case-marker-mismatch",
        )

    assert state is not None
    assert state.analysis_cycle == 3


@pytest.mark.asyncio
async def test_guarded_workspace_projection_without_redis_uses_latest_snapshot_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @dataclass(frozen=True)
    class _SnapshotRead:
        revision: int
        state_json: dict

    class _FakeAsyncRedis:
        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            return cls()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, key):
            return None

    async def _fake_get_latest_snapshot(*, case_number, user_id=None):
        return _SnapshotRead(
            revision=4,
            state_json=_state(analysis_cycle=8, medium="Dampf").model_dump(mode="json"),
        )

    monkeypatch.setenv("REDIS_URL", "redis://test/0")
    monkeypatch.setattr(loaders_module, "get_latest_governed_case_snapshot_async", _fake_get_latest_snapshot)

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_FakeAsyncRedis)}):
        state = await loaders_module._load_guarded_workspace_projection_source(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="ignored-sub",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            case_id="case-no-redis",
        )

    assert state is not None
    assert state.analysis_cycle == 8


@pytest.mark.asyncio
async def test_workspace_projection_preserves_empty_state_creation_when_no_redis_or_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_state = _state(analysis_cycle=11)

    async def _fake_guarded_source(*, current_user, case_id):
        return None

    async def _fake_load_live(*, current_user, session_id, create_if_missing=False):
        assert session_id == "case-empty"
        assert create_if_missing is True
        return created_state

    monkeypatch.setattr(workspace_routes, "_load_guarded_workspace_projection_source", _fake_guarded_source)
    monkeypatch.setattr(workspace_routes, "_load_live_governed_state", _fake_load_live)

    projection = await workspace_routes.get_workspace_projection(
        "case-empty",
        revision=None,
        current_user=RequestUser(
            user_id="user-1",
            username="tester",
            sub="ignored-sub",
            roles=[],
            scopes=[],
            tenant_id="tenant-1",
        ),
    )

    assert projection.case_summary.thread_id == "case-empty"
    assert projection.cycle_info.state_revision == 11


@pytest.mark.asyncio
async def test_workspace_projection_revision_path_does_not_use_guarded_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision_state = _state(analysis_cycle=12)

    async def _fake_revision_source(*, current_user, case_id, revision=None):
        assert case_id == "case-revision"
        assert revision == 3
        return revision_state

    async def _unexpected_guarded_source(*args, **kwargs):
        raise AssertionError("revisioned reads must not use guarded non-revisioned loader")

    monkeypatch.setattr(workspace_routes, "_load_governed_state_snapshot_projection_source", _fake_revision_source)
    monkeypatch.setattr(workspace_routes, "_load_guarded_workspace_projection_source", _unexpected_guarded_source)

    projection = await workspace_routes.get_workspace_projection(
        "case-revision",
        revision=3,
        current_user=RequestUser(
            user_id="user-1",
            username="tester",
            sub="ignored-sub",
            roles=[],
            scopes=[],
            tenant_id="tenant-1",
        ),
    )

    assert projection.case_summary.thread_id == "case-revision"
    assert projection.cycle_info.state_revision == 12


@pytest.mark.asyncio
async def test_list_cases_reads_owned_cases_newest_first_with_latest_revision() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-a",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=3),
            case_number="case-b",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=2),
            case_number="case-c",
            user_id="user-2",
            tenant_id="tenant-2",
        )
        store.cases[0].updated_at = "2026-04-08T00:00:00+00:00"
        store.cases[1].updated_at = "2026-04-09T00:00:00+00:00"
        store.cases[2].updated_at = "2026-04-10T00:00:00+00:00"
        items = await list_cases_async(user_id="user-1")

    assert [item["case_number"] for item in items] == ["case-b", "case-a"]
    assert [item["latest_revision"] for item in items] == [1, 1]


@pytest.mark.asyncio
async def test_list_case_snapshots_reads_revisions_newest_first() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1),
            case_number="case-list",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, medium="Dampf"),
            case_number="case-list",
            user_id="user-1",
            tenant_id="tenant-1",
        )
        items = await list_governed_case_snapshots_async(case_number="case-list", user_id="user-1")

    assert [item.revision for item in items] == [2, 1]
    assert items[0].basis_hash is not None


@pytest.mark.asyncio
async def test_persist_live_governed_state_keeps_redis_and_triggers_postgres_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    redis_instances = []

    class _FakeAsyncRedis:
        def __init__(self, url: str, decode_responses: bool):
            self.url = url
            self.decode_responses = decode_responses
            self.set_calls = []

        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            instance = cls(url, decode_responses)
            redis_instances.append(instance)
            return instance

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def set(self, key, value, ex=None):
            self.set_calls.append((key, value, ex))

    async def _fake_save_snapshot(
        state,
        *,
        case_number,
        user_id,
        tenant_id,
        pre_gate_classification=None,
        subsegment=None,
        status="active",
    ):
        captured["analysis_cycle"] = state.analysis_cycle
        captured["case_number"] = case_number
        captured["user_id"] = user_id
        captured["tenant_id"] = tenant_id
        captured["pre_gate_classification"] = pre_gate_classification
        captured["status"] = status

    monkeypatch.setenv("REDIS_URL", "redis://test/0")
    monkeypatch.setattr(loaders_module, "save_governed_state_snapshot_async", _fake_save_snapshot)

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_FakeAsyncRedis)}):
        marked_input_state = _state(analysis_cycle=3).model_copy(
            update={
                "persistence_marker": GovernedPersistenceMarker(
                    snapshot_comparable=True,
                    postgres_snapshot_revision=2,
                    postgres_case_revision=2,
                )
            }
        )
        await router_module._persist_live_governed_state(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="user-1",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            session_id="case-42",
            state=marked_input_state,
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    assert len(redis_instances) == 1
    assert redis_instances[0].set_calls
    assert redis_instances[0].set_calls[0][0] == "governed_state:tenant-1:case-42"
    assert captured == {
        "analysis_cycle": 3,
        "case_number": "case-42",
        "user_id": "user-1",
        "tenant_id": "tenant-1",
        "pre_gate_classification": "DOMAIN_INQUIRY",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_persist_live_governed_state_stamps_redis_after_snapshot_success(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_instances = []

    class _FakeAsyncRedis:
        def __init__(self, url: str, decode_responses: bool):
            self.url = url
            self.decode_responses = decode_responses
            self.set_calls = []

        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            instance = cls(url, decode_responses)
            redis_instances.append(instance)
            return instance

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def set(self, key, value, ex=None):
            self.set_calls.append((key, value, ex))

    async def _fake_save_snapshot(*args, **kwargs):
        return types.SimpleNamespace(
            postgres_snapshot_revision=7,
            postgres_case_revision=7,
        )

    monkeypatch.setenv("REDIS_URL", "redis://test/0")
    monkeypatch.setattr(loaders_module, "save_governed_state_snapshot_async", _fake_save_snapshot)

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_FakeAsyncRedis)}):
        marked_input_state = _state(analysis_cycle=3).model_copy(
            update={
                "persistence_marker": GovernedPersistenceMarker(
                    snapshot_comparable=True,
                    postgres_snapshot_revision=2,
                    postgres_case_revision=2,
                )
            }
        )
        await router_module._persist_live_governed_state(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="user-1",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            session_id="case-42",
            state=marked_input_state,
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    assert len(redis_instances) == 2
    first_payload = json.loads(redis_instances[0].set_calls[0][1])
    second_payload = json.loads(redis_instances[1].set_calls[0][1])
    assert first_payload["persistence_marker"] is None
    assert second_payload["persistence_marker"] == {
        "snapshot_comparable": True,
        "postgres_snapshot_revision": 7,
        "postgres_case_revision": 7,
    }


@pytest.mark.asyncio
async def test_persist_live_governed_state_does_not_stamp_redis_after_snapshot_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_instances = []

    class _FakeAsyncRedis:
        def __init__(self, url: str, decode_responses: bool):
            self.set_calls = []

        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            instance = cls(url, decode_responses)
            redis_instances.append(instance)
            return instance

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def set(self, key, value, ex=None):
            self.set_calls.append((key, value, ex))

    async def _fake_save_snapshot(*args, **kwargs):
        raise RuntimeError("snapshot unavailable")

    monkeypatch.setenv("REDIS_URL", "redis://test/0")
    monkeypatch.setattr(loaders_module, "save_governed_state_snapshot_async", _fake_save_snapshot)

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_FakeAsyncRedis)}):
        marked_input_state = _state(analysis_cycle=3).model_copy(
            update={
                "persistence_marker": GovernedPersistenceMarker(
                    snapshot_comparable=True,
                    postgres_snapshot_revision=2,
                    postgres_case_revision=2,
                )
            }
        )
        await router_module._persist_live_governed_state(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="user-1",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            session_id="case-42",
            state=marked_input_state,
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    assert len(redis_instances) == 1
    payload = json.loads(redis_instances[0].set_calls[0][1])
    assert payload["persistence_marker"] is None


@pytest.mark.asyncio
async def test_persist_live_governed_state_does_not_store_gate_mode_as_pre_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    redis_instances = []

    class _FakeAsyncRedis:
        @classmethod
        def from_url(cls, url: str, decode_responses: bool):
            instance = cls()
            redis_instances.append(instance)
            return instance

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def set(self, key, value, ex=None):
            return None

    async def _fake_save_snapshot(
        state,
        *,
        case_number,
        user_id,
        tenant_id,
        pre_gate_classification=None,
        subsegment=None,
        status="active",
    ):
        captured["pre_gate_classification"] = pre_gate_classification

    monkeypatch.setenv("REDIS_URL", "redis://test/0")
    monkeypatch.setattr(loaders_module, "save_governed_state_snapshot_async", _fake_save_snapshot)

    with patch.dict(sys.modules, {"redis.asyncio": types.SimpleNamespace(Redis=_FakeAsyncRedis)}):
        await router_module._persist_live_governed_state(
            current_user=RequestUser(
                user_id="user-1",
                username="tester",
                sub="user-1",
                roles=[],
                scopes=[],
                tenant_id="tenant-1",
            ),
            session_id="case-42",
            state=_state(analysis_cycle=3),
            pre_gate_classification="CONVERSATION",
        )

    assert len(redis_instances) == 1
    assert captured == {"pre_gate_classification": None}
