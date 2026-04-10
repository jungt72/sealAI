"""Prometheus metrics for SealAI LangGraph v2."""

from __future__ import annotations

import os
import threading
import time

from prometheus_client import Counter, Gauge, Histogram

# Reuse already-registered HTTP metrics to avoid duplicate registration.
from app.core.metrics import (
    http_request_duration_seconds as HTTP_REQUEST_DURATION_SECONDS,
)
from app.core.metrics import http_requests_total as HTTP_REQUESTS_TOTAL

# ============================================================================
# CONVERSATION PATTERN METRICS
# ============================================================================

PATTERN_REQUESTS_TOTAL = Counter(
    "sealai_pattern_requests_total",
    "Requests by conversation pattern",
    ["pattern"],
)

PATTERN_LATENCY_SECONDS = Histogram(
    "sealai_pattern_latency_seconds",
    "Latency by conversation pattern",
    ["pattern"],
    buckets=(0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0),
)

GATE_ROUTE_DECISIONS_TOTAL = Counter(
    "sealai_gate_route_decisions_total",
    "Frontdoor gate routing decisions by canonical route",
    ["route"],
)

GATE_ROUTE_DECISION_SECONDS = Histogram(
    "sealai_gate_route_decision_seconds",
    "Frontdoor gate decision latency by canonical route",
    ["route"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)

# ============================================================================
# LLM METRICS
# ============================================================================

LLM_CALLS_TOTAL = Counter(
    "sealai_llm_calls_total",
    "Total LLM API calls",
    ["model", "status"],
)

LLM_LATENCY_SECONDS = Histogram(
    "sealai_llm_latency_seconds",
    "LLM API call latency",
    ["model"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
)

LLM_TOKENS_TOTAL = Counter(
    "sealai_llm_tokens_total",
    "Total tokens consumed",
    ["model", "type"],
)

# ============================================================================
# RAG METRICS
# ============================================================================

RAG_RETRIEVALS_TOTAL = Counter(
    "sealai_rag_retrievals_total",
    "Total RAG retrievals",
    ["method", "tier"],
)

RAG_LATENCY_SECONDS = Histogram(
    "sealai_rag_latency_seconds",
    "RAG retrieval latency",
    ["method"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0),
)

RAG_CACHE_HITS_TOTAL = Counter(
    "sealai_rag_cache_hits_total",
    "RAG cache hits",
    ["source"],
)

RAG_CACHE_MISSES_TOTAL = Counter(
    "sealai_rag_cache_misses_total",
    "RAG cache misses",
    ["source"],
)

# ============================================================================
# GRAPH EXECUTION METRICS
# ============================================================================

GRAPH_EXECUTIONS_TOTAL = Counter(
    "sealai_graph_executions_total",
    "Total graph executions",
    ["status"],
)

GRAPH_NODE_EXECUTIONS_TOTAL = Counter(
    "sealai_graph_node_executions_total",
    "Executions per node",
    ["node_name"],
)

GRAPH_NODE_LATENCY_SECONDS = Histogram(
    "sealai_graph_node_latency_seconds",
    "Latency per graph node",
    ["node_name"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0),
)

# ============================================================================
# ERROR METRICS
# ============================================================================

ERRORS_TOTAL = Counter(
    "sealai_errors_total",
    "Total errors",
    ["component", "error_type"],
)

QUALITY_GATE_BLOCKS_TOTAL = Counter(
    "sealai_quality_gate_blocks_total",
    "Quality gate blocks",
    ["check_id", "severity"],
)

# ============================================================================
# DEPENDENCY HEALTH
# ============================================================================

DEPENDENCY_UP = Gauge(
    "sealai_dependency_up",
    "Dependency health (1=up, 0=down)",
    ["dependency"],
)

QDRANT_COLLECTION_STATUS = Gauge(
    "sealai_qdrant_collection_status",
    "Qdrant collection visibility (1=reachable, 0=unreachable)",
    ["collection"],
)

QDRANT_COLLECTION_POINTS = Gauge(
    "sealai_qdrant_collection_points",
    "Last observed point count for a Qdrant collection",
    ["collection"],
)

QDRANT_COLLECTION_INDEXED_VECTORS = Gauge(
    "sealai_qdrant_collection_indexed_vectors",
    "Last observed indexed vector count for a Qdrant collection",
    ["collection"],
)

RAG_INGEST_DOCUMENTS_TOTAL = Counter(
    "sealai_rag_ingest_documents_total",
    "RAG document ingestion attempts by source and status",
    ["source", "status"],
)

RAG_INGEST_DURATION_SECONDS = Histogram(
    "sealai_rag_ingest_duration_seconds",
    "RAG document ingestion duration by source and status",
    ["source", "status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

RAG_LAST_SUCCESSFUL_INGEST_TIMESTAMP_SECONDS = Gauge(
    "sealai_rag_last_successful_ingest_timestamp_seconds",
    "Unix timestamp of the last successful RAG document ingest",
    ["source"],
)

RAG_SYNC_RUNS_TOTAL = Counter(
    "sealai_rag_sync_runs_total",
    "RAG sync runs by source and status",
    ["source", "status"],
)

RAG_SYNC_LAST_DOCUMENTS = Gauge(
    "sealai_rag_sync_last_documents",
    "Document counts from the last completed sync run",
    ["source", "result"],
)


_QDRANT_COLLECTION_METRICS_LOCK = threading.Lock()
_QDRANT_COLLECTION_METRICS_LAST_REFRESH = 0.0
_QDRANT_COLLECTION_METRICS_MIN_INTERVAL_SECONDS = 30.0


def track_pattern_execution(pattern: str, latency_seconds: float) -> None:
    """Track conversation pattern metrics."""
    p = (pattern or "unknown").strip() or "unknown"
    PATTERN_REQUESTS_TOTAL.labels(pattern=p).inc()
    if latency_seconds >= 0:
        PATTERN_LATENCY_SECONDS.labels(pattern=p).observe(latency_seconds)


def track_gate_route_decision(route: str, latency_seconds: float) -> None:
    """Track frontdoor gate decisions using canonical route names only."""
    raw = (route or "").strip()
    canonical = {
        "instant_light_reply": "CONVERSATION",
        "light_exploration": "EXPLORATION",
        "governed_needed": "GOVERNED",
    }.get(raw, raw)
    if canonical not in {"CONVERSATION", "EXPLORATION", "GOVERNED"}:
        canonical = "GOVERNED"
    GATE_ROUTE_DECISIONS_TOTAL.labels(route=canonical).inc()
    if latency_seconds >= 0:
        GATE_ROUTE_DECISION_SECONDS.labels(route=canonical).observe(latency_seconds)


def _default_qdrant_collection() -> str:
    return (os.getenv("QDRANT_COLLECTION") or "sealai_knowledge").strip() or "sealai_knowledge"


def _default_qdrant_url() -> str:
    return (os.getenv("QDRANT_URL") or "http://qdrant:6333").rstrip("/")


def _extract_collection_count(info: object, attr_name: str) -> float | None:
    try:
        value = getattr(info, attr_name, None)
        if value is not None:
            return float(value)
    except Exception:
        return None
    return None


def refresh_qdrant_collection_metrics(
    *,
    collection: str | None = None,
    force: bool = False,
) -> None:
    coll = (collection or _default_qdrant_collection()).strip() or _default_qdrant_collection()
    now = time.time()
    global _QDRANT_COLLECTION_METRICS_LAST_REFRESH
    with _QDRANT_COLLECTION_METRICS_LOCK:
        if not force and (now - _QDRANT_COLLECTION_METRICS_LAST_REFRESH) < _QDRANT_COLLECTION_METRICS_MIN_INTERVAL_SECONDS:
            return
        _QDRANT_COLLECTION_METRICS_LAST_REFRESH = now
    try:
        from qdrant_client import QdrantClient
    except Exception:
        return
    try:
        client = QdrantClient(
            url=_default_qdrant_url(),
            api_key=(os.getenv("QDRANT_API_KEY") or None),
        )
        info = client.get_collection(coll)
        points = _extract_collection_count(info, "points_count")
        indexed_vectors = _extract_collection_count(info, "indexed_vectors_count")
        QDRANT_COLLECTION_STATUS.labels(collection=coll).set(1)
        if points is not None:
            QDRANT_COLLECTION_POINTS.labels(collection=coll).set(points)
        if indexed_vectors is not None:
            QDRANT_COLLECTION_INDEXED_VECTORS.labels(collection=coll).set(indexed_vectors)
    except Exception:
        QDRANT_COLLECTION_STATUS.labels(collection=coll).set(0)


def track_llm_call(
    model: str,
    latency_seconds: float,
    input_tokens: int,
    output_tokens: int,
    success: bool,
) -> None:
    """Track LLM API call metrics."""
    m = (model or "unknown").strip() or "unknown"
    status = "success" if success else "error"
    LLM_CALLS_TOTAL.labels(model=m, status=status).inc()
    if latency_seconds >= 0:
        LLM_LATENCY_SECONDS.labels(model=m).observe(latency_seconds)
    if input_tokens > 0:
        LLM_TOKENS_TOTAL.labels(model=m, type="input").inc(input_tokens)
    if output_tokens > 0:
        LLM_TOKENS_TOTAL.labels(model=m, type="output").inc(output_tokens)


def track_rag_retrieval(method: str, tier: int, latency_seconds: float, cache_hit: bool) -> None:
    """Track RAG retrieval metrics."""
    meth = (method or "unknown").strip() or "unknown"
    RAG_RETRIEVALS_TOTAL.labels(method=meth, tier=str(tier)).inc()
    if latency_seconds >= 0:
        RAG_LATENCY_SECONDS.labels(method=meth).observe(latency_seconds)
    if cache_hit:
        RAG_CACHE_HITS_TOTAL.labels(source=meth).inc()
    else:
        RAG_CACHE_MISSES_TOTAL.labels(source=meth).inc()
    refresh_qdrant_collection_metrics()


def track_rag_ingest(source: str, status: str, latency_seconds: float) -> None:
    src = (source or "unknown").strip() or "unknown"
    st = (status or "unknown").strip() or "unknown"
    RAG_INGEST_DOCUMENTS_TOTAL.labels(source=src, status=st).inc()
    if latency_seconds >= 0:
        RAG_INGEST_DURATION_SECONDS.labels(source=src, status=st).observe(latency_seconds)
    if st == "indexed":
        RAG_LAST_SUCCESSFUL_INGEST_TIMESTAMP_SECONDS.labels(source=src).set(time.time())
    refresh_qdrant_collection_metrics(force=(st == "indexed"))


def track_rag_sync(source: str, status: str, summary: dict[str, object] | None = None) -> None:
    src = (source or "unknown").strip() or "unknown"
    st = (status or "unknown").strip() or "unknown"
    RAG_SYNC_RUNS_TOTAL.labels(source=src, status=st).inc()
    for result_key in (
        "scanned",
        "queued",
        "skipped",
        "errors",
        "ingest_ready",
        "pilot_ready",
        "missing_pilot_tags",
    ):
        value = summary.get(result_key) if isinstance(summary, dict) else None
        if value is None:
            continue
        try:
            RAG_SYNC_LAST_DOCUMENTS.labels(source=src, result=result_key).set(float(value))
        except Exception:
            continue
    refresh_qdrant_collection_metrics(force=(st == "success"))


def track_node_execution(node_name: str, latency_seconds: float) -> None:
    """Track individual node execution."""
    node = (node_name or "unknown").strip() or "unknown"
    GRAPH_NODE_EXECUTIONS_TOTAL.labels(node_name=node).inc()
    if latency_seconds >= 0:
        GRAPH_NODE_LATENCY_SECONDS.labels(node_name=node).observe(latency_seconds)


def track_error(component: str, error_type: str) -> None:
    """Track errors by component and type."""
    comp = (component or "unknown").strip() or "unknown"
    err = (error_type or "unknown").strip() or "unknown"
    ERRORS_TOTAL.labels(component=comp, error_type=err).inc()


def track_quality_gate_block(check_id: str, severity: str) -> None:
    """Track quality gate blocks."""
    cid = (check_id or "unknown").strip() or "unknown"
    sev = (severity or "UNKNOWN").strip() or "UNKNOWN"
    QUALITY_GATE_BLOCKS_TOTAL.labels(check_id=cid, severity=sev).inc()


__all__ = [
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
    "PATTERN_REQUESTS_TOTAL",
    "PATTERN_LATENCY_SECONDS",
    "GATE_ROUTE_DECISIONS_TOTAL",
    "GATE_ROUTE_DECISION_SECONDS",
    "LLM_CALLS_TOTAL",
    "LLM_LATENCY_SECONDS",
    "LLM_TOKENS_TOTAL",
    "RAG_RETRIEVALS_TOTAL",
    "RAG_LATENCY_SECONDS",
    "RAG_CACHE_HITS_TOTAL",
    "RAG_CACHE_MISSES_TOTAL",
    "GRAPH_EXECUTIONS_TOTAL",
    "GRAPH_NODE_EXECUTIONS_TOTAL",
    "GRAPH_NODE_LATENCY_SECONDS",
    "ERRORS_TOTAL",
    "QUALITY_GATE_BLOCKS_TOTAL",
    "DEPENDENCY_UP",
    "QDRANT_COLLECTION_STATUS",
    "QDRANT_COLLECTION_POINTS",
    "QDRANT_COLLECTION_INDEXED_VECTORS",
    "RAG_INGEST_DOCUMENTS_TOTAL",
    "RAG_INGEST_DURATION_SECONDS",
    "RAG_LAST_SUCCESSFUL_INGEST_TIMESTAMP_SECONDS",
    "RAG_SYNC_RUNS_TOTAL",
    "RAG_SYNC_LAST_DOCUMENTS",
    "refresh_qdrant_collection_metrics",
    "track_gate_route_decision",
    "track_pattern_execution",
    "track_llm_call",
    "track_rag_ingest",
    "track_rag_retrieval",
    "track_rag_sync",
    "track_node_execution",
    "track_error",
    "track_quality_gate_block",
]
