"""V2 durable schema (build-spec §3/§7). Every table is tenant-scoped (P0); the composite primary
keys mirror the in-process store's ``(tenant_id, session_id[, feld])`` keying so the Postgres adapter
is a faithful drop-in (bounded window, last-value-wins case-state, separate derived channel).

- ``v2_sessions``       — one row per (tenant, session): the completed-exchange counter (staleness).
- ``v2_messages``       — the message log (L1 working window slices the tail; L3 = full history).
- ``v2_facts``          — the structured case-state (L2), keyed by ``feld`` (last value wins).
- ``v2_derived``        — the M8 kernel-computed slice (backend-only channel), one JSON row/session.
- ``v2_durable_facts``  — the L4 cross-session durable facts, keyed by ``(tenant, feld)`` (per-tenant,
  NOT per-session — the cross-session memory), last value wins.

sealingAI Memory Architecture V1.0 (Patch 2) — the curated Layer-4 successor
(``memory/curated.py`` has the pure domain types; this is schema only, no repository/CRUD yet):

- ``v2_memory_items``    — one row per curated memory item (see ``memory/curated.py::MemoryItem``).
- ``v2_memory_sources``  — provenance records (one-to-many; "keine Memory-Schreibvorgänge ohne
  Source/Provenance"), NOT inlined as JSON so a later patch can query/filter by source kind.
- ``v2_memory_events``   — the append-only status-transition audit trail (Patch 4 writes one row per
  confirm/reject/deprecate/delete action).
- ``v2_memory_outbox``   — the outbox-pattern queue a later worker (Patch 5) drains to sync
  ``v2_memory_items`` into Qdrant — decouples the write path from Qdrant availability/latency.

Patch 9 reconciliation (against "sealingAI Memory Architecture V1.0 — Finales Konzept", 2026-07-03):
extends ``v2_memory_items``/``v2_memory_sources``/``v2_memory_outbox`` with the final doc's §7
columns. Safe as a straight additive schema change (not a migration) — ``memory_context_enabled`` has
never been on in production, so these tables have zero real rows. See each class's docstring for the
per-table detail; ``V2MemoryOutbox.operation`` -> ``event_type`` is the one rename (same zero-rows
reasoning makes it safe now, would not be after real data exists).

No ``ForeignKey`` constraints in the legacy V2 aggregates (matches this schema's existing convention
above — a green-field, still-evolving schema avoids FK migration friction; referential integrity for
``memory_item_id`` is an application-layer concern, same as every other legacy table here).
MAT-GOV-03A and the inert MAT-EVID-01A/01B/01C extensions are deliberately narrow
exceptions documented in ``docs/architecture/ADR_MAT_GOV_03A_PERSISTENCE.md``
and ``docs/architecture/ADR_MAT_EVID_01A_PERSISTENCE.md``. Their new bounded
aggregates use real ``ON DELETE RESTRICT`` foreign keys and do not retrofit
existing tables.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    JSON,
    Boolean,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sealai_v2.db.engine import Base


class V2Session(Base):
    __tablename__ = "v2_sessions"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    # Verified Keycloak subject that owns this private conversation. Nullable only for legacy rows
    # and hermetic tests created before subject ownership existed; authenticated API access to an
    # unowned row fails closed instead of implicitly claiming it.
    owner_subject: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    turns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    case_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # "Fälle"-Sidebar (Patch A): additive, nullable — existing rows stay valid with all three
    # None until their next record_turn. title is derived from the first user message (~60 chars,
    # no LLM call); created_at/updated_at are ISO-8601 strings stamped by the caller (record_turn),
    # never a DB-side clock, matching every other table in this schema.
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )


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
    unit: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="stated", nullable=False)
    source_ref: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    observed_at: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    document_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    document_version: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class V2Derived(Base):
    __tablename__ = "v2_derived"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    # Wholesale-replaced JSON list of serialized DerivedFact (the slice is recomputed-and-replaced,
    # never patched — a stale kernel value can never persist). Backend-only channel.
    slice_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class V2InterviewState(Base):
    """State coupled to one canonical session/topic, never a second case state."""

    __tablename__ = "v2_interview_state"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    pack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    question_catalog_version: Mapped[str] = mapped_column(String(128), nullable=False)
    case_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_questions_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    need_status_overrides_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    conflicts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    fact_snapshots_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    calculator_version_refs_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2InterviewShadowDecision(Base):
    """Privacy-minimized, append-only shadow decision telemetry."""

    __tablename__ = "v2_interview_shadow_decisions"
    __table_args__ = (
        Index(
            "ix_v2_interview_shadow_scope_created",
            "tenant_id",
            "pack_id",
            "pack_version",
            "policy_version",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    pack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    legacy_question_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    legacy_question_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    legacy_need_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    controller_directive: Mapped[str] = mapped_column(String(64), nullable=False)
    controller_question_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    rule_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    divergence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    completeness_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2DurableFact(Base):
    __tablename__ = "v2_durable_facts"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_subject: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    original_feld: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feld: Mapped[str] = mapped_column(String(255), primary_key=True)
    wert: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(
        String(64), default="distilled-from-conversation", nullable=False
    )
    as_of_turn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class V2CaseRecord(Base):
    """Durable tenant-scoped sealing case, separate from chat sessions."""

    __tablename__ = "v2_case_records"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    risk_class: Mapped[str] = mapped_column(
        String(32), nullable=False, default="normal"
    )
    owner_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2CaseSnapshot(Base):
    """Immutable, content-addressed state of a case at one revision."""

    __tablename__ = "v2_case_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "case_id",
            "revision",
            name="uq_v2_case_snapshot_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    open_points_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2DecisionRecord(Base):
    """Evidence-bound decision candidate based on one immutable case snapshot."""

    __tablename__ = "v2_decision_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="review_required"
    )
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    uncertainty: Mapped[str] = mapped_column(String(64), nullable=False)
    responsibilities_json: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    approvals_required_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    supersedes_decision_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2DecisionApproval(Base):
    """Append-only human review; never a sealingAI component release."""

    __tablename__ = "v2_decision_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    approval_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


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


class V2ManufacturerCapabilityProfile(Base):
    """Technical capability evidence, independent from commercial membership."""

    __tablename__ = "v2_manufacturer_capability_profiles"

    manufacturer_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    regions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    contacts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    seal_types_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    materials_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    compounds_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    size_ranges_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    manufacturing_processes_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    tolerances_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    special_capabilities_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    industries_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    certificates_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    test_capabilities_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    approvals_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    documents_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    services_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    application_limits_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    exclusions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    submitted_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    verified_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_expires_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class V2ManufacturerCapabilityReview(Base):
    """Append-only review transition for a manufacturer capability profile."""

    __tablename__ = "v2_manufacturer_capability_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manufacturer_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_relation: Mapped[str] = mapped_column(String(64), nullable=False)
    conflict_of_interest: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


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


class V2MemoryItem(Base):
    """Curated memory item (sealingAI Memory Architecture V1.0). Mirrors
    ``memory/curated.py::MemoryItem`` — that module is the pure domain shape, this is its
    persisted form. ``scope``/``scope_id`` are the single source of truth for WHERE an item is
    bound; ``project_id``/``case_id``/``workspace_id``/``user_id``/``session_id`` are a READ-PATH
    denormalization (nullable, only populated when ``scope`` is the matching dimension) purely so a
    lookup on any one dimension is a direct indexed column match instead of a
    ``scope='case' AND scope_id=...`` filter — the write path (``db/memory_store.py``) is
    responsible for keeping them in sync with ``scope``/``scope_id`` at insert time.

    Patch 9 reconciliation adds the final concept doc's §7 remaining ``memory_items`` columns:
    ``confidence``/``sensitivity`` (both wired, not yet consumed by any policy rule) and the
    conflict-resolution linkage fields ``subject_hash``/``supersedes_memory_id``/
    ``deprecated_by_memory_id`` (Patch 13's own scope — added now so this table doesn't need a
    second migration later), plus ``qdrant_synced_version``/``qdrant_synced_at`` (observability:
    which version last reached Qdrant and when, distinct from ``qdrant_sync_state`` which is a
    coarse pending/synced/failed flag)."""

    __tablename__ = "v2_memory_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    owner_subject: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    case_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Not in the final doc's own memory_items column list, but the doc DOES list "session" as a
    # valid MemoryScope value with no matching column anywhere in its schema section — an apparent
    # internal inconsistency in the source doc. Added here to close that gap (flagged in the Patch
    # 9b PR), following the exact same denormalization pattern as the other scope dimensions.
    session_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # "pending" | "synced" | "failed" — the outbox worker (Patch 5) sets this after each sync
    # attempt; a Postgres-revalidation read (Patch 6) never trusts this value, it's observability
    # for the sync pipeline, not a gate on what's safe to inject.
    qdrant_sync_state: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )
    qdrant_synced_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qdrant_synced_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    sensitivity: Mapped[str] = mapped_column(
        String(64), default="internal", nullable=False
    )
    subject_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    supersedes_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deprecated_by_memory_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    # ISO-8601 strings stamped by the caller (repository layer, a later patch) — no DB-side clock
    # dependency, matches every other table in this schema.
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purge_after: Mapped[str | None] = mapped_column(String(32), nullable=True)


class V2MemorySource(Base):
    """Provenance for a ``V2MemoryItem`` — one-to-many, NOT inlined as JSON on the parent so a
    later patch can query/filter by source kind directly. No FK constraint (schema convention,
    see the module docstring); ``memory_item_id`` integrity is an application-layer concern.

    Patch 9 reconciliation adds the final concept doc's §7 ``memory_sources`` reference columns
    (``source_ref``/``message_id``/``document_id``/``case_snapshot_id``) — see
    ``memory/curated.py::MemorySource``'s docstring for why this stays one-to-many rather than
    the doc's normalized single-catalog shape."""

    __tablename__ = "v2_memory_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    case_snapshot_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MemoryEvent(Base):
    """Append-only status-transition audit trail for a ``V2MemoryItem`` — one row per action
    (created/confirmed/rejected/deprecated/deleted/purged), written by a later patch's status-
    action endpoints (Patch 4). Never updated or deleted once written."""

    __tablename__ = "v2_memory_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MemoryOutbox(Base):
    """Outbox-pattern queue: a later worker (Patch 5) drains ``pending`` rows here to sync
    ``V2MemoryItem`` into Qdrant, decoupling the write path from Qdrant availability/latency — the
    write to Postgres and the enqueue here happen in the same transaction (a later patch's
    concern), so a crash between them can't silently drop a sync.

    Patch 9 reconciliation (final concept doc §6/§7): ``operation`` renamed to ``event_type`` to
    match the doc's naming exactly (safe now — zero production rows ever written, see the module
    docstring). Adds ``target`` (default "qdrant" — every sync target this codebase has today, but
    named per the doc rather than assumed, in case a future patch adds a second sync target),
    ``payload`` (a JSON snapshot of what to sync, captured by the writer at enqueue time — the real
    outbox-pattern shape: the worker drains from this snapshot, not a live re-read of
    ``V2MemoryItem``, so a row enqueued for a state that has since changed still syncs the state
    that was actually committed at enqueue time), and ``next_attempt_at`` (a real time-windowed
    backoff timestamp, replacing the previous attempt-count-cap-with-immediate-retry)."""

    __tablename__ = "v2_memory_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "upsert" | "delete"
    target: Mapped[str] = mapped_column(String(32), default="qdrant", nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # "pending" | "processing" | "done" | "failed"
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    processed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_attempt_at: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )


