"""
Deterministic fit_score computation — no LLM, no randomness.

fit_score ∈ [0.0, 1.0] quantifies how well a manufacturer matches the
current governed state. It is NOT a probability and must never be
described as such in any outward response.

Usage:
    from app.agent.domain.fit_score import compute_fit_score
    score = compute_fit_score(manufacturer_dict, derived, normalized)
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Geographic constants
# ---------------------------------------------------------------------------

EU_COUNTRIES: frozenset[str] = frozenset(
    [
        "AT", "BE", "BG", "CY", "CZ", "DK", "EE", "FI", "FR",
        "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
        "NL", "PL", "PT", "RO", "SE", "SI", "SK",
        # EEA
        "IS", "LI", "NO",
        # CH — not EU but operationally equivalent for logistics
        "CH",
    ]
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_fit_score(
    manufacturer: dict[str, Any],
    derived_state: Any,
    normalized_state: Any,
) -> float:
    """Compute a deterministic fit score for one manufacturer.

    Parameters
    ----------
    manufacturer:
        Entry from pilot_manufacturers.json (or equivalent structure).
    derived_state:
        Object (or dict) with attributes/keys:
          - pressure_bar: float
          - temp_c: float
          - detected_industries: list[str]
    normalized_state:
        Object (or dict) with attributes/keys:
          - shaft_diameter_mm: float | None

    Returns
    -------
    float in [0.0, 1.0], rounded to 3 decimal places.
    """
    caps: dict[str, Any] = manufacturer.get("capabilities", {})
    score = 0.0

    # ------------------------------------------------------------------
    # 40 % — Specialty match: STS-TYPE + STS-MAT
    # ------------------------------------------------------------------
    sts_type: str | None = _get(derived_state, "sealing_type") or _get(
        normalized_state, "sealing_type"
    )
    sts_mat: str | None = _get(derived_state, "material") or _get(
        normalized_state, "material"
    )

    type_match = bool(
        sts_type and sts_type in caps.get("sealing_types", [])
    )
    mat_match = bool(
        sts_mat and sts_mat in caps.get("materials", [])
    )
    score += 0.40 * (0.5 * type_match + 0.5 * mat_match)

    # ------------------------------------------------------------------
    # 30 % — Capability completeness: pressure, temperature, shaft ∅
    # ------------------------------------------------------------------
    pressure_bar: float | None = _get(derived_state, "pressure_bar")
    temp_c: float | None = _get(derived_state, "temp_c")
    shaft_mm: float | None = _get(normalized_state, "shaft_diameter_mm")

    pressure_ok = (
        pressure_bar is None
        or pressure_bar <= caps.get("pressure_max_bar", 0)
    )
    temp_ok = (
        temp_c is None
        or temp_c <= caps.get("temperature_max_c", 0)
    )
    shaft_ok: bool
    if shaft_mm is None:
        shaft_ok = True  # unknown → assume compatible
    else:
        shaft_ok = (
            caps.get("shaft_diameter_min_mm", 0)
            <= shaft_mm
            <= caps.get("shaft_diameter_max_mm", 0)
        )

    score += 0.30 * ((int(pressure_ok) + int(temp_ok) + int(shaft_ok)) / 3)

    # ------------------------------------------------------------------
    # 20 % — Specialty overlap with detected industry context
    # ------------------------------------------------------------------
    detected_industries: list[str] = _get(derived_state, "detected_industries") or []
    industry_match = bool(
        set(detected_industries) & set(manufacturer.get("specialty", []))
    )
    score += 0.20 * int(industry_match)

    # ------------------------------------------------------------------
    # 10 % — Geographic proximity
    # ------------------------------------------------------------------
    country: str = manufacturer.get("location", {}).get("country", "")
    if country == "DE":
        geo_score = 1.0
    elif country in EU_COUNTRIES:
        geo_score = 0.5
    else:
        geo_score = 0.0
    score += 0.10 * geo_score

    return round(score, 3)


def rank_manufacturers(
    manufacturers: list[dict[str, Any]],
    derived_state: Any,
    normalized_state: Any,
    *,
    active_only: bool = True,
) -> list[tuple[float, dict[str, Any]]]:
    """Return (score, manufacturer) pairs sorted descending by score.

    Only active manufacturers are included when active_only=True.
    """
    results = []
    for mfr in manufacturers:
        if active_only and not mfr.get("active", True):
            continue
        score = compute_fit_score(mfr, derived_state, normalized_state)
        results.append((score, mfr))
    results.sort(key=lambda t: t[0], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get(obj: Any, key: str) -> Any:
    """Attribute or dict key access, returns None if absent."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
