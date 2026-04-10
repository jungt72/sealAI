from __future__ import annotations

import os
import sys
import types
import uuid
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
from app.agent.state.models import (
    DerivedState,
    EvidenceState,
    GovernedSessionState,
    NormalizedParameter,
    NormalizedState,
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


def _state(*, analysis_cycle: int, medium: str = "Wasser") -> GovernedSessionState:
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

    def __init__(self, *, case_number, user_id, subsegment=None, status="active", id=None, updated_at=None):
        self.id = id or str(uuid.uuid4())
        self.case_number = case_number
        self.user_id = user_id
        self.subsegment = subsegment
        self.status = status
        self.updated_at = updated_at or f"updated:{case_number}"


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


def _install_fake_snapshot_backend():
    store = _Store(cases=[], snapshots=[])
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: _FakeSessionContext(store))
    fake_case_models = types.SimpleNamespace(CaseRecord=_FakeCaseRecord)
    fake_snapshot_models = types.SimpleNamespace(CaseStateSnapshot=_FakeCaseStateSnapshot)
    return store, {
        "app.database": fake_db,
        "app.models.case_record": fake_case_models,
        "app.models.case_state_snapshot": fake_snapshot_models,
    }


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_creates_case_and_snapshot() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=2),
            case_number="case-123",
            user_id="user-1",
        )

    assert len(store.cases) == 1
    assert len(store.snapshots) == 1
    case_row = store.cases[0]
    snapshot = store.snapshots[0]
    assert case_row.case_number == "case-123"
    assert case_row.user_id == "user-1"
    assert snapshot.revision == 2
    assert snapshot.case_id == case_row.id
    assert snapshot.state_json["analysis_cycle"] == 2
    assert snapshot.basis_hash
    assert snapshot.ontology_version == "sealai_norm_v1"
    assert snapshot.prompt_version == REASONING_PROMPT_VERSION
    assert snapshot.model_version == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_is_idempotent_for_same_state() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        state = _state(analysis_cycle=1)
        await save_governed_state_snapshot_async(state, case_number="case-dup", user_id="user-1")
        await save_governed_state_snapshot_async(state, case_number="case-dup", user_id="user-1")

    assert len(store.cases) == 1
    assert len(store.snapshots) == 1


@pytest.mark.asyncio
async def test_save_governed_state_snapshot_advances_revision_when_cycle_stalls() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(_state(analysis_cycle=1), case_number="case-rev", user_id="user-1")
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, medium="Dampf"),
            case_number="case-rev",
            user_id="user-1",
        )

    assert [snapshot.revision for snapshot in store.snapshots] == [1, 2]


@pytest.mark.asyncio
async def test_get_case_and_latest_snapshot_reads_latest_revision() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(_state(analysis_cycle=1), case_number="case-read", user_id="user-1")
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, medium="Dampf"),
            case_number="case-read",
            user_id="user-1",
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
        await save_governed_state_snapshot_async(_state(analysis_cycle=1), case_number="case-rev-read", user_id="user-1")
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, medium="Dampf"),
            case_number="case-rev-read",
            user_id="user-1",
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
async def test_list_cases_reads_owned_cases_newest_first_with_latest_revision() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(_state(analysis_cycle=1), case_number="case-a", user_id="user-1")
        await save_governed_state_snapshot_async(_state(analysis_cycle=3), case_number="case-b", user_id="user-1")
        await save_governed_state_snapshot_async(_state(analysis_cycle=2), case_number="case-c", user_id="user-2")
        store.cases[0].updated_at = "2026-04-08T00:00:00+00:00"
        store.cases[1].updated_at = "2026-04-09T00:00:00+00:00"
        store.cases[2].updated_at = "2026-04-10T00:00:00+00:00"
        items = await list_cases_async(user_id="user-1")

    assert [item["case_number"] for item in items] == ["case-b", "case-a"]
    assert [item["latest_revision"] for item in items] == [3, 1]


@pytest.mark.asyncio
async def test_list_case_snapshots_reads_revisions_newest_first() -> None:
    store, fake_modules = _install_fake_snapshot_backend()

    with patch.dict(sys.modules, fake_modules), patch("sqlalchemy.select", _fake_select):
        await save_governed_state_snapshot_async(_state(analysis_cycle=1), case_number="case-list", user_id="user-1")
        await save_governed_state_snapshot_async(
            _state(analysis_cycle=1, medium="Dampf"),
            case_number="case-list",
            user_id="user-1",
        )
        items = await list_governed_case_snapshots_async(case_number="case-list", user_id="user-1")

    assert [item.revision for item in items] == [2, 1]
    assert items[0].basis_hash is not None


@pytest.mark.asyncio
async def test_persist_live_governed_state_triggers_postgres_snapshot_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def _fake_save_snapshot(state, *, case_number, user_id, subsegment=None, status="active"):
        captured["analysis_cycle"] = state.analysis_cycle
        captured["case_number"] = case_number
        captured["user_id"] = user_id
        captured["status"] = status

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(router_module, "save_governed_state_snapshot_async", _fake_save_snapshot)

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
    )

    assert captured == {
        "analysis_cycle": 3,
        "case_number": "case-42",
        "user_id": "user-1",
        "status": "active",
    }
