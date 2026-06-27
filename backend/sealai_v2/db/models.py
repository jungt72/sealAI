"""V2 durable schema (build-spec §3/§7). Every table is tenant-scoped (P0); the composite primary
keys mirror the in-process store's ``(tenant_id, session_id[, feld])`` keying so the Postgres adapter
is a faithful drop-in (bounded window, last-value-wins case-state, separate derived channel).

- ``v2_sessions``       — one row per (tenant, session): the completed-exchange counter (staleness).
- ``v2_messages``       — the message log (L1 working window slices the tail; L3 = full history).
- ``v2_facts``          — the structured case-state (L2), keyed by ``feld`` (last value wins).
- ``v2_derived``        — the M8 kernel-computed slice (backend-only channel), one JSON row/session.
- ``v2_durable_facts``  — the L4 cross-session durable facts, keyed by ``(tenant, feld)`` (per-tenant,
  NOT per-session — the cross-session memory), last value wins.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sealai_v2.db.engine import Base


class V2Session(Base):
    __tablename__ = "v2_sessions"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    turns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class V2Message(Base):
    __tablename__ = "v2_messages"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    idx: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )  # monotonic within the session
    role: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # "user" | "assistant"
    text: Mapped[str] = mapped_column(Text, nullable=False)


class V2Fact(Base):
    __tablename__ = "v2_facts"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    feld: Mapped[str] = mapped_column(String(255), primary_key=True)
    wert: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(
        String(64), default="distilled-from-conversation", nullable=False
    )
    as_of_turn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class V2Derived(Base):
    __tablename__ = "v2_derived"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    # Wholesale-replaced JSON list of serialized DerivedFact (the slice is recomputed-and-replaced,
    # never patched — a stale kernel value can never persist). Backend-only channel.
    slice_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class V2DurableFact(Base):
    __tablename__ = "v2_durable_facts"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    feld: Mapped[str] = mapped_column(String(255), primary_key=True)
    wert: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(
        String(64), default="distilled-from-conversation", nullable=False
    )
    as_of_turn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class V2HerstellerPartner(Base):
    """Hersteller-PARTNER (owner business model) — GLOBAL (not tenant-scoped; manufacturers serve all
    tenants). The dashboard-editable paid-membership + company + lead-routing + capability record.
    NEUTRALITY: the §3.9 keystone stays on the capability SEED lane; here neutrality is at the SELECTION
    layer (``rank_partners`` ranks by capability fit, NEVER by ``plan``/``aktiv``). ``plan`` is billing
    metadata stored here, never a ranking input."""

    __tablename__ = "v2_hersteller_partner"

    hersteller: Mapped[str] = mapped_column(
        String(255), primary_key=True
    )  # stable company key
    firmenname: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lead_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    beschreibung: Mapped[str] = mapped_column(Text, default="", nullable=False)
    standort: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    kontakt_oeffentlich: Mapped[str] = mapped_column(
        String(320), default="", nullable=False
    )
    partner_seit: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    plan: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    werkstoffe: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    bauformen: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    groessen: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    zertifikate: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class V2Lead(Base):
    """A captured Anfrage/lead (owner business model: manufacturers RECEIVE the leads) — the structured
    RFQ briefing routed to a partner. GLOBAL by partner; ``tenant_id``/``session_id`` kept for
    provenance (which session produced it). Durable so the partner/owner can retrieve it; email
    delivery is an optional config-gated add-on, not a hard dependency. ``status`` tracks the lead
    lifecycle ("neu" -> ...). ``created_at`` is an ISO-8601 string set at capture (no server clock dep)."""

    __tablename__ = "v2_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    firmenname: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    lead_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    briefing_title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    briefing_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="neu", nullable=False)


class V2Contribution(Base):
    """Wissens-Beitrag (user opts to share a worked-out situation + outcome to improve sealingAI). DRAFT in
    the owner REVIEW QUEUE — NEVER auto-feeds the trust spine; promotion to knowledge is the review gate.
    Anonymous → tenant_ref='anon', subject_ref='' (no identity); the structured case-state is technical."""

    __tablename__ = "v2_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anonym: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_ref: Mapped[str] = mapped_column(String(255), default="anon", nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    situation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    case_state_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    outcome: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="neu", nullable=False)
    review_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
