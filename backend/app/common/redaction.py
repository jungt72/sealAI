from __future__ import annotations

import re
from typing import Any

_PATH_PATTERN = re.compile(r"(?P<path>(?:/[A-Za-z0-9._@%+=:,~ -]+){2,})")


def redact_internal_paths(value: Any) -> Any:
    if isinstance(value, str):
        return _PATH_PATTERN.sub("[REDACTED_PATH]", value)
    if isinstance(value, dict):
        return {key: redact_internal_paths(child) for key, child in value.items()}
    if isinstance(value, list):
        return [redact_internal_paths(child) for child in value]
    return value


def safe_error_message(exc: BaseException) -> str:
    return redact_internal_paths(f"{type(exc).__name__}: {exc}")
