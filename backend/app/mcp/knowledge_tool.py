from __future__ import annotations

import json
import logging
import os
import inspect
from datetime import date, datetime, timezone
from functools import lru_cache, wraps
from typing import Any, Callable, Dict, List, Optional, Sequence

from langchain_core.tools import BaseTool, StructuredTool
from qdrant_client import QdrantClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.langgraph_v2.state.audit import (
    ToolCallRecord,
    append_tool_call_to_state,
    build_tool_call_record,
    emit_tool_call_record,
)
from app.services.rag.rag_orchestrator import hybrid_retrieve

logger = logging.getLogger(__name__)

MCP_KNOWLEDGE_READ_SCOPES = frozenset({"mcp:pim:read", "mcp:knowledge:read"})
MCP_ERP_READ_SCOPES = frozenset({"mcp:erp:read"})
MCP_SALES_ADMIN_SCOPES = frozenset({"mcp:sales:admin"})
SEARCH_TECHNICAL_DOCS_TOOL_NAME = "search_technical_docs"
GET_AVAILABLE_FILTERS_TOOL_NAME = "get_available_filters"
QUERY_DETERMINISTIC_NORMS_TOOL_NAME = "query_deterministic_norms"
PRICING_TOOL_NAME = "pricing_tool"
STOCK_CHECK_TOOL_NAME = "stock_check_tool"
APPROVE_DISCOUNT_TOOL_NAME = "approve_discount"
INITIAL_QDRANT_TIMEOUT_S = 10.0
GLOBAL_TECH_COLLECTIONS_ENV = "QDRANT_GLOBAL_TECH_COLLECTIONS"
DEFAULT_GLOBAL_TECH_COLLECTIONS = ("sealai-docs",)
GLOBAL_SHARED_TENANT = "sealai"
RAG_MIN_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.05"))

# MCP transport policy:
# Prefer Streamable HTTP (JSON-RPC 2.0 over HTTP) for production interoperability.
# Fallback to SSE transport only when streamable HTTP is unavailable.
MCP_TRANSPORT_PREFERENCE: Dict[str, str] = {"primary": "streamable_http", "fallback": "sse"}

SEARCH_TECHNICAL_DOCS_SPEC: Dict[str, Any] = {
    "name": SEARCH_TECHNICAL_DOCS_TOOL_NAME,
    "description": (
        "Search technical PDFs and datasheets in Qdrant using vector retrieval. "
        "Best for material codes like NBR-90, FKM-75 or standards-related datasheet lookups."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Technical question or datasheet lookup query."},
            "material_code": {
                "type": "string",
                "description": "Optional material code filter (e.g. NBR-90, FKM-75).",
            },
            "metadata_filters": {
                "type": "object",
                "description": (
                    "Optional metadata filter map discovered via get_available_filters "
                    "(e.g. {'additional_metadata.trade_name': 'Kyrolon 79X'})."
                ),
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["query"],
    },
}

GET_AVAILABLE_FILTERS_SPEC: Dict[str, Any] = {
    "name": GET_AVAILABLE_FILTERS_TOOL_NAME,
    "description": (
        "Discover available metadata filters by scanning unique keys from Qdrant payload metadata "
        "(including dynamic additional_metadata fields)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "tenant_id": {
                "type": "string",
                "description": "Optional tenant scope (defaults to caller tenant).",
            },
            "max_points": {
                "type": "integer",
                "description": "Max points to scan for discovery (default 2000, max 20000).",
            },
        },
        "required": [],
    },
}

QUERY_DETERMINISTIC_NORMS_SPEC: Dict[str, Any] = {
    "name": QUERY_DETERMINISTIC_NORMS_TOOL_NAME,
    "description": (
        "Deterministically query versioned DIN/material numeric limits from PostgreSQL "
        "using exact/range SQL filters (no vector retrieval)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "material": {"type": "string", "description": "Material identifier (e.g. FKM, NBR, PTFE)."},
            "temp": {"type": "number", "description": "Operating temperature in °C."},
            "pressure": {"type": "number", "description": "Operating pressure in bar."},
            "tenant_id": {"type": "string", "description": "Optional tenant scope."},
        },
        "required": ["material", "temp", "pressure"],
    },
}

PRICING_TOOL_SPEC: Dict[str, Any] = {
    "name": PRICING_TOOL_NAME,
    "description": "Read-only pricing lookup for SKUs and quantities.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "sku": {"type": "string"},
            "quantity": {"type": "integer"},
            "currency": {"type": "string"},
        },
        "required": ["sku"],
    },
}

STOCK_CHECK_TOOL_SPEC: Dict[str, Any] = {
    "name": STOCK_CHECK_TOOL_NAME,
    "description": "Read-only stock availability lookup for a SKU.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "sku": {"type": "string"},
            "warehouse": {"type": "string"},
        },
        "required": ["sku"],
    },
}

APPROVE_DISCOUNT_TOOL_SPEC: Dict[str, Any] = {
    "name": APPROVE_DISCOUNT_TOOL_NAME,
    "description": "Administrative discount approval action (requires sales admin scope).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "quote_id": {"type": "string"},
            "discount_percent": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["quote_id", "discount_percent"],
    },
}


