from __future__ import annotations

from typing import Any, Dict, List
import json
import re
import structlog

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app._legacy_v2.phase import PHASE
from app._legacy_v2.state import SealAIState, WorkingMemory
from app._legacy_v2.utils.jinja import render_template
from app._legacy_v2.utils.llm_factory import LazyChatOpenAI, get_model_tier
from app._legacy_v2.utils.messages import latest_user_text
from app._legacy_v2.utils.prompt_blocks import render_challenger_gate

logger = structlog.get_logger("langgraph_v2.conversational_rag")
_FALLBACK_TEXT = (
    "Ich habe allgemeine Informationen zu PTFE-Dichtungen gefunden, benötige aber für eine präzise "
    "Auslegung Ihres Rührwerks noch folgende Daten: Material/Handelsname, Medium, Temperatur und Druck."
)
_NO_DOCS_TEXT = "Ich konnte keine passenden Dokumente in der Wissensdatenbank finden."
_RAG_LLM: Any | None = None


def _extract_rag_context(state: SealAIState) -> str:
    panel_material = {}
    if state.reasoning.working_memory and isinstance(state.reasoning.working_memory.panel_material, dict):
        panel_material = state.reasoning.working_memory.panel_material
    rag_context = str(panel_material.get("rag_context") or "").strip()
    if rag_context:
        return rag_context
    return str(state.reasoning.context or "").strip()


