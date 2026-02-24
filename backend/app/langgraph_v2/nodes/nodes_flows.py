# backend/app/langgraph_v2/nodes/nodes_flows.py
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.utils.state_debug import log_state_debug
from app.langgraph_v2.state import CalcResults, SealAIState, Source, WorkingMemory
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm, run_llm_async
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.output_sanitizer import strip_meta_preamble
from app.langgraph_v2.utils.rag import apply_rag_quality_gate, unpack_rag_payload
from app.langgraph_v2.utils.rag_safety import wrap_rag_context
from app.langgraph_v2.utils.rag_tool import search_knowledge_base
from app.langgraph_v2.nodes.nodes_frontdoor import (
    detect_material_or_trade_query,
    extract_trade_name_candidate,
)
from app.mcp.knowledge_tool import get_available_filters, search_technical_docs

_MATERIAL_DOC_MARKERS = (
    "datenblatt",
    "datasheet",
    "data sheet",
    "technical sheet",
    "werkstoff",
    "material",
    "nbr",
    "fkm",
    "epdm",
    "hnbr",
    "ptfe",
    "vmq",
    "ffkm",
    "kyrolon",
    "search_technical_docs",
    "get_available_filters",
    "qdrant",
    "knowledge-base",
    "knowledge base",
    "trade_name",
)
_MATERIAL_CODE_PATTERN = re.compile(r"\b([a-z]{2,6}[-_/]?\d{2,4})\b", re.IGNORECASE)
_TRADE_NAME_PATTERN = re.compile(r"trade_name\s*[:=]?\s*['\"]([^'\"]{2,120})['\"]", re.IGNORECASE)
_SIMPLE_QUOTED_PATTERN = re.compile(r"['\"]([^'\"]{2,120})['\"]")
_GLOBAL_SHARED_TENANT = "sealai"


def _update_working_memory(state: SealAIState, updates: Dict[str, Any]) -> WorkingMemory:
    wm = state.working_memory or WorkingMemory()
    return wm.model_copy(update=updates)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _merge_flags(state: SealAIState, updates: Dict[str, Any]) -> Dict[str, Any]:
    flags = dict(state.flags or {})
    flags.update(updates)
    return flags


def _extend_dict(base: Dict[str, Any] | None, extras: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    merged.update(extras)
    return merged


def discovery_schema_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("discovery_schema_node", state)
    user_text = latest_user_text(state.get("messages")) or ""
    required = [
        "medium",
        "pressure_bar",
        "temperature_C",
        "shaft_diameter",
        "speed_rpm",
    ]
    missing = [key for key in required if not getattr(state.parameters, key, None)]
    schema_notes = {
        "missing": missing,
        "required": required,
        "user_input": user_text,
        "prompt": "Bitte teile Brenn- und Bewegungsdaten oder Geometrien mit.",
    }
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"schema": schema_notes})
    wm = _update_working_memory(state, {"design_notes": design_notes})
    flags = _merge_flags(state, {"parameters_complete_for_material": not bool(missing)})
    return {
        "missing_params": missing,
        "working_memory": wm,
        "flags": flags,
        # Phase: Parameter-Vorbereitung
        "phase": PHASE.PREFLIGHT_PARAMETERS,
        "last_node": "discovery_schema_node",
    }


def parameter_check_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("parameter_check_node", state)
    missing = state.missing_params or []
    complete = not bool(missing)
    flags = _merge_flags(state, {"parameters_complete_for_profile": complete})
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"parameter_check": {"missing": missing}})
    wm = _update_working_memory(state, {"design_notes": design_notes})
    return {
        "flags": flags,
        "working_memory": wm,
        "analysis_complete": True,
        # Noch immer Parameter-Phase
        "phase": PHASE.PREFLIGHT_PARAMETERS,
        "last_node": "parameter_check_node",
    }


