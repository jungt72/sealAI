"""Recursive reasoning core for R3 engineering intents.

This node is strictly synthesis-only:
- consumes deterministic pre-computed state
- streams a user-facing response
- writes structured hypothesis updates back to WorkingProfile
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Tuple

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

from app._legacy_v2.phase import PHASE
from app._legacy_v2.state import SealAIState, WorkingMemory
from app._legacy_v2.utils.jinja import render_template
from app._legacy_v2.utils.llm_factory import LazyChatOpenAI, get_model_tier, run_llm_async
from app._legacy_v2.utils.messages import latest_user_text
from app._legacy_v2.utils.prompt_blocks import render_challenger_gate
from app.services.rag.state import WorkingProfile

logger = structlog.get_logger("langgraph_v2.reasoning_core")


_STREAM_LLM: LazyChatOpenAI | None = None
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")

_PROFILE_KEYS: tuple[str, ...] = (
    "medium",
    "medium_additives",
    "material",
    "pressure_min_bar",
    "pressure_max_bar",
    "temperature_min_c",
    "temperature_max_c",
    "dp_dt_bar_per_s",
    "side_load_kn",
    "cycle_rate_hz",
    "extrusion_gap_mm",
    "fluid_contamination_iso",
    "aed_required",
    "surface_hardness_hrc",
    "compound_aed_certified",
)


class ReasoningCoreStructuredUpdate(BaseModel):
    active_hypothesis: str | None = None
    candidate_materials: List[str] = Field(default_factory=list)


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(str(payload or "").encode("utf-8")).hexdigest()


def _extract_langgraph_config(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Any | None:
    config = kwargs.get("config")
    if config is not None:
        return config
    if args:
        candidate = args[0]
        if isinstance(candidate, dict):
            return candidate
    return None


def _chunk_to_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if text is not None:
                    parts.append(str(text))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content or "")


def _compact_profile(profile: WorkingProfile) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key in _PROFILE_KEYS:
        value = getattr(profile, key, None)
        if value is not None:
            compact[key] = value
    return compact


def _resolve_coverage_for_material(profile: WorkingProfile) -> Dict[str, Any]:
    raw = getattr(profile, "knowledge_coverage_check", {}) or {}
    if not isinstance(raw, dict):
        return {}
    material = str(getattr(profile, "material", "") or "").strip().upper()
    if not material:
        return raw

    for key in (material, material.lower(), material.upper()):
        value = raw.get(key)
        if isinstance(value, dict):
            return value

    by_material = raw.get("by_material")
    if isinstance(by_material, dict):
        for key in (material, material.lower(), material.upper()):
            value = by_material.get(key)
            if isinstance(value, dict):
                return value
    return raw


def _unresolved_coverage_gaps(profile: WorkingProfile) -> List[str]:
    coverage = _resolve_coverage_for_material(profile)
    gaps: List[str] = []
    for key, value in coverage.items():
        if str(key).startswith("_"):
            continue
        mandatory = True
        covered = False
        if isinstance(value, bool):
            covered = bool(value)
        elif isinstance(value, dict):
            mandatory = bool(value.get("mandatory", True))
            covered = bool(value.get("value") is True or value.get("covered") is True or value.get("ok") is True)
        if mandatory and not covered:
            gaps.append(str(key))
    return gaps


def _warning_notes(profile: WorkingProfile) -> List[str]:
    notes: List[str] = []
    for conflict in list(getattr(profile, "conflicts_detected", []) or []):
        if isinstance(conflict, dict):
            severity = str(conflict.get("severity") or "").upper()
            handled = bool(conflict.get("handled") or conflict.get("resolved"))
            title = str(conflict.get("title") or conflict.get("rule_id") or "").strip()
            reason = str(conflict.get("reason") or "").strip()
        else:
            severity = str(getattr(conflict, "severity", "") or "").upper()
            handled = bool(getattr(conflict, "handled", False) or getattr(conflict, "resolved", False))
            title = str(getattr(conflict, "title", "") or getattr(conflict, "rule_id", "")).strip()
            reason = str(getattr(conflict, "reason", "") or "").strip()
        if handled or severity not in {"WARNING", "NOTE"}:
            continue
        merged = f"{severity}: {title}".strip()
        if reason:
            merged = f"{merged} | {reason}"
        notes.append(merged)
    return notes


def _calc_snapshot(state: SealAIState) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    live_calc = getattr(state.working_profile, "live_calc_tile", None)
    if live_calc is not None:
        if isinstance(live_calc, dict):
            snapshot.update({k: v for k, v in live_calc.items() if v is not None})
        else:
            dump = getattr(live_calc, "model_dump", None)
            if callable(dump):
                data = dump(exclude_none=True)
                if isinstance(data, dict):
                    snapshot.update(data)
    calc_results = getattr(state.working_profile, "calc_results", None)
    if calc_results is not None:
        dump = getattr(calc_results, "model_dump", None)
        if callable(dump):
            data = dump(exclude_none=True)
            if isinstance(data, dict):
                snapshot.update({f"calc_{k}": v for k, v in data.items() if v is not None})
    if isinstance(getattr(state.working_profile, "calculation_result", None), dict):
        for key, value in state.working_profile.calculation_result.items():
            if value is not None and key not in snapshot:
                snapshot[key] = value
    return snapshot


def _render_calc_ranges(calc_snapshot: Dict[str, Any]) -> str:
    if not calc_snapshot:
        return "none"
    keys = [
        "status",
        "clearance_gap_mm",
        "extrusion_risk",
        "requires_backup_ring",
        "pv_value_mpa_m_s",
        "v_surface_m_s",
        "compression_ratio_pct",
        "groove_fill_pct",
        "stretch_pct",
        "calc_safety_factor",
        "calc_temperature_margin",
        "calc_pressure_margin",
        "temperature_margin_c",
        "pressure_margin_bar",
        "chem_warning",
        "chem_message",
    ]
    lines: List[str] = []
    for key in keys:
        if key in calc_snapshot:
            lines.append(f"{key}={calc_snapshot[key]}")
    if not lines:
        for key, value in list(calc_snapshot.items())[:12]:
            lines.append(f"{key}={value}")
    return "; ".join(lines)


def _build_deterministic_constraints(state: SealAIState) -> str:
    tile = getattr(state.working_profile, "live_calc_tile", None)
    profile = state.working_profile
    if profile:
        conditions: List[str] = []
        if getattr(profile, "pressure_max_bar", None) is not None:
            conditions.append(f"Druck: {profile.pressure_max_bar} bar")
        if getattr(profile, "temperature_max_c", None) is not None:
            conditions.append(f"Temperatur: {profile.temperature_max_c} °C")
        if getattr(profile, "medium", None):
            conditions.append(f"Medium: {profile.medium}")
        return render_challenger_gate(tile=tile, conditions=conditions)
    return render_challenger_gate(tile=tile)


def _build_system_prompt(
    *,
    state: SealAIState,
    profile: WorkingProfile,
    unresolved_gaps: List[str],
    warning_notes: List[str],
    calc_ranges: str,
    structured_json_only: bool = False,
) -> str:
    return render_template(
        "mechanical_design_agent.j2",
        {
            "challenger_gate_text": _build_deterministic_constraints(state),
            "core_profile_json": json.dumps(_compact_profile(profile), ensure_ascii=False, separators=(",", ":")),
            "working_profile_json": json.dumps(_compact_profile(profile), ensure_ascii=False, separators=(",", ":")),
            "calculation_results_json": json.dumps(_calc_snapshot(state), ensure_ascii=False, separators=(",", ":")),
            "unresolved_gaps_text": ", ".join(unresolved_gaps) if unresolved_gaps else "none",
            "warning_notes_text": " | ".join(warning_notes) if warning_notes else "none",
            "calc_ranges": calc_ranges,
            "rag_context": getattr(state.reasoning, "context", "") or "",
            "structured_json_only": structured_json_only,
        },
    )


def _parse_structured_payload(raw_text: str) -> ReasoningCoreStructuredUpdate:
    text = (raw_text or "").strip()
    if not text:
        return ReasoningCoreStructuredUpdate()
    candidates = [text]
    match = _JSON_OBJECT_RE.search(text)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        try:
            return ReasoningCoreStructuredUpdate.model_validate(payload)
        except ValidationError:
            continue
    return ReasoningCoreStructuredUpdate()


def _merge_candidate_materials(existing: List[str], new_values: List[str]) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for item in [*(existing or []), *(new_values or [])]:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.upper()
        if key in seen:
            continue
        seen.add(key)
        merged.append(key)
    return merged[:8]


def _get_stream_llm(model_name: str) -> LazyChatOpenAI:
    global _STREAM_LLM
    if _STREAM_LLM is None:
        _STREAM_LLM = LazyChatOpenAI(
            model=model_name,
            temperature=0,
            cache=False,
            max_tokens=800,
            streaming=True,
        )
    return _STREAM_LLM


async def _stream_reasoning_text(
    *,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    config: Any | None,
) -> Tuple[str, int | None]:
    llm = _get_stream_llm(model_name)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    chunks: List[str] = []
    t0 = time.perf_counter()
    first_token_ms: int | None = None
    async for chunk in llm.astream(messages, config=config):
        text = _chunk_to_text(chunk)
        if not text:
            continue
        if first_token_ms is None:
            first_token_ms = int((time.perf_counter() - t0) * 1000)
        chunks.append(text)
    return "".join(chunks).strip(), first_token_ms


async def reasoning_core_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Recursive, synthesis-only reasoning node for R3."""
    config = _extract_langgraph_config(_args, _kwargs)
    profile = state.working_profile or WorkingProfile()
    unresolved_gaps = _unresolved_coverage_gaps(profile)
    warning_notes = _warning_notes(profile)
    calc_ranges = _render_calc_ranges(_calc_snapshot(state))
    user_prompt = (latest_user_text(state.conversation.messages or []) or "").strip() or "Bitte leite den naechsten besten Datenerhebungs-Schritt ab."
    system_prompt = _build_system_prompt(
        state=state,
        profile=profile,
        unresolved_gaps=unresolved_gaps,
        warning_notes=warning_notes,
        calc_ranges=calc_ranges,
        structured_json_only=False,
    )
    reasoning_system_prompt_hash = _sha256_text(system_prompt)
    model_name = get_model_tier("mini")

    async def _structured_pass() -> ReasoningCoreStructuredUpdate:
        raw = await run_llm_async(
            model=model_name,
            prompt=user_prompt,
            system=_build_system_prompt(
                state=state,
                profile=profile,
                unresolved_gaps=unresolved_gaps,
                warning_notes=warning_notes,
                calc_ranges=calc_ranges,
                structured_json_only=True,
            ),
            temperature=0.0,
            max_tokens=220,
        )
        return _parse_structured_payload(raw)

    structured_task = asyncio.create_task(_structured_pass())
    first_token_ms: int | None = None
    llm_text = ""

    try:
        llm_text, first_token_ms = await _stream_reasoning_text(
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            config=config,
        )
    except Exception as exc:
        logger.exception("reasoning_core_stream_failed", error=str(exc))
        llm_text = ""

    try:
        structured = await structured_task
    except Exception as exc:
        logger.warning("reasoning_core_structured_pass_failed", error=str(exc))
        structured = ReasoningCoreStructuredUpdate()

    if not llm_text:
        if unresolved_gaps:
            llm_text = (
                "Zwischenstand: Die deterministische Datenabdeckung ist noch unvollstaendig. "
                f"Bitte liefern Sie als naechstes: {', '.join(unresolved_gaps[:4])}."
            )
        else:
            llm_text = "Zwischenstand: Ich brauche eine kurze Praezisierung zu Medium, Druckverlauf oder Temperaturbereich."

    merged_candidates = _merge_candidate_materials(
        getattr(profile, "candidate_materials", []),
        structured.candidate_materials,
    )
    next_profile = profile.model_copy(
        update={
            "active_hypothesis": structured.active_hypothesis or getattr(profile, "active_hypothesis", None),
            "candidate_materials": merged_candidates,
        }
    )

    messages = list(state.conversation.messages or [])
    messages.append(AIMessage(content=[{"type": "text", "text": llm_text}]))

    wm = state.reasoning.working_memory or WorkingMemory()
    diagnostic_data = dict(getattr(wm, "diagnostic_data", {}) or {})
    diagnostic_data.update(
        {
            "reasoning_system_prompt_hash": reasoning_system_prompt_hash,
            "reasoning_model_name": model_name,
        }
    )
    wm = wm.model_copy(
        update={
            "response_text": llm_text,
            "diagnostic_data": diagnostic_data,
        }
    )

    flags = dict(state.reasoning.flags or {})
    flags.update(
        {
            "reasoning_core_r3_active": True,
            "reasoning_core_first_token_ms": first_token_ms,
            "reasoning_core_unresolved_gap_count": len(unresolved_gaps),
            "reasoning_system_prompt_hash": reasoning_system_prompt_hash,
        }
    )

    logger.info(
        "reasoning_core_completed",
        first_token_ms=first_token_ms,
        unresolved_gap_count=len(unresolved_gaps),
        warning_count=len(warning_notes),
        candidate_count=len(merged_candidates),
        run_id=state.system.run_id,
        thread_id=state.conversation.thread_id,
    )

    return {
               "working_profile": next_profile,
               "conversation": {
                   "messages": messages,
               },
               "reasoning": {
                   "working_memory": wm,
                   "awaiting_user_input": bool(unresolved_gaps),
                   "flags": flags,
                   "phase": PHASE.CONSULTING,
                   "last_node": "reasoning_core_node",
                   "round_index": int(getattr(state.reasoning, "round_index", 0) or 0) + 1,
                   "turn_count": int(getattr(state.reasoning, "turn_count", 0) or 0) + 1,
               },
               "system": {
                   "preview_text": llm_text,
               },
           }


__all__ = ["reasoning_core_node", "ReasoningCoreStructuredUpdate"]
