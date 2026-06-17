"""§4 matrix → L3 verification (Gap #2, Step B): a reviewed matrix verdict is a CORRECTION source.
A draft compatibility claim that contradicts a reviewed cell is regenerated/hedged against the cell's
verdict (integrity: the replacement fact comes ONLY from the reviewed cell, never free-generated) —
parallel to the trap-catalog path. A consistent draft PASSES (no over-block).
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import Answer, Flags, ModelConfig, VerifierAction
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import (
    L3Verifier,
    build_matrix_correction_note,
    run_verify,
)
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.knowledge.traps import load_traps
from sealai_v2.prompts.assembler import PromptAssembler, VerifierPromptAssembler
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_CATALOG = load_traps()


def _mx(query: str):
    return InProcessCompatibilityMatrix().query(tenant_id="t", query_text=query)


def _verifier(client):
    return L3Verifier(
        client, VerifierPromptAssembler(), ModelConfig("fake-verify"), _CATALOG
    )


def _generator(client):
    return L1Generator(client, PromptAssembler(), ModelConfig("fake-l1"))


def _run(client, draft_text, matrix_facts):
    return asyncio.run(
        run_verify(
            _verifier(client),
            _generator(client),
            _CATALOG,
            "Passt FKM für Heißdampf-Sterilisation?",
            Answer(text=draft_text, model="fake-l1"),
            flags=Flags(),
            matrix_facts=matrix_facts,
        )
    )


def test_matrix_contradiction_corrects_against_the_cell():
    mx = _mx("FKM Heißdampf")
    assert any(f.card_id == "MX-FKM-DAMPF" for f in mx)
    client = ScriptedFakeLlmClient(
        [
            '{"findings":[{"matrix_contradiction":true,"cell_id":"MX-FKM-DAMPF","violated":true,"evidence":"FKM passt für Heißdampf"}],"verdict":"violation"}',  # verify draft
            "Korrigiert: FKM hydrolysiert in Dampf; für Dampf ist EPDM peroxidvernetzt der Standard.",  # regen
            '{"findings":[],"verdict":"clean"}',  # verify regen → clean
        ]
    )
    final, verdict = _run(client, "FKM passt prima für Heißdampf.", mx)
    assert verdict.action == VerifierAction.CORRECTED
    assert verdict.regenerated
    assert any(
        f.kind == "matrix" and f.trap_id == "MX-FKM-DAMPF" for f in verdict.findings
    )
    assert "hydrolysiert" in final.text  # the regenerated, corrected answer


def test_matrix_contradiction_hedges_if_regen_still_trips():
    mx = _mx("FKM Heißdampf")
    contradiction = '{"findings":[{"matrix_contradiction":true,"cell_id":"MX-FKM-DAMPF","violated":true,"evidence":"FKM passt für Heißdampf"}],"verdict":"violation"}'
    client = ScriptedFakeLlmClient(
        [contradiction, "Immer noch falsch: FKM passt für Heißdampf.", contradiction]
    )
    final, verdict = _run(client, "FKM passt prima für Heißdampf.", mx)
    assert verdict.action == VerifierAction.BLOCKED_HEDGE
    assert "hydrolysiert" in final.text  # hedge states the reviewed verdict
    assert "keine Freigabe" in final.text
    assert "passt prima" not in final.text  # never echoes the wrong draft claim


def test_consistent_draft_passes_no_overblock():
    mx = _mx("FKM Heißdampf")
    client = ScriptedFakeLlmClient(['{"findings":[],"verdict":"clean"}'])
    final, verdict = _run(
        client,
        "FKM ist für Heißdampf ungeeignet (Hydrolyse); EPDM ist der Standard.",
        mx,
    )
    assert verdict.action == VerifierAction.PASS
    assert final.text.startswith("FKM ist für Heißdampf ungeeignet")


def test_invented_matrix_cell_id_is_ignored():
    mx = _mx("FKM Heißdampf")
    client = ScriptedFakeLlmClient(
        [
            '{"findings":[{"matrix_contradiction":true,"cell_id":"MX-DOES-NOT-EXIST","violated":true,"evidence":"x"}],"verdict":"violation"}'
        ]
    )
    final, verdict = _run(client, "irgendwas", mx)
    assert verdict.action == VerifierAction.PASS  # invented id → no finding → no block


def test_correction_note_integrity_only_from_reviewed_cell():
    mx = _mx("FKM Heißdampf")  # contains MX-FKM-DAMPF
    from sealai_v2.core.contracts import VerifierFinding

    good = (
        VerifierFinding(
            trap_id="MX-FKM-DAMPF",
            gate="confident_wrong",
            review_state="reviewed",
            evidence="e",
            kind="matrix",
        ),
    )
    note = build_matrix_correction_note(mx, good)
    assert (
        note
        and "hydrolysiert" in note
        and "Verträglichkeitsmatrix · MX-FKM-DAMPF" in note
    )
    # a finding whose cell was NOT injected → no correction fact available → None (→ caller hedges)
    absent = (
        VerifierFinding(
            trap_id="MX-NOT-INJECTED",
            gate="confident_wrong",
            review_state="reviewed",
            evidence="e",
            kind="matrix",
        ),
    )
    assert build_matrix_correction_note(mx, absent) is None
