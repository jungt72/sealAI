"""Opt-in real-PostgreSQL proof for migrations + the exact GATE-07 cutover body.

The test never discovers a DSN. It requires the same explicit ephemeral-only environment guard as
the other GATE-07 proof and refuses a database that already contains any table. When no engine is
provided, pytest records a skip rather than substituting SQLite or a mock RLS implementation.
"""

from __future__ import annotations

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from sealai_v2.db.engine import (
    DatabaseRuntimeRole,
    bind_database_scope,
    elevate_database_role,
    make_engine,
    make_runtime_sessionmaker,
)
from sealai_v2.db.migrate import _upgrade_engine, down, migration_status
from sealai_v2.db.models import V2MemoryItem
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.security.lifecycle_control import (
    LifecyclePolicy,
    PostgresLifecycleControlStore,
)

_DSN_ENV = "SEALAI_TEST_POSTGRES_DSN"
_CONFIRM_ENV = "SEALAI_TEST_POSTGRES_CONFIRM"
_CONFIRM_VALUE = "EPHEMERAL_ONLY"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_PROTECTED_TABLES = (
    "v2_sessions",
    "v2_messages",
    "v2_facts",
    "v2_derived",
    "v2_interview_state",
    "v2_durable_facts",
    "v2_memory_items",
    "v2_leads",
    "v2_contributions",
    "v2_api_lifecycle_windows",
    "v2_api_lifecycle_admissions",
    "v2_api_lifecycle_receipts",
    "v2_api_lifecycle_events",
)
_CONSTRAINT_TABLES = {
    "ck_v2_sessions_boundary_shadow": "v2_sessions",
    "ck_v2_durable_facts_owner_shadow": "v2_durable_facts",
    "ck_v2_memory_items_owner_shadow": "v2_memory_items",
    "ck_v2_leads_case_owner_shadow": "v2_leads",
    "fk_v2_messages_session_shadow": "v2_messages",
    "fk_v2_facts_session_shadow": "v2_facts",
    "fk_v2_derived_session_shadow": "v2_derived",
    "fk_v2_interview_state_session_shadow": "v2_interview_state",
    "fk_v2_leads_case_shadow": "v2_leads",
    "ck_v2_contributions_lifecycle_shadow": "v2_contributions",
    "ck_v2_leads_lifecycle_shadow": "v2_leads",
    "ck_v2_api_lifecycle_windows_nonnegative_shadow": "v2_api_lifecycle_windows",
    "ck_v2_api_lifecycle_admission_bytes_shadow": "v2_api_lifecycle_admissions",
    "ck_v2_api_lifecycle_receipt_digest_shadow": "v2_api_lifecycle_receipts",
    "ck_v2_api_lifecycle_event_digest_shadow": "v2_api_lifecycle_events",
}
_ROLES = (
    "sealai_migration_owner",
    "sealai_api",
    "sealai_worker",
    "sealai_tenant_admin",
    "sealai_platform_owner",
    "sealai_system_operator",
)


def _guard_ephemeral_dsn(raw_dsn: str) -> None:
    url = make_url(raw_dsn)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("runtime-scope integration requires PostgreSQL")
    database = (url.database or "").lower()
    host = (url.host or "").lower()
    if not any(marker in database for marker in ("test", "ci", "ephemeral")):
        raise RuntimeError("test database name must contain test, ci, or ephemeral")
    if host not in _LOCAL_HOSTS and not any(
        marker in host for marker in ("test", "ci", "ephemeral")
    ):
        raise RuntimeError("PostgreSQL host is not explicitly nonproduction")
    if os.getenv(_CONFIRM_ENV) != _CONFIRM_VALUE:
        raise RuntimeError(f"{_CONFIRM_ENV} must equal {_CONFIRM_VALUE}")


def _cutover_transaction_body() -> str:
    source = (
        Path(__file__).parents[3] / "ops/postgres/gate07-rls-cutover.sql"
    ).read_text(encoding="utf-8")
    # Psql's gate checks and post-COMMIT verification are control-plane statements. Execute the
    # exact repository transaction between BEGIN and the verification query; no policy/grant SQL is
    # copied into this test, so drift is exercised rather than mirrored.
    body = source.split("BEGIN;", 1)[1].split("SELECT count(*) = 13 AND bool_and", 1)[0]
    assert "SET LOCAL ROLE" not in body
    assert "FORCE ROW LEVEL SECURITY" in body
    return f"BEGIN;{body}COMMIT;"


