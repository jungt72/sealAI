"""Fail-closed static extraction of MAT-GOV ORM table declarations."""

from __future__ import annotations

import ast
from pathlib import Path


_ALLOWED_BARE_COLUMN_TYPES = frozenset(
    {"Boolean", "Integer", "LargeBinary", "_MATERIAL_RULESET_JSON"}
)


def _is_direct_mapped_column(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "mapped_column"
    )


def _is_mapped_annotation(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Mapped"
    )


def _mapped_column_calls(node: ast.ClassDef) -> list[ast.Call]:
    return [
        candidate
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Name)
        and candidate.func.id == "mapped_column"
    ]


def _is_direct_base_model(node: ast.ClassDef) -> bool:
    return (
        len(node.bases) == 1
        and isinstance(node.bases[0], ast.Name)
        and node.bases[0].id == "Base"
    )


def _is_allowed_column_type(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _ALLOWED_BARE_COLUMN_TYPES
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "String"
        and not node.keywords
        and len(node.args) <= 1
    ):
        return False
    if not node.args:
        return True
    length = node.args[0]
    return (
        isinstance(length, ast.Constant)
        and type(length.value) is int
        and length.value > 0
    )


def _physical_column_name(call: ast.Call, *, attribute_name: str, filename: str) -> str:
    if any(isinstance(argument, ast.Starred) for argument in call.args):
        raise AssertionError(
            f"{filename}:{call.lineno}: dynamic MAT-GOV positional column arguments"
        )
    if any(keyword.arg is None for keyword in call.keywords):
        raise AssertionError(
            f"{filename}:{call.lineno}: dynamic MAT-GOV keyword column arguments"
        )
    if any(keyword.arg == "name" for keyword in call.keywords):
        raise AssertionError(
            f"{filename}:{call.lineno}: MAT-GOV physical column names must use "
            "the first literal mapped_column argument"
        )
    if not call.args:
        return attribute_name
    first_argument = call.args[0]
    if isinstance(first_argument, ast.Constant) and type(first_argument.value) is str:
        physical_name = first_argument.value
        if not physical_name:
            raise AssertionError(
                f"{filename}:{call.lineno}: empty MAT-GOV physical column name"
            )
        return physical_name
    if _is_allowed_column_type(first_argument):
        return attribute_name
    raise AssertionError(
        f"{filename}:{call.lineno}: dynamic or unrecognized MAT-GOV first "
        "mapped_column argument"
    )


def parse_material_schema_source(
    source: str, *, filename: str = "<material-models>"
) -> dict[str, frozenset[str]]:
    tree = ast.parse(source, filename=filename)
    top_level_classes = {
        id(node) for node in tree.body if isinstance(node, ast.ClassDef)
    }
    schema: dict[str, frozenset[str]] = {}

    for node in (
        candidate for candidate in ast.walk(tree) if isinstance(candidate, ast.ClassDef)
    ):
        table_assignments: list[ast.Assign] = []
        for statement in node.body:
            if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__tablename__"
                for target in statement.targets
            ):
                table_assignments.append(statement)

        named_material_class = node.name.startswith("V2Material")
        direct_base_model = _is_direct_base_model(node)
        has_base_reference = any(
            isinstance(base, ast.Name) and base.id == "Base" for base in node.bases
        )
        literal_material_table = any(
            isinstance(assignment.value, ast.Constant)
            and type(assignment.value.value) is str
            and assignment.value.value.startswith("v2_material_")
            for assignment in table_assignments
        )
        material_candidate = named_material_class or literal_material_table

        if has_base_reference and not direct_base_model:
            raise AssertionError(
                f"{filename}:{node.lineno}: ORM models must directly inherit Base only"
            )
        if not direct_base_model and not material_candidate:
            continue
        if not direct_base_model:
            raise AssertionError(
                f"{filename}:{node.lineno}: MAT-GOV model must directly inherit Base"
            )
        if id(node) not in top_level_classes:
            raise AssertionError(
                f"{filename}:{node.lineno}: nested ORM model class is forbidden"
            )
        if len(table_assignments) != 1:
            raise AssertionError(
                f"{filename}:{node.lineno}: ORM model requires one literal "
                "__tablename__"
            )

        assignment = table_assignments[0]
        if len(assignment.targets) != 1 or not (
            isinstance(assignment.value, ast.Constant)
            and type(assignment.value.value) is str
        ):
            raise AssertionError(
                f"{filename}:{assignment.lineno}: dynamic ORM table name"
            )
        table_name = assignment.value.value
        if named_material_class and not table_name.startswith("v2_material_"):
            raise AssertionError(
                f"{filename}:{assignment.lineno}: unrecognized MAT-GOV table name"
            )
        if not table_name.startswith("v2_material_"):
            continue
        if table_name in schema:
            raise AssertionError(
                f"{filename}:{assignment.lineno}: duplicate MAT-GOV table {table_name}"
            )

        columns: set[str] = set()
        recognized_calls: set[int] = set()
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign):
                continue
            if not isinstance(statement.target, ast.Name):
                raise AssertionError(
                    f"{filename}:{statement.lineno}: dynamic MAT-GOV column target"
                )
            if not _is_mapped_annotation(statement.annotation):
                raise AssertionError(
                    f"{filename}:{statement.lineno}: MAT-GOV columns require a "
                    "Mapped[...] annotation"
                )
            if not _is_direct_mapped_column(statement.value):
                raise AssertionError(
                    f"{filename}:{statement.lineno}: MAT-GOV column must use direct "
                    "mapped_column"
                )
            column_name = _physical_column_name(
                statement.value,
                attribute_name=statement.target.id,
                filename=filename,
            )
            if column_name in columns:
                raise AssertionError(
                    f"{filename}:{statement.lineno}: duplicate MAT-GOV column "
                    f"{table_name}.{column_name}"
                )
            columns.add(column_name)
            recognized_calls.add(id(statement.value))

        unrecognized_calls = [
            call
            for call in _mapped_column_calls(node)
            if id(call) not in recognized_calls
        ]
        if unrecognized_calls:
            first = min(unrecognized_calls, key=lambda call: call.lineno)
            raise AssertionError(
                f"{filename}:{first.lineno}: MAT-GOV columns require typed "
                "Mapped[...] AnnAssign declarations"
            )
        if not columns:
            raise AssertionError(
                f"{filename}:{node.lineno}: MAT-GOV table has no static columns"
            )
        schema[table_name] = frozenset(columns)

    return schema


def load_material_schema(path: Path) -> dict[str, frozenset[str]]:
    return parse_material_schema_source(
        path.read_text(encoding="utf-8"), filename=str(path)
    )
