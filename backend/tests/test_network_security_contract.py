from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
COMPOSE_GUARD_PATH = REPO / "ops" / "compose_security_guard.py"
LISTENER_GUARD_PATH = REPO / "ops" / "network_listener_guard.py"
TOPOLOGY_POLICY_PATH = REPO / "ops" / "network_topology_policy.json"
LISTENER_POLICY_PATH = REPO / "ops" / "listener_allowlist.json"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _topology_policy() -> dict:
    return json.loads(TOPOLOGY_POLICY_PATH.read_text(encoding="utf-8"))


def _listener_policy() -> dict:
    return json.loads(LISTENER_POLICY_PATH.read_text(encoding="utf-8"))


def _secure_rendered_compose() -> dict:
    policy = _topology_policy()
    services = {}
    for index, (name, networks) in enumerate(policy["services"].items(), start=1):
        service = {
            "image": f"registry.invalid/{name}@sha256:{index:064x}",
            "restart": "unless-stopped",
            "read_only": True,
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "pids_limit": 128,
            "mem_limit": 512 * 1024 * 1024,
            "cpus": 1.0,
            "logging": {
                "driver": "local",
                "options": {"max-size": "10m", "max-file": "5"},
            },
            "networks": {network: None for network in networks},
        }
        allowed_cap_add = policy["allowed_cap_add"].get(name, [])
        if allowed_cap_add:
            service["cap_add"] = allowed_cap_add
        required_user = policy["required_users"].get(name)
        if required_user:
            service["user"] = required_user
        allowed = policy["allowed_published_ports"].get(name, [])
        if allowed:
            service["ports"] = allowed
        services[name] = service
    services["qdrant"]["environment"] = {
        "QDRANT__SERVICE__API_KEY": "DUMMY_QDRANT_KEY_WITH_32_CHARS_000"
    }
    services["backend-v2"]["environment"] = {
        "SEALAI_V2_QDRANT_API_KEY": "DUMMY_QDRANT_KEY_WITH_32_CHARS_000"
    }
    services["grafana"]["environment"] = {
        "GF_SECURITY_ADMIN_PASSWORD": "DUMMY_GRAFANA_PASSWORD_WITH_32_CHARS"
    }
    networks = {name: {"name": f"test_{name}"} for name in policy["internal_networks"]}
    for name in policy["internal_networks"]:
        networks[name]["internal"] = True
    networks["strapi_postgres_network"] = {
        "external": True,
        "name": "sealai_strapi_postgres_scoped",
    }
    for name in (
        "edge_network",
        "frontend_egress_network",
        "backend_egress_network",
        "keycloak_egress_network",
    ):
        networks[name] = {"name": f"test_{name}"}
    return {"services": services, "networks": networks}


def test_compose_guard_accepts_exact_least_privilege_model() -> None:
    guard = _load(COMPOSE_GUARD_PATH, "compose_security_guard_pass")
    assert guard.validate_compose(_secure_rendered_compose(), _topology_policy()) == []


@pytest.mark.parametrize(
    ("mutate", "reason"),
    (
        (
            lambda model: model["services"]["nginx"]["networks"].update(
                {"postgres_backend_network": None}
            ),
            "nginx->postgres: denied path shares a network",
        ),
        (
            lambda model: model["services"]["backend-v2"].update(
                {"image": "registry.invalid/backend-v2:latest"}
            ),
            "backend-v2: image is not pinned to an immutable sha256 digest",
        ),
        (
            lambda model: model["services"]["backend-v2"].pop("pids_limit"),
            "backend-v2: pids_limit is missing or not positive",
        ),
        (
            lambda model: model["services"]["backend-v2"].update(
                {
                    "ports": [
                        {
                            "host_ip": "0.0.0.0",
                            "published": 8001,
                            "target": 8001,
                            "protocol": "tcp",
                        }
                    ]
                }
            ),
            "backend-v2: published ports differ from policy",
        ),
        (
            lambda model: model["services"]["qdrant"]["environment"].update(
                {"QDRANT__SERVICE__API_KEY": "different-key"}
            ),
            "qdrant/backend-v2: Qdrant credential binding differs",
        ),
        (
            lambda model: model["services"]["backend-v2"].update(
                {"cap_add": ["SYS_ADMIN"]}
            ),
            "backend-v2: added capabilities differ from policy",
        ),
        (
            lambda model: model["services"]["qdrant"].update({"privileged": True}),
            "qdrant: privileged mode is forbidden",
        ),
        (
            lambda model: model["networks"]["strapi_postgres_network"].update(
                {"name": "sealai_default"}
            ),
            "strapi_postgres_network: external network resolves to a forbidden flat name",
        ),
    ),
)
def test_compose_guard_fails_closed(mutate, reason: str) -> None:
    guard = _load(COMPOSE_GUARD_PATH, f"compose_security_guard_{reason[:8]}")
    model = _secure_rendered_compose()
    mutate(model)
    assert reason in guard.validate_compose(model, _topology_policy())


