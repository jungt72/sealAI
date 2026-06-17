"""V2 schema migration — green-field single schema (build-spec §3).

``up`` creates the V2 tables; ``down`` drops them. Both are verified on a FRESH non-prod DB before
prod (self-gate). Reversibility for prod DATA rests on the DB snapshot (the ops gate), not on
``down`` — ``down`` is destructive (the nature of an initial schema's reverse). Alembic is the future
path once the schema evolves; for the first schema a create_all/drop_all migration is the smallest
reversible unit.

Usage (DB host is only reachable from inside the docker network → run via the backend-v2 container):

    python -m sealai_v2.db.migrate up   --url postgresql+psycopg2://…@postgres:5432/sealai_v2
    python -m sealai_v2.db.migrate down --url postgresql+psycopg2://…@postgres:5432/sealai_v2

``--url`` falls back to ``SEALAI_V2_DATABASE_URL``. The value is never logged.
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import inspect

import sealai_v2.db.models  # noqa: F401 — registers the tables on Base.metadata
from sealai_v2.db.engine import Base, make_engine


def _resolve_url(arg_url: str | None) -> str:
    url = arg_url or os.environ.get("SEALAI_V2_DATABASE_URL")
    if not url:
        sys.exit("no DB url: pass --url or set SEALAI_V2_DATABASE_URL")
    return url


def up(engine) -> list[str]:
    Base.metadata.create_all(engine)
    return sorted(inspect(engine).get_table_names())


def down(engine) -> list[str]:
    Base.metadata.drop_all(engine)
    return sorted(inspect(engine).get_table_names())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sealai_v2.db.migrate")
    parser.add_argument("command", choices=["up", "down"])
    parser.add_argument("--url", default=None)
    args = parser.parse_args(argv)

    engine = make_engine(_resolve_url(args.url))
    expected = sorted(Base.metadata.tables)
    if args.command == "up":
        remaining = up(engine)
        present = [t for t in expected if t in remaining]
        print(f"up: ensured {len(present)}/{len(expected)} V2 tables: {present}")
    else:
        remaining = down(engine)
        leftover = [t for t in expected if t in remaining]
        print(
            f"down: dropped V2 tables; leftover from {expected}: {leftover or 'none'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
