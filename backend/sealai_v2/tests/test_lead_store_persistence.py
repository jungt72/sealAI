"""Durable RFQ lead ownership boundaries."""

from __future__ import annotations

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.leads import Lead, PostgresLeadStore
from sealai_v2.db.models import V2Lead


def test_unresolved_legacy_lead_is_never_returned(tmp_path):
    url = f"sqlite:///{tmp_path / 'leads.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    session_factory = make_sessionmaker(engine)
    store = PostgresLeadStore(session_factory)

    lead_id = store.store(
        Lead(
            partner_id="acme",
            firmenname="ACME",
            lead_email="routing@example.test",
            tenant_id="tenant-a",
            session_id="case-a",
            owner_subject="user-a",
            case_id="case-a",
            case_revision=3,
            briefing_title="RFQ",
            briefing_body="Exact case snapshot",
            created_at="2026-07-15T00:00:00Z",
        )
    )
    with session_factory.begin() as session:
        row = session.get(V2Lead, lead_id)
        assert row.ownership_state == "owned"
        row.ownership_state = None

    assert store.list_for_partner("acme") == ()
    assert store.list_all() == ()
