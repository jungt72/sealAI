"""INC-NARRATOR-CONTRACT Phase 4 — the measurement ruler (no model, no tokens).

Validates the harness + the §5 metric functions: the curated reference renders must PASS the guard
(overblock 0) and each contract status must match expect_status; the metrics compute correctly over
synthetic clean/leaky samples; the model harness works with an injected stub render_fn.
"""

from sealai_v2.eval.calibration import (
    overblock_rate,
    required_clause_miss_rate,
    unsupported_claim_rate,
)
from sealai_v2.eval.contract_eval import (
    CONTRACT_EVAL_CASES,
    contract_for_case,
    evaluate_model_over_cases,
    seed_overblock_report,
)

_REF = {c["question"]: c["reference_render"] for c in CONTRACT_EVAL_CASES}


def test_reference_renders_all_pass_the_guard_and_statuses_match():
    rep = seed_overblock_report()
    assert rep["status_mismatch"] == [], rep["status_mismatch"]
    assert rep["overblock"]["overblock_rate"] == 0.0, rep["per_case"]
    assert rep["n_cases"] == len(CONTRACT_EVAL_CASES)


def test_unsupported_claim_rate_clean_vs_leaky():
    case = CONTRACT_EVAL_CASES[0]  # grounded-disqualify
    contract = contract_for_case(case)
    clean = {
        "answer": case["reference_render"],
        "contract": contract,
        "known_values": case["known_values"],
    }
    leaky = {
        "answer": case["reference_render"] + " Dauerhaft sind 250 °C unkritisch.",
        "contract": contract,
        "known_values": case["known_values"],
    }
    assert unsupported_claim_rate([clean])["unsupported_rate"] == 0.0
    assert unsupported_claim_rate([clean])["schranken_quota"] == 1.0
    r = unsupported_claim_rate([leaky])
    assert r["unsupported"] == 1 and r["schranken_quota"] == 0.0


def test_required_clause_miss_rate():
    case = CONTRACT_EVAL_CASES[
        1
    ]  # grounded-compatible (has the COVERED_RECOMMENDATION clause)
    contract = contract_for_case(case)
    miss = {
        "answer": "NBR ist gegen Mineralöl beständig.",
        "contract": contract,
    }  # clause dropped
    assert required_clause_miss_rate([miss])["misses"] == 1
    keep = {"answer": case["reference_render"], "contract": contract}
    assert required_clause_miss_rate([keep])["misses"] == 0


def test_overblock_rate_zero_on_references():
    samples = [
        {
            "answer": c["reference_render"],
            "contract": contract_for_case(c),
            "known_values": c.get("known_values", []),
        }
        for c in CONTRACT_EVAL_CASES
    ]
    assert overblock_rate(samples)["overblock_rate"] == 0.0


def test_model_harness_with_perfect_and_leaky_stub():
    def perfect(question, contract):
        return _REF[question]

    def leaky(question, contract):
        return "Dauerhaft sind 120 °C kein Problem; das passt hier bestens."

    good = evaluate_model_over_cases(perfect)
    assert good["unsupported"]["unsupported_rate"] == 0.0
    assert good["required_clause_miss"]["misses"] == 0

    bad = evaluate_model_over_cases(leaky)
    assert bad["unsupported"]["unsupported_rate"] > 0.0


def test_empty_samples_are_none_not_crash():
    assert unsupported_claim_rate([])["schranken_quota"] is None
    assert required_clause_miss_rate([])["schranken_quota"] is None
    assert overblock_rate([])["overblock_rate"] is None
