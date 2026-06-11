"""M8-C — the L1-parametric-computation leak detector (deterministic core of the new trap class).

Fires iff the draft asserts a PRECISE value for a kern-owned quantity (umfangsgeschwindigkeit /
pv_wert / verpressung_prozent) that the deterministic kern did NOT compute (or that contradicts the
kern's value). Defense-in-depth alongside the L1 prompt rule and the TRAP-L1-PARAMETRIC-CALC
catalog entry — NOT prompt-only.

The zero-FP suite below is the OWNER BOUNDARY-REVIEW package (decision 4, M6b exfiltration
precedent): the lexicon + exemptions are locked agent-final only after the owner reviews exactly
these boundaries.
"""

from __future__ import annotations

from sealai_v2.core.calc.leak_detector import detect_parametric_leaks
from sealai_v2.core.contracts import ComputedValue


def _cv(
    calc_id="umfangsgeschwindigkeit", name="v_m_s", value=10.472, unit="m/s"
) -> ComputedValue:
    return ComputedValue(
        calc_id=calc_id, name=name, value=value, unit=unit, stage=1, derivation_depth=1
    )


# --- MUST FIRE -----------------------------------------------------------------------------------


def test_canonical_leak_fires():
    """THE briefing failure: kern computed nothing, L1 wrote the value anyway."""
    draft = (
        "Bei einer Welle mit 50 mm und 4000 U/min ergibt sich eine Umfangsgeschwindigkeit "
        "von v ≈ 10,5 m/s, was für NBR grenzwertig ist."
    )
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert (
        leaks
    ), "the canonical 'v ≈ 10,5 m/s' leak MUST fire when the kern computed nothing"
    assert leaks[0].calc_id == "umfangsgeschwindigkeit"


def test_leak_fires_on_betraegt_phrasing():
    draft = "Die Umfangsgeschwindigkeit beträgt 10,47 m/s bei diesen Bedingungen."
    assert detect_parametric_leaks(draft, computed_values=())


def test_leak_fires_on_value_contradicting_kern():
    draft = "Die Umfangsgeschwindigkeit liegt bei 15,8 m/s."
    assert detect_parametric_leaks(draft, computed_values=(_cv(value=10.472),))


def test_pv_leak_fires():
    draft = "Der PV-Wert ergibt 5,2 bar·m/s — das ist zu hoch."
    assert detect_parametric_leaks(draft, computed_values=())


def test_verpressung_leak_fires():
    draft = "Die Verpressung beträgt damit 18 % und liegt im Zielband."
    assert detect_parametric_leaks(draft, computed_values=())


# --- MUST NOT FIRE (the zero-FP boundary — owner review package) -----------------------------------


def test_restating_the_kern_value_is_not_a_leak():
    draft = "Die deterministisch berechnete Umfangsgeschwindigkeit ist v = 10.472 m/s [v = π·d1·n/60000]."
    assert detect_parametric_leaks(draft, computed_values=(_cv(),)) == ()


def test_restating_the_kern_value_rounded_is_not_a_leak():
    """L1 rounding the kern's 10.472 to 10,5 is referencing, not recomputing (≤2 % tolerance)."""
    draft = "Laut Berechnung liegt die Umfangsgeschwindigkeit bei rund 10,5 m/s."
    assert detect_parametric_leaks(draft, computed_values=(_cv(),)) == ()


def test_typical_range_with_caveat_is_not_a_leak():
    """Knowledge statement (range + caveat) — the is_precision_overapplication boundary."""
    draft = (
        "Für RWDR ohne Druckbeaufschlagung sind typisch 8–12 m/s zulässig — Richtwert, "
        "gegen das Datenblatt des konkreten Werkstoffs verifizieren."
    )
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_single_typical_value_with_caveat_and_no_assertion_is_not_a_leak():
    draft = "Als grober Richtwert gelten bis ca. 10 m/s für Standard-NBR-RWDR (typisch, Datenblatt prüfen)."
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_symbolic_formula_without_numbers_is_not_a_leak():
    draft = (
        "Die Umfangsgeschwindigkeit folgt aus v = π·d·n/60000; sobald Wellendurchmesser und "
        "Drehzahl bestätigt sind, berechne ich den Wert deterministisch."
    )
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_unrelated_numbers_and_units_are_not_leaks():
    draft = "Bei 80 °C und einer Welle von 50 mm ist NBR bis etwa 100 °C einsetzbar; Druck 0,5 bar."
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_percent_without_verpressung_context_is_not_a_leak():
    draft = "Etwa 30 % der Ausfälle gehen auf Montagefehler zurück."
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_empty_draft_no_leak():
    assert detect_parametric_leaks("", computed_values=()) == ()


# --- policy: regenerate-once with a deterministic CalcResult note → hedge on re-fire --------------


