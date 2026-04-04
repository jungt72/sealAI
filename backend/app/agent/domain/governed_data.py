"""
Governed Domain Data Layer — Phase A4.

Provides the typed abstraction for all governed material records, decoupling
consumers from the concrete data source (flat-file, DB, external API, etc.).

Architecture (Ports & Adapters):
- GovernedMaterialRecord  — canonical immutable value object
- DomainDataProvider      — Port (Protocol); concrete adapters implement this
- DummyDomainDataProvider — Demo-only Adapter; wraps the current flat registry

Consumers MUST use DomainDataProvider — never import flat-file loaders directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Value Object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernedMaterialRecord:
    """
    Canonical representation of a governed material entry.

    All fields required by the masterplan (A4) are present.
    `is_demo_only` bridges Phase 0B.1 quarantine semantics.
    `is_expired`   is a derived property — never set manually.
    """

    # Identity
    record_id: str
    material_family: str

    # Provenance
    source_name: str              # e.g. "Hersteller X Freigabeliste"
    source_version: str           # e.g. "v2025.1"

    # Temporal validity
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None

    # Lifecycle
    release_status: str = "draft"         # "active" | "deprecated" | "draft"
    conflict_status: str = "none"         # "none" | "superseded_by_newer_version"

    # Scope metadata
    coverage_metadata: dict[str, Any] = field(default_factory=dict)

    # Phase 0B.1 quarantine bridge
    is_demo_only: bool = True

    # Optional enrichment fields (may be None for family-level records)
    grade_name: Optional[str] = None
    manufacturer_name: Optional[str] = None

    # ---------------------------------------------------------------------------
    # Derived properties
    # ---------------------------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """True when valid_until is set and is strictly before today."""
        if self.valid_until is None:
            return False
        return self.valid_until < date.today()

    @property
    def is_active(self) -> bool:
        """True when release_status is 'active' and the record is not expired."""
        return self.release_status == "active" and not self.is_expired

    def __post_init__(self) -> None:
        if self.release_status not in {"active", "deprecated", "draft"}:
            raise ValueError(
                f"release_status must be 'active', 'deprecated', or 'draft', "
                f"got {self.release_status!r}"
            )
        if self.conflict_status not in {"none", "superseded_by_newer_version"}:
            raise ValueError(
                f"conflict_status must be 'none' or 'superseded_by_newer_version', "
                f"got {self.conflict_status!r}"
            )


# ---------------------------------------------------------------------------
# Port (Provider Protocol)
# ---------------------------------------------------------------------------

@runtime_checkable
class DomainDataProvider(Protocol):
    """
    Port for governed domain data access.

    Adapters implement this Protocol.  Consumers depend only on this interface —
    they must never import concrete loaders or flat-file helpers directly.
    """

    def get_material_record(self, record_id: str) -> Optional[GovernedMaterialRecord]:
        """Return the governed record for *record_id*, or None if not found."""
        ...

    def list_material_records(self) -> list[GovernedMaterialRecord]:
        """Return all governed material records managed by this provider."""
        ...

    def list_active_material_records(self) -> list[GovernedMaterialRecord]:
        """Return only records where is_active is True."""
        ...


# ---------------------------------------------------------------------------
# Demo Adapter (wraps the current flat registry — Phase 0B.1 quarantined)
# ---------------------------------------------------------------------------

def _build_demo_records() -> tuple[GovernedMaterialRecord, ...]:
    """
    Construct GovernedMaterialRecord objects from the quarantined flat registry.

    These entries are demo-only.  They are kept here so the rest of the system
    can reference the provider interface without knowing about material_core internals.
    """
    return (
        GovernedMaterialRecord(
            record_id="registry-ptfe-g25-acme",
            material_family="PTFE",
            grade_name="G25",
            manufacturer_name="Acme",
            source_name="Demo Registry v1",
            source_version="v2025.1-demo",
            valid_from=None,
            valid_until=None,
            release_status="active",
            conflict_status="none",
            coverage_metadata={
                "max_temp_c": 260,
                "max_pressure_bar": 16,
                "allowed_media": ["water", "acids", "steam"],
                "requirement_class_ids": ["PTFE10", "PTFE-GEN-1", "GENERAL-B1"],
                "supported_seal_types": ["gasket", "radial_shaft_seal"],
                "capability_hints": ["steam_service", "high_temperature_window"],
            },
            is_demo_only=True,
        ),
        GovernedMaterialRecord(
            record_id="registry-ptfe-g10-sealtech",
            material_family="PTFE",
            grade_name="G10",
            manufacturer_name="SealTech",
            source_name="Demo Registry v1",
            source_version="v2025.1-demo",
            valid_from=None,
            valid_until=None,
            release_status="active",
            conflict_status="none",
            coverage_metadata={
                "max_temp_c": 210,
                "max_pressure_bar": 14,
                "allowed_media": ["water", "steam"],
                "requirement_class_ids": [],
                "supported_seal_types": ["gasket"],
                "capability_hints": ["steam_service", "standard_pressure_window"],
            },
            is_demo_only=True,
        ),
    )


class DummyDomainDataProvider:
    """
    Demo-only adapter for the Phase 0B.1 quarantined material registry.

    Satisfies DomainDataProvider.  Replace with a DB-backed adapter when
    governed data is available (Phase A4 full roll-out).
    """

    def __init__(self) -> None:
        self._records: dict[str, GovernedMaterialRecord] = {
            r.record_id: r for r in _build_demo_records()
        }

    def get_material_record(self, record_id: str) -> Optional[GovernedMaterialRecord]:
        return self._records.get(record_id)

    def list_material_records(self) -> list[GovernedMaterialRecord]:
        return list(self._records.values())

    def list_active_material_records(self) -> list[GovernedMaterialRecord]:
        return [r for r in self._records.values() if r.is_active]


# ---------------------------------------------------------------------------
# Module-level default provider (swap out for production adapter later)
# ---------------------------------------------------------------------------

_DEFAULT_PROVIDER: DomainDataProvider = DummyDomainDataProvider()


def get_default_domain_data_provider() -> DomainDataProvider:
    """Return the module-level DomainDataProvider singleton.

    Tests can replace this by calling `set_default_domain_data_provider`.
    """
    return _DEFAULT_PROVIDER


def set_default_domain_data_provider(provider: DomainDataProvider) -> None:
    """Swap the default provider (e.g. for testing or production wiring)."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = provider