def calculator_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("calculator_node", state)
    params = state.parameters
    diameter_mm = _safe_float(params.shaft_diameter) or _safe_float(params.inner_diameter_mm)
    rpm = _safe_float(params.speed_rpm)
    temp_c = _safe_float(params.temperature_C)
    pressure = _safe_float(params.pressure_bar)

    missing: List[str] = []
    if diameter_mm is None:
        missing.append("shaft_diameter")
    if rpm is None:
        missing.append("speed_rpm")
    if temp_c is None:
        missing.append("temperature_C")
    if pressure is None:
        missing.append("pressure_bar")

    calculations: Dict[str, Any] = {}
    if missing:
        calc = CalcResults(
            safety_factor=None,
            temperature_margin=None,
            pressure_margin=None,
            notes=[f"Keine Berechnung: fehlende Kernwerte ({', '.join(missing)})."],
        )
    else:
        circumference_mm = math.pi * float(diameter_mm)
        surface_speed_m_per_min = circumference_mm * float(rpm) / 1000.0
        notes = [f"Berechnete Umfangsgeschwindigkeit: {surface_speed_m_per_min:.1f} m/min"]
        safety_factor = 1.5 if float(pressure) <= 150 else 1.3
        calc = CalcResults(
            safety_factor=safety_factor,
            temperature_margin=max(0.0, 220 - float(temp_c)),
            pressure_margin=max(0.0, 200 - float(pressure)),
            notes=notes,
        )
        calculations = {"surface_speed_m_per_min": surface_speed_m_per_min}
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"calculations": calculations})
    wm = _update_working_memory(state, {"design_notes": design_notes})
    return {
        "calc_results": calc,
        "calc_results_ok": True,
        "working_memory": wm,
        # Phase: Berechnung
        "phase": PHASE.CALCULATION,
        "last_node": "calculator_node",
    }


