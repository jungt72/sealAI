"""SealAI-specific LangSmith quality metadata and redaction helpers.

LangSmith is useful for production quality work only when traces are searchable
without leaking customer wording, IDs, secrets, or technical documents. This
module keeps SealAI's repository as the source of truth and emits only
review-oriented metadata for LangSmith Engine/Evaluators.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

SENSITIVE_REPLACEMENT = "[redacted]"
HASH_PREFIX = "h_"
MAX_TRACE_STRING = 240
MAX_TRACE_ITEMS = 24
GOVERNANCE_VERSION = "v9.2"

_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|cookie|jwt|"
    r"access[_-]?token|refresh[_-]?token|client[_-]?secret)",
    re.IGNORECASE,
)
_CONTENT_KEY_RE = re.compile(
    r"(message|messages|content|text|prompt|completion|markdown|raw|body|"
    r"page_content|snippet|statement|answer|response|query|input|output)",
    re.IGNORECASE,
)
_IDENTITY_KEY_RE = re.compile(
    r"(^|_)(tenant|user|session|thread|case|preview)(_id|id)?$|"
    r"(^|_)request(_id|id)$|"
    r"^(tenant_id|user_id|session_id|thread_id|case_id|preview_id|request_id|sub)$",
    re.IGNORECASE,
)
_HASH_KEY_RE = re.compile(r"(^|_)(hash|id_hash)$", re.IGNORECASE)
_TRACE_HASH_RE = re.compile(r"^h_[0-9a-f]{20}$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_KEYLIKE_RE = re.compile(r"\b(?:sk|lsv2|pk|rk)-[A-Za-z0-9._-]{12,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d ()./-]{7,}\d)(?!\d)")


def _trace_salt() -> bytes:
    salt = (
        os.getenv("SEALAI_TRACE_HASH_SALT")
        or os.getenv("LANGSMITH_TRACE_SALT")
        or os.getenv("AUTH_SECRET")
        or os.getenv("NEXTAUTH_SECRET")
        or "sealai-observability"
    )
    return salt.encode("utf-8")


def stable_trace_hash(value: Any) -> str | None:
    """Return a stable, non-reversible trace hash for identifiers/content."""

    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    digest = hmac.new(_trace_salt(), text.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{HASH_PREFIX}{digest[:20]}"


def _is_trace_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_TRACE_HASH_RE.fullmatch(value))


def redact_text(value: str, *, max_length: int = MAX_TRACE_STRING) -> str:
    """Redact common secrets/PII from a scalar string and bound its size."""

    cleaned = _EMAIL_RE.sub(SENSITIVE_REPLACEMENT, value)
    cleaned = _BEARER_RE.sub(SENSITIVE_REPLACEMENT, cleaned)
    cleaned = _KEYLIKE_RE.sub(SENSITIVE_REPLACEMENT, cleaned)
    cleaned = _PHONE_RE.sub(SENSITIVE_REPLACEMENT, cleaned)
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[:max_length]}...[truncated:{len(cleaned)}]"


def _redacted_content_summary(value: Any) -> dict[str, Any]:
    text = "" if value is None else str(value)
    return {
        "redacted": True,
        "kind": "content",
        "length": len(text),
        "hash": stable_trace_hash(text),
    }


def _redacted_identifier(value: Any) -> str | None:
    return stable_trace_hash(value)


def _model_public_shape(value: Any) -> dict[str, Any]:
    shape: dict[str, Any] = {"type": type(value).__name__}
    for attr in (
        "tenant_id",
        "user_id",
        "session_id",
        "thread_id",
        "case_id",
        "preview_id",
        "sub",
    ):
        if hasattr(value, attr):
            hashed = stable_trace_hash(getattr(value, attr))
            if hashed:
                shape[f"{attr}_hash"] = hashed
    if hasattr(value, "message"):
        shape["message"] = _redacted_content_summary(getattr(value, "message"))
    return shape


def redact_trace_value(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    """Return a LangSmith-safe representation for inputs, outputs, metadata."""

    if value is None or isinstance(value, bool | int | float):
        return value
    if key and _SENSITIVE_KEY_RE.search(key):
        return SENSITIVE_REPLACEMENT
    if (key and _HASH_KEY_RE.search(key) and _is_trace_hash(value)) or _is_trace_hash(
        value
    ):
        return value
    if key and _IDENTITY_KEY_RE.search(key):
        return _redacted_identifier(value)
    if key and _CONTENT_KEY_RE.search(key):
        if isinstance(value, Mapping):
            return {
                str(raw_key): redact_trace_value(
                    item, key=str(raw_key), depth=depth + 1
                )
                for raw_key, item in list(value.items())[:MAX_TRACE_ITEMS]
            }
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            items = list(value)
            safe_items = [
                redact_trace_value(
                    item,
                    key=("content" if isinstance(item, str) else None),
                    depth=depth + 1,
                )
                for item in items[:MAX_TRACE_ITEMS]
            ]
            if len(items) > MAX_TRACE_ITEMS:
                safe_items.append({"_truncated_items": len(items) - MAX_TRACE_ITEMS})
            return safe_items
        return _redacted_content_summary(value)
    if isinstance(value, str):
        return redact_text(value)
    if depth >= 4:
        return {"redacted": True, "reason": "max_depth", "type": type(value).__name__}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return redact_trace_value(dataclasses.asdict(value), depth=depth + 1)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="python")
        except TypeError:
            dumped = value.model_dump()
        except Exception:  # noqa: BLE001
            return _model_public_shape(value)
        return {
            "type": type(value).__name__,
            "fields": redact_trace_value(dumped, depth=depth + 1),
        }
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= MAX_TRACE_ITEMS:
                safe["_truncated_items"] = len(value) - MAX_TRACE_ITEMS
                break
            key_text = str(raw_key)
            safe[key_text] = redact_trace_value(item, key=key_text, depth=depth + 1)
        return safe
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
        safe_items = [
            redact_trace_value(item, depth=depth + 1)
            for item in items[:MAX_TRACE_ITEMS]
        ]
        if len(items) > MAX_TRACE_ITEMS:
            safe_items.append({"_truncated_items": len(items) - MAX_TRACE_ITEMS})
        return safe_items
    if hasattr(value, "__dict__"):
        return _model_public_shape(value)
    return redact_text(str(value))


def redact_trace_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Redact metadata without dropping top-level quality keys.

    LangSmith quality work depends on stable scalar metadata such as route,
    V9.2 status and evaluator flags. Nested payloads are still size-bounded by
    `redact_trace_value`, but the metadata envelope itself is not truncated.
    """

    return {
        str(raw_key): redact_trace_value(item, key=str(raw_key), depth=1)
        for raw_key, item in metadata.items()
    }


