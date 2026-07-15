"""Opt-in PostgreSQL proof for the proposed GATE-07 role/RLS contract.

Nothing in this module discovers or falls back to an application DSN. It runs only when an
operator supplies a dedicated test DSN plus the explicit ephemeral confirmation. The entire proof,
including role creation, is one transaction that is rolled back.
"""

from __future__ import annotations

import os
import re
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

_DSN_ENV = "SEALAI_TEST_POSTGRES_DSN"
_CONFIRM_ENV = "SEALAI_TEST_POSTGRES_CONFIRM"
_CONFIRM_VALUE = "EPHEMERAL_ONLY"
_TEST_NAME = re.compile(r"(^|[_-])(test|ci|ephemeral)([_-]|$)", re.IGNORECASE)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _guard_test_dsn(raw_dsn: str) -> None:
    url = make_url(raw_dsn)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("GATE-07 integration requires a PostgreSQL test DSN")
    database = (url.database or "").strip()
    host = (url.host or "").strip().lower()
    if not _TEST_NAME.search(database):
        raise RuntimeError("test database name must contain test, ci, or ephemeral")
    if host not in _LOCAL_HOSTS and not _TEST_NAME.search(host):
        raise RuntimeError(
            "test PostgreSQL host must be loopback or explicitly test-named"
        )
    if os.getenv(_CONFIRM_ENV) != _CONFIRM_VALUE:
        raise RuntimeError(
            f"{_CONFIRM_ENV} must equal {_CONFIRM_VALUE} for the ephemeral proof"
        )


@pytest.fixture
def gate07_connection():
    raw_dsn = os.getenv(_DSN_ENV)
    if not raw_dsn:
        pytest.skip(f"set {_DSN_ENV} to an explicit ephemeral PostgreSQL DSN")
    _guard_test_dsn(raw_dsn)
    engine = create_engine(raw_dsn, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                actual_database = connection.scalar(text("SELECT current_database()"))
                if not _TEST_NAME.search(str(actual_database or "")):
                    pytest.fail(
                        "connected database does not satisfy the nonproduction name guard"
                    )
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _set_scope(connection, *, role: str, tenant: str, subject: str = "") -> None:
    connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant, true)"),
        {"tenant": tenant},
    )
    connection.execute(
        text("SELECT set_config('app.subject_id', :subject, true)"),
        {"subject": subject},
    )


def _visible_payloads(connection, *, schema: str) -> list[str]:
    return list(
        connection.scalars(
            text(f'SELECT payload FROM "{schema}".boundary_records ORDER BY payload')
        ).all()
    )


def test_force_rls_separates_service_worker_admin_and_operator_roles(
    gate07_connection,
) -> None:
    connection = gate07_connection
    suffix = uuid.uuid4().hex[:12]
    schema = f"gate07_{suffix}"
    owner = f"g07_owner_{suffix}"
    service = f"g07_service_{suffix}"
    worker = f"g07_worker_{suffix}"
    tenant_admin = f"g07_tenant_admin_{suffix}"
    operator = f"g07_operator_{suffix}"
    roles = (owner, service, worker, tenant_admin, operator)

    for role in roles:
        connection.exec_driver_sql(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
            "NOINHERIT NOBYPASSRLS"
        )
    connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    connection.exec_driver_sql(
        f'CREATE TABLE "{schema}".boundary_records ('
        "tenant_id text NOT NULL, owner_subject text NOT NULL, payload text NOT NULL)"
    )
    connection.execute(
        text(
            f'INSERT INTO "{schema}".boundary_records '
            "(tenant_id, owner_subject, payload) VALUES "
            "('tenant-a', 'alice', 'a-alice'), "
            "('tenant-a', 'bob', 'a-bob'), "
            "('tenant-b', 'carol', 'b-carol')"
        )
    )
    connection.exec_driver_sql(
        f'ALTER TABLE "{schema}".boundary_records OWNER TO "{owner}"'
    )
    connection.exec_driver_sql(
        f'GRANT USAGE ON SCHEMA "{schema}" TO '
        + ", ".join(f'"{role}"' for role in roles)
    )
    connection.exec_driver_sql(
        f'GRANT SELECT ON "{schema}".boundary_records TO '
        + ", ".join(f'"{role}"' for role in roles)
    )
    connection.exec_driver_sql(
        f'ALTER TABLE "{schema}".boundary_records ENABLE ROW LEVEL SECURITY'
    )
    connection.exec_driver_sql(
        f'CREATE POLICY service_owner ON "{schema}".boundary_records TO "{service}" '
        "USING (tenant_id = current_setting('app.tenant_id', true) "
        "AND owner_subject = current_setting('app.subject_id', true))"
    )
    connection.exec_driver_sql(
        f'CREATE POLICY worker_tenant ON "{schema}".boundary_records TO "{worker}" '
        "USING (tenant_id = current_setting('app.tenant_id', true))"
    )
    connection.exec_driver_sql(
        f'CREATE POLICY tenant_admin_scope ON "{schema}".boundary_records '
        f'TO "{tenant_admin}" '
        "USING (tenant_id = current_setting('app.tenant_id', true))"
    )
    connection.exec_driver_sql(
        f'CREATE POLICY operator_deny ON "{schema}".boundary_records TO "{operator}" '
        "USING (false)"
    )
    connection.exec_driver_sql(
        f'ALTER TABLE "{schema}".boundary_records FORCE ROW LEVEL SECURITY'
    )

    for role in roles:
        flags = connection.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                "FROM pg_roles WHERE rolname = :role"
            ),
            {"role": role},
        ).one()
        assert tuple(flags) == (False, False, False, False)

    _set_scope(connection, role=service, tenant="tenant-a", subject="alice")
    assert _visible_payloads(connection, schema=schema) == ["a-alice"]
    connection.exec_driver_sql("RESET ROLE")

    _set_scope(connection, role=worker, tenant="tenant-a", subject="worker")
    assert _visible_payloads(connection, schema=schema) == ["a-alice", "a-bob"]
    connection.exec_driver_sql("RESET ROLE")

    _set_scope(connection, role=tenant_admin, tenant="tenant-b", subject="admin")
    assert _visible_payloads(connection, schema=schema) == ["b-carol"]
    connection.exec_driver_sql("RESET ROLE")

    _set_scope(connection, role=operator, tenant="tenant-a", subject="operator")
    assert _visible_payloads(connection, schema=schema) == []
    connection.exec_driver_sql("RESET ROLE")

    _set_scope(connection, role=owner, tenant="tenant-a", subject="alice")
    assert _visible_payloads(connection, schema=schema) == []
    connection.exec_driver_sql("RESET ROLE")

    rls_flags = connection.execute(
        text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relname = 'boundary_records'"
        ),
        {"schema": schema},
    ).one()
    assert tuple(rls_flags) == (True, True)
