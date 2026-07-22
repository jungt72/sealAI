"""Executable proof that MAT-GOV-03A is inert outside its technical aggregate."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from _model_schema_ast import (
    _PROTECTED_BINDING_NAMES,
    load_material_schema,
    parse_material_schema_source,
)


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
        "41a26160c1372f47b075317954972dbac337bd4a49df1d30c12ec8de2fe0f876"
    ),
    "backend/sealai_v2/pipeline/stages.py": (
        "40b36ef33d0e7ad0ff1a2b8119b1420a7cfbe4c918b0a312f7e5520407e9be67"
    ),
    "backend/sealai_v2/api/serializers.py": (
        "df2550c2734e00964dc4549ce140df0885d294949e8b57184117d3c8c74c5fd6"
    ),
    "backend/sealai_v2/core/material_constraints.py": (
        "cf8d9969c3730cd5eaa23c08e1dac81df1f3b20bb5eafd219dbc7b004e91de42"
    ),
    "backend/sealai_v2/core/contracts.py": (
        "ed8af58c5407cd0d65730abfa390d56464e9a1f43f36715f9f6236913054b7b3"
    ),
    "docker-compose.deploy.yml": (
        "e1ebec302d4b101684ca8c9f47f9c79606595ac2ebef5768cfdd31bd97ac4e67"
    ),
    ".env.example": (
        "acc32c4fd4717872f64ae4ad0501c570f348cf9f9daaf90a96163ef407f00da7"
    ),
    "frontend-v2/src/contracts.ts": (
        "7615d47b05b74363910e9879c2a0862d66b5c4fe8e1e98a82660f4b17816efbc"
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
    material_tables = {name: schema[name] for name in EXPECTED_03A_SCHEMA}
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
    alias: Mapped[str] = mapped_column("tenant_id", String(64))
"""
    default_source = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    tenant_id: Mapped[str] = mapped_column(String(64))
"""
    expected = {"v2_material_shadow_unexpected": frozenset({"tenant_id"})}
    assert parse_material_schema_source(aliased_source) == expected
    assert parse_material_schema_source(default_source) == expected


def test_material_schema_parser_accepts_only_static_column_type_forms() -> None:
    source = """
_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), "postgresql")

class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    string_value: Mapped[str] = mapped_column(String(64))
    integer_value: Mapped[int] = mapped_column(Integer)
    boolean_value: Mapped[bool] = mapped_column(Boolean)
    binary_value: Mapped[bytes] = mapped_column(LargeBinary)
    json_value: Mapped[dict] = mapped_column(_MATERIAL_RULESET_JSON)
    foreign_value: Mapped[str] = mapped_column(
        String(68),
        ForeignKey("v2_material_rulesets.ruleset_id", ondelete="RESTRICT"),
        nullable=False,
    )
"""
    assert parse_material_schema_source(source) == {
        "v2_material_shadow_unexpected": frozenset(
            {
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
        "mapped_column(String(64), **COLUMN_OPTIONS)",
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
    value: Mapped[str] = mapped_column(String(64))
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
    field = mapped_column(String(64))
"""
    untyped_annassign = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    field: str = mapped_column(String(64))
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
    value: Mapped[str] = mapped_column(String(64), name="tenant_id")
"""
    for source in (dynamic_table, dynamic_column, dynamic_keyword_name):
        _assert_schema_rejected(source)


def test_material_schema_parser_rejects_every_dynamic_ast_escape() -> None:
    declarations = (
        "field: Mapped[build_type()] = mapped_column(String(64))",
        "field: Mapped[str] = mapped_column(UNKNOWN_TYPE)",
        "field: Mapped[str] = mapped_column(String(dynamic_length))",
        "field: Mapped[str] = mapped_column(String(64), build_constraint())",
        "field: Mapped[str] = mapped_column(String(64), ForeignKey(build_target()))",
        "field: Mapped[str] = mapped_column(String(64), ForeignKey('v2_material_rulesets.ruleset_id', ondelete=DELETE_POLICY))",
        "field: Mapped[str] = mapped_column(String(64), nullable=runtime_nullable())",
        "field: Mapped[str] = mapped_column(String(64), unknown=True)",
        "field: Mapped[str] = mapped_column(String(64), *ARGS)",
        "field: Mapped[str] = mapped_column(String(64), **KWARGS)",
        "field: Mapped[str] = mapped_column(f'{PREFIX}_id', String(64))",
        "field: Mapped[str] = mapped_column(String(32 + 32))",
        "field: Mapped[str] = mapped_column(TYPES[0])",
        "field: Mapped[str] = mapped_column((lambda: String(64))())",
        "field: Mapped[str] = mapped_column(String(64) if FLAG else String(32))",
        "field: Mapped[str] = mapped_column([String(64) for _ in ITEMS][0])",
        "field: Mapped[str] = mapped_column(sa.String(64))",
    )
    for declaration in declarations:
        _assert_schema_rejected(
            f"""\nclass UnexpectedName(Base):\n    __tablename__ = "v2_material_shadow_unexpected"\n    {declaration}\n"""
        )


def test_material_json_helper_has_one_exact_static_binding() -> None:
    valid = """
