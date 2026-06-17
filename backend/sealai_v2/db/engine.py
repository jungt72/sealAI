"""V2 persistence engine — sync SQLAlchemy 2.0 (build-spec §3).

Own engine + declarative ``Base`` + sessionmaker; never imports ``app.*`` (green-field boundary).
Sync by design: the memory Protocols (``core.contracts``) are synchronous, so a sync adapter is a
true drop-in behind them with zero contract change. The hot-path reads are tiny indexed lookups;
an async adapter is a future latency optimization, not a durability requirement.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for the sealai_v2 schema. Own base (no ``app.*`` import) so the V2 tables
    are a self-contained, cleanly-deletable unit."""


def make_engine(url: str) -> Engine:
    """Build a sync engine. ``pool_pre_ping`` transparently replaces a connection dropped by an idle
    backend / a Postgres restart instead of surfacing a dead-connection error on the hot path. sqlite
    (offline tests) needs ``check_same_thread=False`` so a file DB is shared across threads/sessions."""
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        url, pool_pre_ping=True, future=True, connect_args=connect_args
    )


def make_sessionmaker(engine: Engine) -> sessionmaker:
    """``expire_on_commit=False`` so attribute reads after a commit don't trigger a fresh SELECT
    (the adapters return detached domain objects, never the ORM rows)."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
