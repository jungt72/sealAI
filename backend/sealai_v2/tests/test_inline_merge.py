"""INC-3b — merge_inline + Pipeline-Verdrahtung: Inline-Werte ueberlagern recalled facts.

Drei deterministische Akzeptanz-Tests (kein LLM, kein I/O):
- PRAEZEDENZ:    inline gewinnt ueber recalled fuer dasselbe Feld.
- GEGENPROBE:    bind_params nach merge sieht den Inline-Wert.
- RECALLED-FALLBACK: ohne Inline-Treffer bleibt der remembered Wert gebunden.
"""

from __future__ import annotations

from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.calc.inline_extract import extract_inline, merge_inline
from sealai_v2.core.contracts import RememberedFact


def _fact(feld: str, wert: str) -> RememberedFact:
    return RememberedFact(feld=feld, wert=wert)


def test_inline_wins_over_recalled():
    """PRAEZEDENZ: case_state hat 10 bar, Nachricht nennt 16 bar → Ergebnis ist 16 bar."""
    case_state = (_fact("druck", "10 bar"),)
    result = merge_inline(case_state, extract_inline("16 bar"))
    druck_facts = [f for f in result if f.feld == "druck"]
    assert len(druck_facts) == 1
    assert druck_facts[0].wert == "16 bar"


def test_bind_params_sees_inline_value():
    """GEGENPROBE: bind_params(merge_inline(...)) liefert p_bar=16.0, nicht 10.0."""
    case_state = (_fact("druck", "10 bar"),)
    bound = bind_params(merge_inline(case_state, extract_inline("16 bar")))
    assert bound.params == {"p_bar": 16.0}


def test_recalled_fallback_without_inline_match():
    """RECALLED-FALLBACK: kein Inline-Treffer → remembered 10 bar bleibt gebunden."""
    case_state = (_fact("druck", "10 bar"),)
    bound = bind_params(merge_inline(case_state, extract_inline("kein wert")))
    assert bound.params == {"p_bar": 10.0}
