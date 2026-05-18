from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .markdown import write_report
from ..text_sanitizer import escape_markdown


def generate(conn, *, report_dir: Path) -> Path:
    run = conn.execute(
        """
        SELECT *
        FROM seo_crawl_runs
        ORDER BY started_at_utc DESC
        LIMIT 1
        """
    ).fetchone()
    if not run:
        lines = [
            "---",
            "type: indexability_control",
            'status: "missing_data"',
            f'generated_at_utc: "{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}"',
            "---",
            "",
            "# SEO Indexability Control",
            "",
            "No crawl run found. Run `PYTHONPATH=seo/src python -m sealai_seo.cli crawl-indexability`.",
        ]
        return write_report(report_dir / "indexability" / "latest-indexability.md", "\n".join(lines) + "\n")

    issue_rows = conn.execute(
        """
        SELECT url, status_code, indexable, canonical_url, inbound_internal_links_count,
               issue_count, issues_json
        FROM seo_url_checks
        WHERE run_id = ? AND issue_count > 0
        ORDER BY issue_count DESC, inbound_internal_links_count ASC, url ASC
        LIMIT 80
        """,
        (run["run_id"],),
    ).fetchall()
    orphan_rows = conn.execute(
        """
        SELECT url, inbound_internal_links_count, internal_links_count
        FROM seo_url_checks
        WHERE run_id = ? AND inbound_internal_links_count = 0
        ORDER BY url ASC
        LIMIT 80
        """,
        (run["run_id"],),
    ).fetchall()
    lines = [
        "---",
        "type: indexability_control",
        f'run_id: "{run["run_id"]}"',
        f'status: "{run["status"]}"',
        f'base_url: "{run["base_url"]}"',
        f'sitemap_url: "{run["sitemap_url"]}"',
        f'generated_at_utc: "{datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}"',
        "---",
        "",
        "# SEO Indexability Control",
        "",
        "## Executive Summary",
        "",
        f"- URLs discovered: {run['urls_discovered']}",
        f"- URLs checked: {run['urls_checked']}",
        f"- Indexable URLs: {run['indexable_urls']}",
        f"- URLs with issues: {run['issue_urls']}",
        "",
        "## Priority Issues",
        "",
        "| URL | HTTP | Indexable | Inbound Links | Issues |",
        "|---|---:|---:|---:|---|",
    ]
    for row in issue_rows:
        issues = ", ".join(json.loads(row["issues_json"] or "[]"))
        lines.append(
            f"| {escape_markdown(row['url'])} | {row['status_code'] or '-'} | {row['indexable']} | {row['inbound_internal_links_count']} | {escape_markdown(issues)} |"
        )
    lines += [
        "",
        "## Orphan / Low-Authority Candidates",
        "",
        "| URL | Inbound Internal Links | Outbound Internal Links |",
        "|---|---:|---:|",
    ]
    for row in orphan_rows:
        lines.append(
            f"| {escape_markdown(row['url'])} | {row['inbound_internal_links_count']} | {row['internal_links_count']} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "This report is deterministic. It checks crawlability and on-page signals; it does not infer ranking gains.",
    ]
    return write_report(report_dir / "indexability" / "latest-indexability.md", "\n".join(lines) + "\n")
