"""Owner surface /api/v2/admin/* (Hersteller-Partner CRUD + lead retrieval). Proves: the platform-owner
realm-role is required (403 without it, 401 without a token); CRUD round-trips; ``plan`` is stored but
is just metadata; leads are retrievable (with the briefing + routing email — the OWNER surface)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.leads import InProcessLeadStore, Lead
from sealai_v2.knowledge.hersteller_partner import InProcessPartnerRegistry
from sealai_v2.security.auth import FakeAuthValidator

IDS = {
    "tok-admin": VerifiedIdentity(
        "tenant-A", "sess-A", "owner", roles=("platform_owner",)
    ),
    "tok-user": VerifiedIdentity("tenant-B", "sess-B", "user-B"),  # roles=() by default
}


def _client(registry=None, store=None):
    registry = registry if registry is not None else InProcessPartnerRegistry()
    store = store if store is not None else InProcessLeadStore()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(IDS)
    app.dependency_overrides[deps.get_partner_registry] = lambda: registry
    app.dependency_overrides[deps.get_lead_store] = lambda: store
    return TestClient(app), registry, store


def _admin():
    return {"Authorization": "Bearer tok-admin"}


def _user():
    return {"Authorization": "Bearer tok-user"}


def _body(**over):
    base = {
        "firmenname": "ACME Dichtungen GmbH",
        "aktiv": True,
        "lead_email": "leads@acme.example",
        "website": "https://acme.example",
        "beschreibung": "RWDR-Spezialist",
        "standort": "DE",
        "plan": "basic",
        "werkstoffe": ["FKM"],
        "bauformen": ["RWDR"],
        "zertifikate": ["ISO 9001"],
    }
    base.update(over)
    return base


def test_non_admin_is_forbidden():
    client, _, _ = _client()
    assert client.get("/api/v2/admin/hersteller", headers=_user()).status_code == 403


def test_missing_token_unauthorized():
    client, _, _ = _client()
    assert client.get("/api/v2/admin/hersteller").status_code == 401


def test_upsert_then_list_and_get():
    client, _, _ = _client()
    r = client.put("/api/v2/admin/hersteller/acme", json=_body(), headers=_admin())
    assert r.status_code == 200 and r.json()["hersteller"] == "acme"
    lst = client.get("/api/v2/admin/hersteller", headers=_admin()).json()["hersteller"]
    assert [h["hersteller"] for h in lst] == ["acme"]
    one = client.get("/api/v2/admin/hersteller/acme", headers=_admin()).json()
    assert one["firmenname"] == "ACME Dichtungen GmbH"
    assert (
        one["lead_email"] == "leads@acme.example"
    )  # OWNER surface DOES show the routing target
    assert one["plan"] == "basic"  # billing metadata round-trips (stored, never ranks)


def test_upsert_edits_existing():
    client, _, _ = _client()
    client.put("/api/v2/admin/hersteller/acme", json=_body(), headers=_admin())
    client.put(
        "/api/v2/admin/hersteller/acme",
        json=_body(firmenname="ACME 2", aktiv=False, plan="enterprise"),
        headers=_admin(),
    )
    one = client.get("/api/v2/admin/hersteller/acme", headers=_admin()).json()
    assert one["firmenname"] == "ACME 2" and one["aktiv"] is False
    assert one["plan"] == "enterprise"


def test_delete_partner():
    client, _, _ = _client()
    client.put("/api/v2/admin/hersteller/acme", json=_body(), headers=_admin())
    assert (
        client.delete("/api/v2/admin/hersteller/acme", headers=_admin()).status_code
        == 200
    )
    assert (
        client.get("/api/v2/admin/hersteller/acme", headers=_admin()).status_code == 404
    )
    # deleting a ghost id → 404
    assert (
        client.delete("/api/v2/admin/hersteller/ghost", headers=_admin()).status_code
        == 404
    )


def test_get_unknown_partner_404():
    client, _, _ = _client()
    assert (
        client.get("/api/v2/admin/hersteller/ghost", headers=_admin()).status_code
        == 404
    )


def test_leads_retrieval_owner_surface():
    store = InProcessLeadStore()
    store.store(
        Lead(
            partner_id="acme",
            firmenname="ACME Dichtungen GmbH",
            lead_email="leads@acme.example",
            tenant_id="tenant-A",
            session_id="sess-A",
            owner_subject="user-A",
            case_id="sess-A",
            case_revision=1,
            briefing_title="Technische Orientierung (Screening)",
            briefing_body="BRIEFING-INHALT",
            created_at="2026-06-27T00:00:00+00:00",
        )
    )
    client, _, _ = _client(store=store)
    leads = client.get("/api/v2/admin/leads", headers=_admin()).json()["leads"]
    assert len(leads) == 1
    assert leads[0]["partner_id"] == "acme"
    assert (
        leads[0]["lead_email"] == "leads@acme.example"
    )  # owner needs the routing target
    assert leads[0]["briefing_body"] == "BRIEFING-INHALT"
    assert leads[0]["status"] == "neu"


def test_leads_filter_by_partner():
    store = InProcessLeadStore()
    for pid in ("acme", "beta", "acme"):
        store.store(
            Lead(
                partner_id=pid,
                firmenname=pid,
                lead_email=f"leads@{pid}",
                tenant_id="t",
                session_id="s",
                owner_subject="user",
                case_id="s",
                case_revision=1,
                briefing_title="t",
                briefing_body="b",
                created_at="2026-06-27T00:00:00+00:00",
            )
        )
    client, _, _ = _client(store=store)
    acme = client.get("/api/v2/admin/leads?partner_id=acme", headers=_admin()).json()[
        "leads"
    ]
    assert len(acme) == 2 and {ld["partner_id"] for ld in acme} == {"acme"}


def test_leads_require_platform_owner():
    client, _, _ = _client()
    assert client.get("/api/v2/admin/leads", headers=_user()).status_code == 403