class V2KnowledgeDocument(Base):
    """Immutable source-document revision in the technical knowledge ledger.

    ``source_type``/``source_id`` identify the external logical document (for
    example a Paperless document or the reviewed Git seed). A changed checksum
    creates a new monotonically increasing revision; historical revisions are
    retained for reproducibility and audit.
    """

    __tablename__ = "v2_knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_id",
            "version",
            name="uq_v2_knowledge_document_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_id",
            "content_sha256",
            name="uq_v2_knowledge_document_content",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    object_key: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    authority: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    valid_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    valid_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2KnowledgeClaim(Base):
    """Versioned technical claim; Postgres is authoritative for review state.

    Qdrant contains a derived copy only. Retrieval must resolve the ``id`` back
    through this table before a claim may become authoritative prompt context.
    """

    __tablename__ = "v2_knowledge_claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    card_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    card_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    document_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    claim_order: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sources_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    applicability_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    uncertainty: Mapped[str] = mapped_column(
        String(64), nullable=False, default="not_sufficiently_supported"
    )
    transferability: Mapped[str] = mapped_column(
        String(64), nullable=False, default="not_assessed"
    )
    conflicts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    review_expires_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_origin: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unreviewed"
    )
    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provenance_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    qdrant_sync_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    qdrant_synced_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qdrant_synced_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class V2KnowledgeReview(Base):
    """Append-only audit record for every knowledge review transition."""

    __tablename__ = "v2_knowledge_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2KnowledgeOutbox(Base):
    """Transactional queue for the derived technical-knowledge Qdrant index."""

    __tablename__ = "v2_knowledge_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    processed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_attempt_at: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )


