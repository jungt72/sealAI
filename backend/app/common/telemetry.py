from __future__ import annotations

import logging
import os
from fastapi import FastAPI

from app.core.config import settings

logger = logging.getLogger("app.telemetry")


def _is_enabled(name: str, default: bool = True) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _configure_langsmith() -> bool:
    """Configure LangSmith tracing if an API key is available."""
    if not settings.langchain_tracing_v2:
        return False

    if not settings.langchain_api_key:
        logger.info("LangSmith tracing requested but no API key provided – disabling LangSmith telemetry.")
        return False

    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
    if settings.langchain_endpoint:
        os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.langchain_endpoint)
    if settings.langchain_project:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
    return True


def _instrument_fastapi(app: FastAPI) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
    except ImportError:
        logger.warning("OpenTelemetry instrumentation not installed – skipping FastAPI/Requests instrumentation.")
        return

    FastAPIInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
    except ImportError:
        logger.debug("Redis instrumentation not available.")


def configure_telemetry(app: FastAPI) -> None:
    """Enable OpenTelemetry + LangSmith tracing if configured."""
    langsmith_enabled = _configure_langsmith()
    if not _is_enabled("ENABLE_OTEL", True):
        return
    _instrument_fastapi(app)
    logger.info("Telemetry initialized (OTel=%s, LangSmith=%s)", True, bool(langsmith_enabled))
