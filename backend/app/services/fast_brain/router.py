from __future__ import annotations

"""Legacy Fast-Brain router retained only for decommissioned LangGraph v2 runtime paths."""

import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.mcp.calculations.material_limits import check as check_material_limits
from app.mcp.knowledge_tool import aquery_deterministic_norms
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.messages import flatten_message_content, sanitize_message_history

logger = structlog.get_logger("fast_brain.router")
LEGACY_RUNTIME_DEPRECATED = True

_HANDOFF_TOKEN = "TRIGGER_SLOW_BRAIN"
_MAX_HISTORY_MESSAGES = 8
_MAX_TOOL_ROUNDS = 2
_FAST_BRAIN_TOOL_FAILURE_HANDOFF_TEXT = (
    "Die Schnellberechnung war aufgrund technischer Probleme nicht moeglich. "
    "Ich uebergebe an die vollstaendige Analyse."
)
_FAST_BRAIN_KNOWLEDGE_HANDOFF_TEXT = (
    "Die Anfrage benoetigt eine wissensbasierte Material- bzw. Dokumentenanalyse. "
    "Ich uebergebe an die vollstaendige Analyse."
)
_STANDARD_MATERIALS = ("NBR", "FKM", "PTFE")
_GENERAL_KNOWLEDGE_PATTERNS = (
    re.compile(
        r"\b(?:was\s+ist|wer\s+ist|erkl[aä]r(?:e|mir)|was\s+kannst\s+du\s+mir\s+(?:ueber|über|zu)\s+sagen|"
        r"was\s+wei(?:ss|ß)t\s+du\s+(?:ueber|über)|tell\s+me\s+about|what\s+is)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:eigenschaften|properties|werkstoff|material|trade[_\s-]?name|datenblatt|datasheet)\b", re.IGNORECASE),
)
_FALLBACK_SPEED_LIMITS_M_S = {
    "NBR": 12.0,
    "FKM": 35.0,
    "PTFE": 45.0,
}
_FALLBACK_PV_LIMITS_MPA_M_S = {
    "NBR": 1.5,
    "FKM": 3.0,
    "PTFE": 10.0,
}
_SPEED_LIMIT_KINDS = frozenset(
    {
        "speed",
        "speed_limit",
        "speed_m_s",
        "surface_speed",
        "surface_speed_m_s",
        "surface_velocity",
        "umfangsgeschwindigkeit",
        "v_max",
        "v_m_s",
    }
)
_PV_LIMIT_KINDS = frozenset(
    {
        "pv",
        "pv_limit",
        "pv_limit_mpa_m_s",
        "pv_mpa_m_s",
        "pv_value",
        "pv_value_mpa_m_s",
    }
)
_LIMIT_CONDITION_SPEED_KEYS = (
    "max_speed_m_s",
    "speed_limit_m_s",
    "surface_speed_m_s",
    "v_max",
    "v_m_s",
)
_LIMIT_CONDITION_PV_KEYS = (
    "max_pv_limit_mpa_m_s",
    "pv_limit_mpa_m_s",
    "pv_limit",
    "pv_value_mpa_m_s",
)


