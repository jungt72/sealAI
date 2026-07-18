"""Static proof that typed Evidence v2 is additive, closed and inert."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
MIGRATION = REPO / (
    "backend/sealai_v2/db/migrations/versions/"
    "20260718_0018_mat_evid_02_typed_scopes.py"
)
UNCHANGED_V1 = {
    "backend/sealai_v2/core/material_evidence.py": "5d05e5d8ca51ae5f023ed33214c8e28a53cbad642b5777a0d011d5433d605ced",
    "backend/sealai_v2/core/material_evidence_binding.py": "94064cb6fd80ede97327eb5a60bbe8fa9f146d05421aa9e2cb561e8baa7ba214",
    "backend/sealai_v2/core/material_evidence_review.py": "0a9af5a41528e02ef8950e56792525738a74374916d0cba6088ecdb5ab1dc959",
    "backend/sealai_v2/db/material_evidence.py": "ff59409cc59dbd57adac10288906e8605d4d9eda956015f2a74768dfdfce48b7",
    "backend/sealai_v2/db/material_evidence_binding.py": "5f02fa29ef261abdefea07d3f89b1f73f58c9fcb8e27590d778d232d7172cbfb",
    "backend/sealai_v2/db/material_evidence_review.py": "938a4ee4ed38262a7ad672c583f7a5705e6e157a9f3bd491f2a2fecd3d6b2d4d",
    "backend/sealai_v2/db/migrations/versions/20260718_0014_mat_evid_01a.py": "beea89e32632a80a59e56d900d8f089616e07ea7cd93fed1645e74cce860fcb4",
    "backend/sealai_v2/db/migrations/versions/20260718_0015_mat_evid_01b_runtime.py": "d48e77df70328b9c0ef33d980bf11da90a7fa6f70b591d55628aaca0a99fc220",
    "backend/sealai_v2/db/migrations/versions/20260718_0016_mat_evid_01c_review.py": "dfaa96cd0bd5b7d65b8a5b83867e96b8fd1b82cef20d24abfb90499a93625ed7",
}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_v1_contracts_and_persistence_are_byte_identical() -> None:
    for relative, expected in UNCHANGED_V1.items():
        assert hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == expected


def test_v2_migration_is_additive_empty_and_contains_no_activation_surface() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"bulk_insert", "execute_many"}
    lowered = source.lower()
    for token in (
        "active_pointer",
        "deployment_state",
        "sampling_basis_points",
        "seed_data",
        "backfill",
        "convert_v1",
    ):
        assert token not in lowered


def test_primary_runtime_api_and_frontend_do_not_import_v2_contracts() -> None:
    for relative in (
        "backend/sealai_v2/api/deps.py",
        "backend/sealai_v2/api/main.py",
        "backend/sealai_v2/api/serializers.py",
        "backend/sealai_v2/pipeline/pipeline.py",
        "backend/sealai_v2/pipeline/stages.py",
        "backend/sealai_v2/core/material_constraints.py",
        "backend/sealai_v2/knowledge/matrix.py",
        "backend/sealai_v2/orchestration/answer_cache.py",
    ):
        imports = _imports(REPO / relative)
        assert not any(name.endswith("_v2") for name in imports), relative
    for path in (REPO / "frontend-v2/src").rglob("*"):
        if path.is_file():
            source = path.read_text(encoding="utf-8", errors="ignore")
            assert "MAT-EVID-01A.v2" not in source
            assert "media_identity" not in source


def test_v2_contract_has_closed_scope_and_no_material_placeholder_path() -> None:
    source = (REPO / "backend/sealai_v2/core/material_evidence_v2.py").read_text(
        encoding="utf-8"
    )
    assert 'MATERIAL_RELATION = "material_relation"' in source
    assert 'MEDIA_IDENTITY = "media_identity"' in source
    assert "class MaterialRelationClaimScopeV2" in source
    assert "class MediaIdentityClaimScopeV2" in source
    assert "MediaIdentityClaimScopeV2" in source
    assert (
        "materials"
        not in source.split("class MediaIdentityClaimScopeV2", 1)[1].split(
            "def derive_claim_ref_v2", 1
        )[0]
    )
    assert "PLACEHOLDER" not in source


def test_only_med_norm_and_ai_review_consume_media_identity_contract() -> None:
    allowed = {
        REPO / "backend/sealai_v2/core/material_evidence_v2.py",
        REPO / "backend/sealai_v2/core/material_evidence_review_v2.py",
        REPO / "backend/sealai_v2/core/material_evidence_ai_review.py",
        REPO / "backend/sealai_v2/db/material_evidence_review_v2.py",
        REPO / "backend/sealai_v2/db/medium_catalog.py",
    }
    for path in (REPO / "backend/sealai_v2").rglob("*.py"):
        if path in allowed or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert "MediaIdentityClaimScopeV2" not in source, path
