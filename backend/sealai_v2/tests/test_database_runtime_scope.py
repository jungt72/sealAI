from __future__ import annotations

from pathlib import Path
import re

import pytest
from sqlalchemy import create_engine

from sealai_v2.config.settings import Settings
from sealai_v2.db.engine import (
    DatabaseRuntimeRole,
    _apply_runtime_scope,
    bind_database_case,
    bind_database_scope,
    current_database_scope,
    elevate_database_role,
    make_runtime_sessionmaker,
)


class _FakeConnection:
    def __init__(self, actual_role: str) -> None:
        self.actual_role = actual_role
        self.driver_sql: list[str] = []
        self.executions: list[tuple[str, dict | None]] = []

    def exec_driver_sql(self, statement: str) -> None:
        self.driver_sql.append(statement)

    def execute(self, statement, parameters=None):
        self.executions.append((str(statement), parameters))

    def scalar(self, statement):
        self.executions.append((str(statement), None))
        return self.actual_role


@pytest.mark.parametrize(
    ("role", "expected_statement", "expected_name"),
    (
        (DatabaseRuntimeRole.API, "SET LOCAL ROLE sealai_api", "sealai_api"),
        (
            DatabaseRuntimeRole.WORKER,
            "SET LOCAL ROLE sealai_worker",
            "sealai_worker",
        ),
        (
            DatabaseRuntimeRole.TENANT_ADMIN,
            "SET LOCAL ROLE sealai_tenant_admin",
            "sealai_tenant_admin",
        ),
        (
            DatabaseRuntimeRole.PLATFORM_OWNER,
            "SET LOCAL ROLE sealai_platform_owner",
            "sealai_platform_owner",
        ),
        (
            DatabaseRuntimeRole.SYSTEM_OPERATOR,
            "SET LOCAL ROLE sealai_system_operator",
            "sealai_system_operator",
        ),
    ),
)
def test_runtime_scope_uses_only_fixed_role_sql_and_bound_gucs(
    role: DatabaseRuntimeRole, expected_statement: str, expected_name: str
) -> None:
    connection = _FakeConnection(expected_name)
    with bind_database_scope(
        tenant_id="tenant-a'; RESET ROLE; --",
        subject_id="subject-a",
        case_id="case-a",
        role=role,
    ) as scope:
        _apply_runtime_scope(connection, scope)

    assert connection.driver_sql == [expected_statement]
    guc_sql, parameters = connection.executions[0]
    assert "set_config('app.tenant_id', :tenant_id, true)" in guc_sql
    assert "set_config('app.subject_id', :subject_id, true)" in guc_sql
    assert "set_config('app.case_id', :case_id, true)" in guc_sql
    assert "set_config('app.tenant_ref', :tenant_ref, true)" in guc_sql
    assert "set_config('app.actor_ref', :actor_ref, true)" in guc_sql
    assert parameters == {
        "tenant_id": "tenant-a'; RESET ROLE; --",
        "subject_id": "subject-a",
        "case_id": "case-a",
        "tenant_ref": "aebf1117c1ef3efd604f01e6f2918d8d3012306f32e7d23bae343ea1712353e6",
        "actor_ref": "37fadfb208ba167f7bd46b6afe85b1048cd4c674944e99bce32baf238c629d0f",
    }
    assert "RESET ROLE" not in connection.driver_sql[0]


def test_scope_is_nested_and_role_elevation_restores_exact_context() -> None:
    assert current_database_scope() is None
    with bind_database_scope(
        tenant_id="tenant-a", subject_id="alice", case_id="case-a"
    ) as request_scope:
        assert current_database_scope() == request_scope
        with bind_database_case("case-b") as narrowed:
            assert narrowed is not None
            assert narrowed.case_id == "case-b"
            assert current_database_scope() == narrowed
        assert current_database_scope() == request_scope
        with elevate_database_role(DatabaseRuntimeRole.PLATFORM_OWNER) as elevated:
            assert elevated.role is DatabaseRuntimeRole.PLATFORM_OWNER
            assert elevated.tenant_id == request_scope.tenant_id
            assert current_database_scope() == elevated
        assert current_database_scope() == request_scope
    assert current_database_scope() is None