@pytest.fixture(scope="module")
def migrated_gate07_engine():
    raw_dsn = os.getenv(_DSN_ENV)
    if not raw_dsn:
        pytest.skip(f"set {_DSN_ENV} to an explicit empty ephemeral PostgreSQL DSN")
    _guard_ephemeral_dsn(raw_dsn)
    engine = make_engine(raw_dsn)
    existing_roles: set[str] = set()
    try:
        if inspect(engine).get_table_names():
            pytest.fail("GATE-07 migration proof requires an empty ephemeral database")
        with engine.connect() as connection:
            actual_database = str(
                connection.scalar(text("SELECT current_database()")) or ""
            ).lower()
            if not any(
                marker in actual_database for marker in ("test", "ci", "ephemeral")
            ):
                pytest.fail("connected database failed the nonproduction name guard")
            existing_roles = set(
                connection.scalars(
                    text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"),
                    {"roles": list(_ROLES)},
                ).all()
            )
            if existing_roles:
                pytest.fail(
                    "GATE-07 proof requires an ephemeral cluster without canonical runtime roles"
                )

        _upgrade_engine(engine)
        assert migration_status(engine) == ("20260715_0015", "20260715_0015")
        with engine.begin() as connection:
            not_valid = set(
                connection.scalars(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conname = ANY(:names) AND NOT convalidated"
                    ),
                    {"names": list(_CONSTRAINT_TABLES)},
                ).all()
            )
            assert not_valid == set(_CONSTRAINT_TABLES)
            connection.execute(
                text(
                    "INSERT INTO v2_sessions "
                    "(tenant_id, session_id, owner_subject, ownership_state, turns, "
                    "case_revision) VALUES "
                    "('tenant-a', 'case-alice', 'alice', 'owned', 0, 0), "
                    "('tenant-a', 'case-bob', 'bob', 'owned', 0, 0), "
                    "('tenant-b', 'case-carol', 'carol', 'owned', 0, 0)"
                )
            )
            connection.execute(
                V2MemoryItem.__table__.insert(),
                (
                    {
                        "id": "memory-a",
                        "tenant_id": "tenant-a",
                        "owner_subject": "alice",
                        "ownership_state": "owned",
                        "scope": "case",
                        "scope_id": "case-alice",
                        "case_id": "case-alice",
                        "type": "fact",
                        "status": "confirmed",
                        "content": "tenant-a-value",
                        "semantic_key": "memory-a",
                        "created_at": "2026-07-15T00:00:00Z",
                        "updated_at": "2026-07-15T00:00:00Z",
                    },
                    {
                        "id": "memory-b",
                        "tenant_id": "tenant-b",
                        "owner_subject": "carol",
                        "ownership_state": "owned",
                        "scope": "case",
                        "scope_id": "case-carol",
                        "case_id": "case-carol",
                        "type": "fact",
                        "status": "confirmed",
                        "content": "tenant-b-value",
                        "semantic_key": "memory-b",
                        "created_at": "2026-07-15T00:00:00Z",
                        "updated_at": "2026-07-15T00:00:00Z",
                    },
                ),
            )
            for name, table in _CONSTRAINT_TABLES.items():
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table}" VALIDATE CONSTRAINT "{name}"'
                )

        # psycopg executes the repository's multi-statement transaction as one server round-trip.
        raw = engine.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute(_cutover_transaction_body())
            cursor.close()
        finally:
            raw.close()

        # The ephemeral admin must be able to exercise the NOLOGIN roles. Identifier quoting is
        # performed server-side with format(%I); no Python/request value becomes SQL syntax.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DO $grant_test_roles$ DECLARE item text; BEGIN "
                    "FOREACH item IN ARRAY ARRAY["
                    "'sealai_api','sealai_worker','sealai_tenant_admin'] LOOP "
                    "EXECUTE format('GRANT %I TO %I', item, current_user); END LOOP; END "
                    "$grant_test_roles$"
                )
            )
        yield engine
    finally:
        # Best-effort cleanup is restricted to the explicitly empty ephemeral database. Restore
        # ownership before Alembic downgrade; never touch production or a pre-existing schema.
        try:
            with engine.begin() as connection:
                for table in _PROTECTED_TABLES:
                    connection.exec_driver_sql(
                        "DO $restore_owner$ BEGIN "
                        f"IF to_regclass('{table}') IS NOT NULL THEN "
                        f"EXECUTE format('ALTER TABLE {table} OWNER TO %I', current_user); "
                        "END IF; END $restore_owner$"
                    )
            down(engine)
        except Exception:
            pass
        # Roles that predated this isolated run are never dropped or altered during cleanup.
        new_roles = tuple(role for role in _ROLES if role not in existing_roles)
        if new_roles:
            try:
                with engine.begin() as connection:
                    for role in reversed(new_roles):
                        connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
            except Exception:
                pass
        engine.dispose()


