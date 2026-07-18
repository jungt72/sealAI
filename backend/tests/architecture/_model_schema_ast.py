"""Fail-closed static extraction of MAT-GOV ORM table declarations."""

from __future__ import annotations

import ast
from pathlib import Path
import symtable


_ALLOWED_BARE_COLUMN_TYPES = frozenset(
    {"Boolean", "Integer", "LargeBinary", "_MATERIAL_RULESET_JSON"}
)
_ALLOWED_ANNOTATION_TYPES = frozenset({"bool", "bytes", "dict", "int", "str"})
_ALLOWED_COLUMN_KEYWORDS = frozenset({"index", "nullable", "primary_key"})
_ALLOWED_FOREIGN_KEYS = frozenset(
    {
        "v2_material_rulesets.ruleset_id",
        "v2_material_ruleset_snapshots.snapshot_id",
        "v2_material_evidence_manifests.manifest_id",
        "v2_material_evidence_snapshots.snapshot_id",
        "v2_material_evidence_review_dossiers.review_id",
        "v2_material_evidence_review_snapshots.review_snapshot_id",
        "v2_material_evidence_runtime_bindings.binding_id",
        "v2_material_evidence_runtime_evaluations.evaluation_id",
        "v2_material_evidence_runtime_pins.pin_id",
        "v2_material_shadow_bindings.binding_id",
        "v2_material_shadow_pins.pin_id",
        "v2_material_shadow_session_versions.session_version_id",
        "v2_material_shadow_outbox.job_id",
        "v2_material_shadow_evaluations.evaluation_id",
    }
)
_PROTECTED_HELPERS = frozenset(
    {
        "Base",
        "Boolean",
        "CheckConstraint",
        "ForeignKey",
        "Index",
        "Integer",
        "JSON",
        "JSONB",
        "LargeBinary",
        "Mapped",
        "String",
        "UniqueConstraint",
        "mapped_column",
    }
)
_PROTECTED_BINDING_NAMES = _PROTECTED_HELPERS | {"_MATERIAL_RULESET_JSON"}
_DYNAMIC_NAMESPACE_PRIMITIVES = frozenset(
    {"__import__", "compile", "eval", "exec", "globals", "locals", "vars"}
)
_DYNAMIC_NAMESPACE_ROOTS = frozenset({"__builtins__", "builtins"})
_DICT_MUTATION_METHODS = frozenset(
    {"__delitem__", "__setitem__", "clear", "pop", "popitem", "setdefault", "update"}
)
_ALLOWED_HELPER_IMPORTS = {
    "sqlalchemy": frozenset(
        {
            "Boolean",
            "CheckConstraint",
            "ForeignKey",
            "Index",
            "Integer",
            "JSON",
            "LargeBinary",
            "String",
            "UniqueConstraint",
        }
    ),
    "sqlalchemy.dialects.postgresql": frozenset({"JSONB"}),
    "sqlalchemy.orm": frozenset({"Mapped", "mapped_column"}),
    "sealai_v2.db.engine": frozenset({"Base"}),
}


def _is_direct_mapped_column(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "mapped_column"
    )


def _is_allowed_annotation_payload(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _ALLOWED_ANNOTATION_TYPES
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.BitOr)
        and _is_allowed_annotation_payload(node.left)
        and isinstance(node.right, ast.Constant)
        and node.right.value is None
    )


def _is_mapped_annotation(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Mapped"
        and _is_allowed_annotation_payload(node.slice)
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
        and len(node.args) == 1
    ):
        return False
    length = node.args[0]
    return (
        isinstance(length, ast.Constant)
        and type(length.value) is int
        and length.value > 0
    )


def _is_allowed_foreign_key(node: ast.AST) -> bool:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ForeignKey"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and type(node.args[0].value) is str
        and node.args[0].value in _ALLOWED_FOREIGN_KEYS
        and len(node.keywords) == 1
    ):
        return False
    keyword = node.keywords[0]
    return (
        keyword.arg == "ondelete"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value == "RESTRICT"
    )