def _policy_fixtures(scripted):
    import json

    from sealai_v2.core.contracts import Flags, ModelConfig
    from sealai_v2.core.l1_generator import L1Generator
    from sealai_v2.core.l3_verifier import L3Verifier
    from sealai_v2.knowledge.traps import load_traps
    from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
    from sealai_v2.tests._fakes import ScriptedFakeLlmClient

    client = ScriptedFakeLlmClient(scripted)
    cat = load_traps()
    gen = L1Generator(client, PromptAssembler(), ModelConfig("fake-l1"))
    verifier = L3Verifier(
        client, VerifierPromptAssembler(), ModelConfig("fake-l3"), cat
    )
    clean = json.dumps({"findings": [], "verdict": "clean"})
    return client, cat, gen, verifier, Flags(), clean


_NC = None  # set lazily to avoid import cycles at module import


def _not_computed():
    from sealai_v2.core.contracts import NotComputed

    return (
        NotComputed(
            "umfangsgeschwindigkeit", "nicht berechenbar: Eingaben fehlen (d1_mm, rpm)"
        ),
    )


def test_run_verify_leak_regenerates_once_with_calcresult_note():
    """Leak on the draft → ONE regeneration driven by a deterministic note built from the
    CalcResult (fail-closed case: names the missing inputs, forbids a number) → CORRECTED."""
    import asyncio
    import json

    from sealai_v2.core.contracts import Answer, VerifierAction
    from sealai_v2.core.l3_verifier import run_verify

    clean = json.dumps({"findings": [], "verdict": "clean"})
    client, cat, gen, verifier, flags, _ = _policy_fixtures(
        [
            clean,  # L3 LLM verify on the draft (the DETECTOR finds the leak, not the LLM)
            "Ohne bestätigte Eingaben nenne ich keinen Wert; Formel symbolisch: v = π·d·n/60000.",
            clean,  # L3 LLM verify on the regeneration
        ]
    )
    draft = Answer(
        text="Die Umfangsgeschwindigkeit ergibt v ≈ 10,5 m/s.", model="fake-l1"
    )
    final, verdict = asyncio.run(
        run_verify(
            verifier,
            gen,
            cat,
            "q",
            draft,
            flags=flags,
            computed_values=(),
            not_computed=_not_computed(),
        )
    )
    assert verdict.action == VerifierAction.CORRECTED
    assert detect_parametric_leaks(final.text, computed_values=()) == ()
    assert any(f.kind == "calc_leak" for f in verdict.findings)
    regen_system = client.calls[1]["system"]  # the regen generate call carries the note
    assert "d1_mm" in regen_system and "rpm" in regen_system  # missing inputs NAMED
    assert (
        "keinen Zahlenwert" in regen_system.lower()
        or "keinen zahlenwert" in regen_system.lower()
    )


def test_run_verify_leak_persisting_after_regen_hedges_without_number():
    import asyncio

    from sealai_v2.core.contracts import Answer, VerifierAction
    from sealai_v2.core.l3_verifier import run_verify

    import json

    clean = json.dumps({"findings": [], "verdict": "clean"})
    client, cat, gen, verifier, flags, _ = _policy_fixtures(
        [clean, "Trotzdem: die Umfangsgeschwindigkeit beträgt 10,5 m/s.", clean]
    )
    draft = Answer(
        text="Die Umfangsgeschwindigkeit ergibt v ≈ 10,5 m/s.", model="fake-l1"
    )
    final, verdict = asyncio.run(
        run_verify(
            verifier,
            gen,
            cat,
            "q",
            draft,
            flags=flags,
            computed_values=(),
            not_computed=_not_computed(),
        )
    )
    assert verdict.action == VerifierAction.BLOCKED_HEDGE
    assert (
        "10,5" not in final.text and "10.5" not in final.text
    )  # never echo the leaked number
    assert detect_parametric_leaks(final.text, computed_values=()) == ()
    assert (
        "Umfangsgeschwindigkeit" in final.text
    )  # names the quantity, honestly fail-closed
    assert "d1_mm" in final.text or "Eingaben" in final.text


def test_run_verify_clean_draft_stays_pass_single_llm_call():
    import asyncio

    from sealai_v2.core.contracts import Answer, VerifierAction
    from sealai_v2.core.l3_verifier import run_verify

    import json

    clean = json.dumps({"findings": [], "verdict": "clean"})
    client, cat, gen, verifier, flags, _ = _policy_fixtures([clean])
    draft = Answer(text="NBR passt grundsätzlich; Datenblatt prüfen.", model="fake-l1")
    final, verdict = asyncio.run(
        run_verify(
            verifier,
            gen,
            cat,
            "q",
            draft,
            flags=flags,
            computed_values=(),
            not_computed=(),
        )
    )
    assert verdict.action == VerifierAction.PASS and final.text == draft.text
    assert (
        len(client.calls) == 1
    )  # no extra calls on the clean path (REPLAY no-regression)
