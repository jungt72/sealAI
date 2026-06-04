from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from . import db
from .indexability import sitemap_urls


def _index_status(payload: dict) -> dict:
    return (
        payload.get("inspectionResult", {})
        .get("indexStatusResult", {})
        if isinstance(payload, dict)
        else {}
    )


def store_result(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    site_url: str,
    inspection_url: str,
    payload: dict,
) -> None:
    status = _index_status(payload)
    conn.execute(
        """
        INSERT INTO gsc_url_inspection (
          run_id, inspection_url, site_url, verdict, coverage_state, indexing_state,
          page_fetch_state, robots_txt_state, google_canonical, user_canonical,
          last_crawl_time, sitemap_json, raw_json, inspected_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            inspection_url,
            site_url,
            status.get("verdict"),
            status.get("coverageState"),
            status.get("indexingState"),
            status.get("pageFetchState"),
            status.get("robotsTxtState"),
            status.get("googleCanonical"),
            status.get("userCanonical"),
            status.get("lastCrawlTime"),
            json.dumps(status.get("sitemap") or [], ensure_ascii=False, sort_keys=True),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            db.utc_now(),
        ),
    )


def inspect_urls(
    conn: sqlite3.Connection,
    *,
    client,
    site_url: str,
    urls: list[str],
    dry_run: bool = False,
) -> dict:
    run_id = str(uuid4())
    conn.execute(
        """
        INSERT INTO gsc_url_inspection_runs (
          run_id, started_at_utc, status, site_url, urls_requested
        ) VALUES (?, ?, 'running', ?, ?)
        """,
        (run_id, db.utc_now(), site_url, len(urls)),
    )
    conn.commit()
    inspected = 0
    try:
        for url in urls:
            if dry_run:
                inspected += 1
                continue
            payload = client.inspect_url(inspection_url=url, site_url=site_url)
            store_result(conn, run_id=run_id, site_url=site_url, inspection_url=url, payload=payload)
            inspected += 1
            conn.commit()
        conn.execute(
            """
            UPDATE gsc_url_inspection_runs
            SET status = 'success', finished_at_utc = ?, urls_inspected = ?
            WHERE run_id = ?
            """,
            (db.utc_now(), inspected, run_id),
        )
        conn.commit()
        return {"run_id": run_id, "status": "success", "urls_requested": len(urls), "urls_inspected": inspected, "dry_run": dry_run}
    except Exception as exc:
        conn.execute(
            """
            UPDATE gsc_url_inspection_runs
            SET status = 'failed', finished_at_utc = ?, urls_inspected = ?, error_message = ?
            WHERE run_id = ?
            """,
            (db.utc_now(), inspected, str(exc)[:500], run_id),
        )
        conn.commit()
        raise


def urls_from_sitemap_or_args(*, sitemap_url: str | None, urls: list[str] | None, limit: int) -> list[str]:
    selected: list[str] = []
    if urls:
        selected.extend(urls)
    if sitemap_url:
        selected.extend(sitemap_urls(sitemap_url, limit=limit))
    deduped = list(dict.fromkeys(selected))
    return deduped[:limit]