_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), "postgresql")
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    payload: Mapped[dict] = mapped_column(_MATERIAL_RULESET_JSON, nullable=False)
"""
    assert parse_material_schema_source(valid) == {
        "v2_material_shadow_unexpected": frozenset({"payload"})
    }
    invalid_preludes = (
        "_MATERIAL_RULESET_JSON = build_type()",
        "_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), DIALECT)",
        "_MATERIAL_RULESET_JSON = JSON().with_variant(build_type(), 'postgresql')",
        "_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), 'postgresql')\n_MATERIAL_RULESET_JSON = JSON()",
        "_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), 'postgresql')\n_MATERIAL_RULESET_JSON += OTHER",
        "_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), 'postgresql')\ndel _MATERIAL_RULESET_JSON",
    )
    for prelude in invalid_preludes:
        _assert_schema_rejected(
            f"""{prelude}\nclass UnexpectedName(Base):\n    __tablename__ = "v2_material_shadow_unexpected"\n    payload: Mapped[dict] = mapped_column(_MATERIAL_RULESET_JSON, nullable=False)\n"""
        )


def test_material_schema_parser_rejects_rebound_or_foreign_helpers() -> None:
    invalid_preludes = (
        "String = build_type()",
        "def mapped_column(*args):\n    return args",
        "class JSON: pass",
        "from attacker import ForeignKey",
        "from sqlalchemy import String as Integer",
        "import attacker as Mapped",
    )
    for prelude in invalid_preludes:
        _assert_schema_rejected(
            f"""{prelude}\nclass UnexpectedName(Base):\n    __tablename__ = "v2_material_shadow_unexpected"\n    value: Mapped[str] = mapped_column(String(64), nullable=False)\n"""
        )

    nested_rebind = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    String = build_type()
    value: Mapped[str] = mapped_column(String(64), nullable=False)
"""
    _assert_schema_rejected(nested_rebind)


_BINDING_FORMS = (
    "def {name}():\n    pass",
    "async def {name}():\n    pass",
    "class {name}:\n    pass",
    "class Container:\n    def {name}(self):\n        pass",
    "def outer():\n    def {name}():\n        pass",
    "def probe({name}):\n    pass",
    "def probe({name}, /):\n    pass",
    "def probe(*, {name}):\n    pass",
    "def probe(*{name}):\n    pass",
    "def probe(**{name}):\n    pass",
    "probe = lambda {name}: None",
    "import attacker as {name}",
    "from attacker import value as {name}",
    "try:\n    operation()\nexcept Exception as {name}:\n    pass",
    "match payload:\n    case _ as {name}:\n        pass",
    "match payload:\n    case [*{name}]:\n        pass",
    'match payload:\n    case {"key": value, **{name}}:\n        pass',
    (
        "match payload:\n"
        "    case Point(value={name}) | Box(value={name}):\n"
        "        pass"
    ),
    "captured = ({name} := build())",
    "for {name} in values:\n    pass",
    "async def probe():\n    async for {name} in values:\n        pass",
    "captured = [item for {name} in values]",
    "with manager() as {name}:\n    pass",
    "async def probe():\n    async with manager() as {name}:\n        pass",
    "{name} = build()",
    "{name}: object = build()",
    "{name} += value",
    "del {name}",
    "def probe():\n    global {name}",
    (
        "def outer():\n"
        "    {name} = value\n"
        "    def inner():\n"
        "        nonlocal {name}"
    ),
)
if hasattr(ast, "TypeAlias"):
    _BINDING_FORMS += ("type {name} = str",)


def _schema_with_binding(binding: str) -> str:
    return f"""{binding}
class V2MaterialBindingProbe(Base):
    __tablename__ = "v2_material_shadow_binding_probe"
    value: Mapped[str] = mapped_column(String(64), nullable=False)
"""


@pytest.mark.parametrize("name", sorted(_PROTECTED_BINDING_NAMES))
@pytest.mark.parametrize("binding_form", _BINDING_FORMS)
def test_material_schema_parser_rejects_recursive_protected_bindings(
    name: str, binding_form: str
) -> None:
    _assert_schema_rejected(_schema_with_binding(binding_form.replace("{name}", name)))


def test_material_schema_parser_rejects_class_local_string_definition() -> None:
    _assert_schema_rejected(
        _schema_with_binding("class Container:\n    def String(self):\n        pass")
    )


def test_material_schema_parser_rejects_match_string_capture() -> None:
    _assert_schema_rejected(
        _schema_with_binding("match payload:\n    case String:\n        pass")
    )


def test_material_schema_parser_rejects_material_json_pattern_rebinding() -> None:
    _assert_schema_rejected(
        """
_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), "postgresql")
match payload:
    case [*_MATERIAL_RULESET_JSON]:
        pass
class V2MaterialBindingProbe(Base):
    __tablename__ = "v2_material_shadow_binding_probe"
    payload: Mapped[dict] = mapped_column(_MATERIAL_RULESET_JSON, nullable=False)
"""
    )


