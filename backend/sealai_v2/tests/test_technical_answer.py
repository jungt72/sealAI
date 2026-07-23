from __future__ import annotations

import asyncio
import json

import pytest

from sealai_v2.core.contracts import (
    CalcResult,
    ComputedValue,
    Flags,
    GroundingFact,
    ModelConfig,
)
from sealai_v2.core.communication_plan import build_communication_plan
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.technical_answer import (
    TechnicalAnswer,
    TechnicalAnswerValidationError,
    calibrate_technical_answer,
    validate_technical_answer,
)
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.knowledge.traps import load_traps
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient


def _payload(*, evidence_ids=None, revision=7):
    return json.dumps(
        {
            "schema_version": 1,
            "intent": "material_knowledge",
            "case_revision": revision,
            "conclusion": "PTFE ist ein thermoplastischer Dichtungswerkstoff.",
            "assumptions": [],
            "missing_information": [],
            "claims": [
                {
                    "text": "PTFE zeigt eine geringe Reibung.",
                    "evidence_ids": evidence_ids
                    if evidence_ids is not None
                    else ["EV-1"],
                    "criticality": "supporting",
                }
            ],
            "recommendation": {
                "summary": "",
                "status": "none",
                "conditions": [],
            },
            "needs_human_review": False,
        }
    )


def _generator(client):
    return L1Generator(
        client,
        PromptAssembler(),
        ModelConfig("standard"),
        structured_output_enabled=True,
    )


def _knowledge_plan() -> dict:
    return {
        "profile": "material_overview",
        "subjects": ["PTFE"],
        "comparison": False,
        "subject_coverage": [],
        "evidence_status": "complete",
        "evidence_fact_count": 1,
        "evidence_document_count": 1,
        "sections": [],
    }


def test_structured_answer_is_validated_and_rendered_deterministically():
    client = FakeLlmClient(_payload())
    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact("fact", "ledger", card_id="EV-1", sources=("DOC-1",)),
            ),
            case_revision=7,
        )
    )
    assert answer.model == "standard"
    assert answer.text.startswith("PTFE ist ein thermoplastischer Dichtungswerkstoff.")
    assert "quellengebunden" in answer.text
    assert "EV-1" not in answer.text
    assert len(client.calls) == 1


def test_unknown_evidence_id_gets_exactly_one_semantic_repair():
    client = ScriptedFakeLlmClient(
        [_payload(evidence_ids=["INVENTED"]), _payload(evidence_ids=["EV-1"])]
    )
    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(GroundingFact("PTFE fact", "ledger", card_id="EV-1"),),
            case_revision=7,
        )
    )
    assert "quellengebunden" in answer.text
    assert "EV-1" not in answer.text
    assert len(client.calls) == 2


def test_knowledge_answer_falls_back_without_a_second_paid_call():
    client = FakeLlmClient(_payload(evidence_ids=[]))
    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(GroundingFact("PTFE fact", "ledger", card_id="EV-1"),),
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )

    assert "Weitere quellengebundene Einordnung" in answer.text
    assert "- PTFE fact" in answer.text
    assert "geprüft belegt" not in answer.text
    assert answer.finish_reason == "deterministic_engineering_fallback"
    assert len(client.calls) == 1


def test_evidence_bound_technical_answer_repairs_once_then_falls_back():
    client = FakeLlmClient(_payload(evidence_ids=[]))
    answer = asyncio.run(
        _generator(client).generate(
            "Welcher Dichtungsaufbau passt?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Geprüfter technischer Zusammenhang.",
                    "ledger",
                    card_id="EV-1",
                ),
            ),
            require_evidence_for_all_claims=True,
            work_solution_candidate=True,
            case_revision=7,
        )
    )

    assert "Geprüfter technischer Zusammenhang" in answer.text
    assert answer.finish_reason == "deterministic_evidence_fallback"
    assert len(client.calls) == 2
    assert "one primary provisional candidate" in client.calls[0]["system"]
    assert "failed deterministic evidence validation" in client.calls[1]["system"]


