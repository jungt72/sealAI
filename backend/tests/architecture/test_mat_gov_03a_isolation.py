"""Executable proof that MAT-GOV-03A is inert outside its technical aggregate."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[3]
PROTECTED_HASHES = {
    "backend/sealai_v2/knowledge/matrix_seed.json": (
        "ab6a32cf9ef9deac402619cc1d0eaf67d30b39fa2c0c1d45fc2eb5782da4ed82"
    ),
    "backend/sealai_v2/api/deps.py": (
        "a285ed7ad58e2fdee5b6a11793b4f88dff4f708510b510424a2090a32a3e1453"
    ),
    "backend/sealai_v2/pipeline/pipeline.py": (
        "5842a3f7cd658036e867fafc4af74a0fedb2dfdab9b715708f5fd18d15ee7973"
    ),
    "backend/sealai_v2/pipeline/stages.py": (
        "cf042c0327fc7791fa22460a126783fb4c1d20383e169c6e4e7390d0a3872bde"
    ),
    "backend/sealai_v2/api/serializers.py": (
        "1795c1b7f0160bc4e99a174817fbfc3ee5a7c12f55791f34f06572d5fba6bb9d"
    ),
    "backend/sealai_v2/core/material_constraints.py": (
        "cf8d9969c3730cd5eaa23c08e1dac81df1f3b20bb5eafd219dbc7b004e91de42"
    ),
    "backend/sealai_v2/core/contracts.py": (
        "ed8af58c5407cd0d65730abfa390d56464e9a1f43f36715f9f6236913054b7b3"
    ),
    "backend/sealai_v2/config/settings.py": (
        "1dfb4c862bd48ee637d4a5b7cd1e5a26cd93cbf98538d6984c4f884422f1570a"
    ),
    "docker-compose.deploy.yml": (
        "322c08a81b97becffa8af53e63f645ff2ac1b8426b3867ce20443007c284a988"
    ),
    ".env.example": (
        "746c1c14050f996a37087999d4c1ba39068cb879cdb870f4745cea0962d3d6c1"
    ),
    "frontend-v2/src/contracts.ts": (
        "1f0b3d92dba2b30d0207dca2bdfb05b63efea3f33960e67e74705482bce38963"
    ),
    "frontend-v2/src/components/Answer.tsx": (
        "3d6f6ad1b9050032233b2525b20ec5476090d02e9821d38d8429cc15ef07c415"
    ),
}


def _imports(path: Path) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_parent_runtime_and_public_surfaces_are_byte_identical() -> None:
    for relative, expected in PROTECTED_HASHES.items():
        assert hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == expected


def test_no_request_runtime_imports_mat_gov_03a() -> None:
    runtime_files = (
        "backend/sealai_v2/api/deps.py",
        "backend/sealai_v2/api/main.py",
        "backend/sealai_v2/api/serializers.py",
        "backend/sealai_v2/pipeline/pipeline.py",
        "backend/sealai_v2/pipeline/stages.py",
        "backend/sealai_v2/core/material_constraints.py",
        "backend/sealai_v2/knowledge/matrix.py",
        "backend/sealai_v2/orchestration/answer_cache.py",
    )
    for relative in runtime_files:
        assert "sealai_v2.core.material_rulesets" not in _imports(REPO / relative)
        assert "sealai_v2.db.material_rulesets" not in _imports(REPO / relative)


def test_03a_models_contain_no_lifecycle_or_runtime_tables() -> None:
    sys.path.insert(0, str(REPO / "backend"))
    import sealai_v2.db.models  # noqa: F401
    from sealai_v2.db.engine import Base

    material_tables = {
        name for name in Base.metadata.tables if name.startswith("v2_material_")
    }
    assert material_tables == {
        "v2_material_rulesets",
        "v2_material_ruleset_snapshots",
        "v2_material_snapshot_validation_events",
        "v2_material_snapshot_audit_events",
    }
    forbidden = (
        "pointer",
        "approval",
        "review",
        "cohort",
        "lease",
        "stage_ack",
        "pin",
        "evaluation",
    )
    assert not any(token in table for table in material_tables for token in forbidden)
