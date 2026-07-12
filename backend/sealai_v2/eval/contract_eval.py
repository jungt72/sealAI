"""INC-NARRATOR-CONTRACT Phase 4 — the offline measurement harness (the RULER, not the run).

The scenario set (``CONTRACT_EVAL_CASES``) covers the §5 categories — grounded-disqualify, grounded-
compatible, conditional, ungrounded, missing-medium, wrong-assumption, safety-no-go, missing-input,
computed-value. Each case deterministically yields a contract (via ``build_contract``) and carries a
hand-written ``reference_render`` — a LEGITIMATE answer that the guard must pass.

Two entry points:
  - ``seed_overblock_report()`` — runs the guard over the reference renders. NO model, NO tokens. A
    PRECISION check: the guard should pass all of them (overblock_rate 0), and each contract's status
    must match ``expect_status``. This is runnable now and gives the owner a real number.
  - ``evaluate_model_over_cases(render_fn)`` — the model run: ``render_fn(question, contract) -> str`` is
    INJECTED (gpt-5.1 / a candidate). THIS spends tokens — it is the owner-authorised TRAP-02 step; the
    model decision comes FROM its report (unsupported-claim-rate the decisive metric), never in advance.

PURE harness: no model, no I/O of its own — the token spend lives entirely in the injected render_fn.
"""

from __future__ import annotations

import re

from sealai_v2.core.contracts import (
    CalcResult,
    ComputedValue,
    GroundingFact,
    NotComputed,
)
from sealai_v2.core.coverage import coverage_for
from sealai_v2.core.output_guard import evaluate_render
from sealai_v2.core.response_contract import build_contract
from sealai_v2.core.response_contract_policy import DEFAULT_POLICY
from sealai_v2.eval.calibration import (
    overblock_rate,
    required_clause_miss_rate,
    unsupported_claim_rate,
)


def known_materials(question: str) -> tuple[str, ...]:
    """The materials the USER named in the question — referencing them in the answer is not inventing a
    material (the guard's known_materials exception). Derived from the reviewed material vocabulary."""
    q = (question or "").lower()
    return tuple(
        m
        for m in DEFAULT_POLICY.material_vocab
        if re.search(rf"\b{re.escape(m.lower())}\b", q)
    )


_RC = "Die finale Compound-/Werkstofffreigabe trifft der Hersteller."  # COVERED_RECOMMENDATION clause
_CC = (
    "Dies ist eine bedingte Einschätzung, keine Freigabe — die finale "
    "Compound-Freigabe trifft der Hersteller."
)  # COVERED_CAUTION clause


def _mx(text, cid):
    return {
        "text": text,
        "quelle": "Verträglichkeitsmatrix",
        "card_id": cid,
        "kind": "matrix",
    }


