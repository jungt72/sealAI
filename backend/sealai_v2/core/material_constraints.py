"""Pure MAT-GOV-01 material-constraint contract evaluator.

The module consolidates the existing matrix verdict semantics without adding
rules, evidence, media normalization, or a second verdict vocabulary. It is
I/O-free: the caller injects the already loaded compatibility catalog.
"""

from __future__ import annotations

from sealai_v2.core.contracts import (
    EvaluationState,
    InputResolutionState,
    MediumCardinality,
    MaterialConstraintMatch,
    MaterialConstraintQuery,
    MaterialConstraintResult,
    MaterialConstraintVerdict,
    RelationState,
    material_constraint_match_sort_key,
)
from sealai_v2.knowledge.matrix import (
    CompatibilityMatrixCatalog,
    InProcessCompatibilityMatrix,
)


_LEGACY_MATCH_LIMIT = 6


def _legacy_projection_matches(
    result: MaterialConstraintResult,
) -> tuple[MaterialConstraintMatch, ...]:
    """Return only the historical bounded view; never alter ``result``."""

    return result.matches[:_LEGACY_MATCH_LIMIT]


def _result_without_verdict(
    query: MaterialConstraintQuery, evaluation_state: EvaluationState
) -> MaterialConstraintResult:
    return MaterialConstraintResult(
        material_state=query.material_state,
        medium_state=query.medium_state,
        medium_cardinality=query.medium_cardinality,
        relation_state=query.relation_state,
        evaluation_state=evaluation_state,
    )


def _assert_unique_rule_refs(rule_refs: tuple[str, ...]) -> None:
    if len(rule_refs) != len(set(rule_refs)):
        raise ValueError("material-constraint rules require unique rule_ref values")


def resolve_material_constraint_matches(
    matches: tuple[MaterialConstraintMatch, ...], *, query: MaterialConstraintQuery
) -> MaterialConstraintResult:
    """Apply precedence after canonicalizing every serialized match order."""

    if not query.evaluable:
        if matches:
            raise ValueError("blocked material-constraint input cannot carry matches")
        return _result_without_verdict(query, EvaluationState.BLOCKED)

    _assert_unique_rule_refs(tuple(match.rule_ref for match in matches))
    ordered = tuple(sorted(matches, key=material_constraint_match_sort_key))
    if not ordered:
        return _result_without_verdict(query, EvaluationState.NO_RULE_DATA)

    decisive = ordered[0]
    return MaterialConstraintResult(
        material_state=query.material_state,
        medium_state=query.medium_state,
        medium_cardinality=query.medium_cardinality,
        relation_state=query.relation_state,
        evaluation_state=EvaluationState.EVALUATED,
        verdict=decisive.verdict,
        matches=ordered,
        decisive_ref=decisive.rule_ref,
    )


def evaluate_material_constraints(
    query: MaterialConstraintQuery,
    *,
    tenant: str,
    catalog: CompatibilityMatrixCatalog | None,
) -> MaterialConstraintResult:
    """Evaluate explicit inputs against the existing compatibility matrix.

    The canonical evaluator has no result cap, so every simultaneously
    applicable condition survives. ``None`` catalog state is explicit
    ``no_rule_data`` for evaluable inputs, never a silently absent result.
    Multiple media remain blocked even when their relationship is marked
    resolved: MAT-GOV-01 has no structured per-medium evaluation surface.
    """

    if not query.evaluable:
        return _result_without_verdict(query, EvaluationState.BLOCKED)
    if catalog is None:
        return _result_without_verdict(query, EvaluationState.NO_RULE_DATA)

    _assert_unique_rule_refs(tuple(cell.id for cell in catalog.cells))
    facts = InProcessCompatibilityMatrix(catalog).query(
        tenant_id=tenant,
        query_text=f"{query.material} {query.medium}",
        k=len(catalog.cells),
    )
    matches: list[MaterialConstraintMatch] = []
    for fact in facts:
        cell = catalog.by_id(fact.card_id)
        if cell is None:
            continue
        matches.append(
            MaterialConstraintMatch(
                rule_ref=cell.id,
                verdict=cell.bewertung,
                statement=fact.text,
                source_ref=f"matrix-cell:{cell.id}",
            )
        )
    return resolve_material_constraint_matches(tuple(matches), query=query)


def material_constraint_to_gegencheck(result: MaterialConstraintResult) -> dict:
    """Project the complete canonical result onto the bounded legacy shape.

    The canonical verdict and decisive reference have already been computed
    from every applicable match.  Only the historical projection surface is
    bounded; projection never mutates or re-resolves the canonical result.
    """

    if result.evaluation_state is EvaluationState.BLOCKED:
        if result.medium_state is InputResolutionState.MISSING:
            return {"disqualified": False, "basis": "no_medium"}
        return {"disqualified": False, "basis": "no_matrix_data"}
    if result.evaluation_state is EvaluationState.NO_RULE_DATA:
        return {"disqualified": False, "basis": "no_matrix_data"}
    if result.evaluation_state is not EvaluationState.EVALUATED:
        raise ValueError(
            f"unsupported material evaluation state: {result.evaluation_state.value}"
        )

    legacy_matches = _legacy_projection_matches(result)
    decisive = next(
        match for match in legacy_matches if match.rule_ref == result.decisive_ref
    )
    if result.verdict is MaterialConstraintVerdict.UNVERTRAEGLICH:
        return {
            "disqualified": True,
            "reason": decisive.statement,
            "source": decisive.source_ref,
        }
    if result.verdict is MaterialConstraintVerdict.BEDINGT:
        return {
            "disqualified": False,
            "basis": "matrix_conditional",
            "condition": decisive.statement,
            "source": decisive.source_ref,
        }
    return {"disqualified": False, "basis": "matrix_compatible"}


def legacy_material_constraint_query(
    material: str, medium: str | None
) -> MaterialConstraintQuery:
    """Translate the historical loose input surface into orthogonal states."""

    material_value = str(material or "").strip()
    medium_value = str(medium or "").strip()
    material_state = (
        InputResolutionState.KNOWN if material_value else InputResolutionState.MISSING
    )
    medium_state = (
        InputResolutionState.KNOWN if medium_value else InputResolutionState.MISSING
    )
    medium_cardinality = (
        MediumCardinality.SINGLE
        if medium_state is InputResolutionState.KNOWN
        else MediumCardinality.NONE
    )
    relation_state = (
        RelationState.NOT_APPLICABLE
        if medium_state is InputResolutionState.KNOWN
        else RelationState.UNDETERMINED
    )
    return MaterialConstraintQuery(
        material=material_value,
        medium=medium_value,
        material_state=material_state,
        medium_state=medium_state,
        medium_cardinality=medium_cardinality,
        relation_state=relation_state,
    )


__all__ = [
    "evaluate_material_constraints",
    "legacy_material_constraint_query",
    "material_constraint_to_gegencheck",
    "resolve_material_constraint_matches",
]
