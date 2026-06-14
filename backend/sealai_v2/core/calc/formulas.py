"""Deterministic calc formulas — pure, reviewed CODE (build-spec §4).

NOT eval()'d from data, NOT LLM-derived: each function is hand-written, owner-reviewed code bound to
a registry calc-def by id. The registry (``knowledge/calc_registry.py``) holds the metadata
(units / validity / source / review_state); this module holds the math. Inputs arrive in the
calc-def's declared units; functions take keyword args whose names match the def's input names.
"""

from __future__ import annotations

import math


def umfangsgeschwindigkeit(*, d1_mm: float, rpm: float) -> float:
    """Umfangsgeschwindigkeit der Dichtkante: v = π · d · n. d [mm], n [1/min] → v [m/s]
    (v = π · d1_mm · rpm / 60000)."""
    return math.pi * (d1_mm / 1000.0) * (rpm / 60.0)


def pv_wert(*, p_bar: float, v_m_s: float) -> float:
    """PV-Wert = Flächenpressung × Gleitgeschwindigkeit. p [bar], v [m/s] → PV [bar·m/s]."""
    return p_bar * v_m_s


def verpressung_prozent(*, schnurstaerke_mm: float, nuttiefe_mm: float) -> float:
    """Radiale O-Ring-Verpressung: (Schnurstärke − Nuttiefe) / Schnurstärke · 100 [%]."""
    if schnurstaerke_mm <= 0:
        raise ValueError("schnurstaerke_mm must be > 0")
    return (schnurstaerke_mm - nuttiefe_mm) / schnurstaerke_mm * 100.0


# id → bound implementation. The registry asserts every REVIEWED calc-def has an entry here
# (a reviewed def without bound code is a load error — formulas are code, not data).
FORMULAS = {
    "umfangsgeschwindigkeit": umfangsgeschwindigkeit,
    "pv_wert": pv_wert,
    "verpressung_prozent": verpressung_prozent,
}
