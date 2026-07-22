"""INC-NARRATOR-CONTRACT Phase 3/5 wiring — the guard runs after generate; on BLOCK it regenerates ONCE.
Flag-gated: OFF -> no guard. Plus the pure helpers (known_inputs / correction_note). Offline (fakes)."""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import GroundingFact, ModelConfig, RetrievalResult
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.output_guard import (
    GuardResult,
    Violation,
    correction_note,
    fail_closed_answer,
    known_inputs,
)
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
    client = ScriptedFakeLlmClient(
        [_LEAKY, _CLEAN]
    )  # leaky draft, then a clean regeneration
    res = _run(_pipeline(client))
    assert len(client.calls) == 2  # generate + exactly ONE regenerate
    assert res.answer.text == _CLEAN  # the clean regeneration is what ships
    assert res.guard is not None and res.guard["action"] == "PASS"
    assert res.guard["terminal_action"] == "PASS"


def test_guard_fails_closed_when_regeneration_is_still_blocked():
    client = ScriptedFakeLlmClient([_LEAKY, _LEAKY])
    res = _run(_pipeline(client))
    assert len(client.calls) == 2
    assert res.answer.model == "deterministic-output-guard"
    assert _LEAKY not in res.answer.text
    assert "FKM" in res.answer.text
    assert res.guard is not None and res.guard["action"] == "BLOCK"
    assert res.guard["terminal_action"] == "PASS"
    assert res.guard["hedged"] is True
    assert res.guard["claim_mappings"] == []
    assert res.guard["terminal_invalidated_by"] == "output_guard_fallback"


def test_guard_passes_clean_first_time_no_regenerate():
    client = ScriptedFakeLlmClient(
        [_CLEAN]
    )  # only one response scripted -> a 2nd call would raise
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
            (
                Violation("invented_number", "250"),
                Violation("forbidden_phrase", "freigegeben"),
            ),
        )
    )
    assert (
        "250" in note
        and "freigegeben" in note
        and note.startswith("OUTPUT-GUARD-KORREKTUR")
    )


def test_fail_closed_answer_preserves_only_kernel_value_and_warning():
    text = fail_closed_answer(
        {
            "allowed_claims": [],
            "allowed_values": [
                {
                    "calc_id": "umfangsgeschwindigkeit",
                    "name": "v_m_s",
                    "value": 12.5664,
                    "unit": "m/s",
                    "warnings": [
                        "nahe an der Belastungsgrenze → grenzwertige Auslegung"
                    ],
                }
            ],
            "required_clauses": [],
        }
    )
    assert "Umfangsgeschwindigkeit: 12.5664 m/s" in text
    assert "grenzwertige Auslegung" in text


def test_general_knowledge_fallback_names_limited_reviewed_scope_not_contradiction():
    text = fail_closed_answer(
        {
            "status": "GENERAL",
            "allowed_claims": [
                {
                    "id": "FK-PTFE",
                    "text": "PTFE weist eine sehr hohe chemische Beständigkeit auf.",
                    "severity": "info",
                }
            ],
            "allowed_values": [],
            "required_clauses": [],
        }
    )

    assert "aktuell geprüften Quellen" in text
    assert "nicht widerspruchsfrei" not in text


def test_fail_closed_rwdr_case_keeps_kernel_value_and_design_inputs():
    text = fail_closed_answer(
        {
            "status": "GENERAL",
            "allowed_claims": [
                {
                    "id": "FK-RWDR",
                    "text": "Ein RWDR benötigt einen tragfähigen Schmierfilm.",
                    "severity": "info",
                }
            ],
            "allowed_values": [
                {
                    "calc_id": "umfangsgeschwindigkeit",
                    "name": "v_m_s",
                    "value": 3.5343,
                    "unit": "m/s",
                    "warnings": [],
                }
            ],
            "required_clauses": [],
        },
        question=(
            "RWDR für 45 mm Welle bei 1500 U/min, Mineralöl, 80 Grad und Staub "
            "technisch vorprüfen"
        ),
    )

    assert text.startswith("Technische Vorprüfung")
    assert "Umfangsgeschwindigkeit: 3.5343 m/s" in text
    assert "Wellenhärte, Rauheit und Drallfreiheit" in text
    assert "Druckdifferenz mit Druckspitzen" in text
    assert "Wissensfrage" not in text


# ── P0-B: response_contract_general_guard_enabled — the guard on NON-Gegencheck turns ──────────────

