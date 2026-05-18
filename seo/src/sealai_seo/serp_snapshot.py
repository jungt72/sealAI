from __future__ import annotations

import json
import sqlite3
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from . import db
from .dataforseo_budget import check_budget
from .dataforseo_client import DataForSeoClient, summarize_user_data

SERP_ENDPOINT = "serp/google/organic/live/advanced"


def _domain_matches(domain: str | None, targets: set[str]) -> bool:
    if not domain:
        return False
    normalized = domain.lower().removeprefix("www.")
    return normalized in targets


def extract_serp_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in payload.get("tasks") or []:
        keyword = str(task.get("data", {}).get("keyword") or task.get("keyword") or "").strip().lower()
        for result in task.get("result") or []:
            for item in result.get("items") or []:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                domain = item.get("domain")
                if not domain and isinstance(url, str):
                    domain = urlsplit(url).netloc
                rows.append(
                    {
                        "keyword": keyword,
                        "rank_group": item.get("rank_group"),
                        "rank_absolute": item.get("rank_absolute"),
                        "result_type": item.get("type") or "unknown",
                        "domain": domain,
                        "url": url,
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "breadcrumb": item.get("breadcrumb"),
                        "raw_json": item,
                    }
                )
    return rows


def start_run(
    conn: sqlite3.Connection,
    *,
    planned_cost_usd: float,
    location_code: int,
    language_code: str,
    keywords_count: int,
) -> str:
    run_id = str(uuid4())
    conn.execute(
        """
        INSERT INTO dataforseo_serp_runs (
          run_id, started_at_utc, status, endpoint, planned_cost_usd,
          location_code, language_code, keywords_count
        ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?)
        """,
        (run_id, db.utc_now(), SERP_ENDPOINT, planned_cost_usd, location_code, language_code, keywords_count),
    )
    conn.commit()
    return run_id


def finish_run(conn: sqlite3.Connection, *, run_id: str, status: str, actual_cost_usd: float, error: str | None = None) -> None:
    conn.execute(
        """
        UPDATE dataforseo_serp_runs
        SET finished_at_utc = ?, status = ?, actual_cost_usd = ?, error_message = ?
        WHERE run_id = ?
        """,
        (db.utc_now(), status, actual_cost_usd, error, run_id),
    )
    conn.commit()


def upsert_serp_results(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    rows: list[dict[str, Any]],
    location_code: int,
    language_code: str,
    target_domains: set[str],
) -> int:
    collected = db.utc_now()
    for row in rows:
        conn.execute(
            """
            INSERT INTO dataforseo_serp_results (
              run_id, keyword, location_code, language_code, collected_at_utc,
              rank_group, rank_absolute, result_type, domain, url, title,
              description, breadcrumb, is_target_domain, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                row["keyword"],
                location_code,
                language_code,
                collected,
                row.get("rank_group"),
                row.get("rank_absolute"),
                row.get("result_type") or "unknown",
                row.get("domain"),
                row.get("url"),
                row.get("title"),
                row.get("description"),
                row.get("breadcrumb"),
                1 if _domain_matches(row.get("domain"), target_domains) else 0,
                json.dumps(row.get("raw_json") or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
    conn.commit()
    return len(rows)


def run_serp_snapshot(
    conn: sqlite3.Connection,
    *,
    client: DataForSeoClient,
    keywords: list[str],
    location_code: int,
    language_code: str,
    planned_cost_usd: float,
    max_run_cost_usd: float,
    target_domains: list[str],
    depth: int,
    dry_run: bool,
) -> dict[str, Any]:
    targets = {domain.lower().removeprefix("www.") for domain in target_domains}
    user_data = summarize_user_data(client.user_data())
    balance = float(user_data.get("balance") or 0)
    decision = check_budget(
        planned_cost_usd=planned_cost_usd,
        max_run_cost_usd=max_run_cost_usd,
        balance_usd=balance,
    )
    if not decision.allowed:
        return {
            "dry_run": dry_run,
            "allowed": False,
            "reason": decision.reason,
            "planned_cost_usd": planned_cost_usd,
            "max_run_cost_usd": max_run_cost_usd,
            "balance_usd": balance,
            "keywords_count": len(keywords),
        }
    if dry_run:
        return {
            "dry_run": True,
            "allowed": True,
            "planned_cost_usd": planned_cost_usd,
            "max_run_cost_usd": max_run_cost_usd,
            "balance_usd": balance,
            "keywords_count": len(keywords),
            "keywords": keywords,
            "target_domains": sorted(targets),
            "depth": depth,
        }

    run_id = start_run(
        conn,
        planned_cost_usd=planned_cost_usd,
        location_code=location_code,
        language_code=language_code,
        keywords_count=len(keywords),
    )
    try:
        payload = client.serp_google_organic_live_advanced(
            keywords=keywords,
            location_code=location_code,
            language_code=language_code,
            depth=depth,
        )
        actual_cost = float(payload.get("cost") or 0)
        rows = extract_serp_items(payload)
        count = upsert_serp_results(
            conn,
            run_id=run_id,
            rows=rows,
            location_code=location_code,
            language_code=language_code,
            target_domains=targets,
        )
        finish_run(conn, run_id=run_id, status="success", actual_cost_usd=actual_cost)
        return {
            "dry_run": False,
            "allowed": True,
            "run_id": run_id,
            "status_code": payload.get("status_code"),
            "status_message": payload.get("status_message"),
            "actual_cost_usd": actual_cost,
            "rows": count,
            "keywords_count": len(keywords),
            "target_hits": sum(1 for row in rows if _domain_matches(row.get("domain"), targets)),
        }
    except Exception as exc:
        finish_run(conn, run_id=run_id, status="failed", actual_cost_usd=0, error=str(exc)[:500])
        raise
