"""ALTERNATIVEN eval class (Modus F) — offline wellformed-and-wired proof."""

from __future__ import annotations


def test_alternativen_cases_load_and_wellformed():
    from sealai_v2.eval.cases import load_alternativen_cases

    cases = load_alternativen_cases()
    ids = {c.id for c in cases}
    assert ids == {
        "ALT-NEUTRAL-EMPTY-01",
        "ALT-NEUTRALITAET-BESTER-01",
        "ALT-KEINE-ERFINDUNG-01",
    }
    for c in cases:
        assert c.klass == "Alternativen (ALTERNATIVEN)"
        assert c.must_contain and c.must_avoid and c.must_catch
        assert c.hard_gates == ()


def test_alternativen_fold_wired():
    from sealai_v2.eval import harness

    assert hasattr(harness, "_run_alternativen")


def test_alternativen_substrate_present():
    from sealai_v2.core.contracts import PipelineResult
    from sealai_v2.knowledge.hersteller_partner import InProcessPartnerRegistry
    from sealai_v2.pipeline import stages

    assert hasattr(stages, "alternativen")
    assert "alternativen" in PipelineResult.__dataclass_fields__
    # empty partner registry → honest no-grounded-data, neutral
    v = stages.alternativen(
        InProcessPartnerRegistry(), "Wer macht FKM-RWDR? Alternativen?", tenant_id="t1"
    )
    assert v is not None and v["grounded_data"] is False
