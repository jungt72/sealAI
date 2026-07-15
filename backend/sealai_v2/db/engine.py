"""V2 persistence engine — sync SQLAlchemy 2.0 (build-spec §3).

Own engine + declarative ``Base`` + sessionmaker; never imports ``app.*`` (green-field boundary).
Sync by design: the memory Protocols (``core.contracts``) are synchronous, so a sync adapter is a
true drop-in behind them with zero contract change. The hot-path reads are tiny indexed lookups;
an async adapter is a future latency optimization, not a durability requirement.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from enum import Enum
import re

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class DatabaseRuntimeRole(Enum):
    """Closed set of NOLOGIN roles installed by the GATE-07 cutover.

    Role identifiers cannot be SQL bind parameters. Keeping both the public enum and the emitted
    SQL in this module prevents an identity claim, request value, or environment string from ever
    becoming an identifier in ``SET LOCAL ROLE``.
    """

    API = "api"
    WORKER = "worker"
    TENANT_ADMIN = "tenant_admin"
    PLATFORM_OWNER = "platform_owner"
    SYSTEM_OPERATOR = "system_operator"


_ROLE_SQL = {
    DatabaseRuntimeRole.API: "SET LOCAL ROLE sealai_api",
    DatabaseRuntimeRole.WORKER: "SET LOCAL ROLE sealai_worker",
    DatabaseRuntimeRole.TENANT_ADMIN: "SET LOCAL ROLE sealai_tenant_admin",
    DatabaseRuntimeRole.PLATFORM_OWNER: "SET LOCAL ROLE sealai_platform_owner",
    DatabaseRuntimeRole.SYSTEM_OPERATOR: "SET LOCAL ROLE sealai_system_operator",
}
_ROLE_NAMES = {
    role: statement.removeprefix("SET LOCAL ROLE ")
    for role, statement in _ROLE_SQL.items()
}
_SCOPE_VALUE = re.compile(r"^[^\x00-\x1f\x7f]{1,255}$")


@dataclass(frozen=True)
class DatabaseRuntimeScope:
    """Verified transaction context copied into PostgreSQL transaction-local GUCs."""

    tenant_id: str
    subject_id: str
    case_id: str
    role: DatabaseRuntimeRole = DatabaseRuntimeRole.API

    def validated(self) -> "DatabaseRuntimeScope":
        if not isinstance(self.role, DatabaseRuntimeRole):
            raise TypeError("database runtime role must be a fixed DatabaseRuntimeRole")
        for name, value, required in (
            ("tenant_id", self.tenant_id, True),
            ("subject_id", self.subject_id, True),
            ("case_id", self.case_id, False),
        ):
            if not isinstance(value, str) or (required and not value.strip()):
                raise ValueError(f"database {name} is required")
            if value and _SCOPE_VALUE.fullmatch(value) is None:
                raise ValueError(f"database {name} contains an invalid value")
        return self


_DATABASE_SCOPE: ContextVar[DatabaseRuntimeScope | None] = ContextVar(
    "sealai_v2_database_scope", default=None
)


@contextmanager
def bind_database_scope(
    *,
    tenant_id: str,
    subject_id: str,
    case_id: str = "",
    role: DatabaseRuntimeRole = DatabaseRuntimeRole.API,
) -> Iterator[DatabaseRuntimeScope]:
    """Bind one verified request/service scope; nested scopes restore their predecessor."""

    scope = DatabaseRuntimeScope(
        tenant_id=tenant_id,
        subject_id=subject_id,
        case_id=case_id,
        role=role,
    ).validated()
    token = _DATABASE_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _DATABASE_SCOPE.reset(token)


@contextmanager
def elevate_database_role(role: DatabaseRuntimeRole) -> Iterator[DatabaseRuntimeScope]:
    """Select a privileged DB role only after the matching route guard authorized it."""

    if not isinstance(role, DatabaseRuntimeRole):
        raise TypeError("database runtime role must be a fixed DatabaseRuntimeRole")
    current = _DATABASE_SCOPE.get()
    if current is None:
        raise RuntimeError("database request scope is not bound")
    elevated = replace(current, role=role).validated()
    token = _DATABASE_SCOPE.set(elevated)
    try:
        yield elevated
    finally:
        _DATABASE_SCOPE.reset(token)


def current_database_scope() -> DatabaseRuntimeScope | None:
    """Read-only test/adapter seam; never synthesizes a fallback identity."""

    return _DATABASE_SCOPE.get()


@contextmanager
def bind_database_case(case_id: str) -> Iterator[DatabaseRuntimeScope | None]:
    """Narrow an authenticated request scope to the exact validated route/body case.

    Hermetic tests may override the entire identity dependency and use unscoped SQLite stores. In
    that lane this is a no-op; an enabled PostgreSQL runtime factory still independently rejects a
    missing scope before SQL, so the production boundary cannot inherit the test convenience.
    """

    current = _DATABASE_SCOPE.get()
    if current is None:
        yield None
        return
    narrowed = replace(current, case_id=case_id).validated()
    token = _DATABASE_SCOPE.set(narrowed)
    try:
        yield narrowed
    finally:
        _DATABASE_SCOPE.reset(token)


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
        url,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
        # SQLAlchemy exception rendering must never echo bound tenant/subject values or DSN data.
        hide_parameters=True,
    )


def make_sessionmaker(engine: Engine) -> sessionmaker:
    """``expire_on_commit=False`` so attribute reads after a commit don't trigger a fresh SELECT
    (the adapters return detached domain objects, never the ORM rows)."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _apply_runtime_scope(connection, scope: DatabaseRuntimeScope) -> None:
    """Apply one validated scope to the current transaction using only static identifier SQL."""

    scope.validated()
    connection.exec_driver_sql(_ROLE_SQL[scope.role])
    connection.execute(
        text(
            "SELECT "
            "set_config('app.tenant_id', :tenant_id, true), "
            "set_config('app.subject_id', :subject_id, true), "
            "set_config('app.case_id', :case_id, true)"
        ),
        {
            "tenant_id": scope.tenant_id,
            "subject_id": scope.subject_id,
            "case_id": scope.case_id,
        },
    )
    actual_role = connection.scalar(text("SELECT current_role"))
    if actual_role != _ROLE_NAMES[scope.role]:
        raise RuntimeError("database runtime role activation failed")


