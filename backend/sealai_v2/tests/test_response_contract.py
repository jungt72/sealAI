"""INC-NARRATOR-CONTRACT Phase 1 — the deterministic answer-contract truth table.

Validates the pure assembler over REAL kernel shapes: coverage from the real ``coverage_for`` kernel,
the real gegencheck verdict dicts, real GroundingFact / CalcResult / NotComputed / ComputedValue.
The contract is INERT (Phase 1) — these test the MEASUREMENT/assembly, not any prod behaviour.
"""

from sealai_v2.core.contracts import (
    CalcResult,
    ComputedValue,
    GroundingFact,
    NotComputed,
)
from sealai_v2.core.coverage import coverage_for
from sealai_v2.core.response_contract import (
    STATUS_COVERED_CAUTION,
    STATUS_COVERED_RECOMMENDATION,
    STATUS_GENERAL,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_OUT_OF_SCOPE,
    build_contract,
    build_guard_contract,
)

# ── real gegencheck verdict shapes (core/gegencheck.py) ──────────────────────────────────────────
V_DISQUALIFIED = {
    "disqualified": True,
    "reason": "FKM gegen Heißdampf: unverträglich (Hydrolyse).",
    "source": "MX-FKM-DAMPF",
}
V_COMPATIBLE = {"disqualified": False, "basis": "matrix_compatible"}
V_CONDITIONAL = {"disqualified": False, "basis": "matrix_conditional"}
V_NO_DATA = {"disqualified": False, "basis": "no_matrix_data"}
V_NO_MEDIUM = {"disqualified": False, "basis": "no_medium"}


def _matrix_fact(text="FKM gegen Heißdampf: unverträglich.", cid="MX-FKM-DAMPF"):
    return GroundingFact(
        text=text, quelle="Verträglichkeitsmatrix", card_id=cid, kind="matrix"
    )


def _card_fact(
    text="EPDM ist der peroxidvernetzte Dampf-/SIP-Standard.", cid="CARD-EPDM-1"
):
    return GroundingFact(
        text=text,
        quelle="Fachkarte EPDM",
        card_id=cid,
        sources=("Parker O-Ring Handbook",),
        kind="card",
    )


def _contract(verdict, facts=(), calc=None):
    return build_contract(
        coverage=coverage_for(verdict, None),
        grounding_facts=tuple(facts),
        gegencheck_verdict=verdict,
        calc=calc,
    )


# ── status mapping (coverage -> contract) ────────────────────────────────────────────────────────


def test_disqualified_is_covered_recommendation_grounded_no():
    c = _contract(V_DISQUALIFIED, [_matrix_fact()])
    assert c.status == STATUS_COVERED_RECOMMENDATION  # a grounded NO is assertive
    assert c.coverage_status == "in_envelope"
    assert c.allowed_claims[0].severity == "disqualify"


def test_compatible_is_covered_recommendation():
    assert (
        _contract(V_COMPATIBLE, [_matrix_fact()]).status
        == STATUS_COVERED_RECOMMENDATION
    )


def test_conditional_is_covered_caution_with_caution_severity():
    c = _contract(V_CONDITIONAL, [_matrix_fact()])
    assert c.status == STATUS_COVERED_CAUTION
    assert c.coverage_status == "partial_envelope"
    assert c.allowed_claims[0].severity == "caution"


def test_no_matrix_data_is_out_of_scope():
    c = _contract(V_NO_DATA, [])
    assert c.status == STATUS_OUT_OF_SCOPE
    assert c.coverage_status == "out_of_envelope"


def test_no_medium_is_needs_clarification_with_medium_missing():
    c = _contract(V_NO_MEDIUM, [])
    assert c.status == STATUS_NEEDS_CLARIFICATION
    assert "Medium" in c.missing_fields
    # the clarification clause names the missing field
    assert any("Medium" in cl for cl in c.required_clauses)


def test_non_suitability_turn_returns_none():
    assert (
        build_contract(
            coverage=None, grounding_facts=(), gegencheck_verdict=None, calc=None
        )
        is None
    )


# ── forbidden phrases (always + status-conditional) ──────────────────────────────────────────────


def test_forbidden_always_present_in_every_status():
    for verdict in (
        V_DISQUALIFIED,
        V_COMPATIBLE,
        V_CONDITIONAL,
        V_NO_DATA,
        V_NO_MEDIUM,
    ):
        fp = _contract(verdict, [_matrix_fact()]).forbidden_phrases
        # the fabrication markers + the manufacturer-release guard, every status (Phase-4b tuned set)
        assert "belegter befund" in fp
        assert "richtwert" in fp
        assert "fachliteratur" in fp
        assert "freigegeben" in fp and "garantiert" in fp


def test_common_dual_use_words_are_not_blanket_forbidden():
    # Phase 4b: bare "belegt"/"typisch" are dropped (a calibrated narrator uses them honestly); the
    # actual leak is an invented number (number prefilter) or the multi-word "belegter Befund".
    fp = _contract(V_COMPATIBLE, [_matrix_fact()]).forbidden_phrases
    assert "belegt" not in fp
    assert "typisch" not in fp


# ── allowed_materials (only what the grounding names) ────────────────────────────────────────────