def test_compose_guard_rejects_service_missing_from_policy() -> None:
    guard = _load(COMPOSE_GUARD_PATH, "compose_security_guard_unknown")
    model = _secure_rendered_compose()
    model["services"]["surprise-admin"] = model["services"]["grafana"].copy()
    errors = guard.validate_compose(model, _topology_policy())
    assert "services absent from deny-by-default policy: surprise-admin" in errors


def test_listener_allowlist_accepts_only_documented_bindings() -> None:
    guard = _load(LISTENER_GUARD_PATH, "network_listener_guard_pass")
    observed = guard.parse_ss(
        "\n".join(
            (
                "tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*",
                "tcp LISTEN 0 4096 *:80 *:*",
                "tcp LISTEN 0 4096 [::]:443 [::]:*",
                "tcp LISTEN 0 4096 127.0.0.1:3001 0.0.0.0:*",
                "udp UNCONN 0 0 127.0.0.53%lo:53 0.0.0.0:*",
            )
        )
    )
    assert guard.unexpected_listeners(observed, _listener_policy()) == []


@pytest.mark.parametrize("port", (3002, 3003, 3100, 8443))
def test_listener_allowlist_rejects_unexpected_wildcard_listener(port: int) -> None:
    guard = _load(LISTENER_GUARD_PATH, f"network_listener_guard_{port}")
    observed = guard.parse_ss(f"tcp LISTEN 0 4096 0.0.0.0:{port} 0.0.0.0:*\n")
    unexpected = guard.unexpected_listeners(observed, _listener_policy())
    assert len(unexpected) == 1
    assert unexpected[0].scope == "wildcard"
    assert unexpected[0].port == port


def test_listener_allowlist_rejects_specific_non_loopback_binding() -> None:
    guard = _load(LISTENER_GUARD_PATH, "network_listener_guard_explicit")
    observed = guard.parse_ss("tcp LISTEN 0 4096 192.0.2.10:443 0.0.0.0:*\n")
    unexpected = guard.unexpected_listeners(observed, _listener_policy())
    assert [item.scope for item in unexpected] == ["explicit"]


@pytest.mark.parametrize(
    "line",
    (
        "tcp LISTEN 0 4096 not-an-ip:443 0.0.0.0:*",
        "tcp LISTEN 0 4096 0.0.0.0:http 0.0.0.0:*",
        "unix LISTEN 0 4096 /run/socket * 0",
    ),
)
def test_listener_parser_rejects_ambiguous_input(line: str) -> None:
    guard = _load(LISTENER_GUARD_PATH, "network_listener_guard_invalid")
    with pytest.raises(guard.ObservationError):
        guard.parse_ss(line)


def test_listener_guard_and_timer_are_observation_only() -> None:
    guard = LISTENER_GUARD_PATH.read_text(encoding="utf-8")
    service = (REPO / "ops" / "systemd" / "sealai-listener-guard.service").read_text(
        encoding="utf-8"
    )
    timer = (REPO / "ops" / "systemd" / "sealai-listener-guard.timer").read_text(
        encoding="utf-8"
    )
    assert 'choices=("observe",)' in guard
    assert '["ss", "-H", "-lntu"]' in guard
    assert "shell=True" not in guard
    for mutator in ("iptables", "nft", "ufw", "docker network"):
        assert mutator not in guard
    assert "--mode observe" in service
    assert "CapabilityBoundingSet=" in service
    assert "User=nobody" in service
    assert "/usr/local/libexec/sealai/network-listener-guard.py" in service
    assert "/etc/sealai/listener-allowlist.json" in service
    assert "/home/" not in service
    assert "ProtectHome=true" in service
    assert "OnUnitActiveSec=5min" in timer


def _compose_test_environment() -> dict[str, str]:
    source = "\n".join(
        (REPO / name).read_text(encoding="utf-8")
        for name in ("docker-compose.yml", "docker-compose.deploy.yml")
    )
    required = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?[^}]*}", source))
    environment: dict[str, str] = {}
    for index, key in enumerate(sorted(required), start=1):
        if key.endswith("_IMAGE"):
            environment[key] = f"registry.invalid/{key.lower()}@sha256:{index:064x}"
        elif key.endswith("_MEMORY_LIMIT"):
            environment[key] = "512m"
        elif key.endswith("_CPU_LIMIT"):
            environment[key] = "1.0"
        elif key.endswith("_PIDS_LIMIT"):
            environment[key] = "128"
        elif key == "STRAPI_POSTGRES_NETWORK_NAME":
            environment[key] = "sealai_strapi_postgres_scoped"
        elif key == "QDRANT_API_KEY":
            environment[key] = "DUMMY_QDRANT_KEY_WITH_32_CHARS_000"
        elif key == "GRAFANA_ADMIN_PASSWORD":
            environment[key] = "DUMMY_GRAFANA_PASSWORD_WITH_32_CHARS"
        else:
            environment[key] = f"DUMMY_{key}"
    return environment


