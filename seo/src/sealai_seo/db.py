from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
    )
    for migration in sorted(migrations_dir.glob("*.sql")):
        version = migration.stem
        exists = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone()
        if exists:
            continue
        conn.executescript(migration.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)",
            (version, utc_now()),
        )
    conn.commit()


def upsert_page(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO gsc_daily_page (
          data_date, site_url, search_type, country, device, page,
          clicks, impressions, ctr, position, data_state, ingested_at_utc, source
        ) VALUES (
          :data_date, :site_url, :search_type, :country, :device, :page,
          :clicks, :impressions, :ctr, :position, :data_state, :ingested_at_utc, :source
        )
        ON CONFLICT(data_date, site_url, search_type, country, device, page)
        DO UPDATE SET
          clicks=excluded.clicks,
          impressions=excluded.impressions,
          ctr=excluded.ctr,
          position=excluded.position,
          data_state=excluded.data_state,
          ingested_at_utc=excluded.ingested_at_utc,
          source=excluded.source
        """,
        row,
    )


def upsert_page_query(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO gsc_daily_page_query (
          data_date, site_url, search_type, country, device, page, query, query_sanitized,
          query_taint, clicks, impressions, ctr, position, data_state, ingested_at_utc, source
        ) VALUES (
          :data_date, :site_url, :search_type, :country, :device, :page, :query, :query_sanitized,
          :query_taint, :clicks, :impressions, :ctr, :position, :data_state, :ingested_at_utc, :source
        )
        ON CONFLICT(data_date, site_url, search_type, country, device, page, query)
        DO UPDATE SET
          query_sanitized=excluded.query_sanitized,
          query_taint=excluded.query_taint,
          clicks=excluded.clicks,
          impressions=excluded.impressions,
          ctr=excluded.ctr,
          position=excluded.position,
          data_state=excluded.data_state,
          ingested_at_utc=excluded.ingested_at_utc,
          source=excluded.source
        """,
        row,
    )
