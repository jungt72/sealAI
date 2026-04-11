"""
Deterministic inquiry payload builder — no LLM involvement.

build_inquiry_payload() constructs the structured JSON payload sent to a
manufacturer when the user triggers an inquiry.  The payload is bound to
the decision_basis_hash so any state change invalidates it.

Usage:
    from app.agent.manufacturers.payload_builder import build_inquiry_payload
    payload = build_inquiry_payload(state_dict, manufacturer)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAYLOAD_VERSION = "sealai_inquiry_v1"

INQUIRY_DISCLAIMER = (
    "Diese Anfrage wurde von SealAI auf Basis der angegebenen technischen "
    "Parameter automatisch erstellt. Die finale Freigabe obliegt dem "
    "Hersteller. SealAI übernimmt keine Haftung für die technische Eignung "
    "der genannten Werkstoffe oder Bauformen."
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_inquiry_payload(
    state: Any,
    manufacturer: dict[str, Any],
) -> dict[str, Any]:
    """Build the structured JSON inquiry payload for a manufacturer.

    Parameters
    ----------
    state:
        SealAI governed session state.  Accepted as a dict, Pydantic model,
        or any object exposing the expected fields via attribute or key access.
    manufacturer:
        Entry from pilot_manufacturers.json (or equivalent capability DB entry).

    Returns
    -------
    dict — fully self-contained payload, bound to decision_basis_hash.
    """
    # ---- Readiness / identity ----
    action = _section(state, "action_readiness")
    case_number: str | None = _get(action, "case_number")
    idempotency_key: str | None = _get(action, "idempotency_key")

    # ---- Decision / preselection ----
    decision = _section(state, "decision")
    basis_hash: str | None = _get(decision, "decision_basis_hash")
    preselection: dict[str, Any] = _get(decision, "preselection") or {}
    material_combination: list[str] = _get(preselection, "material_combination") or []
    fit_score: float | None = _get(preselection, "fit_score")
    open_points: list[str] = _get(decision, "open_points") or []
    assumptions: list[str] = _get(decision, "assumptions") or []

    # ---- Normalized parameters ----
    normalized = _section(state, "normalized")
    sealing_type: str | None = _get(normalized, "sealing_type")
    shaft_diameter_mm: float | None = _get(normalized, "shaft_diameter_mm")
    temperature_max_c: float | None = _get(normalized, "temperature_max_c")
    pressure_max_bar: float | None = _get(normalized, "pressure_max_bar")
    medium_canonical: str | None = _get(normalized, "medium_canonical") or _get(
        normalized, "medium"
    )

    # ---- Derived ----
    derived = _section(state, "derived")
    requirement_class: str | None = _str_or_id(_get(derived, "requirement_class"))
    applicable_norms: list[str] = _get(derived, "applicable_norms") or []

    # ---- Auto-derive basis_hash if missing ----
    if not basis_hash:
        basis_hash = _derive_hash(
            sealing_type, material_combination, shaft_diameter_mm,
            temperature_max_c, pressure_max_bar, medium_canonical,
        )

    return {
        "sealai_version": PAYLOAD_VERSION,
        "case_number": case_number,
        "basis_hash": basis_hash,
        "idempotency_key": idempotency_key,
        "created_at": _utcnow_iso(),
        "recipient": {
            "manufacturer_id": manufacturer.get("id"),
            "slug": manufacturer.get("slug"),
            "name": manufacturer.get("name"),
            "contact": manufacturer.get("inquiry_config", {}).get("contact"),
        },
        "requirements": {
            "sealing_type": sealing_type,
            "material_combination": material_combination,
            "shaft_diameter_mm": shaft_diameter_mm,
            "temperature_max_c": temperature_max_c,
            "pressure_max_bar": pressure_max_bar,
            "medium": medium_canonical,
            "requirement_class": requirement_class,
        },
        "open_points": list(open_points),
        "assumptions": list(assumptions),
        "fit_score": fit_score,
        "applicable_norms": list(applicable_norms),
        "disclaimer": INQUIRY_DISCLAIMER,
    }


def build_inquiry_payload_from_flat(
    *,
    case_number: str | None = None,
    basis_hash: str | None = None,
    idempotency_key: str | None = None,
    sealing_type: str | None = None,
    material_combination: list[str] | None = None,
    shaft_diameter_mm: float | None = None,
    temperature_max_c: float | None = None,
    pressure_max_bar: float | None = None,
    medium_canonical: str | None = None,
    requirement_class: str | None = None,
    open_points: list[str] | None = None,
    assumptions: list[str] | None = None,
    fit_score: float | None = None,
    applicable_norms: list[str] | None = None,
    manufacturer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience builder that accepts flat keyword arguments.

    Useful when state is not yet hydrated into the full six-layer model.
    """
    state = {
        "action_readiness": {
            "case_number": case_number,
            "idempotency_key": idempotency_key,
        },
        "decision": {
            "decision_basis_hash": basis_hash,
            "preselection": {
                "material_combination": material_combination or [],
                "fit_score": fit_score,
            },
            "open_points": open_points or [],
            "assumptions": assumptions or [],
        },
        "normalized": {
            "sealing_type": sealing_type,
            "shaft_diameter_mm": shaft_diameter_mm,
            "temperature_max_c": temperature_max_c,
            "pressure_max_bar": pressure_max_bar,
            "medium_canonical": medium_canonical,
        },
        "derived": {
            "requirement_class": requirement_class,
            "applicable_norms": applicable_norms or [],
        },
    }
    return build_inquiry_payload(state, manufacturer or {})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _section(state: Any, key: str) -> Any:
    """Return a subsection of state (dict key or attribute), defaulting to {}."""
    result = _get(state, key)
    return result if result is not None else {}


def _get(obj: Any, key: str) -> Any:
    """Dict-key or attribute access; returns None when absent."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _str_or_id(value: Any) -> str | None:
    """Extract a string id from a RequirementClass model or plain string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("id") or value.get("code") or str(value)
    # Pydantic model or dataclass
    for attr in ("id", "code", "name"):
        v = getattr(value, attr, None)
        if v is not None:
            return str(v)
    return str(value)


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derive_hash(*parts: Any) -> str:
    """Stable content-derived hash from arbitrary parts."""
    content = "|".join(str(p) for p in parts if p is not None)
    return hashlib.sha256(content.encode()).hexdigest()[:16]
