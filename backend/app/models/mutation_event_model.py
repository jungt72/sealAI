"""SQLAlchemy ORM model for the mutation_events table.

Mirrors the mutation_events table created by Alembic migration
7e9c4a2b8d31 (Patch 1.2) and hardened by b8c4d6e2f901 (Patch 1.7).
Column names, types, nullability, and defaults match the migration chain.

Design notes
------------
- event_type and actor_type are plain String columns, not SQLAlchemy
  Enum columns. The migration uses VARCHAR(64)/(32), not PG ENUM.
  Value validation happens at the service layer (Patch 1.6) via
  MutationEventType(value) / ActorType(value), which raise ValueError
  on unknown values.
- No relationship() declarations. CaseRecord <-> MutationEventModel
  joins are done via explicit SQL in case_service (Patch 1.6).
  Deferred to avoid circular imports and initialization-order bugs.
- mutation_id is VARCHAR(36) consistent with cases.id convention.
  Application-generated (typically via uuid.uuid4()) not DB-generated.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import validates
from sqlalchemy.types import JSON

from app.database import Base


class MutationEventModel(Base):
    """Immutable audit-trail record for a single case state mutation.

    See mutation_events table (Alembic 7e9c4a2b8d31) for semantics.
    """

    __tablename__ = "mutation_events"

    mutation_id = Column(String(36), primary_key=True)
    case_id = Column(
        String(36),
        ForeignKey("cases.id", ondelete="CASCADE", name="fk_mutation_events_case_id"),
        nullable=False,
    )
    tenant_id = Column(String(255), nullable=False)
    event_type = Column(String(64), nullable=False)
    payload = Column(
        JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    case_revision_before = Column(Integer, nullable=False)
    case_revision_after = Column(Integer, nullable=False)
    actor = Column(String(128), nullable=False)
    actor_type = Column(String(32), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<MutationEventModel mutation_id={self.mutation_id!r} "
            f"case_id={self.case_id!r} event_type={self.event_type!r}>"
        )

    @validates(
        "mutation_id",
        "case_id",
        "tenant_id",
        "event_type",
        "actor",
        "actor_type",
    )
    def _validate_required_string(self, key: str, value: Any) -> str:
        if value is None:
            raise ValueError(f"{key} is required")
        normalized = str(value).strip()
        if not normalized:
            raise ValueError(f"{key} is required")
        return normalized

    @validates("payload")
    def _validate_payload(self, _key: str, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("payload must be a dict")
        return value

    @validates("case_revision_before", "case_revision_after")
    def _validate_revision(self, key: str, value: Any) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{key} must be an integer")
        if value < 0:
            raise ValueError(f"{key} must be non-negative")

        before = value if key == "case_revision_before" else self.case_revision_before
        after = value if key == "case_revision_after" else self.case_revision_after
        if before is not None and after is not None and after != before + 1:
            raise ValueError("case revisions must increase exactly by one")
        return value
