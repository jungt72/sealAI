"""Fail-closed process-wide logging redaction for the V2 runtime.

Application log messages must be static format strings. Dynamic values travel as logging
arguments and are redacted unless their call site deliberately wraps an operationally safe code or
an opaque reference. Exception payloads and tracebacks are never emitted to the standard runtime
log; only the exception class survives. This keeps prompts, document text, identifiers, URLs,
credentials, and provider payloads out of the default Docker log stream.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Any

_SAFE_CODE_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.:/-]{0,95}\Z")
_PROCESS_REFERENCE_KEY = secrets.token_bytes(32)

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{12,}|"
            r"github_pat_[A-Za-z0-9_]{20,}|gh[opurs]_[A-Za-z0-9]{20,}|"
            r"xox[baprs]-[A-Za-z0-9-]{12,}|AIza[A-Za-z0-9_-]{20,})\b"
        ),
        "[REDACTED_API_KEY]",
    ),
    (
        re.compile(r"(?i)\b(authorization\s*[:=]\s*)(?:bearer|basic|token)\s+[^\s,;]+"),
        r"\1[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(r"(?i)\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}"),
        r"\1 [REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|"
            r"client[_-]?secret|private[_-]?key)\s*[:=]\s*[^\s,;]+"
        ),
        r"\1=[REDACTED_CREDENTIAL]",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(
            r"(?i)\b(postgres(?:ql)?|redis|mysql|mongodb(?:\+srv)?)://[^\s/@:]+:"
            r"[^\s/@]+@"
        ),
        r"\1://[REDACTED_CREDENTIAL]@",
    ),
    (
        re.compile(r"(?i)\bhttps?://[^\s?#]+\?[^\s]+"),
        "[REDACTED_URL_WITH_QUERY]",
    ),
)

_STANDARD_LOG_RECORD_FIELDS = frozenset(
    logging.LogRecord(
        name="sealai",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
)


@dataclass(frozen=True)
class SafeLogValue:
    """A value a reviewed call site permits in the standard runtime log."""

    value: str

    def __str__(self) -> str:
        return self.value


def safe_code(value: str) -> SafeLogValue:
    """Mark a short enum/event/error code as safe after strict syntax validation."""
    if not _SAFE_CODE_RE.fullmatch(value):
        raise ValueError("safe log code must use the restricted code alphabet")
    return SafeLogValue(value)


def safe_code_or_placeholder(
    value: str | None, *, placeholder: str = "redacted"
) -> SafeLogValue:
    """Return a reviewed code or a fixed marker; never raise from telemetry/logging code."""
    if value is not None and _SAFE_CODE_RE.fullmatch(value):
        return SafeLogValue(value)
    return safe_code(placeholder)


def opaque_reference(namespace: str, value: str | int) -> SafeLogValue:
    """Return a process-local, non-enumerable reference for a sensitive identifier."""
    ns = safe_code(namespace).value
    digest = hashlib.blake2s(
        f"{ns}\x00{value}".encode("utf-8"),
        key=_PROCESS_REFERENCE_KEY,
        digest_size=12,
    ).hexdigest()
    return SafeLogValue(f"{ns}:{digest}")


def redact_known_secrets(text: str) -> str:
    """Defense-in-depth scrub for static messages and explicitly safe values."""
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _redact_dynamic(value: Any) -> Any:
    if isinstance(value, SafeLogValue):
        return redact_known_secrets(value.value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, BaseException):
        return f"error_class={type(value).__name__}"
    if isinstance(value, str):
        return f"[REDACTED_TEXT length={len(value)}]"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"[REDACTED_BYTES length={len(value)}]"
    if isinstance(value, dict):
        # Mapping keys can be just as attacker-controlled as values (for
        # example parsed document metadata or a prompt-derived JSON object).
        # Do not preserve them unless a reviewed logging schema flattens them
        # into explicit ``extra=`` fields at the call site.
        return {
            f"redacted_field_{index}": _redact_dynamic(item)
            for index, item in enumerate(value.values())
        }
    if isinstance(value, tuple):
        return tuple(_redact_dynamic(item) for item in value)
    return f"[REDACTED_OBJECT type={type(value).__name__}]"


def _secure_record(record: logging.LogRecord) -> logging.LogRecord:
    if isinstance(record.msg, str):
        record.msg = redact_known_secrets(record.msg)
    else:
        record.msg = _redact_dynamic(record.msg)

    if isinstance(record.args, dict):
        record.args = _redact_dynamic(record.args)
    elif record.args:
        record.args = tuple(_redact_dynamic(item) for item in record.args)

    if record.exc_info:
        exc_type = record.exc_info[0]
        class_name = exc_type.__name__ if exc_type is not None else "UnknownError"
        if isinstance(record.msg, str):
            record.msg = f"{record.msg} error_class={class_name}"
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None

    # ``extra=`` fields are merged by Logger.makeRecord *after* the configured
    # LogRecord factory returns. Sanitize every non-standard field here, at the
    # post-merge boundary, so structured formatters cannot bypass redaction.
    for key, value in tuple(record.__dict__.items()):
        if key not in _STANDARD_LOG_RECORD_FIELDS and key != "request_id":
            record.__dict__[key] = _redact_dynamic(value)
    from sealai_v2.obs.request_context import current_request_id

    request_id = current_request_id()
    record.request_id = request_id or "-"
    if request_id and isinstance(record.msg, str):
        record.msg = f"request_id={request_id} {record.msg}"
    return record


def configure_safe_logging() -> None:
    """Install the idempotent post-``extra`` V2 logging boundary."""
    current = logging.Logger.makeRecord
    if getattr(current, "_sealai_safe_logging", False):
        return

    def make_record(
        logger: logging.Logger, *args: Any, **kwargs: Any
    ) -> logging.LogRecord:
        return _secure_record(current(logger, *args, **kwargs))

    make_record._sealai_safe_logging = True  # type: ignore[attr-defined]
    logging.Logger.makeRecord = make_record
