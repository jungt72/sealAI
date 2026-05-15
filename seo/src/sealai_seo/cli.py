from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import sys

from . import db
from .config import DEFAULT_DB_PATH, DEFAULT_REPORT_DIR, DEFAULT_LOG_DIR, DEFAULT_SEARCH_TYPE, settings
from .dataforseo_budget import check_budget
from .dataforseo_client import DataForSeoClient, summarize_user_data
from .gsc_client import GscClient
from .keyword_foundation import load_seed_csv, run_search_volume, seed_keywords_for_run, upsert_seed_keywords
from .pagespeed import sync_pagespeed
from .reports import anomaly, content_roadmap, keyword_foundation, quick_wins
from .sync_gsc import sync


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def final_default_date() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=3)


def cmd_init_db(args) -> None:
    s = settings()
    db_path = Path(args.db or s.db_path)
    conn = db.connect(db_path)
    db.apply_migrations(conn, Path(args.migrations))
    print(db_path)


def cmd_sync_gsc(args) -> None:
    s = settings()
    conn = db.connect(Path(args.db or s.db_path))
    client = GscClient(
        site_url=args.site_url or s.gsc_site_url,
        service_account_file=s.gsc_service_account_file,
        client_id=s.gsc_client_id,
        client_secret=s.gsc_client_secret,
        refresh_token=s.gsc_refresh_token,
    )
    result = sync(
        conn,
        client=client,
        site_url=args.site_url or s.gsc_site_url,
        date_from=parse_date(args.date_from),
        date_to=parse_date(args.date_to),
        search_type=args.search_type,
        log_dir=s.log_dir,
        dry_run=args.dry_run,
        force_provisional=args.force_provisional,
    )
    print(result)


def cmd_report_daily(args) -> None:
    s = settings()
    conn = db.connect(Path(args.db or s.db_path))
    path = anomaly.generate(
        conn,
        site_url=args.site_url or s.gsc_site_url,
        report_dir=Path(args.report_dir or s.report_dir),
        target_date=parse_date(args.target_date) if args.target_date else None,
    )
    print(path)


def cmd_report_weekly(args) -> None:
    s = settings()
    conn = db.connect(Path(args.db or s.db_path))
    path = quick_wins.generate(
        conn,
        site_url=args.site_url or s.gsc_site_url,
        report_dir=Path(args.report_dir or s.report_dir),
        period_end=parse_date(args.period_end) if args.period_end else None,
    )
    print(path)


def cmd_backup(args) -> None:
    s = settings()
    db_path = Path(args.db or s.db_path)
    backup_dir = Path(args.backup_dir or "/var/seo/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z").replace(":", "")
    out = backup_dir / f"seo-{stamp}.db"
    source = db.connect(db_path)
    target = db.connect(out)
    with target:
        source.backup(target)
    target.close()
    source.close()
    print(out)


def cmd_restore_smoke_test(args) -> None:
    backup_dir = Path(args.backup_dir or "/var/seo/backups")
    latest = sorted(backup_dir.glob("seo-*.db"))[-1]
    tmp = Path(args.tmp_dir or "/tmp/sealai-seo-restore-smoke")
    tmp.mkdir(parents=True, exist_ok=True)
    restored = tmp / "seo-restored.db"
    shutil.copy2(latest, restored)
    conn = db.connect(restored)
    conn.execute("SELECT COUNT(*) FROM gsc_daily_page").fetchone()
    print(restored)


def cmd_dataforseo_user_data(args) -> None:
    s = settings()
    if not s.dataforseo_login or not s.dataforseo_password:
        raise SystemExit("Missing DATAFORSEO_LOGIN or DATAFORSEO_PASSWORD.")
    client = DataForSeoClient(
        login=s.dataforseo_login,
        password=s.dataforseo_password,
        base_url=s.dataforseo_base_url,
    )
    payload = client.user_data()
    result = summarize_user_data(payload)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def dataforseo_client_from_settings() -> DataForSeoClient:
    s = settings()
    if not s.dataforseo_login or not s.dataforseo_password:
        raise SystemExit("Missing DATAFORSEO_LOGIN or DATAFORSEO_PASSWORD.")
    return DataForSeoClient(
        login=s.dataforseo_login,
        password=s.dataforseo_password,
        base_url=s.dataforseo_base_url,
    )


