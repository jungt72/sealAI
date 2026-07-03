"""P0-B targeted eval — the offline overblock measurement for ``response_contract_general_guard_enabled``
(audit Leitbild-V3, L1-Scope-Leak/P0-2). Mirrors ``eval/contract_eval.py``'s structure exactly, but drives
``response_contract.build_guard_contract()`` + ``output_guard.evaluate_render(check_sentence_coverage=False)``
— the code path P0-B actually wires for non-Gegencheck (general-knowledge) turns — instead of
``build_contract()``'s Gegencheck-shaped contract.

Grounding content is NOT invented: every case's grounding facts are VERBATIM claim texts from the 9
reviewed Fachkarten already live in prod (FK-ORING-VERPRESSUNG / FK-PTFE-KALTFLUSS / FK-FOODGRADE-FETT /
FK-NBR-DAUERTEMP / FK-VMQ-DYNAMISCH / FK-NBR-OZON) — this eval measures the guard against the ACTUAL
knowledge base, not a hypothetical one.

Two case sets:
  - ``GENERAL_GUARD_EVAL_CASES`` — realistic legitimate answers (paraphrase/cite ONLY what the grounding
    facts already textually support — including alternative materials/numbers the claims themselves
    name, which become part of the contract's allowed_materials/allowed_values). Runs ``NO model, NO
    tokens`` — this IS the overblock_rate measurement the owner reviews.
  - ``GENERAL_GUARD_KNOWN_LIMITATION_CASES`` — realistic answers that step genuinely OUTSIDE the grounded
    vocabulary (a comparison material never named in the grounding/question, an illustrative number never
    grounded/computed, a hedge phrase on the forbidden list). Documented separately, NOT counted into
    overblock_rate — these are expected to BLOCK, and this eval's job is to confirm they still do (the
    guard is not a no-op) and to give the owner concrete, reproducible examples of exactly where the
    guard's conservatism costs UX, instead of a vague "it might overblock sometimes".
"""

from __future__ import annotations

from sealai_v2.core.contracts import CalcResult, ComputedValue, GroundingFact
from sealai_v2.core.output_guard import evaluate_render, known_inputs
from sealai_v2.core.response_contract import build_guard_contract


def _gf(text: str, card_id: str) -> dict:
    return {
        "text": text,
        "quelle": "Fachkarte (reviewed)",
        "card_id": card_id,
        "kind": "card",
    }


# ── verbatim reviewed-claim grounding, pulled 2026-07-03 from the live seed (fachkarten_seed.json) ──

_ORING_VERPRESSUNG = [
    _gf(
        "Die typische statische radiale Verpressung eines O-Rings liegt bei ~15–25 % der Schnurstärke "
        "(Richtwert); dynamisch geringer.",
        "FK-ORING-VERPRESSUNG",
    ),
    _gf(
        "Die Nutfüllung so auslegen, dass Platz für Wärmedehnung und Quellung bleibt — Füllgrad "
        "typischerweise max. ~75–90 %.",
        "FK-ORING-VERPRESSUNG",
    ),
    _gf(
        "Die geeignete Verpressung hängt von Schnurstärke, Medium (Quellung) und Temperatur ab; es sind "
        "Richtwerte/Bereiche — keine Scheingenauigkeit. Gegen Nut-Auslegungsnorm bzw. Herstellertabelle "
        "verifizieren.",
        "FK-ORING-VERPRESSUNG",
    ),
]

_PTFE_KALTFLUSS = [
    _gf(
        "Ein reiner PTFE-O-Ring dichtet statisch unzuverlässig: Kaltfluss/Kriechen unter Dauerlast, keine "
        "elastische Rückstellung.",
        "FK-PTFE-KALTFLUSS",
    ),
    _gf(
        "Chemische Beständigkeit ist nicht gleich mechanische Eignung.",
        "FK-PTFE-KALTFLUSS",
    ),
    _gf(
        "Lösungen: federvorgespannte PTFE-Dichtung, FEP/PFA-ummantelter O-Ring (Elastomerkern) oder "
        "PTFE-Compound.",
        "FK-PTFE-KALTFLUSS",
    ),
]

