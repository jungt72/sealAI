from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

MAX_DAYS_BACKFILL = 90
MAX_ROWS_PER_REQUEST = 25_000
MAX_REQUESTS_PER_RUN = 50
MAX_PROPERTIES_PER_RUN = 3
DEFAULT_SEARCH_TYPE = "web"
DEFAULT_DATAFORSEO_MAX_RUN_COST_USD = 0.25

DEFAULT_DB_PATH = Path("/var/seo/data/seo.db")
DEFAULT_REPORT_DIR = Path("/var/seo/reports")
DEFAULT_LOG_DIR = Path("/var/seo/logs")
DEFAULT_SECRETS_ENV = Path("/etc/seo/secrets/seo.env")
FALLBACK_SECRETS_ENV = Path.home() / ".sealai" / "seo.env"
LEGACY_GSC_ENV = Path.home() / ".sealai" / "gsc.env"
DATAFORSEO_ENV = Path.home() / ".sealai" / "dataforseo.env"


def load_env_file(path: Path = DEFAULT_SECRETS_ENV) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


@dataclass(frozen=True)
class Settings:
    db_path: Path
    report_dir: Path
    log_dir: Path
    gsc_site_url: str
    gsc_service_account_file: Path | None
    gsc_client_id: str | None
    gsc_client_secret: str | None
    gsc_refresh_token: str | None
    dataforseo_login: str | None
    dataforseo_password: str | None
    dataforseo_base_url: str
    dataforseo_max_run_cost_usd: float


def settings() -> Settings:
    file_env = {
        **load_env_file(LEGACY_GSC_ENV),
        **load_env_file(FALLBACK_SECRETS_ENV),
        **load_env_file(DATAFORSEO_ENV),
        **load_env_file(DEFAULT_SECRETS_ENV),
    }
    merged = {**file_env, **os.environ}
    return Settings(
        db_path=Path(merged.get("SEO_DB_PATH", DEFAULT_DB_PATH)),
        report_dir=Path(merged.get("SEO_REPORT_DIR", DEFAULT_REPORT_DIR)),
        log_dir=Path(merged.get("SEO_LOG_DIR", DEFAULT_LOG_DIR)),
        gsc_site_url=merged.get("GSC_SITE_URL", "sc-domain:sealai.net"),
        gsc_service_account_file=Path(merged["GSC_SERVICE_ACCOUNT_FILE"])
        if merged.get("GSC_SERVICE_ACCOUNT_FILE")
        else None,
        gsc_client_id=merged.get("GSC_CLIENT_ID"),
        gsc_client_secret=merged.get("GSC_CLIENT_SECRET"),
        gsc_refresh_token=merged.get("GSC_REFRESH_TOKEN"),
        dataforseo_login=merged.get("DATAFORSEO_LOGIN"),
        dataforseo_password=merged.get("DATAFORSEO_PASSWORD"),
        dataforseo_base_url=merged.get("DATAFORSEO_BASE_URL", "https://api.dataforseo.com/v3"),
        dataforseo_max_run_cost_usd=float(
            merged.get("DATAFORSEO_MAX_RUN_COST_USD", DEFAULT_DATAFORSEO_MAX_RUN_COST_USD)
        ),
    )