def test_solution_fallback_selects_relevant_facets_instead_of_first_card_entries():
    client = FakeLlmClient(_payload(evidence_ids=[]))
    answer = asyncio.run(
        _generator(client).generate(
            "Getriebe in staubiger Umgebung: Was wäre ein sinnvoller Ansatz?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "EPDM passt zu Glykol-Wasser-Gemischen.",
                    "ledger",
                    card_id="FK-UNRELATED-EPDM",
                    answer_facets=("media_compatibility",),
                ),
                GroundingFact(
                    "RWDR-Bauformen unterscheiden sich unter anderem durch eine Staublippe.",
                    "ledger",
                    card_id="FK-RWDR-ENGINEERING-PROFILE",
                    answer_facets=("variants", "applications"),
                    claim_id="RWDR-VARIANTS",
                ),
                GroundingFact(
                    "Die Gegenlauffläche muss hinsichtlich Drall, Rundlauf und Rauheit geprüft werden.",
                    "ledger",
                    card_id="FK-RWDR-ENGINEERING-PROFILE",
                    answer_facets=("design_interfaces", "selection_inputs"),
                    claim_id="RWDR-INTERFACES",
                ),
            ),
            require_evidence_for_all_claims=True,
            work_solution_candidate=True,
            case_revision=7,
        )
    )

    assert "Staublippe" in answer.text
    assert "Drall, Rundlauf und Rauheit" in answer.text
    assert "EPDM passt zu Glykol" not in answer.text
    assert answer.text.count("quellengebunden") == 2


def test_source_bound_policy_fact_outranks_broad_profile_in_fallback():
    client = FakeLlmClient(_payload(evidence_ids=[]))
    answer = asyncio.run(
        _generator(client).generate(
            "Getriebe in staubiger Umgebung: Was wäre ein sinnvoller Ansatz?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Ein RWDR ist eine berührende Rotationsdichtung.",
                    "ledger",
                    card_id="FK-RWDR-ENGINEERING-PROFILE",
                    answer_facets=("definition",),
                ),
                GroundingFact(
                    "Für die staubige Umgebung ist ein RWDR mit Staublippe der zu prüfende Kandidat.",
                    "reviewed policy",
                    card_id="POLICY-GETRIEBE",
                    sources=("primary-source",),
                    kind="trap",
                ),
            ),
            require_evidence_for_all_claims=True,
            work_solution_candidate=True,
            case_revision=7,
        )
    )

    assert "RWDR mit Staublippe" in answer.text
    assert "berührende Rotationsdichtung" not in answer.text
    assert "Nächster Klärungsschritt" not in answer.text
    assert answer.finish_reason == "deterministic_reviewed_policy"
    assert len(client.calls) == 0


def test_source_bound_safety_policy_preempts_unsafe_model_expansion():
    client = FakeLlmClient(_payload())
    safety_policy = load_traps().by_id("SAFETY-RGD-HD-GAS")
    assert safety_policy is not None
    answer = asyncio.run(
        _generator(client).generate(
            "Wasserstoff bei 700 bar mit schnellen Druckwechseln: Welche Dichtung passt?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    safety_policy.correct,
                    "reviewed policy",
                    card_id="SAFETY-RGD-HD-GAS",
                    sources=("ISO 19880-7",),
                    kind="trap",
                ),
                GroundingFact(
                    "Eine doppelte Gleitringdichtung ist eine verfügbare Bauform.",
                    "broad profile",
                    card_id="FK-GLRD-ENGINEERING-PROFILE",
                ),
            ),
            require_evidence_for_all_claims=True,
            work_solution_candidate=True,
            case_revision=7,
        )
    )

    assert answer.text.startswith(
        "Das ist ein sicherheitskritischer Hochdruck-Wasserstofffall."
    )
    assert "RGD/ED" in answer.text
    assert "doppelte Gleitringdichtung" not in answer.text
    assert "HNBR" not in answer.text and "FKM" not in answer.text
    assert answer.text.count("Wasserstoff") == 1
    assert answer.finish_reason == "deterministic_reviewed_policy"
    assert len(client.calls) == 0


def test_safety_lead_is_preserved_when_safety_and_calculation_policies_cofire():
    client = FakeLlmClient(_payload())
    calc = CalcResult(
        computed=(
            ComputedValue(
                calc_id="umfangsgeschwindigkeit",
                name="v_m_s",
                value=14.137,
                unit="m/s",
                stage=1,
                derivation_depth=1,
                formula="pi*d1*n/60000",
                warnings=("grenzwertiger Betriebspunkt",),
            ),
        )
    )
    answer = asyncio.run(
        _generator(client).generate(
            "Wasserstoff-Hochdruckfall an einer rotierenden Welle",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Keine Auswahl ohne sicherheitstechnische Systemfreigabe.",
                    "reviewed safety policy",
                    card_id="SAFETY-RGD-HD-GAS",
                    sources=("safety source",),
                    kind="trap",
                ),
                GroundingFact(
                    "Den Rechenkernbefund exakt übernehmen und nicht als Freigabe behandeln.",
                    "reviewed calculation policy",
                    card_id="CALC-UMFANGSGESCHWINDIGKEIT",
                    sources=("calculation source",),
                    kind="trap",
                ),
            ),
            calc=calc,
            require_evidence_for_all_claims=True,
            case_revision=7,
        )
    )

    assert answer.text.startswith(
        "Das ist ein sicherheitskritischer Hochdruck-Wasserstofffall."
    )
    assert "v_m_s = 14.137 m/s" in answer.text
    assert "grenzwertiger Betriebspunkt" in answer.text