_FOODGRADE_FETT = [
    _gf(
        "'food-grade' bedeutet nicht 'für jedes Lebensmittel geeignet': fetthaltige Lebensmittel (z. B. "
        "Schokolade/Kakaobutter) lassen EPDM quellen.",
        "FK-FOODGRADE-FETT",
    ),
    _gf(
        "Für fetthaltige Lebensmittel: food-grade FKM, VMQ oder FFKM mit Zulassung (FDA 21 CFR / EG "
        "1935/2004).",
        "FK-FOODGRADE-FETT",
    ),
    _gf(
        "VMQ bietet nur moderate Fettbeständigkeit; FKM und FFKM sind für fetthaltige Medien deutlich "
        "stärker.",
        "FK-FOODGRADE-FETT",
    ),
]

_NBR_DAUERTEMP = [
    _gf(
        "NBR liegt bei etwa 100–120 °C an der Dauertemperaturgrenze; dauerhaft darüber (z. B. 130 °C) "
        "drohen Verhärtung, Versprödung und kürzere Lebensdauer.",
        "FK-NBR-DAUERTEMP",
    ),
    _gf("Bei höherer Dauertemperatur: HNBR oder FKM.", "FK-NBR-DAUERTEMP"),
]

_VMQ_DYNAMISCH = [
    _gf(
        "VMQ hat schlechte mechanische/abrasive Eigenschaften und geringe Reißfestigkeit und ist daher "
        "für dynamische, schnelldrehende Wellendichtungen ungeeignet.",
        "FK-VMQ-DYNAMISCH",
    ),
    _gf(
        "Der Temperaturbereich allein qualifiziert VMQ nicht; Dynamik und Verschleiß sind limitierend.",
        "FK-VMQ-DYNAMISCH",
    ),
    _gf("Stattdessen FKM oder eine PTFE-Lippe.", "FK-VMQ-DYNAMISCH"),
]

_NBR_OZON = [
    _gf(
        "NBR ist gegen Ozon und UV nicht beständig — es kommt zur Rissbildung bei Außeneinsatz.",
        "FK-NBR-OZON",
    ),
    _gf("EPDM oder HNBR sind witterungsbeständiger.", "FK-NBR-OZON"),
]


def _calc(calc_id: str, name: str, value: float, unit: str) -> CalcResult:
    return CalcResult(
        computed=(
            ComputedValue(
                calc_id=calc_id,
                name=name,
                value=value,
                unit=unit,
                stage=1,
                derivation_depth=1,
                formula="—",
                source="Kernel",
            ),
        )
    )


