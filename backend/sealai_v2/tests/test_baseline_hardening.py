# -*- coding: utf-8 -*-
"""INC-BASELINE-HARDENING — the two Free-Narrator baseline fixes the narrator-contract-replay
surfaced (BUX-SPEED-TRAP-FIRSTTURN-01 + LOES-UNKLARES-MEDIUM-KEIN-MATERIAL-01).

Deterministic units only: the RWDR shaft-Ø derivation (Welle = d1) + the flag-gated prompt blocks
being byte-identical when OFF and present when ON. The L1 BEHAVIOUR change is owner-adjudicated in
the eval-REPLAY (not asserted here)."""

from __future__ import annotations

from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.calc.inline_extract import (
    extract_inline,
    extract_rwdr_shaft,
    merge_inline,
)
from sealai_v2.core.contracts import Flags
from sealai_v2.prompts.assembler import PromptAssembler

_BUX = "RWDR 40x62x8, NBR, 6000 U/min, Öl. Die Temperatur weiß ich noch nicht."


def test_rwdr_shaft_derives_d1_from_designation():
    facts = extract_rwdr_shaft(_BUX)
    assert [(f.feld, f.wert) for f in facts] == [("wellendurchmesser", "40 mm")]
    assert facts[0].provenance == "chat-inline"


def test_rwdr_shaft_binds_d1_so_v_can_compute():
    # Without the derivation only rpm binds (the gap the replay surfaced); with it, d1_mm binds too.
    inline = extract_inline(_BUX)
    assert "d1_mm" not in bind_params(inline).params
    merged = merge_inline(extract_rwdr_shaft(_BUX), inline)
    params = bind_params(merged).params
    assert params.get("d1_mm") == 40.0 and params.get("rpm") == 6000.0


def test_rwdr_shaft_excludes_oring():
    # An O-Ring's id/cord layout is NOT a shaft Ø — must derive nothing (fail-closed).
    assert extract_rwdr_shaft("O-Ring 40x3 EPDM") == ()


def test_rwdr_shaft_typed_value_wins_over_derived():
    q = "RWDR 40x62x8, Welle ist 50 mm"
    params = bind_params(merge_inline(extract_rwdr_shaft(q), extract_inline(q))).params
    assert params.get("d1_mm") == 50.0  # typed inline beats the derived 40


def test_prompt_byte_identical_when_flag_off():
    a = PromptAssembler()
    for flags in (Flags(), Flags(compliance_hint=True, safety_critical=True)):
        without = a.system_prompt(flags=flags)  # default baseline_hardening=False
        explicit_off = a.system_prompt(flags=flags, baseline_hardening=False)
        assert without == explicit_off
        assert "Speed-Trap als Pflichtbefund" not in without
        assert "Unklare Medienklasse" not in without


def test_prompt_blocks_present_when_flag_on():
    a = PromptAssembler()
    on = a.system_prompt(
        flags=Flags(compliance_hint=True, safety_critical=True),
        baseline_hardening=True,
    )
    assert "Speed-Trap als Pflichtbefund" in on
    assert "Unklare Medienklasse" in on
