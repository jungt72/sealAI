"""Laden und Validieren der STS-Seed-Dateien."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STS_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "sts"

# Prefix → (filename, required_fields)
_CATALOG_SPEC: dict[str, tuple[str, list[str]]] = {
    "STS-MAT": (
        "materials.json",
        ["canonical_name", "material_family", "temperature_max_c"],
    ),
    "STS-TYPE": (
        "sealing_types.json",
        ["canonical_name", "category"],
    ),
    "STS-RS": (
        "requirement_classes.json",
        ["canonical_name", "severity"],
    ),
    "STS-MED": (
        "media.json",
        ["canonical_name", "category"],
    ),
    "STS-OPEN": (
        "open_points.json",
        ["canonical_name", "category", "severity"],
    ),
}

_cache: dict[str, dict[str, Any]] = {}


def _load_file(filename: str) -> dict[str, Any]:
    path = STS_DATA_DIR / filename
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_catalog(prefix: str) -> dict[str, Any]:
    """Lade einen einzelnen Katalog anhand seines Prefix (z.B. 'STS-MAT')."""
    if prefix in _cache:
        return _cache[prefix]
    spec = _CATALOG_SPEC.get(prefix)
    if spec is None:
        raise ValueError(f"Unbekannter STS-Prefix: {prefix}")
    data = _load_file(spec[0])
    _cache[prefix] = data
    return data


def load_all() -> dict[str, dict[str, Any]]:
    """Lade alle STS-Kataloge. Gibt dict[prefix, catalog_data] zurueck."""
    result: dict[str, dict[str, Any]] = {}
    for prefix in _CATALOG_SPEC:
        result[prefix] = load_catalog(prefix)
    return result


class ValidationError(Exception):
    """Fehler bei der Validierung der STS-Seed-Daten."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"{len(errors)} Validierungsfehler: {'; '.join(errors)}")


def validate_catalog(prefix: str, data: dict[str, Any]) -> list[str]:
    """Validiere einen Katalog. Gibt Liste von Fehlermeldungen zurueck (leer = ok)."""
    spec = _CATALOG_SPEC.get(prefix)
    if spec is None:
        return [f"Unbekannter Prefix: {prefix}"]

    _, required_fields = spec
    errors: list[str] = []

    if not data:
        errors.append(f"{prefix}: Katalog ist leer")
        return errors

    seen_names: set[str] = set()
    for code, entry in data.items():
        # Prefix-Check
        if not code.startswith(prefix):
            errors.append(f"{code}: Code beginnt nicht mit {prefix}")

        # Pflichtfelder
        for field in required_fields:
            if field not in entry:
                errors.append(f"{code}: Pflichtfeld '{field}' fehlt")

        # Duplikat canonical_name
        name = entry.get("canonical_name", "")
        if name in seen_names:
            errors.append(f"{code}: Doppelter canonical_name '{name}'")
        seen_names.add(name)

    return errors


def validate_all() -> list[str]:
    """Validiere alle STS-Kataloge. Gibt Liste von Fehlern zurueck (leer = ok)."""
    all_errors: list[str] = []
    catalogs = load_all()
    for prefix, data in catalogs.items():
        all_errors.extend(validate_catalog(prefix, data))
    return all_errors


def clear_cache() -> None:
    """Cache leeren (fuer Tests)."""
    _cache.clear()
