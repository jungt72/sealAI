"""Wissensstand-Referenz (audit §4.3 Versionierung, L8): a single, load-time-fixed identifier for
the knowledge catalogs that could have fed a given pipeline instance's answers.

Deploy-level traceability already exists (``tree_hash`` binds the served image to an adjudicated
eval run — see ``backend/tests/test_tree_hash.py``); this closes the audit's separate "pro Antwort
nein" finding: no field on the response/artifact ties a given recommendation back to the knowledge
catalog state it was grounded against. Each catalog seed already carries its own git-tracked
``version`` string (fachkarten_seed.json, matrix_seed.json, trap_catalog.json, calc_seed.json,
versagensmodi_seed.json) — this module only concatenates the ones actually wired into a pipeline
instance into one string. Pure; no I/O, no LLM.
"""

from __future__ import annotations

_LABELS = (
    ("fk", "fachkarten_version"),
    ("mx", "matrix_version"),
    ("trap", "traps_version"),
    ("calc", "calc_version"),
    ("vm", "versagensmodi_version"),
)


def compute_wissensstand(
    *,
    fachkarten_version: str = "",
    matrix_version: str = "",
    traps_version: str = "",
    calc_version: str = "",
    versagensmodi_version: str = "",
) -> str:
    """Concatenate the wired catalogs' versions as ``label:version`` pairs, joined by ``|``, in a
    fixed label order (fk, mx, trap, calc, vm). A catalog with no version (not wired for this pipeline —
    e.g. ``ground_enabled=False`` leaves matrix/versagensmodi empty) is OMITTED rather than padded,
    so the string never implies a catalog was consulted when it wasn't. All catalogs absent → "".
    """
    values = {
        "fachkarten_version": fachkarten_version,
        "matrix_version": matrix_version,
        "traps_version": traps_version,
        "calc_version": calc_version,
        "versagensmodi_version": versagensmodi_version,
    }
    return "|".join(f"{label}:{values[key]}" for label, key in _LABELS if values[key])
