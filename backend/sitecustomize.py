import logging
import os


def _resolve_log_level(value: str | None) -> int:
    raw = (value or "INFO").strip()
    if not raw:
        return logging.INFO
    name = raw.upper()
    if name in logging._nameToLevel:
        return logging._nameToLevel[name]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return logging.INFO


def _configure_logging() -> None:
    level = _resolve_log_level(os.getenv("LOG_LEVEL"))
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
    else:
        logging.basicConfig(level=level)


_configure_logging()
