"""Minimal error-detail helper for FastAPI HTTPException details.

Recreated after app/common/errors.py was lost during the _legacy_v2 cleanup.
The canonical source of error_detail is app._legacy_v2.contracts; this module
re-exports a compatible implementation so that rag.py and rag/utils.py can
import from their original path without modification.
"""
from __future__ import annotations

from typing import Any


def error_detail(code: str, **kwargs: Any) -> dict[str, Any]:
    """Build a structured error-detail dict for FastAPI HTTPException.

    Args:
        code: machine-readable error code (e.g. "document_not_found")
        **kwargs: any additional context fields (request_id, reason, …)

    Returns:
        dict with at least {"error": code} plus any extra kwargs.
    """
    detail: dict[str, Any] = {"error": code}
    detail.update(kwargs)
    return detail
