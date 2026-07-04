"""L3 optimal wiring — a reviewed trap finding whose caveat the DRAFT itself already states is
demoted to FLAG (the explanatory/correct answer stands, no destructive hedge); a real trap-walk or
a genuinely wrong claim still blocks/hedges.

2026-07-04: extended from walked_into_trap-only to also cover confident_wrong, after a live incident
reproduced the identical failure mode through that gate — see test_calc_umfangsgeschwindigkeit_*
below for the real-world regression case (CALC-UMFANGSGESCHWINDIGKEIT, "welche material empfiehlst
du mir", Salzwasser)."""

from sealai_v2.core.contracts import VerifierFinding
from sealai_v2.core.l3_verifier import _caveat_addressed, _demote_caveat_addressed_traps
from sealai_v2.knowledge.traps import load_traps

_CAT = load_traps()
_E = _CAT.by_id("TRAP-PTFE-KALTFLUSS")
_CALC = _CAT.by_id("CALC-UMFANGSGESCHWINDIGKEIT")

# explanatory knowledge answer that STATES the cold-flow caveat itself (the PTFE wissensfrage case)
_EXPLAIN = (
    "PTFE ist nicht elastisch wie ein O-Ring-Werkstoff, eher kalt verformbar. Reiner PTFE-O-Ring ist "
    "statisch mechanisch kritisch: deutlicher Kaltfluss/Kriechen, keine elastische Rückstellung; "
    "chemische Beständigkeit ist breit, mechanische Eignung begrenzt."
)
# a real trap-walk: affirms the wrong recommendation, omits the caveat
_WALK = "Für deine Statikdichtung nimm einfach einen reinen PTFE-O-Ring — PTFE hält chemisch alles aus."

# the actual flagged sentence from the 2026-07-04 incident trace (generate3 in run 019f2e7f-...):
# judged confident_wrong even though it correctly cites the kern's own v-value and names the
# consequence — a live reproduction of the same "explanation judged as violation" failure mode.
_CALC_EXPLAIN = (
    "Für deine Randbedingungen (RWDR, Salzwasser, ca. 3-4 bar, ~40 C, d1 = 400 mm, 5000 1/min) ist "
    "die berechnete Umfangsgeschwindigkeit von 104,7 m/s kritisch: sie liegt über der "
    "Belastungsgrenze einer Standard-NBR-Lippe, Standard-NBR ist hier als Lippenwerkstoff nicht "
    "ausreichend, du brauchst eine höher belastbare Lippe oder eine Sonderbauform. Für das Medium "
    "Salzwasser kommen chemisch EPDM, HNBR, wasserbeständiges FKM oder PTFE-basierte Lippen in Frage."
)
# a genuine violation of the SAME trap: judges suitability without ever computing/naming a limit
_CALC_WALK = (
    "Eine Standard-NBR-Lippe passt bei 5000 U/min und 400 mm Wellendurchmesser gut."
)

# the ACTUAL, verbatim flagged text from LangSmith trace 019f2e7f-9dd4-7602-958c-4003fb77f3e8
# (generate3's output — the specific draft the L3 judge flagged confident_wrong on 2026-07-04)
_CALC_EXPLAIN_REAL_TRACE = (
    "Für deinen Fall (RWDR in Salzwasser, ca. 3-4 bar, ~40-60 °C, d = 400 mm, 5000 U/min) sind zwei "
    "Punkte kritisch:\n- Die berechnete Umfangsgeschwindigkeit von 104,7 m/s liegt über der "
    "Belastungsgrenze einer Standard-NBR-Lippe -> Standard-NBR ist hier als Lippenwerkstoff nicht "
    "ausreichend.\n- Medium ist Salzwasser -> klassische ölbeständige Elastomere (NBR, FKM) sind "
    "chemisch nicht ideal, du brauchst gute Wasser-/Salzwasserbeständigkeit."
)


def _f(gate="walked_into_trap", tid="TRAP-PTFE-KALTFLUSS"):
    return VerifierFinding(
        trap_id=tid, gate=gate, review_state="reviewed", evidence="x", kind="trap"
    )


def test_caveat_addressed_distinguishes_explain_from_walk():
    assert _caveat_addressed(_E, _EXPLAIN) is True
    assert _caveat_addressed(_E, _WALK) is False


def test_explanatory_draft_demoted_to_flag():
    out = _demote_caveat_addressed_traps((_f(),), _CAT, _EXPLAIN)
    assert (
        out[0].review_state == "draft"
    )  # -> FLAG, the rich draft stands (no destructive hedge)


def test_real_trap_walk_still_blocks():
    out = _demote_caveat_addressed_traps((_f(),), _CAT, _WALK)
    assert out[0].review_state == "reviewed"  # -> still blocking, hedges


def test_confident_wrong_gate_now_demoted_when_caveat_addressed():
    out = _demote_caveat_addressed_traps((_f(gate="confident_wrong"),), _CAT, _EXPLAIN)
    assert (
        out[0].review_state == "draft"
    )  # 2026-07-04: confident_wrong is now covered too


def test_confident_wrong_gate_still_blocks_a_real_violation():
    out = _demote_caveat_addressed_traps((_f(gate="confident_wrong"),), _CAT, _WALK)
    assert (
        out[0].review_state == "reviewed"
    )  # caveat NOT addressed -> still blocks/hedges


def test_invented_precision_gate_still_untouched():
    # NOT extended to invented_precision: stating correct_general doesn't rule out a separate
    # fabricated number elsewhere in the same draft (see the function's own docstring).
    out = _demote_caveat_addressed_traps(
        (_f(gate="invented_precision"),), _CAT, _EXPLAIN
    )
    assert out[0].review_state == "reviewed"


def test_calc_umfangsgeschwindigkeit_explanation_demoted_2026_07_04_incident():
    """The real, reproduced incident: a draft correctly citing the kern's own over-limit verdict for
    v=104,7 m/s (and going on to give a full, correct Salzwasser material analysis) must not have its
    entire answer replaced by a generic calc-methodology hedge."""
    finding = VerifierFinding(
        trap_id="CALC-UMFANGSGESCHWINDIGKEIT",
        gate="confident_wrong",
        review_state="reviewed",
        evidence="Die berechnete Umfangsgeschwindigkeit von 104,7 m/s liegt über der Belastungsgrenze "
        "einer Standard-NBR-Lippe",
        kind="trap",
    )
    out = _demote_caveat_addressed_traps((finding,), _CAT, _CALC_EXPLAIN)
    assert out[0].review_state == "draft"


def test_calc_umfangsgeschwindigkeit_verbatim_production_trace_demoted():
    """Same assertion, but against the UNMODIFIED, verbatim text captured from the actual production
    LangSmith trace of the incident — not a paraphrase, the real flagged draft itself."""
    finding = VerifierFinding(
        trap_id="CALC-UMFANGSGESCHWINDIGKEIT",
        gate="confident_wrong",
        review_state="reviewed",
        evidence="x",
        kind="trap",
    )
    out = _demote_caveat_addressed_traps((finding,), _CAT, _CALC_EXPLAIN_REAL_TRACE)
    assert out[0].review_state == "draft"


def test_calc_umfangsgeschwindigkeit_real_omission_still_blocks():
    finding = VerifierFinding(
        trap_id="CALC-UMFANGSGESCHWINDIGKEIT",
        gate="confident_wrong",
        review_state="reviewed",
        evidence="x",
        kind="trap",
    )
    out = _demote_caveat_addressed_traps((finding,), _CAT, _CALC_WALK)
    assert out[0].review_state == "reviewed"