def _normalize_scopes(scopes: Optional[Sequence[str] | str]) -> set[str]:
    normalized: set[str] = set()
    if scopes is None:
        return normalized
    if isinstance(scopes, str):
        candidates = scopes.replace(",", " ").split()
    else:
        candidates = [str(item).strip() for item in scopes if item is not None]
    for scope in candidates:
        if scope:
            normalized.add(scope)
    return normalized


def _active_collection_name() -> str:
    try:
        configured = settings.QDRANT_COLLECTION_NAME
    except AttributeError:
        configured = None
    if configured:
        return str(configured).strip()
    legacy = getattr(settings, "qdrant_collection", None)
    if legacy:
        return str(legacy).strip()
    return ""


def _global_technical_collections() -> set[str]:
    raw = os.getenv(GLOBAL_TECH_COLLECTIONS_ENV)
    if raw:
        values = [item.strip().lower() for item in raw.split(",") if item.strip()]
        if values:
            return set(values)
    defaults = {item.lower() for item in DEFAULT_GLOBAL_TECH_COLLECTIONS}
    active = _active_collection_name().lower()
    if active:
        defaults.add(active)
    return defaults


def _is_global_technical_collection(collection_name: Optional[str]) -> bool:
    collection = (collection_name or "").strip().lower()
    if not collection:
        return False
    if collection in _global_technical_collections():
        return True
    active = _active_collection_name().strip().lower()
    if active and collection.startswith(active):
        return True
    return "global" in collection and "knowledge" in collection


def has_knowledge_scope(scopes: Optional[Sequence[str] | str]) -> bool:
    return bool(_normalize_scopes(scopes) & MCP_KNOWLEDGE_READ_SCOPES)


def _has_any_scope(scopes: set[str], required: frozenset[str]) -> bool:
    return bool(scopes & required)