class V2LegalAcceptance(Base):
    """Legal-by-Design Phase B (Goal 3): the B2B onboarding / Legal-Gate acceptance record — one row
    per tenant (last acceptance wins, mirrors ``V2DurableFact``'s tenant-scoped-not-session-scoped
    keying: this is an ORG-level fact, not a per-conversation one). ``require_legal_acceptance``
    (``api/deps.py``) fail-closed-gates every productive route on this row existing AND its three
    accepted-version columns matching ``core.legal_doctrine``'s current versions — a doctrine-text
    bump (new ``TERMS_VERSION`` etc.) therefore forces re-acceptance without a migration.

    ``accepted_ip_hash`` is a salted hash (``security/ip_hash.py``), never the raw IP — the record
    proves "an acceptance happened from a stable-but-unlinkable network origin", not who/where,
    matching this schema's existing PII-minimalism (``V2Message.text`` is the only free-text PII
    surface already accepted elsewhere in this schema).
    """

    __tablename__ = "v2_legal_acceptance"

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    vat_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    legal_basis_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dpa_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    business_user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accepted_terms_version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_privacy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_dpa_version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_ip_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    accepted_user_agent: Mapped[str] = mapped_column(Text, nullable=False, default="")


_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), "postgresql")


class V2MaterialRuleset(Base):
    """Stable MAT-GOV-03A family identity; no lifecycle or active-version state."""

    __tablename__ = "v2_material_rulesets"
    __table_args__ = (
        CheckConstraint(
            "length(ruleset_id) = 36 AND ruleset_id LIKE 'mrs_%'",
            name="ck_v2_material_ruleset_id",
        ),
    )

    ruleset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    domain_pack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialRulesetSnapshot(Base):
    """Immutable, content-addressed MAT-GOV-03A snapshot payload."""

    __tablename__ = "v2_material_ruleset_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "ruleset_id",
            "content_sha256",
            name="uq_v2_material_ruleset_snapshot_content",
        ),
        CheckConstraint(
            "length(snapshot_id) = 68 AND snapshot_id LIKE 'mss_%'",
            name="ck_v2_material_snapshot_id",
        ),
        CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256)",
            name="ck_v2_material_snapshot_hash",
        ),
        CheckConstraint(
            "snapshot_schema_version = 1",
            name="ck_v2_material_snapshot_schema_v1",
        ),
        CheckConstraint(
            "canonicalization_version = 1",
            name="ck_v2_material_snapshot_canonicalization_v1",
        ),
        CheckConstraint(
            "mat_gov_contract_version = 'MAT-GOV-03A.v1'",
            name="ck_v2_material_snapshot_contract_v1",
        ),
    )

    snapshot_id: Mapped[str] = mapped_column(String(68), primary_key=True)
    ruleset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("v2_material_rulesets.ruleset_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    canonicalization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    mat_gov_contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_payload_json: Mapped[dict] = mapped_column(
        _MATERIAL_RULESET_JSON, nullable=False
    )
    canonical_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialSnapshotValidationEvent(Base):
    """Append-only technical validation evidence without approval semantics."""

    __tablename__ = "v2_material_snapshot_validation_events"
    __table_args__ = (
        CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mtv_%'",
            name="ck_v2_material_validation_event_id",
        ),
        CheckConstraint(
            "validation_state = 'valid'",
            name="ck_v2_material_validation_state",
        ),
        CheckConstraint(
            "error_code = 'none'",
            name="ck_v2_material_validation_error_code",
        ),
        CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_material_validation_hash",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_ruleset_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    validator_contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_state: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialSnapshotAuditEvent(Base):
    """Append-only technical audit event; never a review or approval record."""

    __tablename__ = "v2_material_snapshot_audit_events"
    __table_args__ = (
        CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mta_%'",
            name="ck_v2_material_audit_event_id",
        ),
        CheckConstraint(
            "event_type = 'snapshot_created'",
            name="ck_v2_material_audit_event_type",
        ),
        CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_material_audit_event_hash",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_ruleset_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(
        _MATERIAL_RULESET_JSON, nullable=False
    )
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceManifest(Base):
    """Stable MAT-EVID-01A manifest family bound to one 03A snapshot."""

    __tablename__ = "v2_material_evidence_manifests"
    __table_args__ = (
        UniqueConstraint(
            "ruleset_snapshot_id",
            name="uq_v2_material_evidence_manifest_ruleset_snapshot",
        ),
        CheckConstraint(
            "length(manifest_id) = 36 AND manifest_id LIKE 'mef_%'",
            name="ck_v2_material_evidence_manifest_id",
        ),
    )

    manifest_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ruleset_snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_ruleset_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    domain_pack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceSnapshot(Base):
    """Immutable, content-addressed MAT-EVID-01A manifest snapshot."""

    __tablename__ = "v2_material_evidence_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "manifest_id",
            "content_sha256",
            name="uq_v2_material_evidence_snapshot_content",
        ),
        CheckConstraint(
            "length(snapshot_id) = 68 AND snapshot_id LIKE 'mes_%'",
            name="ck_v2_material_evidence_snapshot_id",
        ),
        CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256)",
            name="ck_v2_material_evidence_snapshot_hash",
        ),
        CheckConstraint(
            "evidence_manifest_schema_version = 1",
            name="ck_v2_material_evidence_schema_v1",
        ),
        CheckConstraint(
            "canonicalization_version = 1",
            name="ck_v2_material_evidence_canonicalization_v1",
        ),
        CheckConstraint(
            "mat_evid_contract_version = 'MAT-EVID-01A.v1'",
            name="ck_v2_material_evidence_contract_v1",
        ),
    )

    snapshot_id: Mapped[str] = mapped_column(String(68), primary_key=True)
    manifest_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("v2_material_evidence_manifests.manifest_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    evidence_manifest_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    canonicalization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    mat_evid_contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_payload_json: Mapped[dict] = mapped_column(
        _MATERIAL_RULESET_JSON, nullable=False
    )
    canonical_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceValidationEvent(Base):
    """Append-only technical validation event without review semantics."""

    __tablename__ = "v2_material_evidence_validation_events"
    __table_args__ = (
        CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mev_%'",
            name="ck_v2_material_evidence_validation_event_id",
        ),
        CheckConstraint(
            "validation_state = 'valid'",
            name="ck_v2_material_evidence_validation_state",
        ),
        CheckConstraint(
            "error_code = 'none'",
            name="ck_v2_material_evidence_validation_error_code",
        ),
        CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_material_evidence_validation_hash",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_evidence_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    validator_contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_state: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceAuditEvent(Base):
    """Append-only technical creation event; never review or approval."""

    __tablename__ = "v2_material_evidence_audit_events"
    __table_args__ = (
        CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mea_%'",
            name="ck_v2_material_evidence_audit_event_id",
        ),
        CheckConstraint(
            "event_type = 'snapshot_created'",
            name="ck_v2_material_evidence_audit_event_type",
        ),
        CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_material_evidence_audit_event_hash",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_evidence_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(
        _MATERIAL_RULESET_JSON, nullable=False
    )
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceReviewDossier(Base):
    """Stable tenant-scoped 01C review family for one exact 01A snapshot."""

    __tablename__ = "v2_material_evidence_review_dossiers"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "evidence_snapshot_id",
            name="uq_v2_mat_evid_review_tenant_evidence",
        ),
        CheckConstraint(
            "length(review_id) = 36 AND review_id LIKE 'mer_%'",
            name="ck_v2_mat_evid_review_id",
        ),
        CheckConstraint(
            "creator_identity_kind = 'verified_human'",
            name="ck_v2_mat_evid_review_creator_human",
        ),
    )

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_evidence_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    creator_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    creator_identity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceReviewSnapshot(Base):
    """Immutable content-addressed 01C factual review dossier."""

    __tablename__ = "v2_material_evidence_review_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "review_id",
            "content_sha256",
            name="uq_v2_mat_evid_review_snapshot_content",
        ),
        CheckConstraint(
            "length(review_snapshot_id) = 68 AND review_snapshot_id LIKE 'mrv_%'",
            name="ck_v2_mat_evid_review_snapshot_id",
        ),
        CheckConstraint(
            "review_schema_version = 1 AND canonicalization_version = 1 AND "
            "mat_evid_review_contract_version = 'MAT-EVID-01C.v1'",
            name="ck_v2_mat_evid_review_snapshot_contract",
        ),
        CheckConstraint(
            "evidence_manifest_schema_version = 1 AND "
            "evidence_contract_version = 'MAT-EVID-01A.v1'",
            name="ck_v2_mat_evid_review_evidence_contract",
        ),
        CheckConstraint(
            "length(content_sha256) = 64 AND length(evidence_content_sha256) = 64",
            name="ck_v2_mat_evid_review_snapshot_hashes",
        ),
        CheckConstraint(
            "runtime_authority = 'FACTUAL_REVIEW_ONLY' AND "
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_review_no_runtime_authority",
        ),
    )

    review_snapshot_id: Mapped[str] = mapped_column(String(68), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "v2_material_evidence_review_dossiers.review_id", ondelete="RESTRICT"
        ),
        nullable=False,
        index=True,
    )
    evidence_snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_evidence_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    evidence_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_manifest_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    evidence_contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    review_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    canonicalization_version: Mapped[int] = mapped_column(Integer, nullable=False)
    mat_evid_review_contract_version: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_payload_json: Mapped[dict] = mapped_column(
        _MATERIAL_RULESET_JSON, nullable=False
    )
    canonical_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    runtime_authority: Mapped[str] = mapped_column(String(32), nullable=False)
    positive_statement_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceReviewValidationEvent(Base):
    """Append-only technical validation; not a factual review event."""

    __tablename__ = "v2_material_evidence_review_validation_events"
    __table_args__ = (
        CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mvv_%'",
            name="ck_v2_mat_evid_review_validation_id",
        ),
        CheckConstraint(
            "validation_state = 'valid' AND error_code = 'none'",
            name="ck_v2_mat_evid_review_validation_state",
        ),
        CheckConstraint(
            "length(validation_sha256) = 64",
            name="ck_v2_mat_evid_review_validation_hash",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey(
            "v2_material_evidence_review_snapshots.review_snapshot_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    validator_contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_state: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceReviewLifecycleEvent(Base):
    """Hash-chained append-only human review/approval event."""

    __tablename__ = "v2_material_evidence_review_lifecycle_events"
    __table_args__ = (
        CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mrl_%'",
            name="ck_v2_mat_evid_review_lifecycle_id",
        ),
        UniqueConstraint(
            "review_snapshot_id",
            "sequence_no",
            name="uq_v2_mat_evid_review_lifecycle_sequence",
        ),
        CheckConstraint(
            "event_type IN ('reviewed','rejected','approved','revoked','quarantined')",
            name="ck_v2_mat_evid_review_lifecycle_type",
        ),
        CheckConstraint(
            "review_state IN ('draft','reviewed','rejected','revoked','quarantined')",
            name="ck_v2_mat_evid_review_state",
        ),
        CheckConstraint(
            "approval_state IN ('not_approved','approved','revoked','quarantined')",
            name="ck_v2_mat_evid_approval_state",
        ),
        CheckConstraint(
            "actor_role IN ('material_evidence:review','material_evidence:approve')",
            name="ck_v2_mat_evid_review_actor_role",
        ),
        CheckConstraint(
            "actor_identity_kind = 'verified_human'",
            name="ck_v2_mat_evid_review_actor_human",
        ),
        CheckConstraint(
            "sequence_no > 0 AND length(previous_event_sha256) = 64 AND "
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_review_lifecycle_hashes",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey(
            "v2_material_evidence_review_snapshots.review_snapshot_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    review_state: Mapped[str] = mapped_column(String(16), nullable=False)
    approval_state: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_identity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialEvidenceReviewAuditEvent(Base):
    """Append-only technical creation audit for an immutable review snapshot."""

    __tablename__ = "v2_material_evidence_review_audit_events"
    __table_args__ = (
        CheckConstraint(
            "length(event_id) = 36 AND event_id LIKE 'mra_%'",
            name="ck_v2_mat_evid_review_audit_id",
        ),
        CheckConstraint(
            "event_type = 'review_snapshot_created'",
            name="ck_v2_mat_evid_review_audit_type",
        ),
        CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_review_audit_hash",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey(
            "v2_material_evidence_review_snapshots.review_snapshot_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(
        _MATERIAL_RULESET_JSON, nullable=False
    )
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class V2MaterialShadowBinding(Base):
    """Immutable pointerless binding to one exact MAT-GOV-03A snapshot."""

    __tablename__ = "v2_material_shadow_bindings"
    __table_args__ = (
        CheckConstraint(
            "length(binding_id) = 37 AND binding_id LIKE 'mshb_%'",
            name="ck_v2_material_shadow_binding_id",
        ),
        CheckConstraint(
            "binding_schema_version = 1",
            name="ck_v2_material_shadow_binding_schema_v1",
        ),
        CheckConstraint(
            "purpose = 'MATERIAL_RULESET_SHADOW'",
            name="ck_v2_material_shadow_purpose",
        ),
        CheckConstraint(
            "environment IN ('development','staging','production')",
            name="ck_v2_material_shadow_environment",
        ),
        CheckConstraint(
            "scope_kind IN ('GLOBAL','TENANT_CANARY')",
            name="ck_v2_material_shadow_scope_kind",
        ),
        CheckConstraint(
            "(scope_kind = 'GLOBAL' AND tenant_ref_hmac IS NULL AND "
            "hmac_key_id IS NULL) OR "
            "(scope_kind = 'TENANT_CANARY' AND "
            "length(tenant_ref_hmac) = 64 AND hmac_key_id IS NOT NULL "
            "AND length(hmac_key_id) > 0)",
            name="ck_v2_material_shadow_scope_tenant",
        ),
        CheckConstraint(
            "length(content_sha256) = 64 AND content_sha256 = lower(content_sha256)",
            name="ck_v2_material_shadow_content_hash",
        ),
        CheckConstraint(
            "length(runtime_profile_sha256) = 64",
            name="ck_v2_material_shadow_runtime_hash",
        ),
        CheckConstraint(
            "valid_until > valid_from",
            name="ck_v2_material_shadow_valid_interval",
        ),
        CheckConstraint(
            "sampling_basis_points = 0",
            name="ck_v2_material_shadow_sampling_zero",
        ),
    )

    binding_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    binding_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_ruleset_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_ref_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hmac_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    domain_pack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain_pack_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    kernel_version: Mapped[str] = mapped_column(String(128), nullable=False)
    runtime_profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    build_git_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    build_tree_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    valid_from: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_until: Mapped[str] = mapped_column(String(32), nullable=False)
    creator_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    sampling_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    sampling_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialShadowBindingEvent(Base):
    __tablename__ = "v2_material_shadow_binding_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CREATED','REVOKED','TERMINATED')",
            name="ck_v2_material_shadow_binding_event_type",
        ),
        CheckConstraint(
            "event_schema_version = 1",
            name="ck_v2_material_shadow_binding_event_schema_v1",
        ),
        CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_material_shadow_binding_event_hash",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    event_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_bindings.binding_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    effective_at: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class V2MaterialShadowPin(Base):
    __tablename__ = "v2_material_shadow_pins"
    __table_args__ = (
        CheckConstraint(
            "authority = 'SHADOW_NON_AUTHORITATIVE'",
            name="ck_v2_material_shadow_pin_authority",
        ),
        CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_material_shadow_pin_no_positive",
        ),
        CheckConstraint(
            "sampled IS FALSE",
            name="ck_v2_material_shadow_pin_unsampled",
        ),
        CheckConstraint(
            "pin_schema_version = 1",
            name="ck_v2_material_shadow_pin_schema_v1",
        ),
        CheckConstraint(
            "length(content_sha256) = 64 AND "
            "length(runtime_profile_sha256) = 64 AND "
            "length(tenant_ref_hmac) = 64",
            name="ck_v2_material_shadow_pin_hashes",
        ),
    )

    pin_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    pin_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_bindings.binding_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_ruleset_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    tenant_ref_hmac: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hmac_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_pack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain_pack_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    kernel_version: Mapped[str] = mapped_column(String(128), nullable=False)
    runtime_profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    build_git_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    build_tree_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    sampling_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    sampled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    authority: Mapped[str] = mapped_column(String(32), nullable=False)
    positive_statement_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    acquired_at: Mapped[str] = mapped_column(String(32), nullable=False)
    binding_valid_until: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialShadowSessionVersion(Base):
    __tablename__ = "v2_material_shadow_session_versions"
    __table_args__ = (
        UniqueConstraint(
            "hmac_key_id",
            "tenant_ref_hmac",
            "session_ref_hmac",
            "version_no",
            name="uq_v2_material_shadow_session_version",
        ),
        CheckConstraint("version_no > 0", name="ck_v2_material_shadow_session_version"),
        CheckConstraint(
            "length(tenant_ref_hmac) = 64 AND length(session_ref_hmac) = 64",
            name="ck_v2_material_shadow_session_hmac",
        ),
        Index(
            "ix_v2_material_shadow_session_identity",
            "hmac_key_id",
            "tenant_ref_hmac",
            "session_ref_hmac",
        ),
    )

    session_version_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    tenant_ref_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    session_ref_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    hmac_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    pin_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_pins.pin_id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialShadowSessionUpgradeEvent(Base):
    __tablename__ = "v2_material_shadow_session_upgrade_events"
    __table_args__ = (
        UniqueConstraint(
            "from_session_version_id",
            name="uq_v2_material_shadow_session_upgrade_from",
        ),
        UniqueConstraint(
            "to_session_version_id",
            name="uq_v2_material_shadow_session_upgrade_to",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    from_session_version_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey(
            "v2_material_shadow_session_versions.session_version_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    to_session_version_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey(
            "v2_material_shadow_session_versions.session_version_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialShadowOutbox(Base):
    __tablename__ = "v2_material_shadow_outbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_v2_material_shadow_outbox_idem"),
        UniqueConstraint(
            "session_version_id",
            "sequence_no",
            name="uq_v2_material_shadow_session_sequence",
        ),
        CheckConstraint("sequence_no > 0", name="ck_v2_material_shadow_sequence"),
        CheckConstraint(
            "status IN ('pending','processing','done','failed')",
            name="ck_v2_material_shadow_job_status",
        ),
        CheckConstraint(
            "material_state = 'known' AND medium_state = 'known' AND "
            "medium_cardinality = 'single' AND relation_state = 'not_applicable'",
            name="ck_v2_material_shadow_job_eligible_input",
        ),
        CheckConstraint(
            "attempts >= 0 AND length(correlation_hmac) = 64 AND "
            "length(input_fingerprint) = 64 AND length(idempotency_key) = 64 AND "
            "(case_ref_hmac IS NULL OR length(case_ref_hmac) = 64) AND "
            "(decision_ref_hmac IS NULL OR length(decision_ref_hmac) = 64)",
            name="ck_v2_material_shadow_job_integrity",
        ),
        CheckConstraint(
            "(status = 'processing' AND attempts > 0 AND claimed_at IS NOT NULL "
            "AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(status <> 'processing' AND lease_owner IS NULL "
            "AND lease_expires_at IS NULL)",
            name="ck_v2_material_shadow_job_lease_state",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    pin_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_pins.pin_id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_version_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey(
            "v2_material_shadow_session_versions.session_version_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    hmac_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    case_ref_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_ref_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    material_id: Mapped[str] = mapped_column(String(128), nullable=False)
    medium_id: Mapped[str] = mapped_column(String(128), nullable=False)
    material_state: Mapped[str] = mapped_column(String(16), nullable=False)
    medium_state: Mapped[str] = mapped_column(String(16), nullable=False)
    medium_cardinality: Mapped[str] = mapped_column(String(16), nullable=False)
    relation_state: Mapped[str] = mapped_column(String(24), nullable=False)
    domain_pack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain_pack_version: Mapped[str] = mapped_column(String(128), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    stable_error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    claimed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_attempt_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class V2MaterialShadowEvaluation(Base):
    __tablename__ = "v2_material_shadow_evaluations"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_v2_material_shadow_evaluation_job"),
        CheckConstraint(
            "authority = 'SHADOW_NON_AUTHORITATIVE'",
            name="ck_v2_material_shadow_eval_authority",
        ),
        CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_material_shadow_eval_no_positive",
        ),
        CheckConstraint(
            "evaluation_state IN ('evaluated','blocked','no_rule_data',"
            "'ineligible_unresolved_input','revoked','integrity_blocked',"
            "'cache_unavailable','retry_exhausted')",
            name="ck_v2_material_shadow_eval_state",
        ),
        CheckConstraint(
            "(evaluation_state = 'evaluated' AND "
            "verdict IN ('vertraeglich','unvertraeglich','bedingt') AND "
            "decisive_ref IS NOT NULL) OR "
            "(evaluation_state <> 'evaluated' AND verdict IS NULL AND "
            "decisive_ref IS NULL)",
            name="ck_v2_material_shadow_eval_verdict",
        ),
        CheckConstraint(
            "length(result_sha256) = 64",
            name="ck_v2_material_shadow_eval_hash",
        ),
    )

    evaluation_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_outbox.job_id", ondelete="RESTRICT"),
        nullable=False,
    )
    pin_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_pins.pin_id", ondelete="RESTRICT"),
        nullable=False,
    )
    hmac_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_state: Mapped[str] = mapped_column(String(40), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decisive_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stable_error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    authority: Mapped[str] = mapped_column(String(32), nullable=False)
    positive_statement_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialShadowEvaluationMatch(Base):
    __tablename__ = "v2_material_shadow_evaluation_matches"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id", "rule_ref", name="uq_v2_material_shadow_eval_match"
        ),
        CheckConstraint(
            "verdict IN ('vertraeglich','unvertraeglich','bedingt')",
            name="ck_v2_material_shadow_match_verdict",
        ),
        CheckConstraint(
            "source_ref = 'matrix-cell:' || rule_ref",
            name="ck_v2_material_shadow_match_source",
        ),
    )

    match_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_evaluations.evaluation_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rule_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(256), nullable=False)