def cmd_dataforseo_budget_check(args) -> None:
    s = settings()
    client = dataforseo_client_from_settings()
    user_data = summarize_user_data(client.user_data())
    balance = float(user_data.get("balance") or 0)
    max_run_cost = float(args.max_run_cost if args.max_run_cost is not None else s.dataforseo_max_run_cost_usd)
    decision = check_budget(
        planned_cost_usd=float(args.planned_cost),
        max_run_cost_usd=max_run_cost,
        balance_usd=balance,
    )
    result = {
        "allowed": decision.allowed,
        "planned_cost_usd": decision.planned_cost_usd,
        "max_run_cost_usd": decision.max_run_cost_usd,
        "balance_usd": decision.balance_usd,
        "reason": decision.reason,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if not decision.allowed:
        raise SystemExit(2)


def cmd_seed_keywords(args) -> None:
    s = settings()
    conn = db.connect(Path(args.db or s.db_path))
    db.apply_migrations(conn, Path(args.migrations))
    rows = load_seed_csv(Path(args.file))
    count = upsert_seed_keywords(conn, rows)
    print(json.dumps({"seeded": count, "file": args.file}, ensure_ascii=False, sort_keys=True))


def cmd_dataforseo_keyword_volume(args) -> None:
    s = settings()
    conn = db.connect(Path(args.db or s.db_path))
    db.apply_migrations(conn, Path(args.migrations))
    client = dataforseo_client_from_settings()
    if args.keyword:
        keywords = [item.strip().lower() for item in args.keyword if item.strip()]
    else:
        keywords = seed_keywords_for_run(conn, args.limit)
    result = run_search_volume(
        conn,
        client=client,
        keywords=keywords,
        location_code=args.location_code,
        language_code=args.language_code,
        planned_cost_usd=args.planned_cost,
        max_run_cost_usd=float(args.max_run_cost if args.max_run_cost is not None else s.dataforseo_max_run_cost_usd),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if not result.get("allowed"):
        raise SystemExit(2)


def cmd_report_keyword_foundation(args) -> None:
    s = settings()
    conn = db.connect(Path(args.db or s.db_path))
    path = keyword_foundation.generate(
        conn,
        report_dir=Path(args.report_dir or s.report_dir),
        location_code=args.location_code,
        language_code=args.language_code,
    )
    print(path)


def cmd_report_content_roadmap(args) -> None:
    s = settings()
    conn = db.connect(Path(args.db or s.db_path))
    path = content_roadmap.generate(
        conn,
        report_dir=Path(args.report_dir or s.report_dir),
        location_code=args.location_code,
        language_code=args.language_code,
    )
    print(path)


def cmd_sync_pagespeed(args) -> None:
    s = settings()
    conn = db.connect(Path(args.db or s.db_path))
    db.apply_migrations(conn, Path(args.migrations))
    urls = args.url or list(s.pagespeed_urls)
    result = sync_pagespeed(
        conn,
        urls=urls,
        strategy=args.strategy,
        api_key=s.pagespeed_api_key,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sealai-seo")
    sub = parser.add_subparsers(required=True)

    init_db = sub.add_parser("init-db")
    init_db.add_argument("--db")
    init_db.add_argument("--migrations", default="seo/migrations")
    init_db.set_defaults(func=cmd_init_db)

    sync_gsc = sub.add_parser("sync-gsc")
    sync_gsc.add_argument("--site-url")
    sync_gsc.add_argument("--date-from", default=final_default_date().isoformat())
    sync_gsc.add_argument("--date-to", default=final_default_date().isoformat())
    sync_gsc.add_argument("--search-type", default=DEFAULT_SEARCH_TYPE)
    sync_gsc.add_argument("--db")
    sync_gsc.add_argument("--dry-run", action="store_true")
    sync_gsc.add_argument("--force-provisional", action="store_true")
    sync_gsc.set_defaults(func=cmd_sync_gsc)

    daily = sub.add_parser("report-daily")
    daily.add_argument("--site-url")
    daily.add_argument("--target-date")
    daily.add_argument("--db")
    daily.add_argument("--report-dir")
    daily.set_defaults(func=cmd_report_daily)

    weekly = sub.add_parser("report-weekly")
    weekly.add_argument("--site-url")
    weekly.add_argument("--period-end")
    weekly.add_argument("--db")
    weekly.add_argument("--report-dir")
    weekly.set_defaults(func=cmd_report_weekly)

    backup = sub.add_parser("backup")
    backup.add_argument("--db")
    backup.add_argument("--backup-dir")
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore-smoke-test")
    restore.add_argument("--backup-dir")
    restore.add_argument("--tmp-dir")
    restore.set_defaults(func=cmd_restore_smoke_test)

    dfs_user = sub.add_parser("dataforseo-user-data")
    dfs_user.set_defaults(func=cmd_dataforseo_user_data)

    dfs_budget = sub.add_parser("dataforseo-budget-check")
    dfs_budget.add_argument("--planned-cost", type=float, required=True)
    dfs_budget.add_argument("--max-run-cost", type=float)
    dfs_budget.set_defaults(func=cmd_dataforseo_budget_check)

    seed_kw = sub.add_parser("seed-keywords")
    seed_kw.add_argument("--file", default="seo/data/run0_keywords.csv")
    seed_kw.add_argument("--db")
    seed_kw.add_argument("--migrations", default="seo/migrations")
    seed_kw.set_defaults(func=cmd_seed_keywords)

    dfs_volume = sub.add_parser("dataforseo-keyword-volume")
    dfs_volume.add_argument("--limit", type=int, default=40)
    dfs_volume.add_argument("--keyword", action="append")
    dfs_volume.add_argument("--location-code", type=int, default=2276)
    dfs_volume.add_argument("--language-code", default="de")
    dfs_volume.add_argument("--planned-cost", type=float, default=0.10)
    dfs_volume.add_argument("--max-run-cost", type=float)
    dfs_volume.add_argument("--dry-run", action="store_true")
    dfs_volume.add_argument("--db")
    dfs_volume.add_argument("--migrations", default="seo/migrations")
    dfs_volume.set_defaults(func=cmd_dataforseo_keyword_volume)

    kw_foundation = sub.add_parser("report-keyword-foundation")
    kw_foundation.add_argument("--location-code", type=int, default=2276)
    kw_foundation.add_argument("--language-code", default="de")
    kw_foundation.add_argument("--db")
    kw_foundation.add_argument("--report-dir")
    kw_foundation.set_defaults(func=cmd_report_keyword_foundation)

    content_map = sub.add_parser("report-content-roadmap")
    content_map.add_argument("--location-code", type=int, default=2276)
    content_map.add_argument("--language-code", default="de")
    content_map.add_argument("--db")
    content_map.add_argument("--report-dir")
    content_map.set_defaults(func=cmd_report_content_roadmap)

    pagespeed = sub.add_parser("sync-pagespeed")
    pagespeed.add_argument("--url", action="append")
    pagespeed.add_argument("--strategy", choices=["mobile", "desktop"], default="mobile")
    pagespeed.add_argument("--db")
    pagespeed.add_argument("--migrations", default="seo/migrations")
    pagespeed.add_argument("--dry-run", action="store_true")
    pagespeed.set_defaults(func=cmd_sync_pagespeed)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
