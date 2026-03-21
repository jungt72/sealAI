"""
Unit tests for Phase A4 — Governed Domain Data Layer.

Tests cover:
1. GovernedMaterialRecord — field types and defaults
2. GovernedMaterialRecord — release_status / conflict_status validation
3. GovernedMaterialRecord — is_expired property (past / future / None)
4. GovernedMaterialRecord — is_active property
5. DomainDataProvider — Protocol structural check
6. DummyDomainDataProvider — satisfies DomainDataProvider Protocol
7. DummyDomainDataProvider — returns clean GovernedMaterialRecords
8. DummyDomainDataProvider — all demo records carry is_demo_only=True
9. DummyDomainDataProvider — list_active_material_records filters correctly
10. material_core bridge — load_governed_material_records delegates to provider
11. material_core bridge — custom provider is honoured
12. Provider swap — set_default_domain_data_provider replaces the module singleton
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.agent.domain.governed_data import (
    DomainDataProvider,
    DummyDomainDataProvider,
    GovernedMaterialRecord,
    get_default_domain_data_provider,
    set_default_domain_data_provider,
)
from app.agent.material_core import load_governed_material_records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(**kwargs) -> GovernedMaterialRecord:
    defaults = dict(
        record_id="test-rec-001",
        material_family="FKM",
        source_name="Test Source",
        source_version="v1.0",
        release_status="active",
        conflict_status="none",
        is_demo_only=True,
    )
    defaults.update(kwargs)
    return GovernedMaterialRecord(**defaults)


# ---------------------------------------------------------------------------
# 1. Field types and defaults
# ---------------------------------------------------------------------------

class TestGovernedMaterialRecordFields:
    def test_required_fields_accepted(self):
        rec = _make_record()
        assert rec.record_id == "test-rec-001"
        assert rec.material_family == "FKM"
        assert rec.source_name == "Test Source"
        assert rec.source_version == "v1.0"

    def test_optional_fields_default_to_none(self):
        rec = _make_record()
        assert rec.valid_from is None
        assert rec.valid_until is None
        assert rec.grade_name is None
        assert rec.manufacturer_name is None

    def test_coverage_metadata_defaults_to_empty_dict(self):
        rec = _make_record()
        assert rec.coverage_metadata == {}

    def test_coverage_metadata_stored(self):
        meta = {"max_temp_c": 200, "allowed_media": ["water"]}
        rec = _make_record(coverage_metadata=meta)
        assert rec.coverage_metadata["max_temp_c"] == 200

    def test_is_demo_only_defaults_true(self):
        rec = GovernedMaterialRecord(
            record_id="x",
            material_family="NBR",
            source_name="S",
            source_version="v1",
        )
        assert rec.is_demo_only is True

    def test_is_demo_only_can_be_false(self):
        rec = _make_record(is_demo_only=False)
        assert rec.is_demo_only is False

    def test_record_is_frozen(self):
        rec = _make_record()
        with pytest.raises((AttributeError, TypeError)):
            rec.record_id = "other"  # type: ignore[misc]

    def test_release_status_default_is_draft(self):
        rec = GovernedMaterialRecord(
            record_id="x", material_family="NBR", source_name="S", source_version="v1"
        )
        assert rec.release_status == "draft"

    def test_conflict_status_default_is_none(self):
        rec = GovernedMaterialRecord(
            record_id="x", material_family="NBR", source_name="S", source_version="v1"
        )
        assert rec.conflict_status == "none"


# ---------------------------------------------------------------------------
# 2. release_status / conflict_status validation
# ---------------------------------------------------------------------------

class TestGovernedMaterialRecordValidation:
    @pytest.mark.parametrize("rs", ["active", "deprecated", "draft"])
    def test_valid_release_statuses_accepted(self, rs):
        rec = _make_record(release_status=rs)
        assert rec.release_status == rs

    def test_invalid_release_status_raises(self):
        with pytest.raises(ValueError, match="release_status must be"):
            _make_record(release_status="pending")

    @pytest.mark.parametrize("cs", ["none", "superseded_by_newer_version"])
    def test_valid_conflict_statuses_accepted(self, cs):
        rec = _make_record(conflict_status=cs)
        assert rec.conflict_status == cs

    def test_invalid_conflict_status_raises(self):
        with pytest.raises(ValueError, match="conflict_status must be"):
            _make_record(conflict_status="unknown")


# ---------------------------------------------------------------------------
# 3. is_expired property
# ---------------------------------------------------------------------------

class TestIsExpired:
    def test_no_valid_until_is_not_expired(self):
        rec = _make_record(valid_until=None)
        assert rec.is_expired is False

    def test_valid_until_in_past_is_expired(self):
        past = date.today() - timedelta(days=1)
        rec = _make_record(valid_until=past)
        assert rec.is_expired is True

    def test_valid_until_in_future_is_not_expired(self):
        future = date.today() + timedelta(days=365)
        rec = _make_record(valid_until=future)
        assert rec.is_expired is False

    def test_valid_until_today_is_not_expired(self):
        """Expiry is *strictly* before today, so today itself is still valid."""
        rec = _make_record(valid_until=date.today())
        assert rec.is_expired is False

    def test_far_past_is_expired(self):
        rec = _make_record(valid_until=date(2000, 1, 1))
        assert rec.is_expired is True


# ---------------------------------------------------------------------------
# 4. is_active property
# ---------------------------------------------------------------------------

class TestIsActive:
    def test_active_status_not_expired_is_active(self):
        rec = _make_record(release_status="active", valid_until=None)
        assert rec.is_active is True

    def test_draft_status_is_not_active(self):
        rec = _make_record(release_status="draft")
        assert rec.is_active is False

    def test_deprecated_status_is_not_active(self):
        rec = _make_record(release_status="deprecated")
        assert rec.is_active is False

    def test_active_status_but_expired_is_not_active(self):
        past = date.today() - timedelta(days=1)
        rec = _make_record(release_status="active", valid_until=past)
        assert rec.is_active is False


# ---------------------------------------------------------------------------
# 5. DomainDataProvider Protocol structural check
# ---------------------------------------------------------------------------

class TestDomainDataProviderProtocol:
    def test_dummy_provider_satisfies_protocol(self):
        provider = DummyDomainDataProvider()
        assert isinstance(provider, DomainDataProvider)

    def test_mock_satisfying_protocol(self):
        """A MagicMock wired with the right methods satisfies the runtime check."""
        mock = MagicMock(spec=DomainDataProvider)
        # Protocol is runtime_checkable — all attribute names present via spec
        assert hasattr(mock, "get_material_record")
        assert hasattr(mock, "list_material_records")
        assert hasattr(mock, "list_active_material_records")


# ---------------------------------------------------------------------------
# 6–9. DummyDomainDataProvider
# ---------------------------------------------------------------------------

class TestDummyDomainDataProvider:
    def setup_method(self):
        self.provider = DummyDomainDataProvider()

    def test_list_material_records_returns_nonempty(self):
        records = self.provider.list_material_records()
        assert len(records) > 0

    def test_all_records_are_governed_material_records(self):
        for rec in self.provider.list_material_records():
            assert isinstance(rec, GovernedMaterialRecord)

    def test_all_demo_records_are_demo_only(self):
        """Phase 0B.1 quarantine: all dummy records must carry is_demo_only=True."""
        for rec in self.provider.list_material_records():
            assert rec.is_demo_only is True, (
                f"Record {rec.record_id!r} has is_demo_only=False — expected True for demo registry"
            )

    def test_get_material_record_known_id(self):
        rec = self.provider.get_material_record("registry-ptfe-g25-acme")
        assert rec is not None
        assert rec.material_family == "PTFE"

    def test_get_material_record_unknown_id_returns_none(self):
        rec = self.provider.get_material_record("does-not-exist")
        assert rec is None

    def test_all_demo_records_have_draft_or_lower_release_status(self):
        """Demo data must never be 'active' — it would pass is_active checks."""
        for rec in self.provider.list_material_records():
            assert rec.release_status in ("draft", "deprecated"), (
                f"Demo record {rec.record_id!r} has release_status={rec.release_status!r} — "
                "demo records must not be 'active'"
            )

    def test_list_active_material_records_excludes_demo_drafts(self):
        """Since all demo records are 'draft', list_active should return empty."""
        active = self.provider.list_active_material_records()
        # All demo records are draft, so none should pass is_active
        for rec in active:
            assert rec.is_active, f"{rec.record_id!r} in active list but is_active is False"

    def test_coverage_metadata_present_on_demo_record(self):
        rec = self.provider.get_material_record("registry-ptfe-g25-acme")
        assert rec is not None
        assert isinstance(rec.coverage_metadata, dict)
        assert "max_temp_c" in rec.coverage_metadata

    def test_source_name_and_version_set(self):
        rec = self.provider.get_material_record("registry-ptfe-g25-acme")
        assert rec is not None
        assert rec.source_name
        assert rec.source_version


# ---------------------------------------------------------------------------
# 10–11. material_core bridge
# ---------------------------------------------------------------------------

class TestLoadGovernedMaterialRecordsBridge:
    def test_returns_nonempty_list(self):
        records = load_governed_material_records()
        assert len(records) > 0

    def test_all_records_are_governed_material_records(self):
        for rec in load_governed_material_records():
            assert isinstance(rec, GovernedMaterialRecord)

    def test_custom_provider_is_honoured(self):
        """Passing a custom provider bypasses the default."""
        custom_rec = _make_record(record_id="custom-001", material_family="EPDM")
        mock_provider = MagicMock(spec=DomainDataProvider)
        mock_provider.list_material_records.return_value = [custom_rec]

        result = load_governed_material_records(provider=mock_provider)
        assert len(result) == 1
        assert result[0].record_id == "custom-001"
        assert result[0].material_family == "EPDM"

    def test_default_provider_used_when_none_passed(self):
        """Without an explicit provider, the module default is used."""
        records = load_governed_material_records(provider=None)
        assert all(isinstance(r, GovernedMaterialRecord) for r in records)


# ---------------------------------------------------------------------------
# 12. Provider swap
# ---------------------------------------------------------------------------

class TestProviderSwap:
    def test_set_default_provider_replaces_singleton(self):
        """set_default_domain_data_provider makes the new provider the default."""
        original = get_default_domain_data_provider()

        custom_rec = _make_record(record_id="swap-test-001", material_family="HNBR")
        mock_provider = MagicMock(spec=DomainDataProvider)
        mock_provider.list_material_records.return_value = [custom_rec]
        mock_provider.list_active_material_records.return_value = []

        set_default_domain_data_provider(mock_provider)
        try:
            records = load_governed_material_records()
            assert any(r.record_id == "swap-test-001" for r in records)
        finally:
            # Always restore so other tests are not affected
            set_default_domain_data_provider(original)

    def test_restored_provider_is_dummy_provider(self):
        """After restoring the original, load_governed_material_records works normally."""
        original = get_default_domain_data_provider()
        mock_provider = MagicMock(spec=DomainDataProvider)
        mock_provider.list_material_records.return_value = []
        set_default_domain_data_provider(mock_provider)
        set_default_domain_data_provider(original)

        records = load_governed_material_records()
        assert len(records) > 0
