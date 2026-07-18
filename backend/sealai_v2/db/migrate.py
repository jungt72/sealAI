"""Alembic-backed schema management for the active V2 database.

The first Alembic revision can safely adopt the pre-Alembic production schema,
but only after validating that every expected V2 table and column exists. All
later schema changes must be explicit Alembic revisions. Production code never
calls ``create_all`` directly.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

import sealai_v2.db.models  # noqa: F401 - registers the V2 metadata
from sealai_v2.db.engine import Base, make_engine

_SCRIPT_LOCATION = Path(__file__).resolve().parent / "migrations"


def _resolve_url(arg_url: str | None) -> str:
    url = arg_url or os.environ.get("SEALAI_V2_DATABASE_URL")
    if not url:
        raise SystemExit("no DB url: pass --url or set SEALAI_V2_DATABASE_URL")
    return url


def _config(*, url: str | None = None, connection=None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    if url:
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def _upgrade_engine(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        command.upgrade(_config(connection=connection), revision)


def up(engine: Engine) -> list[str]:
    """Compatibility entrypoint used by tests and recovery scripts."""
    _upgrade_engine(engine)
    return sorted(inspect(engine).get_table_names())


def down(engine: Engine) -> list[str]:
    """Development-only full rollback of the initial V2 schema."""
    with engine.begin() as connection:
        command.downgrade(_config(connection=connection), "base")
    return sorted(inspect(engine).get_table_names())


def migration_status(engine: Engine) -> tuple[str | None, str]:
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    head = ScriptDirectory.from_config(_config()).get_current_head()
    assert head is not None
    return current, head


def validate_schema(engine: Engine) -> None:
    """Fail if the database is not at Alembic head or lacks modeled tables/columns."""
    current, head = migration_status(engine)
    if current != head:
        raise RuntimeError(
            f"database revision {current or 'unversioned'} is not head {head}"
        )

    db = inspect(engine)
    table_names = set(db.get_table_names())
    expected_tables = set(Base.metadata.tables)
    missing_tables = sorted(expected_tables - table_names)
    if missing_tables:
        raise RuntimeError(f"database is missing V2 tables: {missing_tables}")

    missing_columns: dict[str, list[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        actual = {column["name"] for column in db.get_columns(table_name)}
        missing = sorted(set(table.columns.keys()) - actual)
        if missing:
            missing_columns[table_name] = missing
    if missing_columns:
        raise RuntimeError(f"database is missing V2 columns: {missing_columns}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sealai_v2.db.migrate")
    parser.add_argument("command", choices=["upgrade", "check", "current", "down"])
    parser.add_argument("--url", default=None)
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="required for the development-only 'down' command",
    )
    args = parser.parse_args(argv)

    engine = make_engine(_resolve_url(args.url))
    if args.command == "upgrade":
        _upgrade_engine(engine)
        validate_schema(engine)
        current, _head = migration_status(engine)
        print(f"upgrade: database is at {current}")
    elif args.command == "check":
        validate_schema(engine)
        current, _head = migration_status(engine)
        print(f"check: database is at {current}; schema matches metadata")
    elif args.command == "current":
        current, head = migration_status(engine)
        print(f"current: {current or 'unversioned'}; head: {head}")
    else:
        if not args.allow_destructive:
            raise SystemExit(
                "refusing destructive downgrade without --allow-destructive"
            )
        down(engine)
        print("down: V2 schema removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