def material_agent_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("material_agent_node", state)
    user_text = latest_user_text(state.get("messages")) or ""
    material_code = _extract_material_code(user_text)
    if _looks_like_material_doc_query(user_text):
        trade_name = _extract_trade_name(user_text)
        allowed_tenants = _build_allowed_tenants(state.user_id)
        metadata_filters: Dict[str, Any] = {}
        available_filter_keys: List[str] = []
        if trade_name:
            # Prefer tenant-scoped discovery first; fall back to global discovery for visibility gaps.
            for tenant_scope in allowed_tenants:
                scoped_filters = get_available_filters(tenant_id=tenant_scope, max_points=4000)
                available_filter_keys = list(scoped_filters.get("filters") or [])
                if available_filter_keys:
                    break
            if not available_filter_keys:
                global_filters = get_available_filters(tenant_id=None, max_points=4000)
                available_filter_keys = list(global_filters.get("filters") or [])
            trade_name_key = _resolve_trade_name_filter_key(available_filter_keys)
            if trade_name_key:
                metadata_filters[trade_name_key] = trade_name
        query = user_text
        print(f"DEBUG RAG: Searching Qdrant for '{query}' with allowed tenants: {allowed_tenants}")
        payload: Dict[str, Any] = {}
        rag_search_exception: Exception | None = None
        for tenant_scope in allowed_tenants:
            try:
                payload = search_technical_docs(
                    query=query,
                    material_code=material_code,
                    tenant_id=tenant_scope,
                    k=4,
                    metadata_filters=metadata_filters or None,
                )
            except Exception as exc:
                rag_search_exception = exc
                print(f"!!! RAG SEARCH FAILED OR RETURNED 0 HITS FOR: {query} !!!")
                print(f"!!! RAG EXCEPTION: {type(exc).__name__}: {exc} !!!")
                payload = {
                    "hits": [],
                    "context": "",
                    "retrieval_meta": {
                        "error": f"{type(exc).__name__}: {exc}",
                        "tenant_id": tenant_scope,
                    },
                }
                continue
            hits = payload.get("hits") or []
            if hits:
                break
        hits = payload.get("hits") or []
        if not hits:
            print(f"!!! RAG SEARCH FAILED OR RETURNED 0 HITS FOR: {query} !!!")
            if rag_search_exception is not None:
                print(
                    "!!! LAST RAG ERROR: "
                    f"{type(rag_search_exception).__name__}: {rag_search_exception} !!!"
                )
        retrieval_meta = dict(payload.get("retrieval_meta") or {})
        retrieval_meta["allowed_tenants"] = allowed_tenants
        payload["retrieval_meta"] = retrieval_meta
        retrieved_context = _build_material_retrieved_context(payload, hits)
        panel_material = {
            "query": user_text,
            "material_code": material_code,
            "trade_name": trade_name,
            "metadata_filters": metadata_filters,
            "available_filter_keys": available_filter_keys,
            "technical_docs": hits,
            "rag_context": retrieved_context,
        }
        candidate_name = material_code or (hits[0].get("document_id") if hits else None) or "Technical datasheet"
        candidates = [
            {
                "name": candidate_name,
                "rationale": "Kontext aus Qdrant-Retrieval (technische Dokumente).",
            }
        ]
        state_material: Dict[str, Any] = {
            "material": candidate_name,
            "confidence": "retrieved",
            "details": "Kontext aus technischer Dokumentensuche.",
            "material_code": material_code,
        }
        existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
        design_notes = _extend_dict(
            existing_design,
            {
                "material_selection": f"Technische Dokumentensuche fuer {candidate_name}",
                "material_docs_context": retrieved_context,
            },
        )
        wm = _update_working_memory(
            state,
            {
                "material_candidates": candidates,
                "panel_material": panel_material,
                "design_notes": design_notes,
            },
        )
        sources = list(state.sources or [])
        seen_sources = {src.source for src in sources if getattr(src, "source", None)}
        for hit in hits:
            source_label = hit.get("source") or hit.get("filename") or hit.get("document_id")
            if not source_label or source_label in seen_sources:
                continue
            sources.append(
                Source(
                    snippet=hit.get("snippet"),
                    source=source_label,
                    metadata={
                        "page": hit.get("page"),
                        "score": hit.get("score"),
                        "document_id": hit.get("document_id"),
                        "panel": "material_agent",
                    },
                )
            )
            seen_sources.add(source_label)
        return {
            "material_choice": state_material,
            "working_memory": wm,
            "sources": sources,
            "retrieval_meta": payload.get("retrieval_meta"),
            "context": retrieved_context,
            "phase": PHASE.RAG,
            "last_node": "material_agent_node",
        }

    temp = _safe_float(state.parameters.temperature_C)
    medium_raw = (state.parameters.medium or "").strip()
    medium = medium_raw.lower()
    candidates: List[Dict[str, Any]] = []
    needs_input: List[str] = []
    if not medium_raw:
        needs_input.append("medium")
    if temp is None:
        needs_input.append("temperature_C")

    if not needs_input:
        if temp >= 180 or "hot" in medium:
            candidates.append({"name": "FKM", "rationale": "Hohe Temperatur-/Medienbeständigkeit (heuristisch, bitte validieren)."})
            candidates.append({"name": "PTFE", "rationale": "Hohe chemische Beständigkeit (heuristisch, bitte validieren)."})
        else:
            candidates.append({"name": "NBR", "rationale": "Robuster Standardwerkstoff (heuristisch, bitte validieren)."})
            candidates.append({"name": "FKM", "rationale": "Gute chemische Beständigkeit (heuristisch, bitte validieren)."})
    summary = f"Materialkandidaten: {', '.join(c['name'] for c in candidates)}"
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"material_selection": summary})
    wm = _update_working_memory(state, {"material_candidates": candidates, "design_notes": design_notes})
    state_material: Dict[str, Any] = {"confidence": "heuristic"}
    if candidates:
        state_material.update({"material": candidates[0]["name"], "details": candidates[0]["rationale"]})
    if needs_input:
        state_material["needs_input"] = needs_input
    return {
        "material_choice": state_material,
        "working_memory": wm,
        # Phase: technischer Consulting-Schritt
        "phase": PHASE.CONSULTING,
        "last_node": "material_agent_node",
    }


