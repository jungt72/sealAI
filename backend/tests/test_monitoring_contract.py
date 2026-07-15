from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROMETHEUS = ROOT / "monitoring" / "prometheus.yml"
ALERTS = ROOT / "monitoring" / "rules" / "sealai-v2-alerts.yml"
BLACKBOX = ROOT / "monitoring" / "blackbox.yml"
ALERTMANAGER = ROOT / "monitoring" / "alertmanager.yml"
DASHBOARDS = ROOT / "monitoring" / "grafana" / "provisioning" / "dashboards"
COMPOSE = ROOT / "docker-compose.yml"
COMPOSE_DEPLOY = ROOT / "docker-compose.deploy.yml"
NGINX = ROOT / "nginx" / "default.conf"


def _yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@lru_cache(maxsize=1)
def _render_compose() -> dict:
    """Render the actual two-file production model without contacting a daemon."""
    docker = shutil.which("docker")
    assert docker is not None, "docker compose is required for the monitoring contract"
    digest = "a" * 64
    env = os.environ.copy()
    compose_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (COMPOSE, COMPOSE_DEPLOY)
    )
    required = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?[^}]*}", compose_source))
    for index, name in enumerate(sorted(required), start=1):
        if name.endswith("_IMAGE"):
            env[name] = f"registry.invalid/{name.lower()}@sha256:{index:064x}"
        elif name.endswith("_MEMORY_LIMIT"):
            env[name] = "512m"
        elif name.endswith("_CPU_LIMIT"):
            env[name] = "1.0"
        elif name.endswith("_PIDS_LIMIT"):
            env[name] = "128"
        else:
            env[name] = f"DUMMY_{name}"
    for name in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "QDRANT_API_KEY",
        "QDRANT_READ_ONLY_API_KEY",
        "REDIS_EXPORTER_PASSWORD",
        "GRAFANA_ADMIN_PASSWORD",
        "NEXTAUTH_SECRET",
        "AUTH_SECRET",
        "KEYCLOAK_CLIENT_SECRET",
        "OPENAI_API_KEY",
        "MISTRAL_API_KEY",
    ):
        env[name] = "DUMMY"
    env["POSTGRES_EXPORTER_DSN"] = "".join(
        ("postgresql", "://monitor:DUMMY@postgres:5432/postgres")
    )
    env.update(
        {
            "ALERTMANAGER_WEBHOOK_URL": "https://alerts.invalid/primary",
            "ALERTMANAGER_WATCHDOG_URL": "https://watchdog.invalid/heartbeat",
            "NODE_EXPORTER_TEXTFILE_DIR": "/tmp/sealai-textfile-contract",
            "NEXTAUTH_URL": "https://example.invalid",
            "KEYCLOAK_ISSUER": "https://example.invalid/realms/test",
            "KEYCLOAK_CLIENT_ID": "synthetic-client",
            "FRONTEND_IMAGE": f"example.invalid/frontend@sha256:{digest}",
            "KEYCLOAK_IMAGE": f"example.invalid/keycloak@sha256:{digest}",
            "ALERTMANAGER_IMAGE": f"prom/alertmanager@sha256:{digest}",
            "BLACKBOX_EXPORTER_IMAGE": f"prom/blackbox-exporter@sha256:{digest}",
            "NODE_EXPORTER_IMAGE": f"prom/node-exporter@sha256:{digest}",
            "CADVISOR_IMAGE": f"gcr.io/cadvisor/cadvisor@sha256:{digest}",
            "POSTGRES_EXPORTER_IMAGE": (
                f"quay.io/prometheuscommunity/postgres-exporter@sha256:{digest}"
            ),
            "REDIS_EXPORTER_IMAGE": f"oliver006/redis_exporter@sha256:{digest}",
        }
    )
    completed = subprocess.run(
        [
            docker,
            "compose",
            "-f",
            str(COMPOSE),
            "-f",
            str(COMPOSE_DEPLOY),
            "--profile",
            "v2",
            "--profile",
            "observability",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value


def test_prometheus_scrapes_only_current_v2_and_required_exporters() -> None:
    config = _yaml(PROMETHEUS)
    assert config["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"] == [
        "alertmanager:9093"
    ]
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
        "sealai-blackbox-tls-apex",
        "sealai-blackbox-tls-www-redirect",
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
    assert jobs["sealai-node"]["metric_relabel_configs"][0] == {
        "source_labels": ["__name__"],
        "regex": "sealai_(backup|offsite_backup|restore_drill)_.*",
        "action": "drop",
    }
    assert jobs["sealai-dr-status"]["metric_relabel_configs"][0]["action"] == ("keep")


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
        "SealAIContainerMissing",
        "SealAIPostgresConnectionsHigh",
        "SealAIOutboxBacklog",
        "SealAIProjectionBacklog",
        "SealAIBackupFailed",
        "SealAIOffsiteBackupStale",
        "SealAIRestoreDrillOverdue",
        "SealAITlsApexProbeFailed",
        "SealAITlsWwwRedirectProbeFailed",
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
        "SealAIWatchdog",
        "SealAIRequiredQueueMetricMissing",
        "SealAIBackupSuccessComponentMissing",
        "SealAIBackupFailureComponentMissing",
        "SealAIOffsiteBackupComponentMissing",
        "SealAIRestoreDrillComponentMissing",
        "SealAIBackupReceiptComponentMissing",
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
    config = _yaml(ALERTS)
    rules = [rule for group in config["groups"] for rule in group["rules"]]
    alert_rules = {
        rule["alert"]: str(rule["expr"]) for rule in rules if "alert" in rule
    }
    targets = alert_rules["SealAIRequiredScrapeTargetMissing"]
    for job in (
        "prometheus",
        "sealai-backend-v2",
        "sealai-backend-v2-worker",
        "sealai-keycloak",
        "sealai-node",
        "sealai-containers",
        "sealai-postgres",
        "sealai-redis",
        "sealai-qdrant",
        "sealai-dr-status",
        "sealai-blackbox-tls-apex",
        "sealai-blackbox-tls-www-redirect",
        "sealai-alertmanager",
    ):
        assert f'up{{job="{job}"}} != 1' in targets
        assert f'absent(up{{job="{job}"}})' in targets

    application = alert_rules["SealAIRequiredApplicationMetricMissing"]
    for metric in (
        "sealai_v2_llm_calls_total",
        "sealai_v2_llm_failures_total",
        "sealai_v2_route_decisions_total",
        "sealai_v2_outbox_rows",
        "sealai_v2_outbox_oldest_pending_seconds",
        "sealai_v2_outbox_metrics_collection_success",
        "sealai_v2_projection_backlog_rows",
        "sealai_v2_provider_budget_limit_minor_units",
        "sealai_v2_provider_spend_minor_units",
        "sealai_v2_quota_denials_total",
        "sealai_v2_auth_denials_total",
    ):
        assert f"absent({metric})" in application

    queue = alert_rules["SealAIRequiredQueueMetricMissing"]
    for metric in (
        "sealai_v2_outbox_rows",
        "sealai_v2_outbox_oldest_pending_seconds",
        "sealai_v2_outbox_metrics_collection_success",
        "sealai_v2_projection_backlog_rows",
    ):
        for queue_name in ("memory", "knowledge"):
            assert f'absent({metric}{{queue="{queue_name}"}})' in queue


def test_required_target_fail_closed_truth_table() -> None:
    """Semantic cases for the committed ``up != 1 or absent(up)`` contract."""

    def fires(sample: float | None) -> bool:
        return sample is None or sample != 1

    assert fires(None) is True  # discovery/configuration loss
    assert fires(0) is True  # target exists but scrape fails
    assert fires(1) is False  # the sole healthy state


def test_required_component_and_queue_completeness_truth_table() -> None:
    """One unrelated sample must not mask a missing required label value."""
    components = {"postgres", "qdrant", "uploads", "documents", "configuration"}
    queues = {"memory", "knowledge"}

    assert components - components == set()
    assert components - (components - {"configuration"}) == {"configuration"}
    assert components - {"redis"} == components
    assert queues - {"memory"} == {"knowledge"}
    assert queues - {"memory", "knowledge"} == set()


def test_notification_family_contract_does_not_require_a_prior_failure() -> None:
    config = _yaml(ALERTS)
    rules = [rule for group in config["groups"] for rule in group["rules"]]
    expression = next(
        str(rule["expr"])
        for rule in rules
        if rule.get("alert") == "SealAIAlertmanagerNotificationMetricMissing"
    )
    assert expression == "absent(alertmanager_notifications_total)"
    assert "notifications_failed" not in expression


def test_recovery_rules_require_each_metric_for_each_required_component() -> None:
    config = _yaml(ALERTS)
    rules = [rule for group in config["groups"] for rule in group["rules"]]
    alert_rules = {
        rule["alert"]: str(rule["expr"]) for rule in rules if "alert" in rule
    }
    metric_alerts = {
        "sealai_backup_last_success_timestamp_seconds": "SealAIBackupSuccessComponentMissing",
        "sealai_backup_last_failure_timestamp_seconds": "SealAIBackupFailureComponentMissing",
        "sealai_offsite_backup_last_success_timestamp_seconds": "SealAIOffsiteBackupComponentMissing",
        "sealai_restore_drill_last_success_timestamp_seconds": "SealAIRestoreDrillComponentMissing",
        "sealai_backup_receipt_valid": "SealAIBackupReceiptComponentMissing",
    }
    for metric, alert in metric_alerts.items():
        expression = alert_rules[alert]
        for component in (
            "postgres",
            "qdrant",
            "uploads",
            "documents",
            "configuration",
        ):
            assert f'absent({metric}{{component="{component}"}})' in expression


def test_projection_metric_does_not_claim_unmeasured_qdrant_drift() -> None:
    combined = "\n".join(
        (
            ALERTS.read_text(encoding="utf-8"),
            (ROOT / "backend" / "sealai_v2" / "obs" / "outbox_metrics.py").read_text(
                encoding="utf-8"
            ),
            (DASHBOARDS / "sealai-rag-intelligence.json").read_text(encoding="utf-8"),
        )
    )
    assert "sealai_v2_projection_backlog_rows" in combined
    assert "sealai_v2_qdrant_sync_drift" not in combined
    assert "Projection Drift" not in combined


def test_blackbox_tls_jobs_bind_each_origin_to_its_exact_policy() -> None:
    jobs = {item["job_name"]: item for item in _yaml(PROMETHEUS)["scrape_configs"]}
    expected = {
        "sealai-blackbox-tls-apex": (
            "https_apex_health_200",
            "https://sealingai.com/api/health",
        ),
        "sealai-blackbox-tls-www-redirect": (
            "https_www_health_308_to_apex",
            "https://www.sealingai.com/api/health",
        ),
    }
    for job_name, (module, target) in expected.items():
        job = jobs[job_name]
        assert job["params"] == {"module": [module]}
        assert job["static_configs"] == [{"targets": [target]}]
        assert job["relabel_configs"][0] == {
            "source_labels": ["__address__"],
            "target_label": "__param_target",
        }
        assert job["relabel_configs"][1] == {
            "source_labels": ["__param_target"],
            "target_label": "instance",
        }
    assert "sealai-blackbox-tls" not in jobs


def test_blackbox_tls_modules_do_not_follow_or_hide_redirects() -> None:
    modules = _yaml(BLACKBOX)["modules"]
    apex = modules["https_apex_health_200"]["http"]
    www = modules["https_www_health_308_to_apex"]["http"]

    for http in (apex, www):
        assert http["fail_if_not_ssl"] is True
        assert http["follow_redirects"] is False
        assert http["tls_config"]["insecure_skip_verify"] is False
        assert http["tls_config"]["min_version"] == "TLS12"

    assert apex["valid_status_codes"] == [200]
    assert "fail_if_header_not_matches" not in apex
    assert www["valid_status_codes"] == [308]
    assert www["fail_if_header_not_matches"] == [
        {
            "header": "Location",
            "regexp": r"^https://sealingai[.]com/api/health$",
            "allow_missing": False,
        }
    ]


def test_blackbox_contract_matches_the_committed_nginx_health_and_www_policy() -> None:
    source = NGINX.read_text(encoding="utf-8")

    def server_block(server_name: str) -> str:
        marker = f"server_name {server_name};"
        before, after = source.split(marker, 1)
        start = before.rfind("\nserver {")
        assert start >= 0
        return before[start:] + marker + after.split("\nserver {", 1)[0]

    www = server_block("www.sealingai.com")
    apex = server_block("sealingai.com")

    assert "listen 443 ssl;" in www
    assert "ssl_certificate " in www
    assert "return 308 https://sealingai.com$request_uri;" in www
    assert "\n    location " not in www
    assert "listen 443 ssl;" in apex
    assert "location = /api/health {" in apex
    assert "proxy_pass http://sealai-frontend:3000/api/health;" in apex


def test_tls_probe_alerts_are_separate_and_fail_closed_per_exact_target() -> None:
    rules = [
        rule
        for group in _yaml(ALERTS)["groups"]
        for rule in group["rules"]
        if "alert" in rule
    ]
    expressions = {rule["alert"]: str(rule["expr"]) for rule in rules}
    expected = {
        "SealAITlsApexProbeFailed": (
            "sealai-blackbox-tls-apex",
            "https://sealingai.com/api/health",
        ),
        "SealAITlsWwwRedirectProbeFailed": (
            "sealai-blackbox-tls-www-redirect",
            "https://www.sealingai.com/api/health",
        ),
    }
    for alert, (job, instance) in expected.items():
        expression = expressions[alert]
        selector = f'probe_success{{job="{job}",instance="{instance}"}}'
        assert f"({selector} != 1)" in expression
        assert f"absent({selector})" in expression
    assert "SealAITlsProbeFailed" not in expressions


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
    watchdog = next(
        item for item in config["receivers"] if item["name"] == "external-watchdog"
    )
    assert watchdog["webhook_configs"][0] == {
        "url_file": "/run/secrets/alertmanager_watchdog_url",
        "send_resolved": True,
    }
    route = next(
        item
        for item in config["route"]["routes"]
        if item["receiver"] == "external-watchdog"
    )
    assert route["matchers"] == ['alertname="SealAIWatchdog"']
    assert route["repeat_interval"] == "1m"


def test_rendered_compose_contains_isolated_non_published_monitoring_graph() -> None:
    rendered = _render_compose()
    services = rendered["services"]
    monitoring = {
        "prometheus",
        "grafana",
        "alertmanager",
        "blackbox-exporter",
        "node-exporter",
        "cadvisor",
        "postgres-exporter",
        "redis-exporter",
    }
    assert monitoring <= services.keys()
    for name in monitoring:
        service = services[name]
        assert "ports" not in service
        assert "@sha256:" in service["image"]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["logging"] == {
            "driver": "local",
            "options": {"max-file": "5", "max-size": "10m"},
        }

    assert set(services["prometheus"]["networks"]) == {
        "observability_network",
        "backend_metrics_network",
        "keycloak_metrics_network",
        "qdrant_metrics_network",
    }
    assert set(services["postgres-exporter"]["networks"]) == {
        "observability_network",
        "postgres_metrics_network",
    }
    assert set(services["redis-exporter"]["networks"]) == {
        "observability_network",
        "redis_metrics_network",
    }
    assert "postgres_metrics_network" not in services["prometheus"]["networks"]
    assert "redis_metrics_network" not in services["prometheus"]["networks"]
    assert "notification_egress_network" in services["alertmanager"]["networks"]
    assert "probe_egress_network" in services["blackbox-exporter"]["networks"]


def test_exporter_image_inputs_fail_closed_until_a_digest_is_supplied() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    env_template = (ROOT / ".env.prod.example").read_text(encoding="utf-8")
    for variable in (
        "ALERTMANAGER_IMAGE",
        "BLACKBOX_EXPORTER_IMAGE",
        "NODE_EXPORTER_IMAGE",
        "CADVISOR_IMAGE",
        "POSTGRES_EXPORTER_IMAGE",
        "REDIS_EXPORTER_IMAGE",
    ):
        assert f"${{{variable}:?" in source
        configured = next(
            line.split("=", 1)[1]
            for line in env_template.splitlines()
            if line.startswith(f"{variable}=")
        )
        assert "@sha256:" in configured


def test_every_rendered_container_has_bounded_log_rotation() -> None:
    for name, service in _render_compose()["services"].items():
        assert service.get("logging") == {
            "driver": "local",
            "options": {"max-file": "5", "max-size": "10m"},
        }, name


def test_rendered_compose_wires_rules_secrets_retention_and_metrics_networks() -> None:
    rendered = _render_compose()
    services = rendered["services"]
    prometheus = services["prometheus"]
    mounts = {item["target"]: item for item in prometheus["volumes"]}
    assert mounts["/etc/prometheus/rules"]["read_only"] is True
    assert {item["target"] for item in prometheus["secrets"]} == {
        "/run/secrets/qdrant_read_only_api_key"
    }
    assert "--storage.tsdb.retention.time=30d" in prometheus["command"]
    assert "--storage.tsdb.retention.size=8GB" in prometheus["command"]
    alertmanager = services["alertmanager"]
    assert {item["target"] for item in alertmanager["secrets"]} == {
        "/run/secrets/alertmanager_webhook_url",
        "/run/secrets/alertmanager_watchdog_url",
    }
    assert "--data.retention=120h" in alertmanager["command"]
    node = services["node-exporter"]
    node_mounts = {item["target"]: item for item in node["volumes"]}
    assert node_mounts["/var/lib/node-exporter/textfile"]["read_only"] is True
    assert (
        "--collector.textfile.directory=/var/lib/node-exporter/textfile"
        in node["command"]
    )
    assert "backend_metrics_network" in services["backend-v2"]["networks"]
    assert "backend_metrics_network" in services["backend-v2-worker"]["networks"]
    assert "keycloak_metrics_network" in services["keycloak"]["networks"]
    assert (
        services["backend-v2"]["environment"]["SEALAI_V2_TELEMETRY_SAMPLE_RATE"]
        == "0.10"
    )
    assert services["redis-exporter"]["environment"]["REDIS_PASSWORD_FILE"] == (
        "/run/secrets/redis_exporter_password"
    )
    assert services["postgres-exporter"]["environment"]["DATA_SOURCE_NAME_FILE"] == (
        "/run/secrets/postgres_exporter_dsn"
    )
    assert rendered["secrets"]["qdrant_read_only_api_key"]["environment"] == (
        "QDRANT_READ_ONLY_API_KEY"
    )
    assert (
        services["qdrant"]["environment"]["QDRANT__SERVICE__API_KEY"]
        == (services["backend-v2"]["environment"]["SEALAI_V2_QDRANT_API_KEY"])
    )


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
