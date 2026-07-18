from __future__ import annotations

from dataclasses import replace

import pytest

from sealai_v2.core.contracts import (
    Case,
    EvaluationState,
    GroundingFact,
    InputResolutionState,
    MaterialConstraintMatch,
    MaterialConstraintPreconditions,
    MaterialConstraintQuery,
    MaterialConstraintScopeState,
    MaterialConstraintVerdict,
    MediumCardinality,
    RelationState,
)
from sealai_v2.core.coverage import (
    MATRIX_COMPATIBLE_NEUTRAL_REASON,
    coverage_for,
)
from sealai_v2.core.material_constraints import (
    evaluate_material_constraints,
    legacy_material_constraint_query,
    material_constraint_to_gegencheck,
    resolve_material_constraint_matches,
)
from sealai_v2.core.response_contract import (
    MATRIX_COMPATIBLE_NEUTRAL_TEXT,
    STATUS_COVERED_CAUTION,
    build_contract,
)
from sealai_v2.pipeline import stages


def _query(
    *,
    cardinality: MediumCardinality = MediumCardinality.SINGLE,
    relation: RelationState = RelationState.NOT_APPLICABLE,
) -> MaterialConstraintQuery:
    return MaterialConstraintQuery(
        material="TESTMAT",
        medium="TESTMEDIUM",
        material_state=InputResolutionState.KNOWN,
        medium_state=InputResolutionState.KNOWN,
        medium_cardinality=cardinality,
        relation_state=relation,
    )


def _compatible_result():
    match = MaterialConstraintMatch(
        rule_ref="MX-COMPAT-1",
        verdict=MaterialConstraintVerdict.VERTRAEGLICH,
        statement="Keine dokumentierte Unverträglichkeit.",
        source_ref="matrix-cell:MX-COMPAT-1",
    )
    return resolve_material_constraint_matches((match,), query=_query())


def test_precondition_blockers_are_complete_and_in_binding_precedence(
    monkeypatch,
) -> None:
    class MustNotConstruct:
        def __init__(self, _catalog) -> None:
            raise AssertionError(
                "matrix access occurred before precondition resolution"
            )

    monkeypatch.setattr(
        "sealai_v2.core.material_constraints.InProcessCompatibilityMatrix",
        MustNotConstruct,
    )
    result = evaluate_material_constraints(
        _query(),
        tenant="tenant-1",
        catalog=object(),
        preconditions=MaterialConstraintPreconditions(
            scope=MaterialConstraintScopeState.OUT_OF_SCOPE,
            hard_gate_refs=("approval:GATE-MATERIAL", "auth:tenant"),
            conflict_refs=("case-conflict:medium",),
        ),
    )
    assert result.evaluation_state is EvaluationState.BLOCKED
    assert [(item.kind.value, item.ref) for item in result.blockers] == [
        ("hard_gate", "approval:GATE-MATERIAL"),
        ("hard_gate", "auth:tenant"),
        ("scope", "material-scope:out_of_scope"),
        ("conflict", "case-conflict:medium"),
    ]
    assert result.verdict is None
    assert result.matches == ()


@pytest.mark.parametrize(
    "preconditions",
    [
        MaterialConstraintPreconditions(
            scope=MaterialConstraintScopeState.IN_SCOPE,
            hard_gate_refs=("approval:blocked",),
        ),
        MaterialConstraintPreconditions(
            scope=MaterialConstraintScopeState.IN_SCOPE,
            conflict_refs=("case-conflict:material",),
        ),
    ],
)
def test_stage_does_not_resolve_catalog_for_precondition_block(preconditions) -> None:
    case = Case(
        seal_spec={"material": "TESTMAT"},
        medium={"name": "TESTMEDIUM", "matched": ["TESTMEDIUM"]},
    )

    class Matrix:
        @property
        def catalog(self):
            raise AssertionError("blocked precondition accessed matrix catalog")

    result = stages.material_constraints(
        Matrix(), case, tenant_id="tenant-1", preconditions=preconditions
    )
    assert result.evaluation_state is EvaluationState.BLOCKED


@pytest.mark.parametrize("relation", [RelationState.UNRESOLVED, RelationState.RESOLVED])
def test_every_multiple_medium_state_blocks_before_matrix_access(
    monkeypatch, relation
) -> None:
    class MustNotConstruct:
        def __init__(self, _catalog) -> None:
            raise AssertionError("multiple media reached matrix evaluation")

    monkeypatch.setattr(
        "sealai_v2.core.material_constraints.InProcessCompatibilityMatrix",
        MustNotConstruct,
    )
    result = evaluate_material_constraints(
        _query(cardinality=MediumCardinality.MULTIPLE, relation=relation),
        tenant="tenant-1",
        catalog=object(),
    )
    assert result.evaluation_state is EvaluationState.BLOCKED
    assert [item.ref for item in result.blockers] == ["medium-cardinality:multiple"]