def test_source_bound_speed_policy_preserves_kernel_result_without_material_guess():
    client = FakeLlmClient(_payload())
    calc = CalcResult(
        computed=(
            ComputedValue(
                calc_id="umfangsgeschwindigkeit",
                name="v_m_s",
                value=14.137,
                unit="m/s",
                stage=1,
                derivation_depth=1,
                formula="pi*d1*n/60000",
                warnings=(
                    "Standard-NBR-Lippe ist in diesem Betriebspunkt überfordert",
                ),
                input_origins=("d1_mm=user", "rpm=user"),
            ),
        )
    )
    answer = asyncio.run(
        _generator(client).generate(
            "RWDR mit 45 mm bei 6000 U/min: Welches Material empfiehlst du?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Die Umfangsgeschwindigkeit ausschließlich deterministisch berechnen "
                    "lassen und ohne geerdete Eignung keine alternative Werkstofffamilie "
                    "empfehlen.",
                    "reviewed policy",
                    card_id="CALC-UMFANGSGESCHWINDIGKEIT",
                    sources=("rotary catalogue",),
                    kind="trap",
                ),
            ),
            calc=calc,
            require_evidence_for_all_claims=True,
            work_solution_candidate=True,
            case_revision=7,
        )
    )

    assert answer.text.startswith("Der Rechenkern ergibt:")
    assert (
        "v_m_s = 14.137 m/s (pi*d1*n/60000; Eingaben: d1_mm=user, rpm=user)"
        in answer.text
    )
    assert "Standard-NBR-Lippe ist in diesem Betriebspunkt überfordert" in answer.text
    assert "FKM" not in answer.text
    assert "höher belastbare Lippe" not in answer.text
    assert "ausschließlich deterministisch berechnen" not in answer.text
    assert "**Technische Einordnung**" not in answer.text
    assert "**Fachprüfung erforderlich**" not in answer.text
    assert answer.finish_reason == "deterministic_reviewed_policy"
    assert len(client.calls) == 0


@pytest.mark.parametrize(
    "question",
    (
        "NBR-Wellendichtringe in Synthetiköl mit Ester-Additiven: ist das in Ordnung?",
        "HNBR-O-Ring in einem polyesterhaltigen Synthetiköl: ist das geeignet?",
    ),
)
def test_source_bound_synthetic_oil_policy_stays_generic_without_invented_case_detail(
    question,
):
    client = FakeLlmClient(_payload())
    answer = asyncio.run(
        _generator(client).generate(
            question,
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Die genaue Synthetiköl-Klasse und das Additivpaket müssen vor einer "
                    "Werkstofffreigabe produktbezogen geprüft werden.",
                    "reviewed policy",
                    card_id="POLICY-SYNTHETIKOEL-KLASSE-OFFEN",
                    sources=("material handbook",),
                    kind="trap",
                ),
            ),
            require_evidence_for_all_claims=True,
            case_revision=7,
        )
    )

    assert "Werkstoffwahl" in answer.text
    assert "ausdrücklich offen" in answer.text
    assert "Ölbasis, Additivpaket" in answer.text
    assert "NBR-Wellendichtringe" not in answer.text
    assert "Ester-Additiven" not in answer.text
    assert len(client.calls) == 0


