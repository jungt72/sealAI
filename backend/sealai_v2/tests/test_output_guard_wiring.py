"""INC-NARRATOR-CONTRACT Phase 3/5 wiring — the guard runs after generate; on BLOCK it regenerates ONCE.
Flag-gated: OFF -> no guard. Plus the pure helpers (known_inputs / correction_note). Offline (fakes)."""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.output_guard import GuardResult, Violation, correction_note, known_inputs
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_Q = "Wir verwenden FKM in Heißdampf, passt das?"
# A clean render for the FKM×Heißdampf (disqualified -> COVERED_RECOMMENDATION) contract: names only the
# user's material, defers to the manufacturer, includes the required clause verbatim, invents nothing.
_CLEAN = (
    "FKM ist hier kritisch — bitte den Werkstoff für diesen Anwendungsfall beim Hersteller absichern. "
    "Die finale Compound-/Werkstofffreigabe trifft der Hersteller."
)
_LEAKY = "FKM ist bis 250 °C in Heißdampf bestens geeignet und freigegeben."


def _pipeline(client, *, rc: bool = True) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        matrix=InProcessCompatibilityMatrix(),
        response_contract_enabled=rc,
    )


def _run(p):
    return asyncio.run(p.run(_Q, tenant=TenantContext("t1")))


def test_guard_regenerates_once_on_block():
    client = ScriptedFakeLlmClient([_LEAKY, _CLEAN])  # leaky draft, then a clean regeneration
    res = _run(_pipeline(client))
    assert len(client.calls) == 2  # generate + exactly ONE regenerate
    assert res.answer.text == _CLEAN  # the clean regeneration is what ships
    assert res.guard is not None and res.guard["action"] == "PASS"


def test_guard_passes_clean_first_time_no_regenerate():
    client = ScriptedFakeLlmClient([_CLEAN])  # only one response scripted -> a 2nd call would raise
    res = _run(_pipeline(client))
    assert len(client.calls) == 1
    assert res.guard["action"] == "PASS"


def test_guard_off_is_noop():
    client = ScriptedFakeLlmClient([_LEAKY])  # ships as-is; no guard, no regenerate
    res = _run(_pipeline(client, rc=False))
    assert res.guard is None
    assert len(client.calls) == 1


# ── the pure helpers ─────────────────────────────────────────────────────────────────────────────


def test_known_inputs_extracts_user_values_and_materials():
    vals, mats = known_inputs("Wir setzen FKM in Heißdampf bei 140 °C ein.")
    assert "FKM" in mats and "140" in vals


def test_correction_note_empty_on_pass_and_names_violations_on_block():
    assert correction_note(GuardResult(True, "PASS", ())) == ""
    note = correction_note(
        GuardResult(
            False,
            "BLOCK",
            (Violation("invented_number", "250"), Violation("forbidden_phrase", "freigegeben")),
        )
    )
    assert "250" in note and "freigegeben" in note and note.startswith("OUTPUT-GUARD-KORREKTUR")
