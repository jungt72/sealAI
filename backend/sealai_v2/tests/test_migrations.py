from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine
from sealai_v2.db.migrate import migration_status, up, validate_schema


def test_alembic_upgrade_creates_fresh_schema(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'fresh.db'}")

    tables = set(up(engine))

    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables
    current, head = migration_status(engine)
    assert current == head == "20260710_0003"
    validate_schema(engine)


def test_alembic_baseline_adopts_complete_legacy_schema(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()

    up(engine)

    assert "alembic_version" in inspect(engine).get_table_names()
    validate_schema(engine)


def test_alembic_baseline_adopts_known_legacy_schema_without_legal_table(
    tmp_path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy-before-legal.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE v2_legal_acceptance")

    up(engine)

    assert "v2_legal_acceptance" in inspect(engine).get_table_names()
    validate_schema(engine)


def test_alembic_baseline_rejects_partial_legacy_schema(tmp_path) -> None:
    path = tmp_path / "partial.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE v2_sessions (tenant_id TEXT NOT NULL, session_id TEXT NOT NULL, "
            "turns INTEGER NOT NULL, PRIMARY KEY (tenant_id, session_id))"
        )

    engine = make_engine(f"sqlite:///{path}")
    with pytest.raises(RuntimeError, match="partial V2 schema"):
        up(engine)


def test_knowledge_migration_rejects_partial_precreated_ledger(tmp_path) -> None:
    path = tmp_path / "partial-knowledge.db"
    engine = make_engine(f"sqlite:///{path}")
    up(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE v2_knowledge_outbox")
        connection.exec_driver_sql(
            "UPDATE alembic_version SET version_num='20260710_0002'"
        )

    with pytest.raises(RuntimeError, match="partial technical-knowledge ledger"):
        up(engine)