@pytest.mark.parametrize(
    ("policy_id", "question", "expected", "forbidden"),
    (
        (
            "TRAP-FKM-DAMPF",
            "Bitte empfiehl mir ein Material für Wasserdampf.",
            "EPDM (peroxidvernetzt) ist der Dampf-/SIP-Standard",
            "Der entscheidende fachliche Punkt ist",
        ),
        (
            "POLICY-TRINKWASSER-FAMILIE-ZULASSUNG",
            "FFKM hält alles aus, also nehme ich es für Trinkwasser.",
            "produkt- beziehungsweise compoundbezogene Trinkwassernachweis",
            "Belastbar festhalten lässt sich",
        ),
    ),
)
def test_user_facing_policy_is_exact_concise_and_never_calls_model(
    policy_id, question, expected, forbidden
):
    client = FakeLlmClient(_payload())
    policy = load_traps().by_id(policy_id)
    assert policy is not None and policy.sources

    answer = asyncio.run(
        _generator(client).generate(
            question,
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    policy.correct,
                    "reviewed policy",
                    card_id=policy.id,
                    sources=policy.sources,
                    kind="trap",
                ),
            ),
            require_evidence_for_all_claims=True,
            case_revision=7,
        )
    )

    assert expected in answer.text
    assert forbidden not in answer.text
    assert "quellengebunden" not in answer.text
    assert answer.finish_reason == "deterministic_reviewed_policy"
    assert len(client.calls) == 0


def test_broad_knowledge_answer_omits_unrequested_example_values():
    facts = (
        GroundingFact(
            "PTFE besitzt eine niedrige Reibung und ausgeprägte Kriechneigung.",
            "reviewed handbook",
            card_id="PTFE-MECHANISM",
            claim_kind="mechanism",
            answer_facets=("mechanism",),
        ),
        GroundingFact(
            "Ein PTFE-Beispielcompound ist bis 260 °C katalogisiert.",
            "reviewed catalogue",
            card_id="PTFE-EXAMPLE-VALUE",
            claim_kind="example_value",
            answer_facets=("parameters",),
        ),
    )
    broad_client = FakeLlmClient(_payload(evidence_ids=[]))
    broad = asyncio.run(
        _generator(broad_client).generate(
            "Erkläre PTFE bitte ausführlich.",
            flags=Flags(),
            grounding_facts=facts,
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )
    quantitative_client = FakeLlmClient(_payload(evidence_ids=[]))
    quantitative = asyncio.run(
        _generator(quantitative_client).generate(
            "Welche Temperaturbereiche und Kennwerte hat PTFE?",
            flags=Flags(),
            grounding_facts=facts,
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )

    assert "niedrige Reibung" in broad.text
    assert "260 °C" not in broad.text
    assert "omit catalogue ranges" in broad_client.calls[0]["system"].lower()
    assert "260 °C" in quantitative.text


def test_named_standard_must_exist_in_the_cited_evidence():
    payload = json.loads(_payload(evidence_ids=["EV-1"]))
    payload["claims"][0]["text"] = "ISO 99999 bestätigt diese Auslegung."
    client = FakeLlmClient(json.dumps(payload))

    answer = asyncio.run(
        _generator(client).generate(
            "Welcher Dichtungsaufbau passt?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Die Bauform muss gegen den realen Betriebspunkt geprüft werden.",
                    "ledger",
                    card_id="EV-1",
                ),
            ),
            require_evidence_for_all_claims=True,
            case_revision=7,
        )
    )

    assert "ISO 99999" not in answer.text
    assert answer.finish_reason == "deterministic_evidence_fallback"


def test_recommendation_may_not_add_material_absent_from_evidenced_decision_claim():
    payload = json.loads(_payload(evidence_ids=["EV-1"]))
    payload["claims"][0] = {
        "text": "Ein RWDR benötigt einen tragfähigen Schmierfilm.",
        "evidence_ids": ["EV-1"],
        "criticality": "decision_relevant",
    }
    payload["recommendation"] = {
        "summary": "FKM als Primärwerkstoff einsetzen.",
        "status": "conditional",
        "conditions": ["Betriebspunkt prüfen"],
    }
    client = FakeLlmClient(json.dumps(payload))

    answer = asyncio.run(
        _generator(client).generate(
            "Welcher Dichtungsaufbau passt?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Ein RWDR benötigt einen tragfähigen Schmierfilm.",
                    "ledger",
                    card_id="EV-1",
                ),
            ),
            require_evidence_for_all_claims=True,
            case_revision=7,
        )
    )

    assert "FKM als Primärwerkstoff" not in answer.text
    assert answer.finish_reason == "deterministic_evidence_fallback"