def _validate_column_keywords(call: ast.Call, *, filename: str) -> None:
    names = [keyword.arg for keyword in call.keywords]
    if any(name is None for name in names):
        raise AssertionError(
            f"{filename}:{call.lineno}: dynamic MAT-GOV keyword column arguments"
        )
    if len(names) != len(set(names)):
        raise AssertionError(f"{filename}:{call.lineno}: duplicate column keyword")
    unknown = set(names) - _ALLOWED_COLUMN_KEYWORDS
    if unknown:
        raise AssertionError(
            f"{filename}:{call.lineno}: unrecognized MAT-GOV column keywords"
        )
    if any(
        not isinstance(keyword.value, ast.Constant)
        or type(keyword.value.value) is not bool
        for keyword in call.keywords
    ):
        raise AssertionError(
            f"{filename}:{call.lineno}: MAT-GOV column keyword values must be booleans"
        )


def _physical_column_name(call: ast.Call, *, attribute_name: str, filename: str) -> str:
    if any(isinstance(argument, ast.Starred) for argument in call.args):
        raise AssertionError(
            f"{filename}:{call.lineno}: dynamic MAT-GOV positional column arguments"
        )
    _validate_column_keywords(call, filename=filename)
    if not call.args:
        raise AssertionError(
            f"{filename}:{call.lineno}: MAT-GOV columns require an explicit type"
        )
    arguments = list(call.args)
    first_argument = arguments.pop(0)
    if isinstance(first_argument, ast.Constant) and type(first_argument.value) is str:
        physical_name = first_argument.value
        if not physical_name:
            raise AssertionError(
                f"{filename}:{call.lineno}: empty MAT-GOV physical column name"
            )
        if not arguments:
            raise AssertionError(
                f"{filename}:{call.lineno}: named MAT-GOV column requires a type"
            )
        first_argument = arguments.pop(0)
        column_name = physical_name
    else:
        column_name = attribute_name
    if not _is_allowed_column_type(first_argument):
        raise AssertionError(
            f"{filename}:{call.lineno}: dynamic or unrecognized MAT-GOV column type"
        )
    if arguments:
        if len(arguments) != 1 or not _is_allowed_foreign_key(arguments[0]):
            raise AssertionError(
                f"{filename}:{call.lineno}: dynamic or unrecognized MAT-GOV "
                "column constraint"
            )
    return column_name


def _is_material_json_expression(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "with_variant"
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Name)
        and node.func.value.func.id == "JSON"
        and not node.func.value.args
        and not node.func.value.keywords
        and len(node.args) == 2
        and isinstance(node.args[0], ast.Call)
        and isinstance(node.args[0].func, ast.Name)
        and node.args[0].func.id == "JSONB"
        and not node.args[0].args
        and not node.args[0].keywords
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "postgresql"
        and not node.keywords
    )


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and type(node.value) is str and node.value:
        return node.value
    return None