def _bound_args_payload(func: Callable[..., Any], args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        signature = inspect.signature(func)
        bound = signature.bind_partial(*args, **kwargs)
        return {key: value for key, value in bound.arguments.items()}
    except Exception:
        return dict(kwargs or {})


def _append_tool_call_record(
    *,
    record: ToolCallRecord,
    state: Any = None,
    audit_trail: Optional[List[Dict[str, Any] | ToolCallRecord]] = None,
) -> None:
    emit_tool_call_record(record)
    append_tool_call_to_state(state, record)
    if isinstance(audit_trail, list):
        audit_trail.append(record.model_dump(mode="python"))


def _invoke_tool_with_audit(
    *,
    tool_name: str,
    tool_fn: Callable[..., Any],
    args: tuple[Any, ...] = (),
    kwargs: Optional[Dict[str, Any]] = None,
    state: Any = None,
    audit_trail: Optional[List[Dict[str, Any] | ToolCallRecord]] = None,
    run_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Any:
    call_kwargs = dict(kwargs or {})
    started_at = datetime.now(timezone.utc)
    call_input = _bound_args_payload(tool_fn, args, call_kwargs)
    try:
        output = tool_fn(*args, **call_kwargs)
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        record = build_tool_call_record(
            tool_name=tool_name,
            tool_input=call_input,
            tool_output={},
            started_at=started_at,
            finished_at=finished_at,
            error=exc,
            run_id=run_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            metadata={"user_id": user_id} if user_id else None,
        )
        _append_tool_call_record(record=record, state=state, audit_trail=audit_trail)
        logger.warning(
            "mcp_tool_call_failed",
            extra={
                "tool_name": tool_name,
                "duration_ms": record.duration_ms,
                "run_id": run_id,
                "thread_id": thread_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "error": str(exc),
            },
        )
        raise

    finished_at = datetime.now(timezone.utc)
    record = build_tool_call_record(
        tool_name=tool_name,
        tool_input=call_input,
        tool_output=output,
        started_at=started_at,
        finished_at=finished_at,
        run_id=run_id,
        thread_id=thread_id,
        tenant_id=tenant_id,
        metadata={"user_id": user_id} if user_id else None,
    )
    _append_tool_call_record(record=record, state=state, audit_trail=audit_trail)
    logger.info(
        "mcp_tool_call_audit",
        extra={
            "tool_name": tool_name,
            "duration_ms": record.duration_ms,
            "run_id": run_id,
            "thread_id": thread_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "status": record.status,
        },
    )
    return output


def _audited_tool(tool_name: str, tool_fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(tool_fn)
    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        state = kwargs.pop("__audit_state", None)
        audit_trail = kwargs.pop("__audit_trail", None)
        run_id = kwargs.pop("__audit_run_id", None)
        thread_id = kwargs.pop("__audit_thread_id", None)
        tenant_id = kwargs.pop("__audit_tenant_id", None)
        user_id = kwargs.pop("__audit_user_id", None)
        return _invoke_tool_with_audit(
            tool_name=tool_name,
            tool_fn=tool_fn,
            args=args,
            kwargs=kwargs,
            state=state,
            audit_trail=audit_trail,
            run_id=run_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    return _wrapped


def _pricing_tool(sku: str, quantity: int = 1, currency: str = "EUR") -> Dict[str, Any]:
    return {
        "tool": PRICING_TOOL_NAME,
        "sku": sku,
        "quantity": int(quantity or 1),
        "currency": currency or "EUR",
        "status": "stubbed_mcp_gateway",
    }


def _stock_check_tool(sku: str, warehouse: str | None = None) -> Dict[str, Any]:
    return {
        "tool": STOCK_CHECK_TOOL_NAME,
        "sku": sku,
        "warehouse": warehouse,
        "status": "stubbed_mcp_gateway",
    }


def _approve_discount_tool(quote_id: str, discount_percent: float, reason: str | None = None) -> Dict[str, Any]:
    return {
        "tool": APPROVE_DISCOUNT_TOOL_NAME,
        "quote_id": quote_id,
        "discount_percent": float(discount_percent),
        "reason": reason,
        "status": "stubbed_mcp_gateway",
    }


def _build_tool_registry() -> Dict[str, Dict[str, Any]]:
    search_docs_tool = _audited_tool(SEARCH_TECHNICAL_DOCS_TOOL_NAME, search_technical_docs)
    filters_tool = _audited_tool(GET_AVAILABLE_FILTERS_TOOL_NAME, get_available_filters)
    deterministic_norms_tool = _audited_tool(QUERY_DETERMINISTIC_NORMS_TOOL_NAME, query_deterministic_norms)
    pricing_tool = _audited_tool(PRICING_TOOL_NAME, _pricing_tool)
    stock_tool = _audited_tool(STOCK_CHECK_TOOL_NAME, _stock_check_tool)
    discount_tool = _audited_tool(APPROVE_DISCOUNT_TOOL_NAME, _approve_discount_tool)
    return {
        SEARCH_TECHNICAL_DOCS_TOOL_NAME: {
            "scopes": MCP_KNOWLEDGE_READ_SCOPES,
            "spec": SEARCH_TECHNICAL_DOCS_SPEC,
            "tool": StructuredTool.from_function(
                func=search_docs_tool,
                name=SEARCH_TECHNICAL_DOCS_TOOL_NAME,
                description=SEARCH_TECHNICAL_DOCS_SPEC["description"],
            ),
        },
        GET_AVAILABLE_FILTERS_TOOL_NAME: {
            "scopes": MCP_KNOWLEDGE_READ_SCOPES,
            "spec": GET_AVAILABLE_FILTERS_SPEC,
            "tool": StructuredTool.from_function(
                func=filters_tool,
                name=GET_AVAILABLE_FILTERS_TOOL_NAME,
                description=GET_AVAILABLE_FILTERS_SPEC["description"],
            ),
        },
        QUERY_DETERMINISTIC_NORMS_TOOL_NAME: {
            "scopes": MCP_KNOWLEDGE_READ_SCOPES,
            "spec": QUERY_DETERMINISTIC_NORMS_SPEC,
            "tool": StructuredTool.from_function(
                func=deterministic_norms_tool,
                name=QUERY_DETERMINISTIC_NORMS_TOOL_NAME,
                description=QUERY_DETERMINISTIC_NORMS_SPEC["description"],
            ),
        },
        PRICING_TOOL_NAME: {
            "scopes": MCP_ERP_READ_SCOPES,
            "spec": PRICING_TOOL_SPEC,
            "tool": StructuredTool.from_function(
                func=pricing_tool,
                name=PRICING_TOOL_NAME,
                description=PRICING_TOOL_SPEC["description"],
            ),
        },
        STOCK_CHECK_TOOL_NAME: {
            "scopes": MCP_ERP_READ_SCOPES,
            "spec": STOCK_CHECK_TOOL_SPEC,
            "tool": StructuredTool.from_function(
                func=stock_tool,
                name=STOCK_CHECK_TOOL_NAME,
                description=STOCK_CHECK_TOOL_SPEC["description"],
            ),
        },
        APPROVE_DISCOUNT_TOOL_NAME: {
            "scopes": MCP_SALES_ADMIN_SCOPES,
            "spec": APPROVE_DISCOUNT_TOOL_SPEC,
            "tool": StructuredTool.from_function(
                func=discount_tool,
                name=APPROVE_DISCOUNT_TOOL_NAME,
                description=APPROVE_DISCOUNT_TOOL_SPEC["description"],
            ),
        },
    }


def get_permitted_tools(user_scopes: List[str]) -> List[BaseTool]:
    normalized = _normalize_scopes(user_scopes)
    tools: List[BaseTool] = []
    for item in _build_tool_registry().values():
        if _has_any_scope(normalized, item["scopes"]):
            tools.append(item["tool"])
    return tools


def get_permitted_tool_specs(user_scopes: List[str]) -> List[Dict[str, Any]]:
    normalized = _normalize_scopes(user_scopes)
    specs: List[Dict[str, Any]] = []
    for item in _build_tool_registry().values():
        if _has_any_scope(normalized, item["scopes"]):
            specs.append(dict(item["spec"]))
    return specs


def discover_tools_for_scopes(scopes: Optional[Sequence[str] | str]) -> List[Dict[str, Any]]:
    return get_permitted_tool_specs(list(_normalize_scopes(scopes)))


def _iter_metadata_keys(value: Any, *, prefix: str = "") -> List[str]:
    keys: List[str] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).strip()
            if not key:
                continue
            dotted = f"{prefix}.{key}" if prefix else key
            keys.append(dotted)
            keys.extend(_iter_metadata_keys(child, prefix=dotted))
    return keys


def _contains_material_code(hit: Dict[str, Any], material_code: str) -> bool:
    code = material_code.strip().lower()
    if not code:
        return False
    metadata = hit.get("metadata") or {}
    candidate_fields = (
        metadata.get("material_code"),
        metadata.get("material"),
        metadata.get("code"),
        metadata.get("product_code"),
        metadata.get("document_id"),
        metadata.get("document_title"),
        metadata.get("filename"),
        hit.get("source"),
        hit.get("text"),
    )
    for value in candidate_fields:
        if value is None:
            continue
        if code in str(value).lower():
            return True
    return False


def _normalize_metadata_filters(raw_filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    if not isinstance(raw_filters, dict):
        return normalized
    for raw_key, raw_value in raw_filters.items():
        key = str(raw_key).strip()
        if not key:
            continue
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if not value:
            continue
        normalized[key] = value
    return normalized


def _normalize_tenant_scope(tenant_id: Optional[str]) -> List[str]:
    scope: List[str] = []
    for raw in (tenant_id, GLOBAL_SHARED_TENANT):
        tenant = str(raw or "").strip()
        if not tenant or tenant in scope:
            continue
        scope.append(tenant)
    return scope


def _resolve_sync_postgres_url() -> str:
    raw = str(getattr(settings, "POSTGRES_SYNC_URL", "") or getattr(settings, "database_url", "") or "").strip()
    if raw.startswith("postgresql+asyncpg://"):
        return raw.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if raw.startswith("postgres+asyncpg://"):
        return raw.replace("postgres+asyncpg://", "postgresql+psycopg://", 1)
    return raw


@lru_cache(maxsize=1)
def _get_sync_engine() -> Engine:
    sync_url = _resolve_sync_postgres_url()
    if not sync_url:
        raise RuntimeError("POSTGRES_SYNC_URL/database_url is not configured for deterministic norms query.")
    return create_engine(sync_url, future=True, pool_pre_ping=True)


def _normalize_material(material: str) -> str:
    return str(material or "").strip().lower()


def _serialize_date(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if value is None:
        return None
    return str(value)


def _serialize_din_norm_row(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("payload_json")
    if not isinstance(payload, dict):
        payload = {}
    return {
        "norm_code": row.get("norm_code"),
        "material": row.get("material"),
        "medium": row.get("medium"),
        "pressure_min_bar": row.get("pressure_min_bar"),
        "pressure_max_bar": row.get("pressure_max_bar"),
        "temperature_min_c": row.get("temperature_min_c"),
        "temperature_max_c": row.get("temperature_max_c"),
        "payload": payload,
        "source_ref": row.get("source_ref"),
        "revision": row.get("revision"),
        "version": int(row.get("version") or 1),
        "effective_date": _serialize_date(row.get("effective_date")),
        "valid_until": _serialize_date(row.get("valid_until")),
        "tenant_id": row.get("tenant_id"),
    }


def _serialize_material_limit_row(row: Dict[str, Any]) -> Dict[str, Any]:
    conditions = row.get("conditions_json")
    if not isinstance(conditions, dict):
        conditions = {}
    return {
        "material": row.get("material"),
        "medium": row.get("medium"),
        "limit_kind": row.get("limit_kind"),
        "min_value": row.get("min_value"),
        "max_value": row.get("max_value"),
        "unit": row.get("unit"),
        "conditions": conditions,
        "source_ref": row.get("source_ref"),
        "revision": row.get("revision"),
        "version": int(row.get("version") or 1),
        "effective_date": _serialize_date(row.get("effective_date")),
        "valid_until": _serialize_date(row.get("valid_until")),
        "tenant_id": row.get("tenant_id"),
    }


def query_deterministic_norms(
    material: str,
    temp: float,
    pressure: float,
    *,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministic SQL query for numeric norms/material limits."""
    material_norm = _normalize_material(material)
    if not material_norm:
        raise ValueError("material is required")
    try:
        temp_value = float(temp)
        pressure_value = float(pressure)
    except (TypeError, ValueError) as exc:
        raise ValueError("temp and pressure must be numeric") from exc

    today = date.today()
    tenant_scope = _normalize_tenant_scope(tenant_id)
    normalized_tenant_id = str(tenant_id or "").strip() or None

    try:
        engine = _get_sync_engine()
        with Session(engine) as session:
            norm_result = session.execute(
                text(
                    """
                    SELECT
                        tenant_id,
                        norm_code,
                        material,
                        medium,
                        pressure_min_bar,
                        pressure_max_bar,
                        temperature_min_c,
                        temperature_max_c,
                        payload_json,
                        source_ref,
                        revision,
                        version,
                        effective_date,
                        valid_until
                    FROM deterministic_din_norms
                    WHERE lower(material) = :material
                      AND is_active = TRUE
                      AND effective_date <= :today
                      AND (valid_until IS NULL OR valid_until >= :today)
                      AND (temperature_min_c IS NULL OR temperature_min_c <= :temp)
                      AND (temperature_max_c IS NULL OR temperature_max_c >= :temp)
                      AND (pressure_min_bar IS NULL OR pressure_min_bar <= :pressure)
                      AND (pressure_max_bar IS NULL OR pressure_max_bar >= :pressure)
                      AND (
                            :tenant_id IS NULL
                            OR tenant_id IS NULL
                            OR tenant_id = :tenant_id
                            OR tenant_id = :global_tenant
                      )
                    ORDER BY effective_date DESC, version DESC
                    LIMIT 25
                    """
                ),
                {
                    "material": material_norm,
                    "temp": temp_value,
                    "pressure": pressure_value,
                    "today": today,
                    "tenant_id": normalized_tenant_id,
                    "global_tenant": GLOBAL_SHARED_TENANT,
                },
            )
            limit_result = session.execute(
                text(
                    """
                    SELECT
                        tenant_id,
                        material,
                        medium,
                        limit_kind,
                        min_value,
                        max_value,
                        unit,
                        conditions_json,
                        source_ref,
                        revision,
                        version,
                        effective_date,
                        valid_until
                    FROM deterministic_material_limits
                    WHERE lower(material) = :material
                      AND is_active = TRUE
                      AND effective_date <= :today
                      AND (valid_until IS NULL OR valid_until >= :today)
                      AND (
                            :tenant_id IS NULL
                            OR tenant_id IS NULL
                            OR tenant_id = :tenant_id
                            OR tenant_id = :global_tenant
                      )
                      AND (
                            limit_kind NOT IN ('temperature', 'pressure')
                            OR (
                                limit_kind = 'temperature'
                                AND (min_value IS NULL OR min_value <= :temp)
                                AND (max_value IS NULL OR max_value >= :temp)
                            )
                            OR (
                                limit_kind = 'pressure'
                                AND (min_value IS NULL OR min_value <= :pressure)
                                AND (max_value IS NULL OR max_value >= :pressure)
                            )
                      )
                    ORDER BY effective_date DESC, version DESC
                    LIMIT 50
                    """
                ),
                {
                    "material": material_norm,
                    "temp": temp_value,
                    "pressure": pressure_value,
                    "today": today,
                    "tenant_id": normalized_tenant_id,
                    "global_tenant": GLOBAL_SHARED_TENANT,
                },
            )
            norm_rows = [dict(row._mapping) for row in norm_result]
            limit_rows = [dict(row._mapping) for row in limit_result]
    except SQLAlchemyError as exc:
        logger.warning(
            "query_deterministic_norms_sql_error",
            extra={
                "material": material,
                "temp": temp_value,
                "pressure": pressure_value,
                "tenant_id": tenant_id,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return {
            "tool": QUERY_DETERMINISTIC_NORMS_TOOL_NAME,
            "material": material,
            "temp": temp_value,
            "pressure": pressure_value,
            "status": "error",
            "matches": {"din_norms": [], "material_limits": []},
            "context": "Deterministic norms query failed.",
            "retrieval_meta": {
                "source": "postgresql",
                "mode": "exact_range_sql",
                "error": f"{type(exc).__name__}: {exc}",
            },
        }

    norm_matches = [_serialize_din_norm_row(row) for row in norm_rows]
    limit_matches = [_serialize_material_limit_row(row) for row in limit_rows]

    status = "ok" if norm_matches or limit_matches else "no_match"
    if status == "ok":
        summary = (
            f"Deterministic limits matched: {len(norm_matches)} DIN norm rows, "
            f"{len(limit_matches)} material limit rows."
        )
    else:
        summary = "No deterministic norm/material limit rows matched the input range."

    return {
        "tool": QUERY_DETERMINISTIC_NORMS_TOOL_NAME,
        "material": material,
        "temp": temp_value,
        "pressure": pressure_value,
        "status": status,
        "matches": {
            "din_norms": norm_matches,
            "material_limits": limit_matches,
        },
        "context": summary,
        "retrieval_meta": {
            "source": "postgresql",
            "mode": "exact_range_sql",
            "tenant_scope": tenant_scope,
            "din_match_count": len(norm_matches),
            "material_limit_match_count": len(limit_matches),
        },
    }


def _extract_tables_from_metadata(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    table_payloads: List[Dict[str, Any]] = []
    if not isinstance(metadata, dict):
        return table_payloads
    candidates: List[Any] = [metadata]
    nested_metadata = metadata.get("metadata")
    if isinstance(nested_metadata, dict):
        candidates.append(nested_metadata)
    additional = metadata.get("additional_metadata")
    if isinstance(additional, dict):
        candidates.append(additional)
    if isinstance(nested_metadata, dict):
        nested_additional = nested_metadata.get("additional_metadata")
        if isinstance(nested_additional, dict):
            candidates.append(nested_additional)

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("table", "tables", "table_data", "tabular_data"):
            raw = candidate.get(key)
            if isinstance(raw, dict):
                table_payloads.append(raw)
            elif isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        table_payloads.append(item)
    return table_payloads


def _markdown_table(table_payload: Dict[str, Any], max_rows: int = 8, max_cols: int = 6) -> str:
    columns = table_payload.get("columns")
    rows = table_payload.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list) or not columns or not rows:
        return ""
    col_names = [str(col).strip() for col in columns if str(col).strip()]
    if not col_names:
        return ""
    col_names = col_names[:max_cols]

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
    return "\n".join([header, divider, *body])


def _render_hit_tables(metadata: Dict[str, Any]) -> str:
    blocks: List[str] = []
    for table_payload in _extract_tables_from_metadata(metadata):
        table_markdown = _markdown_table(table_payload)
        if table_markdown:
            blocks.append("Table:\n" + table_markdown)
    return "\n\n".join(blocks).strip()


def _format_hit(hit: Dict[str, Any], *, index: int) -> Dict[str, Any]:
    metadata = hit.get("metadata") or {}
    text = (hit.get("text") or "").strip()
    if len(text) > 420:
        text = f"{text[:420]}..."
    score_value = _raw_hit_score(hit)
    table_context = _render_hit_tables(metadata)
    return {
        "rank": index,
        "score": round(score_value, 4),
        "snippet": text,
        "source": metadata.get("source") or hit.get("source"),
        "document_id": metadata.get("document_id") or metadata.get("doc_id") or metadata.get("id"),
        "filename": metadata.get("filename") or metadata.get("file_name"),
        "page": metadata.get("page") or metadata.get("page_number"),
        "table_context": table_context,
        "metadata": metadata,
    }


def _raw_hit_score(hit: Dict[str, Any]) -> float:
    has_retrieval_score = ("vector_score" in hit) or ("sparse_score" in hit)
    if has_retrieval_score:
        score = max(
            float(hit.get("vector_score") or 0.0),
            float(hit.get("sparse_score") or 0.0),
        )
    else:
        score = hit.get("fused_score")
    try:
        return float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _is_relevant_hit(hit: Dict[str, Any]) -> bool:
    score_value = _raw_hit_score(hit)
    return score_value > 0.0


def _render_context(hits: List[Dict[str, Any]]) -> str:
    if not hits:
        return ""
    lines: List[str] = []
    for hit in hits:
        src = hit.get("source") or hit.get("filename") or hit.get("document_id") or "unknown"
        page = f" page {hit['page']}" if hit.get("page") is not None else ""
        lines.append(f"[{hit['rank']}] {src}{page} (score {hit['score']})")
        snippet = (hit.get("snippet") or "").strip()
        if snippet:
            lines.append(snippet)
        table_context = str(hit.get("table_context") or "").strip()
        if table_context:
            lines.append(table_context)
    return "\n".join(lines)


def search_technical_docs(
    query: str,
    material_code: Optional[str] = None,
    *,
    tenant_id: Optional[str] = None,
    k: int = 5,
    metadata_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    query_text = (query or "").strip()
    if not query_text:
        raise ValueError("query is required")

    requested_k = max(1, min(int(k or 5), 10))
    retrieval_query = query_text
    material_code_norm = material_code.strip() if material_code and material_code.strip() else None
    if material_code_norm:
        retrieval_query = f"{query_text} {material_code_norm}"

    collection = _active_collection_name()
    global_collection = _is_global_technical_collection(collection)
    tenant_scope = _normalize_tenant_scope(tenant_id)

    retrieval_filters: Dict[str, Any] = {}
    if tenant_scope:
        retrieval_filters["tenant_id"] = tenant_scope if len(tenant_scope) > 1 else tenant_scope[0]
    if material_code_norm:
        retrieval_filters["material_code"] = material_code_norm
    retrieval_filters.update(_normalize_metadata_filters(metadata_filters))

    def _retrieve(filters: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        raw_tenant = filters.get("tenant_id")
        effective_tenant = None
        if isinstance(raw_tenant, list):
            effective_tenant = next((str(item).strip() for item in raw_tenant if str(item).strip() and str(item).strip() != GLOBAL_SHARED_TENANT), None)
            if not effective_tenant and raw_tenant:
                effective_tenant = str(raw_tenant[0]).strip() or None
        else:
            effective_tenant = str(raw_tenant or "").strip() or None
        retrieved_hits, retrieved_metrics = hybrid_retrieve(
            query=retrieval_query,
            tenant=effective_tenant,
            k=max(requested_k, 8),
            metadata_filters=dict(filters) if filters else None,
            use_rerank=True,
            qdrant_timeout_s=INITIAL_QDRANT_TIMEOUT_S,
            return_metrics=True,
        )
        metrics_payload = dict(retrieved_metrics or {})
        if tenant_scope:
            metrics_payload["tenant_scope"] = tenant_scope
        if tenant_scope and global_collection:
            metrics_payload["tenant_scope_applied_on_global_collection"] = True
        return list(retrieved_hits or []), metrics_payload

    active_filters = dict(retrieval_filters)
    retrieved, metrics = _retrieve(active_filters)
    # If material metadata is missing in the index, relax the exact metadata filter.
    if material_code_norm and not retrieved:
        active_filters.pop("material_code", None)
        retrieved, metrics = _retrieve(active_filters)
        metrics["material_code_filter_relaxed"] = True
    # If tenant scoping yields no hits, retry without tenant filter.
    if tenant_id and "tenant_id" in active_filters and not retrieved:
        active_filters.pop("tenant_id", None)
        retrieved, metrics = _retrieve(active_filters)
        metrics["tenant_filter_relaxed"] = True

    filtered = list(retrieved or [])
    filtered = [hit for hit in filtered if isinstance(hit, dict) and _is_relevant_hit(hit)]
    if material_code_norm:
        strict = [hit for hit in filtered if _contains_material_code(hit, material_code_norm)]
        if strict:
            filtered = strict

    final_hits = [_format_hit(hit, index=i + 1) for i, hit in enumerate(filtered[:requested_k])]
    context = _render_context(final_hits)
    top_scores = [float(hit.get("score") or 0.0) for hit in final_hits]
    metrics = dict(metrics or {})
    metrics["threshold"] = 0.0
    metrics["configured_threshold"] = RAG_MIN_SCORE_THRESHOLD
    metrics["k_returned"] = len(final_hits)
    metrics["top_scores"] = top_scores[:5]
    logger.info(
        "mcp_search_technical_docs",
        extra={
            "tenant_id": tenant_id,
            "global_collection": global_collection,
            "collection": collection,
            "query": query_text[:120],
            "material_code": material_code_norm,
            "metadata_filter_keys": sorted((metadata_filters or {}).keys()),
            "hits": len(final_hits),
        },
    )

    return {
        "tool": SEARCH_TECHNICAL_DOCS_TOOL_NAME,
        "query": query_text,
        "material_code": material_code_norm,
        "metadata_filters": _normalize_metadata_filters(metadata_filters),
        "hits": final_hits,
        "context": context,
        "retrieval_meta": metrics,
    }


def get_available_filters(
    *,
    tenant_id: Optional[str] = None,
    max_points: int = 2000,
    collection_name: Optional[str] = None,
) -> Dict[str, Any]:
    scanned = 0
    matched = 0
    filters: set[str] = set()

    max_points = max(1, min(int(max_points or 2000), 20000))
    configured_collection = _active_collection_name()
    collection = (configured_collection or collection_name or "").strip()
    apply_tenant_scope = bool(tenant_id and not _is_global_technical_collection(collection))
    client = QdrantClient(url=str(settings.qdrant_url).rstrip("/"), api_key=(os.getenv("QDRANT_API_KEY") or None))

    offset: Any = None
    while scanned < max_points:
        points, offset = client.scroll(
            collection_name=collection,
            limit=min(256, max_points - scanned),
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for point in points:
            scanned += 1
            payload = point.payload or {}
            metadata = payload.get("metadata") or {}
            point_tenant = payload.get("tenant_id") or metadata.get("tenant_id")
            if apply_tenant_scope and point_tenant != tenant_id:
                continue
            matched += 1
            if isinstance(metadata, dict):
                for key in _iter_metadata_keys(metadata):
                    filters.add(key)
        if offset is None:
            break

    logger.info(
        "mcp_get_available_filters",
        extra={
            "tenant_id": tenant_id,
            "collection": collection,
            "scanned_points": scanned,
            "matched_points": matched,
            "filter_count": len(filters),
            "tenant_filter_applied": apply_tenant_scope,
        },
    )
    sorted_filters = sorted(filters)
    preview = ", ".join(sorted_filters[:12]) if sorted_filters else "none"
    return {
        "tool": GET_AVAILABLE_FILTERS_TOOL_NAME,
        "tenant_id": tenant_id,
        "collection": collection,
        "scanned_points": scanned,
        "matched_points": matched,
        "tenant_filter_applied": apply_tenant_scope,
        "filters": sorted_filters,
        "context": f"Discovered {len(sorted_filters)} metadata filters. Preview: {preview}",
    }


def build_mcp_tool_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    content_text = payload.get("context") or "No results."
    return {
        "content": [{"type": "text", "text": content_text}],
        "structuredContent": payload,
    }


def execute_tool_call(
    *,
    tool_name: str,
    arguments: Optional[Dict[str, Any]],
    tenant_id: Optional[str],
    state: Any = None,
    audit_trail: Optional[List[Dict[str, Any] | ToolCallRecord]] = None,
    run_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    args = arguments or {}
    if tool_name == SEARCH_TECHNICAL_DOCS_TOOL_NAME:
        payload = _invoke_tool_with_audit(
            tool_name=SEARCH_TECHNICAL_DOCS_TOOL_NAME,
            tool_fn=search_technical_docs,
            kwargs={
                "query": str(args.get("query") or ""),
                "material_code": (str(args.get("material_code")) if args.get("material_code") is not None else None),
                "tenant_id": tenant_id,
                "k": int(args.get("k") or 5),
                "metadata_filters": (
                    args.get("metadata_filters") if isinstance(args.get("metadata_filters"), dict) else None
                ),
            },
            state=state,
            audit_trail=audit_trail,
            run_id=run_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return build_mcp_tool_result(payload)
    if tool_name == GET_AVAILABLE_FILTERS_TOOL_NAME:
        payload = _invoke_tool_with_audit(
            tool_name=GET_AVAILABLE_FILTERS_TOOL_NAME,
            tool_fn=get_available_filters,
            kwargs={
                "tenant_id": str(args.get("tenant_id") or tenant_id or "").strip() or None,
                "max_points": int(args.get("max_points") or 2000),
            },
            state=state,
            audit_trail=audit_trail,
            run_id=run_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return build_mcp_tool_result(payload)
    if tool_name == QUERY_DETERMINISTIC_NORMS_TOOL_NAME:
        payload = _invoke_tool_with_audit(
            tool_name=QUERY_DETERMINISTIC_NORMS_TOOL_NAME,
            tool_fn=query_deterministic_norms,
            kwargs={
                "material": str(args.get("material") or ""),
                "temp": float(args.get("temp")),
                "pressure": float(args.get("pressure")),
                "tenant_id": str(args.get("tenant_id") or tenant_id or "").strip() or None,
            },
            state=state,
            audit_trail=audit_trail,
            run_id=run_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return build_mcp_tool_result(payload)
    if tool_name == PRICING_TOOL_NAME:
        payload = _invoke_tool_with_audit(
            tool_name=PRICING_TOOL_NAME,
            tool_fn=_pricing_tool,
            kwargs={
                "sku": str(args.get("sku") or ""),
                "quantity": int(args.get("quantity") or 1),
                "currency": str(args.get("currency") or "EUR"),
            },
            state=state,
            audit_trail=audit_trail,
            run_id=run_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return build_mcp_tool_result(payload)
    if tool_name == STOCK_CHECK_TOOL_NAME:
        payload = _invoke_tool_with_audit(
            tool_name=STOCK_CHECK_TOOL_NAME,
            tool_fn=_stock_check_tool,
            kwargs={
                "sku": str(args.get("sku") or ""),
                "warehouse": (str(args.get("warehouse")) if args.get("warehouse") is not None else None),
            },
            state=state,
            audit_trail=audit_trail,
            run_id=run_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return build_mcp_tool_result(payload)
    if tool_name == APPROVE_DISCOUNT_TOOL_NAME:
        payload = _invoke_tool_with_audit(
            tool_name=APPROVE_DISCOUNT_TOOL_NAME,
            tool_fn=_approve_discount_tool,
            kwargs={
                "quote_id": str(args.get("quote_id") or ""),
                "discount_percent": float(args.get("discount_percent") or 0.0),
                "reason": (str(args.get("reason")) if args.get("reason") is not None else None),
            },
            state=state,
            audit_trail=audit_trail,
            run_id=run_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return build_mcp_tool_result(payload)
    raise KeyError(f"unknown_tool:{tool_name}")


def tool_spec_json() -> str:
    return json.dumps(
        [SEARCH_TECHNICAL_DOCS_SPEC, GET_AVAILABLE_FILTERS_SPEC, QUERY_DETERMINISTIC_NORMS_SPEC],
        ensure_ascii=False,
    )


__all__ = [
    "APPROVE_DISCOUNT_TOOL_NAME",
    "APPROVE_DISCOUNT_TOOL_SPEC",
    "MCP_KNOWLEDGE_READ_SCOPES",
    "MCP_ERP_READ_SCOPES",
    "MCP_SALES_ADMIN_SCOPES",
    "MCP_TRANSPORT_PREFERENCE",
    "GET_AVAILABLE_FILTERS_SPEC",
    "GET_AVAILABLE_FILTERS_TOOL_NAME",
    "QUERY_DETERMINISTIC_NORMS_SPEC",
    "QUERY_DETERMINISTIC_NORMS_TOOL_NAME",
    "PRICING_TOOL_NAME",
    "PRICING_TOOL_SPEC",
    "SEARCH_TECHNICAL_DOCS_SPEC",
    "SEARCH_TECHNICAL_DOCS_TOOL_NAME",
    "STOCK_CHECK_TOOL_NAME",
    "STOCK_CHECK_TOOL_SPEC",
    "build_mcp_tool_result",
    "discover_tools_for_scopes",
    "execute_tool_call",
    "get_permitted_tools",
    "get_permitted_tool_specs",
    "get_available_filters",
    "has_knowledge_scope",
    "query_deterministic_norms",
    "search_technical_docs",
    "tool_spec_json",
]