_KQ = "Was ist FKM und wo wird es eingesetzt?"
_FKM_FACT = GroundingFact(
    text="FKM ist ein fluoriertes Elastomer mit hoher Temperatur- und Ölbeständigkeit.",
    quelle="Fachkarte FKM",
    card_id="CARD-FKM-1",
    kind="card",
)
_KNOWLEDGE_CLEAN = (
    "FKM ist ein fluoriertes Elastomer mit hoher Temperatur- und Ölbeständigkeit."
)
_KNOWLEDGE_LEAKY = (
    "FKM ist bis 400 °C dauerhaft einsetzbar und für alle Medien freigegeben."
)


class _FixedRetriever:
    """Minimal Retriever test double — returns the SAME GroundingFact for any query (no matrix_facts,
    no provisional): a stand-in for a real L2 hit on a pure knowledge question (no Gegencheck verdict
    is ever produced for a question with no stated medium, regardless of grounding)."""

    async def retrieve(self, query, *, tenant_id, k=5):
        return RetrievalResult(grounding_facts=(_FKM_FACT,))


def _knowledge_pipeline(
    client, *, rc: bool = True, general_guard: bool = False
) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=_FixedRetriever(),
        matrix=InProcessCompatibilityMatrix(),  # present, but this question states no medium -> gegencheck stays None
        response_contract_enabled=rc,
        response_contract_general_guard_enabled=general_guard,
    )


def _run_knowledge(p):
    return asyncio.run(p.run(_KQ, tenant=TenantContext("t1")))


def test_general_guard_off_by_default_is_noop_on_a_grounded_knowledge_turn():
    # regression lock: response_contract_enabled=True ALONE (the new flag defaulted/omitted) must
    # behave EXACTLY as before this change — a knowledge turn with real grounding ships unguarded.
    client = ScriptedFakeLlmClient([_KNOWLEDGE_LEAKY])
    res = _run_knowledge(_knowledge_pipeline(client))  # general_guard defaults to False
    assert (
        res.gegencheck is None
    )  # no medium stated -> no verdict, confirms this is the non-Gegencheck path
    assert (
        res.contract is None
    )  # the renderer-mode contract never builds without a verdict
    assert res.guard is None  # the NEW guard path did not fire either — flag is off
    assert len(client.calls) == 1  # no regenerate


def test_general_guard_on_passes_a_clean_knowledge_answer():
    client = ScriptedFakeLlmClient([_KNOWLEDGE_CLEAN])
    res = _run_knowledge(_knowledge_pipeline(client, general_guard=True))
    assert res.guard is not None and res.guard["action"] == "PASS"
    assert len(client.calls) == 1


def test_general_guard_on_blocks_invented_number_and_regenerates_without_renderer_mode():
    client = ScriptedFakeLlmClient([_KNOWLEDGE_LEAKY, _KNOWLEDGE_CLEAN])
    res = _run_knowledge(_knowledge_pipeline(client, general_guard=True))
    assert len(client.calls) == 2  # generate + exactly one regenerate
    assert res.answer.text == _KNOWLEDGE_CLEAN
    assert res.guard is not None and res.guard["action"] == "PASS"
    # the regenerate call's rendered system prompt must NOT contain the Renderer-Modus takeover —
    # contract stayed None (only guard_contract, guard-only, was ever built) — this is the whole
    # point of P0-B's design: the safety net widens, the teaching-depth prompt does not narrow.
    regenerate_system_prompt = client.calls[1]["system"]
    assert "# MODUS: RENDERER" not in regenerate_system_prompt
    assert "Du bist Renderer, nicht Autor" not in regenerate_system_prompt
    # the correction note DID reach L1 independent of contract (own prompt block, not nested in it)
    assert "OUTPUT-GUARD-KORREKTUR" in regenerate_system_prompt


def test_general_guard_does_not_change_the_existing_gegencheck_renderer_path():
    # both new-flag states, on a REAL Gegencheck turn: must reproduce test_guard_regenerates_once_on_block
    # exactly — the general-guard flag only ever ADDS a second path for turns with no verdict.
    for general_guard in (False, True):
        client = ScriptedFakeLlmClient([_LEAKY, _CLEAN])
        res = asyncio.run(
            Pipeline(
                generator=L1Generator(
                    client, PromptAssembler(), ModelConfig("fake-l1")
                ),
                client=client,
                helper_model=ModelConfig("fake-helper"),
                understand_enabled=False,
                retriever=None,
                matrix=InProcessCompatibilityMatrix(),
                response_contract_enabled=True,
                response_contract_general_guard_enabled=general_guard,
            ).run(_Q, tenant=TenantContext("t1"))
        )
        assert len(client.calls) == 2
        assert res.answer.text == _CLEAN
        assert res.guard is not None and res.guard["action"] == "PASS"
        # the renderer-mode contract (Gegencheck-shaped) is unaffected either way
        assert (
            res.contract is not None
            and res.contract["status"] == "COVERED_RECOMMENDATION"
        )
