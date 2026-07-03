"""Curated memory domain types — sealingAI Memory Architecture V1.0, Patch 1 (Types & Schemas),
reconciled against "sealingAI Memory Architecture V1.0 — Finales Konzept" (2026-07-03) in Patch 9.

RECONCILIATION NOTE (Patch 9): Patch 1 built ``MemoryType`` as a 3-value INFERENCE (flagged
explicitly at the time — the earlier source prompt named only preference/technical_note/
case_parameter in prose, without an exhaustive enum the way Status/Scope had one). The final,
authoritative concept doc DOES give the full 9-value enum — this module now matches it exactly.
The inference was directionally correct (all 3 original values are a subset of the real 9) but
incomplete; nothing built against the smaller set needs to change, it only gains new values.

This is the CURATED, cross-session, owner-confirmable memory tier the existing
``db/cross_session_memory.py`` (Layer 4) explicitly deferred: "the broader CURATED cross-session
sub-gate (what to promote, vector retrieval) stays deferred". These types are the domain shape a
later patch persists as ``memory_items`` (Patch 2) and syncs to Qdrant via an outbox (Patch 5) —
this module does NOT touch persistence, it only defines PURE, dependency-free vocabulary (no I/O,
no SQLAlchemy, no Qdrant import), matching this codebase's ``core/`` discipline.

Doctrine (product doctrine, not to be relaxed by a later patch):
- Memory is context, not truth. Postgres is the system-of-record; Qdrant is a retrieval index only.
- Case-State, Kernel and RAG sources take precedence over Memory (Leitsatz L1/L6).
- Memory never alone justifies technical suitability.
- A ``rejected``/``deprecated``/``deleted_*``/``purged`` item is NEVER usable as context — a later
  patch's Postgres-revalidation step (Patch 6) is what actually enforces this against a possibly
  stale Qdrant mirror; this module only defines the status vocabulary that enforcement checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MemoryScope(str, Enum):
    """The scope level a curated memory item is bound to. Broader scopes (user/workspace/tenant)
    are candidate global context; narrower ones (project/case/session) are read alongside broader
    ones per the context assembler's precedence rules (Patch 8) — never instead of them."""

    USER = "user"
    WORKSPACE = "workspace"
    TENANT = "tenant"
    PROJECT = "project"
    CASE = "case"
    SESSION = "session"


class MemoryType(str, Enum):
    """What KIND of thing a memory item records — drives the per-type policy (Patch 7's
    ``policy.py``). Full 9-value set per the final concept doc §3 (Patch 9 reconciliation);
    ``usage_for()`` currently has explicit policy rules for preference/implicit_context-status/
    technical_note/case_parameter (the four the final concept's §7 policy table spells out) — the
    other five fall through to the fail-closed NEVER default until a later patch defines their
    policy explicitly (matches this codebase's "wire the field, gate the behavior" discipline)."""

    PREFERENCE = "preference"  # style/UX preference — policy: style_only, never a technical input
    WORKFLOW_INSTRUCTION = "workflow_instruction"  # e.g. "RFQ-Briefe immer kurz halten"
    PROJECT_CONTEXT = "project_context"  # standing project-level facts (non-technical)
    CASE_PARAMETER = (
        "case_parameter"  # a concrete case fact — policy: confirmed + case-scope only
    )
    TECHNICAL_NOTE = "technical_note"  # a technical hint — policy: context_only, never a recommendation
    MANUFACTURER_FEEDBACK = (
        "manufacturer_feedback"  # e.g. a supplier's stated capability/preference
    )
    RFQ_PATTERN = (
        "rfq_pattern"  # recurring RFQ shape/preference for a customer or project
    )
    RISK_NOTE = (
        "risk_note"  # a flagged risk observation, never itself a technical verdict
    )
    CONVERSATION_SUMMARY = (
        "conversation_summary"  # a condensed prior-conversation digest
    )