GENERAL_GUARD_EVAL_CASES = (
    {
        "id": "oring-verpressung-explainer",
        "question": "Wie stark sollte ich einen O-Ring in der Nut verpressen?",
        "grounding": _ORING_VERPRESSUNG,
        "reference_render": (
            "Die statische radiale Verpressung liegt als Richtwert bei ca. 15–25 % der Schnurstärke, "
            "dynamisch etwas weniger. Die Nutfüllung sollte höchstens ~75–90 % betragen, damit noch Platz "
            "für Wärmedehnung und Quellung bleibt. Der genaue Wert hängt von Schnurstärke, Medium und "
            "Temperatur ab — bitte gegen Nut-Auslegungsnorm oder Herstellertabelle verifizieren."
        ),
    },
    {
        "id": "ptfe-static-sealing-explainer",
        "question": "Kann ich einen reinen PTFE-O-Ring statisch einsetzen?",
        "grounding": _PTFE_KALTFLUSS,
        "reference_render": (
            "Ein reiner PTFE-O-Ring ist statisch riskant: Kaltfluss/Kriechen unter Dauerlast, und die "
            "elastische Rückstellung fehlt weitgehend — chemische Beständigkeit ist eben nicht dasselbe "
            "wie mechanische Eignung. Üblich sind stattdessen eine federvorgespannte PTFE-Dichtung, ein "
            "FEP/PFA-ummantelter O-Ring mit Elastomerkern, oder ein PTFE-Compound."
        ),
    },
    {
        "id": "foodgrade-explainer",
        "question": "Was bedeutet food-grade bei Dichtungswerkstoffen?",
        "grounding": _FOODGRADE_FETT,
        "reference_render": (
            "'food-grade' heißt nicht automatisch 'für jedes Lebensmittel geeignet' — fetthaltige "
            "Lebensmittel wie Schokolade oder Kakaobutter lassen EPDM zum Beispiel quellen. Für "
            "fetthaltige Medien braucht es food-grade FKM, VMQ oder FFKM mit passender Zulassung (FDA 21 "
            "CFR bzw. EG 1935/2004) — wobei VMQ nur moderat fettbeständig ist, FKM und FFKM deutlich "
            "stärker."
        ),
    },
    {
        "id": "nbr-temp-explainer",
        "question": "Bis zu welcher Temperatur kann ich NBR dauerhaft einsetzen?",
        "grounding": _NBR_DAUERTEMP,
        "reference_render": (
            "NBR liegt bei etwa 100–120 °C an seiner Dauertemperaturgrenze. Dauerhaft darüber, "
            "beispielsweise bei 130 °C, drohen Verhärtung, Versprödung und eine kürzere Lebensdauer. Für "
            "höhere Dauertemperaturen sind HNBR oder FKM die bessere Wahl."
        ),
    },
    {
        "id": "vmq-dynamic-explainer",
        "question": "Ist Silikon (VMQ) für eine schnelldrehende Wellendichtung geeignet?",
        "grounding": _VMQ_DYNAMISCH,
        "reference_render": (
            "VMQ hat schlechte mechanische und abrasive Eigenschaften sowie eine geringe Reißfestigkeit "
            "und ist deshalb für dynamische, schnelldrehende Wellendichtungen ungeeignet. Der "
            "Temperaturbereich allein qualifiziert VMQ hier nicht — Dynamik und Verschleiß sind "
            "limitierend. Üblicherweise kommt stattdessen FKM oder eine PTFE-Lippe zum Einsatz."
        ),
    },
    {
        "id": "nbr-ozon-diagnose-style",
        "question": "Meine NBR-Dichtung ist im Freien verbaut und zeigt Risse, woran liegt das?",
        "grounding": _NBR_OZON,
        "reference_render": (
            "Das passt zum bekannten Bild: NBR ist gegen Ozon und UV im Außeneinsatz nicht beständig, es "
            "kommt zur Rissbildung. Witterungsbeständiger sind EPDM oder HNBR."
        ),
    },
    {
        "id": "calc-only-umfangsgeschwindigkeit",
        "question": "Wie schnell dreht sich meine Welle an der Dichtkante bei 3000 U/min und 40 mm "
        "Durchmesser?",
        "grounding": [],
        "calc": _calc("umfangsgeschwindigkeit", "v_m_s", 6.283, "m/s"),
        "reference_render": "Die Umfangsgeschwindigkeit an der Dichtkante beträgt 6.283 m/s.",
    },
    {
        "id": "calc-only-pv-wert",
        "question": "Wie hoch ist der PV-Wert bei 5 bar und 10 m/s?",
        "grounding": [],
        "calc": _calc("pv_wert", "pv", 50.0, "bar·m/s"),
        "reference_render": "Der PV-Wert liegt bei 50.0 bar·m/s.",
    },
    {
        "id": "no-grounding-no-calc-open-question",
        "question": "Was ist eine Gleitringdichtung, ganz allgemein?",
        "grounding": [],
        "calc": None,
        "reference_render": (
            "Eine Gleitringdichtung dichtet eine rotierende Welle gegenüber einem Gehäuse über zwei "
            "aufeinander gleitende, plangeschliffene Ringe ab — meist bei Pumpen oder Rührwerken."
        ),
    },
    {
        "id": "richtwert-word-is-exempt-when-grounded",
        "question": "Gibt es einen Richtwert für die O-Ring-Verpressung?",
        "grounding": _ORING_VERPRESSUNG,
        "reference_render": (
            "Ja, als Richtwert gelten ~15–25 % der Schnurstärke bei statischer radialer Verpressung — "
            "aber es sind eben Richtwerte, keine Scheingenauigkeit; gegen die Herstellertabelle "
            "verifizieren."
        ),
    },
)


