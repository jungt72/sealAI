"""Domain-layer value types for case state mutations.

This module defines the immutable value types that represent a single
mutation event applied to a case. It is the domain-layer contract: it
is imported by services, ORM models, and persistence code, but it
imports nothing from those layers.

Layer discipline (per Supplement v1 §35, AGENTS §27.5):
    domain/    <- this module lives here; imports only stdlib
    models/    <- imports from domain/ (SQLAlchemy ORM, Patch 1.5)
    services/  <- imports from domain/ and models/ (Patch 1.6)
    agent/     <- imports from domain/ and services/ via defined interfaces

Type convention (VARCHAR strings, not UUID objects):
    Case and mutation IDs are stored as VARCHAR(36) in the database
    (per cases.id and Patch 1.1/1.2/1.3 migration precedent). We
    represent them in Python as `str` to match storage, not as
    uuid.UUID. Format validation (must be a valid UUID-shaped string)
    is enforced at test time via uuid.UUID(s) round-trip; runtime
    services may enforce the same where appropriate.

Event type values must exactly match the VARCHAR values written to
the mutation_events.event_type column. This is not enforced by SQL
CHECK constraint (unlike outbox.status), but is enforced by this
enum being the single source of truth used by case_service.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class MutationEventType(str, Enum):
    """Types of state mutations persisted to mutation_events.event_type.

    Ordering is alphabetical-by-value for stable iteration in tests.
    """

    ADVISORY_GENERATED = "advisory_generated"
    CALCULATION_RESULT = "calculation_result"
    CASE_CREATED = "case_created"
    COMPOUND_SELECTED = "compound_selected"
    FIELD_UPDATED = "field_updated"
    MEDIUM_IDENTIFIED = "medium_identified"
    NORM_CHECK_RESULT = "norm_check_result"
    OUTPUT_CLASS_ASSIGNED = "output_class_assigned"
    PATTERN_ASSIGNED = "pattern_assigned"
    READINESS_CHANGED = "readiness_changed"


class ActorType(str, Enum):
    """Who performed the mutation, persisted to mutation_events.actor_type."""

    AGENT = "agent"
    SERVICE = "service"
    SYSTEM = "system"
    USER = "user"


@dataclass(frozen=True, slots=True)
class MutationEvent:
    """Immutable record of a single mutation applied to a case.

    Fields mirror the mutation_events SQL columns (Patch 1.2). The
    dataclass is frozen to guarantee immutability. Use
    dataclasses.replace() if a new event with altered fields is needed.

    IDs are VARCHAR strings (per DB convention), not uuid.UUID objects.
    Callers should pass UUID-formatted strings; tests validate this.

    tenant_id may be None for system-wide events with no tenant scope.
    """

    mutation_id: str
    case_id: str
    tenant_id: str | None
    event_type: MutationEventType
    payload: dict[str, Any]
    case_revision_before: int
    case_revision_after: int
    actor: str
    actor_type: ActorType
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict representation."""

        result = asdict(self)
        result["event_type"] = self.event_type.value
        result["actor_type"] = self.actor_type.value
        result["created_at"] = self.created_at.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MutationEvent:
        """Reconstruct from a to_dict() output.

        Raises ValueError or KeyError on malformed input. No silent
        defaults are applied.
        """

        return cls(
            mutation_id=data["mutation_id"],
            case_id=data["case_id"],
            tenant_id=data["tenant_id"],
            event_type=MutationEventType(data["event_type"]),
            payload=data["payload"],
            case_revision_before=data["case_revision_before"],
            case_revision_after=data["case_revision_after"],
            actor=data["actor"],
            actor_type=ActorType(data["actor_type"]),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