def test_material_schema_parser_allows_pure_helper_references() -> None:
    source = """
def reference_only():
    return (Base, String, mapped_column, _MATERIAL_RULESET_JSON)

_MATERIAL_RULESET_JSON = JSON().with_variant(JSONB(), "postgresql")
class V2MaterialBindingProbe(Base):
    __tablename__ = "v2_material_shadow_binding_probe"
    payload: Mapped[dict] = mapped_column(_MATERIAL_RULESET_JSON, nullable=False)
"""
    assert parse_material_schema_source(source) == {
        "v2_material_shadow_binding_probe": frozenset({"payload"})
    }


_DYNAMIC_NAMESPACE_MUTATIONS = (
    'exec("{name} = build_dynamic_type()")',
    'globals()["{name}"] = build_dynamic_type()',
    'locals()["{name}"] = build_dynamic_type()',
    'vars()["{name}"] = build_dynamic_type()',
    'del globals()["{name}"]',
    'globals()["{name}"] = {name}',
    'builtins.__dict__["{name}"] = build_dynamic_type()',
    'del builtins.__dict__["{name}"]',
    "builtins.{name} = build_dynamic_type()",
    "del builtins.{name}",
    '__builtins__["{name}"] = build_dynamic_type()',
    'dict.__setitem__(namespace, "{name}", build_dynamic_type())',
    'dict.__delitem__(namespace, "{name}")',
    'dict.update(namespace, {"{name}": build_dynamic_type()})',
    "dict.update(namespace, {name}=build_dynamic_type())",
    'dict.update(namespace, **{"{name}": build_dynamic_type()})',
    "namespace.update({name}=build_dynamic_type())",
    'namespace.update(**{"{name}": build_dynamic_type()})',
    'payload = {"{name}": build_dynamic_type()}\n' "dict.update(namespace, **payload)",
)


@pytest.mark.parametrize("name", sorted(_PROTECTED_BINDING_NAMES))
@pytest.mark.parametrize("mutation", _DYNAMIC_NAMESPACE_MUTATIONS)
def test_material_schema_parser_rejects_dynamic_namespace_mutation(
    name: str, mutation: str
) -> None:
    _assert_schema_rejected(_schema_with_binding(mutation.replace("{name}", name)))


@pytest.mark.parametrize(
    "dynamic_source",
    (
        'eval("String")',
        'compile("String = build_dynamic_type()", "<schema>", "exec")',
        'builtins.exec("String = build_dynamic_type()")',
        '__builtins__.eval("String")',
        "runner = exec",
        "runner = builtins.exec",
        "import builtins",
        "import builtins as runtime_builtins",
        "from builtins import exec",
        "from builtins import exec as runner",
        "from attacker import value as globals",
    ),
)
def test_material_schema_parser_rejects_dynamic_namespace_primitives(
    dynamic_source: str,
) -> None:
    _assert_schema_rejected(_schema_with_binding(dynamic_source))


@pytest.mark.parametrize(
    "safe_update",
    (
        "dict.update(namespace, harmless=build_value())",
        'dict.update(namespace, **{"harmless": build_value()})',
        "namespace.update(harmless=build_value())",
        'namespace.update(**{"harmless": build_value()})',
        (
            'namespace.update(**{"harmless": build_value(), '
            '**{"also_harmless": build_value()}})'
        ),
    ),
)
def test_material_schema_parser_allows_static_unprotected_namespace_updates(
    safe_update: str,
) -> None:
    assert parse_material_schema_source(_schema_with_binding(safe_update)) == {
        "v2_material_shadow_binding_probe": frozenset({"value"})
    }


def test_material_schema_parser_closes_table_constraint_ast() -> None:
    valid = """
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    __table_args__ = (
        CheckConstraint("length(value) = 64", name="ck_static"),
        UniqueConstraint("value", name="uq_static"),
        Index("ix_static", "value"),
    )
    value: Mapped[str] = mapped_column(String(64), nullable=False)
"""
    assert parse_material_schema_source(valid, require_table_constraints=True) == {
        "v2_material_shadow_unexpected": frozenset({"value"})
    }

    invalid_items = (
        "build_constraint()",
        "CheckConstraint(build_sql(), name='ck_static')",
        "CheckConstraint(f'{COLUMN}=1', name='ck_static')",
        "CheckConstraint('value=1', name=build_name())",
        "CheckConstraint('value=1', unknown=True)",
        "UniqueConstraint(dynamic_column, name='uq_static')",
        "UniqueConstraint('other', name='uq_static')",
        "Index('ix_static', build_column())",
        "Index(build_name(), 'value')",
        "Index('ix_static', 'other')",
        "Index('ix_static', *COLUMNS)",
        "UniqueConstraint('value', **OPTIONS)",
    )
    for item in invalid_items:
        _assert_schema_rejected(
            f"""\nclass UnexpectedName(Base):\n    __tablename__ = "v2_material_shadow_unexpected"\n    __table_args__ = ({item},)\n    value: Mapped[str] = mapped_column(String(64), nullable=False)\n"""
        )
