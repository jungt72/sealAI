"""Tests for Sprint 1 Patch 1.4 domain types."""

from __future__ import annotations

import json
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from app.domain.mutation_events import (
    ActorType,
    MutationEvent,
    MutationEventType,
)


class TestMutationEventType:
    def test_all_expected_values_present(self) -> None:
        """The 10 enum values per Patch 1.2 migration."""

        expected = {
            "advisory_generated",
            "calculation_result",
            "case_created",
            "compound_selected",
            "field_updated",
            "medium_identified",
            "norm_check_result",
            "output_class_assigned",
            "pattern_assigned",
            "readiness_changed",
        }
        actual = {member.value for member in MutationEventType}
        assert actual == expected

    def test_is_string_enum(self) -> None:
        """Must be str-Enum so DB column VARCHAR stores the value directly."""

        assert isinstance(MutationEventType.CASE_CREATED, str)
        assert MutationEventType.CASE_CREATED == "case_created"


class TestActorType:
    def test_all_expected_values_present(self) -> None:
        """Four actor types per plan."""

        expected = {"agent", "service", "system", "user"}
        actual = {member.value for member in ActorType}
        assert actual == expected

    def test_is_string_enum(self) -> None:
        assert isinstance(ActorType.USER, str)
        assert ActorType.USER == "user"


class TestMutationEvent:
    def _make_event(self) -> MutationEvent:
        return MutationEvent(
            mutation_id=str(uuid.uuid4()),
            case_id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            event_type=MutationEventType.CASE_CREATED,
            payload={"field": "value", "n": 42},
            case_revision_before=0,
            case_revision_after=1,
            actor="user-abc",
            actor_type=ActorType.USER,
            created_at=datetime.now(timezone.utc),
        )

    def test_construction(self) -> None:
        evt = self._make_event()
        assert evt.event_type == MutationEventType.CASE_CREATED
        assert evt.actor_type == ActorType.USER
        assert evt.case_revision_after - evt.case_revision_before == 1

    def test_frozen_cannot_modify(self) -> None:
        """frozen=True must prevent attribute writes."""

        evt = self._make_event()
        with pytest.raises(FrozenInstanceError):
            setattr(evt, "actor", "new-user")

    def test_slots_no_extra_attributes(self) -> None:
        """slots=True must prevent attribute additions."""

        evt = self._make_event()
        with pytest.raises(AttributeError):
            object.__setattr__(evt, "extra_field", "x")

    def test_tenant_id_may_be_none(self) -> None:
        evt = MutationEvent(
            mutation_id=str(uuid.uuid4()),
            case_id=str(uuid.uuid4()),
            tenant_id=None,
            event_type=MutationEventType.CASE_CREATED,
            payload={},
            case_revision_before=0,
            case_revision_after=1,
            actor="system",
            actor_type=ActorType.SYSTEM,
            created_at=datetime.now(timezone.utc),
        )
        assert evt.tenant_id is None

    def test_ids_are_valid_uuid_strings(self) -> None:
        """IDs are VARCHAR strings but must be UUID-format for DB compat."""

        evt = self._make_event()
        uuid.UUID(evt.mutation_id)
        uuid.UUID(evt.case_id)
        assert evt.tenant_id is not None
        uuid.UUID(evt.tenant_id)

    def test_to_dict_is_json_serializable(self) -> None:
        evt = self._make_event()
        result = evt.to_dict()
        serialized = json.dumps(result)
        assert isinstance(serialized, str)
        assert result["event_type"] == "case_created"
        assert result["actor_type"] == "user"
        assert isinstance(result["created_at"], str)

    def test_round_trip_python_to_json_to_python(self) -> None:
        """The mandatory serialization round-trip test per plan."""

        original = self._make_event()
        result = original.to_dict()
        serialized = json.dumps(result)
        deserialized = json.loads(serialized)
        reconstructed = MutationEvent.from_dict(deserialized)

        assert reconstructed.mutation_id == original.mutation_id
        assert reconstructed.case_id == original.case_id
        assert reconstructed.tenant_id == original.tenant_id
        assert reconstructed.event_type == original.event_type
        assert reconstructed.payload == original.payload
        assert reconstructed.case_revision_before == original.case_revision_before
        assert reconstructed.case_revision_after == original.case_revision_after
        assert reconstructed.actor == original.actor
        assert reconstructed.actor_type == original.actor_type
        assert reconstructed.created_at == original.created_at

    def test_from_dict_rejects_malformed_input(self) -> None:
        """Missing required fields raise KeyError, not silent defaults."""

        partial = {"mutation_id": "foo"}
        with pytest.raises(KeyError):
            MutationEvent.from_dict(partial)

    def test_from_dict_rejects_invalid_enum_value(self) -> None:
        """Unknown event_type raises ValueError from Enum()."""

        evt = self._make_event()
        result = evt.to_dict()
        result["event_type"] = "not_a_real_type"
        with pytest.raises(ValueError):
            MutationEvent.from_dict(result)


class TestLayerDiscipline:
    """Meta-tests enforcing AGENTS §27.5 layer isolation."""

    def test_domain_module_no_forbidden_imports(self) -> None:
        """Domain must not import from models, schemas, agent, services."""

        import app.domain.mutation_events as mod

        src_file = mod.__file__
        assert src_file is not None
        with open(src_file, encoding="utf-8") as source_file:
            source = source_file.read()
        forbidden = [
            "from app.models",
            "from app.schemas",
            "from app.agent",
            "from app.services",
            "import app.models",
            "import app.schemas",
            "import app.agent",
            "import app.services",
        ]
        violations = [pattern for pattern in forbidden if pattern in source]
        assert not violations, f"Forbidden imports in domain: {violations}"
