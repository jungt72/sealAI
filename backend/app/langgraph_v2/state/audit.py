"""Audit and evidence schemas for LangGraph v2 observability."""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

try:
    from app.services.rag.state import WorkingProfile
except Exception:
    WorkingProfile = Any  # type: ignore[assignment,misc]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class ToolCallRecord(BaseModel):
    tool_name: str
    tool_input: Dict[str, Any] = Field(default_factory=dict)
    tool_output: Any = None
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime = Field(default_factory=_utcnow)
    duration_ms: int = 0
    status: str = "success"
    error_message: Optional[str] = None
    run_id: Optional[str] = None
    thread_id: Optional[str] = None
    tenant_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class SourceRefPayload(BaseModel):
    source_id: str
    chunk_text: str
    source: Optional[str] = None
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    effective_date: Optional[date] = None
    version: str = "1.0"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=_utcnow)

    model_config = ConfigDict(extra="forbid")


class EvidenceBundle(BaseModel):
    schema_version: str = "1.0.0"
    bundle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=_utcnow)
    run_id: Optional[str] = None
    thread_id: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    working_profile_snapshot: Dict[str, Any] = Field(default_factory=dict)
    reasoning_system_prompt_hash: str = ""
    combinatorial_guard_version_hash: str = ""
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    source_ref_payloads: List[SourceRefPayload] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    bundle_hash_sha256: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_components(
        cls,
        *,
        working_profile: WorkingProfile | Mapping[str, Any] | None,
        tool_calls: Optional[List[ToolCallRecord]] = None,
        source_ref_payloads: Optional[List[SourceRefPayload]] = None,
        run_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        reasoning_system_prompt_hash: Optional[str] = None,
        combinatorial_guard_version_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "EvidenceBundle":
        if isinstance(working_profile, BaseModel):
            working_profile_snapshot = dict(working_profile.model_dump(mode="json", exclude_none=True))
        elif isinstance(working_profile, Mapping):
            working_profile_snapshot = dict(working_profile)
        else:
            working_profile_snapshot = {}
        return cls(
            run_id=run_id,
            thread_id=thread_id,
            user_id=user_id,
            tenant_id=tenant_id,
            working_profile_snapshot=working_profile_snapshot,
            reasoning_system_prompt_hash=str(reasoning_system_prompt_hash or "").strip(),
            combinatorial_guard_version_hash=str(combinatorial_guard_version_hash or "").strip(),
            tool_calls=list(tool_calls or []),
            source_ref_payloads=list(source_ref_payloads or []),
            metadata=dict(metadata or {}),
        )

    def generate_sha256(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=True, exclude={"bundle_hash_sha256"})
        canonical_json = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def seal(self) -> str:
        digest = self.generate_sha256()
        self.bundle_hash_sha256 = digest
        return digest


_AUDIT_SINK: ContextVar[Optional[Callable[[ToolCallRecord], None]]] = ContextVar(
    "sealai_tool_audit_sink",
    default=None,
)


def emit_tool_call_record(record: ToolCallRecord) -> None:
    sink = _AUDIT_SINK.get()
    if sink is not None:
        sink(record)


def set_tool_audit_sink(sink: Callable[[ToolCallRecord], None]) -> Token:
    return _AUDIT_SINK.set(sink)


def reset_tool_audit_sink(token: Token) -> None:
    _AUDIT_SINK.reset(token)


@contextmanager
def tool_audit_context(sink: Callable[[ToolCallRecord], None]) -> Iterator[None]:
    token = set_tool_audit_sink(sink)
    try:
        yield
    finally:
        reset_tool_audit_sink(token)


def append_tool_call_to_state(state: Any, record: ToolCallRecord) -> None:
    if state is None:
        return
    payload = record.model_dump(mode="python")
    if isinstance(state, dict):
        records = state.setdefault("tool_call_records", [])
        if isinstance(records, list):
            records.append(payload)
        return
    records = getattr(state, "tool_call_records", None)
    if isinstance(records, list):
        records.append(record)


def build_tool_call_record(
    *,
    tool_name: str,
    tool_input: Mapping[str, Any],
    tool_output: Any,
    started_at: datetime,
    finished_at: datetime,
    error: Optional[Exception] = None,
    run_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ToolCallRecord:
    duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    return ToolCallRecord(
        tool_name=tool_name,
        tool_input=dict(_json_safe(dict(tool_input or {}))),
        tool_output=_json_safe(tool_output),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status="error" if error is not None else "success",
        error_message=str(error) if error is not None else None,
        run_id=run_id,
        thread_id=thread_id,
        tenant_id=tenant_id,
        metadata=dict(_json_safe(metadata or {})),
    )


__all__ = [
    "EvidenceBundle",
    "SourceRefPayload",
    "ToolCallRecord",
    "append_tool_call_to_state",
    "build_tool_call_record",
    "emit_tool_call_record",
    "reset_tool_audit_sink",
    "set_tool_audit_sink",
    "tool_audit_context",
]