def _looks_like_material_doc_query(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    if detect_material_or_trade_query(text):
        return True
    if any(marker in normalized for marker in _MATERIAL_DOC_MARKERS):
        return True
    return bool(_MATERIAL_CODE_PATTERN.search(normalized))


def _extract_material_code(text: str) -> str | None:
    match = _MATERIAL_CODE_PATTERN.search(text or "")
    if not match:
        return None
    return match.group(1).upper()


def _extract_trade_name(text: str) -> str | None:
    source = text or ""
    direct = _TRADE_NAME_PATTERN.search(source)
    if direct:
        candidate = direct.group(1).strip()
        return candidate or None
    if "trade_name" in source.lower():
        quoted = _SIMPLE_QUOTED_PATTERN.search(source)
        if quoted:
            candidate = quoted.group(1).strip()
            return candidate or None
    candidate = extract_trade_name_candidate(source)
    if candidate and not _MATERIAL_CODE_PATTERN.fullmatch(candidate):
        return candidate
    return None


def _resolve_trade_name_filter_key(filters: List[str]) -> str | None:
    if not filters:
        return None
    for key in (
        "additional_metadata.trade_name",
        "metadata.additional_metadata.trade_name",
        "trade_name",
        "metadata.trade_name",
    ):
        if key in filters:
            return key
    return None


def _build_allowed_tenants(primary_tenant: str | None) -> List[str]:
    allowed: List[str] = []
    for candidate in [primary_tenant, _GLOBAL_SHARED_TENANT]:
        tenant = str(candidate or "").strip()
        if not tenant or tenant in allowed:
            continue
        allowed.append(tenant)
    return allowed or [_GLOBAL_SHARED_TENANT]


def _build_material_retrieved_context(payload: Dict[str, Any], hits: List[Dict[str, Any]]) -> str:
    context = str(payload.get("context") or "").strip()
    snippets: List[str] = []
    table_blocks: List[str] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        snippet = str(hit.get("snippet") or "").strip()
        if snippet:
            snippets.append(snippet)
        table_markdown = _extract_hit_tables(hit)
        if table_markdown:
            table_blocks.append(table_markdown)
    parts: List[str] = []
    if context:
        parts.append(context)
    if snippets:
        parts.append("\n\n".join(snippets[:4]).strip())
    if table_blocks:
        parts.append("\n\n".join(table_blocks[:3]).strip())
    merged_parts: List[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = str(part or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged_parts.append(normalized)
    return "\n\n".join(merged_parts).strip()


def _extract_hit_tables(hit: Dict[str, Any]) -> str:
    metadata = hit.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    candidates: List[Any] = [metadata]
    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        candidates.append(nested)
    additional = metadata.get("additional_metadata")
    if isinstance(additional, dict):
        candidates.append(additional)
    if isinstance(nested, dict):
        nested_additional = nested.get("additional_metadata")
        if isinstance(nested_additional, dict):
            candidates.append(nested_additional)

    blocks: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("table", "tables", "table_data", "tabular_data"):
            raw = candidate.get(key)
            if isinstance(raw, dict):
                rendered = _render_markdown_table(raw)
                if rendered:
                    blocks.append(rendered)
            elif isinstance(raw, list):
                for table in raw:
                    if not isinstance(table, dict):
                        continue
                    rendered = _render_markdown_table(table)
                    if rendered:
                        blocks.append(rendered)
    if not blocks:
        return ""
    return "\n\n".join(blocks)


def _render_markdown_table(table: Dict[str, Any], max_rows: int = 8, max_cols: int = 6) -> str:
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list) or not columns or not rows:
        return ""
    col_names = [str(col).strip() for col in columns if str(col).strip()][:max_cols]
    if not col_names:
        return ""

    rendered_rows: List[List[str]] = []
    for row in rows[:max_rows]:
        values: List[str] = []
        if isinstance(row, dict):
            for col in col_names:
                values.append(str(row.get(col, "")).strip())
        elif isinstance(row, list):
            for idx in range(len(col_names)):
                values.append(str(row[idx]).strip() if idx < len(row) else "")
        else:
            continue
        rendered_rows.append(values)
    if not rendered_rows:
        return ""
    header = "| " + " | ".join(col_names) + " |"
    divider = "| " + " | ".join(["---"] * len(col_names)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rendered_rows]
    return "Table:\n" + "\n".join([header, divider, *body])


def profile_agent_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("profile_agent_node", state)
    profile = {
        "profile": "Radial-Doppellippendichtung",
        "lip_count": 2,
        "construction": "Gummieinlage mit Metallträger",
        "rationale": "Heuristischer Kandidat; finale Auswahl hängt von Einbauraum, Druck-/Δp und Gegenlauffläche ab.",
        "confidence": "heuristic",
    }
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"profile": profile})
    wm = _update_working_memory(state, {"design_notes": design_notes})
    return {
        "profile_choice": profile,
        "working_memory": wm,
        # Phase: weiterhin Consulting
        "phase": PHASE.CONSULTING,
        "last_node": "profile_agent_node",
    }


