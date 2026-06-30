"""L3 optimal wiring — a walked_into_trap whose caveat the DRAFT itself states is demoted to FLAG (the
explanatory answer stands, no destructive hedge); a real trap-walk still blocks/hedges."""

from sealai_v2.core.contracts import VerifierFinding
from sealai_v2.core.l3_verifier import _caveat_addressed, _demote_caveat_addressed_traps
from sealai_v2.knowledge.traps import load_traps

_CAT = load_traps()
_E = _CAT.by_id("TRAP-PTFE-KALTFLUSS")

# explanatory knowledge answer that STATES the cold-flow caveat itself (the PTFE wissensfrage case)
_EXPLAIN = (
    "PTFE ist nicht elastisch wie ein O-Ring-Werkstoff, eher kalt verformbar. Reiner PTFE-O-Ring ist "
    "statisch mechanisch kritisch: deutlicher Kaltfluss/Kriechen, keine elastische Rückstellung; "
    "chemische Beständigkeit ist breit, mechanische Eignung begrenzt."
)
# a real trap-walk: affirms the wrong recommendation, omits the caveat
_WALK = "Für deine Statikdichtung nimm einfach einen reinen PTFE-O-Ring — PTFE hält chemisch alles aus."


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


def test_confident_wrong_gate_untouched():
    out = _demote_caveat_addressed_traps((_f(gate="confident_wrong"),), _CAT, _EXPLAIN)
    assert out[0].review_state == "reviewed"  # only walked_into_trap is affected
