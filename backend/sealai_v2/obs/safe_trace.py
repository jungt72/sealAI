"""Production-safe LangSmith tracing policy (Phase 0 of the LangGraph-suitability audit).

Audit finding: the parent-turn trace and every wrapped OpenAI-compatible call previously carried
RAW question/answer/prompt/completion text with no redaction — a real data-exfiltration risk for
confidential B2B engineering cases. This module is the single place that decides WHAT may ever be
sent to LangSmith and provides the safe building blocks (hashing, bucketing, a regex fallback).

Design:
- Three modes: ``off`` (no tracing), ``safe_metadata_only`` (the production default — booleans,
  lengths, hashed IDs, no content), ``full_synthetic_only`` (raw content allowed — ONLY meant for a
  non-production run against synthetic/fixture data, never real user traffic).
- FAIL CLOSED: in production (``APP_ENV`` unset or not ``"development"``/``"test"``/``"staging"``),
  a request for ``full_synthetic_only`` is silently downgraded to ``safe_metadata_only`` — an
  operator cannot accidentally leak real data by setting the wrong env var.
- Every helper here is pure (no I/O, no LangSmith import) so it is trivially unit-testable and
  reusable by both ``obs/tracing.py`` (the LangSmith wrap point) and ``pipeline/pipeline.py`` (the
  ``@traceable`` input/output projections).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass

_VALID_MODES = ("off", "safe_metadata_only", "full_synthetic_only")
_NON_PRODUCTION_ENVS = {"development", "dev", "test", "testing", "staging", "local"}

# Not a real secret by default — set SEALAI_V2_TRACE_HMAC_SECRET in any environment where a
# stable-but-non-reversible ID actually matters (the default only prevents trivial "same value
# every time" reversal, not a determined attacker without the real secret).
_DEFAULT_HMAC_PEPPER = "sealai-v2-safe-trace-default-pepper-not-a-secret"


def is_production() -> bool:
    """True unless ``APP_ENV`` explicitly names a non-production environment. Fails closed: an
    unset/unknown value is treated as production (the safest assumption for a tracing decision)."""
    env = (os.getenv("APP_ENV") or "").strip().lower()
    return env not in _NON_PRODUCTION_ENVS


def resolve_tracing_mode() -> str:
    """The effective tracing mode. Reads ``SEALAI_V2_LANGSMITH_TRACING_MODE``; an unset or
    unrecognized value defaults to ``safe_metadata_only`` (never ``off`` by inference — whether
    tracing is attempted at all is decided by ``obs.tracing.tracing_enabled()``; this function only
    decides how safe a requested mode is). In production, ``full_synthetic_only`` is downgraded to
    ``safe_metadata_only`` — full raw tracing is never reachable from a production env var alone."""
    requested = (os.getenv("SEALAI_V2_LANGSMITH_TRACING_MODE") or "").strip().lower()
    if requested not in _VALID_MODES:
        requested = "safe_metadata_only"
    if requested == "full_synthetic_only" and is_production():
        return "safe_metadata_only"
    return requested


def hmac_id(value: str, *, secret: str | None = None) -> str:
    """Stable, non-reversible id for a piece of content (e.g. a question) — same input always
    produces the same output (so repeated occurrences are still correlatable in a trace), but the
    original value cannot be recovered from it. Never use this as the ONLY safety net for something
    that must never correlate across tenants; it is for observability grouping, not anonymization
    guarantees beyond "not the raw text"."""
    key = (
        secret or os.getenv("SEALAI_V2_TRACE_HMAC_SECRET") or _DEFAULT_HMAC_PEPPER
    ).encode("utf-8")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


_DEFAULT_BUCKET_EDGES: tuple[float, ...] = (0, 1, 5, 10, 50, 100, 500, 1000, 5000)


def bucket_numeric_value(
    value: float, *, edges: tuple[float, ...] = _DEFAULT_BUCKET_EDGES
) -> str:
    """Coarse, reversible-resistant bucket label for a technical value (e.g. a pressure or
    temperature reading) — reserved for future use where an exact number is not observability-safe
    but its rough magnitude is useful. ``edges`` must be sorted ascending."""
    if value < edges[0]:
        return f"<{edges[0]:g}"
    for lo, hi in zip(edges, edges[1:]):
        if lo <= value < hi:
            return f"{lo:g}-{hi:g}"
    return f">={edges[-1]:g}"


# Second-line regex net — NEVER the primary mechanism (the primary mechanism is: don't put raw
# content into the projection in the first place). Catches obvious PII/identifier SHAPES if raw
# text ever reaches this function by mistake (e.g. a future call site regression).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_DIGIT_RE = re.compile(r"\b\d{5,}\b")
_URL_RE = re.compile(r"https?://\S+")
_IBAN_LIKE_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")


def redact_text_fallback(text: str) -> str:
    """Regex-based scrub of common PII/identifier shapes (emails, URLs, long digit runs,
    IBAN-like tokens). This is a defense-in-depth SECOND line, not the primary control — the
    primary control is that raw text never reaches a trace projection at all (see
    ``safe_input_projection`` / ``safe_output_projection`` below, and ``obs.tracing``)."""
    out = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    out = _URL_RE.sub("[REDACTED_URL]", out)
    out = _IBAN_LIKE_RE.sub("[REDACTED_ID]", out)
    out = _LONG_DIGIT_RE.sub("[REDACTED_NUMBER]", out)
    return out


def safe_input_projection(
    *,
    question: str | None,
    flags_repr: str | None,
    has_untrusted: bool,
) -> dict:
    """The ONLY view of a turn's input LangSmith may see in ``safe_metadata_only`` mode (the
    production default). No raw question text — length + a stable hash only."""
    q = question or ""
    return {
        "has_question": bool(q),
        "question_length": len(q),
        "question_hash": hmac_id(q) if q else None,
        "flags": flags_repr,
        "has_untrusted": bool(has_untrusted),
    }


def safe_output_projection(
    *,
    answer_text: str | None,
    answer_model: str | None,
    grounded: bool | None,
    verdict: str | None = None,
) -> dict:
    """The ONLY view of a turn's output LangSmith may see in ``safe_metadata_only`` mode. No raw
    answer text — length only."""
    a = answer_text or ""
    return {
        "answer_length": len(a),
        "answer_model": answer_model,
        "grounded": grounded,
        "verifier_status": verdict,
    }


@dataclass(frozen=True)
class LangSmithClientPolicy:
    """What ``obs.tracing.maybe_wrap_openai`` should configure on the LangSmith ``Client`` it
    constructs. ``hide_inputs``/``hide_outputs`` map directly onto the SDK's own redaction knobs —
    this is the mechanism the audit found was never actually invoked (the SDK defaults to showing
    everything unless a ``Client`` is built with these explicitly True)."""

    hide_inputs: bool
    hide_outputs: bool


def resolve_langsmith_client_policy() -> LangSmithClientPolicy:
    """Per-call (``wrap_openai``) redaction policy for the resolved tracing mode. Only
    ``full_synthetic_only`` (and only outside production — see ``resolve_tracing_mode``) ever
    disables the SDK's input/output hiding."""
    mode = resolve_tracing_mode()
    if mode == "full_synthetic_only":
        return LangSmithClientPolicy(hide_inputs=False, hide_outputs=False)
    return LangSmithClientPolicy(hide_inputs=True, hide_outputs=True)
