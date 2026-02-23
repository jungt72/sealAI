"""Prometheus instruments for SEALAI v4.4.0 (Sprint 9).

All counters and histograms are defined here as module-level singletons.
Import from this module wherever metrics need to be incremented.

Metric naming convention: sealai_<subsystem>_<name>_<unit>
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "sealai_http_requests_total",
    "Total HTTP requests handled by the SEALAI backend",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "sealai_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ---------------------------------------------------------------------------
# LangGraph node executions
# ---------------------------------------------------------------------------

graph_node_runs_total = Counter(
    "sealai_graph_node_runs_total",
    "Number of LangGraph node executions",
    ["node"],
)

# ---------------------------------------------------------------------------
# Quality Gate (P4.5)
# ---------------------------------------------------------------------------

qgate_checks_total = Counter(
    "sealai_qgate_checks_total",
    "Quality gate check outcomes",
    ["check_name", "severity", "passed"],
)

# ---------------------------------------------------------------------------
# MCP tool calls
# ---------------------------------------------------------------------------

mcp_tool_calls_total = Counter(
    "sealai_mcp_tool_calls_total",
    "MCP tool invocations",
    ["tool", "status"],
)

__all__ = [
    "http_requests_total",
    "http_request_duration_seconds",
    "graph_node_runs_total",
    "qgate_checks_total",
    "mcp_tool_calls_total",
]
