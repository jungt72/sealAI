from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROMETHEUS = ROOT / "monitoring" / "prometheus.yml"
ALERTS = ROOT / "monitoring" / "rules" / "sealai-v2-alerts.yml"
BLACKBOX = ROOT / "monitoring" / "blackbox.yml"
ALERTMANAGER = ROOT / "monitoring" / "alertmanager.yml"
DASHBOARDS = ROOT / "monitoring" / "grafana" / "provisioning" / "dashboards"


def _yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_prometheus_scrapes_only_current_v2_and_required_exporters() -> None:
    config = _yaml(PROMETHEUS)
    jobs = {item["job_name"]: item for item in config["scrape_configs"]}
    required = {
        "prometheus",
        "sealai-backend-v2",
        "sealai-backend-v2-worker",
        "sealai-keycloak",
        "sealai-qdrant",
        "sealai-node",
        "sealai-containers",
        "sealai-postgres",
        "sealai-redis",
        "sealai-dr-status",
        "sealai-blackbox-tls",
        "sealai-alertmanager",
    }
    assert required <= jobs.keys()
    assert "sealai-backend" not in jobs
    assert jobs["sealai-backend-v2"]["static_configs"][0]["targets"] == [
        "backend-v2:8001"
    ]
    qdrant_headers = jobs["sealai-qdrant"]["http_headers"]
    assert qdrant_headers == {
        "api-key": {"files": ["/run/secrets/qdrant_read_only_api_key"]}
    }


def test_alert_contract_covers_every_master_required_signal() -> None:
    config = _yaml(ALERTS)
    rules = [rule for group in config["groups"] for rule in group["rules"]]
    alerts = {rule["alert"] for rule in rules if "alert" in rule}
    expected = {
        "SealAIFilesystemUsage75",
        "SealAIFilesystemUsage85",
        "SealAIFilesystemUsage90",
        "SealAIFilesystemInodesHigh",
        "SealAIRedisMemoryCritical",
        "SealAIRedisWriteErrors",
        "SealAIRedisKeyGrowth",
        "SealAIRedisTtlCoverageVeryLow",
        "SealAIContainerRestarted",
        "SealAIContainerOOM",
        "SealAIContainerUnhealthy",
        "SealAIPostgresConnectionsHigh",
        "SealAIOutboxBacklog",
        "SealAIQdrantSyncDrift",
        "SealAIBackupFailed",
        "SealAIOffsiteBackupStale",
        "SealAIRestoreDrillOverdue",
        "SealAITlsCertificateExpiring",
        "SealAIProviderBudgetWarning",
        "SealAIQuotaDenials",
        "SealAIAuthAbuse",
        "SealAIBackendHigh4xxRate",
        "SealAIBackendHigh5xxRate",
        "SealAILlmProviderErrors",
        "SealAIProviderTimeouts",
        "SealAIQueueBacklog",
        "SealAIAlertDeliveryFailed",
    }
    assert expected <= alerts
    for rule in rules:
        if "alert" not in rule:
            continue
        assert rule.get("labels", {}).get("severity") in {
            "warning",
            "critical",
            "emergency",
        }
        assert "summary" in rule.get("annotations", {})


def test_rules_fail_closed_when_required_metrics_are_missing() -> None:
    text = ALERTS.read_text(encoding="utf-8")
    for metric in (
        "sealai_v2_llm_calls_total",
        "sealai_v2_route_decisions_total",
        "sealai_v2_outbox_rows",
        "sealai_v2_qdrant_sync_drift",
        "sealai_v2_provider_budget_limit_minor_units",
        "sealai_v2_provider_spend_minor_units",
        "sealai_backup_last_success_timestamp_seconds",
        "sealai_offsite_backup_last_success_timestamp_seconds",
        "sealai_restore_drill_last_success_timestamp_seconds",
        "sealai_backup_receipt_valid",
    ):
        assert f"absent({metric})" in text


def test_blackbox_tls_is_verified_and_redirects_do_not_mask_hostname_drift() -> None:
    module = _yaml(BLACKBOX)["modules"]["https_2xx"]
    http = module["http"]
    assert http["fail_if_not_ssl"] is True
    assert http["follow_redirects"] is False
    assert http["tls_config"]["insecure_skip_verify"] is False
    assert http["tls_config"]["min_version"] == "TLS12"


def test_alertmanager_receiver_is_external_file_backed_and_sends_resolution() -> None:
    config = _yaml(ALERTMANAGER)
    assert config["route"]["receiver"] == "external-primary"
    receiver = next(
        item for item in config["receivers"] if item["name"] == "external-primary"
    )
    webhook = receiver["webhook_configs"][0]
    assert webhook == {
        "url_file": "/run/secrets/alertmanager_webhook_url",
        "send_resolved": True,
    }


def test_grafana_dashboards_use_only_v2_observability_contract() -> None:
    expressions: list[str] = []
    for path in DASHBOARDS.glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        for panel in document["panels"]:
            expressions.extend(target["expr"] for target in panel["targets"])
    rendered = "\n".join(expressions)
    assert 'sealai-backend"' not in rendered
    assert "sealai_http_" not in rendered
    assert "sealai_gate_" not in rendered
    assert "/api/v1" not in rendered
    assert "sealai_v2_" in rendered


def test_monitoring_configs_do_not_embed_secrets_or_permissive_tls() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROMETHEUS, ALERTS, BLACKBOX, ALERTMANAGER)
    ).lower()
    assert "password:" not in combined
    assert "credentials:" not in combined
    assert "insecure_skip_verify: true" not in combined
    assert re.search(r"(?:image:\s*\S+:latest\b|@latest\b)", combined) is None
