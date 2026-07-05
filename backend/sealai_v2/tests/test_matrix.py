"""§4 Verträglichkeitsmatrix (Gap #2, Step A) — loader + no-fabrication guard + query precision +
the doctrine guard (grounding, NOT Steuerlogik). The matrix is a relational compatibility-VERDICT
table that grounds L1; it must never select/rank/recommend a material.
"""

from __future__ import annotations

import json

import pytest

from sealai_v2.core.contracts import (
    _MATRIX_VERDICTS,
    CompatibilityMatrix,
    GroundingFact,
    MatrixCell,
)
from sealai_v2.knowledge.matrix import (
    CompatibilityMatrixCatalog,
    InProcessCompatibilityMatrix,
    _provenance_authority,
    load_matrix,
)
from sealai_v2.security.tenant import TenantScopeError


def _matrix() -> InProcessCompatibilityMatrix:
    return InProcessCompatibilityMatrix(load_matrix())


def _cell(cid, *, provenance=("owner:x",), material="FKM", medium="Testmedium"):
    return MatrixCell(
        id=cid,
        werkstoff=material,
        medium=medium,
        bedingung="",
        bewertung="vertraeglich",
        begruendung=f"{material} ist vertraeglich mit {medium}.",
        scope={"material": [material], "medium": [medium], "bedingung": []},
        provenance=provenance,
    )


# --- loader + no-fabrication circularity guard -------------------------------------------------


def test_seed_loads_and_every_cell_traces_to_a_reviewed_source():
    cat = load_matrix()
    assert cat.cells, "seed is empty"
    for c in cat.cells:
        assert c.bewertung in _MATRIX_VERDICTS
        assert c.begruendung.strip()
        assert c.scope.get("material"), f"{c.id}: no werkstoff match-tag"
        # no-fabrication: a reviewed source id OR a primary source — zero model-generated cells
        reviewed_prov = any(
            p.lower().startswith(
                ("trap-correct:", "trap:", "owner:", "eval:", "fk-", "fachkarte:")
            )
            for p in c.provenance
        )
        assert reviewed_prov or c.sources, (
            f"{c.id}: no reviewed provenance and no source"
        )


def test_loader_rejects_a_model_sourced_cell(tmp_path):
    """The circularity guard (build-spec §8 'no LLM erdet LLM'): a cell with neither a reviewed
    provenance nor a primary source is a LOAD ERROR — model-generated cells cannot enter."""
    bad = {
        "version": "x",
        "cells": [
            {
                "id": "MX-BAD",
                "werkstoff": "FKM",
                "medium": "Wunschmedium",
                "bedingung": "",
                "bewertung": "vertraeglich",
                "begruendung": "vom Modell erfunden",
                "scope": {
                    "material": ["FKM"],
                    "medium": ["Wunschmedium"],
                    "bedingung": [],
                },
                "provenance": ["model:guess"],
                "sources": [],
            }
        ],
    }
    f = tmp_path / "bad_matrix.json"
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="no LLM erdet LLM|model-generated"):
        load_matrix(f)


def test_loader_rejects_unknown_bewertung(tmp_path):
    bad = {
        "cells": [
            {
                "id": "MX-BAD2",
                "werkstoff": "FKM",
                "medium": "X",
                "bewertung": "super-geeignet",
                "begruendung": "y",
                "scope": {"material": ["FKM"], "medium": ["X"]},
                "provenance": ["owner:test"],
            }
        ]
    }
    f = tmp_path / "bad2.json"
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="bewertung"):
        load_matrix(f)


# --- query precision (the eval-relevant compatibility cases) -----------------------------------


@pytest.mark.parametrize(
    "label,query,expect_id",
    [
        (
            "TRAP-01",
            "Dichtung mit FKM für Heißdampf-Sterilisation bei 140 °C",
            "MX-FKM-DAMPF",
        ),
        (
            "TRAP-02",
            "EPDM-O-Ringe quellen in unserem Hydrauliköl auf",
            "MX-EPDM-MINERALOEL",
        ),
        (
            "TRAP-03",
            "NBR-Dichtung für eine Welle, Maschine steht im Freien",
            "MX-NBR-OZON",
        ),
        ("TRAP-04", "reiner PTFE-O-Ring als statische Dichtung", "MX-PTFE-STATISCH"),
        ("COMBO-01", "FKM gegen verdünnte Natronlauge und hält 200 °C", "MX-FKM-LAUGE"),
        (
            "COMBO-02",
            "VMQ für meine schnelldrehende Wellendichtung",
            "MX-VMQ-DYNAMISCH",
        ),
        (
            "COMBO-03",
            "lebensmittelechte Dichtung für eine Schokoladen-Anlage, EPDM food-grade?",
            "MX-EPDM-FETTLEBENSMITTEL",
        ),
        (
            "DEFAULT",
            "wir nehmen immer FKM, jetzt mit aminhaltigem Kühlmittel",
            "MX-FKM-AMIN",
        ),
    ],
)
def test_query_grounds_the_right_compatibility_verdict(label, query, expect_id):
    facts = _matrix().query(tenant_id="t1", query_text=query)
    ids = [f.card_id for f in facts]
    assert expect_id in ids, f"{label}: {expect_id} not surfaced (got {ids})"
    assert all(f.kind == "matrix" for f in facts)