def make_runtime_sessionmaker(
    engine: Engine,
    *,
    allowed_roles: frozenset[DatabaseRuntimeRole],
    default_scope: DatabaseRuntimeScope | None = None,
) -> sessionmaker:
    """Build a PostgreSQL factory that binds role and GUCs at every root transaction.

    ``SET LOCAL`` and transaction-local ``set_config`` values disappear on commit/rollback before
    a pooled connection can be reused. Missing context and unexpected role selection fail before
    application SQL. A non-PostgreSQL engine is rejected so SQLite can never masquerade as RLS
    evidence.
    """

    if engine.dialect.name != "postgresql":
        raise RuntimeError("database runtime scoping requires PostgreSQL")
    if not allowed_roles or any(
        not isinstance(role, DatabaseRuntimeRole) for role in allowed_roles
    ):
        raise ValueError("database runtime factory requires fixed allowed roles")
    if default_scope is not None:
        default_scope.validated()
        if default_scope.role not in allowed_roles:
            raise ValueError("default database scope uses a disallowed role")

    factory = make_sessionmaker(engine)

    def _after_begin(_session, transaction, connection) -> None:
        if transaction.nested:
            return
        scope = _DATABASE_SCOPE.get() or default_scope
        if scope is None:
            raise RuntimeError("database transaction has no verified runtime scope")
        if scope.role not in allowed_roles:
            raise PermissionError(
                "database runtime role is not allowed for this process"
            )
        _apply_runtime_scope(connection, scope)

    event.listen(factory, "after_begin", _after_begin)
    return factory


_API_ROLES = frozenset(
    {
        DatabaseRuntimeRole.API,
        DatabaseRuntimeRole.TENANT_ADMIN,
        DatabaseRuntimeRole.PLATFORM_OWNER,
        DatabaseRuntimeRole.SYSTEM_OPERATOR,
    }
)


def make_api_sessionmaker(settings) -> sessionmaker:
    """Construct the API factory from the API-only URL and optional GATE-07 adapter."""

    url = getattr(settings, "database_url", None)
    if not url:
        raise RuntimeError("SEALAI_V2_DATABASE_URL is required for the API database")
    engine = make_engine(url)
    if not getattr(settings, "database_rls_scope_enabled", False):
        return make_sessionmaker(engine)
    return make_runtime_sessionmaker(engine, allowed_roles=_API_ROLES)


def make_worker_sessionmaker(settings) -> sessionmaker:
    """Construct the worker factory from its separate credential and fixed worker role."""

    url = getattr(settings, "worker_database_url", None)
    if not url:
        raise RuntimeError(
            "SEALAI_V2_WORKER_DATABASE_URL is required for the outbox worker"
        )
    engine = make_engine(url)
    if not getattr(settings, "database_rls_scope_enabled", False):
        return make_sessionmaker(engine)
    return make_runtime_sessionmaker(
        engine,
        allowed_roles=frozenset({DatabaseRuntimeRole.WORKER}),
        default_scope=DatabaseRuntimeScope(
            tenant_id="service:outbox",
            subject_id="service:outbox-worker",
            case_id="",
            role=DatabaseRuntimeRole.WORKER,
        ),
    )