def test_allowed_materials_extracted_from_claims_longest_first():
    facts = [_matrix_fact(), _card_fact()]  # texts name FKM + EPDM
    mats = _contract(V_DISQUALIFIED, facts).allowed_materials
    assert "FKM" in mats and "EPDM" in mats


def test_glasfaser_ptfe_wins_over_ptfe():
    f = _card_fact(text="Glasfaser-PTFE eignet sich als Stützring.", cid="CARD-GFPTFE")
    mats = _contract(V_COMPATIBLE, [f]).allowed_materials
    assert "Glasfaser-PTFE" in mats


# ── allowed_values + missing_fields (from the calc) ──────────────────────────────────────────────


def test_allowed_values_from_calc_computed():
    calc = CalcResult(
        computed=(
            ComputedValue(
                calc_id="pv_wert",
                name="pv",
                value=3.2,
                unit="N/(mm·s)",
                stage=1,
                derivation_depth=1,
            ),
        )
    )
    vals = _contract(V_COMPATIBLE, [_matrix_fact()], calc=calc).allowed_values
    assert vals == (
        {"name": "pv", "value": 3.2, "unit": "N/(mm·s)", "calc_id": "pv_wert"},
    )


def test_missing_input_surfaces_as_missing_field_and_clause():
    calc = CalcResult(
        not_computed=(
            NotComputed("pv_wert", "nicht berechenbar: Eingaben fehlen (p_bar)"),
        )
    )
    c = _contract(V_COMPATIBLE, [_matrix_fact()], calc=calc)
    assert "p_bar" in c.missing_fields
    assert any("p_bar" in cl for cl in c.required_clauses)
    # a grounded verdict is NOT suppressed by a missing calc input
    assert c.status == STATUS_COVERED_RECOMMENDATION


def test_outside_validity_reason_is_not_a_missing_field():
    calc = CalcResult(
        not_computed=(NotComputed("pv_wert", "außerhalb des Gültigkeitsbereichs"),)
    )
    assert _contract(V_COMPATIBLE, [_matrix_fact()], calc=calc).missing_fields == ()


# ── serialization ────────────────────────────────────────────────────────────────────────────────


def test_to_dict_round_trips_the_surface():
    d = _contract(V_DISQUALIFIED, [_matrix_fact()]).to_dict()
    assert d["status"] == STATUS_COVERED_RECOMMENDATION
    assert d["allowed_claims"][0]["id"] == "MX-FKM-DAMPF"
    assert isinstance(d["forbidden_phrases"], list)


# ── build_guard_contract (P0-B: the guard-only path for non-Gegencheck turns) ───────────────────────


def test_guard_contract_none_with_no_evidence_at_all():
    assert build_guard_contract(grounding_facts=(), calc=None) is None


def test_guard_contract_none_with_calc_but_nothing_computed():
    # not_computed-only (fail-closed kern misses) is still "nothing to check an answer against"
    calc = CalcResult(not_computed=(NotComputed("pv_wert", "nicht berechenbar"),))
    assert build_guard_contract(grounding_facts=(), calc=calc) is None


def test_guard_contract_built_from_grounding_alone():
    c = build_guard_contract(grounding_facts=(_card_fact(),), calc=None)
    assert c is not None
    assert c.status == STATUS_GENERAL
    assert c.allowed_claims[0].id == "CARD-EPDM-1"
    assert "EPDM" in c.allowed_materials


def test_guard_contract_required_clauses_always_empty():
    # L1 was never instructed (no Renderer-Modus) to include any required clause on this path —
    # asserting their presence would be a guaranteed, meaningless BLOCK. See the docstring.
    c = build_guard_contract(grounding_facts=(_card_fact(),), calc=None)
    assert c.required_clauses == ()


def test_guard_contract_allowed_values_from_calc_computed():
    calc = CalcResult(
        computed=(
            ComputedValue(
                calc_id="pv_wert",
                name="pv",
                value=3.2,
                unit="N/(mm·s)",
                stage=1,
                derivation_depth=1,
            ),
        )
    )
    c = build_guard_contract(grounding_facts=(), calc=calc)
    assert (
        c is not None
    )  # a computed value alone is evidence, even with zero grounding_facts
    assert c.allowed_values == (
        {"name": "pv", "value": 3.2, "unit": "N/(mm·s)", "calc_id": "pv_wert"},
    )


def test_guard_contract_forbidden_always_present():
    # the universal fabricated-authority markers apply on EVERY turn type, guard-only path included
    c = build_guard_contract(grounding_facts=(_card_fact(),), calc=None)
    assert "belegter befund" in c.forbidden_phrases
    assert "freigegeben" in c.forbidden_phrases and "garantiert" in c.forbidden_phrases


def test_guard_contract_never_reaches_the_gegencheck_status_values():
    # sentinel status must be distinct from every renderer-mode status — nothing downstream should
    # ever confuse a guard-only contract for a Gegencheck-shaped one by status alone
    c = build_guard_contract(grounding_facts=(_card_fact(),), calc=None)
    assert c.status not in (
        STATUS_OUT_OF_SCOPE,
        STATUS_NEEDS_CLARIFICATION,
        STATUS_COVERED_CAUTION,
        STATUS_COVERED_RECOMMENDATION,
    )
