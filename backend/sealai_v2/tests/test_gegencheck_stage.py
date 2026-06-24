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


def test_realistic_multi_tag_incompatible_fires():
    # REGRESSION (the extract_medium fail-closed bug): one steam medium named with three
    # vocab tags must still disqualify, not abstain to None.
    case = Case.from_case_state(
        (), question="Wir verbauen FKM in Heißdampf-Sterilisation (SIP) bei 140 °C. Passt das?"
    )
    v = stages.gegencheck(_matrix(), case, tenant_id="t1")
    assert v is not None
    assert v["disqualified"] is True


def test_realistic_multi_tag_conditional_fires():
    case = Case.from_case_state(
        (), question="Unsere NBR-WDR laufen in Synthetiköl mit Ester-Additiven. Ok?"
    )
    v = stages.gegencheck(_matrix(), case, tenant_id="t1")
    assert v is not None
    assert v["basis"] == "matrix_conditional"
    assert v["condition"]


def test_co_mentioned_disqualifier_wins_over_compatible():
    # FKM × Mineralöl is compatible (MX-FKM-MINERALOEL) but FKM × Aceton/Keton is NOT
    # (MX-FKM-KETON). Co-mentioned → the documented disqualifier wins, never silently
    # dropped (the safety reason for folding over all matched media).
    case = Case.from_case_state(
        (), question="FKM in Mineralöl, teils auch Aceton im Prozess — passt das?"
    )
    v = stages.gegencheck(_matrix(), case, tenant_id="t1")
    assert v is not None
    assert v["disqualified"] is True


def test_no_medium_means_not_a_gegencheck_situation():
    case = Case.from_case_state((), question="Was kann FKM?")
    assert stages.gegencheck(_matrix(), case, tenant_id="t1") is None


def test_no_material_means_not_a_gegencheck_situation():
    case = Case.from_case_state((), question="Ist Heißdampf kritisch?")
    assert stages.gegencheck(_matrix(), case, tenant_id="t1") is None


def test_matrix_off_yields_none():
    case = Case.from_case_state((), question="FKM in Heißdampf passt das?")
    assert stages.gegencheck(None, case, tenant_id="t1") is None
