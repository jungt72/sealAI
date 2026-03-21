"""
Deterministic Boundary & Coverage Block Injector — Phase 0B.2

Rules:
- FAST_PATH  → always append ORIENTATION_DISCLAIMER (non-negotiable, not LLM-generated)
- STRUCTURED → append Scope-of-Validity block (coverage status + known unknowns)
- Demo data  → if synthetic registry data was in scope, declare it explicitly

These strings are injected AFTER LLM output — they are never produced by the LLM itself.
"""
from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Fast-path: orientation disclaimer (invariant)
# ---------------------------------------------------------------------------

FAST_PATH_DISCLAIMER = (
    "---\n"
    "⚠️ Unverbindliche Orientierung — kein Ersatz für eine vollständige technische "
    "Qualifikation oder Herstellerfreigabe."
)

# ---------------------------------------------------------------------------
# Structured-path: scope-of-validity block
# ---------------------------------------------------------------------------

_STRUCTURED_PREAMBLE = "ℹ️ Technischer Scope-of-Validity:"

_COVERAGE_NOTES: dict[str | None, str] = {
    "full": "Alle Kernparameter vorhanden.",
    "partial": "Teilweise abgedeckt — einige Parameter fehlen noch.",
    "limited": "Eingeschränkte Datenbasis — wichtige Parameter ausstehend.",
}

_DEMO_DATA_NOTE = (
    "Enthält synthetische Referenzdaten zur Veranschaulichung "
    "(keine governe Materialdaten, nicht produktiv verwenden)."
)

STRUCTURED_PATH_SUFFIX = "Keine bindende Material- oder Compound-Freigabe."

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


REVIEW_PENDING_PREFIX = "⏳ **Experten-Review ausstehend:**"


def _build_review_pending_line(review_reason: str) -> str:
    """Return the deterministic review-pending notice line."""
    return (
        f"{REVIEW_PENDING_PREFIX} Dieser Fall wurde zur manuellen Prüfung durch einen "
        f"Application Engineer markiert. (Grund: {review_reason})"
    )


def build_boundary_block(
    path: str,
    *,
    coverage_status: Optional[str] = None,
    known_unknowns: Optional[list[str]] = None,
    demo_data_present: bool = False,
    review_required: bool = False,
    review_reason: str = "",
) -> str:
    """Return the deterministic boundary string for the given routing path.

    Args:
        path: "fast" | "structured"
        coverage_status: "full" | "partial" | "limited" | None
        known_unknowns: list of parameter names blocking release
        demo_data_present: True if synthetic/demo registry data was in scope
        review_required: True when HITL review is pending (Phase A3)
        review_reason: human-readable trigger reason for the review notice

    Returns:
        A ready-to-append boundary string (begins with ``---``).
    """
    if path == "fast":
        return FAST_PATH_DISCLAIMER

    # Structured path — build variable block
    parts: list[str] = [_STRUCTURED_PREAMBLE]

    coverage_note = _COVERAGE_NOTES.get(coverage_status)
    if coverage_note:
        parts.append(coverage_note)

    if known_unknowns:
        unknowns_str = ", ".join(known_unknowns)
        parts.append(f"Fehlende / ungeklärte Parameter: {unknowns_str}.")

    if demo_data_present:
        parts.append(_DEMO_DATA_NOTE)

    parts.append(STRUCTURED_PATH_SUFFIX)

    block = "---\n" + " ".join(parts)

    # Phase A3: HITL review notice is injected after the scope block, never by the LLM
    if review_required:
        block = block + "\n\n" + _build_review_pending_line(review_reason)

    return block