def _validate_table_constraints(
    model: ast.ClassDef,
    *,
    columns: set[str],
    filename: str,
    required: bool,
) -> None:
    assignments = [
        statement
        for statement in model.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__table_args__"
            for target in statement.targets
        )
    ]
    if not assignments and not required:
        return
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Tuple):
        line = assignments[0].lineno if assignments else model.lineno
        raise AssertionError(
            f"{filename}:{line}: MAT-GOV __table_args__ must be one static tuple"
        )
    names: set[str] = set()
    for item in assignments[0].value.elts:
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name):
            raise AssertionError(
                f"{filename}:{item.lineno}: dynamic MAT-GOV table constraint"
            )
        kind = item.func.id
        if any(isinstance(argument, ast.Starred) for argument in item.args) or any(
            keyword.arg is None for keyword in item.keywords
        ):
            raise AssertionError(
                f"{filename}:{item.lineno}: expanded MAT-GOV table constraint"
            )
        keyword_names = [keyword.arg for keyword in item.keywords]
        if len(keyword_names) != len(set(keyword_names)):
            raise AssertionError(
                f"{filename}:{item.lineno}: duplicate MAT-GOV constraint keyword"
            )
        if kind == "CheckConstraint":
            valid = (
                len(item.args) == 1
                and _literal_string(item.args[0]) is not None
                and keyword_names == ["name"]
            )
            referenced_columns: tuple[str, ...] = ()
        elif kind == "UniqueConstraint":
            referenced_columns = tuple(
                value
                for argument in item.args
                if (value := _literal_string(argument)) is not None
            )
            valid = (
                bool(item.args)
                and len(referenced_columns) == len(item.args)
                and keyword_names == ["name"]
                and set(referenced_columns) <= columns
            )
        elif kind == "Index":
            values = tuple(
                value
                for argument in item.args
                if (value := _literal_string(argument)) is not None
            )
            referenced_columns = values[1:]
            valid = (
                len(values) == len(item.args)
                and len(values) >= 2
                and not item.keywords
                and set(referenced_columns) <= columns
            )
        else:
            valid = False
            referenced_columns = ()
        if not valid:
            raise AssertionError(
                f"{filename}:{item.lineno}: unrecognized MAT-GOV table constraint"
            )
        if kind == "Index":
            name = _literal_string(item.args[0])
        else:
            name = _literal_string(item.keywords[0].value)
        if name is None or name in names:
            raise AssertionError(
                f"{filename}:{item.lineno}: invalid or duplicate constraint name"
            )
        names.add(name)


def _direct_bound_names(node: ast.AST) -> tuple[str, ...]:
    """Return names bound directly by one AST node, never by its descendants."""

    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return (node.id,)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (node.name,)
    if isinstance(node, ast.arg):
        return (node.arg,)
    if isinstance(node, ast.Import):
        return tuple(
            alias.asname or alias.name.split(".", 1)[0] for alias in node.names
        )
    if isinstance(node, ast.ImportFrom):
        return tuple(alias.asname or alias.name for alias in node.names)
    if isinstance(node, ast.ExceptHandler) and node.name:
        return (
            (node.name,)
            if isinstance(node.name, str)
            else _direct_bound_names(node.name)
        )
    if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
        return (node.name,)
    if isinstance(node, ast.MatchMapping) and node.rest:
        return (node.rest,)
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return tuple(node.names)

    type_alias = getattr(ast, "TypeAlias", None)
    if type_alias is not None and isinstance(node, type_alias):
        target = node.name
        if isinstance(target, ast.Name):
            return (target.id,)
        if isinstance(target, str):
            return (target,)
        return ("<unrecognized-type-alias-target>",)
    return ()


def _literal_protected_name(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and type(node.value) is str
        and node.value in _PROTECTED_BINDING_NAMES
    )


def _static_mapping_has_no_protected_keys(node: ast.AST) -> bool:
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=True):
            if key is None:
                if not _static_mapping_has_no_protected_keys(value):
                    return False
            elif not isinstance(key, ast.Constant):
                return False
            elif type(key.value) is str and key.value in _PROTECTED_BINDING_NAMES:
                return False
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and not node.args
    ):
        return _mutation_keywords_are_statically_safe(node.keywords)
    return False


def _mutation_keywords_are_statically_safe(
    keywords: list[ast.keyword],
) -> bool:
    for keyword in keywords:
        if keyword.arg is None:
            if not _static_mapping_has_no_protected_keys(keyword.value):
                return False
        elif keyword.arg in _PROTECTED_BINDING_NAMES:
            return False
    return True