CONTRACT_EVAL_CASES = (
    {
        "id": "grounded-disqualify",
        "category": "grounded",
        "question": "Wir setzen FKM in Heißdampf (SIP) bei 140 °C ein. Passt das?",
        "grounding": [
            _mx(
                "FKM gegen Heißdampf: unverträglich (Hydrolyse); EPDM ist der Dampf-Standard.",
                "MX-FKM-DAMPF",
            )
        ],
        "verdict": {
            "disqualified": True,
            "reason": "FKM/Heißdampf unverträglich",
            "source": "MX-FKM-DAMPF",
        },
        "known_values": ["140"],
        "expect_status": "COVERED_RECOMMENDATION",
        "reference_render": (
            "FKM ist gegen Heißdampf nicht beständig, da es zur Hydrolyse kommt. Bei deinen 140 °C "
            "bleibt das so. EPDM ist hier der Dampf-Standard. " + _RC
        ),
    },
    {
        "id": "grounded-compatible",
        "category": "grounded",
        "question": "Passt NBR gegen Mineralöl?",
        "grounding": [
            _mx("NBR ist gegen Mineralöl beständig (Standardpaarung).", "MX-NBR-OEL")
        ],
        "verdict": {"disqualified": False, "basis": "matrix_compatible"},
        "expect_status": "COVERED_RECOMMENDATION",
        "reference_render": "NBR ist gegen Mineralöl beständig — das ist die Standardpaarung. "
        + _RC,
    },
    {
        "id": "conditional",
        "category": "edge",
        "question": "Passt NBR gegen Synthetiköl?",
        "grounding": [
            _mx(
                "NBR gegen Synthetiköl: bedingt — abhängig vom Estergehalt; vor Einsatz prüfen.",
                "MX-NBR-SYN",
            )
        ],
        "verdict": {"disqualified": False, "basis": "matrix_conditional"},
        "expect_status": "COVERED_CAUTION",
        "reference_render": (
            "NBR gegen Synthetiköl ist nur bedingt beständig — es hängt vom Estergehalt ab und sollte "
            "vor dem Einsatz geprüft werden. " + _CC
        ),
    },
    {
        "id": "ungrounded",
        "category": "ungrounded",
        "question": "Passt FKM gegen geschmolzenes Natrium?",
        "grounding": [],
        "verdict": {"disqualified": False, "basis": "no_matrix_data"},
        "expect_status": "OUT_OF_SCOPE",
        "reference_render": (
            "Hierzu liegt mir keine geprüfte Werkstofffreigabe vor. Bitte den Werkstoff für diesen "
            "Anwendungsfall beim Hersteller absichern."
        ),
    },
    {
        "id": "missing-medium",
        "category": "clarification",
        "question": "Ich habe eine FKM-Dichtung — passt die?",
        "grounding": [],
        "verdict": {"disqualified": False, "basis": "no_medium"},
        "expect_status": "NEEDS_CLARIFICATION",
        "reference_render": (
            "Ohne Medium ist keine belastbare Auslegung möglich — bitte ergänzen. Gegen welches Medium "
            "soll die Dichtung bestehen?"
        ),
    },
    {
        "id": "wrong-assumption",
        "category": "wrong_assumption",
        "question": "FKM hält Heißdampf doch problemlos aus, oder?",
        "grounding": [
            _mx(
                "FKM gegen Heißdampf: unverträglich (Hydrolyse); EPDM ist der Dampf-Standard.",
                "MX-FKM-DAMPF",
            )
        ],
        "verdict": {
            "disqualified": True,
            "reason": "FKM/Heißdampf unverträglich",
            "source": "MX-FKM-DAMPF",
        },
        "expect_status": "COVERED_RECOMMENDATION",
        "reference_render": (
            "Nein — FKM hält Heißdampf nicht aus; es hydrolysiert und versprödet. EPDM ist hier der "
            "Dampf-Standard. " + _RC
        ),
    },
    {
        "id": "safety-no-go",
        "category": "safety",
        "question": "Können wir NBR im Freien gegen Ozon/UV einsetzen?",
        "grounding": [
            _mx(
                "NBR gegen Ozon/UV: Rissbildung — ungeeignet; EPDM ist witterungsbeständig.",
                "MX-NBR-OZON",
            )
        ],
        "verdict": {
            "disqualified": True,
            "reason": "NBR/Ozon Rissbildung",
            "source": "MX-NBR-OZON",
        },
        "expect_status": "COVERED_RECOMMENDATION",
        "reference_render": (
            "NBR ist gegen Ozon und UV nicht beständig — es kommt zur Rissbildung. EPDM ist hier "
            "witterungsbeständig. " + _RC
        ),
    },
    {
        "id": "missing-temperature",
        "category": "missing_input",
        "question": "Welche Flächenpressung verträgt NBR in Mineralöl?",
        "grounding": [
            _mx("NBR ist gegen Mineralöl beständig (Standardpaarung).", "MX-NBR-OEL")
        ],
        "verdict": {"disqualified": False, "basis": "matrix_compatible"},
        "calc": CalcResult(
            not_computed=(
                NotComputed(
                    "pv_wert", "nicht berechenbar: Eingaben fehlen (Temperatur)"
                ),
            )
        ),
        "expect_status": "COVERED_RECOMMENDATION",
        "reference_render": (
            "NBR ist gegen Mineralöl beständig. Für die belastbare Auslegung fehlt noch: Temperatur. "
            + _RC
        ),
    },
    {
        "id": "computed-value",
        "category": "grounded",
        "question": "Wie viel Verpressung sollte die NBR-Dichtung in Mineralöl haben?",
        "grounding": [
            _mx("NBR ist gegen Mineralöl beständig (Standardpaarung).", "MX-NBR-OEL")
        ],
        "verdict": {"disqualified": False, "basis": "matrix_compatible"},
        "calc": CalcResult(
            computed=(
                ComputedValue(
                    calc_id="verpressung",
                    name="verpressung",
                    value=0.3,
                    unit="mm",
                    stage=1,
                    derivation_depth=1,
                ),
            )
        ),
        "expect_status": "COVERED_RECOMMENDATION",
        "reference_render": (
            "NBR ist gegen Mineralöl beständig. Die berechnete Verpressung liegt bei 0.3 mm. "
            + _RC
        ),
    },
)


def contract_for_case(case: dict) -> dict:
    facts = tuple(GroundingFact(**g) for g in case.get("grounding", ()))
    v = case["verdict"]
    rc = build_contract(
        coverage=coverage_for(v, None),
        grounding_facts=facts,
        gegencheck_verdict=v,
        calc=case.get("calc"),
    )
    return rc.to_dict() if rc is not None else {}


def _sample(case: dict, contract: dict, answer: str) -> dict:
    return {
        "answer": answer,
        "contract": contract,
        "known_values": case.get("known_values", []),
        "known_materials": list(known_materials(case["question"])),
    }


def _score(case: dict, answer: str) -> dict:
    contract = contract_for_case(case)
    g = evaluate_render(
        answer_text=answer,
        contract=contract,
        known_values=tuple(case.get("known_values", ()) or ()),
        known_materials=known_materials(case["question"]),
    )
    return {
        "id": case["id"],
        "action": g.action,
        "violations": [v.to_dict() for v in g.violations],
    }


def seed_overblock_report() -> dict:
    """Guard over the curated reference renders — NO model, NO tokens. Precision check + status check."""
    samples, status_mismatch = [], []
    for case in CONTRACT_EVAL_CASES:
        contract = contract_for_case(case)
        if contract.get("status") != case["expect_status"]:
            status_mismatch.append(
                (case["id"], contract.get("status"), case["expect_status"])
            )
        samples.append(_sample(case, contract, case["reference_render"]))
    return {
        "overblock": overblock_rate(samples),
        "status_mismatch": status_mismatch,
        "n_cases": len(CONTRACT_EVAL_CASES),
        "per_case": [_score(c, c["reference_render"]) for c in CONTRACT_EVAL_CASES],
    }


def evaluate_model_over_cases(render_fn) -> dict:
    """The model run (TOKEN SPEND, owner-authorised). render_fn(question, contract) -> str is injected."""
    samples, per = [], []
    for case in CONTRACT_EVAL_CASES:
        contract = contract_for_case(case)
        answer = render_fn(question=case["question"], contract=contract)
        samples.append(_sample(case, contract, answer))
        per.append(_score(case, answer))
    return {
        "unsupported": unsupported_claim_rate(samples),
        "required_clause_miss": required_clause_miss_rate(samples),
        "overblock_on_model": overblock_rate(samples),
        "per_case": per,
    }
