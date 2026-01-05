"""Lookup-Stubs für Normen und Toleranzen."""

from __future__ import annotations

from typing import Dict

_STANDARDS: Dict[str, str] = {
    "DIN EN 1092-1": "Flansche und ihre Verbindungen – Rundflansche aus Stahl (Teil 1).",
    "DIN EN ISO 3302-1": "Toleranzen für Elastomer-Formteile – Maße und Oberflächen (Klasse M2).",
    "DIN EN 681-1": "Elastomer-Dichtungen für Wasser- und Abwasseranwendungen – Anforderungen.",
}

_TOLERANCES: Dict[str, Dict[str, str]] = {
    "DIN EN 1092-1": {
        "bohrung": "Nenndurchmesser +0.3/-0.1 mm für DN ≤ 200.",
        "laufläche": "Planlaufabweichung ≤ 0.15 mm für PN 40.",
    },
    "DIN EN ISO 3302-1": {
        "profilhöhe": "Toleranzklasse M2: ±0.40 mm bei 6 mm ≤ Nennmaß < 10 mm.",
        "breite": "Toleranzklasse M2: ±0.30 mm bei 4 mm ≤ Nennmaß < 6 mm.",
    },
    "DIN EN 681-1": {
        "dichte": "Härte 60 ±5 Shore A, Dichte 1.15 ±0.03 g/cm³.",
        "temperaturbereich": "Betriebsbereich -40 °C bis +120 °C (Materialgruppe WA).",
    },
}


def find_standard(code: str) -> str:
    """Lieferbare Kurzbeschreibung zu einem Normcode (deterministischer Offline-Lookup)."""
    key = _normalize_code(code)
    description = _STANDARDS.get(key)
    if description:
        return f"{code.strip()}: {description}"
    return (
        f"Für '{code.strip()}' ist keine hinterlegte Kurzbeschreibung vorhanden. "
        "Bitte Normenverzeichnis konsultieren."
    )


def get_tolerance(standard_code: str, feature: str) -> str:
    """Gibt eine deterministische Toleranzbeschreibung für ein Merkmal innerhalb der Norm zurück."""
    code_key = _normalize_code(standard_code)
    feature_key = feature.strip().lower()
    if not feature_key:
        raise ValueError("feature darf nicht leer sein.")

    tolerances = _TOLERANCES.get(code_key)
    if not tolerances:
        return (
            f"Für '{standard_code.strip()}' liegen keine Toleranzdaten vor. "
            "Bitte Originalnorm prüfen."
        )

    tolerance = tolerances.get(feature_key)
    if tolerance:
        return f"{standard_code.strip()} – {feature.strip()}: {tolerance}"

    available = ", ".join(sorted(tolerances.keys()))
    return (
        f"Für '{feature.strip()}' ist in {standard_code.strip()} keine Toleranz hinterlegt. "
        f"Verfügbare Merkmale: {available or 'keine'}."
    )


def _normalize_code(code: str) -> str:
    cleaned = (code or "").strip()
    if not cleaned:
        raise ValueError("code darf nicht leer sein.")
    return cleaned.upper()