def _literal_mutation_key_is_statically_safe(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and not _literal_protected_name(node)


def _namespace_mutation_is_statically_safe(call: ast.Call) -> bool:
    if not isinstance(call.func, ast.Attribute):
        return True
    method = call.func.attr
    if method not in _DICT_MUTATION_METHODS:
        return True

    direct_dict_call = (
        isinstance(call.func.value, ast.Name) and call.func.value.id == "dict"
    )
    arguments = call.args[1:] if direct_dict_call else call.args
    if direct_dict_call and not call.args:
        return False

    if method == "update":
        return all(
            _static_mapping_has_no_protected_keys(argument) for argument in arguments
        ) and _mutation_keywords_are_statically_safe(call.keywords)
    if method in {"clear", "popitem"}:
        return False
    if call.keywords or not arguments:
        return False
    return _literal_mutation_key_is_statically_safe(arguments[0])


def _validate_dynamic_namespace_boundary(tree: ast.Module, *, filename: str) -> None:
    """Reject syntactic dynamic namespace access; this is not alias analysis."""

    violations: list[ast.AST] = []
    for node in ast.walk(tree):
        bound = set(_direct_bound_names(node))
        if bound & (_DYNAMIC_NAMESPACE_PRIMITIVES | _DYNAMIC_NAMESPACE_ROOTS):
            violations.append(node)
            continue

        if isinstance(node, ast.Import):
            if any(
                alias.name == "builtins"
                or (alias.asname or alias.name.split(".", 1)[0])
                in _DYNAMIC_NAMESPACE_PRIMITIVES
                for alias in node.names
            ):
                violations.append(node)
                continue
        elif isinstance(node, ast.ImportFrom):
            if node.module == "builtins" or any(
                alias.name in _DYNAMIC_NAMESPACE_PRIMITIVES
                or (alias.asname or alias.name) in _DYNAMIC_NAMESPACE_PRIMITIVES
                for alias in node.names
            ):
                violations.append(node)
                continue
        elif isinstance(node, ast.Name):
            if node.id in _DYNAMIC_NAMESPACE_PRIMITIVES | _DYNAMIC_NAMESPACE_ROOTS:
                violations.append(node)
                continue
        elif isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in _DYNAMIC_NAMESPACE_ROOTS
            ):
                violations.append(node)
                continue
            if node.attr == "__dict__" and isinstance(node.ctx, (ast.Store, ast.Del)):
                violations.append(node)
                continue
        elif isinstance(node, ast.Subscript):
            if (
                isinstance(node.ctx, (ast.Store, ast.Del))
                and _literal_protected_name(node.slice)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "__dict__"
            ):
                violations.append(node)
                continue
        elif isinstance(node, ast.Call):
            if not _namespace_mutation_is_statically_safe(node):
                violations.append(node)

    if violations:
        first = min(violations, key=lambda node: getattr(node, "lineno", 1))
        raise AssertionError(
            f"{filename}:{getattr(first, 'lineno', 1)}: dynamic MAT-GOV schema "
            "namespace access is forbidden"
        )


def _symbol_is_binding(symbol: symtable.Symbol) -> bool:
    return any(
        predicate()
        for predicate in (
            symbol.is_assigned,
            symbol.is_imported,
            symbol.is_parameter,
            symbol.is_namespace,
        )
    )


def _validate_symbol_bindings(
    source: str,
    *,
    filename: str,
    allowed_helper_imports: frozenset[str],
    json_binding_allowed: bool,
) -> None:
    """Cross-check compiler-recognized bindings so unknown AST forms fail closed."""

    root = symtable.symtable(source, filename, "exec")

    def inspect(table: symtable.SymbolTable, *, module: bool) -> None:
        for name in _PROTECTED_BINDING_NAMES:
            try:
                symbol = table.lookup(name)
            except KeyError:
                continue
            if not _symbol_is_binding(symbol):
                continue
            allowed = False
            if module and name in allowed_helper_imports:
                allowed = (
                    symbol.is_imported()
                    and not symbol.is_assigned()
                    and not symbol.is_parameter()
                    and not symbol.is_namespace()
                )
            elif module and name == "_MATERIAL_RULESET_JSON" and json_binding_allowed:
                allowed = (
                    symbol.is_assigned()
                    and not symbol.is_imported()
                    and not symbol.is_parameter()
                    and not symbol.is_namespace()
                )
            if not allowed:
                raise AssertionError(
                    f"{filename}: protected MAT-GOV helper was rebound in "
                    f"{table.get_type()} scope {table.get_name()!r}"
                )
        for child in table.get_children():
            inspect(child, module=False)

    inspect(root, module=True)