@pytest.mark.parametrize(
    "kwargs",
    (
        {"tenant_id": "", "subject_id": "alice"},
        {"tenant_id": "tenant-a", "subject_id": ""},
        {"tenant_id": "tenant-a\nforged", "subject_id": "alice"},
        {"tenant_id": "tenant-a", "subject_id": "alice", "case_id": "x" * 256},
        {
            "tenant_id": "tenant-a",
            "subject_id": "alice",
            "role": "sealai_api",
        },
    ),
)
def test_invalid_or_dynamic_database_scope_fails_closed(kwargs: dict) -> None:
    expected = TypeError if isinstance(kwargs.get("role"), str) else ValueError
    with pytest.raises(expected):
        with bind_database_scope(**kwargs):  # type: ignore[arg-type]
            pass


def test_runtime_factory_rejects_non_postgres_false_evidence() -> None:
    engine = create_engine("sqlite://")
    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        make_runtime_sessionmaker(
            engine, allowed_roles=frozenset({DatabaseRuntimeRole.API})
        )


def test_settings_require_distinct_database_users_and_postgres_for_rls() -> None:
    with pytest.raises(ValueError, match="must be distinct"):
        Settings(
            database_url="postgresql+psycopg2://shared@localhost/app",
            worker_database_url="postgresql+psycopg2://shared@localhost/app",
        )
    with pytest.raises(ValueError, match="requires PostgreSQL"):
        Settings(database_url="sqlite://", database_rls_scope_enabled=True)


def test_deploy_contract_keeps_rls_off_and_separates_worker_credential() -> None:
    root = Path(__file__).parents[3]
    compose = (root / "docker-compose.deploy.yml").read_text(encoding="utf-8")
    worker = compose.split("  backend-v2-worker:", 1)[1].split("\nvolumes:", 1)[0]

    assert (
        "SEALAI_V2_DATABASE_RLS_SCOPE_ENABLED: "
        "${SEALAI_V2_DATABASE_RLS_SCOPE_ENABLED:-false}"
    ) in compose
    assert 'SEALAI_V2_DATABASE_URL: ""' in worker
    assert "SEALAI_V2_WORKER_DATABASE_URL: postgresql+psycopg2://" in worker
    assert "SEALAI_V2_WORKER_DB_USER" in worker
    assert "SEALAI_V2_WORKER_DB_PASSWORD" in worker
    assert "SEALAI_V2_DB_PASSWORD" not in worker


def test_cutover_contract_is_adapter_gated_and_adds_tenant_scoped_worker_policy() -> (
    None
):
    source = (
        Path(__file__).parents[3] / "ops/postgres/gate07-rls-cutover.sql"
    ).read_text(encoding="utf-8")

    assert "runtime_scope_adapter_verified is required" in source
    assert "CREATE POLICY worker_tenant ON v2_memory_items TO sealai_worker" in source
    assert "tenant_id = current_setting('app.tenant_id', true)" in source
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON" in source
    assert "TO sealai_worker;" in source
    assert "current_setting('app.actor_ref', true)" in source
    assert "current_setting('app.tenant_ref', true)" in source
    assert source.count("FORCE ROW LEVEL SECURITY") >= 13
    grants = re.findall(r"\bGRANT\s+(.+?)\s+TO\s+\w+\s*;", source, re.DOTALL)
    no_delete = (
        "v2_leads",
        "v2_contributions",
        "v2_api_lifecycle_windows",
        "v2_api_lifecycle_admissions",
        "v2_api_lifecycle_receipts",
        "v2_api_lifecycle_events",
    )
    for grant in grants:
        privileges = grant.split(" ON", 1)[0]
        if "DELETE" in privileges:
            assert all(table not in grant for table in no_delete)
        if "UPDATE" in privileges:
            assert "v2_api_lifecycle_receipts" not in grant
            assert "v2_api_lifecycle_events" not in grant
    assert re.search(
        r"GRANT SELECT, INSERT ON\s+"
        r"v2_api_lifecycle_receipts, v2_api_lifecycle_events\s+"
        r"TO sealai_api;",
        source,
    )