def validation_agent_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("validation_agent_node", state)
    issues: List[str] = []
    if not state.flags.get("parameters_complete_for_profile"):
        issues.append("Einige Profilparameter fehlen noch.")
    status = "warning" if issues else "ok"
    validation = {"status": status, "issues": issues}
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"validation": validation})
    wm = _update_working_memory(state, {"design_notes": design_notes})
    return {
        "validation": validation,
        "working_memory": wm,
        # Phase: Validierung
        "phase": PHASE.VALIDATION,
        "last_node": "validation_agent_node",
    }


def critical_review_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("critical_review_node", state)
    validation = state.validation or {}
    issues = validation.get("issues") or []
    critical = dict(state.critical or {})
    iteration = int(critical.get("iteration_count") or 0)
    iteration += 1
    target = "final"
    next_step = "final_answer_node"
    if issues:
        critical_status = "needs_refinement" if iteration <= 2 else "warning"
        target = "discovery"
        next_step = "discovery_schema_node"
    else:
        critical_status = "ok"
    critical.update(
        {
            "status": critical_status,
            "target": target,
            "next_step": next_step,
            "iteration_count": iteration,
        }
    )
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"critical_review": critical})
    wm = _update_working_memory(state, {"design_notes": design_notes})
    return {
        "critical": critical,
        "working_memory": wm,
        # Phase: ich ordne Critical Review unter Validierung ein
        "phase": PHASE.VALIDATION,
        "last_node": "critical_review_node",
    }


def product_match_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("product_match_node", state)
    want_products = bool(state.plan.get("want_product_recommendation"))
    catalog_connected = bool(str(os.getenv("PRODUCT_CATALOG_URL", "")).strip())
    matches: List[Dict[str, Any]] = []
    products = {
        "requested": want_products,
        "catalog_connected": catalog_connected,
        "manufacturer": matches[0]["manufacturer"] if matches else None,
        "matches": matches,
        "match_quality": "high" if matches else None,
    }
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"product_match": matches})
    wm = _update_working_memory(state, {"design_notes": design_notes})
    return {
        "products": products,
        "working_memory": wm,
        # Phase: Consulting (Produkt-Mapping)
        "phase": PHASE.CONSULTING,
        "last_node": "product_match_node",
    }


def product_explainer_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("product_explainer_node", state)
    products = state.products or {}
    matches = products.get("matches") or []
    explanation = (
        "Produktbegründung: Die erste Empfehlung deckt Geometrie und Temperaturniveau ab."
        if matches
        else "Keine spezielle Produktempfehlung gewünscht."
    )
    existing_design = getattr(state.working_memory, "design_notes", None) if state.working_memory else {}
    design_notes = _extend_dict(existing_design, {"product_explainer": explanation})
    wm = _update_working_memory(state, {"design_notes": design_notes})
    return {
        "working_memory": wm,
        # Phase: immer noch Consulting
        "phase": PHASE.CONSULTING,
        "last_node": "product_explainer_node",
    }