def _extract_langgraph_config(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Any | None:
    config = kwargs.get("config")
    if config is not None:
        return config
    if args:
        candidate = args[0]
        if isinstance(candidate, dict):
            return candidate
    return None


def _extract_live_calc_tile(state: SealAIState) -> Dict[str, Any]:
    raw = getattr(state.working_profile, "live_calc_tile", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    model_dump = getattr(raw, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    return {}


def _build_profile_snapshot(state: SealAIState) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    working_profile = getattr(state.working_profile, "engineering_profile", None)
    model_dump = getattr(working_profile, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            snapshot.update(dumped)

    params = getattr(state.working_profile, "engineering_profile", None)
    as_dict = getattr(params, "as_dict", None)
    if callable(as_dict):
        for key, value in (as_dict() or {}).items():
            if value is not None:
                snapshot.setdefault(key, value)
    elif isinstance(params, dict):
        for key, value in params.items():
            if value is not None:
                snapshot.setdefault(key, value)

    extracted = getattr(state.working_profile, "extracted_params", None)
    if isinstance(extracted, dict):
        for key, value in extracted.items():
            if value is not None:
                snapshot.setdefault(key, value)

    # Canonical aliases used by downstream prompts and checks.
    if snapshot.get("speed_rpm") is None and snapshot.get("rpm") is not None:
        snapshot["speed_rpm"] = snapshot.get("rpm")
    if snapshot.get("shaft_diameter") is None:
        shaft_d = snapshot.get("shaft_d1_mm") or snapshot.get("shaft_d1") or snapshot.get("d1")
        if shaft_d is not None:
            snapshot["shaft_diameter"] = shaft_d

    return snapshot


def _build_engineering_physics_report(tile: Dict[str, Any]) -> tuple[str, bool]:
    if not tile:
        return "ENGINEERING PHYSICS REPORT: Keine berechneten Physikdaten verfuegbar.", False

    metrics: List[Dict[str, Any]] = [{"key": "status", "value": tile.get("status")}]
    for key in (
        "friction_power_watts",
        "compression_ratio_pct",
        "groove_fill_pct",
        "stretch_pct",
        "thermal_expansion_mm",
        "clearance_gap_mm",
    ):
        if tile.get(key) is not None:
            metrics.append({"key": key, "value": tile.get(key)})

    risk_flags = (
        "hrc_warning",
        "runout_warning",
        "pv_warning",
        "dry_running_risk",
        "extrusion_risk",
        "requires_backup_ring",
        "geometry_warning",
        "shrinkage_risk",
        "chem_warning",
    )
    has_risk = any(bool(tile.get(flag)) for flag in risk_flags)

    report = render_challenger_gate(tile=tile, metrics=metrics)
    return report, has_risk


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


def _extract_shaft_hardness_hrc(state: SealAIState, user_query: str) -> float | None:
    params = getattr(state.working_profile, "engineering_profile", None)
    for value in (
        getattr(params, "shaft_hardness", None) if params is not None else None,
        getattr(params, "hardness", None) if params is not None else None,
    ):
        if value is None:
            continue
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(value))
        if match and "hrc" in str(value).lower():
            try:
                return float(match.group(0).replace(",", "."))
            except ValueError:
                pass
    query_match = re.search(
        r"(?:wellenh[aä]rte|h[aä]rte)\D{0,20}([-+]?\d+(?:[.,]\d+)?)\s*hrc",
        user_query or "",
        re.IGNORECASE,
    )
    if query_match:
        try:
            return float(query_match.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def _get_rag_llm(model_name: str) -> Any:
    global _RAG_LLM
    if _RAG_LLM is None:
        _RAG_LLM = LazyChatOpenAI(
            model=model_name,
            temperature=0,
            cache=False,
            max_tokens=1000,
            streaming=True,
        )
    return _RAG_LLM


async def conversational_rag_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    user_query = (latest_user_text(state.conversation.messages or []) or "").strip()
    rag_context = _extract_rag_context(state)
    live_calc_tile = _extract_live_calc_tile(state)
    profile_snapshot = _build_profile_snapshot(state)
    physics_report, has_physics_risk = _build_engineering_physics_report(live_calc_tile)
    _calc_results = state.working_profile.calc_results
    calc_notes = list((_calc_results.notes if _calc_results else []) or [])
    if calc_notes:
        notes_block = "\n".join(f"- {note}" for note in calc_notes)
        physics_report = f"{physics_report}\n\nSYSTEM WARNMELDUNGEN (WÖRTLICH ZITIEREN):\n{notes_block}"
    if physics_report:
        logger.info("material_agent.deterministic_constraints_injected", physics_report_len=len(physics_report))
    flags = state.reasoning.flags or {}
    low_quality = bool(flags.get("rag_low_quality_results"))
    rag_turn_count = int(getattr(state.reasoning, "rag_turn_count", 0) or 0)
    config = _extract_langgraph_config(_args, _kwargs)

    if not rag_context or low_quality:
        if rag_turn_count >= 3 or flags.get("rag_limit_reached"):
            final_text = _NO_DOCS_TEXT
        else:
            final_text = _FALLBACK_TEXT
    else:
        model_name = get_model_tier("mini")
        hardness_hrc = _extract_shaft_hardness_hrc(state, user_query)
        hardness_warning = ""
        if hardness_hrc is not None and hardness_hrc < 58.0:
            hardness_warning = (
                f"\nAKUTE WARNUNG: Angegebene Wellenhaerte {hardness_hrc:.1f} HRC liegt unter 58 HRC. "
                "Warne explizit vor moeglichem Versagen der PTFE-Loesung durch Abrasivitaet."
            )
        system_prompt = render_template(
            "material_scientist_agent.j2",
            {
                "agent_mode": "contextual_consulting",
                "challenger_gate_text": physics_report,
                "working_profile_json": json.dumps(profile_snapshot, ensure_ascii=False, indent=2),
                "calculation_results_json": json.dumps(live_calc_tile, ensure_ascii=False, indent=2),
                "rag_context": rag_context,
                "has_physics_risk": has_physics_risk,
                "hardness_warning_text": hardness_warning.strip(),
            },
        )
        user_prompt = user_query or "Bitte gib eine kurze, hilfreiche technische Erklärung."
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        chunks: List[str] = []
        llm = _get_rag_llm(model_name)
        async for chunk in llm.astream(messages, config=config):
            text = _chunk_to_text(chunk)
            if text:
                chunks.append(text)
        final_text = "".join(chunks).strip()
        if not final_text:
            final_text = _FALLBACK_TEXT

    messages = list(state.conversation.messages or [])
    messages.append(AIMessage(content=[{"type": "text", "text": final_text}]))
    wm = state.reasoning.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"response_text": final_text})

    return {
               "conversation": {
                   "messages": messages,
               },
               "reasoning": {
                   "working_memory": wm,
                   "phase": PHASE.KNOWLEDGE,
                   "last_node": "conversational_rag_node",
               },
               "system": {
                   "governed_output_text": final_text,
                   "governed_output_status": "conversational_rag",
                   "governed_output_ready": True,
                   "final_text": final_text,    # legacy mirror
                   "final_answer": final_text,  # legacy mirror
               },
           }


__all__ = ["conversational_rag_node"]
