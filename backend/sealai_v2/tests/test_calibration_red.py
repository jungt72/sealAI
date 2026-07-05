"""C4-RED (V2.1 Inc 2, Calibration) — red-before-green, offline + keyless.

Two halves:

  GREEN now (proves the C4 eval cases are NOT a test-bug): the 4 calibration cases load + validate,
  and the harness fold is importable + wired. These pass today.

  RED now (proves any failure reason is 'die Kalibrierung existiert noch nicht', NOT a test bug):
  the three substrate pieces C1/C2/C3 will build are absent today —
    C1: the kernel emits NO v-over-limit fact for v>14 (calc_seed limit + evaluator branch missing),
    C2: l3_verifier has NO deterministic v-over-limit detector,
    C3: the L1 system prompt has NO calibration block (confident-where-grounded).
  These three flip to GREEN as C1/C2/C3 land (and the live eval-REPLAY over calibration_v0.json is
  the semantic GREEN gate). Keyless: uses the deterministic kernel + static prompt assembly only,
  never the LLM.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# GREEN now — the C4 cases + harness fold are well-formed and wired (not a test-bug).
# ---------------------------------------------------------------------------


def test_calibration_cases_load_and_are_wellformed() -> None:
    from sealai_v2.eval.cases import load_calibration_cases

    cases = load_calibration_cases()
    ids = {c.id for c in cases}
    assert ids == {
        "CALIB-VLIMIT-GENERIC-01",
        "CALIB-MATRIX-GROUNDED-01",
        "CALIB-HEDGE-EDGE-01",
        "CALIB-RESTRAINT-01",
        "CALIB-PTFE-DYN-01",
    }
    for c in cases:
        assert c.klass == "Kalibrierung (CALIBRATION)"
        assert c.must_contain and c.must_avoid  # both sides of the boundary specified
        assert c.hard_gates == ()  # credibility/axes class — NO new hard gate (brief)


def test_calibration_fold_is_wired_into_harness() -> None:
    from sealai_v2.eval import harness

    assert hasattr(harness, "_run_calibration"), "C4 harness fold not wired"


# ---------------------------------------------------------------------------
# RED now — the calibration substrate is absent (the right reason). Flips green at C1/C2/C3.
# ---------------------------------------------------------------------------


def test_c1_kernel_emits_v_over_limit_fact() -> None:
    """C1: v=π·40·8000/60000 ≈ 16.76 m/s > 14 → the kernel must surface the grounded over-limit FACT
    (no material name). RED until calc_seed carries the limit + the evaluator branch emits it."""
    from sealai_v2.core.calc.evaluator import CascadeCalcEngine

    res = CascadeCalcEngine().evaluate(
        params={"d1_mm": 40, "rpm": 8000, "seal_type": "rwdr"}
    )
    v = next(c for c in res.computed if c.calc_id == "umfangsgeschwindigkeit")
    assert v.value > 14  # sanity: this case is genuinely over the limit
    blob = " ".join(v.warnings).lower()
    assert "grenze" in blob or "unzureichend" in blob, (
        "C1 not built: kernel emits no v-over-limit fact "
        "(calc_seed limit field + evaluator one-sided branch missing)"
    )


def test_c2_l3_has_deterministic_v_over_limit_detector() -> None:
    """C2: a deterministic v-over-limit verifier rule (DD-2a block-trigger), sibling to
    detect_parametric_leaks. RED until built."""
    import sealai_v2.core.l3_verifier as l3

    assert hasattr(l3, "detect_velocity_over_limit"), (
        "C2 not built: deterministic v-over-limit verifier rule missing in l3_verifier"
    )


def _velocity_cv(d1_mm: float, rpm: float):
    """Real ComputedValue(s) for umfangsgeschwindigkeit from the deterministic kernel (keyless)."""
    from sealai_v2.core.calc.evaluator import CascadeCalcEngine

    res = CascadeCalcEngine().evaluate(
        params={"d1_mm": d1_mm, "rpm": rpm, "seal_type": "rwdr"}
    )
    return tuple(c for c in res.computed if c.calc_id == "umfangsgeschwindigkeit")


def test_c2_over_limit_nonprescriptive_yields_finding() -> None:
    """DD-2a: over-limit (C1 warning present) + a draft that ignores the consequence → a finding."""
    from sealai_v2.core.l3_verifier import detect_velocity_over_limit

    cv = _velocity_cv(40, 8000)  # v≈16.76 > 14
    assert detect_velocity_over_limit(
        "Eine Standard-NBR-Lippe passt hier gut.", computed_values=cv
    ), "over-limit + non-prescriptive draft must yield a finding"


def test_c2_over_limit_prescriptive_passes() -> None:
    """Over-limit but the draft already names the consequence (prescriptive) → PASS (no finding)."""
    from sealai_v2.core.l3_verifier import detect_velocity_over_limit

    cv = _velocity_cv(40, 8000)
    draft = (
        "Die berechnete Umfangsgeschwindigkeit liegt über der Belastungsgrenze einer "
        "Standard-NBR-Lippe; NBR ist hier unzureichend, eine höher belastbare Lippe ist nötig."
    )
    assert not detect_velocity_over_limit(draft, computed_values=cv)


def test_c2_over_limit_natural_paraphrase_passes() -> None:
    """2026-07-04 incident: a draft that names the consequence using a NATURAL paraphrase ("liegt
    deutlich oberhalb dessen, was ... abkönnen") rather than the exact hardcoded markers must also
    PASS — the earlier marker list missed this real, correct phrasing and triggered an unneeded
    regeneration (plus its LLM round-trip latency) even though the draft already addressed the limit."""
    from sealai_v2.core.l3_verifier import detect_velocity_over_limit

    cv = _velocity_cv(40, 8000)
    draft = (
        "Die berechnete Umfangsgeschwindigkeit liegt deutlich oberhalb dessen, was ein "
        "Standard-RWDR mit einer typischen Standard-Lippe abkönnen."
    )
    assert not detect_velocity_over_limit(draft, computed_values=cv)


def test_c2_under_limit_passes() -> None:
    """Under the limit (no C1 over-limit warning) → PASS regardless of the draft."""
    from sealai_v2.core.l3_verifier import detect_velocity_over_limit

    cv = _velocity_cv(40, 4000)  # v≈8.38 < 14
    assert not detect_velocity_over_limit(
        "Eine NBR-Lippe passt hier gut.", computed_values=cv
    )


def test_e2_calc_velocity_trap_preserved_when_v_computed() -> None:
    """Eingriff 2 (catch-preservation): when the kern computed a velocity verdict (the (i)-like case),
    the CALC-UMFANGSGESCHWINDIGKEIT trap is NOT scoped away — the catch holds. RED until the scope
    helper exists; GREEN after (the catch is preserved)."""
    from sealai_v2.core.contracts import VerifierFinding
    from sealai_v2.core.l3_verifier import scope_calc_velocity_trap

    f = VerifierFinding(
        trap_id="CALC-UMFANGSGESCHWINDIGKEIT",
        gate="confident_wrong",
        review_state="reviewed",
        evidence="x",
        kind="trap",
    )
    cv = _velocity_cv(40, 8000)  # kern computed umfangsgeschwindigkeit
    assert scope_calc_velocity_trap((f,), cv) == (f,)


def test_e2_calc_velocity_trap_suppressed_when_no_v() -> None:
    """Eingriff 2 (over-fire fix): no kern velocity verdict (materials-only turn) → the
    CALC-UMFANGSGESCHWINDIGKEIT trap is scoped away (no over-fire on a qualitative 'Hochdrehzahl'
    draft). A NON-velocity trap is never scoped. RED before the helper exists, GREEN after."""
    from sealai_v2.core.contracts import VerifierFinding
    from sealai_v2.core.l3_verifier import scope_calc_velocity_trap

    f = VerifierFinding(
        trap_id="CALC-UMFANGSGESCHWINDIGKEIT",
        gate="confident_wrong",
        review_state="reviewed",
        evidence="x",
        kind="trap",
    )
    assert scope_calc_velocity_trap((f,), ()) == ()  # no v verdict → suppressed
    g = VerifierFinding(
        trap_id="TRAP-FKM-DAMPF",
        gate="confident_wrong",
        review_state="reviewed",
        evidence="y",
        kind="trap",
    )
    assert scope_calc_velocity_trap((g,), ()) == (g,)  # non-velocity trap untouched


def test_c3_l1_prompt_has_calibration_block() -> None:
    """C3: the L1 system prompt must carry the calibration block (confident-where-grounded). RED until
    the block is added to system_l1.jinja. Static block → renders regardless of flags."""
    from sealai_v2.core.contracts import Flags
    from sealai_v2.prompts.assembler import PromptAssembler

    sys = PromptAssembler().system_prompt(
        flags=Flags(compliance_hint=False, safety_critical=False)
    )
    low = sys.lower()
    assert (
        "so assertiv wie" in low
        or "selbstbewusst, wo geerdet" in low
        or "# kalibrierung" in low
    ), "C3 not built: L1 calibration block (confident-where-grounded) absent"


def test_c_ptfe_cold_flow_caution_scoped_to_static() -> None:
    """(c): the PTFE cold-flow trap (system_l1.jinja 'Bekannte Fallen') must stay SCOPED to pure static
    PTFE (still fires there — not weakened) but must NOT over-apply to a dynamic RWDR PTFE lip (a valid,
    fachkarte-grounded solution). RED until :59 is scoped; the scoping is a MODIFICATION, not a block."""
    from sealai_v2.core.contracts import Flags
    from sealai_v2.prompts.assembler import PromptAssembler

    sys = PromptAssembler().system_prompt(flags=Flags(False, False)).lower()
    assert "reine statik" in sys, (
        "the static cold-flow caution must remain (not weakened)"
    )
    assert "im dynamischen rwdr-kontext" in sys, (
        "(c) not built: the cold-flow caution is not scoped — a dynamic RWDR PTFE lip is not marked valid"
    )


def test_c3_restraint_and_selfcheck_byte_unchanged() -> None:
    """C3 DIFF-ASSERTION: the kern-fix-01 restraint (incl. the 'die Eignung, die sie braucht'
    exception) + Selfcheck #6 must stay BYTE-IDENTICAL — C3 inserts the calibration block far above
    them and must not touch them. GREEN before AND after C3 (a regression guard, not red-before-green)."""
    from pathlib import Path

    import sealai_v2

    jinja = (
        Path(sealai_v2.__file__).resolve().parent / "prompts" / "system_l1.jinja"
    ).read_text(encoding="utf-8")
    for fragment in (
        "Hat der Nutzer in diesem Turn nicht nach der Größe gefragt",
        "ziehst du sie nicht von dir aus herein",
        "fehlende Pflicht-Berechnung stillschweigend übergangen",
    ):
        assert fragment in jinja, (
            f"restraint/selfcheck guard altered: {fragment!r} missing"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
