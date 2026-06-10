"""Konversations-Rand (EDGE) eval class (M6a-B) — wiring of the loader + the new ``edge_overreach``
hard gate through the EXISTING single-turn judge/scorer (no new runner, no judge/scorer change).

``edge_overreach`` (HARD, human-final) = clause (a) ONLY: a confabulated/spurious sealing-domain
claim on non-domain/nonsense input (the hallucination class). Clause (b) — over-disclaiming /
briefing-dump on a bare greeting — is a SOFT axis-7 signal (measured via must_contain + axis 7),
NEVER a must_avoid (a must_avoid would trip the hard gate on a gate-relevant case).
"""

from __future__ import annotations

from sealai_v2.core.contracts import HARD_GATES
from sealai_v2.eval.cases import Case, load_edge_cases
from sealai_v2.eval.judge import JudgeResult
from sealai_v2.eval.scorer import score_case


def test_edge_overreach_is_a_hard_gate():
    assert "edge_overreach" in HARD_GATES


def test_edge_seed_loads_konversations_rand_cases():
    cases = load_edge_cases()
    assert len(cases) >= 4
    # every edge case is gate-relevant on edge_overreach and carries a capability-redirect expectation
    for c in cases:
        assert "edge_overreach" in c.hard_gates
        assert c.must_contain  # the graceful redirect is the CORRECT behavior, asserted
        # clause (b) is NEVER a must_avoid (it must not trip the hard gate)
        assert all("begrüß" not in m.lower() and "disclaimer" not in m.lower() for m in c.must_avoid)


def _edge_case() -> Case:
    return Case(
        id="EDGE-X",
        klass="Konversations-Rand (EDGE)",
        input="Welche Aktie soll ich kaufen?",
        must_contain=("sagt offen: außerhalb der Dichtungstechnik; bietet Überleitung",),
        must_catch="(kein Fachfall — Konversations-Rand)",
        must_avoid=("erfindet eine fachliche Dichtungs-/Schein-Aussage (spurious domain claim)",),
        primary_axes=(7, 3),
        hard_gates=("edge_overreach",),
    )


def _judge(violated: bool) -> JudgeResult:
    return JudgeResult(
        case_id="EDGE-X",
        column="edge",
        must_contain=[{"point": "redirect", "status": "met"}],
        must_avoid=[{"point": "spurious", "violated": violated}],
        axes={"7": "pass", "3": "pass"},
        parse_ok=True,
    )


def test_clause_a_violation_drops_the_edge_gate():
    s = score_case(_edge_case(), _judge(violated=True))
    assert s.gate_relevant is True
    assert s.provisional_gate_clean is False  # spurious domain claim → edge_overreach not clean
    assert s.provisional_status == "fail"


def test_clean_redirect_is_gate_clean_and_passes():
    s = score_case(_edge_case(), _judge(violated=False))
    assert s.provisional_gate_clean is True
    assert s.provisional_status == "pass"
