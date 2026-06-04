#!/usr/bin/env python3
"""Masked repository secret hygiene check.

The check intentionally reports only file paths, key/field names, and risk
classes. It never prints env values, JSON secret values, tokens, passwords, or
private keys.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

ENV_SENSITIVE_KEY_RE = re.compile(
    r"(SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CLIENT_SECRET|AUTH_SECRET)",
    re.IGNORECASE,
)
JSON_SECRET_KEYS = {
    "apikey",
    "api_key",
    "authsecret",
    "auth_secret",
    "clientsecret",
    "client_secret",
    "credentialdata",
    "password",
    "privatekey",
    "private_key",
    "secret",
    "secretdata",
}
PLACEHOLDER_RE = re.compile(
    r"^(|<[^>]+>|\\$\\{[^}]+\\}|SET_IN_SECRET_STORE|REPLACE_ME|CHANGE_ME|"
    r"YOUR_[A-Z0-9_]+|PLACEHOLDER|DUMMY|EXAMPLE|TEST|DEV|LOCAL|NOT_SET|"
    r"DISABLED|UNSET|NONE|null|false|0|\\*+)$",
    re.IGNORECASE,
)
IGNORED_DIRS = {
    ".git",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv_audit",
    "archive",
    "backups",
    "__pycache__",
    "backend/.venv",
    "frontend/.next",
    "frontend/node_modules",
    "node_modules",
}
ALLOWED_TRACKED_ENV_FILES = {
    ".env.example",
    ".env.prod.example",
    ".env.frontend.example",
    ".env.backend.example",
    ".env.keycloak.example",
    ".env.shared.example",
    "backend/.env.example",
    "langgraph_backup/.env.example",
    "strapi-backend/.env.example",
}
TRACKED_KEYCLOAK_EXPORTS = {
    "keycloak/realm-export.json",
    "keycloak/import/realm-export.json",
    "keycloak-realm-backup/sealAI-realm-export.json",
    "realm-export.json",
}


class Finding:
    def __init__(self, severity: str, path: str, detail: str) -> None:
        self.severity = severity
        self.path = path
        self.detail = detail

    def line(self) -> str:
        return f"{self.severity}: {self.path}: {self.detail}"


def git_files(*args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args, "-z"],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not proc.stdout:
        return []
    return [
        item.decode("utf-8", errors="replace")
        for item in proc.stdout.split(b"\0")
        if item
    ]


def is_env_file(path: str) -> bool:
    name = Path(path).name
    return (
        name.startswith(".env")
        or name.endswith(".env")
        or ".env." in name
        or name == "docker-compose.env"
        or name.startswith("docker-compose.env.")
    )


def is_example_env(path: str) -> bool:
    name = Path(path).name
    return (
        name.endswith(".example")
        or name.endswith(".template")
        or name.endswith(".sample")
    )


def is_ignored_path(path: str) -> bool:
    parts = Path(path).parts
    if "node_modules" in parts or "__pycache__" in parts:
        return True
    prefixes = {"/".join(parts[:idx]) for idx in range(1, len(parts) + 1)}
    return bool(prefixes & IGNORED_DIRS)


def parse_env_keys(path: Path) -> Iterable[tuple[int, str, str]]:
    for lineno, raw in enumerate(path.read_text(errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        yield lineno, key.strip().removeprefix("export "), value.strip().strip("'\"")


def check_tracked_envs(tracked: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in tracked:
        if not is_env_file(path):
            continue
        if path not in ALLOWED_TRACKED_ENV_FILES:
            findings.append(
                Finding(
                    "ERROR",
                    path,
                    "tracked env-like file is not an approved placeholder example",
                )
            )
            continue
        file_path = REPO_ROOT / path
        for lineno, key, value in parse_env_keys(file_path):
            if ENV_SENSITIVE_KEY_RE.search(key) and not PLACEHOLDER_RE.match(value):
                findings.append(
                    Finding(
                        "ERROR",
                        path,
                        f"{key} on line {lineno} does not look like a placeholder; rotate if ever real",
                    )
                )
    return findings


def check_untracked_envs() -> list[Finding]:
    findings: list[Finding] = []
    candidates = git_files("ls-files", "--others", "--ignored", "--exclude-standard")
    for path in candidates:
        if is_ignored_path(path) or not is_env_file(path):
            continue
        if is_example_env(path):
            findings.append(
                Finding(
                    "WARN",
                    path,
                    "untracked env example; verify placeholders before committing",
                )
            )
        else:
            findings.append(
                Finding(
                    "WARN",
                    path,
                    "local env/backup/rollback file; keep untracked and rotate if exposed",
                )
            )
    return findings


def placeholderish(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return bool(PLACEHOLDER_RE.match(value.strip()))


def walk_json(value: object, trail: str = "$") -> Iterable[tuple[str, str, object]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{trail}.{key}"
            yield child_path, key, child
            yield from walk_json(child, child_path)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from walk_json(child, f"{trail}[{idx}]")


def check_keycloak_exports(tracked: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(set(tracked) & TRACKED_KEYCLOAK_EXPORTS):
        file_path = REPO_ROOT / path
        raw_text = file_path.read_text(errors="replace")
        if not raw_text.strip():
            findings.append(
                Finding(
                    "WARN",
                    path,
                    "empty tracked Keycloak export; no secret fields to scan",
                )
            )
            continue
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            findings.append(Finding("ERROR", path, f"invalid JSON: {exc.msg}"))
            continue

        for json_path, key, value in walk_json(data):
            normalized_key = re.sub(r"[^a-zA-Z0-9_]", "", key).lower()
            if normalized_key not in JSON_SECRET_KEYS:
                continue
            if placeholderish(value):
                continue
            findings.append(
                Finding(
                    "ERROR",
                    path,
                    f"{json_path} may contain a live secret; value suppressed; rotation required if real",
                )
            )
    return findings


def main() -> int:
    tracked = git_files("ls-files")
    findings = [
        *check_tracked_envs(tracked),
        *check_keycloak_exports(tracked),
        *check_untracked_envs(),
    ]

    if not findings:
        print("OK: secret hygiene check found no reportable env/Auth risks.")
        return 0

    print("Masked secret hygiene findings:")
    for finding in findings:
        print(finding.line())
    print("Values are intentionally suppressed. Treat ERROR findings as blockers.")
    return 1 if any(f.severity == "ERROR" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