@pytest.mark.parametrize(
    "query",
    [
        "Ist FKM beständig gegen Essigsäure?",  # UNCERT-03 — no reviewed cell
        "Hallo, wer bist du?",  # greeting
        "Erklär mir die Eigenschaften von PTFE für Dichtungen",  # knowledge, no medium/condition
        "Bitte empfiehl mir ein Material für die Anwendung mit Wasserdampf",  # no material named
    ],
)
def test_query_stays_silent_without_a_reviewed_cell(query):
    """Sparse by design: no reviewed verdict for the (werkstoff × medium) → the matrix returns
    nothing rather than fabricate. This is the no-fabrication property at query time."""
    assert _matrix().query(tenant_id="t1", query_text=query) == ()


def test_query_tenant_scope_is_mandatory_p0():
    m = _matrix()
    for bad in ("", "   "):
        with pytest.raises(TenantScopeError):
            m.query(tenant_id=bad, query_text="FKM Heißdampf")


def test_protocol_conformance():
    assert isinstance(_matrix(), CompatibilityMatrix)


# --- doctrine guard: grounding, NOT Steuerlogik ------------------------------------------------

# user-directed selection / ranking / recommendation language — forbidden in matrix output (the
# matrix states a compatibility VERDICT + mechanism; the comparison/selection is L1's job).
_STEUERLOGIK_TOKENS = (
    "verwende",
    " nimm ",
    "wähle",
    "empfehl",
    "stattdessen",
    "solltest",
    "greife zu",
    "besser als",
    "geeigneter als",
    "am besten",
    "vorzuziehen",
    "wir nehmen",
)


def test_no_cell_introduces_selection_or_ranking():
    for c in load_matrix().cells:
        low = c.begruendung.lower()
        for tok in _STEUERLOGIK_TOKENS:
            assert tok not in low, f"{c.id}: Steuerlogik token {tok!r} in begruendung"


def test_matrix_grounding_facts_carry_provenance_and_no_selection():
    facts = _matrix().query(
        tenant_id="t1", query_text="VMQ schnelldrehende Wellendichtung"
    )
    assert facts
    for f in facts:
        assert isinstance(f, GroundingFact) and f.kind == "matrix"
        assert "Verträglichkeitsmatrix" in f.quelle and "reviewed" in f.quelle
        low = f.text.lower()
        assert not any(tok in low for tok in _STEUERLOGIK_TOKENS)


# --- P2-D: provenance-authority tie-break (Quellenhierarchie/Konfliktlogik §4.3) ----------------


@pytest.mark.parametrize(
    "provenance,expected",
    [
        (("eval:CONFLICT-01",), 3),
        (("owner:x",), 2),
        (("trap-correct:TRAP-X",), 1),
        (("trap:TRAP-X",), 1),
        (("fk-EPDM-1",), 0),
        (("fachkarte:FK-1",), 0),
        ((), 0),
        (
            ("model:guess",),
            0,
        ),  # no reviewed prefix — degrades safely, not a loader-valid cell anyway
    ],
)
def test_provenance_authority_ranks_each_prefix(provenance, expected):
    assert _provenance_authority(_cell("MX-T", provenance=provenance)) == expected


def test_provenance_authority_takes_the_max_across_multiple_entries():
    c = _cell("MX-T", provenance=("fk-EPDM-1", "owner:x"))
    assert _provenance_authority(c) == 2  # owner: (2) beats fk- (0)


def test_tie_break_prefers_higher_provenance_authority_at_equal_relevance():
    # two cells, IDENTICAL scope (same score) — MX-A would win the OLD alphabetical tie-break, but
    # MX-Z (eval: — an adjudicated conflict resolution) must win under the new provenance tie-break.
    low = _cell("MX-A", provenance=("fk-OTHER",), material="FKM", medium="Testmedium")
    high = _cell(
        "MX-Z", provenance=("eval:CONFLICT-01",), material="FKM", medium="Testmedium"
    )
    cat = CompatibilityMatrixCatalog(cells=(low, high))
    facts = InProcessCompatibilityMatrix(cat).query(
        tenant_id="t1", query_text="FKM Testmedium"
    )
    assert [f.card_id for f in facts] == ["MX-Z", "MX-A"]


def test_relevance_still_beats_provenance_authority():
    # a cell with MORE scope hits always wins, regardless of provenance tier — the tie-break only
    # decides between EQUALLY relevant cells, it never overrides the primary relevance ranking.
    weaker_but_high_authority = _cell(
        "MX-A", provenance=("eval:CONFLICT-01",), material="FKM", medium="Testmedium"
    )
    stronger_but_low_authority = MatrixCell(
        id="MX-Z",
        werkstoff="FKM",
        medium="Testmedium",
        bedingung="Hochdruck",
        bewertung="bedingt",
        begruendung="FKM ist bedingt vertraeglich mit Testmedium bei Hochdruck.",
        scope={
            "material": ["FKM"],
            "medium": ["Testmedium"],
            "bedingung": ["Hochdruck"],
        },
        provenance=("fk-OTHER",),
    )
    cat = CompatibilityMatrixCatalog(
        cells=(weaker_but_high_authority, stronger_but_low_authority)
    )
    facts = InProcessCompatibilityMatrix(cat).query(
        tenant_id="t1", query_text="FKM Testmedium Hochdruck"
    )
    assert facts[0].card_id == "MX-Z"  # 3 scope hits beats 2, despite lower authority
