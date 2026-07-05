"""Coverage-classification accuracy (V2.2 §8(d) — the keystone calibration schranke) END-TO-END over
REAL §4-matrix evidence: a real material×medium → the gegencheck kernel → ``coverage_status``. The gate
is deterministic, so these grounded reference cases pin the classification accuracy (the L3 ≥0.95 floor)
by construction — a regression here means the gate mis-recognised *whether it was grounded*, which is the
precondition the spec calls out (§8: validate the gate before measuring whether an assertive answer was
wrong). The doctrine (§2) goes productive only when this is green (I-CAL-1)."""

import pytest

from sealai_v2.core.coverage import CoverageStatus as CS
from sealai_v2.core.coverage import chemical_axis, classify_coverage
from sealai_v2.core.gegencheck import evaluate_gegencheck
from sealai_v2.knowledge.matrix import load_matrix

_CATALOG = load_matrix()
_TENANT = "coverage-classification-eval"


def _coverage(material: str, medium: str) -> CS:
    verdict = evaluate_gegencheck(material, medium, tenant=_TENANT, catalog=_CATALOG)
    return classify_coverage(chemical=chemical_axis(verdict)).status


# (material, medium, expected coverage status) — a grounded reference set over the real §4 matrix.
_CASES = [
    (
        "FKM",
        "Heißdampf",
        CS.IN_ENVELOPE,
    ),  # unverträglich → grounded NO → assertive disqualification (§6.2)
    ("NBR", "Mineralöl", CS.IN_ENVELOPE),  # verträglich → grounded
    (
        "NBR",
        "Synthetiköl",
        CS.PARTIAL_ENVELOPE,
    ),  # bedingt → matrix_conditional → conditional
    ("FEPM (AFLAS)", "Dampf", CS.PARTIAL_ENVELOPE),  # bedingt
    ("FKM", "Wasser", CS.OUT_OF_ENVELOPE),  # no reviewed cell → ungrounded → OUT
    ("VMQ", "Schmierfett", CS.OUT_OF_ENVELOPE),  # no reviewed cell → ungrounded → OUT
]


@pytest.mark.parametrize("material,medium,expect", _CASES)
def test_coverage_classification_on_real_matrix(material, medium, expect):
    assert _coverage(material, medium) is expect


def test_classification_accuracy_is_at_or_above_floor():
    # the deterministic gate must classify the grounded reference set at 100% (≥ the §8 / L3 0.95 floor).
    correct = sum(1 for m, med, exp in _CASES if _coverage(m, med) is exp)
    accuracy = correct / len(_CASES)
    assert accuracy >= 0.95, (
        f"coverage-classification accuracy {accuracy:.2f} below the 0.95 floor"
    )
