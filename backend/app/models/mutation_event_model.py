"""SQLAlchemy ORM model for the mutation_events table.

Mirrors the mutation_events table created by Alembic migration
7e9c4a2b8d31 (Patch 1.2). Column names, types, nullability, and
defaults match the migration exactly.

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

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
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
    tenant_id = Column(String(255), nullable=True)
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
