"""WORM evidence bundle generation node.

Builds and seals an immutable evidence bundle from state, then writes it to a
local append-only simulation store representing S3/Postgres WORM storage.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import structlog

from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.state.audit import EvidenceBundle, SourceRefPayload, ToolCallRecord
from app.services.rag.state import WorkingProfile

logger = structlog.get_logger("langgraph_v2.worm_evidence")

_DEFAULT_WORM_DIR = "/tmp/sealai_worm_store"


def _to_tool_call_records(items: List[Any]) -> List[ToolCallRecord]:
    records: List[ToolCallRecord] = []
    for item in items or []:
        if isinstance(item, ToolCallRecord):
            records.append(item)
        elif isinstance(item, dict):
            records.append(ToolCallRecord.model_validate(item))
    return records


def _to_source_ref_payloads(items: List[Any]) -> List[SourceRefPayload]:
    payloads: List[SourceRefPayload] = []
    for item in items or []:
        if isinstance(item, SourceRefPayload):
            payloads.append(item)
        elif isinstance(item, dict):
            payloads.append(SourceRefPayload.model_validate(item))
    return payloads


def _resolve_worm_root() -> Path:
    configured = str(os.getenv("SEALAI_WORM_SIMULATED_DIR", _DEFAULT_WORM_DIR)).strip() or _DEFAULT_WORM_DIR
    return Path(configured)


def _extract_hash(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else ""


def _extract_audit_hashes(state: SealAIState) -> tuple[str, str]:
    wm_diag: Dict[str, Any] = {}
    if state.working_memory is not None and isinstance(getattr(state.working_memory, "diagnostic_data", None), dict):
        wm_diag = dict(state.working_memory.diagnostic_data or {})

    flags = dict(state.flags or {})
    prompt_hash = _extract_hash(
        wm_diag.get("reasoning_system_prompt_hash")
        or flags.get("reasoning_system_prompt_hash")
        or (state.final_prompt_metadata or {}).get("prompt_hash")
    )
    guard_hash = _extract_hash(
        wm_diag.get("combinatorial_guard_version_hash")
        or flags.get("combinatorial_guard_version_hash")
    )
    return prompt_hash, guard_hash


def _write_immutable_bundle(bundle: EvidenceBundle) -> str:
    root = _resolve_worm_root()
    root.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    date_prefix = now.strftime("%Y/%m/%d")
    bundle_key = f"worm://sealai/{date_prefix}/{bundle.bundle_id}_{bundle.bundle_hash_sha256[:16]}.json"

    relative = bundle_key.replace("worm://sealai/", "")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = bundle.model_dump(mode="json", exclude_none=True)
    # Exclusive create emulates write-once behavior.
    with target.open("x", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    return bundle_key


def worm_evidence_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    profile = state.working_profile or WorkingProfile()
    reasoning_system_prompt_hash, combinatorial_guard_version_hash = _extract_audit_hashes(state)
    bundle = EvidenceBundle.from_components(
        working_profile=profile,
        tool_calls=_to_tool_call_records(list(state.tool_call_records or [])),
        source_ref_payloads=_to_source_ref_payloads(list(state.source_ref_payloads or [])),
        run_id=state.run_id,
        thread_id=state.thread_id,
        user_id=state.user_id,
        tenant_id=state.tenant_id,
        reasoning_system_prompt_hash=reasoning_system_prompt_hash,
        combinatorial_guard_version_hash=combinatorial_guard_version_hash,
        metadata={
            "phase": state.phase,
            "last_node": state.last_node,
            "final_text_present": bool((state.final_text or "").strip()),
            "final_answer_present": bool((state.final_answer or "").strip()),
            "final_prompt_metadata": dict(state.final_prompt_metadata or {}),
            "reasoning_system_prompt_hash_present": bool(reasoning_system_prompt_hash),
            "combinatorial_guard_version_hash_present": bool(combinatorial_guard_version_hash),
        },
    )
    digest = bundle.seal()
    bundle_key = _write_immutable_bundle(bundle)

    next_profile = profile.model_copy(update={"evidence_bundle_key": bundle_key})
    flags = dict(state.flags or {})
    flags.update(
        {
            "worm_bundle_written": True,
            "worm_bundle_key": bundle_key,
            "worm_bundle_hash": digest,
        }
    )

    logger.info(
        "worm_evidence_bundle_written",
        bundle_id=bundle.bundle_id,
        bundle_key=bundle_key,
        bundle_hash=digest,
        thread_id=state.thread_id,
        run_id=state.run_id,
    )

    return {
        "last_node": "worm_evidence_node",
        "working_profile": next_profile,
        "evidence_bundle": bundle,
        "evidence_bundle_hash": digest,
        "flags": flags,
    }


__all__ = ["worm_evidence_node"]