async def material_comparison_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("material_comparison_node", state)
    user_text = latest_user_text(state.get("messages")) or ""

    full_text = render_template("material_comparison.j2", {"user_text": user_text})
    parts = full_text.split("---", 1)
    if len(parts) == 2:
        system = parts[0].strip()
        prompt = parts[1].strip()
    else:
        system = "Du bist ein technischer Materialvergleichs-Experte."
        prompt = full_text.strip()

    response = await run_llm_async(
        model=get_model_tier("mini"),
        prompt=prompt,
        system=system,
        temperature=0,
        max_tokens=320,
        metadata={"node": "material_comparison_node"},
    )
    existing_notes = getattr(state.working_memory, "comparison_notes", None) if state.working_memory else {}
    notes = _extend_dict(existing_notes, {"comparison_text": response.strip()})
    wm = _update_working_memory(state, {"comparison_notes": notes})
    force_rag = str(os.getenv("RAG_FORCE_COMPARISON", "")).strip().lower() in {"1", "true", "yes", "on"}
    return {
        "working_memory": wm,
        # Phase: Wissens-/Vergleichs-Flow
        "phase": PHASE.KNOWLEDGE,
        "last_node": "material_comparison_node",
        "requires_rag": bool(getattr(state, "requires_rag", False) or force_rag),
    }


def rag_support_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("rag_support_node", state)
    user_text = latest_user_text(state.get("messages")) or ""
    from app.langgraph_v2.nodes.nodes_frontdoor import detect_sources_request

    if not bool(getattr(state, "requires_rag", False)) and not detect_sources_request(user_text):
        return {
            "phase": PHASE.KNOWLEDGE,
            "last_node": "rag_support_node",
        }

    intent_goal = getattr(state.intent, "goal", "design_recommendation") if state.intent else "design_recommendation"
    notes = dict(state.working_memory.comparison_notes if state.working_memory else {})
    rag_context = search_knowledge_base.invoke({
        "query": user_text or "Aktuelle technische Frage",
        "category": "norms",
        "k": 3,
        "tenant": state.user_id,
    })
    rag_text, retrieval_meta = unpack_rag_payload(rag_context)
    min_score = float(os.getenv("MIN_TOP_SCORE", "0.20"))
    rag_text, retrieval_meta = apply_rag_quality_gate(rag_text, retrieval_meta, min_top_score=min_score)
    rag_text = wrap_rag_context(rag_text)
    notes["rag_context"] = rag_text or ""

    # Only emit references if the tool output contains citation-like artifacts.
    rag_reference: list[str] = []
    for line in rag_text.splitlines():
        line = line.strip()
        if line.lower().startswith("quelle:"):
            src = line.split(":", 1)[1].strip()
            if src:
                rag_reference.append(src)

    has_error = rag_text.lower().startswith("fehler beim abrufen") or "rag retrieval failed" in rag_text.lower()
    has_no_hits = "keine relevanten informationen" in rag_text.lower()

    if has_error or has_no_hits or not rag_reference:
        notes["rag_reference"] = None
        if has_error or has_no_hits:
            notes["rag_note"] = "Quellen derzeit nicht verfügbar."
    else:
        # Keep it compact; de-duplicate while preserving order.
        deduped: list[str] = []
        seen: set[str] = set()
        for src in rag_reference:
            if src in seen:
                continue
            seen.add(src)
            deduped.append(src)
        notes["rag_reference"] = deduped

    sources = list(state.sources or [])
    seen_sources = {src.source for src in sources if getattr(src, "source", None)}
    if notes.get("rag_reference"):
        for src in notes.get("rag_reference") or []:
            if src in seen_sources:
                continue
            sources.append(Source(snippet=None, source=src, metadata={"panel": "rag_support"}))
            seen_sources.add(src)

    if intent_goal == "explanation_or_comparison":
        wm = _update_working_memory(state, {"comparison_notes": notes})
    else:
        wm = _update_working_memory(state, {"comparison_notes": notes, "panel_norms_rag": notes})

    return {
        "working_memory": wm,
        "sources": sources,
        "retrieval_meta": retrieval_meta,
        # Phase: explizit RAG
        "phase": PHASE.RAG,
        "last_node": "rag_support_node",
    }


