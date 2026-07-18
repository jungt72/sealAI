"""Exact, read-only structural fingerprints for unpublished MAT-GOV migrations."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import sqlalchemy as sa


_SPACE = re.compile(r"\s+")


def _normalized(value: object, *, schema: str) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        return _SPACE.sub(" ", value.replace(f'"{schema}".', '"<schema>".')).strip()
    if isinstance(value, dict):
        return {
            str(key): _normalized(item, schema=schema)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalized(item, schema=schema) for item in value]
    return str(value)


def _inspector_manifest(
    bind: sa.engine.Connection,
    tables: tuple[str, ...],
    *,
    schema: str,
) -> dict[str, Any]:
    inspector = sa.inspect(bind)
    result: dict[str, Any] = {}
    for table in tables:
        columns = []
        for position, column in enumerate(inspector.get_columns(table, schema=schema)):
            columns.append(
                {
                    "position": position,
                    "name": column["name"],
                    "type": column["type"].compile(dialect=bind.dialect),
                    "nullable": column["nullable"],
                    "default": column.get("default"),
                    "computed": column.get("computed"),
                    "identity": column.get("identity"),
                }
            )
        foreign_keys = []
        for foreign_key in inspector.get_foreign_keys(table, schema=schema):
            foreign_keys.append(
                {
                    "name": foreign_key.get("name"),
                    "columns": foreign_key.get("constrained_columns") or [],
                    "referred_schema": foreign_key.get("referred_schema") or schema,
                    "referred_table": foreign_key.get("referred_table"),
                    "referred_columns": foreign_key.get("referred_columns") or [],
                    "options": foreign_key.get("options") or {},
                }
            )
        result[table] = {
            "columns": columns,
            "primary_key": inspector.get_pk_constraint(table, schema=schema),
            "foreign_keys": sorted(
                foreign_keys, key=lambda item: (str(item["name"]), item["columns"])
            ),
            "checks": sorted(
                inspector.get_check_constraints(table, schema=schema),
                key=lambda item: str(item.get("name")),
            ),
            "uniques": sorted(
                inspector.get_unique_constraints(table, schema=schema),
                key=lambda item: str(item.get("name")),
            ),
            "indexes": sorted(
                inspector.get_indexes(table, schema=schema),
                key=lambda item: str(item.get("name")),
            ),
        }
    return result


def _postgres_catalog_manifest(
    bind: sa.engine.Connection,
    tables: tuple[str, ...],
    *,
    schema: str,
) -> dict[str, Any]:
    parameters = {"schema": schema, "tables": list(tables)}
    constraints = bind.execute(
        sa.text(
            """
            SELECT c.relname AS table_name, con.conname, con.contype,
                   con.convalidated, con.condeferrable, con.condeferred,
                   pg_get_constraintdef(con.oid, true) AS definition
              FROM pg_constraint con
              JOIN pg_class c ON c.oid=con.conrelid
              JOIN pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname=:schema AND c.relname=ANY(:tables)
             ORDER BY c.relname, con.conname
            """
        ),
        parameters,
    ).mappings()
    indexes = bind.execute(
        sa.text(
            """
            SELECT table_rel.relname AS table_name, index_rel.relname AS index_name,
                   access_method.amname AS access_method, idx.indisunique,
                   idx.indisvalid, idx.indisready,
                   pg_get_indexdef(idx.indexrelid) AS definition,
                   pg_get_expr(idx.indpred, idx.indrelid, true) AS predicate,
                   pg_get_expr(idx.indexprs, idx.indrelid, true) AS expressions
              FROM pg_index idx
              JOIN pg_class table_rel ON table_rel.oid=idx.indrelid
              JOIN pg_class index_rel ON index_rel.oid=idx.indexrelid
              JOIN pg_namespace n ON n.oid=table_rel.relnamespace
              JOIN pg_am access_method ON access_method.oid=index_rel.relam
             WHERE n.nspname=:schema AND table_rel.relname=ANY(:tables)
             ORDER BY table_rel.relname, index_rel.relname
            """
        ),
        parameters,
    ).mappings()
    triggers = bind.execute(
        sa.text(
            """
            SELECT c.relname AS table_name, t.tgname,
                   pg_get_triggerdef(t.oid, true) AS definition,
                   pn.nspname AS function_schema, p.proname AS function_name,
                   p.prosrc, l.lanname AS language, p.provolatile,
                   p.prosecdef, p.proleakproof, p.proconfig
              FROM pg_trigger t
              JOIN pg_class c ON c.oid=t.tgrelid
              JOIN pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_proc p ON p.oid=t.tgfoid
              JOIN pg_namespace pn ON pn.oid=p.pronamespace
              JOIN pg_language l ON l.oid=p.prolang
             WHERE NOT t.tgisinternal AND n.nspname=:schema
               AND c.relname=ANY(:tables)
             ORDER BY c.relname, t.tgname
            """
        ),
        parameters,
    ).mappings()
    functions = bind.execute(
        sa.text(
            """
            SELECT n.nspname AS function_schema, p.proname AS function_name,
                   pg_get_function_identity_arguments(p.oid) AS identity_arguments,
                   pg_get_function_result(p.oid) AS result_type,
                   p.prosrc, l.lanname AS language, p.provolatile,
                   p.prosecdef, p.proleakproof, p.proconfig
              FROM pg_proc p
              JOIN pg_namespace n ON n.oid=p.pronamespace
              JOIN pg_language l ON l.oid=p.prolang
             WHERE n.nspname=:schema AND p.proname IN (
                   SELECT DISTINCT trigger_function.proname
                     FROM pg_trigger trigger
                     JOIN pg_class trigger_table ON trigger_table.oid=trigger.tgrelid
                     JOIN pg_namespace trigger_schema
                       ON trigger_schema.oid=trigger_table.relnamespace
                     JOIN pg_proc trigger_function
                       ON trigger_function.oid=trigger.tgfoid
                    WHERE NOT trigger.tgisinternal
                      AND trigger_schema.nspname=:schema
                      AND trigger_table.relname=ANY(:tables)
             )
             ORDER BY p.proname, identity_arguments
            """
        ),
        parameters,
    ).mappings()
    return {
        "constraints": [dict(row) for row in constraints],
        "functions": [dict(row) for row in functions],
        "indexes": [dict(row) for row in indexes],
        "triggers": [dict(row) for row in triggers],
    }


def _sqlite_catalog_manifest(
    bind: sa.engine.Connection, tables: tuple[str, ...]
) -> list[dict[str, Any]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT type, name, tbl_name, sql
              FROM sqlite_master
             WHERE tbl_name IN :tables AND type IN ('table','index','trigger')
             ORDER BY type, tbl_name, name
            """
        ).bindparams(sa.bindparam("tables", expanding=True)),
        {"tables": list(tables)},
    ).mappings()
    return [dict(row) for row in rows]


