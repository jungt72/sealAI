from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

from . import db
from .config import MAX_ROWS_PER_REQUEST
from .safety import enforce_date_range, enforce_request_budget
from .text_sanitizer import QUERY_TAINT, sanitize_text


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def data_state(data_date: date, today: date | None = None, force_provisional: bool = False) -> str:
    if force_provisional:
        return "provisional"
    today = today or datetime.now(timezone.utc).date()
    return "provisional" if data_date >= today - timedelta(days=2) else "final"


def log_json(log_dir: Path, event: dict) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts_utc": db.utc_now(),
        **event,
    }
    with (log_dir / "gsc_sync.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _metrics(row: dict) -> dict:
    return {
        "clicks": float(row.get("clicks", 0)),
        "impressions": float(row.get("impressions", 0)),
        "ctr": float(row.get("ctr", 0)),
        "position": float(row.get("position", 0)),
    }


def ingest_rows(conn, *, site_url: str, search_type: str, data_date_value: date, dimensions: list[str], rows: list[dict], force_provisional: bool = False) -> int:
    ingested_at = db.utc_now()
    state = data_state(data_date_value, force_provisional=force_provisional)
    for item in rows:
        keys = item.get("keys", [])
        metrics = _metrics(item)
        if dimensions == ["page"]:
            db.upsert_page(
                conn,
                {
                    "data_date": data_date_value.isoformat(),
                    "site_url": site_url,
                    "search_type": search_type,
                    "country": "ALL",
                    "device": "ALL",
                    "page": keys[0],
                    **metrics,
                    "data_state": state,
                    "ingested_at_utc": ingested_at,
                    "source": "gsc_api",
                },
            )
        elif dimensions == ["page", "query"]:
            query = keys[1]
            db.upsert_page_query(
                conn,
                {
                    "data_date": data_date_value.isoformat(),
                    "site_url": site_url,
                    "search_type": search_type,
                    "country": "ALL",
                    "device": "ALL",
                    "page": keys[0],
                    "query": query,
                    "query_sanitized": sanitize_text(query),
                    "query_taint": QUERY_TAINT,
                    **metrics,
                    "data_state": state,
                    "ingested_at_utc": ingested_at,
                    "source": "gsc_api",
                },
            )
        else:
            raise ValueError(f"unsupported dimensions: {dimensions}")
    return len(rows)


def sync(conn, *, client, site_url: str, date_from: date, date_to: date, search_type: str = "web", log_dir: Path = Path("/var/seo/logs"), dry_run: bool = False, force_provisional: bool = False) -> dict:
    enforce_date_range(date_from, date_to)
    run_id = str(uuid4())
    started = db.utc_now()
    requests_made = 0
    rows_fetched = 0
    if not dry_run:
        conn.execute(
            "INSERT INTO gsc_sync_runs (run_id, started_at_utc, status, site_url, search_type, date_from, date_to) VALUES (?, ?, 'running', ?, ?, ?, ?)",
            (run_id, started, site_url, search_type, date_from.isoformat(), date_to.isoformat()),
        )
        conn.commit()
    try:
        for current_date in date_range(date_from, date_to):
            for dimensions in (["page"], ["page", "query"]):
                start_row = 0
                while True:
                    enforce_request_budget(requests_made + 1)
                    requests_made += 1
                    if dry_run:
                        log_json(log_dir, {"level": "info", "event": "dry_run_fetch", "site_url": site_url, "data_date": current_date.isoformat(), "dimensions": dimensions, "start_row": start_row})
                        break
                    response = client.query(date=current_date.isoformat(), search_type=search_type, dimensions=dimensions, start_row=start_row)
                    rows = response.get("rows", [])
                    rows_fetched += len(rows)
                    ingest_rows(conn, site_url=site_url, search_type=search_type, data_date_value=current_date, dimensions=dimensions, rows=rows, force_provisional=force_provisional)
                    conn.commit()
                    log_json(log_dir, {"level": "info", "event": "gsc_page_fetched", "site_url": site_url, "data_date": current_date.isoformat(), "dimensions": dimensions, "start_row": start_row, "row_count": len(rows)})
                    if not rows:
                        break
                    start_row += MAX_ROWS_PER_REQUEST
        if not dry_run:
            conn.execute("UPDATE gsc_sync_runs SET status='success', finished_at_utc=?, requests_made=?, rows_fetched=? WHERE run_id=?", (db.utc_now(), requests_made, rows_fetched, run_id))
            conn.commit()
        return {"run_id": run_id, "requests_made": requests_made, "rows_fetched": rows_fetched, "dry_run": dry_run}
    except Exception as exc:
        log_json(log_dir, {"level": "error", "event": "gsc_sync_failed", "site_url": site_url, "error_message": str(exc)})
        if not dry_run:
            conn.execute("UPDATE gsc_sync_runs SET status='failed', finished_at_utc=?, requests_made=?, rows_fetched=?, error_message=? WHERE run_id=?", (db.utc_now(), requests_made, rows_fetched, str(exc), run_id))
            conn.commit()
        raise
