"""The deterministic Gegencheck pipeline stage (Modus E).

Fires ONLY on a real "passt das?" situation — an existing seal material AND a
medium in the case. Otherwise None (byte-identical no-Gegencheck turn). The verdict
is the kernel's binary disqualified-or-not dict; never affirms suitability (E4-1).

Deterministic, offline, no LLM.
"""

from __future__ import annotations

from sealai_v2.core.contracts import Case
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.pipeline import stages


def _matrix():
    return InProcessCompatibilityMatrix()


def test_incompatible_disqualifies():
    case = Case.from_case_state(
        (), question="Wir verwenden FKM in Heißdampf, passt das?"
    )
    v = stages.gegencheck(_matrix(), case, tenant_id="t1")
    assert v is not None
    assert v["disqualified"] is True
    assert v["reason"] and v["source"]


def test_conditional_marks_condition_inline():
    case = Case.from_case_state((), question="Wir nutzen NBR mit Synthetiköl, ok?")
    v = stages.gegencheck(_matrix(), case, tenant_id="t1")
    assert v is not None
    assert v["disqualified"] is False
    assert v["basis"] == "matrix_conditional"
    assert v["condition"]  # grounded condition travels inline


def test_no_medium_means_not_a_gegencheck_situation():
    case = Case.from_case_state((), question="Was kann FKM?")
    assert stages.gegencheck(_matrix(), case, tenant_id="t1") is None


def test_no_material_means_not_a_gegencheck_situation():
    case = Case.from_case_state((), question="Ist Heißdampf kritisch?")
    assert stages.gegencheck(_matrix(), case, tenant_id="t1") is None


def test_matrix_off_yields_none():
    case = Case.from_case_state((), question="FKM in Heißdampf passt das?")
    assert stages.gegencheck(None, case, tenant_id="t1") is None