def schema_fingerprint(
    bind: sa.engine.Connection,
    tables: tuple[str, ...],
) -> str:
    """Hash the complete structural contract without executing application models."""

    schema = sa.inspect(bind).default_schema_name
    manifest: dict[str, Any] = {
        "dialect": bind.dialect.name,
        "tables": _inspector_manifest(bind, tables, schema=schema),
    }
    if bind.dialect.name == "postgresql":
        manifest["catalog"] = _postgres_catalog_manifest(bind, tables, schema=schema)
    elif bind.dialect.name == "sqlite":
        manifest["catalog"] = _sqlite_catalog_manifest(bind, tables)
    else:
        raise RuntimeError(
            f"MAT-GOV adoption fingerprint unsupported for {bind.dialect.name!r}"
        )
    normalized = _normalized(manifest, schema=schema)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_schema_fingerprint(
    bind: sa.engine.Connection,
    tables: tuple[str, ...],
    expected_by_dialect: dict[str, frozenset[str]],
    *,
    contract: str,
) -> None:
    actual = schema_fingerprint(bind, tables)
    expected = expected_by_dialect.get(bind.dialect.name, frozenset())
    if actual not in expected:
        raise RuntimeError(
            f"{contract} structural adoption fingerprint mismatch: {actual}"
        )
