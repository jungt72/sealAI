"""Pure technical evaluator over one already validated 03A snapshot."""

from __future__ import annotations

import hashlib
import json

from sealai_v2.core.contracts import MaterialConstraintMatch, MaterialConstraintQuery
from sealai_v2.core.material_constraints import resolve_material_constraint_matches
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.core.material_shadow import ShadowMaterialInput


_RESULT_DOMAIN = b"sealai.material-shadow.result.v1\x00"


def evaluate_snapshot(
    snapshot: MaterialRulesetSnapshotV1,
    material_input: ShadowMaterialInput,
) -> dict:
    if snapshot.payload.domain_pack_id != material_input.domain_pack_id:
        raise ValueError("shadow input and snapshot domain pack differ")
    query = MaterialConstraintQuery(
        material=material_input.material_id.canonical_id,
        medium=material_input.medium_id.canonical_id,
        material_state=material_input.material_state,
        medium_state=material_input.medium_state,
        medium_cardinality=material_input.medium_cardinality,
        relation_state=material_input.relation_state,
    )
    matches: list[MaterialConstraintMatch] = []
    for rule in snapshot.payload.rules:
        material_ids = {rule.material, *rule.scope.materials}
        medium_ids = {rule.medium, *rule.scope.media}
        if query.material not in material_ids or query.medium not in medium_ids:
            continue
        matches.append(
            MaterialConstraintMatch(
                rule_ref=rule.rule_ref,
                verdict=rule.verdict,
                statement=rule.statement,
                source_ref=f"matrix-cell:{rule.rule_ref}",
            )
        )
    result = resolve_material_constraint_matches(tuple(matches), query=query)
    projection = {
        "evaluation_state": result.evaluation_state.value,
        "verdict": result.verdict.value if result.verdict is not None else None,
        "decisive_ref": result.decisive_ref,
        "matches": [
            {
                "rule_ref": match.rule_ref,
                "verdict": match.verdict.value,
                "source_ref": match.source_ref,
            }
            for match in result.matches
        ],
        "stable_error_code": "none",
    }
    encoded = json.dumps(projection, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    projection["result_sha256"] = hashlib.sha256(_RESULT_DOMAIN + encoded).hexdigest()
    return projection