def test_rendered_production_compose_satisfies_security_guard() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker CLI unavailable; unit-level contract remains covered")
    version = subprocess.run(
        [docker, "compose", "version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if version.returncode != 0:
        pytest.skip("docker compose unavailable; unit-level contract remains covered")
    completed = subprocess.run(
        [
            docker,
            "compose",
            "-f",
            str(REPO / "docker-compose.yml"),
            "-f",
            str(REPO / "docker-compose.deploy.yml"),
            "--profile",
            "v2",
            "--profile",
            "frontend-container",
            "--profile",
            "observability",
            "config",
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=_compose_test_environment(),
    )
    assert completed.returncode == 0, completed.stderr
    rendered = json.loads(completed.stdout)
    guard = _load(COMPOSE_GUARD_PATH, "compose_security_guard_rendered")
    assert guard.validate_compose(rendered, _topology_policy()) == []


def test_foreign_compose_projects_never_join_flat_production_network() -> None:
    biz = (REPO / "docker-compose.biz.yml").read_text(encoding="utf-8")
    paperless = (REPO / "paperless" / "docker-compose.yml").read_text(encoding="utf-8")
    assert "sealai_default" not in biz
    assert "sealai_default" not in paperless
    assert "STRAPI_POSTGRES_NETWORK_NAME" in biz
    assert "paperless_internal" in paperless
    assert "container_name:" not in paperless


def test_compose_source_requires_separate_data_credentials() -> None:
    base = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    deploy = (REPO / "docker-compose.deploy.yml").read_text(encoding="utf-8")
    assert "QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY:?" in deploy
    assert "SEALAI_V2_QDRANT_API_KEY: ${QDRANT_API_KEY:?" in deploy
    assert "${KC_DB_PASSWORD:?" in deploy
    assert "${SEALAI_V2_DB_PASSWORD:?" in deploy
    assert "KCRAW_DB_PASSWORD: ${POSTGRES_PASSWORD" not in deploy
    assert "SEALAI_V2_DATABASE_URL: postgresql+psycopg2://${POSTGRES_USER" not in deploy
    assert "POSTGRES_IMAGE required" not in base
    assert "QDRANT_API_KEY required" not in base


def test_all_sanctioned_production_compose_paths_call_security_guard() -> None:
    validator = (REPO / "ops" / "validate-production-compose-security.sh").read_text(
        encoding="utf-8"
    )
    assert "config --format json" in validator
    assert "compose_security_guard.py" in validator
    assert "--profile observability" in validator
    assert "docker compose" in validator
    assert "LIVE_PRODUCTION_ENV=/home/thorsten/sealai/.env.prod" in validator
    assert "STAGED_RELEASE_ROOT=/var/lib/sealai/release-control/releases" in validator
    assert "[0-9a-f]{40}" in validator
    for relative in (
        "ops/up-prod.sh",
        "ops/release-backend-v2.sh",
        "ops/release-frontend.sh",
        "ops/keycloak_recover_admin.sh",
    ):
        script = (REPO / relative).read_text(encoding="utf-8")
        assert "validate-production-compose-security.sh" in script


def test_marketing_frontend_release_has_no_mutable_image_fallback() -> None:
    script = (REPO / "ops" / "release-frontend.sh").read_text(encoding="utf-8")
    assert "ALLOW_LOCAL_FRONTEND_IMAGE_FALLBACK" not in script
    assert 'FRONTEND_PULL_POLICY="never"' not in script
    assert "mutable/local production image fallbacks are forbidden" in script


def test_env_gate_covers_every_mutable_production_image_input() -> None:
    script = (REPO / "ops" / "check-env-drift.sh").read_text(encoding="utf-8")
    for key in (
        "BACKEND_V2_IMAGE",
        "KEYCLOAK_IMAGE",
        "FRONTEND_IMAGE",
        "NGINX_IMAGE",
        "POSTGRES_IMAGE",
        "REDIS_IMAGE",
        "QDRANT_IMAGE",
        "GOTENBERG_IMAGE",
        "TIKA_IMAGE",
    ):
        assert key in script
    assert "@sha256:[0-9a-f]{64}" in script
