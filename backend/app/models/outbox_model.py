"""SQLAlchemy ORM model for the outbox table.

Mirrors the outbox table created by Alembic migration 4c2f8a9d1b73
(Patch 1.3) and hardened by b8c4d6e2f901 (Patch 1.7). Column names,
types, nullability, and defaults match the migration chain.

Design notes
------------
- status is a plain String column. The SQL CHECK constraint enforces
  allowed values at the DB level; Python validation happens via a
  future service-layer enum.
- task_type is a plain String column. Python enum will be added at
  service layer (not in domain yet; deferred until outbox_worker
  sprint).
- No relationship() declarations; same reasoning as mutation_event_model.
- outbox_id is VARCHAR(36) PK, app-generated.
- FK to cases.id CASCADE; FK to mutation_events.mutation_id no-cascade
  (task survives mutation archival).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from app.database import Base


class OutboxModel(Base):
    """Durable async task queue row.

    See outbox table (Alembic 4c2f8a9d1b73) for semantics. Status
    CHECK constraint and indexes are defined in the migration, not
    redeclared here.
    """

    __tablename__ = "outbox"

    outbox_id = Column(String(36), primary_key=True)
    case_id = Column(
        String(36),
        ForeignKey("cases.id", ondelete="CASCADE", name="fk_outbox_case_id"),
        nullable=True,
    )
    mutation_id = Column(
        String(36),
        ForeignKey("mutation_events.mutation_id", name="fk_outbox_mutation_id"),
        nullable=True,
    )
    tenant_id = Column(String(255), nullable=False)
    task_type = Column(String(64), nullable=False)
    payload = Column(
        JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
        nullable=False,
    )
    status = Column(String(32), nullable=False, server_default="pending")
    priority = Column(Integer, nullable=False, server_default="0")
    attempts = Column(Integer, nullable=False, server_default="0")
    max_attempts = Column(Integer, nullable=False, server_default="5")
    next_attempt_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<OutboxModel outbox_id={self.outbox_id!r} "
            f"status={self.status!r} task_type={self.task_type!r}>"
        )
