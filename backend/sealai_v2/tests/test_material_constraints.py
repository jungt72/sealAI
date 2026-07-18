"""MAT-GOV-01 canonical material-constraint contract tests."""

from __future__ import annotations

import ast
import inspect
import json
import re
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import (
    MATRIX_VERDICTS,
    EvaluationState,
    InputResolutionState,
    MatrixCell,
    MaterialConstraintMatch,
    MaterialConstraintQuery,
    MaterialConstraintResult,
    MaterialConstraintVerdict,
    MediumCardinality,
    RelationState,
)
from sealai_v2.core.gegencheck import evaluate_gegencheck
import sealai_v2.core.material_constraints as material_constraint_module
from sealai_v2.core.material_constraints import (
    evaluate_material_constraints,
    material_constraint_to_gegencheck,
    resolve_material_constraint_matches,
)
from sealai_v2.knowledge.matrix import (
    CompatibilityMatrixCatalog,
    InProcessCompatibilityMatrix,
    load_matrix,
)
from sealai_v2.pipeline import stages


REPO_ROOT = Path(__file__).resolve().parents[3]


def _query(
    *,
    material: str = "TESTMAT",
    medium: str = "TESTMEDIUM",
    material_state: InputResolutionState = InputResolutionState.KNOWN,
    medium_state: InputResolutionState = InputResolutionState.KNOWN,
    medium_cardinality: MediumCardinality = MediumCardinality.SINGLE,
    relation_state: RelationState = RelationState.NOT_APPLICABLE,
) -> MaterialConstraintQuery:
    return MaterialConstraintQuery(
        material=material,
        medium=medium,
        material_state=material_state,
        medium_state=medium_state,
        medium_cardinality=medium_cardinality,
        relation_state=relation_state,
    )


def _match(ref: str, verdict: MaterialConstraintVerdict) -> MaterialConstraintMatch:
    return MaterialConstraintMatch(
        rule_ref=ref,
        verdict=verdict,
        statement=f"rule statement {ref}",
        source_ref=f"matrix-cell:{ref}",
    )


def _cell(ref: str, verdict: MaterialConstraintVerdict) -> MatrixCell:
    return MatrixCell(
        id=ref,
        werkstoff="TESTMAT",
        medium="TESTMEDIUM",
        bedingung="",
        bewertung=verdict,
        begruendung=f"rule statement {ref}",
        scope={
            "material": ["TESTMAT"],
            "medium": ["TESTMEDIUM"],
            "bedingung": [],
        },
        provenance=(f"owner:{ref}",),
    )


