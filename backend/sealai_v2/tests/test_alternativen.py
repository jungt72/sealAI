"""Alternativen/Hersteller (Modus F, Dim. 6) — the PARTNER POOL (owner business model): payment gates
pool MEMBERSHIP, the SELECTION ranks by capability fit (§3.9, never pay-to-rank). The capability-SEED
neutrality keystone stays structural on hersteller.py. Empty/no-match pool → honest "no partner" with
ZERO firm names (P1.7 — the backend invents none)."""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import (
    Answer,
    Flags,
    LlmResult,
    ModelConfig,
    PipelineResult,
    RememberedFact,
    SessionContext,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.hersteller import _entry, load_hersteller
from sealai_v2.knowledge.hersteller_partner import (
    HerstellerPartner,
    InProcessPartnerRegistry,
)
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import InProcessConversationMemory
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


def _partner(name, werkstoffe=(), bauformen=(), *, aktiv=True, plan=""):
    return HerstellerPartner(
        hersteller=name.lower().replace(" ", "-"),
        firmenname=name,
        aktiv=aktiv,
        lead_email=f"leads@{name}",
        plan=plan,
        werkstoffe=werkstoffe,
        bauformen=bauformen,
        beschreibung=f"{name} – Dichtungen",
    )


def _reg(*partners):
    return InProcessPartnerRegistry(tuple(partners))


# A realistic stages.gegencheck() shape (any assessed verdict — the ranking precondition (L6,
# P0-C) only cares that ONE ran, not its outcome). Used by the tests below that exercise the
# ranking/pool-lookup logic itself, not the new verdict precondition.
_VERDICT = {"disqualified": False, "basis": "matrix_compatible"}


def _fact(feld, wert, provenance="chat-inline"):
    return RememberedFact(feld=feld, wert=wert, provenance=provenance)


class TestCaseStateMaterial:
    """stages._case_state_material — recovers a canonical material from PERSISTED case-state,
    never trusting a distilled string blindly (L6, P0-C follow-up, Akzeptanzkriterium 4)."""

    def test_form_channel_werkstoffvorgabe_wins_when_canonical(self):
        cs = (_fact("werkstoffvorgabe", "FKM"),)
        assert stages._case_state_material(cs) == "FKM"

    def test_chat_channel_werkstoff_is_re_canonicalised_not_trusted_verbatim(self):
        # the distiller is an LLM — its free-text value must resolve through the SAME
        # deterministic vocabulary the live turn uses, exactly like "FPM" -> canonical "FKM".
        cs = (_fact("werkstoff", "wir verwenden FPM-Dichtungen"),)
        assert stages._case_state_material(cs) == "FKM"

    def test_unrecognised_distilled_string_never_counts_as_a_material(self):
        # P0-C's whole point: no string-matching stand-in for a real vocabulary check.
        cs = (_fact("werkstoff", "irgendein Gummi"),)
        assert stages._case_state_material(cs) is None

    def test_no_material_fact_at_all_returns_none(self):
        assert stages._case_state_material((_fact("medium", "Heißdampf"),)) is None

    def test_most_recent_fact_wins_over_an_earlier_one(self):
        cs = (_fact("werkstoffvorgabe", "FKM"), _fact("werkstoffvorgabe", "NBR"))
        assert stages._case_state_material(cs) == "NBR"


class TestCaseStateMedium:
    """stages._case_state_medium — collects every DISTINCT canonical medium persisted across
    turns (feld="medium" is already canonical, written by extract_medium_facts)."""

    def test_collects_distinct_media_across_turns(self):
        cs = (_fact("medium", "Heißdampf"), _fact("medium", "Aceton"))
        assert stages._case_state_medium(cs) == ["Heißdampf", "Aceton"]

    def test_deduplicates_repeated_medium(self):
        cs = (_fact("medium", "Heißdampf"), _fact("medium", "Heißdampf"))
        assert stages._case_state_medium(cs) == ["Heißdampf"]

    def test_no_medium_fact_returns_empty(self):
        assert stages._case_state_medium((_fact("werkstoffvorgabe", "FKM"),)) == []


class TestIsAlternativenRequest:
    """stages.is_alternativen_request — the public mirror of alternativen's own keyword gate
    (P0-C review fix: lets pipeline.py skip the case-state verdict fallback's matrix query on
    turns that were never going to trigger Modus F). Must agree with `alternativen` exactly."""

    def test_true_on_a_manufacturer_question(self):
        assert (
            stages.is_alternativen_request("Welcher Hersteller kann das liefern?")
            is True
        )

    def test_false_on_an_unrelated_question(self):
        assert (
            stages.is_alternativen_request("Was ist der Unterschied FKM vs. EPDM?")
            is False
        )

    def test_agrees_with_alternativen_itself_on_the_keyword_gate(self):
        # regression: this helper must never drift from _ALT_RE inside alternativen()
        reg = _reg(_partner("A", werkstoffe=("FKM",)))
        for q in ("Welcher Hersteller kann das liefern?", "Was kann FKM?"):
            gated_by_helper = stages.is_alternativen_request(q)
            fires_in_alternativen = (
                stages.alternativen(reg, q, _VERDICT, tenant_id="t1") is not None
            )
            assert gated_by_helper == fires_in_alternativen


class TestGegencheckFromCaseState:
    """stages.gegencheck_from_case_state — the L6 fallback itself: a REAL verdict re-derived
    from persisted case-state, not just a boolean "something was said once" flag."""

    def test_none_matrix_is_a_kill_switch(self):
        cs = (_fact("werkstoffvorgabe", "FKM"), _fact("medium", "Heißdampf"))
        assert stages.gegencheck_from_case_state(None, cs, tenant_id="t1") is None

    def test_material_without_medium_is_none(self):
        cs = (_fact("werkstoffvorgabe", "FKM"),)
        m = InProcessCompatibilityMatrix()
        assert stages.gegencheck_from_case_state(m, cs, tenant_id="t1") is None

    def test_medium_without_material_is_none(self):
        cs = (_fact("medium", "Heißdampf"),)
        m = InProcessCompatibilityMatrix()
        assert stages.gegencheck_from_case_state(m, cs, tenant_id="t1") is None

    def test_both_present_yields_a_real_verdict(self):
        # FKM + Heißdampf is a KNOWN disqualifying matrix cell (test_gegencheck_pipeline.py) —
        # same fixture, now reached via persisted case-state instead of the live question text.
        cs = (_fact("werkstoffvorgabe", "FKM"), _fact("medium", "Heißdampf"))
        m = InProcessCompatibilityMatrix()
        v = stages.gegencheck_from_case_state(m, cs, tenant_id="t1")
        assert v is not None and v["disqualified"] is True


def test_shipped_capability_seed_is_empty():
    assert (
        len(load_hersteller().faehigkeiten) == 0
    )  # owner-provided, not model-generated


def test_capability_seed_neutrality_keystone_rejects_payment_field():
    # The §3.9 structural guard on the capability SEED lane is UNTOUCHED by the partner model.
    with pytest.raises(ValueError, match="pay-to-rank|Bezahlung"):
        _entry(
            {
                "id": "X",
                "hersteller": "Y",
                "review_state": "draft",
                "provenance": ["draft:t"],
                "rank": 1,
            }
        )


def test_stage_empty_registry_no_data_zero_firm_names():
    # P1.7 — empty pool (eval/CI): grounded_data=False AND zero firm names; the backend invents none.
    v = stages.alternativen(
        InProcessPartnerRegistry(),
        "Wer kann einen RWDR aus FKM herstellen? Nenne vergleichbare Hersteller.",
        _VERDICT,
        tenant_id="t1",
    )
    assert v is not None and v["grounded_data"] is False
    assert v.get("hersteller", []) == [] and "ordered_by" not in v


def test_stage_none_without_alternatives_keyword():
    assert (
        stages.alternativen(
            _reg(_partner("A")), "Was kann FKM?", _VERDICT, tenant_id="t1"
        )
        is None
    )


def test_generic_replacement_and_comparison_are_not_partner_requests():
    registry = _reg(_partner("A"))
    for question in (
        "Meine alte Dichtung ist kaputt. Wie finde ich Ersatz?",
        "Schlüssel den RWDR auf und finde etwas Vergleichbares.",
        "Sind diese beiden Dichtungen austauschbar?",
    ):
        assert stages.alternativen(registry, question, None, tenant_id="t1") is None


def test_stage_none_without_verdict_asks_for_assessment_first():
    # L6 "Matching folgt dem Verdikt, nie umgekehrt" (Relay-Increment P0-C, owner Leitbild-Audit
    # 2026-07-02): the keyword gate alone used to be sufficient. A first-turn manufacturer
    # question with no prior Gegencheck verdict must NOT rank partners — it must ask for the
    # missing assessment instead, with zero firm names (same P1.7 discipline as the empty pool).
    reg = _reg(_partner("Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",)))
    v = stages.alternativen(
        reg, "Welcher Hersteller kann NBR-RWDR liefern?", None, tenant_id="t1"
    )
    assert v is not None and v["grounded_data"] is False
    assert v.get("hersteller", []) == [] and "ordered_by" not in v
    assert "Bewertung" in v["hinweis"] or "Situationsbewertung" in v["hinweis"]