def test_unclear_medium_blocks_even_an_evidenced_material_as_recommendation():
    payload = json.loads(_payload(evidence_ids=["EV-1"]))
    payload["conclusion"] = "Die Werkstoffwahl bleibt bis zur Medienklärung offen."
    payload["claims"][0] = {
        "text": "FKM ist eine Elastomerfamilie.",
        "evidence_ids": ["EV-1"],
        "criticality": "decision_relevant",
    }
    payload["recommendation"] = {
        "summary": "FKM als Primärwerkstoff einsetzen.",
        "status": "conditional",
        "conditions": ["Datenblatt prüfen"],
    }
    client = FakeLlmClient(json.dumps(payload))

    answer = asyncio.run(
        _generator(client).generate(
            "Synthetisches Öl, genaue Sorte unbekannt: Welcher Werkstoff passt?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "FKM ist eine Elastomerfamilie.",
                    "ledger",
                    card_id="EV-1",
                ),
            ),
            baseline_hardening=True,
            require_evidence_for_all_claims=True,
            case_revision=7,
        )
    )

    assert "FKM als Primärwerkstoff einsetzen" not in answer.text
    assert answer.finish_reason == "deterministic_evidence_fallback"


def test_rwdr_fallback_surfaces_kernel_value_and_discriminating_inputs():
    client = FakeLlmClient(_payload(evidence_ids=[]))
    calc = CalcResult(
        computed=(
            ComputedValue(
                calc_id="umfangsgeschwindigkeit",
                name="v_m_s",
                value=3.534,
                unit="m/s",
                stage=1,
                derivation_depth=1,
                formula="pi*d*n/60",
                warnings=("grenzwertige Auslegung; Temperatur bestimmt die Reserve",),
            ),
        )
    )
    answer = asyncio.run(
        _generator(client).generate(
            "RWDR 45 mm bei 1500 U/min technisch vorprüfen",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Ein RWDR benötigt einen tragfähigen Schmierfilm.",
                    "ledger",
                    card_id="FK-RWDR-ENGINEERING-PROFILE",
                ),
            ),
            calc=calc,
            require_evidence_for_all_claims=True,
            case_revision=7,
        )
    )
    assert "v_m_s = 3.534 m/s" in answer.text
    assert "grenzwertige Auslegung" in answer.text
    assert "Wellenhärte, Rauheit und Drallfreiheit" in answer.text
    assert "Druckdifferenz einschließlich Druckspitzen" in answer.text
    assert answer.finish_reason == "deterministic_evidence_fallback"
    assert len(client.calls) == 2


def test_compact_technical_answer_caps_first_turn_density_deterministically():
    payload = json.loads(_payload())
    payload["conclusion"] = "Technische Einordnung."
    payload["assumptions"] = ["a", "b"]
    payload["missing_information"] = ["m1", "m2", "m3", "m4", "m5"]
    payload["claims"] = [
        {
            "text": f"claim {index}",
            "evidence_ids": ["EV-1"],
            "criticality": "decision_relevant" if index == 4 else "supporting",
        }
        for index in range(5)
    ]
    payload["recommendation"] = {
        "summary": "Prüfpfad",
        "status": "conditional",
        "conditions": ["c1", "c2", "c3", "c4"],
    }
    client = FakeLlmClient(json.dumps(payload))

    answer = asyncio.run(
        _generator(client).generate(
            "RWDR-Fall",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "claim 0 claim 1 claim 2 claim 3 claim 4",
                    "ledger",
                    card_id="EV-1",
                ),
            ),
            require_evidence_for_all_claims=True,
            compact_technical_answer=True,
            case_revision=7,
        )
    )

    assert "claim 4" in answer.text
    assert answer.text.count("quellengebunden") == 3
    assert "m4" not in answer.text and "m5" not in answer.text
    assert "c3" not in answer.text and "c4" not in answer.text
    assert "**Annahmen**" not in answer.text