def test_blocker_order_is_independent_of_input_order() -> None:
    first = MaterialConstraintPreconditions(
        scope=MaterialConstraintScopeState.IN_SCOPE,
        hard_gate_refs=("gate:b", "gate:a"),
        conflict_refs=("conflict:b", "conflict:a"),
    )
    second = MaterialConstraintPreconditions(
        scope=MaterialConstraintScopeState.IN_SCOPE,
        hard_gate_refs=tuple(reversed(first.hard_gate_refs)),
        conflict_refs=tuple(reversed(first.conflict_refs)),
    )
    assert first.blockers == second.blockers


def test_unspecified_scope_is_not_an_in_scope_wildcard() -> None:
    result = evaluate_material_constraints(
        _query(),
        tenant="tenant-1",
        catalog=None,
        preconditions=MaterialConstraintPreconditions(),
    )
    assert result.evaluation_state is EvaluationState.BLOCKED
    assert [(item.kind.value, item.ref) for item in result.blockers] == [
        ("scope", "material-scope:unknown")
    ]


def test_matrix_compatible_is_neutral_partial_and_never_recommendation() -> None:
    result = _compatible_result()
    legacy = material_constraint_to_gegencheck(result)
    coverage = coverage_for(legacy, None, material_constraints=result)
    assert coverage == {
        "status": "partial_envelope",
        "chemical": "neutral",
        "operating": "not_applicable",
        "archetype": "not_applicable",
        "axes": "chemical=neutral operating=not_applicable archetype=not_applicable",
        "reason_code": MATRIX_COMPATIBLE_NEUTRAL_REASON,
    }
    contract = build_contract(
        coverage=coverage,
        grounding_facts=(
            GroundingFact(
                text="TESTMAT ist mit TESTMEDIUM verträglich.",
                quelle="matrix",
                card_id="MX-COMPAT-1",
                kind="matrix",
            ),
        ),
        gegencheck_verdict=legacy,
        calc=None,
        material_constraints=result,
    )
    assert contract is not None
    assert contract.status == STATUS_COVERED_CAUTION
    assert contract.reason_code == MATRIX_COMPATIBLE_NEUTRAL_REASON
    assert MATRIX_COMPATIBLE_NEUTRAL_TEXT in contract.required_clauses
    assert contract.allowed_claims == ()
    assert result.positive_statement_allowed is False


def test_legacy_coverage_is_unchanged_without_canonical_feature_result() -> None:
    result = _compatible_result()
    legacy = material_constraint_to_gegencheck(result)
    assert coverage_for(legacy, None)["status"] == "in_envelope"


def test_non_evaluated_material_data_never_becomes_not_applicable() -> None:
    blocked = evaluate_material_constraints(
        replace(
            _query(),
            material="",
            material_state=InputResolutionState.MISSING,
        ),
        tenant="tenant-1",
        catalog=None,
    )
    coverage = coverage_for(
        material_constraint_to_gegencheck(blocked),
        None,
        material_constraints=blocked,
    )
    assert coverage["chemical"] == "missing"
    assert coverage["status"] == "out_of_envelope"


def test_recognized_material_ambiguity_is_preserved_and_blocks_matrix(
    monkeypatch,
) -> None:
    case = Case.from_case_state((), question="NBR oder FKM in Heißdampf")
    assert case.material_state is InputResolutionState.AMBIGUOUS
    assert case.material_candidates == ("FKM", "NBR")

    class Matrix:
        @property
        def catalog(self):
            raise AssertionError("ambiguous material accessed matrix catalog")

    result = stages.material_constraints(Matrix(), case, tenant_id="tenant-1")
    assert result.evaluation_state is EvaluationState.BLOCKED
    assert result.material_state is InputResolutionState.AMBIGUOUS


@pytest.mark.parametrize(
    "medium", ["Öl/Wasser", "Öl + Wasser", "Öl, Wasser", "Öl und Wasser"]
)
def test_punctuation_and_conjunctions_do_not_infer_medium_cardinality(medium) -> None:
    query = legacy_material_constraint_query("NBR", medium)
    assert query.medium_cardinality is MediumCardinality.SINGLE
    assert query.relation_state is RelationState.NOT_APPLICABLE
