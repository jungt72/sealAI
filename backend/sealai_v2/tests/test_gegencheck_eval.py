"""GEGENCHECK eval class (Modus E, V2.1) — offline + keyless wellformed-and-wired proof.

Proves the gegencheck eval cases are NOT a test-bug and the substrate they exercise
exists today. The SEMANTIC green gate is the live eval-REPLAY over gegencheck_v0.json
(owner-adjudicated, axis 1 / any gate human-final) — that cannot run here (API key is
.env-denied, the human is the factual-correctness oracle). This file asserts only the
deterministic, offline-checkable scaffolding.
"""

from __future__ import annotations


def test_gegencheck_cases_load_and_are_wellformed() -> None:
    from sealai_v2.eval.cases import load_gegencheck_cases

    cases = load_gegencheck_cases()
    ids = {c.id for c in cases}
    assert ids == {
        "GC-UNVERTRAEGLICH-FKM-DAMPF-01",
        "GC-BEDINGT-NBR-SYNTHETIKOEL-01",
        "GC-VERTRAEGLICH-NBR-MINERALOEL-01",
        "GC-KEINE-DATEN-FKM-WASSER-01",
    }
    for c in cases:
        assert c.klass == "Gegencheck (GEGENCHECK)"
        assert c.must_contain and c.must_avoid  # both sides of the boundary specified
        assert c.must_catch  # the one disqualifying/condition insight is named
        assert c.hard_gates == ()  # credibility/axes class — NO new hard gate
        assert c.primary_axes  # axis-anchored


def test_one_case_per_matrix_state() -> None:
    # The four cases cover exactly the four Gegencheck outcomes (the doctrine spine).
    from sealai_v2.eval.cases import load_gegencheck_cases

    tags = {t for c in load_gegencheck_cases() for t in c.tags}
    for state in ("unvertraeglich", "bedingt", "vertraeglich", "keine-daten"):
        assert state in tags, f"missing Gegencheck state coverage: {state}"


def test_gegencheck_fold_is_wired_into_harness() -> None:
    from sealai_v2.eval import harness

    assert hasattr(harness, "_run_gegencheck"), "Gegencheck harness fold not wired"


def test_verdict_substrate_is_present() -> None:
    # The deterministic substrate the eval narration rides on exists today.
    from sealai_v2.core.contracts import Case, PipelineResult
    from sealai_v2.core.gegencheck import evaluate_gegencheck  # noqa: F401
    from sealai_v2.core.medium_extract import extract_medium
    from sealai_v2.pipeline import stages

    assert hasattr(stages, "gegencheck"), "gegencheck stage missing"
    assert "gegencheck" in PipelineResult.__dataclass_fields__, "result field missing"
    # the Case fills both slots the stage needs, from a real Gegencheck question
    case = Case.from_case_state((), question="Wir verwenden FKM in Heißdampf, passt das?")
    assert case.seal_spec == {"material": "FKM"}
    assert case.medium == {"name": "Heißdampf", "matched": ["Heißdampf"]}
    assert extract_medium("in Heißdampf") == "Heißdampf"
