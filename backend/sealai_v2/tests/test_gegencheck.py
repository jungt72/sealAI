"""Unit tests for evaluate_gegencheck (INC-GEGENCHECK-CORE acceptance criteria).

All tests are deterministic, offline, no LLM. The kernel queries the real §4
Verträglichkeitsmatrix seed and returns a structured verdict — never narration.

Owner doctrine E4-1: the kernel may DISQUALIFY, never QUALIFY. The only
non-disqualifying outcome is the *absence* of a documented incompatibility —
there is never an affirmative "passt/geeignet" field.
"""

from __future__ import annotations

from sealai_v2.core.contracts import _MATRIX_VERDICTS
from sealai_v2.core.gegencheck import evaluate_gegencheck
from sealai_v2.knowledge.matrix import load_matrix

# An affirmative-suitability field would violate E4-1. The kernel must NEVER emit one.
_FORBIDDEN_KEYS = frozenset(
    {"passt", "geeignet", "suitable", "qualified", "compatible", "ok"}
)


def _cat():
    return load_matrix()


# ---------------------------------------------------------------------------
# Acceptance tests (one per matrix state, against REAL seed cells)
# ---------------------------------------------------------------------------


def test_unvertraeglich_disqualifies():
    # FKM × Heißdampf -> MX-FKM-DAMPF (unvertraeglich, sole match)
    result = evaluate_gegencheck("FKM", "Heißdampf", tenant="t1", catalog=_cat())
    assert result["disqualified"] is True
    assert result["reason"]  # grounded begründung, non-empty
    assert result["source"]  # grounded cell reference, non-empty


def test_bedingt_does_not_disqualify_but_marks_conditional():
    # NBR × Synthetiköl -> MX-NBR-SYNTHETIKOEL (bedingt, sole match)
    result = evaluate_gegencheck("NBR", "Synthetiköl", tenant="t1", catalog=_cat())
    assert result["disqualified"] is False
    assert result["basis"] == "matrix_conditional"
    # The condition is the most valuable Gegencheck output — it must travel WITH the
    # verdict (inline), not be lost behind a bare citation. Grounded from the reviewed
    # cell (verbatim begründung), never kernel-formulated.
    assert result["condition"]  # the grounded condition text, inline
    assert result["source"]  # plus the cell citation reference
    grounded_texts = {c.begruendung for c in _cat().cells}
    assert result["condition"] in grounded_texts  # verbatim from the reviewed cell


def test_vertraeglich_does_not_qualify():
    # NBR × Mineralöl -> MX-NBR-MINERALOEL (vertraeglich, sole match)
    result = evaluate_gegencheck("NBR", "Mineralöl", tenant="t1", catalog=_cat())
    assert result["disqualified"] is False
    assert result["basis"] == "matrix_compatible"
    # E4-1: compatible is the absence of disqualification — NOT an affirmation.
    assert "source" not in result
    assert "reason" not in result
    assert "condition" not in result


def test_no_matrix_data_does_not_disqualify():
    # FKM × Wasser -> no cell (sole, verified empty against the live matcher)
    result = evaluate_gegencheck("FKM", "Wasser", tenant="t1", catalog=_cat())
    assert result["disqualified"] is False
    assert result["basis"] == "no_matrix_data"


def test_material_absent_from_matrix_is_no_matrix_data():
    # ACM is not in any scope.material -> zero hits -> no data (still not disqualified)
    result = evaluate_gegencheck("ACM", "Mineralöl", tenant="t1", catalog=_cat())
    assert result["disqualified"] is False
    assert result["basis"] == "no_matrix_data"


def test_no_medium_does_not_disqualify():
    result = evaluate_gegencheck("FKM", None, tenant="t1", catalog=_cat())
    assert result["disqualified"] is False
    assert result["basis"] == "no_medium"


def test_blank_medium_treated_as_no_medium():
    result = evaluate_gegencheck("FKM", "   ", tenant="t1", catalog=_cat())
    assert result["disqualified"] is False
    assert result["basis"] == "no_medium"


# ---------------------------------------------------------------------------
# Doctrine guards (E4-1 + structure, not prose)
# ---------------------------------------------------------------------------


def test_no_return_path_carries_an_affirmative_suitability_field():
    cat = _cat()
    cases = [
        ("FKM", "Heißdampf"),  # unvertraeglich
        ("NBR", "Synthetiköl"),  # bedingt
        ("NBR", "Mineralöl"),  # vertraeglich
        ("FKM", "Wasser"),  # no_matrix_data
        ("FKM", None),  # no_medium
    ]
    for mat, med in cases:
        result = evaluate_gegencheck(mat, med, tenant="t1", catalog=cat)
        assert _FORBIDDEN_KEYS.isdisjoint(result.keys()), (mat, med, result)


def test_headline_is_always_binary_disqualified():
    cat = _cat()
    cases = [
        ("FKM", "Heißdampf"),
        ("NBR", "Synthetiköl"),
        ("NBR", "Mineralöl"),
        ("FKM", "Wasser"),
        ("FKM", None),
    ]
    for mat, med in cases:
        result = evaluate_gegencheck(mat, med, tenant="t1", catalog=cat)
        assert isinstance(result["disqualified"], bool), (mat, med, result)


def test_basis_is_an_opaque_marker_not_a_german_sentence():
    # `basis` is a stable state marker — no spaces, drawn from a small closed set.
    cat = _cat()
    allowed_basis = {
        "matrix_compatible",
        "matrix_conditional",
        "no_matrix_data",
        "no_medium",
    }
    for mat, med in [("NBR", "Mineralöl"), ("NBR", "Synthetiköl"), ("FKM", None)]:
        result = evaluate_gegencheck(mat, med, tenant="t1", catalog=cat)
        assert result["basis"] in allowed_basis
        assert " " not in result["basis"]


def test_conditional_condition_is_grounded_not_fabricated():
    # The condition text must be the reviewed cell's own begründung (a real verdict
    # in the seed), never a kernel-formulated sentence.
    cat = _cat()
    result = evaluate_gegencheck("NBR", "Synthetiköl", tenant="t1", catalog=cat)
    grounded_texts = {c.begruendung for c in cat.cells}
    assert result["condition"] in grounded_texts


def test_disqualifying_verdict_is_grounded_not_fabricated():
    # The reason must be the reviewed cell's own text (a real verdict in the seed),
    # never a kernel-formulated sentence.
    cat = _cat()
    result = evaluate_gegencheck("FKM", "Heißdampf", tenant="t1", catalog=cat)
    grounded_texts = {c.begruendung for c in cat.cells}
    assert result["reason"] in grounded_texts
    # the verdict it acted on is a real matrix verdict value
    cell_verdicts = {c.bewertung for c in cat.cells}
    assert cell_verdicts <= set(_MATRIX_VERDICTS)
