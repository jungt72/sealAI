from __future__ import annotations

import logging

import pytest

from sealai_v2.llm.telemetry import LlmCallTelemetry, LoggingTelemetrySink
from sealai_v2.obs.telemetry_sampling import (
    resolve_telemetry_sample_rate,
    should_sample,
)


@pytest.mark.parametrize(
    ("configured", "expected"),
    ((None, 1.0), ("", 1.0), ("0", 0.0), ("0.125", 0.125), ("1", 1.0)),
)
def test_sample_rate_contract(monkeypatch, configured, expected) -> None:
    monkeypatch.delenv("SEALAI_V2_TELEMETRY_SAMPLE_RATE", raising=False)
    if configured is not None:
        monkeypatch.setenv("SEALAI_V2_TELEMETRY_SAMPLE_RATE", configured)
    assert resolve_telemetry_sample_rate() == expected


@pytest.mark.parametrize("configured", ("invalid", "-0.1", "1.1", "nan", "inf"))
def test_invalid_sample_rate_fails_closed(configured: str) -> None:
    assert resolve_telemetry_sample_rate(configured) == 0.0


def test_sampling_boundaries_do_not_call_rng() -> None:
    def fail() -> float:
        raise AssertionError("RNG must not be called")

    assert should_sample(1.0, random_value=fail) is True
    assert should_sample(0.0, random_value=fail) is False


def _event(status: str) -> LlmCallTelemetry:
    return LlmCallTelemetry(
        provider="mistral",
        model="mistral-small-2603",
        stage="l1",
        prompt_cache_key="sealai:global:l1:model:0123456789abcdef",
        prompt_hash=None,
        prompt_tokens=10,
        cached_tokens=4,
        completion_tokens=3,
        total_tokens=13,
        cache_ratio=0.4,
        latency_ms=12.5,
        status=status,
        error_type="ProviderTimeout" if status == "error" else None,
    )


def test_success_logs_can_be_fully_sampled_out(caplog) -> None:
    sink = LoggingTelemetrySink(sample_rate=0.0)
    with caplog.at_level(logging.INFO, logger="sealai_v2.llm.telemetry"):
        sink.record(_event("ok"))
    assert caplog.records == []


def test_error_logs_are_never_sampled_out(caplog) -> None:
    sink = LoggingTelemetrySink(sample_rate=0.0)
    with caplog.at_level(logging.INFO, logger="sealai_v2.llm.telemetry"):
        sink.record(_event("error"))
    assert len(caplog.records) == 1
    rendered = caplog.records[0].getMessage()
    assert "status=error" in rendered
    assert "ProviderTimeout" in rendered
    assert "sealai:global" not in rendered