def sanitize_trace_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Default `traceable.process_inputs` hook for custom SealAI spans."""

    return redact_trace_value(inputs)


def sanitize_trace_outputs(output: Any) -> Any:
    """Default `traceable.process_outputs` hook for custom SealAI spans."""

    return redact_trace_value(output, key="output")


def identity_trace_metadata(
    *,
    request: Any | None = None,
    current_user: Any | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    case_id: str | None = None,
    preview_id: str | None = None,
) -> dict[str, Any]:
    """Build hashed tenant/user/session/case metadata for grouping traces."""

    resolved_user_id = (
        user_id
        or getattr(current_user, "user_id", None)
        or getattr(current_user, "sub", None)
    )
    tenant_claim = tenant_id or getattr(current_user, "tenant_id", None)
    resolved_tenant_id = tenant_claim or resolved_user_id
    resolved_session_id = (
        session_id
        or getattr(request, "session_id", None)
        or getattr(request, "thread_id", None)
    )
    resolved_case_id = case_id or getattr(request, "case_id", None)

    metadata: dict[str, Any] = {
        "tenant_metadata_present": bool(resolved_tenant_id),
        "tenant_metadata_source": "tenant_claim"
        if tenant_claim
        else ("user_scope_fallback" if resolved_user_id else "missing"),
        "user_metadata_present": bool(resolved_user_id),
        "session_metadata_present": bool(resolved_session_id),
        "case_metadata_present": bool(resolved_case_id),
    }
    for name, value in (
        ("tenant_id_hash", resolved_tenant_id),
        ("user_id_hash", resolved_user_id),
        ("session_id_hash", resolved_session_id),
        ("thread_id", resolved_session_id),
        ("case_id_hash", resolved_case_id),
        ("preview_id_hash", preview_id),
    ):
        hashed = stable_trace_hash(value)
        if hashed:
            metadata[name] = hashed
    return metadata


def build_quality_metadata(
    *,
    component: str,
    request: Any | None = None,
    current_user: Any | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    case_id: str | None = None,
    preview_id: str | None = None,
    **values: Any,
) -> dict[str, Any]:
    """Build the standard SealAI quality metadata envelope."""

    metadata = {
        "sealai_component": component,
        "governance_version": GOVERNANCE_VERSION,
        "quality_layer": "langsmith_observability",
        "engine_review_mode": "human_review_required",
        "engine_auto_merge_allowed": False,
    }
    metadata.update(
        identity_trace_metadata(
            request=request,
            current_user=current_user,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            case_id=case_id,
            preview_id=preview_id,
        )
    )
    metadata.update(redact_trace_metadata(values))
    return metadata


def emit_current_trace_metadata(
    metadata: Mapping[str, Any], *, tags: Sequence[str] = ()
) -> None:
    """Attach metadata/tags to the active LangSmith run if one exists."""

    try:
        from langsmith import get_current_run_tree  # type: ignore

        run_tree = get_current_run_tree()
    except Exception:  # noqa: BLE001
        return
    if run_tree is None:
        return
    safe_metadata = redact_trace_metadata(dict(metadata))
    try:
        current_metadata = getattr(run_tree, "metadata", None)
        if isinstance(current_metadata, dict):
            current_metadata.update(safe_metadata)
        else:
            setattr(run_tree, "metadata", safe_metadata)
        current_tags = getattr(run_tree, "tags", None)
        if isinstance(current_tags, list):
            for tag in tags:
                if tag not in current_tags:
                    current_tags.append(tag)
        elif tags:
            setattr(run_tree, "tags", list(tags))
    except Exception:  # noqa: BLE001
        return


def emit_quality_trace(
    *,
    component: str,
    tags: Sequence[str] = (),
    request: Any | None = None,
    current_user: Any | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    case_id: str | None = None,
    preview_id: str | None = None,
    **values: Any,
) -> None:
    """Build and attach the standard SealAI trace metadata envelope."""

    emit_current_trace_metadata(
        build_quality_metadata(
            component=component,
            request=request,
            current_user=current_user,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            case_id=case_id,
            preview_id=preview_id,
            **values,
        ),
        tags=("sealai", GOVERNANCE_VERSION, *tags),
    )


@dataclasses.dataclass(frozen=True)
class SealAIEvaluatorSpec:
    name: str
    feedback_key: str
    evaluation_type: str
    objective: str
    signal: str
    severity: str = "medium"
    engine_action_policy: str = "suggest_only_human_review_required"
    auto_merge_allowed: bool = False


SEALAI_EVALUATORS: tuple[SealAIEvaluatorSpec, ...] = (
    SealAIEvaluatorSpec(
        name="no_final_approval_claims",
        feedback_key="sealai.no_final_approval_claims",
        evaluation_type="code_or_llm_judge",
        objective="No response may present suitability, validation, compliance, or release as final approval.",
        signal="Detects approval language such as freigegeben, validiert, sicher geeignet, or FDA-konform without evidence.",
        severity="critical",
    ),
    SealAIEvaluatorSpec(
        name="rfq_boundary_guard",
        feedback_key="sealai.rfq_boundary_guard",
        evaluation_type="code_or_llm_judge",
        objective="RFQ previews remain clarification/request artifacts and never become technical releases.",
        signal="Checks RFQ traces for consent, open points, no dispatch, and no final technical release metadata.",
        severity="critical",
    ),
    SealAIEvaluatorSpec(
        name="asks_one_next_useful_question",
        feedback_key="sealai.asks_one_next_useful_question",
        evaluation_type="llm_judge",
        objective="Ask one useful next question when information is missing, not a broad checklist.",
        signal="Flags answer turns that ask many unrelated slots or fail to prioritize the next decision lever.",
    ),
    SealAIEvaluatorSpec(
        name="explains_parameter_relevance",
        feedback_key="sealai.explains_parameter_relevance",
        evaluation_type="llm_judge",
        objective="Explain why a requested parameter matters for the sealing decision.",
        signal="Checks whether Medium, Temperatur, Druck, Bewegung, Geometrie, or Compliance questions include relevance.",
    ),
    SealAIEvaluatorSpec(
        name="uncertainty_not_hidden",
        feedback_key="sealai.uncertainty_not_hidden",
        evaluation_type="llm_judge",
        objective="State assumptions, uncertainty, and missing evidence instead of overclaiming.",
        signal="Flags confident final statements when trace metadata shows missing slots or low evidence.",
        severity="high",
    ),
    SealAIEvaluatorSpec(
        name="no_forced_case_creation",
        feedback_key="sealai.no_forced_case_creation",
        evaluation_type="trajectory",
        objective="Smalltalk and pure knowledge questions must not create or mutate a governed case.",
        signal="Compares route_decision, case_creation_allowed, and runtime_action metadata.",
        severity="high",
    ),
    SealAIEvaluatorSpec(
        name="tenant_metadata_present",
        feedback_key="sealai.tenant_metadata_present",
        evaluation_type="code",
        objective="Every production trace has redacted tenant/user/session grouping metadata.",
        signal="Checks tenant_metadata_present, user_metadata_present, and hashed identity fields.",
        severity="high",
    ),
    SealAIEvaluatorSpec(
        name="rag_claim_level_respected",
        feedback_key="sealai.rag_claim_level_respected",
        evaluation_type="trajectory",
        objective="RAG evidence is not used beyond its source claim level or provenance.",
        signal="Checks source_ids, claim_levels, material_family, and answer claim wording.",
        severity="critical",
    ),
    SealAIEvaluatorSpec(
        name="compliance_claim_guard",
        feedback_key="sealai.compliance_claim_guard",
        evaluation_type="code_or_llm_judge",
        objective="FDA, ATEX, Food, Pharma, drinking-water, and other compliance claims require evidence and no release wording.",
        signal="Flags compliance claims without source_ids, claim_levels, or manufacturer review wording.",
        severity="critical",
    ),
)


def evaluator_catalog() -> list[dict[str, Any]]:
    """Return the repo-owned evaluator contract for LangSmith setup/review."""

    return [dataclasses.asdict(spec) for spec in SEALAI_EVALUATORS]
