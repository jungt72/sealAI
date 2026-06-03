"""P0-1 — LTM (Long-Term-Memory) tenant scoping.

Security regression guard for V1.7 §8 / audit C6: the Qdrant LTM access
must pin BOTH user and tenant. Before P0-1 the filter was user-only, so a
user that spans two tenants could export/delete another tenant's memory
points, and writes carried no tenant at all. These tests reproduce that gap
(red) and lock the fix (green): the query/delete filter pins tenant, the
functions are fail-closed (tenant mandatory), and the write path stamps an
authoritative tenant that a client body cannot override.

LTM is disabled in production (LTM_ENABLE unset) and the `sealai_ltm`
collection does not exist yet, so this is defense-in-depth — additive
scoping with no live behaviour change. The Qdrant client is stubbed in
conftest (scroll returns []), so these tests assert the *filter structure*
and the *written payload*, not data round-trips.
"""

from __future__ import annotations

import types

import pytest

from app.api.v1.endpoints import memory as memory_api
from app.services.auth.dependencies import RequestUser
from app.services.memory import memory_core


class _RecordingClient:
    """Captures the filters/selectors/payloads handed to Qdrant."""

    def __init__(self) -> None:
        self.upserts: list = []
        self.scroll_filters: list = []
        self.delete_selectors: list = []

    def get_collection(self, *_a, **_k):
        return types.SimpleNamespace(payload_schema={})

    def recreate_collection(self, *_a, **_k):  # pragma: no cover - collection "exists"
        return None

    def upsert(self, collection_name=None, points=None, wait=True, **_k):
        self.upserts.append((collection_name, points))

    def scroll(self, collection_name=None, scroll_filter=None, **_k):
        self.scroll_filters.append(scroll_filter)
        return [], None

    def delete(self, collection_name=None, points_selector=None, wait=True, **_k):
        self.delete_selectors.append(points_selector)


def _conditions(flt) -> dict:
    """key -> matched value from a (stubbed) qdrant Filter."""
    out: dict = {}
    for cond in getattr(flt, "must", []) or []:
        out[getattr(cond, "key", None)] = getattr(getattr(cond, "match", None), "value", None)
    return out


def _user(tenant_id="tenant-A", user_id="u1") -> RequestUser:
    return RequestUser(user_id=user_id, username="u1", sub=user_id, roles=[], scopes=[], tenant_id=tenant_id)


@pytest.fixture()
def client(monkeypatch):
    rec = _RecordingClient()
    # Other tests in the session may swap app.core.config.settings for a stub
    # that lacks LTM fields; set both deterministically (raising=False) so this
    # test is order-independent.
    for mod in (memory_core, memory_api):
        monkeypatch.setattr(mod.settings, "ltm_enable", True, raising=False)
        monkeypatch.setattr(mod.settings, "qdrant_collection_ltm", "sealai_ltm_test", raising=False)
    monkeypatch.setattr(memory_core, "_get_qdrant_client", lambda: rec)
    monkeypatch.setattr(memory_api, "_get_qdrant_client", lambda: rec)
    return rec


# --- the security invariant: the filter pins user AND tenant -----------------

def test_build_user_filter_pins_user_and_tenant():
    conds = _conditions(memory_core._build_user_filter(user="u1", tenant_id="tenant-A"))
    assert conds.get("user") == "u1"
    assert conds.get("tenant_id") == "tenant-A"


def test_build_user_filter_requires_tenant():
    with pytest.raises(TypeError):
        memory_core._build_user_filter(user="u1")  # fail-closed: tenant mandatory


# --- export / delete forward the tenant into the Qdrant query ----------------

def test_export_scopes_query_by_tenant(client):
    memory_core.ltm_export_all(user="u1", tenant_id="tenant-A")
    assert client.scroll_filters, "export must query qdrant"
    conds = _conditions(client.scroll_filters[-1])
    assert conds.get("user") == "u1" and conds.get("tenant_id") == "tenant-A"


def test_delete_scopes_selector_by_tenant(client):
    memory_core.ltm_delete_all(user="u1", tenant_id="tenant-B")
    assert client.delete_selectors, "delete must run"
    selector = client.delete_selectors[-1]
    conds = _conditions(getattr(selector, "filter", selector))
    assert conds.get("user") == "u1" and conds.get("tenant_id") == "tenant-B"


def test_export_requires_tenant():
    with pytest.raises(TypeError):
        memory_core.ltm_export_all(user="u1")


def test_delete_requires_tenant():
    with pytest.raises(TypeError):
        memory_core.ltm_delete_all(user="u1")


# --- create stamps an authoritative tenant the client cannot override --------

@pytest.mark.asyncio
async def test_create_writes_authoritative_tenant_and_ignores_client_override(client):
    await memory_api.create_memory_item(
        payload={"text": "hello", "tenant_id": "evil-tenant"},  # client tries to spoof
        user=_user(tenant_id="tenant-A"),
    )
    assert client.upserts, "create must upsert"
    _coll, points = client.upserts[-1]
    payload = points[0].payload
    assert payload["tenant_id"] == "tenant-A"  # authoritative, not the client value
    assert payload["user"] == "u1"
