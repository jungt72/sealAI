from __future__ import annotations

import csv
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from . import db
from .dataforseo_budget import check_budget
from .dataforseo_client import DataForSeoClient, summarize_user_data

SEARCH_VOLUME_ENDPOINT = "keywords_data/google_ads/search_volume/live"


def load_seed_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"keyword", "cluster", "intent", "page_type", "v8_positioning", "rfq_relevance", "priority"}
    missing = required - set(rows[0].keys() if rows else [])
    if missing:
        raise ValueError(f"Missing seed columns: {', '.join(sorted(missing))}")
    return rows


def upsert_seed_keywords(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    now = db.utc_now()
    for row in rows:
        conn.execute(
            """
            INSERT INTO keyword_seed (
              keyword, cluster, intent, page_type, v8_positioning, rfq_relevance, priority, created_at_utc, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(keyword) DO UPDATE SET
              cluster=excluded.cluster,
              intent=excluded.intent,
              page_type=excluded.page_type,
              v8_positioning=excluded.v8_positioning,
              rfq_relevance=excluded.rfq_relevance,
              priority=excluded.priority,
              source=excluded.source
            """,
            (
                row["keyword"].strip().lower(),
                row["cluster"].strip(),
                row["intent"].strip(),
                row["page_type"].strip(),
                row["v8_positioning"].strip(),
                row["rfq_relevance"].strip(),
                int(row["priority"]),
                now,
                row.get("source", "run0_seed"),
            ),
        )
    conn.commit()
    return len(rows)


def seed_keywords_for_run(conn: sqlite3.Connection, limit: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT keyword
        FROM keyword_seed
        ORDER BY priority DESC, keyword ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row["keyword"] for row in rows]


def start_run(
    conn: sqlite3.Connection,
    *,
    endpoint: str,
    planned_cost_usd: float,
    location_code: int,
    language_code: str,
    keywords_count: int,
) -> str:
    run_id = str(uuid4())
    conn.execute(
        """
        INSERT INTO dataforseo_runs (
          run_id, started_at_utc, status, endpoint, planned_cost_usd,
          location_code, language_code, keywords_count
        ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?)
        """,
        (run_id, db.utc_now(), endpoint, planned_cost_usd, location_code, language_code, keywords_count),
    )
    conn.commit()
    return run_id


def finish_run(conn: sqlite3.Connection, *, run_id: str, status: str, actual_cost_usd: float, error: str | None = None) -> None:
    conn.execute(
        """
        UPDATE dataforseo_runs
        SET finished_at_utc = ?, status = ?, actual_cost_usd = ?, error_message = ?
        WHERE run_id = ?
        """,
        (db.utc_now(), status, actual_cost_usd, error, run_id),
    )
    conn.commit()


def extract_search_volume_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for task in payload.get("tasks") or []:
        for result in task.get("result") or []:
            if isinstance(result, dict) and result.get("keyword"):
                items.append(result)
    return items


def upsert_keyword_metrics(
    conn: sqlite3.Connection,
    *,
    items: list[dict[str, Any]],
    location_code: int,
    language_code: str,
    run_id: str,
    task_id: str | None,
) -> int:
    collected = db.utc_now()
    for item in items:
        conn.execute(
            """
            INSERT INTO keyword_metrics (
              keyword, location_code, language_code, collected_at_utc, search_volume, cpc,
              competition, competition_index, low_top_of_page_bid, high_top_of_page_bid,
              monthly_searches_json, source, task_id, run_id, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'dataforseo_google_ads_search_volume', ?, ?, ?)
            ON CONFLICT(keyword, location_code, language_code, source) DO UPDATE SET
              collected_at_utc=excluded.collected_at_utc,
              search_volume=excluded.search_volume,
              cpc=excluded.cpc,
              competition=excluded.competition,
              competition_index=excluded.competition_index,
              low_top_of_page_bid=excluded.low_top_of_page_bid,
              high_top_of_page_bid=excluded.high_top_of_page_bid,
              monthly_searches_json=excluded.monthly_searches_json,
              task_id=excluded.task_id,
              run_id=excluded.run_id,
              raw_json=excluded.raw_json
            """,
            (
                str(item.get("keyword", "")).strip().lower(),
                location_code,
                language_code,
                collected,
                item.get("search_volume"),
                item.get("cpc"),
                item.get("competition"),
                item.get("competition_index"),
                item.get("low_top_of_page_bid"),
                item.get("high_top_of_page_bid"),
                json.dumps(item.get("monthly_searches") or [], ensure_ascii=False),
                task_id,
                run_id,
                json.dumps(item, ensure_ascii=False, sort_keys=True),
            ),
        )
    conn.commit()
    return len(items)


def run_search_volume(
    conn: sqlite3.Connection,
    *,
    client: DataForSeoClient,
    keywords: list[str],
    location_code: int,
    language_code: str,
    planned_cost_usd: float,
    max_run_cost_usd: float,
    dry_run: bool,
) -> dict[str, Any]:
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
        }

    run_id = start_run(
        conn,
        endpoint=SEARCH_VOLUME_ENDPOINT,
        planned_cost_usd=planned_cost_usd,
        location_code=location_code,
        language_code=language_code,
        keywords_count=len(keywords),
    )
    try:
        payload = client.google_ads_search_volume_live(
            keywords=keywords,
            location_code=location_code,
            language_code=language_code,
        )
        actual_cost = float(payload.get("cost") or 0)
        items = extract_search_volume_items(payload)
        task_id = None
        tasks = payload.get("tasks") or []
        if tasks:
            task_id = tasks[0].get("id")
        rows = upsert_keyword_metrics(
            conn,
            items=items,
            location_code=location_code,
            language_code=language_code,
            run_id=run_id,
            task_id=task_id,
        )
        finish_run(conn, run_id=run_id, status="success", actual_cost_usd=actual_cost)
        return {
            "dry_run": False,
            "allowed": True,
            "run_id": run_id,
            "status_code": payload.get("status_code"),
            "status_message": payload.get("status_message"),
            "actual_cost_usd": actual_cost,
            "rows": rows,
            "keywords_count": len(keywords),
        }
    except Exception as exc:
        finish_run(conn, run_id=run_id, status="failed", actual_cost_usd=0, error=str(exc))
        raise


def score_keyword(row: sqlite3.Row) -> float:
    volume = float(row["search_volume"] or 0)
    priority = float(row["priority"] or 0)
    cpc = float(row["cpc"] or 0)
    competition_index = float(row["competition_index"] or 0)
    rfq_bonus = 20 if str(row["rfq_relevance"]).lower() == "high" else 8
    return round((min(volume, 5000) / 50) + priority + (cpc * 6) + (competition_index / 6) + rfq_bonus, 2)


def keyword_foundation_rows(conn: sqlite3.Connection, *, location_code: int, language_code: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          s.keyword, s.cluster, s.intent, s.page_type, s.v8_positioning, s.rfq_relevance, s.priority,
          m.search_volume, m.cpc, m.competition, m.competition_index,
          m.low_top_of_page_bid, m.high_top_of_page_bid, m.collected_at_utc
        FROM keyword_seed s
        LEFT JOIN keyword_metrics m
          ON m.keyword = s.keyword
         AND m.location_code = ?
         AND m.language_code = ?
         AND m.source = 'dataforseo_google_ads_search_volume'
        ORDER BY COALESCE(m.search_volume, -1) DESC, s.priority DESC, s.keyword ASC
        """,
        (location_code, language_code),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["opportunity_score"] = score_keyword(row)
        result.append(item)
    return sorted(result, key=lambda item: item["opportunity_score"], reverse=True)
