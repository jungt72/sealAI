"""Prometheus metrics for SealAI LangGraph v2."""

from __future__ import annotations

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


def track_pattern_execution(pattern: str, latency_seconds: float) -> None:
    """Track conversation pattern metrics."""
    p = (pattern or "unknown").strip() or "unknown"
    PATTERN_REQUESTS_TOTAL.labels(pattern=p).inc()
    if latency_seconds >= 0:
        PATTERN_LATENCY_SECONDS.labels(pattern=p).observe(latency_seconds)


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
    "track_pattern_execution",
    "track_llm_call",
    "track_rag_retrieval",
    "track_node_execution",
    "track_error",
    "track_quality_gate_block",
]
