"""
O-Ring-Nutmaße nach DIN 3770 / ISO 3601-2
Deterministisch — kein LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Einbausituation = Literal["statisch", "dynamisch"]


@dataclass
class NutmaßeResult:
    schnurdurchmesser_mm: float     # nächster Normwert
    einbausituation: str
    nuttiefe_mm: float
    nutbreite_mm: float
    vorpressung_pct: float
    backup_ring_empfohlen: bool
    empfohlene_shore: str
    norm_ref: str = "DIN 3770 / ISO 3601-2"
    hinweis: str = ""


# ---------------------------------------------------------------------------
# Lookup-Tabellen
# Quelle: DIN 3770 / ISO 3601-2
# Schlüssel: d2 (Schnurdurchmesser mm)
# Wert:     (nuttiefe_mm, nutbreite_mm, vorpressung_pct)
# ---------------------------------------------------------------------------
# Vorpressung = (d2 - nuttiefe) / d2 × 100

_STATISCH: dict[float, tuple[float, float, float]] = {
    #   d2      tiefe   breite  press%
    1.78: (1.38,  2.4,  22.5),  # (1.78-1.38)/1.78
    2.62: (2.00,  3.6,  23.7),  # (2.62-2.00)/2.62
    3.53: (2.70,  4.8,  23.5),  # (3.53-2.70)/3.53
    5.33: (4.10,  7.1,  23.1),  # (5.33-4.10)/5.33
    6.99: (5.40,  9.5,  22.7),  # (6.99-5.40)/6.99
}

_DYNAMISCH: dict[float, tuple[float, float, float]] = {
    #   d2      tiefe   breite  press%
    1.78: (1.45,  2.4,  18.5),  # (1.78-1.45)/1.78
    2.62: (2.16,  3.6,  17.6),  # (2.62-2.16)/2.62
    3.53: (2.90,  4.8,  17.8),  # (3.53-2.90)/3.53
    5.33: (4.40,  7.1,  17.4),  # (5.33-4.40)/5.33
    6.99: (5.85,  9.5,  16.3),  # (6.99-5.85)/6.99
}

# Shore-Empfehlung nach Betriebsdruck (Schwellwerte in bar)
_SHORE_STUFEN: list[tuple[float, str]] = [
    ( 25.0, "70 Shore A"),
    (100.0, "70–80 Shore A"),
    (250.0, "80 Shore A"),
    (float("inf"), "90 Shore A"),
]

_BACKUP_GRENZE_STATISCH  = 150.0   # bar
_BACKUP_GRENZE_DYNAMISCH = 100.0   # bar


def lookup_nut(
    schnurdurchmesser_mm: float,
    einbausituation: Einbausituation,
    druck_bar: float,
) -> NutmaßeResult:
    """
    Gibt Nutmaße nach DIN 3770 / ISO 3601-2 zurück.
    Wählt den nächsten Tabellenwert — kein LLM, keine Interpolation.
    """
    table = _STATISCH if einbausituation == "statisch" else _DYNAMISCH

    # Nächster Normwert
    d2 = min(table, key=lambda k: abs(k - schnurdurchmesser_mm))
    nuttiefe, nutbreite, vorpressung = table[d2]

    # Shore-Empfehlung
    shore = next(s for (limit, s) in _SHORE_STUFEN if druck_bar <= limit)

    # Stützring
    grenze = (
        _BACKUP_GRENZE_STATISCH if einbausituation == "statisch"
        else _BACKUP_GRENZE_DYNAMISCH
    )
    backup = druck_bar > grenze

    # Hinweis bei Abweichung oder Stützring
    teile: list[str] = []
    if abs(d2 - schnurdurchmesser_mm) > 0.05:
        teile.append(f"Eingabe {schnurdurchmesser_mm} mm → nächster Normwert: {d2} mm")
    if backup:
        teile.append("Stützring erforderlich")

    return NutmaßeResult(
        schnurdurchmesser_mm=d2,
        einbausituation=einbausituation,
        nuttiefe_mm=nuttiefe,
        nutbreite_mm=nutbreite,
        vorpressung_pct=vorpressung,
        backup_ring_empfohlen=backup,
        empfohlene_shore=shore,
        hinweis=" | ".join(teile),
    )


__all__ = ["lookup_nut", "NutmaßeResult", "Einbausituation"]
