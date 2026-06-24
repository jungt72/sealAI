"""Allowlist-drift guard: the Verträglichkeitsmatrix MEDIUM vocabulary must stay a
subset of what the medium extractor can match.

Sibling of ``test_seal_spec_matrix_drift`` for the medium axis. The vocabulary
lives duplicated — ``_MEDIUM_SYNONYMS`` in the extractor vs. ``scope.medium`` in
``knowledge/matrix_seed.json``. Import boundary I3 forbids a runtime
``knowledge/`` import, so the cross-check lives here as a TEST: the seed is read
STATICALLY (``json.load``), with NO import of ``knowledge/``.

Doctrine sibling of "the kernel owns the numbers": the matrix owns the medium
vocabulary; this test keeps the extractor's copy honest. ONE-DIRECTIONAL — the
extractor may know synonyms that are not standalone matrix tags, but no matrix
medium tag may be unknown to the extractor (else the Gegencheck would silently
miss media the matrix can actually judge).

Deterministic, offline, no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

from sealai_v2.core.medium_extract import _MEDIUM_SYNONYMS

_MATRIX_SEED = Path(__file__).resolve().parents[1] / "knowledge" / "matrix_seed.json"


def _matrix_medium_tags() -> set[str]:
    """Distinct set of all cells[*].scope.medium tags — static read, no import."""
    data = json.loads(_MATRIX_SEED.read_text(encoding="utf-8"))
    tags: set[str] = set()
    for cell in data["cells"]:
        tags.update(cell.get("scope", {}).get("medium", []))
    return tags


def test_matrix_seed_has_medium_tags():
    assert _matrix_medium_tags(), "matrix_seed.json yielded no scope.medium tags"


def test_matrix_medium_tags_are_extractor_input_tokens():
    extractor_tokens = {token.lower() for token in _MEDIUM_SYNONYMS}
    missing = sorted(
        tag for tag in _matrix_medium_tags() if tag.lower() not in extractor_tokens
    )
    assert not missing, (
        f"Matrix-Medium-Tag(s) nicht im Extractor — Allowlist nachziehen: {missing}. "
        "Die Matrix-Medienvokabel muss eine Teilmenge der _MEDIUM_SYNONYMS-Eingabe-"
        "Token sein (kein Matrix-Tag darf dem Extractor unbekannt sein)."
    )