def test_diagnostic_evidence_preempts_model_and_uses_one_governed_question():
    payload = json.loads(_payload())
    payload["conclusion"] = (
        "Grenze zuerst den Versagenspfad ein; ein Werkstoffwechsel allein löst die "
        "Ursache nicht."
    )
    payload["assumptions"] = ["unbelegte Annahme"]
    payload["missing_information"] = ["m1", "m2", "m3", "m4"]
    payload["claims"] = [
        {
            "text": f"diagnostic claim {index}",
            "evidence_ids": ["EV-1"],
            "criticality": "supporting",
        }
        for index in range(5)
    ]
    payload["recommendation"] = {
        "summary": "FKM einsetzen.",
        "status": "conditional",
        "conditions": ["c1", "c2", "c3"],
    }
    client = FakeLlmClient(json.dumps(payload))
    communication_plan = build_communication_plan(
        question="Der Wellendichtring ist undicht. Was soll ich prüfen?",
        route_name="leakage_troubleshooting",
    )
    answer = asyncio.run(
        _generator(client).generate(
            "Der Wellendichtring ist undicht. Was soll ich prüfen?",
            flags=Flags(),
            grounding_facts=tuple(
                GroundingFact(
                    f"diagnostic claim {index}",
                    "ledger",
                    card_id=f"EV-{index}",
                )
                for index in range(5)
            ),
            communication_plan=communication_plan.to_dict(),
            require_evidence_for_all_claims=True,
            compact_technical_answer=True,
            case_revision=7,
        )
    )

    assert answer.text.count("diagnostic claim") == 1
    assert "FKM einsetzen" not in answer.text
    assert "**Annahmen**" not in answer.text
    assert "**Technische Einordnung**" not in answer.text
    assert communication_plan.next_question in answer.text
    assert answer.finish_reason == "deterministic_diagnostic_evidence"
    assert len(client.calls) == 0


def test_hardened_nbr_diagnostic_prefers_thermal_and_oil_evidence():
    client = FakeLlmClient(_payload())
    question = "Der NBR-RWDR ist hart und rissig. Was tun?"
    communication_plan = build_communication_plan(
        question=question,
        route_name="leakage_troubleshooting",
    )
    thermal = (
        "NBR liegt bei erhöhter Dauertemperatur an seiner Grenze; dauerhaft darüber "
        "drohen Verhärtung und Versprödung."
    )
    oil = "Synthetiköle und Additive können NBR zusätzlich angreifen."
    answer = asyncio.run(
        _generator(client).generate(
            question,
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    thermal,
                    "ledger",
                    card_id="FK-NBR-DAUERTEMP",
                    claim_id="FK-NBR-DAUERTEMP:0",
                    answer_facets=("limits", "failure_modes"),
                ),
                GroundingFact(
                    oil,
                    "ledger",
                    card_id="FK-NBR-DAUERTEMP",
                    claim_id="FK-NBR-DAUERTEMP:2",
                    answer_facets=("media_compatibility", "limits"),
                ),
                GroundingFact(
                    "Ein allgemeines RWDR-Profil.",
                    "ledger",
                    card_id="FK-RWDR-ENGINEERING-PROFILE",
                    claim_id="FK-RWDR-ENGINEERING-PROFILE:0",
                    answer_facets=("failure_modes",),
                ),
            ),
            communication_plan=communication_plan.to_dict(),
            require_evidence_for_all_claims=True,
            compact_technical_answer=True,
            case_revision=7,
        )
    )

    assert "passt vorläufig zu thermischer Alterung" in answer.text
    assert thermal in answer.text and oil in answer.text
    assert "allgemeines RWDR-Profil" not in answer.text
    assert communication_plan.next_question in answer.text
    assert len(client.calls) == 0


def test_replacement_identification_without_dedicated_evidence_fails_bounded():
    client = FakeLlmClient(_payload())
    question = "Wie finde ich Ersatz für die kaputte Wellendichtung ohne Code am Altteil?"
    communication_plan = build_communication_plan(
        question=question,
        route_name="engineering_case",
    )
    unrelated = "Allgemeiner Hinweis zu einer Wellendichtung."
    answer = asyncio.run(
        _generator(client).generate(
            question,
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    unrelated,
                    "ledger",
                    card_id="FK-RWDR-ENGINEERING-PROFILE",
                    claim_id="FK-RWDR-ENGINEERING-PROFILE:0",
                    answer_facets=("definition",),
                ),
            ),
            communication_plan=communication_plan.to_dict(),
            require_evidence_for_all_claims=True,
            compact_technical_answer=True,
            case_revision=7,
        )
    )

    assert "noch nicht belastbar identifizieren" in answer.text
    assert "Ja – auch ohne lesbaren Code" not in answer.text
    assert unrelated not in answer.text
    assert communication_plan.next_question in answer.text
    assert len(client.calls) == 0


