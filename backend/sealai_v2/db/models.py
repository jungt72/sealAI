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

from sqlalchemy import JSON, Integer, String, Text
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