def test_stage_returns_partner_pool_fit_ranked_and_transparent():
    reg = _reg(
        _partner(
            "Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",), plan="basic"
        ),  # fit 4
        _partner(
            "Premium-Teilfit", werkstoffe=("FKM",), plan="enterprise-xxl"
        ),  # fit 2
    )
    v = stages.alternativen(reg, "Wer macht RWDR aus FKM?", _VERDICT, tenant_id="t1")
    assert (
        v["grounded_data"] is True and v["partner"] is True
    )  # transparent partner pool
    assert [h["firmenname"] for h in v["hersteller"]] == [
        "Voll-Fit",
        "Premium-Teilfit",
    ]  # fit, NOT plan
    assert v["ordered_by"] == "capability"
    assert (
        "lead_email" not in v["hersteller"][0]
    )  # internal routing field NEVER exposed


def test_stage_inactive_partner_not_in_pool():
    v = stages.alternativen(
        _reg(
            _partner("Inaktiv", werkstoffe=("FKM",), bauformen=("RWDR",), aktiv=False)
        ),
        "Wer macht RWDR aus FKM?",
        _VERDICT,
        tenant_id="t1",
    )
    assert v["grounded_data"] is False  # inactive → not a partner → no firm shown


def _pipeline(client, registry, *, matrix=None):
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        partner_registry=registry,
        matrix=matrix,
    )


