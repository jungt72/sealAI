#!/usr/bin/env python3
"""Rehearse the committed Alertmanager route against an isolated local receiver."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

_MAX_WEBHOOK_BYTES = 1_000_000


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class _Receiver(BaseHTTPRequestHandler):
    events: queue.Queue[dict] = queue.Queue()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= _MAX_WEBHOOK_BYTES:
            self.send_error(413)
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400)
            return
        if not isinstance(payload, dict):
            self.send_error(400)
            return
        self.events.put(payload)
        self.send_response(200)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _wait_ready(
    url: str, process: subprocess.Popen[str], timeout: float = 15.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"alertmanager exited before readiness: stdout={stdout!r} stderr={stderr!r}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:  # noqa: S310 - loopback only
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    raise TimeoutError("alertmanager did not become ready")


def _post_alert(api_url: str, *, resolved: bool) -> None:
    now = datetime.now(timezone.utc)
    payload = [
        {
            "labels": {
                "alertname": "SealAISyntheticRouteVerification",
                "severity": "warning",
                "category": "synthetic",
            },
            "annotations": {"summary": "Synthetic redacted route verification"},
            "startsAt": _iso(now - timedelta(minutes=1)),
            "endsAt": _iso(
                now - timedelta(seconds=1) if resolved else now + timedelta(minutes=10)
            ),
            "generatorURL": "http://127.0.0.1/synthetic",
        }
    ]
    request = urllib.request.Request(  # noqa: S310 - loopback only
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3.0) as response:  # noqa: S310 - loopback only
        if response.status != 200:
            raise RuntimeError(f"alert API returned HTTP {response.status}")


def _wait_webhook(status: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event = _Receiver.events.get(timeout=max(0.1, deadline - time.monotonic()))
        except queue.Empty:
            break
        if event.get("status") == status:
            return event
    raise TimeoutError(f"no {status!r} webhook arrived")


def _write_private(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _runtime_config(source: Path, target: Path, webhook_file: Path) -> str:
    source_bytes = source.read_bytes()
    config = yaml.safe_load(source_bytes)
    config["route"]["group_wait"] = "1s"
    config["route"]["group_interval"] = "1s"
    root_receiver_found = False
    for receiver in config["receivers"]:
        if receiver["name"] == config["route"]["receiver"]:
            root_receiver_found = True
        # The rehearsal is hermetic: every configured webhook points at the
        # private loopback receiver so added routes never require production
        # secret files or contact external systems during config loading.
        for webhook in receiver.get("webhook_configs", []):
            webhook["url_file"] = str(webhook_file)
    if not root_receiver_found:
        raise ValueError("root Alertmanager receiver is not configured")
    _write_private(target, yaml.safe_dump(config, sort_keys=False))
    return hashlib.sha256(source_bytes).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alertmanager-bin", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("monitoring/alertmanager.yml"),
    )
    args = parser.parse_args(argv)
    binary = args.alertmanager_bin.resolve(strict=True)
    source_config = args.config.resolve(strict=True)

    alert_port = _free_port()
    receiver_port = _free_port()
    receiver = ThreadingHTTPServer(("127.0.0.1", receiver_port), _Receiver)
    receiver_thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    receiver_thread.start()

    process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="sealai-alert-route-") as raw_dir:
            directory = Path(raw_dir)
            webhook_file = directory / "webhook-url"
            config_file = directory / "alertmanager.yml"
            _write_private(webhook_file, f"http://127.0.0.1:{receiver_port}/alerts\n")
            config_sha256 = _runtime_config(source_config, config_file, webhook_file)
            process = subprocess.Popen(
                [
                    str(binary),
                    f"--config.file={config_file}",
                    f"--storage.path={directory / 'data'}",
                    f"--web.listen-address=127.0.0.1:{alert_port}",
                    "--cluster.listen-address=",
                    "--log.level=error",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            base_url = f"http://127.0.0.1:{alert_port}"
            _wait_ready(f"{base_url}/-/ready", process)
            _post_alert(f"{base_url}/api/v2/alerts", resolved=False)
            firing = _wait_webhook("firing")
            _post_alert(f"{base_url}/api/v2/alerts", resolved=True)
            resolved = _wait_webhook("resolved")

            for event in (firing, resolved):
                if event.get("receiver") != "external-primary":
                    raise RuntimeError("synthetic alert reached an unexpected receiver")
                alerts = event.get("alerts") or []
                if not any(
                    alert.get("labels", {}).get("alertname")
                    == "SealAISyntheticRouteVerification"
                    for alert in alerts
                ):
                    raise RuntimeError("synthetic alert identity was not preserved")

            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "PASS",
                        "config_sha256": config_sha256,
                        "receiver": "external-primary",
                        "firing_receipt": True,
                        "resolved_receipt": True,
                        "network_scope": "loopback_only",
                    },
                    sort_keys=True,
                )
            )
    finally:
        receiver.shutdown()
        receiver.server_close()
        receiver_thread.join(timeout=2.0)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
