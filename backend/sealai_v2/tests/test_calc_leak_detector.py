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
    assert leaks, (
        "the canonical 'v ≈ 10,5 m/s' leak MUST fire when the kern computed nothing"
    )
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


def test_point_value_with_caveat_alone_still_fires():
    """Owner hardening (boundary review 2026-06-11): a caveat token does NOT exempt a single
    asserted point-value — the exemption requires an actual RANGE structure AND the caveat."""
    draft = "Die Umfangsgeschwindigkeit liegt hier bei v ≈ 10,5 m/s (typisch)."
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].calc_id == "umfangsgeschwindigkeit"


def test_point_value_smuggled_beside_a_range_still_fires():
    """Owner hardening, span-scoped: only the RANGE'S OWN values are exempt — an asserted
    point-value sitting in the same sentence as a legitimate range+caveat is still a leak."""
    draft = (
        "Typisch sind für RWDR 8–12 m/s (Richtwert, Datenblatt verifizieren); "
        "die Umfangsgeschwindigkeit ergibt hier v ≈ 10,47 m/s."
    )
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].calc_id == "umfangsgeschwindigkeit"
    assert leaks[0].value_text == "10,47"


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


# --- M8-C hardening: live staging repro 2026-06-11 (branch (b)) — symbol-form / window-2 ----------
#
# The live leak: turn 2 stated the inputs ("40mm und 8000"), the kern was fail-closed by
# construction (binding reads only prior-turn facts), L1 self-computed v = 16,76 m/s with a false
# "deterministisch berechnet" label — and the detector missed it because the asserting line carries
# only the SYMBOL form while "Umfangsgeschwindigkeit" sits in the lead sentence, several
# sentences/lines back. Owner decision FIX-FIRST (flip HELD): symbol+unit self-trigger (negative-
# context guard narrowed to the ASSERTING sentence — FN > FP) + window-2 own-token gate.

_TURN2_VERBATIM = """Bei deinen Werten ergibt sich bereits eine berechnete Umfangsgeschwindigkeit:
- d₁ = 40 mm
- n = 8 000 1/min

Formel:
v = π · d₁ · n / 60000
→ v = 16,76 m/s (deterministisch berechnet, vorläufiger Orientierungswert).

Damit liegst du deutlich über dem Bereich klassischer NBR-RWDR in problematischem Medium wie Salzsäure. Für die weitere Auslegung heißt das:
- NBR ist hier sowohl chemisch (HCl) als auch tribologisch (v ≈ 16,8 m/s, keine Schmierung) raus.
- Wenn es bei berührender Wellenabdichtung bleibt, reden wir über PTFE-Hochgeschwindigkeitslippen oder eher gleich über eine Gleitringdichtung / medienfreie Welle."""


def test_live_turn2_verbatim_fires_with_empty_kern():
    """THE live repro (owner-captured staging answer, 2026-06-11, verbatim): kern fail-closed,
    both symbol-form assertions must fire — specifically the '→ v = 16,76 m/s' lead-layout one."""
    leaks = detect_parametric_leaks(_TURN2_VERBATIM, computed_values=())
    assert leaks, "the live turn-2 answer MUST fire against an empty kern"
    assert all(leak.calc_id == "umfangsgeschwindigkeit" for leak in leaks)
    values = [leak.value_text for leak in leaks]
    assert "16,76" in values, (
        "the lead-layout '→ v = 16,76 m/s' assertion must be caught"
    )
    lead = next(leak for leak in leaks if leak.value_text == "16,76")
    assert (
        "deterministisch berechnet" in lead.excerpt
    )  # the false-provenance line itself
    assert (
        len(leaks) == 2 and "16,8" in values
    )  # the NBR-bullet 'v ≈ 16,8 m/s' fires too


def test_live_turn2_verbatim_clean_with_real_kern():
    """Turns 3+ shape: the same answer with the kern's 16.7552 present is referencing, not
    recomputing — '16,76' (≈0,03 %) and '16,8' (≈0,27 %) both inside the ≤2 % band."""
    kern = (_cv(value=16.7552),)
    assert detect_parametric_leaks(_TURN2_VERBATIM, computed_values=kern) == ()


def test_symbol_form_with_token_one_sentence_back_fires():
    draft = (
        "Die Umfangsgeschwindigkeit lässt sich aus den genannten Werten direkt bestimmen. "
        "Damit ergibt sich v = 16,76 m/s."
    )
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].value_text == "16,76"


