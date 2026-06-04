"""SQLAlchemy ORM model for the outbox table.

Mirrors the outbox table created by Alembic migration 4c2f8a9d1b73
(Patch 1.3) and hardened by b8c4d6e2f901 (Patch 1.7). Column names,
types, nullability, and defaults match the migration chain.

Design notes
------------
- status is a plain String column. The SQL CHECK constraint and ORM
  validator enforce the allowed queue states.
- task_type is a plain String column. Python enum will be added at
  service layer (not in domain yet; deferred until outbox_worker
  sprint).
- No relationship() declarations; same reasoning as mutation_event_model.
- outbox_id is VARCHAR(36) PK, app-generated.
- FK to cases.id CASCADE; FK to mutation_events.mutation_id no-cascade
  (task survives mutation archival).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import validates
from sqlalchemy.types import JSON

from app.database import Base


class OutboxModel(Base):
    """Durable async task queue row.

    See outbox table (Alembic 4c2f8a9d1b73) for semantics. Status
    CHECK constraint is mirrored here; indexes remain migration-owned.
    """

    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', "
            "'failed_retryable', 'failed_permanent')",
            name="valid_status",
        ),
    )

    VALID_STATUSES = frozenset(
        {
            "pending",
            "in_progress",
            "completed",
            "failed_retryable",
            "failed_permanent",
        }
    )

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

    @validates("outbox_id", "tenant_id", "task_type")
    def _validate_required_string(self, key: str, value: Any) -> str:
        if value is None:
            raise ValueError(f"{key} is required")
        normalized = str(value).strip()
        if not normalized:
            raise ValueError(f"{key} is required")
        return normalized

    @validates("case_id", "mutation_id")
    def _validate_optional_string(self, key: str, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError(f"{key} cannot be blank")
        return normalized

    @validates("payload")
    def _validate_payload(self, _key: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("payload must be a dict")
        return value

    @validates("status")
    def _validate_status(self, _key: str, value: Any) -> str:
        normalized = str(value).strip() if value is not None else ""
        if normalized not in self.VALID_STATUSES:
            raise ValueError(f"unsupported outbox status: {value}")
        return normalized

    @validates("priority", "attempts", "max_attempts")
    def _validate_attempt_counter(self, key: str, value: Any) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{key} must be an integer")
        if key == "priority":
            return value
        if key == "max_attempts":
            if value < 1:
                raise ValueError("max_attempts must be positive")
        elif value < 0:
            raise ValueError(f"{key} must be non-negative")
        return value
