"""Fail-closed static extraction of MAT-GOV ORM table declarations."""

from __future__ import annotations

import ast
from pathlib import Path


def _is_direct_mapped_column(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "mapped_column"
    )


def _mapped_column_calls(node: ast.ClassDef) -> list[ast.Call]:
    return [
        candidate
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Name)
        and candidate.func.id == "mapped_column"
    ]


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

        material_class = node.name.startswith("V2Material")
        if not material_class and not table_assignments:
            continue
        if material_class and id(node) not in top_level_classes:
            raise AssertionError(
                f"{filename}:{node.lineno}: nested MAT-GOV model class is forbidden"
            )
        if len(table_assignments) != 1:
            if material_class:
                raise AssertionError(
                    f"{filename}:{node.lineno}: MAT-GOV model requires one literal "
                    "__tablename__"
                )
            continue

        assignment = table_assignments[0]
        if len(assignment.targets) != 1 or not (
            isinstance(assignment.value, ast.Constant)
            and type(assignment.value.value) is str
        ):
            if material_class:
                raise AssertionError(
                    f"{filename}:{assignment.lineno}: dynamic MAT-GOV table name"
                )
            continue
        table_name = assignment.value.value
        if material_class and not table_name.startswith("v2_material_"):
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
            if not _is_direct_mapped_column(statement.value):
                raise AssertionError(
                    f"{filename}:{statement.lineno}: MAT-GOV column must use direct "
                    "mapped_column"
                )
            column_name = statement.target.id
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
                f"{filename}:{first.lineno}: dynamic or unannotated MAT-GOV column"
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