async def leakage_troubleshooting_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("leakage_troubleshooting_node", state)
    user_text = latest_user_text(state.get("messages")) or ""

    full_text = render_template("leakage_troubleshooting.j2", {"user_text": user_text})
    parts = full_text.split("---", 1)
    if len(parts) == 2:
        system = parts[0].strip()
        prompt = parts[1].strip()
    else:
        system = "Du bist ein Troubleshooting Spezialist."
        prompt = full_text.strip()

    response = await run_llm_async(
        model=get_model_tier("mini"),
        prompt=prompt,
        system=system,
        temperature=0,
        max_tokens=260,
        metadata={"node": "leakage_troubleshooting_node"},
    )
    troubleshooting = {
        "symptoms": [user_text],
        "hypotheses": ["Überdruck", "Montagefehler"],
        "notes": response.strip(),
    }
    existing_notes = getattr(state.working_memory, "troubleshooting_notes", None) if state.working_memory else {}
    merged_notes = _extend_dict(existing_notes, troubleshooting)
    wm = _update_working_memory(state, {"troubleshooting_notes": merged_notes})
    updated = dict(state.troubleshooting or {})
    updated.update(troubleshooting)
    updated["done"] = False
    return {
        "troubleshooting": updated,
        "working_memory": wm,
        # Phase: Consulting-Flow für Troubleshooting
        "phase": PHASE.CONSULTING,
        "last_node": "leakage_troubleshooting_node",
    }


def troubleshooting_pattern_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("troubleshooting_pattern_node", state)
    text = latest_user_text(state.get("messages")) or ""
    patterns = [
        ("undercompression", ["leck", "druck", "unter"]),
        ("overcompression", ["zu stark", "deformiert"]),
        ("material_mismatch", ["medium", "chemisch"]),
    ]
    pattern = "assembly_error"
    for name, markers in patterns:
        if any(marker in text.lower() for marker in markers):
            pattern = name
            break
    updated = dict(state.troubleshooting or {})
    updated["pattern_match"] = pattern
    updated.setdefault("hypotheses", []).append(pattern)
    existing_notes = getattr(state.working_memory, "troubleshooting_notes", None) if state.working_memory else {}
    notes = _extend_dict(existing_notes, {"pattern": pattern})
    wm = _update_working_memory(state, {"troubleshooting_notes": notes})
    return {
        "troubleshooting": updated,
        "working_memory": wm,
        # Phase: weiterhin Troubleshooting-Consulting
        "phase": PHASE.CONSULTING,
        "last_node": "troubleshooting_pattern_node",
    }


async def troubleshooting_explainer_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    log_state_debug("troubleshooting_explainer_node", state)
    pattern = (state.troubleshooting or {}).get("pattern_match") or "assembly_error"
    symptoms = ", ".join(state.troubleshooting.get('symptoms', []))

    full_text = render_template("troubleshooting_explainer.j2", {"pattern": pattern, "symptoms": symptoms})
    parts = full_text.split("---", 1)
    if len(parts) == 2:
        system = parts[0].strip()
        prompt = parts[1].strip()
    else:
        system = "Du gibst eine pragmatische Fehleranalyse."
        prompt = full_text.strip()

    response = await run_llm_async(
        model=get_model_tier("mini"),
        prompt=prompt,
        system=system,
        temperature=0,
        max_tokens=320,
        metadata={"node": "troubleshooting_explainer_node"},
    )
    updated = dict(state.troubleshooting or {})
    updated["explanation_text"] = response.strip()
    updated["done"] = True
    existing_notes = getattr(state.working_memory, "troubleshooting_notes", None) if state.working_memory else {}
    notes = _extend_dict(existing_notes, {"explanation": response.strip()})
    wm = _update_working_memory(state, {"troubleshooting_notes": notes})
    return {
        "troubleshooting": updated,
        "working_memory": wm,
        # Phase: weiterhin Consulting
        "phase": PHASE.CONSULTING,
        "last_node": "troubleshooting_explainer_node",
    }


