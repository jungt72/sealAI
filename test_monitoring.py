"""Smoke tests for monitoring setup."""

from __future__ import annotations

import time

import requests

BASE_URL = "http://localhost:8000"


def test_health_endpoint() -> None:
    response = requests.get(f"{BASE_URL}/health", timeout=10)
    assert response.status_code in (200, 503), f"Unexpected status: {response.status_code}"

    data = response.json()
    assert "status" in data
    assert "checks" in data

    print("/health endpoint working")
    print(f"  status={data['status']} checks={list(data['checks'].keys())}")


def test_metrics_endpoint() -> None:
    response = requests.get(f"{BASE_URL}/metrics", timeout=10)
    assert response.status_code == 200

    content = response.text
    assert "sealai_http_requests_total" in content
    assert "sealai_pattern_requests_total" in content

    print("/metrics endpoint working")
    print(f"  metric_types={content.count('# TYPE')}")


def test_prometheus_connection() -> None:
    time.sleep(20)
    response = requests.get("http://localhost:9090/api/v1/targets", timeout=10)
    assert response.status_code == 200

    data = response.json()
    targets = data["data"]["activeTargets"]
    sealai_target = next((t for t in targets if "sealai" in t.get("labels", {}).get("job", "")), None)

    assert sealai_target is not None, "SealAI target not found"
    assert sealai_target.get("health") == "up", "SealAI target not healthy"

    print("Prometheus scraping working")


def test_grafana_connection() -> None:
    response = requests.get("http://localhost:3000/api/health", timeout=10)
    assert response.status_code == 200
    print("Grafana accessible")


if __name__ == "__main__":
    print("=== MONITORING SMOKE TESTS ===")
    try:
        test_health_endpoint()
        test_metrics_endpoint()
        test_prometheus_connection()
        test_grafana_connection()
        print("ALL TESTS PASSED")
    except AssertionError as exc:
        print(f"TEST FAILED: {exc}")
    except requests.exceptions.ConnectionError:
        print("CONNECTION ERROR: Is docker-compose running?")