def test_symbol_form_with_token_far_back_fires():
    """Lead-sentence layout: the token sits 3+ sentences back — only the symbol+unit
    self-trigger can carry this (window-2 alone misses it)."""
    draft = (
        "Die Umfangsgeschwindigkeit ist hier die zentrale Auslegungsgröße. "
        "Salzsäure greift NBR chemisch an. "
        "Eine Schmierung durch das Medium ist nicht gegeben. "
        "Damit ergibt sich v = 16,76 m/s."
    )
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].calc_id == "umfangsgeschwindigkeit"


def test_no_symbol_window2_anaphora_fires():
    """No symbol form at all — 'Sie beträgt …' with the token one sentence back needs the
    window-2 own-token gate."""
    draft = (
        "Die Umfangsgeschwindigkeit hängt von Wellendurchmesser und Drehzahl ab. "
        "Sie beträgt 16,76 m/s."
    )
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].value_text == "16,76"


def test_foreign_velocity_in_preceding_sentence_does_not_shadow():
    """FOLD 1 (owner): the foreign-word suppression consults ONLY the asserting sentence —
    a foreign velocity word one sentence back must not shadow a real symbol-form leak."""
    draft = (
        "Die Strömungsgeschwindigkeit des Mediums ist hier nicht entscheidend. "
        "Damit ergibt sich v = 16,76 m/s."
    )
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].value_text == "16,76"


def test_pv_symbol_form_without_word_token_fires():
    draft = "Damit ergibt sich pv = 8,4 bar·m/s für diese Auslegung."
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].calc_id == "pv_wert"


# guards for the hardening (must hold before AND after) ---------------------------------------------


def test_foreign_velocity_in_asserting_sentence_suppresses_self_trigger():
    """Negative-context guard: the asserting sentence itself names a DIFFERENT velocity —
    the bare symbol form is not claimed for the kern quantity (documented residual (a))."""
    draft = "Die Strömungsgeschwindigkeit im Spalt liegt bei v = 0,5 m/s."
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_symbol_without_unit_does_not_self_trigger():
    draft = "Aus den genannten Werten folgt v = 16,76 ohne weitere Angaben."
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_token_two_sentences_back_without_symbol_does_not_fire():
    """Documented residual: window-2 reaches exactly one sentence back; without a symbol
    form a token further back does not gate (deliberate boundary, not an accident)."""
    draft = (
        "Die Umfangsgeschwindigkeit ist wichtig. "
        "Salzsäure ist aggressiv. "
        "Sie beträgt 16,76 m/s."
    )
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_window2_does_not_cross_newline_into_list_items():
    """FP shape found by the zero-FP sweep (m8-calc CALC-02 draft): a 'Verpressung' list
    header must not import its token into the NEXT list line — 'Nutfüllgrad … 75–90 %' is
    a different quantity and knowledge, not a computation. The window is sentence flow
    WITHIN a line; it never crosses a newline."""
    draft = (
        "- **Verpressung**: hängt von Einbaulage und Härte ab\n"
        "- **Nutfüllgrad**: in der Regel maximal **~75–90 %** gefüllt, damit noch Reserve bleibt"
    )
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_window2_does_not_cross_newline_for_knowledge_ranges():
    """Second sweep FP shape (m3-grounding/m6a CALC-02): hardness-dependent knowledge
    ranges in list lines under a 'Verpressung' header stay clean."""
    draft = (
        "Radiale Verpressung (statisch) = Richtwerte nach Härte:\n"
        "- Weiche Materialien (≈ 60–65 Shore A): eher **20–25 %**\n"
        "- Härtere Materialien: eher **15–20 %**"
    )
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_citation_range_split_by_abbreviation_is_not_a_leak():
    """Third sweep FP shape (m6a-b-edge CALC-02, verbatim structure): the abbreviation
    'typ.' splits the citation sentence, orphaning the range from token AND caveat — a
    window-granted fragment takes the caveat from its granting sentence, and 'typ.' is
    the abbreviated caveat. A Fachkarte citation line must never fire."""
    draft = (
        "→ Quelle: Fachkarte FK-ORING-VERPRESSUNG "
        "(statische radiale Verpressung typ. ~15–25 %)"
    )
    assert detect_parametric_leaks(draft, computed_values=()) == ()


def test_window_granted_point_value_with_window_caveat_still_fires():
    """Span-scoping stays locked THROUGH the caveat-inheritance path: token AND caveat sit in
    the granting sentence, the window-granted fragment asserts a POINT value — the inherited
    caveat blesses only RANGE structures, so the point value fires (safety lock, narrowing 2)."""
    draft = "Die Verpressung als Richtwert beachten. Sie ergibt hier 18 %."
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].calc_id == "verpressung_prozent"
    assert leaks[0].value_text == "18"