def test_alternativen_flows_to_result_empty_honest():
    res = asyncio.run(
        _pipeline(FakeLlmClient("Antwort"), InProcessPartnerRegistry()).run(
            "Wer kann das noch herstellen, RWDR aus FKM?", tenant=TenantContext("t1")
        )
    )
    assert res.alternativen is not None and res.alternativen["grounded_data"] is False


def test_alternativen_asks_for_assessment_first_without_verdict_end_to_end():
    # L6 (Relay-Increment P0-C), full pipeline: a manufacturer question with NO recognisable
    # material/medium in it never reaches a Gegencheck verdict (stages.gegencheck requires
    # both) — even with a matching partner in a wired registry, ranking must not fire.
    reg = _reg(_partner("Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",)))
    res = asyncio.run(
        _pipeline(
            FakeLlmClient("Antwort"), reg, matrix=InProcessCompatibilityMatrix()
        ).run("Welcher Hersteller kann das liefern?", tenant=TenantContext("t1"))
    )
    assert res.gegencheck is None  # no material/medium in the question → no verdict
    assert res.alternativen is not None
    assert res.alternativen["grounded_data"] is False
    assert res.alternativen.get("hersteller", []) == []


def test_alternativen_ranks_once_a_verdict_exists_end_to_end():
    # L6 (Relay-Increment P0-C), full pipeline, positive/regression path: once material+medium
    # are stated (so stages.gegencheck runs — ANY verdict, even a disqualifying one, per the
    # existing FKM+Heißdampf incompatibility fixture in test_gegencheck_pipeline.py), a
    # manufacturer question in the SAME turn ranks partners exactly as before this fix.
    reg = _reg(_partner("Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",)))
    res = asyncio.run(
        _pipeline(
            FakeLlmClient("Antwort"), reg, matrix=InProcessCompatibilityMatrix()
        ).run(
            "Wir verwenden FKM in Heißdampf, welcher Hersteller kann das liefern?",
            tenant=TenantContext("t1"),
        )
    )
    assert (
        res.gegencheck is not None
    )  # verdict ran (disqualified — irrelevant to matching)
    assert res.alternativen is not None
    assert res.alternativen["grounded_data"] is True
    assert [h["firmenname"] for h in res.alternativen["hersteller"]] == ["Voll-Fit"]


_DISTILL_MARKER = "extrahierst strukturierte Fakten"  # distill.jinja's opening line