class MemoryStatus(str, Enum):
    """Curation lifecycle a memory item moves through. ``IMPLICIT_CONTEXT`` is a STATUS (not a
    type): an item in this status may only trigger a clarifying question (Patch 7 policy), never a
    recommendation, and is never treated as confirmed knowledge. The terminal states
    (``rejected``/``deprecated``/``deleted_pending_purge``/``purged``) must never be usable as
    context regardless of type or scope."""

    CANDIDATE = "candidate"
    IMPLICIT_CONTEXT = "implicit_context"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    DELETED_PENDING_PURGE = "deleted_pending_purge"
    PURGED = "purged"


# Statuses that a Postgres-revalidation step (Patch 6) must NEVER let through into a prompt, even if
# a stale Qdrant mirror still returns them. Centralized here so every later patch checks the SAME
# set rather than re-deriving it (and risking divergence).
NEVER_INJECTABLE_STATUSES: frozenset[MemoryStatus] = frozenset(
    {
        MemoryStatus.REJECTED,
        MemoryStatus.DEPRECATED,
        MemoryStatus.DELETED_PENDING_PURGE,
        MemoryStatus.PURGED,
    }
)


# Status-transition state machine (Patch 4). CANDIDATE/IMPLICIT_CONTEXT can be confirmed, rejected, or
# deleted directly — a user hasn't committed to anything yet. CONFIRMED can only be deprecated (a new
# fact supersedes it) or deleted, never re-rejected (it was already accepted; "wrong now" is a
# deprecation, not an un-confirmation — keeps the audit trail honest about what was actually true when).
# REJECTED/DEPRECATED can only move to DELETED_PENDING_PURGE. DELETED_PENDING_PURGE/PURGED are terminal
# from the status-action API's perspective — only the purge job (Patch 14) advances past them.
_VALID_TRANSITIONS: dict[MemoryStatus, frozenset[MemoryStatus]] = {
    MemoryStatus.CANDIDATE: frozenset(
        {
            MemoryStatus.CONFIRMED,
            MemoryStatus.REJECTED,
            MemoryStatus.DELETED_PENDING_PURGE,
        }
    ),
    MemoryStatus.IMPLICIT_CONTEXT: frozenset(
        {
            MemoryStatus.CONFIRMED,
            MemoryStatus.REJECTED,
            MemoryStatus.DELETED_PENDING_PURGE,
        }
    ),
    MemoryStatus.CONFIRMED: frozenset(
        {MemoryStatus.DEPRECATED, MemoryStatus.DELETED_PENDING_PURGE}
    ),
    MemoryStatus.REJECTED: frozenset({MemoryStatus.DELETED_PENDING_PURGE}),
    MemoryStatus.DEPRECATED: frozenset({MemoryStatus.DELETED_PENDING_PURGE}),
    MemoryStatus.DELETED_PENDING_PURGE: frozenset(),
    MemoryStatus.PURGED: frozenset(),
}


def is_valid_transition(from_status: MemoryStatus, to_status: MemoryStatus) -> bool:
    """Pure state-machine check — the single source of truth both the API layer (for a clean 409)
    and the store's write path (defense in depth) consult, so the two can never disagree."""
    return to_status in _VALID_TRANSITIONS.get(from_status, frozenset())