def _validate_helper_bindings(tree: ast.Module, *, source: str, filename: str) -> None:
    _validate_dynamic_namespace_boundary(tree, filename=filename)
    top_level_ids = {id(statement) for statement in tree.body}
    import_counts = {name: 0 for name in _PROTECTED_HELPERS}
    allowed_binding_nodes: set[tuple[int, str]] = set()

    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom):
            continue
        allowed = _ALLOWED_HELPER_IMPORTS.get(statement.module or "", frozenset())
        for alias in statement.names:
            if alias.name == "*":
                raise AssertionError(
                    f"{filename}:{statement.lineno}: wildcard imports are forbidden"
                )
            bound = alias.asname or alias.name
            if bound not in _PROTECTED_HELPERS:
                continue
            import_counts[bound] += 1
            if alias.asname is None and alias.name in allowed:
                allowed_binding_nodes.add((id(statement), bound))

    duplicated_imports = sorted(
        name for name, count in import_counts.items() if count > 1
    )
    if duplicated_imports:
        raise AssertionError(
            f"{filename}: protected MAT-GOV helpers imported more than once: "
            f"{duplicated_imports}"
        )

    json_assignments = [
        statement
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "_MATERIAL_RULESET_JSON"
    ]
    json_binding_allowed = len(json_assignments) == 1 and _is_material_json_expression(
        json_assignments[0].value
    )
    if json_binding_allowed:
        allowed_binding_nodes.add(
            (id(json_assignments[0].targets[0]), "_MATERIAL_RULESET_JSON")
        )

    protected_bindings: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == "*" for alias in node.names
        ):
            protected_bindings.append(node)
            continue
        for name in _direct_bound_names(node):
            if name not in _PROTECTED_BINDING_NAMES:
                continue
            binding_node_id = id(node)
            if isinstance(node, ast.ImportFrom) and id(node) in top_level_ids:
                binding_node_id = id(node)
            if (binding_node_id, name) not in allowed_binding_nodes:
                protected_bindings.append(node)

    if protected_bindings:
        first = min(protected_bindings, key=lambda node: getattr(node, "lineno", 1))
        raise AssertionError(
            f"{filename}:{getattr(first, 'lineno', 1)}: protected MAT-GOV helper "
            "was rebound"
        )

    json_uses = any(
        isinstance(node, ast.Name) and node.id == "_MATERIAL_RULESET_JSON"
        for node in ast.walk(tree)
    )
    if json_uses and not json_binding_allowed:
        line = json_assignments[0].lineno if json_assignments else 1
        raise AssertionError(
            f"{filename}:{line}: invalid _MATERIAL_RULESET_JSON binding"
        )

    _validate_symbol_bindings(
        source,
        filename=filename,
        allowed_helper_imports=frozenset(
            name for name, count in import_counts.items() if count == 1
        ),
        json_binding_allowed=json_binding_allowed,
    )


def parse_material_schema_source(
    source: str,
    *,
    filename: str = "<material-models>",
    require_table_constraints: bool = False,
) -> dict[str, frozenset[str]]:
    tree = ast.parse(source, filename=filename)
    _validate_helper_bindings(tree, source=source, filename=filename)
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
        _validate_table_constraints(
            node,
            columns=columns,
            filename=filename,
            required=require_table_constraints,
        )
        schema[table_name] = frozenset(columns)

    return schema


def load_material_schema(path: Path) -> dict[str, frozenset[str]]:
    return parse_material_schema_source(
        path.read_text(encoding="utf-8"),
        filename=str(path),
        require_table_constraints=True,
    )