GENERAL_GUARD_KNOWN_LIMITATION_CASES = (
    {
        "id": "comparison-material-not-grounded",
        "question": "Was ist PTFE als Dichtungswerkstoff?",
        "grounding": _PTFE_KALTFLUSS,
        "reference_render": (
            "PTFE ist chemisch extrem beständig, neigt als reiner O-Ring aber zu Kaltfluss. Im Vergleich "
            "zu FKM ist PTFE chemisch universeller einsetzbar, aber mechanisch schwächer."
        ),
        "expected_violation_kind": "invented_material",
        "note": "FKM wird zum Vergleich genannt, ist aber weder in der Frage noch in der Grundierung "
        "vorhanden — bekannte Grenze: ein spontaner Vergleichswerkstoff blockt, auch wenn er fachlich "
        "korrekt und harmlos ist.",
    },
    {
        "id": "illustrative-number-not-grounded",
        "question": "Welche Härte hat ein typischer FKM O-Ring?",
        "grounding": [
            _gf(
                "FKM gegen Heißdampf: unverträglich (Hydrolyse); EPDM ist der Dampf-Standard.",
                "FK-FKM-DAMPF",
            )
        ],
        "reference_render": "FKM-Compounds liegen meist im Bereich 70-90 Shore A.",
        "expected_violation_kind": "invented_number",
        "note": "Ein branchenüblicher Härte-Richtwert (70-90 Shore A) ist weder berechnet noch in der "
        "Grundierung genannt — bekannte Grenze: allgemeines Fachwissen ohne konkreten Beleg blockt.",
    },
    {
        "id": "forbidden-hedge-word",
        "question": "Wie stark sollte ich einen O-Ring in der Nut verpressen?",
        "grounding": _ORING_VERPRESSUNG,
        "reference_render": "Erfahrungsgemäß liegt die Verpressung bei 15-25 % der Schnurstärke.",
        "expected_violation_kind": "forbidden_phrase",
        "note": "'Erfahrungsgemäß' steht auf der FORBIDDEN_ALWAYS-Liste (Fabrikations-Marker) — auch wenn "
        "die genannte Zahl selbst grundiert/gedeckt ist, blockt die Formulierung.",
    },
)


def _score(case: dict) -> dict:
    facts = tuple(GroundingFact(**g) for g in case.get("grounding", ()))
    contract = build_guard_contract(grounding_facts=facts, calc=case.get("calc"))
    contract_dict = contract.to_dict() if contract is not None else None
    known_values, known_materials = known_inputs(case["question"])
    if contract_dict is None:
        return {
            "id": case["id"],
            "contract_built": False,
            "action": "PASS",
            "violations": [],
        }
    g = evaluate_render(
        answer_text=case["reference_render"],
        contract=contract_dict,
        known_values=known_values,
        known_materials=known_materials,
        check_sentence_coverage=False,
    )
    return {
        "id": case["id"],
        "contract_built": True,
        "action": g.action,
        "violations": [v.to_dict() for v in g.violations],
    }


def seed_general_guard_overblock_report() -> dict:
    """NO model, NO tokens. Overblock rate over realistic, grounded-content-based legitimate answers
    (the number the owner reviews) + a precision check over the documented known-limitation cases
    (confirms the guard still catches what it should — not counted into overblock_rate)."""
    main = [_score(c) for c in GENERAL_GUARD_EVAL_CASES]
    blocked = [r for r in main if r["action"] == "BLOCK"]
    limitation = [_score(c) for c in GENERAL_GUARD_KNOWN_LIMITATION_CASES]
    limitation_confirmed = [
        r
        for r, c in zip(limitation, GENERAL_GUARD_KNOWN_LIMITATION_CASES)
        if r["action"] == "BLOCK"
        and any(v["kind"] == c["expected_violation_kind"] for v in r["violations"])
    ]
    return {
        "overblock_rate": round(len(blocked) / len(main), 3) if main else None,
        "blocked": len(blocked),
        "n": len(main),
        "unexpected_blocks": [r for r in main if r["action"] == "BLOCK"],
        "per_case": main,
        "known_limitations_confirmed": len(limitation_confirmed),
        "known_limitations_n": len(limitation),
        "known_limitations_detail": limitation,
    }
