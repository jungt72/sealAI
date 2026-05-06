from __future__ import annotations

from pathlib import Path
import sqlite3

from ..keyword_foundation import keyword_foundation_rows
from .markdown import write_report


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def generate(
    conn: sqlite3.Connection,
    *,
    report_dir: Path,
    location_code: int,
    language_code: str,
) -> Path:
    rows = keyword_foundation_rows(conn, location_code=location_code, language_code=language_code)
    path = report_dir / "keyword-foundation" / f"run0-keyword-foundation-{location_code}-{language_code}.md"
    lines = [
        "# SealAI Run 0 Keyword Foundation",
        "",
        "This report ranks seed keywords for a greenfield V8-compliant SEO architecture.",
        "",
        "V8 guardrail: SealAI pages should create technical orientation and a manufacturer-review-ready inquiry basis. They must not claim final material suitability, final design approval, or manufacturer responsibility.",
        "",
        "| Score | Keyword | Cluster | Volume | CPC | Comp. idx | Page Type | V8 Positioning | RFQ |",
        "|---:|---|---|---:|---:|---:|---|---|---|",
    ]
    for row in rows[:40]:
        lines.append(
            "| {score} | {keyword} | {cluster} | {volume} | {cpc} | {competition_index} | {page_type} | {v8} | {rfq} |".format(
                score=_fmt(row["opportunity_score"]),
                keyword=row["keyword"],
                cluster=row["cluster"],
                volume=_fmt(row["search_volume"]),
                cpc=_fmt(row["cpc"]),
                competition_index=_fmt(row["competition_index"]),
                page_type=row["page_type"],
                v8=row["v8_positioning"],
                rfq=row["rfq_relevance"],
            )
        )
    lines.extend(
        [
            "",
            "## Recommended First Content Architecture",
            "",
            "1. RFQ preparation landing page: explain structured inquiry quality, required operating data, and manufacturer review boundary.",
            "2. Material hub: FKM, PTFE, NBR, EPDM pages with media/temperature limits framed as orientation.",
            "3. Media compatibility hub: hydrochloric acid, oil, steam, chemical resistance pages that collect missing RFQ parameters.",
            "4. Failure intake workflow: leakage and damage-analysis pages focused on structured clarification.",
            "5. Standards/dimensions knowledge layer: DIN 3760 and shaft seal dimensions as support content.",
        ]
    )
    return write_report(path, "\n".join(lines) + "\n")