def build_final_answer_context(state: SealAIState) -> Dict[str, Any]:
    wm = state.working_memory or WorkingMemory()
    intent_goal = getattr(state.intent, "goal", "design_recommendation") if state.intent else "design_recommendation"
    parameters = state.parameters.as_dict()
    calc_results = state.calc_results.model_dump(exclude_none=True) if state.calc_results else {}
    panel_material = getattr(wm, "panel_material", {}) or {}
    design_notes = getattr(wm, "design_notes", {}) or {}
    retrieved_blocks: List[str] = []
    seen_blocks: set[str] = set()

    def _append_context(value: Any) -> None:
        text = str(value or "").strip()
        if not text or text in seen_blocks:
            return
        seen_blocks.add(text)
        retrieved_blocks.append(text)

    if isinstance(panel_material, dict):
        _append_context(panel_material.get("rag_context"))
        _append_context(panel_material.get("reducer_context"))
    if isinstance(design_notes, dict):
        _append_context(design_notes.get("material_docs_context"))
    _append_context(state.get("context"))
    material_retrieved_context = "\n\n".join(retrieved_blocks).strip()

    return {
        "intent_goal": intent_goal,
        "frontdoor_reply": getattr(wm, "frontdoor_reply", None),
        "parameters": parameters,
        "calc_results": calc_results,
        "material_choice": state.material_choice or {},
        "profile_choice": state.profile_choice or {},
        "validation": state.validation or {},
        "critical": state.critical or {},
        "products": state.products or {},
        "comparison_notes": getattr(wm, "comparison_notes", {}),
        "requires_rag": bool(getattr(state, "requires_rag", False)),
        "troubleshooting": state.troubleshooting or {},
        "response_text": getattr(wm, "response_text", None),
        "material_retrieved_context": material_retrieved_context,
        "context": material_retrieved_context,
        "phase": state.phase or "final",
    }


def render_final_answer_draft(context: Dict[str, Any]) -> str:
    text = render_template("final_answer_router.j2", context)
    return (text or "").strip()


def map_final_answer_to_state(
    state: SealAIState,
    final_text: str,
    *,
    final_prompt: str = "",
    final_prompt_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    clean_text = strip_meta_preamble((final_text or "").strip())
    messages: List[BaseMessage] = list(state.messages or [])
    if clean_text:
        messages.append(AIMessage(content=[{"type": "text", "text": clean_text}]))

    patch: Dict[str, Any] = {
        "messages": messages,
        "final_text": clean_text,
        "final_prompt": (final_prompt or "").strip() or None,
        "final_prompt_metadata": dict(final_prompt_metadata or {}),
        "phase": state.phase or "final",
        "last_node": "final_answer_node",
    }
    return patch


def prepare_final_answer_llm_payload(
    state: SealAIState,
    *,
    system_prompt: str,
    rendered_messages: List[BaseMessage],
    user_messages: List[BaseMessage],
    prompt_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    # Platinum Blueprint v4.1: Removed hardcoded ignorance blockers.
    # Accuracy is managed by RAG quality gates and prompt instructions, not static string matches.
    user_query = (latest_user_text(user_messages) or latest_user_text(rendered_messages) or "").strip()
    context_text = str(getattr(state, "context", None) or "").strip()
    forced_text: str | None = None
    prepared_messages: List[BaseMessage] = list(rendered_messages or [])

    # Debug Visibility
    print(f"DEBUG RAG: Routing query '{user_query}' with context length: {len(context_text)}")

    # We keep the messages structure but remove the forced_text manipulation logic
    # that existed here for 'kyrolon' specific masking.
    
    return {
        "messages": prepared_messages,
        "prompt_text": system_prompt,
        "prompt_metadata": dict(prompt_metadata or {}),
        "forced_text": forced_text,
    }


__all__ = [
    "discovery_schema_node",
    "parameter_check_node",
    "calculator_node",
    "material_agent_node",
    "profile_agent_node",
    "validation_agent_node",
    "critical_review_node",
    "product_match_node",
    "product_explainer_node",
    "material_comparison_node",
    "rag_support_node",
    "leakage_troubleshooting_node",
    "troubleshooting_pattern_node",
    "troubleshooting_explainer_node",
    "build_final_answer_context",
    "render_final_answer_draft",
    "map_final_answer_to_state",
    "prepare_final_answer_llm_payload",
]
