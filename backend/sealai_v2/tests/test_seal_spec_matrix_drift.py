"""Allowlist-drift guard: the Verträglichkeitsmatrix vocabulary must stay a
subset of what the extractor can match.

The material vocabulary lives duplicated — ``_MATERIAL_SYNONYMS`` in the
extractor vs. ``scope.material`` in ``knowledge/matrix_seed.json``. If the matrix
allowlist grows, the extractor would silently diverge. Import boundary I3 forbids
a runtime ``knowledge/`` import, so the cross-check lives here as a TEST, not in
the runtime path: the seed is read STATICALLY (``json.load``), with NO import of
``knowledge/``.

Doctrine sibling of "the kernel owns the numbers": the matrix owns the material
vocabulary; this test keeps the extractor's copy honest. The assertion is
deliberately ONE-DIRECTIONAL — the extractor may know synonyms that are not
standalone matrix tags (FPM, VMQ, AFLAS), but no matrix tag may be unknown to the
extractor.

Deterministic, offline, no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

from sealai_v2.core.seal_spec_extract import _MATERIAL_SYNONYMS

_MATRIX_SEED = Path(__file__).resolve().parents[1] / "knowledge" / "matrix_seed.json"


def _matrix_material_tags() -> set[str]:
    """Distinct set of all cells[*].scope.material tags — static read, no import."""
    data = json.loads(_MATRIX_SEED.read_text(encoding="utf-8"))
    tags: set[str] = set()
    for cell in data["cells"]:
        tags.update(cell.get("scope", {}).get("material", []))
    return tags


def test_matrix_seed_present_and_nonempty():
    tags = _matrix_material_tags()
    assert tags, "matrix_seed.json yielded no scope.material tags — fixture broken"


def test_matrix_material_tags_are_extractor_input_tokens():
    extractor_tokens = {token.lower() for token in _MATERIAL_SYNONYMS}
    missing = sorted(
        tag for tag in _matrix_material_tags() if tag.lower() not in extractor_tokens
    )
    assert not missing, (
        f"Matrix-Tag(s) nicht im Extractor — Allowlist nachziehen: {missing}. "
        "Die Matrix-Werkstoffvokabel muss eine Teilmenge der _MATERIAL_SYNONYMS-"
        "Eingabe-Token sein (kein Matrix-Tag darf dem Extractor unbekannt sein)."
    )
