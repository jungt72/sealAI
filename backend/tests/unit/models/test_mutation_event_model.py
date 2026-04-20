"""Tests for Sprint 1 Patch 1.5 - MutationEventModel ORM."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.case_record import CaseRecord  # noqa: F401
from app.models.mutation_event_model import MutationEventModel


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    _create_sqlite_cases_table(engine)
    _create_sqlite_mutation_events_table(engine)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


def _create_sqlite_cases_table(engine: Engine) -> None:
    """Create the minimal parent table needed by FK metadata in SQLite.

    CaseRecord itself is intentionally not created here: its ORM payload
    server_default mirrors PostgreSQL JSONB syntax from Patch 1.1 and is
    therefore not valid SQLite DDL.
    """

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
    """Create a SQLite-compatible table for ORM insert/query behavior.

    The ORM column's server_default intentionally mirrors PostgreSQL
    JSONB syntax from the migration; this fixture keeps the persistence
    test SQLite-only without weakening the model metadata assertion.
    """

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE mutation_events (
                    mutation_id VARCHAR(36) PRIMARY KEY,
                    case_id VARCHAR(36) NOT NULL,
                    tenant_id VARCHAR(255),
                    event_type VARCHAR(64) NOT NULL,
                    payload JSON NOT NULL DEFAULT '{}',
                    case_revision_before INTEGER NOT NULL,
                    case_revision_after INTEGER NOT NULL,
                    actor VARCHAR(128) NOT NULL,
                    actor_type VARCHAR(32) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_mutation_events_case_id
                        FOREIGN KEY(case_id) REFERENCES cases (id)
                        ON DELETE CASCADE
                )
                """
            )
        )


class TestMutationEventModelStructure:
    def test_model_loads(self) -> None:
        """Import works, class is a SQLAlchemy mapped class."""

        assert MutationEventModel.__tablename__ == "mutation_events"

    def test_expected_columns(self) -> None:
        """All 10 columns declared."""

        cols = {c.name for c in MutationEventModel.__table__.columns}
        expected = {
            "mutation_id",
            "case_id",
            "tenant_id",
            "event_type",
            "payload",
            "case_revision_before",
            "case_revision_after",
            "actor",
            "actor_type",
            "created_at",
        }
        assert cols == expected, f"Column mismatch: {cols ^ expected}"

    def test_column_types_and_nullability(self) -> None:
        columns = MutationEventModel.__table__.c

        assert str(columns.mutation_id.type) == "VARCHAR(36)"
        assert str(columns.case_id.type) == "VARCHAR(36)"
        assert str(columns.tenant_id.type) == "VARCHAR(255)"
        assert str(columns.event_type.type) == "VARCHAR(64)"
        assert str(columns.case_revision_before.type) == "INTEGER"
        assert str(columns.case_revision_after.type) == "INTEGER"
        assert str(columns.actor.type) == "VARCHAR(128)"
        assert str(columns.actor_type.type) == "VARCHAR(32)"
        assert not columns.case_id.nullable
        assert columns.tenant_id.nullable
        assert not columns.payload.nullable
        assert not columns.created_at.nullable

    def test_payload_default_matches_migration(self) -> None:
        default = MutationEventModel.__table__.c.payload.server_default

        assert default is not None
        assert str(default.arg) == "'{}'::jsonb"

    def test_primary_key(self) -> None:
        pk_cols = [c.name for c in MutationEventModel.__table__.primary_key.columns]
        assert pk_cols == ["mutation_id"]

    def test_foreign_key_to_cases(self) -> None:
        fks = list(MutationEventModel.__table__.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk.column.table.name == "cases"
        assert fk.column.name == "id"
        assert fk.ondelete == "CASCADE"


class TestMutationEventModelPersistence:
    def _make_case(self, session: Session) -> str:
        """Insert a case row so FK is satisfied; return case id."""

        case_id = str(uuid.uuid4())
        session.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id) "
                "VALUES (:id, :case_number, :user_id)"
            ),
            {
                "id": case_id,
                "case_number": f"CASE-TEST-{case_id[:8]}",
                "user_id": "user-test",
            },
        )
        session.flush()
        return case_id

    def test_insert_and_query(self, session: Session) -> None:
        case_id = self._make_case(session)
        evt = MutationEventModel(
            mutation_id=str(uuid.uuid4()),
            case_id=case_id,
            tenant_id=None,
            event_type="case_created",
            payload={"any": "dict"},
            case_revision_before=0,
            case_revision_after=1,
            actor="test-user",
            actor_type="user",
        )
        session.add(evt)
        session.flush()

        retrieved = (
            session.query(MutationEventModel)
            .filter_by(mutation_id=evt.mutation_id)
            .one()
        )
        assert retrieved.event_type == "case_created"
        assert retrieved.payload == {"any": "dict"}
        assert retrieved.case_revision_after - retrieved.case_revision_before == 1

    def test_repr_readable(self, session: Session) -> None:
        case_id = self._make_case(session)
        evt = MutationEventModel(
            mutation_id=str(uuid.uuid4()),
            case_id=case_id,
            tenant_id=None,
            event_type="field_updated",
            payload={},
            case_revision_before=1,
            case_revision_after=2,
            actor="agent-x",
            actor_type="agent",
        )
        rendered = repr(evt)
        assert "MutationEventModel" in rendered
        assert "field_updated" in rendered
