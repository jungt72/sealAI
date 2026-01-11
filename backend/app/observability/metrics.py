from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Iterable

_LOCK = Lock()

_HTTP_REQUESTS_TOTAL: Counter[tuple[str, str, str]] = Counter()
_HTTP_DURATION_MS_SUM: Counter[tuple[str, str]] = Counter()
_HTTP_DURATION_MS_COUNT: Counter[tuple[str, str]] = Counter()
_RAG_RETRIEVAL_TOTAL: Counter[tuple[str]] = Counter()
_DEPENDENCY_ERRORS_TOTAL: Counter[tuple[str, str, str]] = Counter()


def observe_http_request(*, method: str, route: str, status: int, duration_ms: int) -> None:
    key = (method, route, str(status))
    sum_key = (method, route)
    with _LOCK:
        _HTTP_REQUESTS_TOTAL[key] += 1
        _HTTP_DURATION_MS_SUM[sum_key] += max(duration_ms, 0)
        _HTTP_DURATION_MS_COUNT[sum_key] += 1


def inc_rag_retrieval(outcome: str) -> None:
    with _LOCK:
        _RAG_RETRIEVAL_TOTAL[(outcome,)] += 1


def inc_dependency_error(*, dependency: str, op: str, error_class: str) -> None:
    with _LOCK:
        _DEPENDENCY_ERRORS_TOTAL[(dependency, op, error_class)] += 1


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', "\\\"")


def _format_labels(*pairs: tuple[str, str]) -> str:
    items = [f'{key}="{_escape_label(value)}"' for key, value in sorted(pairs)]
    return "{" + ",".join(items) + "}" if items else ""


def render_metrics() -> str:
    lines: list[str] = []
    with _LOCK:
        lines.append("# HELP http_requests_total Total HTTP requests.")
        lines.append("# TYPE http_requests_total counter")
        for (method, route, status), value in sorted(_HTTP_REQUESTS_TOTAL.items()):
            labels = _format_labels(("method", method), ("route", route), ("status", status))
            lines.append(f"http_requests_total{labels} {value}")

        lines.append("# HELP http_request_duration_ms Duration of HTTP requests in ms.")
        lines.append("# TYPE http_request_duration_ms summary")
        for (method, route), value in sorted(_HTTP_DURATION_MS_SUM.items()):
            labels = _format_labels(("method", method), ("route", route))
            lines.append(f"http_request_duration_ms_sum{labels} {value}")
        for (method, route), value in sorted(_HTTP_DURATION_MS_COUNT.items()):
            labels = _format_labels(("method", method), ("route", route))
            lines.append(f"http_request_duration_ms_count{labels} {value}")

        lines.append("# HELP rag_retrieval_total RAG retrievals by outcome.")
        lines.append("# TYPE rag_retrieval_total counter")
        for (outcome,), value in sorted(_RAG_RETRIEVAL_TOTAL.items()):
            labels = _format_labels(("outcome", outcome),)
            lines.append(f"rag_retrieval_total{labels} {value}")

        lines.append("# HELP dependency_errors_total Dependency errors by source.")
        lines.append("# TYPE dependency_errors_total counter")
        for (dependency, op, error_class), value in sorted(_DEPENDENCY_ERRORS_TOTAL.items()):
            labels = _format_labels(
                ("dependency", dependency),
                ("op", op),
                ("error_class", error_class),
            )
            lines.append(f"dependency_errors_total{labels} {value}")

    return "\n".join(lines) + "\n"