class _ChatDistillFake:
    """Routes by system prompt: a distill call -> a fixed facts-JSON; any other call -> a fixed
    prose answer. Lets one fake drive a full two-turn chat path (distill + L1) — same pattern as
    test_calc_binding_channels.py's _ChatFake, duplicated here to keep this file self-contained."""

    def __init__(self, distill_json: str, answer: str = "ok") -> None:
        self.distill_json = distill_json
        self.answer = answer

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        text = self.distill_json if _DISTILL_MARKER in system else self.answer
        return LlmResult(text=text, model=model_config.model, finish_reason="stop")


def _chat_pipeline_with_partners(client, registry, matrix):
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        matrix=matrix,
        partner_registry=registry,
        memory=InProcessConversationMemory(),
        distiller=Distiller(
            client, DistillPromptAssembler(), ModelConfig("fake-helper")
        ),
    )


def test_alternativen_ranks_on_a_later_turn_using_persisted_case_state():
    # L6 (Relay-Increment P0-C, follow-up — Akzeptanzkriterium 2 + 4): the real multi-turn shape.
    # Turn 1 states material (via the chat distiller -> feld="werkstoff") + medium (deterministic
    # extract_medium_facts -> feld="medium") but asks nothing about manufacturers. Turn 2 asks
    # ONLY the manufacturer question — no material/medium in ITS text — and must still rank,
    # because the assessment from turn 1 is read back from the PERSISTED case-state
    # (gegencheck_from_case_state), not re-derived from turn 2's text.
    reg = _reg(_partner("Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",)))
    client = _ChatDistillFake('{"facts": [{"feld": "werkstoff", "wert": "FKM"}]}')
    p = _chat_pipeline_with_partners(client, reg, InProcessCompatibilityMatrix())
    tenant, session = TenantContext("t1"), SessionContext("s1")

    turn1 = asyncio.run(
        p.run(
            "Wir verwenden FKM in Heißdampf, ist das okay?",
            tenant=tenant,
            session=session,
        )
    )
    assert (
        turn1.gegencheck is not None
    )  # turn 1 itself already assessed it (same-turn path)
    assert turn1.alternativen is None  # turn 1 never asked about manufacturers

    asyncio.run(
        p.flush_memory(tenant_id="t1", session_id="s1")
    )  # land the background remember

    turn2 = asyncio.run(
        p.run("Welcher Hersteller kann das liefern?", tenant=tenant, session=session)
    )
    assert (
        turn2.gegencheck is None
    )  # turn 2's OWN text names neither material nor medium
    assert turn2.alternativen is not None
    assert (
        turn2.alternativen["grounded_data"] is True
    )  # ranked anyway — via persisted case-state
    assert [h["firmenname"] for h in turn2.alternativen["hersteller"]] == ["Voll-Fit"]


def test_alternativen_still_blocked_on_a_later_turn_without_any_prior_assessment():
    # Regression companion: a later turn's manufacturer question stays blocked when NEITHER the
    # live turn NOR any earlier turn established material+medium — the case-state fallback must
    # not accidentally rank on unrelated persisted facts.
    reg = _reg(_partner("Voll-Fit", werkstoffe=("FKM",), bauformen=("RWDR",)))
    client = _ChatDistillFake('{"facts": [{"feld": "anwendung", "wert": "Getriebe"}]}')
    p = _chat_pipeline_with_partners(client, reg, InProcessCompatibilityMatrix())
    tenant, session = TenantContext("t1"), SessionContext("s1")

    asyncio.run(p.run("Wir bauen ein Getriebe.", tenant=tenant, session=session))
    asyncio.run(p.flush_memory(tenant_id="t1", session_id="s1"))
    turn2 = asyncio.run(
        p.run("Welcher Hersteller kann das liefern?", tenant=tenant, session=session)
    )
    assert turn2.alternativen is not None
    assert turn2.alternativen["grounded_data"] is False
    assert turn2.alternativen.get("hersteller", []) == []


def test_serializer_surfaces_alternativen():
    out = chat_response(
        PipelineResult(
            question="x",
            tenant_id="t1",
            flags=Flags(),
            understanding=None,
            answer=Answer(text="…", model="fake"),
            alternativen={"grounded_data": False, "neutralitaet": "…"},
        )
    )
    assert out["alternativen"]["grounded_data"] is False
