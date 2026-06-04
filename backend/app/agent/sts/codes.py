"""Code-Lookup-Funktionen fuer STS-Kataloge."""

from __future__ import annotations

from typing import Any

from app.agent.sts.loader import load_catalog

# Prefix-Mapping fuer is_valid_code / generische Lookups
_PREFIX_ORDER = ["STS-OPEN", "STS-TYPE", "STS-MAT", "STS-MED", "STS-RS"]


def _detect_prefix(code: str) -> str | None:
    """Ermittle den Katalog-Prefix eines Codes."""
    for prefix in _PREFIX_ORDER:
        if code.startswith(prefix):
            return prefix
    return None


def get_material(code: str) -> dict[str, Any] | None:
    """Materialcode nachschlagen. Gibt None zurueck wenn nicht gefunden."""
    catalog = load_catalog("STS-MAT")
    return catalog.get(code)


def get_sealing_type(code: str) -> dict[str, Any] | None:
    """Dichtungstyp nachschlagen."""
    catalog = load_catalog("STS-TYPE")
    return catalog.get(code)


def get_requirement_class(code: str) -> dict[str, Any] | None:
    """Requirement Class nachschlagen."""
    catalog = load_catalog("STS-RS")
    return catalog.get(code)


def get_medium(code: str) -> dict[str, Any] | None:
    """Mediumcode nachschlagen."""
    catalog = load_catalog("STS-MED")
    return catalog.get(code)


def get_open_point(code: str) -> dict[str, Any] | None:
    """Offenen Pruefpunkt nachschlagen."""
    catalog = load_catalog("STS-OPEN")
    return catalog.get(code)


def is_valid_code(code: str) -> bool:
    """Pruefe ob ein STS-Code in irgendeinem Katalog existiert."""
    prefix = _detect_prefix(code)
    if prefix is None:
        return False
    catalog = load_catalog(prefix)
    return code in catalog


def list_codes(prefix: str) -> list[str]:
    """Alle Codes eines Katalogs auflisten."""
    catalog = load_catalog(prefix)
    return sorted(catalog.keys())