def test_typ_abbreviation_does_not_exempt_point_values():
    """Safety lock for narrowing 3: 'typ.' in the caveat lexicon enables only the RANGE
    exemption — an asserted POINT value next to 'typ.' still fires against an empty kern."""
    draft = "Die Umfangsgeschwindigkeit beträgt 16,76 m/s (typ.)"
    leaks = detect_parametric_leaks(draft, computed_values=())
    assert leaks and leaks[0].calc_id == "umfangsgeschwindigkeit"
    assert leaks[0].value_text == "16,76"


def test_token_on_header_line_with_no_symbol_value_next_line_is_a_documented_miss():
    """ACCEPTED RESIDUAL (conscious decision, FIX-FIRST sweep 2026-06-11): a kern-quantity
    token on a header/label LINE with a no-symbol value on the NEXT line is missed by both
    gates — window-2 is line-bounded (cross-line grants produced the Nutfüllgrad/Shore-A
    knowledge-range FPs) and there is no symbol form to self-trigger. Every observed true
    leak is symbol-form or same-line; the LLM-critic trap entry covers paraphrase shapes.
    This test PINS the boundary so a future change of it is deliberate, not accidental."""
    draft = "**Umfangsgeschwindigkeit:**\nSie beträgt 16,76 m/s."
    assert detect_parametric_leaks(draft, computed_values=()) == ()
    # the same header layout WITH a symbol-form value line IS caught (self-trigger):
    assert detect_parametric_leaks(
        "**Umfangsgeschwindigkeit:**\nv = 16,76 m/s.", computed_values=()
    )


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


def test_run_verify_trap_hedge_is_parametric_clean_even_if_correct_has_number():
    """Backstop (kern-fix-01): the user-facing trap-hedge (build_hedge) echoes a reviewed entry's
    `correct` VERBATIM. If that field ever carries a plugged speed number, the hedge would leak it
    (the canonical CALC-MEM-01 Turn-0 failure). run_verify must re-scan the emitted hedge and fall
    back to a number-free hedge — catalog-content-independent, so it holds even for a future entry
    that re-introduces a number. Uses a SYNTHETIC numbered reviewed trap (not the production
    catalog) so the guarantee is independent of Fix A's wording."""
    import asyncio
    import json

    from sealai_v2.core.contracts import Answer, Flags, ModelConfig, VerifierAction
    from sealai_v2.core.l1_generator import L1Generator
    from sealai_v2.core.l3_verifier import L3Verifier, run_verify
    from sealai_v2.knowledge.traps import TrapCatalog, TrapEntry
    from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
    from sealai_v2.tests._fakes import ScriptedFakeLlmClient

    numbered = TrapEntry(
        id="RNUM",
        trigger="synthetic numbered reviewed trap",
        wrong=("falsch",),
        correct="Die Umfangsgeschwindigkeit liegt bei ~14 m/s — grenzwertig; FKM gibt Reserve.",
        gates=("confident_wrong",),
        provenance=("eval:synthetic",),
        review_state="reviewed",
    )
    cat = TrapCatalog(entries=(numbered,))
    violation = json.dumps(
        {
            "findings": [
                {
                    "trap_id": "RNUM",
                    "gate": "confident_wrong",
                    "violated": True,
                    "evidence": "x",
                }
            ],
            "verdict": "violation",
        }
    )
    # draft + regen both carry NO number → the only parametric number is the one build_hedge echoes
    client = ScriptedFakeLlmClient(
        [
            violation,  # L3 verify on the draft → flags reviewed trap RNUM
            "FKM ist hier die sichere Wahl; bitte Datenblatt prüfen.",  # regen (no number)
            violation,  # L3 verify on the regen → persists → fall to the trap-hedge
        ]
    )
    gen = L1Generator(client, PromptAssembler(), ModelConfig("fake-l1"))
    verifier = L3Verifier(client, VerifierPromptAssembler(), ModelConfig("fake-l3"), cat)
    draft = Answer(
        text="Standard-NBR ist für diese Anwendung optimal.", model="fake-l1"
    )
    final, verdict = asyncio.run(
        run_verify(verifier, gen, cat, "Welche Werkstoffe?", draft, flags=Flags())
    )
    assert verdict.action == VerifierAction.BLOCKED_HEDGE
    assert detect_parametric_leaks(final.text, computed_values=()) == ()
    assert "14 m/s" not in final.text  # never echo the catalog's plugged number
