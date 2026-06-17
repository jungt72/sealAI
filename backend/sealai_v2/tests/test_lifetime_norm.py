"""OPTIMIZE_BACKLOG #6 — the L1 norm forbids quantitative future-performance PREDICTIONS (lifetime/
wear/leakage/interval), incl. a hedged range, while staying HELPFUL (explain factors + route to a
source) and preserving legitimate kernel/cited numbers. The L3 side: a lifetime range is no longer
exempted from the precision guard, but a compound-LIMIT range (temperature/Verpressung) still is.
"""

from __future__ import annotations

from sealai_v2.core.contracts import Flags
from sealai_v2.core.l3_verifier import is_precision_overapplication as ov
from sealai_v2.prompts.assembler import PromptAssembler


def _prompt() -> str:
    return PromptAssembler().system_prompt(flags=Flags())


def test_l1_norm_forbids_quantitative_lifetime_prediction_incl_range():
    p = _prompt()
    assert "Künftige Performance sagst du nicht in Zahlen voraus" in p
    # explicitly covers ranges / orders-of-magnitude / "Orientierung", not just a single number
    assert "keine Zahl" in p and "Spanne" in p and "Orientierungs" in p
    # generalised to the prediction class (not only Lebensdauer)
    assert "Verschleiß- und Leckageraten" in p and "Wartungsintervalle" in p


def test_l1_norm_stays_helpful_not_a_refusal():
    p = _prompt()
    # the answer must still address the factors and route to a real source — not bare refusal
    assert "Einflussfaktoren" in p
    assert "Datenblatt / Test / Hersteller" in p


def test_l1_norm_preserves_kernel_and_cited_numbers():
    p = _prompt()
    assert "Kern-Werte" in p and "Quellenzahlen bleiben" in p
    # the compound-LIMIT range norm (temperature etc.) is untouched — ranges there stay correct
    assert "Gib **Bereiche** statt Schein-Präzision" in p


def test_l3_lifetime_range_is_not_exempt_but_limit_range_is():
    # a lifetime range with a caveat is NO LONGER exempt → L3 catches it
    assert not ov(
        "PREC-LEBENSDAUER", "5 000–20 000 Betriebsstunden (typisch, Richtwert)"
    )
    assert not ov(
        "PREC-LEBENSDAUER", "einige tausend bis zehntausend Stunden (als Orientierung)"
    )
    # a compound-LIMIT range (temperature/Verpressung) with a caveat is still the correct form → exempt
    assert ov(
        "PREC-EINZELZAHL", "ca. 120–130 °C (typisch, gegen Datenblatt verifizieren)"
    )
    assert ov(
        "PREC-EINZELZAHL",
        "statische O-Ring-Verpressung ~15–25 % (Richtwert, Datenblatt)",
    )
