from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .markdown import write_report, pct
from ..text_sanitizer import escape_markdown


def default_target_date(today: date | None = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    return today - timedelta(days=3)


def generate(conn, *, site_url: str, report_dir: Path, target_date: date | None = None) -> Path:
    target = target_date or default_target_date()
    start = target - timedelta(days=28)
    rows = conn.execute(
        """
        WITH baseline AS (
          SELECT page, AVG(clicks) avg_clicks, AVG(impressions) avg_impressions,
                 AVG(ctr) avg_ctr, AVG(position) avg_position, COUNT(*) days
          FROM gsc_daily_page
          WHERE site_url=? AND data_state='final' AND data_date>=? AND data_date<?
          GROUP BY page
        )
        SELECT t.page, t.clicks, t.impressions, t.ctr, t.position,
               b.avg_clicks, b.avg_impressions, b.avg_ctr, b.avg_position, b.days
        FROM gsc_daily_page t
        JOIN baseline b ON b.page=t.page
        WHERE t.site_url=? AND t.data_date=? AND t.data_state='final'
          AND (b.avg_impressions >= 50 OR b.avg_clicks >= 2)
        """,
        (site_url, start.isoformat(), target.isoformat(), site_url, target.isoformat()),
    ).fetchall()
    alerts = []
    for row in rows:
        types = []
        score = 0.0
        if row["clicks"] <= row["avg_clicks"] * 0.70 and row["avg_clicks"] - row["clicks"] >= 5:
            types.append("click_drop")
            score += 4
        if row["impressions"] <= row["avg_impressions"] * 0.70 and row["avg_impressions"] - row["impressions"] >= 50:
            types.append("impression_drop")
            score += 3
        if row["avg_impressions"] >= 100 and row["impressions"] >= 50 and row["ctr"] <= row["avg_ctr"] * 0.70 and row["avg_ctr"] - row["ctr"] >= 0.02:
            types.append("ctr_drop")
            score += 2
        if row["impressions"] >= 50 and row["position"] - row["avg_position"] >= 3.0:
            types.append("position_loss")
            score += 2
        if types:
            alerts.append((score, row, ", ".join(types)))
    alerts.sort(key=lambda item: item[0], reverse=True)
    lines = [
        "---",
        "type: daily_anomaly",
        f'site_url: "{site_url}"',
        f'target_date: "{target.isoformat()}"',
        "baseline_days: 28",
        "data_state: final",
        f'generated_at_utc: "{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}"',
        "source: gsc_api",
        "---",
        "",
        f"# Daily SEO Anomaly Report — {target.isoformat()}",
        "",
        "## Executive Summary",
        "",
        f"{len(alerts[:30])} deterministic alert candidates found.",
        "",
        "## Data Quality Notes",
        "",
        "GSC Search Analytics API data is treated as a strong SEO performance signal, not a complete raw export of all search data.",
        "",
        "## Alerts",
        "",
        "| Severity | Page | Alert Type | Target | Baseline | Change |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for score, row, types in alerts[:30]:
        target_text = f"{row['clicks']:.0f} clicks / {row['impressions']:.0f} impr. / {pct(row['ctr'])} / pos {row['position']:.1f}"
        baseline = f"{row['avg_clicks']:.1f} clicks / {row['avg_impressions']:.1f} impr. / {pct(row['avg_ctr'])} / pos {row['avg_position']:.1f}"
        change = f"{row['clicks'] - row['avg_clicks']:.1f} clicks"
        lines.append(f"| {score:.0f} | {escape_markdown(row['page'])} | {types} | {target_text} | {baseline} | {change} |")
    lines += ["", "## Notes", "", "This report detects movement. It does not prove causes."]
    return write_report(report_dir / "daily" / f"{target.isoformat()}-daily-anomaly.md", "\n".join(lines) + "\n")