@dataclass(frozen=True)
class MemorySource:
    """Provenance for a memory item — mandatory per doctrine ("Keine Memory-Schreibvorgänge ohne
    Source/Provenance"). ``kind`` is a free-form tag (e.g. "user_stated", "llm_inferred",
    "owner_manual_entry") rather than its own enum for now — Patch 1 doesn't have enough real
    extraction cases yet to know the full set; revisit once Patch 12 (extraction) lands real data.

    Patch 9 reconciliation: the final concept doc models ``memory_sources`` as a normalized
    source-CATALOG (one row per message/document/case-snapshot, referenced by id) rather than a
    one-to-many provenance-note list per item. Deliberately NOT restructured to match that exactly —
    the existing one-to-many model (multiple sources per item, already required + tested end-to-end
    since Patch 3) is a legitimate, arguably richer alternative normalization, and rebuilding it
    would invalidate significant already-shipped, already-tested surface for no functional gain.
    Instead this dataclass gains the specific REFERENCE fields the final doc calls for, so the same
    provenance information is captured either way."""

    kind: str
    session_id: str | None = None
    turn_id: str | None = None
    note: str = ""
    # Patch 9 additions (final concept doc §7 memory_sources columns):
    source_ref: str | None = None  # a human/URI-ish reference to the source (free-form)
    message_id: str | None = (
        None  # the specific chat message this was extracted from, if any
    )
    document_id: str | None = None  # the specific uploaded/ingested document, if any
    case_snapshot_id: str | None = None  # the specific case-state snapshot, if any


@dataclass(frozen=True)
class MemoryItem:
    """One curated memory record — the domain shape Patch 2 persists as ``memory_items``. PURE (no
    I/O, no SQLAlchemy, no timestamps generated here) — the persistence layer maps to/from this
    shape, this module never reads a clock or a database.

    ``semantic_key`` is the stable dedup/conflict-detection key Patch 13 (Conflict Detection &
    Consolidation) matches on — e.g. a normalized (scope, type, subject) hash, not the free-text
    content itself (two differently-worded statements of the same fact must collide on this key).
    """

    id: str
    tenant_id: str
    scope: MemoryScope
    scope_id: (
        str  # the concrete user_id/workspace_id/tenant_id/project_id/case_id/session_id
    )
    type: MemoryType
    status: MemoryStatus
    content: str
    semantic_key: str
    sources: tuple[MemorySource, ...] = field(default_factory=tuple)
    version: int = 1
    # Timestamps are ISO-8601 strings stamped by the persistence layer (Patch 2), never generated
    # in this pure module — matches the workflow-script "no Date.now() in pure code" discipline
    # already followed elsewhere in this codebase.
    created_at: str = ""
    updated_at: str = ""
    deleted_at: str | None = None
    purge_after: str | None = None
    # Patch 9 reconciliation (final concept doc §7 memory_items columns):
    # How confident the source (extraction, manual entry) is in this item's content — [0.0, 1.0].
    # Wired here + persisted (Patch 2 extension) but NOT yet consumed by usage_for() (Patch 7) — a
    # later patch's policy refinement, not invented speculatively now without a concrete rule.
    confidence: float = 1.0
    # A free-form data-classification tag (e.g. "internal", "customer_confidential") — no exhaustive
    # enum given in the final concept doc (only one example value shown), so left as a string rather
    # than guessing a full taxonomy. Wired + persisted, not yet enforced by any access-control rule.
    sensitivity: str = "internal"
    # Conflict-detection keys (Patch 13's own scope) — wired now so Patch 2's schema doesn't need a
    # second migration later. subject_hash identifies "the same real-world subject" independent of
    # semantic_key (which identifies "the same claim shape"); supersedes/deprecated_by link items in
    # a resolved-conflict chain. All None until Patch 13 actually populates them.
    subject_hash: str | None = None
    supersedes_memory_id: str | None = None
    deprecated_by_memory_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError(
                "tenant_id is mandatory (P0 repository-layer scope, same as Layer 1-4)"
            )
        if not self.scope_id.strip():
            raise ValueError(
                "scope_id is mandatory — a scope without a concrete binding is a leak risk"
            )
        if not self.semantic_key.strip():
            raise ValueError(
                "semantic_key is mandatory (Patch 13 conflict detection needs it)"
            )

    @property
    def is_injectable(self) -> bool:
        """True only when this item's status is safe to surface as context. Pure, deterministic —
        the actual enforcement point is Patch 6's Postgres-revalidation, which re-checks the LIVE
        status (this property just centralizes the rule so both sides agree on what it means)."""
        return self.status not in NEVER_INJECTABLE_STATUSES