def test_diagnostic_fallback_prefers_case_lexical_relevance_over_generic_failure_card():
    client = FakeLlmClient(_payload())
    question = (
        "Der gleiche RWDR leckt im Rührwerk ständig, im baugleichen Getriebe nie."
    )
    communication_plan = build_communication_plan(
        question=question,
        route_name="leakage_troubleshooting",
    )
    answer = asyncio.run(
        _generator(client).generate(
            question,
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Allgemeine Ausfälle können durch Temperatur oder Montage entstehen.",
                    "ledger",
                    card_id="GENERIC-FAILURE",
                    answer_facets=("failure_modes",),
                ),
                GroundingFact(
                    "Beim Rührwerk können Rundlauf und Wellenauslenkung stärker als im Getriebe "
                    "sein und den dynamischen Lippenkontakt des RWDR unterbrechen.",
                    "ledger",
                    card_id="APPLICATION-CONTRAST",
                    answer_facets=("mechanism", "design_interfaces"),
                ),
            ),
            communication_plan=communication_plan.to_dict(),
            require_evidence_for_all_claims=True,
            compact_technical_answer=True,
            case_revision=7,
        )
    )

    assert "Beim Rührwerk können Rundlauf" in answer.text
    assert "Allgemeine Ausfälle" not in answer.text
    assert communication_plan.next_question in answer.text
    assert len(client.calls) == 0


def test_generic_diagnostic_prefers_failure_mode_over_lexical_design_detail():
    client = FakeLlmClient(_payload())
    question = "Der Wellendichtring am Getriebe ist undicht."
    communication_plan = build_communication_plan(
        question=question,
        route_name="leakage_troubleshooting",
    )
    answer = asyncio.run(
        _generator(client).generate(
            question,
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Wellendichtring und Getriebe benötigen eine definierte Laufspur.",
                    "ledger",
                    card_id="DESIGN-DETAIL",
                    answer_facets=("design_interfaces",),
                ),
                GroundingFact(
                    "Zuerst sind Montage, Schmierung, thermische Schädigung und Rundlauf als "
                    "mögliche Versagenspfade zu trennen.",
                    "ledger",
                    card_id="FAILURE-MODES",
                    answer_facets=("failure_modes",),
                ),
            ),
            communication_plan=communication_plan.to_dict(),
            require_evidence_for_all_claims=True,
            compact_technical_answer=True,
            case_revision=7,
        )
    )

    assert "Zuerst sind Montage" in answer.text
    assert "definierte Laufspur" not in answer.text
    assert len(client.calls) == 0


def test_dynamic_tightness_target_uses_evidence_bound_tradeoff_without_model_call():
    client = FakeLlmClient(_payload())
    question = "Maximale Dichtheit an der Welle, Leckage null – was ist optimal?"
    communication_plan = build_communication_plan(
        question=question,
        route_name="engineering_case",
    )
    answer = asyncio.run(
        _generator(client).generate(
            question,
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Die Dichtkante benötigt einen tragfähigen Schmierfilm; radiale "
                    "Lippenkraft beeinflusst Reibung, Wärmeeintrag und Verlustleistung.",
                    "reviewed rwdr profile",
                    card_id="FK-RWDR-ENGINEERING-PROFILE",
                    claim_id="rwdr-film",
                    answer_facets=("mechanism", "tradeoffs"),
                ),
                GroundingFact(
                    "Bei einer Gleitringdichtung sind kontrollierte mikroskopische Leckage "
                    "und Wärmeabfuhr Teil des Funktionsprinzips.",
                    "reviewed glrd profile",
                    card_id="FK-GLRD-ENGINEERING-PROFILE",
                    claim_id="glrd-film",
                    answer_facets=("mechanism", "operating_factors"),
                ),
            ),
            communication_plan=communication_plan.to_dict(),
            require_evidence_for_all_claims=True,
            work_solution_candidate=True,
            case_revision=7,
        )
    )

    assert "physikalisch kaum erreichbar" in answer.text
    assert "kein einzelnes Optimum" in answer.text
    assert "Schmierfilm" in answer.text and "Reibung" in answer.text
    assert communication_plan.next_question in answer.text
    assert answer.finish_reason == "deterministic_tradeoff_evidence"
    assert len(client.calls) == 0


def test_knowledge_answer_drops_redundant_recommendation_block():
    payload = json.loads(_payload(evidence_ids=["E1"]))
    payload["recommendation"] = {
        "summary": "PTFE nur nach Prüfung einsetzen.",
        "status": "provisional",
        "conditions": ["Herstellerprüfung"],
    }
    payload["needs_human_review"] = True
    client = FakeLlmClient(json.dumps(payload))

    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(GroundingFact("fact", "ledger", card_id="EV-1"),),
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )

    assert "Vorläufige Orientierung" not in answer.text
    assert "PTFE nur nach Prüfung einsetzen" not in answer.text
    assert "Fachprüfung erforderlich" not in answer.text