class V2MaterialShadowEvaluationRef(Base):
    __tablename__ = "v2_material_shadow_evaluation_refs"
    __table_args__ = (
        CheckConstraint(
            "ref_kind IN ('REQUEST','SESSION','CASE','DECISION')",
            name="ck_v2_material_shadow_ref_kind",
        ),
        CheckConstraint(
            "authority = 'SHADOW_NON_AUTHORITATIVE'",
            name="ck_v2_material_shadow_ref_authority",
        ),
        CheckConstraint(
            "length(ref_hmac) = 64",
            name="ck_v2_material_shadow_ref_hmac",
        ),
        UniqueConstraint(
            "evaluation_id", "ref_kind", "ref_hmac", name="uq_v2_material_shadow_ref"
        ),
    )

    ref_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_evaluations.evaluation_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ref_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    hmac_key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    authority: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialEvidenceRuntimeBinding(Base):
    """Immutable 01B companion to one exact pointerless shadow binding."""

    __tablename__ = "v2_material_evidence_runtime_bindings"
    __table_args__ = (
        CheckConstraint(
            "binding_state IN ('unbound','bound_unreviewed')",
            name="ck_v2_mat_evid_runtime_binding_state",
        ),
        CheckConstraint(
            "binding_schema_version = 1 AND "
            "binding_contract_version = 'MAT-EVID-01B.v1'",
            name="ck_v2_mat_evid_runtime_binding_contract",
        ),
        CheckConstraint(
            "length(ruleset_content_sha256) = 64",
            name="ck_v2_mat_evid_runtime_binding_ruleset_hash",
        ),
        CheckConstraint(
            "(binding_state = 'unbound' AND evidence_snapshot_id IS NULL AND "
            "evidence_content_sha256 IS NULL AND "
            "evidence_manifest_schema_version IS NULL AND "
            "evidence_canonicalization_version IS NULL AND "
            "evidence_contract_version IS NULL AND authority = 'NONE') OR "
            "(binding_state = 'bound_unreviewed' AND "
            "evidence_snapshot_id IS NOT NULL AND "
            "length(evidence_content_sha256) = 64 AND "
            "evidence_manifest_schema_version = 1 AND "
            "evidence_canonicalization_version = 1 AND "
            "evidence_contract_version = 'MAT-EVID-01A.v1' AND "
            "authority = 'TECHNICAL_UNREVIEWED')",
            name="ck_v2_mat_evid_runtime_binding_evidence_identity",
        ),
        CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_binding_no_positive",
        ),
    )

    binding_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_bindings.binding_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    binding_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    binding_state: Mapped[str] = mapped_column(String(24), nullable=False)
    ruleset_snapshot_id: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_ruleset_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    ruleset_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_snapshot_id: Mapped[str | None] = mapped_column(
        String(68),
        ForeignKey("v2_material_evidence_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=True,
    )
    evidence_content_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    evidence_manifest_schema_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    evidence_canonicalization_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    evidence_contract_version: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    domain_pack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    domain_pack_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    kernel_version: Mapped[str] = mapped_column(String(128), nullable=False)
    authority: Mapped[str] = mapped_column(String(32), nullable=False)
    positive_statement_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialEvidenceRuntimePin(Base):
    """Immutable evidence companion for one exact 03B pin."""

    __tablename__ = "v2_material_evidence_runtime_pins"
    __table_args__ = (
        CheckConstraint(
            "pin_schema_version = 1",
            name="ck_v2_mat_evid_runtime_pin_schema",
        ),
        CheckConstraint(
            "binding_state IN ('unbound','bound_unreviewed')",
            name="ck_v2_mat_evid_runtime_pin_state",
        ),
        CheckConstraint(
            "length(ruleset_content_sha256) = 64",
            name="ck_v2_mat_evid_runtime_pin_ruleset_hash",
        ),
        CheckConstraint(
            "(binding_state = 'unbound' AND evidence_snapshot_id IS NULL AND "
            "evidence_content_sha256 IS NULL AND authority = 'NONE') OR "
            "(binding_state = 'bound_unreviewed' AND "
            "evidence_snapshot_id IS NOT NULL AND "
            "length(evidence_content_sha256) = 64 AND "
            "authority = 'TECHNICAL_UNREVIEWED')",
            name="ck_v2_mat_evid_runtime_pin_evidence_identity",
        ),
        CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_pin_no_positive",
        ),
    )

    pin_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_pins.pin_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    pin_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey(
            "v2_material_evidence_runtime_bindings.binding_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    binding_state: Mapped[str] = mapped_column(String(24), nullable=False)
    ruleset_snapshot_id: Mapped[str] = mapped_column(String(68), nullable=False)
    ruleset_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_snapshot_id: Mapped[str | None] = mapped_column(String(68), nullable=True)
    evidence_content_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    authority: Mapped[str] = mapped_column(String(32), nullable=False)
    positive_statement_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialEvidenceRuntimeEvaluation(Base):
    """Reference-only evidence envelope for one shadow evaluation."""

    __tablename__ = "v2_material_evidence_runtime_evaluations"
    __table_args__ = (
        CheckConstraint(
            "binding_state IN ('unbound','bound_unreviewed')",
            name="ck_v2_mat_evid_runtime_eval_state",
        ),
        CheckConstraint(
            "length(result_sha256) = 64",
            name="ck_v2_mat_evid_runtime_eval_hash",
        ),
        CheckConstraint(
            "positive_statement_allowed IS FALSE",
            name="ck_v2_mat_evid_runtime_eval_no_positive",
        ),
    )

    evaluation_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_shadow_evaluations.evaluation_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    pin_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey("v2_material_evidence_runtime_pins.pin_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    binding_state: Mapped[str] = mapped_column(String(24), nullable=False)
    ruleset_snapshot_id: Mapped[str] = mapped_column(String(68), nullable=False)
    ruleset_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_snapshot_id: Mapped[str | None] = mapped_column(String(68), nullable=True)
    evidence_content_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stable_error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    authority: Mapped[str] = mapped_column(String(32), nullable=False)
    positive_statement_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class V2MaterialEvidenceRuntimeEvaluationRef(Base):
    __tablename__ = "v2_material_evidence_runtime_evaluation_refs"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            "rule_ref",
            "claim_ref",
            "source_ref",
            name="uq_v2_mat_evid_runtime_eval_ref",
        ),
    )

    ref_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey(
            "v2_material_evidence_runtime_evaluations.evaluation_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    rule_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    claim_ref: Mapped[str] = mapped_column(String(68), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(68), nullable=False)


class V2MaterialEvidenceRuntimeAuditEvent(Base):
    __tablename__ = "v2_material_evidence_runtime_audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('binding_created','pin_created',"
            "'evaluation_created','integrity_blocked')",
            name="ck_v2_mat_evid_runtime_audit_type",
        ),
        CheckConstraint(
            "length(event_sha256) = 64",
            name="ck_v2_mat_evid_runtime_audit_hash",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    binding_id: Mapped[str] = mapped_column(
        String(37),
        ForeignKey(
            "v2_material_evidence_runtime_bindings.binding_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    pin_id: Mapped[str | None] = mapped_column(
        String(37),
        ForeignKey("v2_material_evidence_runtime_pins.pin_id", ondelete="RESTRICT"),
        nullable=True,
    )
    evaluation_id: Mapped[str | None] = mapped_column(
        String(37),
        ForeignKey(
            "v2_material_evidence_runtime_evaluations.evaluation_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    event_payload_json: Mapped[dict] = mapped_column(
        _MATERIAL_RULESET_JSON, nullable=False
    )
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
