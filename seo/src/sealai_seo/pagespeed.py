from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import uuid4

from .db import utc_now

PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


@dataclass(frozen=True)
class PageSpeedMetrics:
    url: str
    strategy: str
    performance_score: float | None
    lcp_ms: float | None
    inp_ms: float | None
    cls: float | None
    fcp_ms: float | None
    ttfb_ms: float | None
    source: str


def _numeric_audit(audits: dict, audit_id: str) -> float | None:
    value = audits.get(audit_id, {}).get("numericValue")
    return float(value) if isinstance(value, (int, float)) else None


def extract_metrics(payload: dict, *, url: str, strategy: str, source: str = "pagespeed_api") -> PageSpeedMetrics:
    lighthouse = payload.get("lighthouseResult") if isinstance(payload, dict) else {}
    lighthouse = lighthouse if isinstance(lighthouse, dict) else {}
    audits = lighthouse.get("audits") if isinstance(lighthouse.get("audits"), dict) else {}
    categories = lighthouse.get("categories") if isinstance(lighthouse.get("categories"), dict) else {}
    performance = categories.get("performance") if isinstance(categories.get("performance"), dict) else {}
    score = performance.get("score")

    return PageSpeedMetrics(
        url=url,
        strategy=strategy,
        performance_score=float(score) if isinstance(score, (int, float)) else None,
        lcp_ms=_numeric_audit(audits, "largest-contentful-paint"),
        inp_ms=_numeric_audit(audits, "interaction-to-next-paint"),
        cls=_numeric_audit(audits, "cumulative-layout-shift"),
        fcp_ms=_numeric_audit(audits, "first-contentful-paint"),
        ttfb_ms=_numeric_audit(audits, "server-response-time"),
        source=source,
    )


def fetch_pagespeed(url: str, *, strategy: str, api_key: str | None = None, timeout: int = 180) -> dict:
    query = {
        "url": url,
        "strategy": strategy,
        "category": "performance",
    }
    if api_key:
        query["key"] = api_key
    request_url = f"{PAGESPEED_ENDPOINT}?{urlencode(query)}"
    with urlopen(request_url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def sample_pagespeed_payload() -> dict:
    return {
        "lighthouseResult": {
            "categories": {"performance": {"score": 0.91}},
            "audits": {
                "largest-contentful-paint": {"numericValue": 1850},
                "interaction-to-next-paint": {"numericValue": 120},
                "cumulative-layout-shift": {"numericValue": 0.02},
                "first-contentful-paint": {"numericValue": 980},
                "server-response-time": {"numericValue": 180},
            },
        }
    }


def insert_metric(conn: sqlite3.Connection, run_id: str, metric: PageSpeedMetrics) -> None:
    conn.execute(
        """
        INSERT INTO pagespeed_url_metrics (
          run_id, url, strategy, performance_score, lcp_ms, inp_ms, cls, fcp_ms, ttfb_ms, source, fetched_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            metric.url,
            metric.strategy,
            metric.performance_score,
            metric.lcp_ms,
            metric.inp_ms,
            metric.cls,
            metric.fcp_ms,
            metric.ttfb_ms,
            metric.source,
            utc_now(),
        ),
    )


def sync_pagespeed(
    conn: sqlite3.Connection,
    *,
    urls: list[str],
    strategy: str = "mobile",
    api_key: str | None = None,
    dry_run: bool = False,
) -> dict:
    if strategy not in {"mobile", "desktop"}:
        raise ValueError("strategy must be mobile or desktop")
    run_id = uuid4().hex
    conn.execute(
        """
        INSERT INTO pagespeed_sync_runs (run_id, started_at_utc, status, strategy)
        VALUES (?, ?, 'running', ?)
        """,
        (run_id, utc_now(), strategy),
    )
    conn.commit()

    scanned = 0
    try:
        for url in urls:
            payload = sample_pagespeed_payload() if dry_run else fetch_pagespeed(url, strategy=strategy, api_key=api_key)
            metric = extract_metrics(
                payload,
                url=url,
                strategy=strategy,
                source="pagespeed_dry_run" if dry_run else "pagespeed_api",
            )
            insert_metric(conn, run_id, metric)
            scanned += 1
        conn.execute(
            """
            UPDATE pagespeed_sync_runs
            SET status = 'success', finished_at_utc = ?, urls_scanned = ?
            WHERE run_id = ?
            """,
            (utc_now(), scanned, run_id),
        )
        conn.commit()
        return {"run_id": run_id, "status": "success", "urls_scanned": scanned, "strategy": strategy}
    except Exception as exc:
        conn.execute(
            """
            UPDATE pagespeed_sync_runs
            SET status = 'failed', finished_at_utc = ?, urls_scanned = ?, error_message = ?
            WHERE run_id = ?
            """,
            (utc_now(), scanned, str(exc)[:500], run_id),
        )
        conn.commit()
        raise
