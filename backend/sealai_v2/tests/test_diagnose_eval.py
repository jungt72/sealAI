"""DIAGNOSE eval class (Modus D) — offline wellformed-and-wired proof.

The semantic green gate is the live eval-REPLAY over diagnose_v0.json (owner-adjudicated;
the Dim. 5 cards are deepened by the owner's end-stage multi-LLM challenge). This file asserts
only the deterministic, offline-checkable scaffolding.
"""

from __future__ import annotations


def test_diagnose_cases_load_and_wellformed():
    from sealai_v2.eval.cases import load_diagnose_cases

    cases = load_diagnose_cases()
    ids = {c.id for c in cases}
    assert ids == {
        "DIAG-LIPPE-VERHAERTET-01",
        "DIAG-QUELLUNG-MEDIUM-01",
        "DIAG-OZONRISSE-AUSSEN-01",
        "DIAG-KEIN-KLARES-BILD-01",
    }
    for c in cases:
        assert c.klass == "Diagnose (DIAGNOSE)"
        assert c.must_contain and c.must_avoid and c.must_catch
        assert c.hard_gates == ()  # credibility/axes class — NO new hard gate
        assert c.primary_axes


def test_diagnose_fold_wired_into_harness():
    from sealai_v2.eval import harness

    assert hasattr(harness, "_run_diagnose")


def test_diagnose_substrate_present():
    from sealai_v2.core.contracts import PipelineResult
    from sealai_v2.knowledge.versagensmodi import InProcessVersagensmodiStore
    from sealai_v2.pipeline import stages

    assert hasattr(stages, "diagnose")
    assert "diagnose" in PipelineResult.__dataclass_fields__
    # a symptom turn yields a provisional (all-draft seed) structured diagnosis
    v = stages.diagnose(
        InProcessVersagensmodiStore(),
        "die Lippe ist hart und rissig und leckt",
        tenant_id="t1",
    )
    assert v is not None and v["provisional"] is True
