from __future__ import annotations

from pathlib import Path
import sqlite3

from ..content_roadmap import roadmap_rows
from .markdown import write_report


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def generate(conn: sqlite3.Connection, *, report_dir: Path, location_code: int, language_code: str) -> Path:
    rows = roadmap_rows(conn, location_code=location_code, language_code=language_code)
    path = report_dir / "content-roadmap" / f"run0-content-roadmap-{location_code}-{language_code}.md"
    lines = [
        "# SealAI Run 0 Content Roadmap",
        "",
        "Purpose: convert the greenfield keyword foundation into a V8-compliant website architecture.",
        "",
        "Core V8 rule: every page may provide technical orientation and prepare a manufacturer-review-ready inquiry basis. No page may claim final sealing design approval, final material suitability, or final root-cause approval.",
        "",
        "## Priority Pages",
        "",
        "| Phase | URL | Route | Primary Keyword | Volume | Score | Page Type | H1 |",
        "|---:|---|---|---|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {phase} | `{path}` | {route} | {keyword} | {volume} | {score} | {page_type} | {h1} |".format(
                phase=row["phase"],
                path=row["path"],
                route=row["route_status"],
                keyword=row["primary_keyword"],
                volume=_fmt(row["primary_search_volume"]),
                score=_fmt(row["opportunity_score"]),
                page_type=row["page_type"],
                h1=row["h1"],
            )
        )
    lines.extend(["", "## Page Briefs", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['path']}",
                "",
                f"- Phase: {row['phase']}",
                f"- Route status: {row['route_status']}",
                f"- Primary keyword: {row['primary_keyword']} (volume: {_fmt(row['primary_search_volume'])})",
                f"- Secondary keywords: {row['secondary_keywords']}",
                f"- Intent: {row['intent']}",
                f"- H1: {row['h1']}",
                f"- Meta title: {row['meta_title']}",
                f"- Meta description: {row['meta_description']}",
                f"- V8 boundary: {row['v8_claim_boundary']}",
                f"- RFQ fields: {row['rfq_fields']}",
                f"- Internal links: {row['internal_links']}",
                "",
            ]
        )
    lines.extend(
        [
            "## GSC Actions After Publishing",
            "",
            "1. Ensure the generated sitemap contains every published public URL.",
            "2. Resubmit `https://sealai.net/sitemap.xml` in Google Search Console.",
            "3. Use URL inspection for the phase-1 pages only after deployment.",
            "4. Compare GSC query/page data against this roadmap after Google has recrawled and accumulated impressions.",
        ]
    )
    return write_report(path, "\n".join(lines) + "\n")
