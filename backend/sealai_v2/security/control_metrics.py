"""Low-cardinality Prometheus signals for authentication and provider admission.

The durable Postgres store remains the authority for monetary ceilings.  The collector reads that
authority at scrape time, so a process restart cannot temporarily publish a false zero spend.  If
the store or migration is unavailable, the cost metric families are deliberately absent and the
monitoring missing-signal alert fires fail-closed.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from typing import Any

from prometheus_client import REGISTRY, Counter
from prometheus_client.core import GaugeMetricFamily

_MICROS_PER_MINOR_UNIT = 10_000
_AUTH_REASONS = ("missing_bearer", "invalid_token", "email_unverified", "other")
_QUOTA_REASONS = (
    "subject_rate",
    "tenant_rate",
    "subject_daily_quota",
    "tenant_daily_quota",
    "tenant_monthly_quota",
    "subject_concurrency",
    "tenant_concurrency",
    "provider_daily_budget",
    "provider_monthly_budget",
    "other",
)

_AUTH_DENIALS = Counter(
    "sealai_v2_auth_denials",
    "Authentication and verified-email denials at the V2 server boundary.",
    ("reason",),
)
_QUOTA_DENIALS = Counter(
    "sealai_v2_quota_denials",
    "Provider rate, quota, concurrency, and hard-budget denials.",
    ("reason",),
)

# Seed every bounded label so Prometheus sees a zero-valued counter before the first denial.
for _reason in _AUTH_REASONS:
    _AUTH_DENIALS.labels(reason=_reason).inc(0)
for _reason in _QUOTA_REASONS:
    _QUOTA_DENIALS.labels(reason=_reason).inc(0)


def record_auth_denial(reason: str) -> None:
    _AUTH_DENIALS.labels(reason=reason if reason in _AUTH_REASONS else "other").inc()


def record_quota_denial(reason: str | None) -> None:
    bounded = reason if reason in _QUOTA_REASONS else "other"
    _QUOTA_DENIALS.labels(reason=bounded).inc()


class ProviderCostCollector:
    """Scrape-time aggregate of non-refundable reservations and configured hard ceilings."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store_supplier: Callable[[], Any] | None = None
        self._daily_budget_micros = 0
        self._monthly_budget_micros = 0

    def configure(
        self,
        *,
        store_supplier: Callable[[], Any],
        daily_budget_micros: int,
        monthly_budget_micros: int,
    ) -> None:
        with self._lock:
            self._store_supplier = store_supplier
            self._daily_budget_micros = daily_budget_micros
            self._monthly_budget_micros = monthly_budget_micros

    def collect(self) -> Iterable[GaugeMetricFamily]:
        with self._lock:
            supplier = self._store_supplier
            limits = {
                "daily": self._daily_budget_micros,
                "monthly": self._monthly_budget_micros,
            }
        if supplier is None:
            return
        try:
            store = supplier()
            if store is None:
                return
            from sealai_v2.db.engine import (
                DatabaseRuntimeRole,
                bind_database_scope,
            )

            with bind_database_scope(
                tenant_id="service:metrics",
                subject_id="service:prometheus-collector",
                role=DatabaseRuntimeRole.SYSTEM_OPERATOR,
            ):
                summary = store.summary()
            reserved = {
                "daily": int(summary["day"]["reserved_cost_micros"]),
                "monthly": int(summary["month"]["reserved_cost_micros"]),
            }
            if any(value < 0 for value in (*limits.values(), *reserved.values())):
                return
        except Exception:
            # Collection is an observability boundary: omit stale/guessed values and let the
            # dedicated missing-signal alert report authority failure.
            return

        spend = GaugeMetricFamily(
            "sealai_v2_provider_spend_minor_units",
            "Aggregate non-refundable provider reservations in normalized minor currency units.",
            labels=("period", "provider"),
        )
        budget = GaugeMetricFamily(
            "sealai_v2_provider_budget_limit_minor_units",
            "Configured aggregate hard provider ceiling in normalized minor currency units.",
            labels=("period", "provider"),
        )
        for period in ("daily", "monthly"):
            labels = (period, "aggregate")
            spend.add_metric(labels, reserved[period] / _MICROS_PER_MINOR_UNIT)
            budget.add_metric(labels, limits[period] / _MICROS_PER_MINOR_UNIT)
        yield spend
        yield budget


_PROVIDER_COST_COLLECTOR = ProviderCostCollector()
REGISTRY.register(_PROVIDER_COST_COLLECTOR)


def configure_provider_cost_metrics(
    *,
    store_supplier: Callable[[], Any],
    daily_budget_micros: int,
    monthly_budget_micros: int,
) -> None:
    _PROVIDER_COST_COLLECTOR.configure(
        store_supplier=store_supplier,
        daily_budget_micros=daily_budget_micros,
        monthly_budget_micros=monthly_budget_micros,
    )
