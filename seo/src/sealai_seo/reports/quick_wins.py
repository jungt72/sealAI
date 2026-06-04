from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .markdown import write_report, pct
from ..text_sanitizer import escape_markdown


def default_period_end(today: date | None = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    return today - timedelta(days=3)


def _expected_ctr(position: float) -> float:
    if 5 <= position <= 8:
        return 0.05
    if 9 <= position <= 12:
        return 0.03
    return 0.015


def generate(conn, *, site_url: str, report_dir: Path, period_end: date | None = None) -> Path:
    end = period_end or default_period_end()
    start = end - timedelta(days=27)
    rows = conn.execute(
        """
        SELECT page, query_sanitized AS query, SUM(clicks) clicks, SUM(impressions) impressions,
               CASE WHEN SUM(impressions) > 0 THEN SUM(clicks) / SUM(impressions) ELSE 0 END ctr,
               CASE WHEN SUM(impressions) > 0 THEN SUM(position * impressions) / SUM(impressions) ELSE AVG(position) END position
        FROM gsc_daily_page_query
        WHERE site_url=? AND data_state='final' AND data_date BETWEEN ? AND ?
        GROUP BY page, query
        HAVING impressions >= 100 AND position >= 5 AND position <= 20
        """,
        (site_url, start.isoformat(), end.isoformat()),
    ).fetchall()
    candidates = []
    for row in rows:
        expected = _expected_ctr(row["position"])
        if row["ctr"] >= expected:
            continue
        gap = max(expected - row["ctr"], 0)
        score = row["impressions"] * gap * (21 - row["position"])
        candidates.append((score, row))
    candidates.sort(key=lambda item: item[0], reverse=True)
    week = end.isocalendar()
    lines = [
        "---",
        "type: weekly_quick_wins",
        f'site_url: "{site_url}"',
        f'period_start: "{start.isoformat()}"',
        f'period_end: "{end.isoformat()}"',
        "data_state: final",
        f'generated_at_utc: "{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}"',
        "source: gsc_api",
        "---",
        "",
        f"# Weekly SEO Quick-Win Report — {week.year}-W{week.week:02d}",
        "",
        "## Executive Summary",
        "",
        f"{len(candidates[:50])} keyword/page opportunity candidates found.",
        "",
        "## Data Quality Notes",
        "",
        "GSC Search Analytics API data is treated as a strong SEO performance signal, not a complete raw export of all search data.",
        "",
        "## Top Opportunities",
        "",
        "| Score | Page | Query | Impressions | Clicks | CTR | Avg Position |",
        "|---:|---|---|---:|---:|---:|---:|",
    ]
    for score, row in candidates[:50]:
        lines.append(
            f"| {score:.2f} | {escape_markdown(row['page'])} | {escape_markdown(row['query'])} | {row['impressions']:.0f} | {row['clicks']:.0f} | {pct(row['ctr'])} | {row['position']:.1f} |"
        )
    lines += [
        "",
        "## Recommended Manual Review",
        "",
        "- Check search intent fit, title/H1 clarity, snippet promise, and whether the page actually deserves the query.",
        "- Do not infer ranking gains automatically; use this list as deterministic prioritization.",
        "",
        "## Notes",
        "",
        "This report identifies candidates. It does not guarantee ranking gains.",
    ]
    return write_report(report_dir / "weekly" / f"{week.year}-W{week.week:02d}-weekly-quick-wins.md", "\n".join(lines) + "\n")