def test_knowledge_answer_supplements_missing_claim_level_facet_coverage():
    plan = _knowledge_plan()
    plan["sections"] = [
        {
            "heading": "Kennwerte",
            "instruction": "Definition und Parameter abdecken.",
            "facets": ["definition", "parameters"],
            "covered_facets": ["definition", "parameters"],
            "missing_facets": [],
        }
    ]
    client = FakeLlmClient(_payload(evidence_ids=["E1"]))
    facts = (
        GroundingFact(
            "PTFE definition",
            "ledger",
            card_id="FK-PTFE",
            answer_facets=("definition",),
            claim_id="claim-definition",
        ),
        GroundingFact(
            "PTFE parameter",
            "ledger",
            card_id="FK-PTFE",
            answer_facets=("parameters",),
            claim_id="claim-parameters",
        ),
    )

    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=facts,
            knowledge_answer_plan=plan,
            case_revision=7,
        )
    )

    assert len(client.calls) == 1
    assert (
        "Evidence ownership: E1=>subject[PTFE];facets[definition]"
        in client.calls[0]["system"]
    )
    assert "[Evidenz-ID: E1]" in client.calls[0]["system"]
    assert "claim-definition" not in client.calls[0]["system"]
    assert "EV-1" not in client.calls[0]["system"]
    assert "PTFE definition" in answer.text
    assert "PTFE parameter" in answer.text


def test_knowledge_answer_hides_canonical_uuid_behind_short_alias():
    canonical_id = "7cf25557-4816-5ec1-b8f7-03cf5346e587"
    client = FakeLlmClient(_payload(evidence_ids=["E1"]))
    fact = GroundingFact(
        "PTFE definition",
        "ledger",
        card_id="FK-PTFE-ENGINEERING-PROFILE",
        claim_id=canonical_id,
    )

    answer = asyncio.run(
        _generator(client).generate(
            "Erkläre PTFE.",
            flags=Flags(),
            grounding_facts=(fact,),
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )

    assert (
        "Evidence ownership: E1=>subject[PTFE];facets[none]"
        in client.calls[0]["system"]
    )
    assert canonical_id not in client.calls[0]["system"]
    assert answer.grounding_facts == (fact,)


def test_second_semantic_failure_stops_without_retry_loop():
    client = ScriptedFakeLlmClient(
        [_payload(evidence_ids=["BAD-1"]), _payload(evidence_ids=["BAD-2"])]
    )
    with pytest.raises(TechnicalAnswerValidationError):
        asyncio.run(
            _generator(client).generate(
                "Was ist PTFE?",
                flags=Flags(),
                grounding_facts=(GroundingFact("fact", "ledger", card_id="EV-1"),),
                case_revision=7,
            )
        )
    assert len(client.calls) == 2


def test_human_review_calibrates_unsupported_decisions_to_provisional():
    payload = json.loads(_payload(evidence_ids=[]))
    payload["claims"][0]["criticality"] = "decision_relevant"
    payload["recommendation"] = {
        "summary": "Werkstoff nur nach Prüfung einsetzen.",
        "status": "conditional",
        "conditions": ["Herstellerprüfung"],
    }
    payload["needs_human_review"] = True
    answer = TechnicalAnswer.model_validate(payload)

    calibrated = calibrate_technical_answer(answer)

    assert calibrated.claims[0].criticality == "supporting"
    assert calibrated.recommendation.status == "provisional"
    validate_technical_answer(
        calibrated, case_revision=7, allowed_evidence_ids=frozenset()
    )


def test_unsupported_decision_forces_conservative_human_review():
    payload = json.loads(_payload(evidence_ids=[]))
    payload["claims"][0]["criticality"] = "decision_relevant"
    answer = TechnicalAnswer.model_validate(payload)

    calibrated = calibrate_technical_answer(answer)

    assert calibrated.needs_human_review is True
    assert calibrated.claims[0].criticality == "supporting"
    assert calibrated.conclusion.startswith(
        "Vorläufige Einordnung ohne belastbaren Beleg:"
    )
    validate_technical_answer(
        calibrated, case_revision=7, allowed_evidence_ids=frozenset()
    )


def test_structured_answer_contract_caps_chat_density():
    schema = TechnicalAnswer.model_json_schema()
    props = schema["properties"]
    assert props["assumptions"]["maxItems"] == 6
    assert props["missing_information"]["maxItems"] == 6
    assert props["claims"]["maxItems"] == 8
