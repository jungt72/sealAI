#!/usr/bin/python3
"""Fail-closed validation for a fully rendered production Compose model.

The guard is deliberately read-only. Feed it JSON from ``docker compose
config --format json``; it never invokes Docker, reads an env file, or prints
environment values.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


_DIGEST_IMAGE = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
_SCOPED_CREDENTIAL = re.compile(r"^[A-Za-z0-9._~-]{32,256}$")


class ContractInputError(ValueError):
    """Raised when the policy or rendered Compose document is malformed."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractInputError(f"{label} must be an object")
    return value


def load_json(path: Path | None) -> dict[str, Any]:
    try:
        if path is None:
            payload = json.load(sys.stdin)
        else:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractInputError("JSON input is unavailable or invalid") from exc
    return _object(payload, "JSON document")


def _network_names(service: dict[str, Any]) -> set[str]:
    networks = service.get("networks", {})
    if isinstance(networks, list):
        return {str(item) for item in networks}
    if isinstance(networks, dict):
        return {str(item) for item in networks}
    raise ContractInputError("service networks must be a list or object")


def _positive_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _normalized_ports(service: dict[str, Any]) -> set[tuple[str, int, int, str]]:
    normalized: set[tuple[str, int, int, str]] = set()
    for item in service.get("ports", []) or []:
        if not isinstance(item, dict):
            raise ContractInputError("rendered service ports must be objects")
        try:
            normalized.add(
                (
                    str(item.get("host_ip") or ""),
                    int(item["published"]),
                    int(item["target"]),
                    str(item.get("protocol") or "tcp"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractInputError("rendered service port is malformed") from exc
    return normalized


def _policy_ports(items: Any) -> set[tuple[str, int, int, str]]:
    if not isinstance(items, list):
        raise ContractInputError("allowed published ports must be arrays")
    result: set[tuple[str, int, int, str]] = set()
    for item in items:
        obj = _object(item, "allowed published port")
        try:
            result.add(
                (
                    str(obj.get("host_ip") or ""),
                    int(obj["published"]),
                    int(obj["target"]),
                    str(obj.get("protocol") or "tcp"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractInputError("allowed published port is malformed") from exc
    return result


def validate_compose(compose: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    if policy.get("schema_version") != 1 or policy.get("default_action") != "deny":
        raise ContractInputError(
            "policy must use schema_version=1 and default_action=deny"
        )

    services = _object(compose.get("services"), "compose services")
    expected = _object(policy.get("services"), "policy services")
    allowed_cap_add = _object(policy.get("allowed_cap_add"), "policy allowed_cap_add")
    required_users = _object(policy.get("required_users"), "policy required_users")
    errors: list[str] = []

    missing = sorted(set(expected) - set(services))
    unexpected = sorted(set(services) - set(expected))
    if missing:
        errors.append("missing policy services: " + ",".join(missing))
    if unexpected:
        errors.append(
            "services absent from deny-by-default policy: " + ",".join(unexpected)
        )

    service_networks: dict[str, set[str]] = {}
    forbidden = {str(item) for item in policy.get("forbidden_network_names", [])}
    for name in sorted(set(expected) & set(services)):
        service = _object(services[name], f"service {name}")
        actual_networks = _network_names(service)
        service_networks[name] = actual_networks
        wanted = {str(item) for item in expected[name]}
        if actual_networks != wanted:
            errors.append(f"{name}: network membership differs from policy")
        if actual_networks & forbidden:
            errors.append(f"{name}: forbidden flat network attached")

        image = service.get("image")
        if not isinstance(image, str) or not _DIGEST_IMAGE.fullmatch(image):
            errors.append(f"{name}: image is not pinned to an immutable sha256 digest")
        if service.get("restart") != "unless-stopped":
            errors.append(f"{name}: restart policy is not unless-stopped")
        if service.get("read_only") is not True:
            errors.append(f"{name}: root filesystem is not read-only")
        security_opt = {str(item) for item in service.get("security_opt", []) or []}
        if security_opt != {"no-new-privileges:true"}:
            errors.append(f"{name}: security options differ from the hardened policy")
        cap_drop = {str(item).upper() for item in service.get("cap_drop", []) or []}
        if "ALL" not in cap_drop:
            errors.append(f"{name}: cap_drop ALL is missing")
        actual_cap_add = {
            str(item).upper() for item in service.get("cap_add", []) or []
        }
        wanted_cap_add = {str(item).upper() for item in allowed_cap_add.get(name, [])}
        if actual_cap_add != wanted_cap_add:
            errors.append(f"{name}: added capabilities differ from policy")
        if service.get("privileged") is True:
            errors.append(f"{name}: privileged mode is forbidden")
        for field in ("network_mode", "pid", "ipc", "uts"):
            if service.get(field):
                errors.append(f"{name}: host namespace override {field} is forbidden")
        if service.get("devices"):
            errors.append(f"{name}: device passthrough is forbidden")
        wanted_user = required_users.get(name)
        if wanted_user is not None and str(service.get("user") or "") != str(
            wanted_user
        ):
            errors.append(f"{name}: runtime identity differs from policy")
        for field in ("pids_limit", "mem_limit", "cpus"):
            if not _positive_number(service.get(field)):
                errors.append(f"{name}: {field} is missing or not positive")
        logging = service.get("logging")
        if not isinstance(logging, dict) or logging.get("driver") != "local":
            errors.append(f"{name}: bounded local logging driver is missing")
        else:
            options = logging.get("options")
            if (
                not isinstance(options, dict)
                or not options.get("max-size")
                or not options.get("max-file")
            ):
                errors.append(f"{name}: log rotation bounds are incomplete")

    for pair in policy.get("denied_reachability", []):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ContractInputError(
                "denied_reachability entries must be two-item arrays"
            )
        left, right = (str(pair[0]), str(pair[1]))
        shared = service_networks.get(left, set()) & service_networks.get(right, set())
        if shared:
            errors.append(f"{left}->{right}: denied path shares a network")

    networks = _object(compose.get("networks"), "compose networks")
    for name in policy.get("internal_networks", []):
        network = networks.get(str(name))
        if not isinstance(network, dict) or network.get("internal") is not True:
            errors.append(f"{name}: service-only network is not internal")
    external = _object(policy.get("external_networks"), "policy external_networks")
    for name in external:
        network = networks.get(name)
        if not isinstance(network, dict) or network.get("external") is not True:
            errors.append(f"{name}: scoped cross-project network is not external")
        elif network.get("name") in forbidden:
            errors.append(f"{name}: external network resolves to a forbidden flat name")

    allowed_ports = _object(
        policy.get("allowed_published_ports"), "policy allowed_published_ports"
    )
    for name, service in services.items():
        obj = _object(service, f"service {name}")
        actual = _normalized_ports(obj)
        wanted = _policy_ports(allowed_ports.get(name, []))
        if actual != wanted:
            errors.append(f"{name}: published ports differ from policy")

    qdrant_env = _object(
        services.get("qdrant", {}).get("environment"), "qdrant environment"
    )
    backend_env = _object(
        services.get("backend-v2", {}).get("environment"), "backend-v2 environment"
    )
    qdrant_key = qdrant_env.get("QDRANT__SERVICE__API_KEY")
    backend_key = backend_env.get("SEALAI_V2_QDRANT_API_KEY")
    if not isinstance(qdrant_key, str) or not _SCOPED_CREDENTIAL.fullmatch(qdrant_key):
        errors.append("qdrant: API-key authentication is not configured")
    if not isinstance(backend_key, str) or not _SCOPED_CREDENTIAL.fullmatch(
        backend_key
    ):
        errors.append("backend-v2: Qdrant client credential is not configured")
    if qdrant_key and backend_key and qdrant_key != backend_key:
        errors.append("qdrant/backend-v2: Qdrant credential binding differs")

    grafana_env = _object(
        services.get("grafana", {}).get("environment"), "grafana environment"
    )
    grafana_password = grafana_env.get("GF_SECURITY_ADMIN_PASSWORD")
    if not isinstance(grafana_password, str) or not _SCOPED_CREDENTIAL.fullmatch(
        grafana_password
    ):
        errors.append("grafana: scoped administrator credential is not configured")

    return sorted(set(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument(
        "--compose-json",
        type=Path,
        help="rendered Compose JSON; omit to read it from stdin",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        policy = load_json(args.policy)
        compose = load_json(args.compose_json)
        errors = validate_compose(compose, policy)
    except ContractInputError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, sort_keys=True))
        return 3
    if errors:
        print(json.dumps({"status": "blocked", "errors": errors}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {"status": "pass", "services_checked": len(policy["services"])},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
