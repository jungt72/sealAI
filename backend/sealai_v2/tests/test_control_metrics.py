from __future__ import annotations

from prometheus_client import REGISTRY, generate_latest

from sealai_v2.security.control_metrics import (
    ProviderCostCollector,
    record_auth_denial,
    record_quota_denial,
)


class _Store:
    def summary(self) -> dict:
        return {
            "day": {"reserved_cost_micros": 250_000},
            "month": {"reserved_cost_micros": 1_500_000},
        }


def _samples(collector: ProviderCostCollector) -> dict[tuple[str, str, str], float]:
    result: dict[tuple[str, str, str], float] = {}
    for family in collector.collect():
        for sample in family.samples:
            result[
                (sample.name, sample.labels["period"], sample.labels["provider"])
            ] = sample.value
    return result


def test_provider_cost_collector_reads_durable_aggregate_at_scrape_time():
    collector = ProviderCostCollector()
    collector.configure(
        store_supplier=_Store,
        daily_budget_micros=10_000_000,
        monthly_budget_micros=100_000_000,
    )
    samples = _samples(collector)
    assert samples[("sealai_v2_provider_spend_minor_units", "daily", "aggregate")] == 25
    assert (
        samples[("sealai_v2_provider_spend_minor_units", "monthly", "aggregate")] == 150
    )
    assert (
        samples[("sealai_v2_provider_budget_limit_minor_units", "daily", "aggregate")]
        == 1000
    )
    assert (
        samples[("sealai_v2_provider_budget_limit_minor_units", "monthly", "aggregate")]
        == 10_000
    )


def test_provider_cost_collector_omits_values_when_authority_is_unavailable():
    collector = ProviderCostCollector()
    collector.configure(
        store_supplier=lambda: None,
        daily_budget_micros=10_000_000,
        monthly_budget_micros=100_000_000,
    )
    assert list(collector.collect()) == []


def test_auth_and_quota_counters_have_only_bounded_reason_labels():
    record_auth_denial("attacker-controlled-value")
    record_quota_denial("attacker-controlled-value")
    metrics = generate_latest(REGISTRY).decode()
    assert 'sealai_v2_auth_denials_total{reason="other"}' in metrics
    assert 'sealai_v2_quota_denials_total{reason="other"}' in metrics
    assert "attacker-controlled-value" not in metrics