def test_real_migrations_cutover_and_pool_reuse_enforce_tenant_owner_scope(
    migrated_gate07_engine,
) -> None:
    engine = migrated_gate07_engine
    factory = make_runtime_sessionmaker(
        engine,
        allowed_roles=frozenset(
            {DatabaseRuntimeRole.API, DatabaseRuntimeRole.TENANT_ADMIN}
        ),
    )

    pids: list[int] = []
    with bind_database_scope(
        tenant_id="tenant-a", subject_id="alice", case_id="case-alice"
    ):
        with factory() as session:
            pids.append(int(session.scalar(text("SELECT pg_backend_pid()"))))
            assert session.scalars(
                text("SELECT session_id FROM v2_sessions ORDER BY session_id")
            ).all() == ["case-alice"]
            assert session.scalar(text("SELECT current_setting('app.case_id')")) == (
                "case-alice"
            )

    with bind_database_scope(
        tenant_id="tenant-b", subject_id="carol", case_id="case-carol"
    ):
        with factory() as session:
            pids.append(int(session.scalar(text("SELECT pg_backend_pid()"))))
            assert session.scalars(
                text("SELECT session_id FROM v2_sessions ORDER BY session_id")
            ).all() == ["case-carol"]

    # QueuePool's last returned connection is reused; transaction-local role/GUC state must not be.
    assert pids[0] == pids[1]
    with engine.connect() as connection:
        role, login, tenant, subject, case_id = connection.execute(
            text(
                "SELECT current_role, current_user, "
                "current_setting('app.tenant_id', true), "
                "current_setting('app.subject_id', true), "
                "current_setting('app.case_id', true)"
            )
        ).one()
        assert role == login
        assert tenant in (None, "")
        assert subject in (None, "")
        assert case_id in (None, "")

    with pytest.raises(RuntimeError, match="no verified runtime scope"):
        with factory() as session:
            session.execute(text("SELECT 1"))

    with bind_database_scope(
        tenant_id="tenant-a", subject_id="tenant-admin", case_id="case-alice"
    ):
        with elevate_database_role(DatabaseRuntimeRole.TENANT_ADMIN):
            with factory() as session:
                assert session.scalars(
                    text("SELECT session_id FROM v2_sessions ORDER BY session_id")
                ).all() == ["case-alice", "case-bob"]


def test_exact_cutover_sets_force_rls_and_non_bypass_roles(
    migrated_gate07_engine,
) -> None:
    engine = migrated_gate07_engine
    with engine.connect() as connection:
        flags = connection.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() AND c.relname = ANY(:tables)"
            ),
            {"tables": list(_PROTECTED_TABLES)},
        ).all()
        assert {row[0] for row in flags} == set(_PROTECTED_TABLES)
        assert all(bool(row[1]) and bool(row[2]) for row in flags)
        role_flags = connection.execute(
            text(
                "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                "FROM pg_roles WHERE rolname = ANY(:roles)"
            ),
            {"roles": list(_ROLES)},
        ).all()
        assert {row[0] for row in role_flags} == set(_ROLES)
        assert all(tuple(row[1:]) == (False, False, False, False) for row in role_flags)


def test_real_postgres_lifecycle_concurrency_race_admits_one(
    migrated_gate07_engine,
) -> None:
    engine = migrated_gate07_engine
    factory = make_runtime_sessionmaker(
        engine, allowed_roles=frozenset({DatabaseRuntimeRole.API})
    )
    identity = VerifiedIdentity("tenant-race", "session-race", "actor-race")
    policy = LifecyclePolicy(
        actor_per_minute=100,
        tenant_per_minute=100,
        actor_per_day=100,
        tenant_per_day=100,
        actor_storage_bytes=100_000,
        tenant_storage_bytes=100_000,
        actor_max_concurrent=1,
        tenant_max_concurrent=5,
        lease_s=60,
    )
    barrier = Barrier(2)

    def compete(index: int):
        barrier.wait()
        with bind_database_scope(
            tenant_id=identity.tenant_id,
            subject_id=identity.subject,
            case_id=identity.session_id,
        ):
            return PostgresLifecycleControlStore(factory).admit(
                identity,
                policy,
                action="contribution.create",
                idempotency_key=f"postgres-race-{index:04d}",
                request_digest=f"{'a' if index == 0 else 'b'}" * 64,
                estimated_bytes=1,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(executor.map(compete, range(2)))
    assert sum(decision.allowed for decision in decisions) == 1
    assert next(decision for decision in decisions if not decision.allowed).reason == (
        "actor_concurrency"
    )


def test_exact_worker_role_is_tenant_bounded_on_destructive_memory_table(
    migrated_gate07_engine,
) -> None:
    factory = make_runtime_sessionmaker(
        migrated_gate07_engine,
        allowed_roles=frozenset({DatabaseRuntimeRole.WORKER}),
    )
    with bind_database_scope(
        tenant_id="tenant-a",
        subject_id="service:outbox-worker",
        role=DatabaseRuntimeRole.WORKER,
    ):
        with factory() as session:
            assert session.scalars(
                text("SELECT id FROM v2_memory_items ORDER BY id")
            ).all() == ["memory-a"]
            assert (
                session.execute(
                    text("DELETE FROM v2_memory_items WHERE id = 'memory-b'")
                ).rowcount
                == 0
            )

    with bind_database_scope(
        tenant_id="tenant-b",
        subject_id="service:outbox-worker",
        role=DatabaseRuntimeRole.WORKER,
    ):
        with factory() as session:
            assert session.scalars(
                text("SELECT id FROM v2_memory_items ORDER BY id")
            ).all() == ["memory-b"]
