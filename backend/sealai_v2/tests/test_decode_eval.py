"""DECODE eval class (Modus G) — offline wellformed-and-wired proof."""

from __future__ import annotations


def test_decode_cases_load_and_wellformed():
    from sealai_v2.eval.cases import load_decode_cases

    cases = load_decode_cases()
    ids = {c.id for c in cases}
    assert ids == {
        "DEC-DECODE-VERGLEICH-01",
        "DEC-AEQUIVALENZ-GRENZE-01",
        "DEC-ORING-DECODE-01",
        "DEC-KEINE-BEZEICHNUNG-01",
    }
    for c in cases:
        assert c.klass == "Decode (DECODE)"
        assert c.must_contain and c.must_avoid and c.must_catch
    # the equivalence case carries the existing confident_wrong gate (§9.2 sharpest edge)
    eq = next(c for c in cases if c.id == "DEC-AEQUIVALENZ-GRENZE-01")
    assert eq.hard_gates == ("confident_wrong",)


def test_decode_fold_wired():
    from sealai_v2.eval import harness

    assert hasattr(harness, "_run_decode")


def test_decode_substrate_present():
    from sealai_v2.core.contracts import PipelineResult
    from sealai_v2.pipeline import stages

    assert hasattr(stages, "decode")
    assert "decode" in PipelineResult.__dataclass_fields__
    v = stages.decode("RWDR 40x62x10 FKM")
    assert v["id_mm"] == 40.0 and "Austausch-Garantie" in v["equivalenz_grenze"]
