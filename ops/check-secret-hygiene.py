#!/usr/bin/env python3
"""Fail-closed, value-redacting repository secret scanner.

The worktree scan reads tracked and non-ignored candidate files; ignored local
runtime env/backup files are never opened. Index/tree/range modes read immutable
Git blobs. Findings contain rule IDs, paths, line numbers, and sources only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator


REPO_ROOT = Path(__file__).resolve().parents[1]

ENV_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|_)(?:SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CLIENT_SECRET|AUTH_SECRET)(?:$|_)",
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
    "passwd",
    "privatekey",
    "private_key",
    "secret",
    "secretdata",
    "token",
    "access_token",
}
PLACEHOLDER_RE = re.compile(
    r"^(?:|<[^>]+>|\$\{[^}]+\}|\$\$\{[^}]+\}|"
    r"SET_IN_SECRET_STORE|INJECT_AT_RUNTIME|REPLACE_ME|CHANGE[-_]?ME(?:[-_.][A-Z0-9]+)*|"
    r"YOUR_[A-Z0-9_]+|PLACEHOLDER|DUMMY(?:_[A-Z0-9_]+)*|"
    r"EXAMPLE|TEST|FAKE|MOCK|"
    r"DEV|LOCAL|"
    r"NOT_SET|DISABLED|UNSET|NONE|NULL|FALSE|0|\*+)$",
    re.IGNORECASE,
)

PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.IGNORECASE,
)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\b")
BEARER_RE = re.compile(
    r"\bbearer\s+[A-Za-z0-9._~+/=-]{16,}",
    re.IGNORECASE,
)
PROVIDER_TOKEN_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
CONNECTION_RE = re.compile(
    r"\b(?:postgres(?:ql)?|redis|rediss|mysql|mariadb|mongodb(?:\+srv)?|"
    r"amqp|amqps|https?)://([^:\s/@]+):([^@\s/]+)@",
    re.IGNORECASE,
)
ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+)?[\"']?([A-Za-z_][A-Za-z0-9_.-]*)[\"']?" r"\s*[:=]\s*(.*?)\s*$"
)
SQL_DATA_DUMP_RE = re.compile(r"^COPY\s+.+\s+FROM\s+stdin;\s*$", re.MULTILINE)

ZERO_OID_RE = re.compile(r"^0+$")


class ScannerError(RuntimeError):
    """A scanner/runtime error that must fail the gate closed."""


class Finding:
    def __init__(
        self,
        rule: str,
        path: str,
        *,
        source: str,
        line_number: int | None = None,
    ) -> None:
        self.rule = rule
        self.path = path
        self.source = source
        self.line_number = line_number

    def line(self) -> str:
        location = f" line={self.line_number}" if self.line_number is not None else ""
        return (
            f"ERROR rule={self.rule} path={self.path}{location} "
            f"source={self.source} value=[REDACTED]"
        )

    def sort_key(self) -> tuple[str, str, int, str]:
        return (self.path, self.rule, self.line_number or 0, self.source)

    def identity(self) -> tuple[str, str, int | None, str]:
        return (self.rule, self.path, self.line_number, self.source)


def run_git(*args: str) -> bytes:
    process = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        safe_command = " ".join(args[:2])
        raise ScannerError(
            f"git operation failed ({safe_command}); output intentionally suppressed"
        )
    return process.stdout


def nul_items(raw: bytes) -> list[str]:
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in raw.split(b"\0")
        if item
    ]


def is_env_file(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return (
        name.startswith(".env")
        or name.endswith(".env")
        or ".env." in name
        or name == "docker-compose.env"
        or name.startswith("docker-compose.env.")
    )


def is_example_env(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return name.endswith((".example", ".sample", ".template"))


def placeholderish(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return bool(PLACEHOLDER_RE.fullmatch(value.strip()))


def normalized_scalar(raw: str) -> str:
    value = raw.strip().rstrip(",").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def secretish_scalar(value: object) -> bool:
    if not isinstance(value, str):
        return False
    candidate = normalized_scalar(value)
    if placeholderish(candidate) or len(candidate) < 8:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._~+/=@:$%!-]+", candidate))


def private_jwk_scalar(value: object) -> bool:
    if not isinstance(value, str):
        return False
    candidate = normalized_scalar(value)
    return bool(candidate) and not placeholderish(candidate)


def assignment_scalar(path: str, raw_value: str) -> str | None:
    """Return only literal/config scalars, never code expressions."""

    stripped = raw_value.strip().rstrip(",;").strip()
    suffix = PurePosixPath(path).suffix.lower()
    config_like = (
        is_env_file(path)
        or suffix
        in {
            ".cfg",
            ".conf",
            ".http",
            ".ini",
            ".log",
            ".md",
            ".properties",
            ".service",
            ".txt",
            ".toml",
            ".yaml",
            ".yml",
        }
        or suffix in {".sh", ".bash", ".zsh"}
        or PurePosixPath(path).name.lower() in {"dockerfile", "containerfile"}
    )
    if config_like:
        return normalized_scalar(stripped)
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1].strip()
    return None


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def filename_findings(path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    pure_path = PurePosixPath(path)
    name = pure_path.name.lower()
    lowered = path.lower()
    suffixes = [suffix.lower() for suffix in pure_path.suffixes]

    if is_env_file(path) and not is_example_env(path):
        findings.append(Finding("filename.env", path, source=source))

    private_name = (
        name.endswith((".key", ".p8", ".private.pem"))
        or name in {"key.pem", "private_key.json", "id_rsa", "id_ed25519"}
        or name.startswith(("id_rsa.", "id_ed25519."))
        or ("private" in name and name.endswith((".jwk", ".json", ".pem")))
    )
    if private_name:
        findings.append(Finding("filename.private-key", path, source=source))

    dump_name = name.endswith(
        (".dump", ".pgdump", ".rdb", ".aof", ".sql.gz", ".sql.bz2", ".sql.xz")
    ) or (
        ("backup" in lowered or "dump" in lowered or "export" in lowered)
        and bool(set(suffixes) & {".sql", ".dump", ".pgdump", ".rdb", ".aof"})
    )
    if dump_name:
        findings.append(Finding("filename.database-dump", path, source=source))

    diagnostic_auth_capture = (
        ("/live/" in f"/{lowered}" or "debug" in lowered)
        and any(marker in name for marker in ("auth", "token", "credential"))
        and name.endswith((".txt", ".log", ".json", ".http"))
    )
    if diagnostic_auth_capture:
        findings.append(Finding("filename.auth-capture", path, source=source))

    return findings


def walk_json(value: object) -> Iterator[tuple[str, object]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def json_findings(path: str, text: str, source: str) -> list[Finding]:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return []
    try:
        document = json.loads(stripped)
    except (json.JSONDecodeError, RecursionError):
        return []

    findings: list[Finding] = []
    values: Iterable[object]
    if isinstance(document, list):
        values = document
    else:
        values = (document,)

    stack = list(values)
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "kty" in current and private_jwk_scalar(current.get("d")):
                findings.append(
                    Finding("content.private-jwk", path, source=source, line_number=1)
                )
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)

    for key, child in walk_json(document):
        normalized = re.sub(r"[^a-zA-Z0-9_]", "", key).lower()
        key_is_sensitive = normalized in JSON_SECRET_KEYS or bool(
            ENV_SENSITIVE_KEY_RE.search(normalized.upper())
        )
        if key_is_sensitive and secretish_scalar(child):
            findings.append(
                Finding(
                    "content.sensitive-assignment",
                    path,
                    source=source,
                    line_number=1,
                )
            )
    return findings


def scan_blob(path: str, content: bytes, *, source: str) -> list[Finding]:
    findings = filename_findings(path, source)
    text = content.decode("utf-8", errors="ignore")

    for match in PEM_PRIVATE_KEY_RE.finditer(text):
        findings.append(
            Finding(
                "content.private-key-pem",
                path,
                source=source,
                line_number=line_number(text, match.start()),
            )
        )
    for match in JWT_RE.finditer(text):
        findings.append(
            Finding(
                "content.jwt",
                path,
                source=source,
                line_number=line_number(text, match.start()),
            )
        )
    for match in BEARER_RE.finditer(text):
        findings.append(
            Finding(
                "content.bearer-token",
                path,
                source=source,
                line_number=line_number(text, match.start()),
            )
        )
    for pattern in PROVIDER_TOKEN_RES:
        for match in pattern.finditer(text):
            findings.append(
                Finding(
                    "content.api-token",
                    path,
                    source=source,
                    line_number=line_number(text, match.start()),
                )
            )
    for match in CONNECTION_RE.finditer(text):
        embedded_password = match.group(2)
        if placeholderish(embedded_password):
            continue
        findings.append(
            Finding(
                "content.connection-string",
                path,
                source=source,
                line_number=line_number(text, match.start()),
            )
        )

    for lineno, raw_line in enumerate(text.splitlines(), 1):
        match = ASSIGNMENT_RE.match(raw_line)
        if not match:
            continue
        key, raw_value = match.groups()
        normalized_key = re.sub(r"[^a-zA-Z0-9_]", "", key).lower()
        key_is_sensitive = normalized_key in JSON_SECRET_KEYS or bool(
            ENV_SENSITIVE_KEY_RE.search(key)
        )
        scalar = assignment_scalar(path, raw_value)
        if key_is_sensitive and scalar is not None and secretish_scalar(scalar):
            findings.append(
                Finding(
                    "content.sensitive-assignment",
                    path,
                    source=source,
                    line_number=lineno,
                )
            )

    findings.extend(json_findings(path, text, source))

    if content.startswith((b"PGDMP", b"REDIS")):
        findings.append(
            Finding("content.database-dump", path, source=source, line_number=1)
        )
    for match in SQL_DATA_DUMP_RE.finditer(text):
        findings.append(
            Finding(
                "content.database-dump",
                path,
                source=source,
                line_number=line_number(text, match.start()),
            )
        )

    unique: dict[tuple[str, str, int | None, str], Finding] = {}
    for finding in findings:
        unique[finding.identity()] = finding
    return sorted(unique.values(), key=Finding.sort_key)


def read_blob(oid: str) -> bytes:
    if ZERO_OID_RE.fullmatch(oid):
        return b""
    return run_git("cat-file", "blob", oid)


def tree_entries(treeish: str) -> list[tuple[str, str]]:
    run_git("rev-parse", "--verify", f"{treeish}^{{tree}}")
    entries: list[tuple[str, str]] = []
    for item in nul_items(run_git("ls-tree", "-r", "-z", treeish)):
        try:
            metadata, path = item.split("\t", 1)
            _mode, object_type, oid = metadata.split(" ", 2)
        except ValueError as exc:
            raise ScannerError("unexpected git tree entry format") from exc
        if object_type == "blob":
            entries.append((path, oid))
    return entries


def scan_entries(entries: Iterable[tuple[str, str]], source: str) -> list[Finding]:
    findings: list[Finding] = []
    for path, oid in entries:
        findings.extend(scan_blob(path, read_blob(oid), source=source))
    return findings


def scan_tree(treeish: str, *, source: str | None = None) -> list[Finding]:
    return scan_entries(tree_entries(treeish), source or f"tree:{treeish}")


def scan_staged() -> list[Finding]:
    staged_paths = set(
        nul_items(
            run_git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
        )
    )
    index: dict[str, str] = {}
    for item in nul_items(run_git("ls-files", "--stage", "-z")):
        try:
            metadata, path = item.split("\t", 1)
            _mode, oid, stage = metadata.split(" ", 2)
        except ValueError as exc:
            raise ScannerError("unexpected git index entry format") from exc
        if stage == "0":
            index[path] = oid

    missing = sorted(staged_paths - set(index))
    if missing:
        raise ScannerError(
            "staged paths could not be resolved from index; path output suppressed"
        )
    return scan_entries(((path, index[path]) for path in sorted(staged_paths)), "index")


def scan_worktree() -> list[Finding]:
    findings: list[Finding] = []
    candidates = run_git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    for path in nul_items(candidates):
        file_path = REPO_ROOT / path
        if not file_path.exists() and not file_path.is_symlink():
            continue
        try:
            if file_path.is_symlink():
                content = os.readlink(file_path).encode(
                    "utf-8", errors="surrogateescape"
                )
            else:
                content = file_path.read_bytes()
        except OSError as exc:
            raise ScannerError(f"tracked file could not be read: {path}") from exc
        findings.extend(scan_blob(path, content, source="worktree"))
    return findings


def scan_range(revision_range: str) -> list[Finding]:
    commits = [
        line
        for line in run_git("rev-list", "--reverse", revision_range)
        .decode()
        .splitlines()
        if line
    ]
    seen: set[tuple[str, str]] = set()
    findings: list[Finding] = []
    for commit in commits:
        entries = []
        for path, oid in tree_entries(commit):
            identity = (path, oid)
            if identity in seen:
                continue
            seen.add(identity)
            entries.append((path, oid))
        findings.extend(scan_entries(entries, f"commit:{commit[:12]}"))
    return findings


def render_findings(findings: Iterable[Finding]) -> str:
    unique: dict[tuple[str, str, int | None, str], Finding] = {}
    for finding in findings:
        unique[finding.identity()] = finding
    ordered = sorted(unique.values(), key=Finding.sort_key)
    return "\n".join(finding.line() for finding in ordered)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--worktree",
        action="store_true",
        help="scan tracked and non-ignored worktree files",
    )
    scope.add_argument(
        "--staged", action="store_true", help="scan staged blobs from the Git index"
    )
    scope.add_argument("--tree", metavar="TREEISH", help="scan one explicit Git tree")
    scope.add_argument(
        "--range",
        dest="revision_range",
        metavar="REV_RANGE",
        help="scan each commit tree in a revision range",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.staged:
            findings = scan_staged()
            scope_name = "staged index"
        elif args.tree:
            findings = scan_tree(args.tree)
            scope_name = f"tree {args.tree}"
        elif args.revision_range:
            findings = scan_range(args.revision_range)
            scope_name = f"range {args.revision_range}"
        else:
            findings = scan_worktree()
            scope_name = "tracked and non-ignored worktree"
    except (OSError, ScannerError, UnicodeError) as exc:
        print(f"FATAL: secret scan failed closed: {exc}", file=sys.stderr)
        return 2

    if findings:
        print("Committed-secret gate failed. Values are always redacted.")
        print(render_findings(findings))
        print(
            "Remove the artifact and follow docs/security/credential-rotation-runbook.md."
        )
        return 1

    print(f"OK: no secret artifacts detected in {scope_name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
