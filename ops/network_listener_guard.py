#!/usr/bin/python3
"""Observe host TCP/UDP listeners against a fail-closed allowlist.

There is intentionally no enforcement or firewall-apply mode. The command
invokes ``ss`` without process details, applies a fixed timeout, and reports
only listener coordinates needed to diagnose drift.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ObservationError(ValueError):
    """Raised for invalid policy, invalid input, or failed observation."""


@dataclass(frozen=True, order=True)
class Listener:
    protocol: str
    address: str
    port: int
    scope: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "protocol": self.protocol,
            "address": self.address,
            "port": self.port,
            "scope": self.scope,
        }


def _load_policy(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            policy = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservationError("listener policy is unavailable or invalid") from exc
    if not isinstance(policy, dict):
        raise ObservationError("listener policy must be an object")
    if policy.get("schema_version") != 1 or policy.get("default_action") != "deny":
        raise ObservationError(
            "listener policy must be schema_version=1/default_action=deny"
        )
    for scope in ("wildcard", "loopback"):
        value = policy.get(scope)
        if not isinstance(value, dict):
            raise ObservationError(f"listener policy {scope} must be an object")
        for protocol in ("tcp", "udp"):
            ports = value.get(protocol)
            if not isinstance(ports, list) or not all(
                isinstance(port, int)
                and not isinstance(port, bool)
                and 0 < port < 65536
                for port in ports
            ):
                raise ObservationError(f"listener policy {scope}.{protocol} is invalid")
    if not isinstance(policy.get("exact"), list):
        raise ObservationError("listener policy exact must be an array")
    return policy


def _split_endpoint(endpoint: str) -> tuple[str, int]:
    value = endpoint.strip()
    if value.startswith("["):
        end = value.find("]")
        if end <= 0 or end + 2 > len(value) or value[end + 1] != ":":
            raise ObservationError("ss endpoint is malformed")
        address, port_text = value[1:end], value[end + 2 :]
    else:
        try:
            address, port_text = value.rsplit(":", 1)
        except ValueError as exc:
            raise ObservationError("ss endpoint is malformed") from exc
    if "%" in address:
        address = address.split("%", 1)[0]
    if address == "*":
        address = "0.0.0.0"
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ObservationError("ss listener port is not numeric") from exc
    if not 0 < port < 65536:
        raise ObservationError("ss listener port is out of range")
    return address, port


def _scope(address: str) -> tuple[str, str]:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ObservationError("ss listener address is not an IP address") from exc
    if ip.is_unspecified:
        return "wildcard", ip.compressed
    if ip.is_loopback:
        return "loopback", ip.compressed
    return "explicit", ip.compressed


def parse_ss(output: str) -> list[Listener]:
    listeners: set[Listener] = set()
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) < 6:
            raise ObservationError("ss output row has too few fields")
        protocol = fields[0].lower()
        if protocol.startswith("tcp"):
            protocol = "tcp"
        elif protocol.startswith("udp"):
            protocol = "udp"
        else:
            raise ObservationError("ss output contains an unsupported protocol")
        address, port = _split_endpoint(fields[4])
        scope, normalized = _scope(address)
        listeners.add(Listener(protocol, normalized, port, scope))
    return sorted(listeners)


def observe(timeout_seconds: float) -> str:
    if not 0 < timeout_seconds <= 30:
        raise ObservationError("timeout must be within (0,30] seconds")
    try:
        completed = subprocess.run(
            ["ss", "-H", "-lntu"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ObservationError("listener observation failed or timed out") from exc
    if completed.returncode != 0:
        raise ObservationError("listener observation returned a non-zero status")
    return completed.stdout


def unexpected_listeners(
    listeners: list[Listener], policy: dict[str, Any]
) -> list[Listener]:
    scoped: dict[str, dict[str, set[int]]] = {}
    for scope in ("wildcard", "loopback"):
        scoped[scope] = {
            protocol: {int(port) for port in policy[scope][protocol]}
            for protocol in ("tcp", "udp")
        }
    exact: set[tuple[str, str, int]] = set()
    for item in policy["exact"]:
        if not isinstance(item, dict):
            raise ObservationError("listener policy exact entry must be an object")
        try:
            protocol = str(item["protocol"]).lower()
            address = ipaddress.ip_address(str(item["address"])).compressed
            port = int(item["port"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ObservationError("listener policy exact entry is invalid") from exc
        if protocol not in {"tcp", "udp"} or not 0 < port < 65536:
            raise ObservationError("listener policy exact entry is invalid")
        exact.add((protocol, address, port))

    unexpected: list[Listener] = []
    for listener in listeners:
        if (listener.protocol, listener.address, listener.port) in exact:
            continue
        if (
            listener.scope in scoped
            and listener.port in scoped[listener.scope][listener.protocol]
        ):
            continue
        unexpected.append(listener)
    return unexpected


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument(
        "--input",
        type=Path,
        help="read a captured ss fixture instead of observing the host",
    )
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--mode", choices=("observe",), default="observe")
    return parser


def main() -> int:
    args = _parser().parse_args()
    os.umask(0o077)
    try:
        policy = _load_policy(args.policy)
        if args.input is None:
            raw = observe(args.timeout_seconds)
        else:
            raw = args.input.read_text(encoding="utf-8")
        listeners = parse_ss(raw)
        unexpected = unexpected_listeners(listeners, policy)
    except (OSError, ObservationError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, sort_keys=True))
        return 3
    if unexpected:
        print(
            json.dumps(
                {
                    "status": "drift",
                    "unexpected": [item.as_dict() for item in unexpected],
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {"status": "pass", "listeners_checked": len(listeners)}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
