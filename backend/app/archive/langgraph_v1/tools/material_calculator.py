"""Hilfsfunktionen für Materialberechnungen."""

from __future__ import annotations


def _to_float(value: float, *, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} muss numerisch sein.") from exc
    return number


def material_quantity(
    length_m: float,
    width_m: float,
    density_kg_per_m3: float,
    thickness_m: float,
) -> float:
    """Berechnet die Masse einer rechteckigen Platte in Kilogramm.

    Alle Längenangaben werden in Metern erwartet, die Dichte in Kilogramm pro Kubikmeter.
    """
    length = _to_float(length_m, name="length_m")
    width = _to_float(width_m, name="width_m")
    thickness = _to_float(thickness_m, name="thickness_m")
    density = _to_float(density_kg_per_m3, name="density_kg_per_m3")

    if any(val <= 0 for val in (length, width, thickness)):
        raise ValueError("length_m, width_m und thickness_m müssen größer als 0 sein.")
    if density <= 0:
        raise ValueError("density_kg_per_m3 muss größer als 0 sein.")

    volume_m3 = length * width * thickness
    return volume_m3 * density


def wastage(quantity: float, wastage_percent: float = 5.0) -> float:
    """Wendet einen Verschnitt-Zuschlag auf eine Ausgangsmenge (Kilogramm) an.

    Der Parameter ``wastage_percent`` ist eine Prozentangabe, z.B. 5.0 für fünf Prozent.
    """
    base_quantity = _to_float(quantity, name="quantity")
    if base_quantity < 0:
        raise ValueError("quantity darf nicht negativ sein.")

    percent = _to_float(wastage_percent, name="wastage_percent")
    if percent < 0:
        raise ValueError("wastage_percent darf nicht negativ sein.")

    return base_quantity * (1.0 + percent / 100.0)
