"""Tests for Sprint 1 Patch 1.5 - OutboxModel ORM."""

from __future__ import annotations

import pathlib
import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.case_record import CaseRecord  # noqa: F401
from app.models.mutation_event_model import MutationEventModel  # noqa: F401
from app.models.outbox_model import OutboxModel


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    _create_sqlite_cases_table(engine)
    _create_sqlite_mutation_events_table(engine)
    OutboxModel.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


def _create_sqlite_cases_table(engine: Engine) -> None:
    """Create the minimal parent table needed by FK metadata in SQLite."""

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE cases (
                    id VARCHAR(36) PRIMARY KEY,
                    case_number VARCHAR(50) NOT NULL,
                    user_id VARCHAR(255) NOT NULL
                )
                """
            )
        )


def _create_sqlite_mutation_events_table(engine: Engine) -> None:
    """Create the minimal parent table needed by OutboxModel's mutation FK."""

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE mutation_events (
                    mutation_id VARCHAR(36) PRIMARY KEY
                )
                """
            )
        )


class TestOutboxModelStructure:
    def test_model_loads(self) -> None:
        assert OutboxModel.__tablename__ == "outbox"

    def test_expected_columns(self) -> None:
        cols = {c.name for c in OutboxModel.__table__.columns}
        expected = {
            "outbox_id",
            "case_id",
            "mutation_id",
            "tenant_id",
            "task_type",
            "payload",
            "status",
            "priority",
            "attempts",
            "max_attempts",
            "next_attempt_at",
            "last_error",
            "created_at",
            "completed_at",
        }
        assert cols == expected, f"Column mismatch: {cols ^ expected}"

    def test_column_types_and_nullability(self) -> None:
        columns = OutboxModel.__table__.c

        assert str(columns.outbox_id.type) == "VARCHAR(36)"
        assert str(columns.case_id.type) == "VARCHAR(36)"
        assert str(columns.mutation_id.type) == "VARCHAR(36)"
        assert str(columns.tenant_id.type) == "VARCHAR(255)"
        assert str(columns.task_type.type) == "VARCHAR(64)"
        assert str(columns.status.type) == "VARCHAR(32)"
        assert str(columns.priority.type) == "INTEGER"
        assert str(columns.attempts.type) == "INTEGER"
        assert str(columns.max_attempts.type) == "INTEGER"
        assert str(columns.last_error.type) == "TEXT"
        assert not columns.outbox_id.nullable
        assert columns.case_id.nullable
        assert columns.mutation_id.nullable
        assert not columns.tenant_id.nullable
        assert not columns.task_type.nullable
        assert not columns.payload.nullable
        assert not columns.status.nullable
        assert not columns.priority.nullable
        assert not columns.attempts.nullable
        assert not columns.max_attempts.nullable
        assert not columns.next_attempt_at.nullable
        assert columns.last_error.nullable
        assert not columns.created_at.nullable
        assert columns.completed_at.nullable

    def test_server_defaults_match_migration(self) -> None:
        columns = OutboxModel.__table__.c

        assert str(columns.status.server_default.arg) == "pending"
        assert str(columns.priority.server_default.arg) == "0"
        assert str(columns.attempts.server_default.arg) == "0"
        assert str(columns.max_attempts.server_default.arg) == "5"
        assert columns.next_attempt_at.server_default is not None
        assert columns.created_at.server_default is not None

    def test_primary_key(self) -> None:
        pk_cols = [c.name for c in OutboxModel.__table__.primary_key.columns]
        assert pk_cols == ["outbox_id"]

    def test_two_foreign_keys(self) -> None:
        fks = list(OutboxModel.__table__.foreign_keys)
        fk_by_ref = {(fk.column.table.name, fk.column.name): fk for fk in fks}
        assert ("cases", "id") in fk_by_ref
        assert ("mutation_events", "mutation_id") in fk_by_ref
        assert fk_by_ref[("cases", "id")].ondelete == "CASCADE"
        assert fk_by_ref[("mutation_events", "mutation_id")].ondelete is None


class TestOutboxModelPersistence:
    def test_insert_minimal_with_defaults(self, session: Session) -> None:
        """Insert without specifying status/priority uses server defaults."""

        row = OutboxModel(
            outbox_id=str(uuid.uuid4()),
            tenant_id="tenant-test",
            task_type="notify_audit_log",
            payload={},
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        assert row.status == "pending"
        assert row.priority == 0
        assert row.attempts == 0
        assert row.max_attempts == 5

    def test_insert_and_query(self, session: Session) -> None:
        row = OutboxModel(
            outbox_id=str(uuid.uuid4()),
            case_id=None,
            mutation_id=None,
            tenant_id="tenant-test",
            task_type="risk_score_recompute",
            payload={"key": "value"},
            status="pending",
            priority=10,
        )
        session.add(row)
        session.flush()

        retrieved = (
            session.query(OutboxModel).filter_by(outbox_id=row.outbox_id).one()
        )
        assert retrieved.task_type == "risk_score_recompute"
        assert retrieved.priority == 10
        assert retrieved.payload == {"key": "value"}

    def test_repr_readable(self, session: Session) -> None:
        row = OutboxModel(
            outbox_id=str(uuid.uuid4()),
            tenant_id="tenant-test",
            task_type="project_case_snapshot",
            payload={},
        )
        rendered = repr(row)
        assert "OutboxModel" in rendered
        assert "project_case_snapshot" in rendered


class TestLayerDiscipline:
    """Meta-tests enforcing AGENTS §27.5 layer isolation for models."""

    def test_no_forbidden_imports_in_models(self) -> None:
        """models/ must not import from agent/, services/, schemas/."""

        models_dir = pathlib.Path(__file__).parents[3] / "app" / "models"
        forbidden = [
            "from app.agent",
            "from app.services",
            "from app.schemas",
            "import app.agent",
            "import app.services",
            "import app.schemas",
        ]
        violations: list[str] = []
        for py_file in models_dir.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            for pattern in forbidden:
                if pattern in source:
                    violations.append(f"{py_file.name}: {pattern}")
        assert not violations, f"Forbidden imports in models: {violations}"
