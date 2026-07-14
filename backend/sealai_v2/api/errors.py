"""Fixed-code client errors and a fail-closed unhandled-exception boundary."""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from sealai_v2.obs.log_redaction import safe_code_or_placeholder
from sealai_v2.obs.request_context import current_request_id

_ERROR_CODE_RE = re.compile(r"\A[a-z][a-z0-9_]{0,63}\Z")
_LOG = logging.getLogger(__name__)


def safe_http_error(status_code: int, code: str) -> HTTPException:
    """Build an HTTP error whose public payload cannot contain exception text."""
    if not _ERROR_CODE_RE.fullmatch(code):
        raise ValueError("public error code must be a fixed lowercase token")
    return HTTPException(status_code=status_code, detail={"code": code})


async def _safe_unhandled_exception(
    _request: Request, exc: Exception
) -> JSONResponse:
    """Map an unexpected failure to a stable payload and metadata-only log."""
    _LOG.error(
        "event=unhandled_request_exception error_class=%s",
        safe_code_or_placeholder(type(exc).__name__, placeholder="UnknownError"),
    )
    detail: dict[str, str] = {"code": "internal_error"}
    request_id = current_request_id()
    if request_id:
        detail["request_id"] = request_id
    return JSONResponse(status_code=500, content={"detail": detail})


def install_safe_exception_mapper(app: FastAPI) -> None:
    """Install the process-wide unexpected-error mapper on a FastAPI app."""
    app.add_exception_handler(Exception, _safe_unhandled_exception)