def _should_force_knowledge_handoff(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False

    try:
        from app.langgraph_v2.nodes.nodes_frontdoor import (
            detect_material_or_trade_query,
            detect_sources_request,
        )
    except Exception:
        detect_material_or_trade_query = None
        detect_sources_request = None

    if callable(detect_material_or_trade_query) and detect_material_or_trade_query(text):
        return True
    if callable(detect_sources_request) and detect_sources_request(text):
        return True
    return any(pattern.search(text) for pattern in _GENERAL_KNOWLEDGE_PATTERNS)


def _calculate_v_m_s(shaft_diameter_mm: float, speed_rpm: float) -> float:
    return (math.pi * shaft_diameter_mm * speed_rpm) / 60000.0


def _calculate_pv_value(pressure_bar: Optional[float], v_m_s: float) -> Optional[float]:
    if pressure_bar is None:
        return None
    return (pressure_bar * 0.1) * v_m_s


def _coerce_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", ".")
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


async def _lookup_material_limit_rows(
    *,
    material: str,
    pressure_bar: Optional[float],
    temperature_c: Optional[float],
) -> List[Dict[str, Any]]:
    try:
        payload = await aquery_deterministic_norms(
            material=material,
            temp=temperature_c if temperature_c is not None else 20.0,
            pressure=pressure_bar if pressure_bar is not None else 0.0,
        )
    except Exception:
        logger.exception("fast_brain_material_limits_query_failed", material=material)
        return []
    matches = payload.get("matches") if isinstance(payload, dict) else {}
    rows = matches.get("material_limits") if isinstance(matches, dict) else []
    return list(rows) if isinstance(rows, list) else []


def _extract_limit_value(
    rows: List[Dict[str, Any]],
    *,
    limit_kinds: frozenset[str],
    condition_keys: Tuple[str, ...],
) -> Tuple[Optional[float], List[str]]:
    values: List[float] = []
    source_refs: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("limit_kind") or "").strip().lower()
        if kind not in limit_kinds:
            continue
        candidate = _coerce_float(row.get("max_value"))
        if candidate is None:
            conditions = row.get("conditions")
            if isinstance(conditions, dict):
                for key in condition_keys:
                    candidate = _coerce_float(conditions.get(key))
                    if candidate is not None:
                        break
        if candidate is None:
            continue
        values.append(candidate)
        source_ref = str(row.get("source_ref") or "").strip()
        if source_ref and source_ref not in source_refs:
            source_refs.append(source_ref)
    return (min(values) if values else None), source_refs


def _format_limit_warning(
    *,
    metric_label: str,
    material: str,
    measured_value: float,
    limit_value: float,
    unit: str,
    source_refs: List[str],
) -> str:
    source_suffix = f" (Quelle: {', '.join(source_refs[:2])})" if source_refs else ""
    return (
        f"{metric_label} {measured_value:.2f} {unit} überschreitet {material}-Limit "
        f"von {limit_value:.2f} {unit}{source_suffix}."
    )