def test_backend_has_one_canonical_verdict_definition() -> None:
    definitions = []
    for path in (REPO_ROOT / "backend" / "sealai_v2").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        definitions.extend(
            (path, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and node.name == "MaterialConstraintVerdict"
        )
    assert len(definitions) == 1
    assert get_type_hints(MatrixCell)["bewertung"] is MaterialConstraintVerdict
    assert MATRIX_VERDICTS == tuple(item.value for item in MaterialConstraintVerdict)


def test_frontend_has_one_material_verdict_union_and_reuses_it() -> None:
    source = (REPO_ROOT / "frontend-v2" / "src" / "contracts.ts").read_text(
        encoding="utf-8"
    )
    union = re.compile(
        r'export type MaterialConstraintVerdict\s*=\s*"vertraeglich"\s*\|\s*'
        r'"unvertraeglich"\s*\|\s*"bedingt";'
    )
    assert len(union.findall(source)) == 1
    assert source.count("MaterialConstraintVerdict;") == 2
    assert (
        'export type MediumCardinality = "none" | "single" | "multiple" | "unknown";'
        in source
    )
    assert (
        'relation_state: "undetermined" | "resolved" | "unresolved" | "not_applicable";'
        in source
    )


def test_complete_json_is_identical_for_every_match_permutation() -> None:
    matches = (
        _match("BLOCK-B", MaterialConstraintVerdict.UNVERTRAEGLICH),
        _match("COND-B", MaterialConstraintVerdict.BEDINGT),
        _match("BLOCK-A", MaterialConstraintVerdict.UNVERTRAEGLICH),
        _match("COMPAT-A", MaterialConstraintVerdict.VERTRAEGLICH),
        _match("COND-A", MaterialConstraintVerdict.BEDINGT),
    )
    payloads = {
        json.dumps(
            resolve_material_constraint_matches(ordered, query=_query()).to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )
        for ordered in permutations(matches)
    }
    assert len(payloads) == 1
    result = resolve_material_constraint_matches(matches, query=_query())
    assert result.decisive_ref == "BLOCK-A"
    assert tuple(match.rule_ref for match in result.matches) == (
        "BLOCK-A",
        "BLOCK-B",
        "COND-A",
        "COND-B",
        "COMPAT-A",
    )
    assert tuple(match.rule_ref for match in result.conditions) == (
        "COND-A",
        "COND-B",
    )


def test_duplicate_match_rule_ref_is_rejected() -> None:
    with pytest.raises(ValueError, match="unique rule_ref"):
        resolve_material_constraint_matches(
            (
                _match("DUPLICATE", MaterialConstraintVerdict.BEDINGT),
                _match("DUPLICATE", MaterialConstraintVerdict.UNVERTRAEGLICH),
            ),
            query=_query(),
        )


def test_duplicate_catalog_rule_ref_is_rejected_before_evaluation() -> None:
    catalog = CompatibilityMatrixCatalog(
        cells=(
            _cell("DUPLICATE", MaterialConstraintVerdict.BEDINGT),
            _cell("DUPLICATE", MaterialConstraintVerdict.UNVERTRAEGLICH),
        )
    )
    with pytest.raises(ValueError, match="unique rule_ref"):
        evaluate_material_constraints(_query(), tenant="tenant-1", catalog=catalog)


@pytest.mark.parametrize(
    (
        "medium",
        "medium_state",
        "medium_cardinality",
        "relation_state",
        "evaluation_state",
    ),
    [
        (
            "",
            InputResolutionState.MISSING,
            MediumCardinality.NONE,
            RelationState.UNDETERMINED,
            EvaluationState.BLOCKED,
        ),
        (
            "unmapped medium",
            InputResolutionState.UNKNOWN,
            MediumCardinality.UNKNOWN,
            RelationState.UNDETERMINED,
            EvaluationState.BLOCKED,
        ),
        (
            "candidate A or B",
            InputResolutionState.AMBIGUOUS,
            MediumCardinality.UNKNOWN,
            RelationState.UNDETERMINED,
            EvaluationState.BLOCKED,
        ),
        (
            "TESTMEDIUM",
            InputResolutionState.KNOWN,
            MediumCardinality.SINGLE,
            RelationState.NOT_APPLICABLE,
            EvaluationState.NO_RULE_DATA,
        ),
        (
            "MEDIUM-A MEDIUM-B",
            InputResolutionState.KNOWN,
            MediumCardinality.MULTIPLE,
            RelationState.UNRESOLVED,
            EvaluationState.BLOCKED,
        ),
        (
            "MEDIUM-A MEDIUM-B",
            InputResolutionState.KNOWN,
            MediumCardinality.MULTIPLE,
            RelationState.RESOLVED,
            EvaluationState.BLOCKED,
        ),
    ],
)
def test_every_allowed_medium_cardinality_relation_combination(
    medium: str,
    medium_state: InputResolutionState,
    medium_cardinality: MediumCardinality,
    relation_state: RelationState,
    evaluation_state: EvaluationState,
) -> None:
    query = _query(
        medium=medium,
        medium_state=medium_state,
        medium_cardinality=medium_cardinality,
        relation_state=relation_state,
    )
    result = evaluate_material_constraints(query, tenant="tenant-1", catalog=None)
    assert result.medium_state is medium_state
    assert result.medium_cardinality is medium_cardinality
    assert result.relation_state is relation_state
    assert result.evaluation_state is evaluation_state
    assert result.verdict is None


def test_both_inputs_missing_are_blocked_with_undetermined_relation() -> None:
    result = evaluate_material_constraints(
        _query(
            material="",
            medium="",
            material_state=InputResolutionState.MISSING,
            medium_state=InputResolutionState.MISSING,
            medium_cardinality=MediumCardinality.NONE,
            relation_state=RelationState.UNDETERMINED,
        ),
        tenant="tenant-1",
        catalog=None,
    )
    assert result.to_dict() == {
        "material_state": "missing",
        "medium_state": "missing",
        "medium_cardinality": "none",
        "relation_state": "undetermined",
        "evaluation_state": "blocked",
        "disqualified": False,
        "requires_resolution": True,
        "positive_statement_allowed": False,
        "conditions": [],
        "blockers": [
            {"kind": "input", "ref": "material-input:missing"},
            {"kind": "input", "ref": "medium-input:missing"},
        ],
    }


@pytest.mark.parametrize(
    ("material", "material_state", "evaluation_state"),
    [
        ("TESTMAT", InputResolutionState.KNOWN, EvaluationState.NO_RULE_DATA),
        ("", InputResolutionState.MISSING, EvaluationState.BLOCKED),
        ("unmapped", InputResolutionState.UNKNOWN, EvaluationState.BLOCKED),
        ("candidate A or B", InputResolutionState.AMBIGUOUS, EvaluationState.BLOCKED),
    ],
)
def test_material_resolution_is_independent_from_single_medium_cardinality(
    material: str,
    material_state: InputResolutionState,
    evaluation_state: EvaluationState,
) -> None:
    result = evaluate_material_constraints(
        _query(material=material, material_state=material_state),
        tenant="tenant-1",
        catalog=None,
    )
    assert result.material_state is material_state
    assert result.medium_state is InputResolutionState.KNOWN
    assert result.medium_cardinality is MediumCardinality.SINGLE
    assert result.relation_state is RelationState.NOT_APPLICABLE
    assert result.evaluation_state is evaluation_state


@pytest.mark.parametrize(
    ("medium_state", "medium_cardinality", "relation_state", "medium"),
    [
        (
            InputResolutionState.MISSING,
            MediumCardinality.NONE,
            RelationState.UNRESOLVED,
            "",
        ),
        (
            InputResolutionState.MISSING,
            MediumCardinality.NONE,
            RelationState.NOT_APPLICABLE,
            "",
        ),
        (
            InputResolutionState.UNKNOWN,
            MediumCardinality.UNKNOWN,
            RelationState.RESOLVED,
            "unknown medium",
        ),
        (
            InputResolutionState.AMBIGUOUS,
            MediumCardinality.UNKNOWN,
            RelationState.RESOLVED,
            "ambiguous medium",
        ),
        (
            InputResolutionState.KNOWN,
            MediumCardinality.SINGLE,
            RelationState.UNRESOLVED,
            "TESTMEDIUM",
        ),
        (
            InputResolutionState.KNOWN,
            MediumCardinality.SINGLE,
            RelationState.RESOLVED,
            "TESTMEDIUM",
        ),
        (
            InputResolutionState.KNOWN,
            MediumCardinality.MULTIPLE,
            RelationState.NOT_APPLICABLE,
            "MEDIUM-A MEDIUM-B",
        ),
        (
            InputResolutionState.KNOWN,
            MediumCardinality.NONE,
            RelationState.UNDETERMINED,
            "TESTMEDIUM",
        ),
        (
            InputResolutionState.KNOWN,
            MediumCardinality.UNKNOWN,
            RelationState.UNDETERMINED,
            "TESTMEDIUM",
        ),
    ],
)
def test_invalid_medium_cardinality_relation_combinations_are_rejected(
    medium_state: InputResolutionState,
    medium_cardinality: MediumCardinality,
    relation_state: RelationState,
    medium: str,
) -> None:
    with pytest.raises(ValueError, match="invalid medium_state"):
        _query(
            medium=medium,
            medium_state=medium_state,
            medium_cardinality=medium_cardinality,
            relation_state=relation_state,
        )


@pytest.mark.parametrize(
    ("medium_state", "medium_cardinality", "relation_state"),
    [
        (
            InputResolutionState.MISSING,
            MediumCardinality.NONE,
            RelationState.UNDETERMINED,
        ),
        (
            InputResolutionState.KNOWN,
            MediumCardinality.MULTIPLE,
            RelationState.UNRESOLVED,
        ),
        (
            InputResolutionState.KNOWN,
            MediumCardinality.MULTIPLE,
            RelationState.RESOLVED,
        ),
    ],
)
def test_evaluated_rejects_every_non_single_medium_relation(
    medium_state: InputResolutionState,
    medium_cardinality: MediumCardinality,
    relation_state: RelationState,
) -> None:
    match = _match("RULE-1", MaterialConstraintVerdict.BEDINGT)
    with pytest.raises(ValueError, match="evaluated result requires evaluable"):
        MaterialConstraintResult(
            material_state=InputResolutionState.KNOWN,
            medium_state=medium_state,
            medium_cardinality=medium_cardinality,
            relation_state=relation_state,
            evaluation_state=EvaluationState.EVALUATED,
            verdict=MaterialConstraintVerdict.BEDINGT,
            matches=(match,),
            decisive_ref=match.rule_ref,
        )


def test_relation_not_applicable_for_one_relevant_component() -> None:
    result = evaluate_material_constraints(_query(), tenant="tenant-1", catalog=None)
    assert result.relation_state is RelationState.NOT_APPLICABLE
    assert result.medium_cardinality is MediumCardinality.SINGLE
    assert result.evaluation_state is EvaluationState.NO_RULE_DATA


def test_pipeline_cardinality_uses_structured_items_not_text_punctuation() -> None:
    matrix = SimpleNamespace(catalog=CompatibilityMatrixCatalog(cells=()))
    single = SimpleNamespace(
        seal_spec={"material": "TESTMAT"},
        medium={"matched": ["A + B / C, und D"]},
    )
    multiple = SimpleNamespace(
        seal_spec={"material": "TESTMAT"},
        medium={"matched": ["MEDIUM-A", "MEDIUM-B"]},
    )

    single_result = stages.material_constraints(matrix, single, tenant_id="tenant-1")
    multiple_result = stages.material_constraints(
        matrix, multiple, tenant_id="tenant-1"
    )

    assert single_result.medium_cardinality is MediumCardinality.SINGLE
    assert single_result.relation_state is RelationState.NOT_APPLICABLE
    assert multiple_result.medium_cardinality is MediumCardinality.MULTIPLE
    assert multiple_result.relation_state is RelationState.UNRESOLVED
    assert multiple_result.evaluation_state is EvaluationState.BLOCKED


@pytest.mark.parametrize(
    ("medium", "relation_state"),
    [
        ("oil steam", RelationState.UNRESOLVED),
        ("oil", RelationState.RESOLVED),
        ("oil steam", RelationState.RESOLVED),
    ],
)
def test_every_multiple_medium_query_is_blocked_without_rule_output(
    medium: str, relation_state: RelationState
) -> None:
    catalog = CompatibilityMatrixCatalog(
        cells=(
            MatrixCell(
                id="RULE-OIL",
                werkstoff="NBR",
                medium="oil",
                bedingung="",
                bewertung=MaterialConstraintVerdict.BEDINGT,
                begruendung="Oil condition",
                scope={"material": ["NBR"], "medium": ["oil"], "bedingung": []},
                provenance=("owner:RULE-OIL",),
            ),
            MatrixCell(
                id="RULE-STEAM",
                werkstoff="NBR",
                medium="steam",
                bedingung="",
                bewertung=MaterialConstraintVerdict.UNVERTRAEGLICH,
                begruendung="Steam incompatibility",
                scope={
                    "material": ["NBR"],
                    "medium": ["steam"],
                    "bedingung": [],
                },
                provenance=("owner:RULE-STEAM",),
            ),
        )
    )
    result = evaluate_material_constraints(
        _query(
            material="NBR",
            medium=medium,
            medium_cardinality=MediumCardinality.MULTIPLE,
            relation_state=relation_state,
        ),
        tenant="tenant-1",
        catalog=catalog,
    )

    assert result.evaluation_state is EvaluationState.BLOCKED
    assert result.verdict is None
    assert result.matches == ()
    assert result.conditions == ()
    assert result.decisive_ref is None
    assert "verdict" not in result.to_dict()
    assert "matches" not in result.to_dict()
    assert "decisive_ref" not in result.to_dict()


def test_single_medium_not_applicable_remains_evaluable() -> None:
    catalog = CompatibilityMatrixCatalog(
        cells=(_cell("RULE-SINGLE", MaterialConstraintVerdict.BEDINGT),)
    )
    result = evaluate_material_constraints(_query(), tenant="tenant-1", catalog=catalog)

    assert result.evaluation_state is EvaluationState.EVALUATED
    assert result.verdict is MaterialConstraintVerdict.BEDINGT


def test_no_rule_data_has_no_verdict() -> None:
    result = evaluate_material_constraints(
        _query(),
        tenant="tenant-1",
        catalog=CompatibilityMatrixCatalog(cells=()),
    )
    assert result.evaluation_state is EvaluationState.NO_RULE_DATA
    assert result.verdict is None
    assert "verdict" not in result.to_dict()


def test_canonical_evaluator_keeps_more_than_legacy_six_conditions() -> None:
    catalog = CompatibilityMatrixCatalog(
        cells=tuple(
            _cell(f"MX-COND-{index:02d}", MaterialConstraintVerdict.BEDINGT)
            for index in range(8)
        )
    )
    result = evaluate_material_constraints(_query(), tenant="tenant-1", catalog=catalog)
    assert len(result.conditions) == 8


def test_canonical_evaluator_and_stage_expose_no_match_limit() -> None:
    assert (
        "max_matches" not in inspect.signature(evaluate_material_constraints).parameters
    )
    assert (
        "max_matches" not in inspect.signature(stages.material_constraints).parameters
    )

    catalog = CompatibilityMatrixCatalog(
        cells=tuple(
            _cell(f"MX-COND-{index:02d}", MaterialConstraintVerdict.BEDINGT)
            for index in range(8)
        )
    )
    case = SimpleNamespace(
        seal_spec={"material": "TESTMAT"},
        medium={"matched": ["TESTMEDIUM"]},
    )
    result = stages.material_constraints(
        SimpleNamespace(catalog=catalog), case, tenant_id="tenant-1"
    )

    assert result.evaluation_state is EvaluationState.EVALUATED
    assert len(result.matches) == 8
    assert len(result.conditions) == 8


def test_legacy_projection_is_bounded_after_full_canonical_precedence() -> None:
    catalog = CompatibilityMatrixCatalog(
        cells=tuple(
            _cell(f"A-COND-{index:02d}", MaterialConstraintVerdict.BEDINGT)
            for index in range(7)
        )
        + (_cell("Z-BLOCK-08", MaterialConstraintVerdict.UNVERTRAEGLICH),)
    )
    canonical = evaluate_material_constraints(
        _query(), tenant="tenant-1", catalog=catalog
    )
    before = canonical.to_dict()

    legacy_matches = material_constraint_module._legacy_projection_matches(canonical)
    legacy = material_constraint_to_gegencheck(canonical)

    assert len(canonical.matches) == 8
    assert len(canonical.conditions) == 7
    assert canonical.verdict is MaterialConstraintVerdict.UNVERTRAEGLICH
    assert canonical.decisive_ref == "Z-BLOCK-08"
    assert len(legacy_matches) == 6
    assert legacy_matches[0].rule_ref == canonical.decisive_ref
    assert legacy["disqualified"] is True
    assert canonical.to_dict() == before


def test_source_ref_is_neutral_and_evidence_is_explicitly_unbound() -> None:
    result = evaluate_material_constraints(
        _query(),
        tenant="tenant-1",
        catalog=CompatibilityMatrixCatalog(
            cells=(_cell("MX-COND-01", MaterialConstraintVerdict.BEDINGT),)
        ),
    )
    payload = result.to_dict()
    match = payload["matches"][0]
    assert match["source_ref"] == "matrix-cell:MX-COND-01"
    assert match["evidence_binding_state"] == "unbound"
    serialized = json.dumps(payload).lower()
    assert "grounded" not in serialized
    assert "reviewed" not in serialized
    assert "approved" not in serialized


@pytest.mark.parametrize(
    "source_ref",
    [
        "reviewed:approved:claim-7",
        "approved:RULE-1",
        "grounded:RULE-1",
        "foreign:RULE-1",
        "matrix-cell:OTHER-ID",
        "matrix-cell:",
        " matrix-cell:RULE-1",
        "matrix-cell:RULE-1 ",
        "matrix-cell: RULE-1",
        "Matrix-Cell:RULE-1",
        "MATRIX-CELL:RULE-1",
        "matrix-cell:rule-1",
        "matrіx-cell:RULE-1",
        "matrix-cell：RULE-1",
        "matrix-\u200bcell:RULE-1",
        "https://example.invalid/source",
        "free source description",
    ],
)
def test_source_ref_must_exactly_bind_its_rule_ref(source_ref: str) -> None:
    with pytest.raises(ValueError, match="source_ref must equal"):
        MaterialConstraintMatch(
            rule_ref="RULE-1",
            verdict=MaterialConstraintVerdict.BEDINGT,
            statement="rule statement",
            source_ref=source_ref,
        )


@pytest.mark.parametrize(
    ("rule_ref", "source_ref"),
    [("", "matrix-cell:"), (" ", "matrix-cell: ")],
)
def test_empty_rule_ref_is_rejected(rule_ref: str, source_ref: str) -> None:
    with pytest.raises(ValueError, match="stable rule_ref"):
        MaterialConstraintMatch(
            rule_ref=rule_ref,
            verdict=MaterialConstraintVerdict.BEDINGT,
            statement="rule statement",
            source_ref=source_ref,
        )


def test_positive_statement_is_structurally_forbidden() -> None:
    result = resolve_material_constraint_matches(
        (_match("COMPAT-01", MaterialConstraintVerdict.VERTRAEGLICH),),
        query=_query(),
    )
    assert result.positive_statement_allowed is False
    assert result.to_dict()["positive_statement_allowed"] is False
    assert material_constraint_to_gegencheck(result) == {
        "disqualified": False,
        "basis": "matrix_compatible",
        "source": "matrix-cell:COMPAT-01",
    }


def _legacy_reference(material: str, medium: str | None, *, catalog) -> dict:
    if medium is None or not str(medium).strip():
        return {"disqualified": False, "basis": "no_medium"}
    facts = InProcessCompatibilityMatrix(catalog).query(
        tenant_id="tenant-1", query_text=f"{material} {medium}"
    )
    if not facts:
        return {"disqualified": False, "basis": "no_matrix_data"}
    incompatible = None
    conditional = None
    for fact in facts:
        cell = catalog.by_id(fact.card_id)
        if cell is None:
            continue
        if cell.bewertung == "unvertraeglich" and incompatible is None:
            incompatible = fact
        elif cell.bewertung == "bedingt" and conditional is None:
            conditional = fact
    if incompatible is not None:
        return {
            "disqualified": True,
            "reason": incompatible.text,
            "source": incompatible.quelle,
        }
    if conditional is not None:
        return {
            "disqualified": False,
            "basis": "matrix_conditional",
            "condition": conditional.text,
            "source": conditional.quelle,
        }
    return {"disqualified": False, "basis": "matrix_compatible"}


@pytest.mark.parametrize("material", ["", " ", "NBR", "FKM", "UNKNOWN"])
@pytest.mark.parametrize("medium", [None, "", " ", "Mineralöl", "Heißdampf", "UNKNOWN"])
def test_flag_off_legacy_dictionary_matches_parent_for_all_input_combinations(
    material: str, medium: str | None
) -> None:
    catalog = load_matrix()
    expected = _legacy_reference(material, medium, catalog=catalog)
    actual = evaluate_gegencheck(material, medium, tenant="tenant-1", catalog=catalog)
    assert actual == expected


def test_material_constraints_feature_is_default_off() -> None:
    assert Settings().material_constraints_enabled is False


def test_enabled_material_constraints_require_matrix_setting() -> None:
    with pytest.raises(ValueError, match="requires compatibility_matrix_enabled"):
        Settings(material_constraints_enabled=True)


def test_invalid_evaluated_input_cannot_use_blank_as_wildcard() -> None:
    with pytest.raises(ValueError, match="state known requires"):
        _query(medium="")


def test_raw_or_unknown_enum_values_are_rejected_inside_the_contract() -> None:
    with pytest.raises(TypeError, match="material_state"):
        MaterialConstraintQuery(
            material="TESTMAT",
            medium="TESTMEDIUM",
            material_state="known",  # type: ignore[arg-type]
            medium_state=InputResolutionState.KNOWN,
            medium_cardinality=MediumCardinality.SINGLE,
            relation_state=RelationState.NOT_APPLICABLE,
        )
    with pytest.raises(TypeError, match="medium_cardinality"):
        MaterialConstraintQuery(
            material="TESTMAT",
            medium="TESTMEDIUM",
            material_state=InputResolutionState.KNOWN,
            medium_state=InputResolutionState.KNOWN,
            medium_cardinality="single",  # type: ignore[arg-type]
            relation_state=RelationState.NOT_APPLICABLE,
        )
    with pytest.raises(TypeError, match="match verdict"):
        MaterialConstraintMatch(
            rule_ref="RULE-1",
            verdict="unknown-verdict",  # type: ignore[arg-type]
            statement="rule statement",
            source_ref="matrix-cell:RULE-1",
        )
