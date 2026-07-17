"""Executable proof that MAT-GOV-03A is inert outside its technical aggregate."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from _model_schema_ast import load_material_schema, parse_material_schema_source


REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend/sealai_v2/db/models.py"
EXPECTED_03A_SCHEMA = {
    "v2_material_rulesets": frozenset(
        {"ruleset_id", "domain_pack_id", "created_by_subject", "created_at"}
    ),
    "v2_material_ruleset_snapshots": frozenset(
        {
            "snapshot_id",
            "ruleset_id",
            "snapshot_schema_version",
            "canonicalization_version",
            "mat_gov_contract_version",
            "content_sha256",
            "canonical_payload_json",
            "canonical_bytes",
            "created_by_subject",
            "created_at",
        }
    ),
    "v2_material_snapshot_validation_events": frozenset(
        {
            "event_id",
            "snapshot_id",
            "validator_contract_version",
            "validation_state",
            "error_code",
            "validation_sha256",
            "created_at",
        }
    ),
    "v2_material_snapshot_audit_events": frozenset(
        {
            "event_id",
            "snapshot_id",
            "event_type",
            "actor_subject",
            "event_payload_json",
            "event_sha256",
            "created_at",
        }
    ),
}
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
    schema = load_material_schema(MODELS)
    material_tables = {
        name: columns
        for name, columns in schema.items()
        if not name.startswith("v2_material_shadow_")
    }
    assert material_tables == EXPECTED_03A_SCHEMA
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


def _assert_schema_rejected(source: str) -> None:
    try:
        parse_material_schema_source(source)
    except AssertionError:
        return
    raise AssertionError("invalid MAT-GOV schema declaration was accepted")


def test_material_schema_parser_resolves_physical_column_names() -> None:
    aliased_source = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    alias: Mapped[str] = mapped_column("tenant_id", String())
"""
    default_source = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    tenant_id: Mapped[str] = mapped_column(String())
"""
    expected = {"v2_material_shadow_unexpected": frozenset({"tenant_id"})}
    assert parse_material_schema_source(aliased_source) == expected
    assert parse_material_schema_source(default_source) == expected


def test_material_schema_parser_accepts_only_static_column_type_forms() -> None:
    source = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    inferred_value: Mapped[str] = mapped_column()
    string_value: Mapped[str] = mapped_column(String(64))
    integer_value: Mapped[int] = mapped_column(Integer)
    boolean_value: Mapped[bool] = mapped_column(Boolean)
    binary_value: Mapped[bytes] = mapped_column(LargeBinary)
    json_value: Mapped[dict] = mapped_column(_MATERIAL_RULESET_JSON)
    foreign_value: Mapped[str] = mapped_column(
        String(68), ForeignKey("v2_material_rulesets.ruleset_id")
    )
"""
    assert parse_material_schema_source(source) == {
        "v2_material_shadow_unexpected": frozenset(
            {
                "inferred_value",
                "string_value",
                "integer_value",
                "boolean_value",
                "binary_value",
                "json_value",
                "foreign_value",
            }
        )
    }


def test_material_schema_parser_rejects_dynamic_column_arguments() -> None:
    dynamic_sources = (
        "mapped_column(COLUMN_NAME, String())",
        "mapped_column(build_name(), String())",
        'mapped_column(f"{PREFIX}_id", String())',
        "mapped_column(*COLUMN_ARGS)",
        "mapped_column(String(), **COLUMN_OPTIONS)",
    )
    for declaration in dynamic_sources:
        _assert_schema_rejected(
            f"""
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    safe_alias: Mapped[str] = {declaration}
"""
        )


def test_material_schema_parser_rejects_duplicate_physical_column_names() -> None:
    _assert_schema_rejected(
        """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    first: Mapped[str] = mapped_column("same_name", String())
    second: Mapped[str] = mapped_column("same_name", String())
"""
    )


def test_material_schema_parser_recognizes_models_structurally() -> None:
    literal_model = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    value: Mapped[str] = mapped_column(String())
"""
    assert parse_material_schema_source(literal_model) == {
        "v2_material_shadow_unexpected": frozenset({"value"})
    }

    dynamic_model = """
class UnexpectedName(Base):
    __tablename__ = PREFIX + "_shadow_table"
    value: Mapped[str] = mapped_column(String())
"""
    _assert_schema_rejected(dynamic_model)

    non_model_helper = """
class UnexpectedName:
    __tablename__ = PREFIX + "_shadow_table"
"""
    assert parse_material_schema_source(non_model_helper) == {}


def test_material_schema_parser_normatively_rejects_plain_assign_columns() -> None:
    plain_assign = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    field = mapped_column(String())
"""
    untyped_annassign = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    field: str = mapped_column(String())
"""
    for source in (plain_assign, untyped_annassign):
        _assert_schema_rejected(source)


def test_material_schema_parser_rejects_dynamic_declarations() -> None:
    dynamic_table = """
class V2MaterialShadowDynamic(Base):
    __tablename__ = prefix + suffix
    value: Mapped[str] = mapped_column(String())
"""
    dynamic_column = """
class V2MaterialShadowDynamic(Base):
    __tablename__ = "v2_material_shadow_dynamic"
    value: Mapped[str] = build_column()
"""
    dynamic_keyword_name = """
class V2MaterialShadowDynamic(Base):
    __tablename__ = "v2_material_shadow_dynamic"
    value: Mapped[str] = mapped_column(String(), name="tenant_id")
"""
    for source in (dynamic_table, dynamic_column, dynamic_keyword_name):
        _assert_schema_rejected(source)