async def _screen_standard_materials(
    *,
    v_m_s: float,
    pv_value: Optional[float],
    pressure_bar: Optional[float],
    temperature_c: Optional[float],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    warnings: List[str] = []
    screening: List[Dict[str, Any]] = []
    has_any_db_limit_rows = False

    for material in _STANDARD_MATERIALS:
        rows = await _lookup_material_limit_rows(
            material=material,
            pressure_bar=pressure_bar,
            temperature_c=temperature_c,
        )
        has_db_limit_rows = bool(rows)
        has_any_db_limit_rows = has_any_db_limit_rows or has_db_limit_rows
        db_speed_limit, speed_refs = _extract_limit_value(
            rows,
            limit_kinds=_SPEED_LIMIT_KINDS,
            condition_keys=_LIMIT_CONDITION_SPEED_KEYS,
        )
        db_pv_limit, pv_refs = _extract_limit_value(
            rows,
            limit_kinds=_PV_LIMIT_KINDS,
            condition_keys=_LIMIT_CONDITION_PV_KEYS,
        )
        speed_limit = db_speed_limit if db_speed_limit is not None else _FALLBACK_SPEED_LIMITS_M_S.get(material)
        pv_limit = db_pv_limit if db_pv_limit is not None else _FALLBACK_PV_LIMITS_MPA_M_S.get(material)
        limit_check = check_material_limits(
            material,
            temp_c=temperature_c,
            pressure_bar=pressure_bar,
            is_dynamic=True,
        )

        material_warnings: List[str] = []
        if speed_limit is not None and v_m_s > speed_limit:
            material_warnings.append(
                _format_limit_warning(
                    metric_label="v_m_s",
                    material=material,
                    measured_value=v_m_s,
                    limit_value=speed_limit,
                    unit="m/s",
                    source_refs=speed_refs,
                )
            )
        if pv_value is not None and pv_limit is not None and pv_value > pv_limit:
            material_warnings.append(
                _format_limit_warning(
                    metric_label="pV",
                    material=material,
                    measured_value=pv_value,
                    limit_value=pv_limit,
                    unit="MPa*m/s",
                    source_refs=pv_refs,
                )
            )
        material_warnings.extend(limit_check.warnings)

        screening.append(
            {
                "material": material,
                "has_database_limits": has_db_limit_rows,
                "speed_limit_m_s": speed_limit,
                "pv_limit_mpa_m_s": pv_limit,
                "pressure_dynamic_max_bar": limit_check.limits.pressure_dynamic_max_bar,
                "temperature_max_c": limit_check.limits.temp_max_c,
                "source_refs": sorted(set(speed_refs + pv_refs)),
                "warnings": material_warnings,
                "database_message": (
                    None
                    if has_db_limit_rows
                    else "Ich finde keine spezifischen Normwerte in der Datenbank für dieses Material."
                ),
            }
        )
        warnings.extend(material_warnings)

    deduped_warnings: List[str] = []
    for warning in warnings:
        if warning not in deduped_warnings:
            deduped_warnings.append(warning)
    if not has_any_db_limit_rows:
        deduped_warnings.append("Ich finde keine spezifischen Normwerte in der Datenbank für dieses Material.")
    return deduped_warnings, screening


class CalculatePhysicsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shaft_diameter_mm: float = Field(..., description="Wellendurchmesser in mm")
    speed_rpm: float = Field(..., description="Drehzahl in U/min")
    pressure_bar: Optional[float] = Field(None, description="Druck in bar")
    temperature_c: Optional[float] = Field(None, description="Temperatur in °C")


@tool("live_physics_tool", args_schema=CalculatePhysicsArgs)
async def live_physics_tool(
    shaft_diameter_mm: float,
    speed_rpm: float,
    pressure_bar: Optional[float] = None,
    temperature_c: Optional[float] = None,
) -> str:
    """Berechnet v/pV und prüft deterministische Material-Grenzwerte für Standardwerkstoffe."""
    v_m_s = _calculate_v_m_s(shaft_diameter_mm=shaft_diameter_mm, speed_rpm=speed_rpm)
    pv_value = _calculate_pv_value(pressure_bar=pressure_bar, v_m_s=v_m_s)
    warnings, material_screening = await _screen_standard_materials(
        v_m_s=v_m_s,
        pv_value=pv_value,
        pressure_bar=pressure_bar,
        temperature_c=temperature_c,
    )
    result = {
        "v_m_s": round(v_m_s, 2),
        "pv": round(pv_value, 2) if pv_value is not None else None,
        "warnings": warnings,
        "material_screening": material_screening,
        "status": "success",
    }
    logger.info("fast_brain_live_physics_tool", result=result)
    return json.dumps(result, ensure_ascii=False)


class FastBrainRouter:
    def __init__(self, *, model: str = "gpt-4o-mini", temperature: float = 0) -> None:
        self.llm = ChatOpenAI(model=model, temperature=temperature)
        self.tools: List[BaseTool] = [live_physics_tool]
        self._tool_by_name = {tool_.name: tool_ for tool_ in self.tools}
        self.llm_with_tools = self.llm.bind_tools(self.tools)

    async def chat(self, user_input: str, history: List[Any]) -> Dict[str, Any]:
        messages = self._build_messages(user_input=user_input, history=history)
        if _should_force_knowledge_handoff(user_input):
            logger.info("fast_brain_knowledge_handoff", user_input=user_input[:160])
            return {
                "status": "handoff_to_langgraph",
                "content": _FAST_BRAIN_KNOWLEDGE_HANDOFF_TEXT,
                "messages": messages,
                "tool_executions": [],
                "state_patch": {},
                "handoff_to_slow_brain": True,
                "route": "slow_brain",
            }
        response = await self.llm_with_tools.ainvoke(messages)
        messages.append(response)
        tool_executions: List[Dict[str, Any]] = []

        tool_round = 0
        while getattr(response, "tool_calls", None) and tool_round < _MAX_TOOL_ROUNDS:
            tool_round += 1
            tool_messages, executed_tools, handoff_message = await self._execute_tool_calls(response)
            tool_executions.extend(executed_tools)
            if handoff_message:
                return {
                    "status": "handoff_to_langgraph",
                    "content": handoff_message,
                    "messages": messages,
                    "tool_executions": tool_executions,
                    "state_patch": self._build_state_patch(tool_executions),
                    "handoff_to_slow_brain": True,
                    "route": "slow_brain",
                }
            if not tool_messages:
                break
            messages.extend(tool_messages)
            response = await self.llm_with_tools.ainvoke(messages)
            messages.append(response)

        content = flatten_message_content(getattr(response, "content", "")).strip()
        handoff_to_slow_brain = _HANDOFF_TOKEN in content
        if handoff_to_slow_brain:
            content = content.replace(_HANDOFF_TOKEN, "").strip()
        status = "handoff_to_langgraph" if handoff_to_slow_brain else "chat_continue"

        return {
            "status": status,
            "content": content,
            "messages": messages,
            "tool_executions": tool_executions,
            "state_patch": self._build_state_patch(tool_executions),
            "handoff_to_slow_brain": handoff_to_slow_brain,
            "route": "slow_brain" if handoff_to_slow_brain else "fast_brain",
        }

    def _build_messages(self, *, user_input: str, history: List[Any]) -> List[BaseMessage]:
        system_prompt = render_template(
            "fast_brain_system.j2",
            {"handoff_token": _HANDOFF_TOKEN},
        )
        messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]
        messages.extend(sanitize_message_history(history, include_system=False)[-_MAX_HISTORY_MESSAGES:])

        text = user_input.strip()
        if text:
            last_message = messages[-1] if len(messages) > 1 else None
            if not (
                isinstance(last_message, HumanMessage)
                and flatten_message_content(getattr(last_message, "content", "")).strip() == text
            ):
                messages.append(HumanMessage(content=text))
        return messages

    async def _execute_tool_calls(
        self,
        response: AIMessage,
    ) -> Tuple[List[ToolMessage], List[Dict[str, Any]], Optional[str]]:
        tool_messages: List[ToolMessage] = []
        tool_executions: List[Dict[str, Any]] = []
        for tool_call in list(getattr(response, "tool_calls", []) or []):
            name = str(tool_call.get("name") or "").strip()
            tool = self._tool_by_name.get(name)
            if tool is None:
                logger.warning("fast_brain_unknown_tool", tool_name=name, tool_call=tool_call)
                continue

            args = self._coerce_tool_args(tool_call.get("args"))
            try:
                result = await tool.ainvoke(args)
                logger.info("fast_brain_tool_executed", tool_name=name, args=args)
            except Exception as exc:
                logger.exception("fast_brain_tool_execution_failed", tool_name=name, args=args)
                parsed_result = {"status": "error", "message": str(exc)}
                tool_executions.append(
                    {
                        "tool_name": name,
                        "args": args,
                        "result": parsed_result,
                    }
                )
                if name == "live_physics_tool":
                    return [], tool_executions, _FAST_BRAIN_TOOL_FAILURE_HANDOFF_TEXT
                result = json.dumps(parsed_result, ensure_ascii=False)

            parsed_result = self._coerce_tool_result(result)
            tool_executions.append(
                {
                    "tool_name": name,
                    "args": args,
                    "result": parsed_result,
                }
            )

            tool_messages.append(
                ToolMessage(
                    content=result,
                    tool_call_id=str(tool_call.get("id") or ""),
                    name=name,
                )
            )
        return tool_messages, tool_executions, None

    @staticmethod
    def _coerce_tool_args(raw_args: Any) -> Dict[str, Any]:
        if isinstance(raw_args, dict):
            return dict(raw_args)
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
            except json.JSONDecodeError:
                logger.warning("fast_brain_tool_args_invalid_json", raw_args=raw_args)
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _coerce_tool_result(raw_result: Any) -> Dict[str, Any]:
        if isinstance(raw_result, dict):
            return dict(raw_result)
        if isinstance(raw_result, str):
            try:
                parsed = json.loads(raw_result)
            except json.JSONDecodeError:
                logger.warning("fast_brain_tool_result_invalid_json", raw_result=raw_result)
                return {"raw_result": raw_result}
            if isinstance(parsed, dict):
                return parsed
        return {"raw_result": raw_result}

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        return _coerce_float(value)

    @classmethod
    def _build_state_patch(cls, tool_executions: List[Dict[str, Any]]) -> Dict[str, Any]:
        parameters: Dict[str, Any] = {}
        live_calc_tile: Dict[str, Any] | None = None
        calc_results: Dict[str, Any] | None = None

        for execution in tool_executions:
            if str(execution.get("tool_name") or "").strip() != "live_physics_tool":
                continue

            args = execution.get("args") if isinstance(execution.get("args"), dict) else {}
            result = execution.get("result") if isinstance(execution.get("result"), dict) else {}
            if str(result.get("status") or "").strip().lower() == "error":
                continue

            shaft_diameter = cls._coerce_float(args.get("shaft_diameter_mm"))
            speed_rpm = cls._coerce_float(args.get("speed_rpm"))
            pressure_bar = cls._coerce_float(args.get("pressure_bar"))
            temperature_c = cls._coerce_float(args.get("temperature_c"))
            if shaft_diameter is not None:
                parameters["shaft_diameter"] = shaft_diameter
            if speed_rpm is not None:
                parameters["speed_rpm"] = speed_rpm
            if pressure_bar is not None:
                parameters["pressure_bar"] = pressure_bar
            if temperature_c is not None:
                parameters["temperature_c"] = temperature_c

            v_surface_m_s = cls._coerce_float(result.get("v_m_s"))
            pv_value_mpa_m_s = cls._coerce_float(result.get("pv"))
            if v_surface_m_s is None and pv_value_mpa_m_s is None:
                continue

            live_calc_parameters = {
                key: value
                for key, value in {
                    "shaft_diameter": shaft_diameter,
                    "speed_rpm": speed_rpm,
                    "pressure_bar": pressure_bar,
                    "temperature_c": temperature_c,
                }.items()
                if value is not None
            }
            live_calc_tile = {
                "status": "ok" if str(result.get("status") or "").lower() == "success" else "warning",
                "v_surface_m_s": v_surface_m_s,
                "pv_value_mpa_m_s": pv_value_mpa_m_s,
                "parameters": live_calc_parameters,
            }
            calc_results = {
                key: value
                for key, value in {
                    "v_surface_m_s": v_surface_m_s,
                    "pv_value_mpa_m_s": pv_value_mpa_m_s,
                }.items()
                if value is not None
            }

        working_profile_patch: Dict[str, Any] = {}
        if live_calc_tile:
            working_profile_patch["live_calc_tile"] = live_calc_tile
        if calc_results:
            working_profile_patch["calc_results"] = calc_results

        patch: Dict[str, Any] = {}
        if parameters:
            patch["parameters"] = parameters
        if working_profile_patch:
            patch["working_profile"] = working_profile_patch
        return patch


__all__ = [
    "CalculatePhysicsArgs",
    "FastBrainRouter",
    "live_physics_tool",
    "_should_force_knowledge_handoff",
]
