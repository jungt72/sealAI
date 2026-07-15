#!/usr/bin/env python3
"""Fail-closed local supply-chain policy and scanner-result gate."""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "security" / "supply-chain-policy.json"
EXCEPTIONS_PATH = REPO_ROOT / "security" / "supply-chain-exceptions.json"
REQUIRED_CHECKS_PATH = REPO_ROOT / ".github" / "required-security-checks.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_REF_RE = re.compile(
    r"^[a-z0-9._/-]+:[A-Za-z0-9][A-Za-z0-9._-]{0,127}@sha256:[0-9a-f]{64}$"
)
IMMUTABLE_REF_RE = re.compile(
    r"^[a-z0-9._/-]+(?::[A-Za-z0-9][A-Za-z0-9._-]{0,127})?@sha256:[0-9a-f]{64}$"
)
REQUIREMENT_RE = re.compile(
    r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s\\]+)\s*\\", re.MULTILINE
)
DIRECT_REQUIREMENT_RE = re.compile(
    r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s;]+)(?:\s*;.*)?$"
)
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PRINCIPAL_RE = re.compile(r"^github:[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
EXCEPTION_ID_RE = re.compile(r"^SCX-[0-9]{4}-[0-9]{3,}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BACKEND_IMAGE_REPOSITORY = "ghcr.io/jungt72/sealai-backend-v2"
INTERNAL_IMAGE_REPOSITORIES = {
    BACKEND_IMAGE_REPOSITORY,
    "ghcr.io/jungt72/sealai-frontend",
    "ghcr.io/jungt72/sealai-keycloak",
}
BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
TRIVY_EXCLUDED_FILES = {
    "requirements.txt": "inactive_python_host_snapshot",
    "backend/requirements.txt": "inactive_python_v1_runtime",
    "backend/requirements-dev.txt": "inactive_python_v1_development",
    "AGENTS.md": "license_scanner_false_positive_non_license",
}
REQUIRED_SECURITY_CHECKS = (
    "backend-contracts",
    "backend ruff-format (re-debt guard)",
    "dashboard-contracts",
    "marketing-contracts",
    "supply-chain-policy",
    "python-audit (backend-v2-runtime)",
    "python-audit (backend-v2-ci)",
    "python-audit (security-control-tools)",
    "node-audit (repository-tooling)",
    "node-audit (marketing-frontend)",
    "node-audit (dashboard)",
    "node-audit (strapi)",
    "node-audit (nginx-node-compat)",
    "node-app-validation (marketing-frontend)",
    "node-app-validation (dashboard)",
    "node-app-validation (strapi)",
    "repository-vulnerability-license-sbom",
    "secret-scan",
    "v2-contracts",
)
GOVERNANCE_BLOCK_REASON = (
    "GitHub ruleset enforcement and independent review cannot be proven from "
    "repository content."
)


class SupplyChainError(RuntimeError):
    """The repository or a scanner result cannot prove policy compliance."""


@dataclass(frozen=True)
class Finding:
    control: str
    scope: str
    advisory_id: str
    package: str
    installed_version: str

    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.control,
            self.scope,
            self.advisory_id,
            self.package,
            self.installed_version,
        )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SupplyChainError(
            f"required JSON is missing or invalid: {path.name}"
        ) from exc
    if not isinstance(value, dict):
        raise SupplyChainError(f"JSON root must be an object: {path.name}")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise SupplyChainError(f"{label} contains missing or unexpected fields")


def _safe_path(root: Path, raw: Any, label: str) -> Path:
    if (
        not isinstance(raw, str)
        or not raw
        or PurePosixPath(raw).is_absolute()
        or ".." in PurePosixPath(raw).parts
    ):
        raise SupplyChainError(f"{label} must be a safe repository-relative path")
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SupplyChainError(f"{label} escapes the repository") from exc
    return resolved


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SupplyChainError(f"required file is missing: {path.name}") from exc


def _normalize_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = _load_json(path)
    _exact_keys(
        policy,
        {
            "schema_version",
            "lock_generator",
            "python_locks",
            "trivy_excluded_files",
            "node_projects",
            "dockerfiles",
            "production_manifests",
            "audit_policy",
            "exception_policy",
        },
        "supply-chain policy",
    )
    if policy.get("schema_version") != 2:
        raise SupplyChainError("unsupported supply-chain policy schema")
    generator = policy.get("lock_generator")
    if not isinstance(generator, dict):
        raise SupplyChainError("lock generator policy must be an object")
    _exact_keys(
        generator,
        {
            "archives",
            "command",
            "generator",
            "platform",
            "python_version",
            "release_base_url",
        },
        "lock generator policy",
    )
    if generator != {
        "archives": {
            "aarch64-apple-darwin": "33540eb7c883ab857eff79bd5ac2aa31fe27b595abecb4a9c003a2c998447232",
            "aarch64-unknown-linux-gnu": "03e9fe0a81b0718d0bc84625de3885df6cc3f89a8b6af6121d6b9f6113fb6533",
            "x86_64-apple-darwin": "2ad79983127ffca7d77b77ce6a24278d7e4f7b817a1acf72fea5f8124b4aac5e",
            "x86_64-unknown-linux-gnu": "e490a6464492183c5d4534a5527fb4440f7f2bb2f228162ad7e4afe076dc0224",
        },
        "command": "ops/update-python-locks.sh",
        "generator": "uv==0.11.28",
        "platform": "x86_64-manylinux_2_28",
        "python_version": "3.12",
        "release_base_url": "https://github.com/astral-sh/uv/releases/download/0.11.28",
    }:
        raise SupplyChainError("lock generator policy was weakened or drifted")
    if not all(
        isinstance(policy.get(key), list) and policy[key]
        for key in (
            "python_locks",
            "trivy_excluded_files",
            "node_projects",
            "dockerfiles",
            "production_manifests",
        )
    ):
        raise SupplyChainError("supply-chain inventories must be non-empty lists")
    audit = policy.get("audit_policy")
    exceptions = policy.get("exception_policy")
    if not isinstance(audit, dict) or not isinstance(exceptions, dict):
        raise SupplyChainError("audit and exception policies must be objects")
    _exact_keys(
        audit,
        {
            "image_fail_severities",
            "license_fail_severities",
            "node_fail_severities",
            "python_fail_on_any_vulnerability",
            "license_confidence_level",
            "license_full_scan",
            "trivy_version",
        },
        "audit policy",
    )
    _exact_keys(
        exceptions,
        {"allowed_controls", "max_duration_days", "non_waivable_controls"},
        "exception policy",
    )
    if audit != {
        "image_fail_severities": ["high", "critical"],
        "license_fail_severities": ["unknown", "high", "critical"],
        "license_confidence_level": 0.9,
        "license_full_scan": True,
        "node_fail_severities": ["high", "critical"],
        "python_fail_on_any_vulnerability": True,
        "trivy_version": "0.69.3",
    }:
        raise SupplyChainError("audit policy was weakened or drifted")
    if (
        exceptions.get("max_duration_days") != 30
        or set(exceptions.get("allowed_controls", []))
        != {
            "image-vulnerability",
            "license",
            "node-vulnerability",
            "python-vulnerability",
        }
        or set(exceptions.get("non_waivable_controls", []))
        != {
            "attestation",
            "base-image-digest",
            "dependency-drift",
            "lockfile",
            "secret-exposure",
        }
    ):
        raise SupplyChainError("exception policy was weakened or drifted")
    if set(exceptions["allowed_controls"]) & set(exceptions["non_waivable_controls"]):
        raise SupplyChainError("waivable and non-waivable controls overlap")
    return policy


def _direct_requirements(
    path: Path, *, allowed_includes: Iterable[Path] | None = None
) -> dict[str, str]:
    """Read pinned direct requirements and recursively bind reviewed includes."""

    allowed = {
        candidate.resolve()
        for candidate in (allowed_includes if allowed_includes is not None else (path,))
    }
    result: dict[str, str] = {}
    visiting: set[Path] = set()
    visited: set[Path] = set()

    def visit(current: Path) -> None:
        current = current.resolve()
        if current not in allowed:
            raise SupplyChainError(
                "Python input includes an unreviewed requirements file"
            )
        if current in visiting:
            raise SupplyChainError("Python requirement includes contain a cycle")
        if current in visited:
            return
        visiting.add(current)
        try:
            lines = current.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise SupplyChainError(
                "included Python input is missing or invalid"
            ) from exc
        for number, raw in enumerate(lines, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            include = re.fullmatch(r"(?:-r|--requirement)\s+([^\s]+)", line)
            if include:
                raw_target = include.group(1)
                parsed = urllib.parse.urlsplit(raw_target)
                if (
                    parsed.scheme
                    or parsed.netloc
                    or PurePosixPath(raw_target).is_absolute()
                ):
                    raise SupplyChainError(
                        f"remote or absolute Python include at {current.name}:{number}"
                    )
                target = (current.parent / raw_target).resolve()
                visit(target)
                continue
            match = DIRECT_REQUIREMENT_RE.fullmatch(line)
            if not match:
                raise SupplyChainError(
                    f"unpinned Python input at {current.name}:{number}"
                )
            name, version = _normalize_package(match.group(1)), match.group(2)
            if name in result:
                raise SupplyChainError(f"duplicate Python input package: {name}")
            result[name] = version
        visiting.remove(current)
        visited.add(current)

    visit(path)
    return result


def _locked_requirements(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith(
        "# This file was autogenerated by uv via the following command:\n"
        "#    ops/update-python-locks.sh\n"
    ):
        raise SupplyChainError(f"Python lock has an unapproved generator: {path.name}")
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("--") and not line.startswith("--hash=sha256:"):
            raise SupplyChainError(
                f"unapproved Python lock source or option at {path.name}:{number}"
            )
    matches = list(REQUIREMENT_RE.finditer(text))
    if not matches:
        raise SupplyChainError(f"Python lock is empty or malformed: {path.name}")
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        block = text[
            match.start() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        ]
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})(?:\s|\\|$)", block)
        if not hashes or block.count("--hash=") != len(hashes):
            raise SupplyChainError(
                f"Python lock entry has no valid SHA-256 hash: {match.group(1)}"
            )
        name = _normalize_package(match.group(1))
        if name in result:
            raise SupplyChainError(f"duplicate Python lock package: {name}")
        result[name] = match.group(2)
    return result


def verify_python_locks(root: Path, policy: dict[str, Any]) -> None:
    allowed_inputs = {
        _safe_path(root, item.get("input"), "Python input")
        for item in policy["python_locks"]
        if isinstance(item, dict)
    }
    seen: set[str] = set()
    for item in policy["python_locks"]:
        if not isinstance(item, dict):
            raise SupplyChainError("Python lock inventory entries must be objects")
        _exact_keys(
            item,
            {"name", "input", "input_sha256", "lock", "lock_sha256"},
            "Python lock inventory entry",
        )
        name = item.get("name")
        if not isinstance(name, str) or not name or name in seen:
            raise SupplyChainError("Python lock names must be unique")
        seen.add(name)
        source = _safe_path(root, item["input"], "Python input")
        lock = _safe_path(root, item["lock"], "Python lock")
        for key, path in (("input_sha256", source), ("lock_sha256", lock)):
            expected = item.get(key)
            if (
                not isinstance(expected, str)
                or not SHA256_RE.fullmatch(expected)
                or _sha256(path) != expected
            ):
                raise SupplyChainError(
                    f"dependency drift detected for {path.relative_to(root)}"
                )
        direct = _direct_requirements(source, allowed_includes=allowed_inputs)
        locked = _locked_requirements(lock)
        for package, version in direct.items():
            if locked.get(package) != version:
                raise SupplyChainError(
                    f"Python direct dependency is absent from lock: {package}"
                )
    process = subprocess.run(
        ["git", "ls-files", "*requirements*.txt"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise SupplyChainError("cannot inventory tracked Python dependency files")
    tracked = {line for line in process.stdout.splitlines() if line}
    governed = {
        str(item["input"])
        for item in policy["python_locks"]
        if isinstance(item, dict) and isinstance(item.get("input"), str)
    }
    excluded = {
        str(item["path"])
        for item in policy["trivy_excluded_files"]
        if isinstance(item, dict)
        and str(item.get("classification", "")).startswith("inactive_python_")
    }
    if tracked != governed | excluded:
        raise SupplyChainError("Python dependency manifest inventory is incomplete")


def verify_trivy_exclusions(root: Path, policy: dict[str, Any]) -> None:
    exclusions = policy["trivy_excluded_files"]
    if not isinstance(exclusions, list) or len(exclusions) != len(TRIVY_EXCLUDED_FILES):
        raise SupplyChainError("Trivy exclusion inventory is invalid")
    observed: dict[str, str] = {}
    for item in exclusions:
        if not isinstance(item, dict):
            raise SupplyChainError("Trivy exclusion entries must be objects")
        _exact_keys(item, {"classification", "path", "sha256"}, "Trivy exclusion")
        path_value = item.get("path")
        classification = item.get("classification")
        digest = item.get("sha256")
        if (
            not isinstance(path_value, str)
            or path_value in observed
            or TRIVY_EXCLUDED_FILES.get(path_value) != classification
            or not isinstance(digest, str)
            or not SHA256_RE.fullmatch(digest)
        ):
            raise SupplyChainError("Trivy exclusion inventory is invalid")
        path = _safe_path(root, path_value, "Trivy excluded file")
        if _sha256(path) != digest:
            raise SupplyChainError("Trivy excluded file drifted")
        observed[path_value] = str(classification)
    if observed != TRIVY_EXCLUDED_FILES:
        raise SupplyChainError("Trivy exclusion inventory is incomplete")

    deployment_surfaces = [
        *(_safe_path(root, path, "Dockerfile") for path in policy["dockerfiles"]),
        *sorted((root / ".github" / "workflows").glob("*.y*ml")),
    ]
    inactive_python = [
        path
        for path, classification in TRIVY_EXCLUDED_FILES.items()
        if classification.startswith("inactive_python_")
    ]
    for surface in deployment_surfaces:
        text = surface.read_text(encoding="utf-8")
        for excluded_path in inactive_python:
            excluded = PurePosixPath(excluded_path)
            candidates = {excluded_path}
            if (
                PurePosixPath(surface.relative_to(root).as_posix()).parent
                == excluded.parent
            ):
                candidates.add(excluded.name)
            if any(
                re.search(
                    rf"(?<![A-Za-z0-9_.-]){re.escape(candidate)}(?![A-Za-z0-9_.-])",
                    text,
                )
                for candidate in candidates
            ):
                raise SupplyChainError(
                    "inactive Python manifest is referenced by a deployment surface"
                )


def verify_node_locks(root: Path, policy: dict[str, Any]) -> None:
    process = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise SupplyChainError("cannot inventory tracked Node dependency files")
    tracked = {PurePosixPath(line) for line in process.stdout.splitlines()}
    manifests = {
        "." if path.parent == PurePosixPath(".") else path.parent.as_posix()
        for path in tracked
        if path.name == "package.json"
    }
    locks = {
        "." if path.parent == PurePosixPath(".") else path.parent.as_posix()
        for path in tracked
        if path.name == "package-lock.json"
    }
    inventory = {
        str(item.get("path"))
        for item in policy["node_projects"]
        if isinstance(item, dict)
    }
    if manifests != locks or inventory != manifests:
        raise SupplyChainError(
            "Node project inventory or package-lock coverage is incomplete"
        )
    seen: set[str] = set()
    for item in policy["node_projects"]:
        if not isinstance(item, dict):
            raise SupplyChainError("Node inventory entries must be objects")
        _exact_keys(item, {"name", "path"}, "Node inventory entry")
        name = item.get("name")
        if not isinstance(name, str) or not name or name in seen:
            raise SupplyChainError("Node project names must be unique")
        seen.add(name)
        directory = _safe_path(root, item["path"], "Node project path")
        manifest = _load_json(directory / "package.json")
        lock = _load_json(directory / "package-lock.json")
        if lock.get("lockfileVersion") != 3 or not isinstance(
            lock.get("packages"), dict
        ):
            raise SupplyChainError(f"Node lockfile v3 is required for {name}")
        locked_root = lock["packages"].get("")
        if not isinstance(locked_root, dict):
            raise SupplyChainError(f"Node lock root is missing for {name}")
        for field in (
            "dependencies",
            "devDependencies",
            "optionalDependencies",
            "peerDependencies",
        ):
            if (manifest.get(field) or {}) != (locked_root.get(field) or {}):
                raise SupplyChainError(
                    f"package.json/package-lock drift in {name}: {field}"
                )
        packages = lock["packages"]
        for package_path, package in packages.items():
            if not package_path:
                continue
            if not isinstance(package, dict):
                raise SupplyChainError(f"Node lock package is malformed in {name}")
            if package.get("link") is True:
                resolved = package.get("resolved")
                if (
                    not isinstance(resolved, str)
                    or not resolved
                    or package.get("inBundle") is not None
                    or package.get("integrity") is not None
                ):
                    raise SupplyChainError(f"unsafe Node link entry in {name}")
                target = PurePosixPath(resolved)
                if (
                    target.is_absolute()
                    or ".." in target.parts
                    or resolved not in packages
                ):
                    raise SupplyChainError(
                        f"Node link escapes its reviewed lock in {name}"
                    )
                continue
            if package.get("inBundle") is True:
                if (
                    not isinstance(package.get("version"), str)
                    or not package["version"]
                    or package.get("resolved") is not None
                    or package.get("integrity") is not None
                    or "/node_modules/" not in package_path
                ):
                    raise SupplyChainError(f"unsafe bundled Node package in {name}")
                parent_path, bundled_name = package_path.rsplit("/node_modules/", 1)
                parent = packages.get(parent_path)
                bundle = (
                    parent.get("bundleDependencies", parent.get("bundledDependencies"))
                    if isinstance(parent, dict)
                    else None
                )
                if not isinstance(bundle, list) or bundled_name not in bundle:
                    raise SupplyChainError(
                        f"bundled Node package lacks a signed parent declaration in {name}"
                    )
                continue
            if package.get("link") is not None or package.get("inBundle") is not None:
                raise SupplyChainError(f"invalid Node lock exception marker in {name}")
            resolved = package.get("resolved")
            integrity = package.get("integrity")
            if not isinstance(resolved, str) or not isinstance(integrity, str):
                raise SupplyChainError(f"missing Node source or integrity in {name}")
            parsed = urllib.parse.urlsplit(resolved)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "registry.npmjs.org"
                or parsed.port is not None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or not parsed.path.endswith(".tgz")
            ):
                raise SupplyChainError(f"unapproved Node package source in {name}")
            match = re.fullmatch(r"sha512-([A-Za-z0-9+/]+={0,2})", integrity)
            if not match:
                raise SupplyChainError(f"missing Node package integrity in {name}")
            try:
                decoded = base64.b64decode(match.group(1), validate=True)
            except (binascii.Error, ValueError) as exc:
                raise SupplyChainError(
                    f"invalid Node package integrity in {name}"
                ) from exc
            if len(decoded) != hashlib.sha512().digest_size:
                raise SupplyChainError(f"invalid Node package integrity in {name}")


def _tracked_dockerfiles(root: Path) -> set[str]:
    process = subprocess.run(
        ["git", "ls-files", "*Dockerfile*"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise SupplyChainError("cannot inventory tracked Dockerfiles")
    return {
        line
        for line in process.stdout.splitlines()
        if PurePosixPath(line).name.startswith("Dockerfile")
    }


def verify_dockerfiles(root: Path, policy: dict[str, Any]) -> None:
    expected = set(policy["dockerfiles"])
    if len(expected) != len(policy["dockerfiles"]) or expected != _tracked_dockerfiles(
        root
    ):
        raise SupplyChainError("Dockerfile inventory is incomplete or duplicated")
    for relative in sorted(expected):
        path = _safe_path(root, relative, "Dockerfile")
        dockerfile_text = path.read_text(encoding="utf-8")
        aliases: set[str] = set()
        found = False
        for number, raw in enumerate(dockerfile_text.splitlines(), 1):
            match = re.match(
                r"^\s*FROM\s+(\S+)(?:\s+AS\s+(\S+))?\s*$", raw, re.IGNORECASE
            )
            if not match:
                continue
            found = True
            image, alias = match.group(1), match.group(2)
            if (
                image not in aliases
                and image != "scratch"
                and not DIGEST_REF_RE.fullmatch(image)
            ):
                raise SupplyChainError(
                    f"base image is not digest-pinned: {relative}:{number}"
                )
            if ":latest" in image.lower():
                raise SupplyChainError(
                    f"latest base image is forbidden: {relative}:{number}"
                )
            if alias:
                aliases.add(alias)
        if not found:
            raise SupplyChainError(f"Dockerfile has no FROM instruction: {relative}")
        if "apt-get install" in dockerfile_text and not any(
            snapshot in dockerfile_text
            for snapshot in (
                "snapshot.debian.org/archive/",
                "snapshot.ubuntu.com/ubuntu/",
            )
        ):
            raise SupplyChainError(
                f"apt packages are not bound to an immutable snapshot: {relative}"
            )
        logical: list[str] = []
        current = ""
        for raw in dockerfile_text.splitlines():
            stripped = raw.strip()
            current = f"{current} {stripped}".strip()
            if stripped.endswith("\\"):
                current = current[:-1].rstrip()
                continue
            if current:
                logical.append(current)
            current = ""
        if current:
            logical.append(current)
        for instruction in logical:
            external_download = re.search(
                r"\b(?:curl|wget)\b(?:\s+-[^\s]+)*\s+https?://|^ADD\s+https?://",
                instruction,
                re.IGNORECASE,
            )
            if external_download:
                if re.search(r"http://(?!127\.0\.0\.1|localhost)", instruction):
                    raise SupplyChainError(
                        f"plaintext external Docker download is forbidden: {relative}"
                    )
                if "sha256sum" not in instruction:
                    raise SupplyChainError(
                        f"Docker download lacks an inline SHA-256 check: {relative}"
                    )
            apk = re.search(r"\bapk\s+add\s+(.*?)(?:\s+(?:&&|;)|$)", instruction)
            if apk:
                packages = [
                    token for token in apk.group(1).split() if not token.startswith("-")
                ]
                if not packages or any("=" not in package for package in packages):
                    raise SupplyChainError(
                        f"apk packages are not version-pinned: {relative}"
                    )


def _tracked_compose_files(root: Path) -> set[str]:
    process = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise SupplyChainError("cannot inventory tracked Compose manifests")
    result: set[str] = set()
    for line in process.stdout.splitlines():
        name = PurePosixPath(line).name
        if re.fullmatch(r"(?:docker-)?compose(?:\.[A-Za-z0-9_-]+)?\.ya?ml", name):
            result.add(line)
    return result


def _image_repository(reference: str) -> str:
    if not IMMUTABLE_REF_RE.fullmatch(reference):
        raise SupplyChainError("image reference must be an exact sha256 digest")
    without_digest = reference.split("@", 1)[0]
    last = without_digest.rsplit("/", 1)[-1]
    if ":" in last:
        without_digest = without_digest.rsplit(":", 1)[0]
    return without_digest


def _manifest_literal_repositories(path: Path) -> set[str]:
    repositories: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*image:\s*(\S.*)\s*$", raw)
        if not match:
            continue
        image = match.group(1).strip().strip("\"'")
        if image.startswith("${"):
            continue
        repositories.add(_image_repository(image))
    return repositories


def verify_production_manifests(root: Path, policy: dict[str, Any]) -> None:
    inventory = policy["production_manifests"]
    expected_paths = {item.get("path") for item in inventory if isinstance(item, dict)}
    if len(expected_paths) != len(
        inventory
    ) or expected_paths != _tracked_compose_files(root):
        raise SupplyChainError("Compose manifest inventory is incomplete or duplicated")
    for item in inventory:
        if not isinstance(item, dict):
            raise SupplyChainError("production manifest entries must be objects")
        _exact_keys(
            item,
            {"classification", "path", "required_digest_variables"},
            "production manifest entry",
        )
        classification = item.get("classification")
        if classification not in {
            "development",
            "staging",
            "production",
            "blocked_external",
        }:
            raise SupplyChainError("Compose classification is invalid")
        required = item["required_digest_variables"]
        if not isinstance(required, list) or not all(
            isinstance(value, dict) for value in required
        ):
            raise SupplyChainError("runtime digest variable inventory is invalid")
        required_names: set[str] = set()
        required_repositories: set[str] = set()
        for value in required:
            _exact_keys(value, {"name", "repository"}, "runtime digest variable")
            variable = value.get("name")
            repository = value.get("repository")
            if (
                not isinstance(variable, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9_]*", variable)
                or variable in required_names
                or not isinstance(repository, str)
                or not re.fullmatch(r"[a-z0-9._/-]+", repository)
                or repository in required_repositories
            ):
                raise SupplyChainError("runtime digest variable inventory is invalid")
            required_names.add(variable)
            required_repositories.add(repository)
        seen: set[str] = set()
        path = _safe_path(root, item["path"], "production manifest")
        text = path.read_text(encoding="utf-8")
        if classification == "blocked_external":
            if (
                BLOCKED_EXTERNAL not in text
                or not re.search(r"(?m)^services:\s*\{\}\s*$", text)
                or re.search(r"(?m)^\s+(?:image|build):", text)
            ):
                raise SupplyChainError(
                    f"blocked Compose manifest is not mechanically inert: {path.name}"
                )
            if required:
                raise SupplyChainError("blocked Compose manifest cannot require images")
            continue
        if classification != "production":
            if required:
                raise SupplyChainError(
                    "non-production Compose manifest cannot define production images"
                )
            continue
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = re.match(r"^\s*image:\s*(\S.*)\s*$", raw)
            if not match:
                continue
            image = match.group(1).strip().strip("\"'")
            variable = re.fullmatch(r"\$\{([A-Z][A-Z0-9_]*):\?(.+)\}", image)
            if variable:
                seen.add(variable.group(1))
                if variable.group(1) not in required_names or not re.search(
                    r"(?:tag@sha256|sha256 digest)", variable.group(2), re.IGNORECASE
                ):
                    raise SupplyChainError(
                        f"runtime image variable lacks digest contract: {path.name}:{number}"
                    )
            elif not IMMUTABLE_REF_RE.fullmatch(image):
                raise SupplyChainError(
                    f"production image is not digest-pinned: {path.name}:{number}"
                )
        if seen != required_names:
            raise SupplyChainError(
                f"production digest variable inventory drift: {path.name}"
            )


def verify_materialized_images(
    manifest_paths: Iterable[str], images_path: Path, *, root: Path = REPO_ROOT
) -> None:
    policy = load_policy()
    selected = set(manifest_paths)
    inventory = {str(item["path"]): item for item in policy["production_manifests"]}
    if not selected or any(
        path not in inventory or inventory[path]["classification"] != "production"
        for path in selected
    ):
        raise SupplyChainError(
            "materialized images require inventoried production manifests"
        )
    expected: set[str] = set()
    for relative in selected:
        entry = inventory[relative]
        expected.update(
            str(value["repository"]) for value in entry["required_digest_variables"]
        )
        expected.update(
            _manifest_literal_repositories(_safe_path(root, relative, "manifest"))
        )
    try:
        references = [
            line.strip()
            for line in images_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeDecodeError) as exc:
        raise SupplyChainError(
            "materialized Compose image inventory is unavailable"
        ) from exc
    if not references:
        raise SupplyChainError("materialized Compose image inventory is empty")
    observed = {_image_repository(reference) for reference in references}
    if observed != expected:
        raise SupplyChainError("materialized Compose repositories do not match policy")
    if BACKEND_IMAGE_REPOSITORY in expected:
        backend = [
            reference
            for reference in references
            if _image_repository(reference) == BACKEND_IMAGE_REPOSITORY
        ]
        if len(set(backend)) != 1 or not DIGEST_REF_RE.fullmatch(backend[0]):
            raise SupplyChainError(
                "backend-v2 must use its exact approved tag@digest repository"
            )


def _timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise SupplyChainError(f"{label} must be an exact UTC timestamp")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise SupplyChainError(f"{label} is invalid") from exc


def canonical_exception_sha256(item: dict[str, Any]) -> str:
    subject = {key: value for key, value in item.items() if key != "approval_receipt"}
    encoded = json.dumps(
        subject, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_exceptions(
    policy: dict[str, Any],
    path: Path = EXCEPTIONS_PATH,
    *,
    now: dt.datetime | None = None,
) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    registry = _load_json(path)
    _exact_keys(
        registry,
        {"approval_verification", "schema_version", "exceptions"},
        "exception registry",
    )
    if (
        registry.get("schema_version") != 2
        or registry.get("approval_verification") != BLOCKED_EXTERNAL
        or not isinstance(registry.get("exceptions"), list)
    ):
        raise SupplyChainError("unsupported exception registry")
    now = now or dt.datetime.now(dt.timezone.utc)
    allowed = set(policy["exception_policy"]["allowed_controls"])
    maximum = dt.timedelta(days=int(policy["exception_policy"]["max_duration_days"]))
    active: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    ids: set[str] = set()
    expected = {
        "exception_id",
        "control",
        "scope",
        "advisory_id",
        "package",
        "installed_version",
        "approved_by",
        "reason",
        "approved_at",
        "approval_receipt",
        "expires_at",
        "tracking_url",
    }
    for item in registry["exceptions"]:
        if not isinstance(item, dict):
            raise SupplyChainError("exception entries must be objects")
        _exact_keys(item, expected, "exception entry")
        receipt = item.get("approval_receipt")
        if not isinstance(receipt, dict):
            raise SupplyChainError("exception lacks a canonical approval receipt")
        _exact_keys(
            receipt,
            {
                "exception_sha256",
                "principal",
                "review_commit_sha",
                "review_url",
                "schema_version",
                "status",
            },
            "exception approval receipt",
        )
        if (
            receipt.get("schema_version") != 1
            or receipt.get("status") != BLOCKED_EXTERNAL
            or receipt.get("exception_sha256") != canonical_exception_sha256(item)
            or receipt.get("principal") != item.get("approved_by")
            or not isinstance(receipt.get("review_commit_sha"), str)
            or not GIT_SHA_RE.fullmatch(receipt["review_commit_sha"])
            or receipt.get("review_url") != item.get("tracking_url")
        ):
            raise SupplyChainError("exception approval receipt is invalid or unbound")
        identifier = item.get("exception_id")
        if (
            not isinstance(identifier, str)
            or not EXCEPTION_ID_RE.fullmatch(identifier)
            or identifier in ids
        ):
            raise SupplyChainError("exception IDs must be unique SCX identifiers")
        ids.add(identifier)
        if item.get("control") not in allowed:
            raise SupplyChainError("exception targets a non-waivable control")
        if any(
            not isinstance(item.get(field), str) or not item[field]
            for field in ("scope", "advisory_id", "package", "installed_version")
        ):
            raise SupplyChainError("exception subject must be exact and non-empty")
        if not isinstance(item.get("approved_by"), str) or not PRINCIPAL_RE.fullmatch(
            item["approved_by"]
        ):
            raise SupplyChainError(
                "exception approval must be bound to a GitHub principal"
            )
        if not isinstance(item.get("reason"), str) or len(item["reason"].strip()) < 20:
            raise SupplyChainError("exception reason is too short")
        tracking = urllib.parse.urlsplit(str(item.get("tracking_url", "")))
        if (
            tracking.scheme != "https"
            or tracking.netloc != "github.com"
            or not re.fullmatch(r"/jungt72/sealAI/(?:issues|pull)/\d+", tracking.path)
        ):
            raise SupplyChainError(
                "exception must reference a GitHub issue or pull request"
            )
        approved = _timestamp(item["approved_at"], "approved_at")
        expires = _timestamp(item["expires_at"], "expires_at")
        if (
            approved > now
            or expires <= approved
            or expires - approved > maximum
            or expires <= now
        ):
            raise SupplyChainError(
                "exception is not active, is expired, or exceeds maximum duration"
            )
        finding = Finding(
            item["control"],
            item["scope"],
            item["advisory_id"],
            item["package"],
            item["installed_version"],
        )
        if finding.key() in active:
            raise SupplyChainError("duplicate exception subject")
        raise SupplyChainError(
            "exception principal verification is BLOCKED_EXTERNAL; no waiver is active"
        )
    return active


def verify_ci_workflows(root: Path) -> None:
    workflow_root = root / ".github" / "workflows"
    paths = sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
    if not paths:
        raise SupplyChainError("GitHub workflow inventory is empty")
    action_ref = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}")
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise SupplyChainError("GitHub workflow is unreadable") from exc
        if not re.search(r"(?m)^permissions:", text):
            raise SupplyChainError(f"workflow has implicit permissions: {path.name}")
        runners = re.findall(r"(?m)^\s*runs-on:\s*(\S+)\s*$", text)
        if not runners or any(runner != "ubuntu-24.04" for runner in runners):
            raise SupplyChainError(f"workflow runner is mutable: {path.name}")
        for raw in text.splitlines():
            match = re.match(r"^\s*-?\s*uses:\s*(\S+)", raw)
            if not match:
                continue
            reference = match.group(1)
            if reference.startswith("./"):
                continue
            if not action_ref.fullmatch(reference):
                raise SupplyChainError(
                    f"workflow action is not commit-pinned: {path.name}"
                )
        if "actions/checkout@" in text and "persist-credentials: false" not in text:
            raise SupplyChainError(
                f"workflow checkout retains credentials: {path.name}"
            )
        if path.name in {"dependency-audit.yml", "secret-scan.yml"} and not all(
            marker in text
            for marker in ("  push:\n    branches: [main]\n", "  pull_request:\n")
        ):
            raise SupplyChainError(
                f"security workflow trigger boundary drifted: {path.name}"
            )
        for raw in text.splitlines():
            if "pip install" in raw and not re.search(
                r"pip install --require-hashes -r \S+\.lock", raw
            ):
                raise SupplyChainError(
                    f"workflow has an unhashed Python install: {path.name}"
                )
            if re.search(r"\b(?:npm install|npx)\b", raw):
                raise SupplyChainError(
                    f"workflow has a non-lock-bound Node install: {path.name}"
                )
        if "aquasecurity/trivy-action@" in text and any(
            required not in text
            for required in (
                "version: v0.69.3",
                "scanners: vuln,license",
                "trivy-config: security/trivy.yaml",
                "severity: UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL",
            )
        ):
            raise SupplyChainError(f"workflow Trivy policy is incomplete: {path.name}")


def verify_trivy_config(root: Path) -> None:
    try:
        lines = [
            line.rstrip()
            for line in (root / "security" / "trivy.yaml")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except (OSError, UnicodeDecodeError) as exc:
        raise SupplyChainError("Trivy policy config is missing") from exc
    if lines != [
        "scan:",
        "  skip-files:",
        "    - requirements.txt",
        "    - backend/requirements.txt",
        "    - backend/requirements-dev.txt",
        "    - AGENTS.md",
        "license:",
        "  confidenceLevel: 0.9",
        "  full: true",
        "  ignored: []",
    ]:
        raise SupplyChainError("Trivy license policy config drifted")


def verify_external_governance(root: Path) -> None:
    receipt = _load_json(root / ".github" / "required-security-checks.json")
    _exact_keys(
        receipt,
        {
            "schema_version",
            "control_id",
            "repository",
            "protected_branch",
            "strict",
            "required_checks",
            "enforcement_receipt",
        },
        "required-check governance receipt",
    )
    enforcement = receipt.get("enforcement_receipt")
    if not isinstance(enforcement, dict):
        raise SupplyChainError("required-check enforcement receipt must be an object")
    _exact_keys(
        enforcement,
        {
            "status",
            "reason",
            "ruleset_id",
            "verified_at",
            "verified_by",
            "evidence_url",
        },
        "required-check enforcement receipt",
    )
    if receipt != {
        "schema_version": 2,
        "control_id": "H6",
        "repository": "jungt72/sealAI",
        "protected_branch": "main",
        "strict": True,
        "required_checks": list(REQUIRED_SECURITY_CHECKS),
        "enforcement_receipt": {
            "status": BLOCKED_EXTERNAL,
            "reason": GOVERNANCE_BLOCK_REASON,
            "ruleset_id": None,
            "verified_at": None,
            "verified_by": None,
            "evidence_url": None,
        },
    }:
        raise SupplyChainError(
            "required-check inventory or BLOCKED_EXTERNAL receipt drifted"
        )
    try:
        codeowners = (root / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SupplyChainError("supply-chain CODEOWNERS policy is missing") from exc
    required_owner_paths = {
        "/.github/workflows/ @jungt72",
        "/.github/CODEOWNERS @jungt72",
        "/.github/dependabot.yml @jungt72",
        "/.github/required-security-checks.json @jungt72",
        "/security/ @jungt72",
        "/backend/requirements*.txt @jungt72",
        "/backend/requirements*.lock @jungt72",
        "/**/package.json @jungt72",
        "/**/package-lock.json @jungt72",
        "/Dockerfile* @jungt72",
        "/**/Dockerfile* @jungt72",
        "/docker-compose*.yml @jungt72",
        "/paperless/docker-compose.yml @jungt72",
        "/ops/staging/docker-compose.staging.yml @jungt72",
        "/ops/supply_chain_gate.py @jungt72",
        "/ops/update-python-locks.sh @jungt72",
        "/ops/verify-image-attestations.sh @jungt72",
    }
    owner_lines = {
        line.strip()
        for line in codeowners.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if owner_lines != required_owner_paths:
        raise SupplyChainError("supply-chain CODEOWNERS policy drifted")


def verify_repository(
    root: Path = REPO_ROOT,
    policy_path: Path = POLICY_PATH,
    exceptions_path: Path = EXCEPTIONS_PATH,
) -> None:
    policy = load_policy(policy_path)
    verify_python_locks(root, policy)
    verify_trivy_exclusions(root, policy)
    verify_node_locks(root, policy)
    verify_dockerfiles(root, policy)
    verify_production_manifests(root, policy)
    load_exceptions(policy, exceptions_path)
    verify_ci_workflows(root)
    verify_trivy_config(root)
    verify_external_governance(root)


def _npm_versions(
    root: Path, policy: dict[str, Any], scope: str, package: str, nodes: Iterable[str]
) -> set[str]:
    project = next(
        (item for item in policy["node_projects"] if item["name"] == scope), None
    )
    if project is None:
        raise SupplyChainError("npm audit scope is not in policy")
    lock = _load_json(
        _safe_path(root, project["path"], "Node project") / "package-lock.json"
    )
    packages = lock.get("packages") or {}
    versions = {
        str(packages[node].get("version"))
        for node in nodes
        if node in packages and packages[node].get("version")
    }
    if not versions:
        versions = {
            str(value.get("version"))
            for path, value in packages.items()
            if path.endswith(f"node_modules/{package}")
            and isinstance(value, dict)
            and value.get("version")
        }
    if not versions:
        raise SupplyChainError(f"npm report package is absent from lock: {package}")
    return versions


def _trivy_image_path(raw: Any, label: str, *, allow_absolute: bool) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise SupplyChainError(f"{label} must be a safe image-relative path")
    path = PurePosixPath(raw)
    if (path.is_absolute() and not allow_absolute) or ".." in path.parts:
        raise SupplyChainError(f"{label} must be a safe image-relative path")
    normalized = path.as_posix().lstrip("/")
    if allow_absolute and path.as_posix() == "/":
        return "/"
    if not normalized or normalized == ".":
        raise SupplyChainError(f"{label} must be a safe image-relative path")
    return normalized


def _trivy_os_package_identities(
    report: dict[str, Any],
    *,
    package: str | None = None,
    file_path: str | None = None,
    license_name: str | None = None,
) -> set[tuple[str, str]]:
    """Resolve a versionless image license to Trivy's exact OS inventory."""

    identities: set[tuple[str, str]] = set()
    inventory_seen = False
    for result in report.get("Results") or []:
        if not isinstance(result, dict) or result.get("Class") != "os-pkgs":
            continue
        packages = result.get("Packages")
        if not isinstance(packages, list) or not packages:
            raise SupplyChainError("Trivy image OS package inventory is malformed")
        inventory_seen = True
        for item in packages:
            if not isinstance(item, dict):
                raise SupplyChainError("Trivy image OS package inventory is malformed")
            name = item.get("Name")
            if package is not None and name != package:
                continue
            if license_name is not None:
                licenses = item.get("Licenses")
                if not isinstance(licenses, list) or license_name not in licenses:
                    continue
            if file_path is not None:
                installed_files = item.get("InstalledFiles")
                if not isinstance(installed_files, list):
                    continue
                normalized_files = {
                    _trivy_image_path(
                        installed_file,
                        "Trivy installed package file",
                        allow_absolute=True,
                    )
                    for installed_file in installed_files
                }
                if file_path not in normalized_files:
                    continue
            identifier = item.get("Identifier")
            purl = identifier.get("PURL") if isinstance(identifier, dict) else None
            if (
                not isinstance(name, str)
                or not name
                or not isinstance(purl, str)
                or not purl.startswith("pkg:")
                or any(character.isspace() for character in purl)
            ):
                raise SupplyChainError(
                    "Trivy image OS package lacks an exact package identity"
                )
            identities.add((name, purl))
    if not inventory_seen:
        raise SupplyChainError("Trivy image has no exact OS package inventory")
    if not identities:
        raise SupplyChainError(
            "Trivy image license cannot be resolved in its exact OS inventory"
        )
    return identities


def _trivy_license_identities(
    root: Path,
    report: dict[str, Any],
    result: dict[str, Any],
    license_item: dict[str, Any],
) -> set[tuple[str, str]]:
    """Return exact, repository-bound identities for a Trivy license finding."""

    package = license_item.get("PkgName")
    version = license_item.get("Version") or license_item.get("InstalledVersion")
    if isinstance(package, str) and package and isinstance(version, str) and version:
        return {(package, version)}

    file_path = license_item.get("FilePath")
    if report.get("ArtifactType") == "container_image":
        license_name = license_item.get("Name")
        if isinstance(package, str) and package:
            if file_path:
                raise SupplyChainError(
                    "versionless Trivy image package license has an unexpected file"
                )
            if result.get("Target") != "OS Packages" or not isinstance(
                license_name, str
            ):
                raise SupplyChainError(
                    "versionless Trivy image package license is malformed"
                )
            return _trivy_os_package_identities(
                report,
                package=package,
                license_name=license_name,
            )
        if result.get("Target") != "Loose File License(s)":
            raise SupplyChainError(
                "Trivy image license finding lacks an exact package identity"
            )
        image_path = _trivy_image_path(
            file_path, "Trivy license file", allow_absolute=False
        )
        return _trivy_os_package_identities(report, file_path=image_path)

    path = _safe_path(root, file_path, "Trivy license file")
    if isinstance(package, str) and package:
        if path.name != "package-lock.json":
            raise SupplyChainError(
                "versionless Trivy package license is not bound to an npm lock"
            )
        lock = _load_json(path)
        packages = lock.get("packages")
        if not isinstance(packages, dict):
            raise SupplyChainError("Trivy license npm lock is malformed")
        versions = {
            str(value["version"])
            for key, value in packages.items()
            if isinstance(key, str)
            and (
                key == f"node_modules/{package}"
                or key.endswith(f"/node_modules/{package}")
            )
            and isinstance(value, dict)
            and isinstance(value.get("version"), str)
            and value["version"]
        }
        if not versions:
            raise SupplyChainError(
                "Trivy package license cannot be resolved in its exact npm lock"
            )
        return {(package, item) for item in versions}

    target = result.get("Target")
    if target != "Loose File License(s)":
        raise SupplyChainError("Trivy license finding lacks an exact package identity")
    relative = PurePosixPath(str(file_path)).as_posix()
    return {(f"file:{relative}", f"sha256:{_sha256(path)}")}


def findings_from_report(
    scanner: str,
    report: dict[str, Any],
    *,
    scope: str,
    root: Path,
    policy: dict[str, Any],
) -> list[Finding]:
    findings: set[Finding] = set()
    if scanner == "pip-audit":
        dependencies = report.get("dependencies")
        if not isinstance(dependencies, list):
            raise SupplyChainError("pip-audit report has no dependency inventory")
        project = next(
            (item for item in policy["python_locks"] if item["name"] == scope), None
        )
        if project is None:
            raise SupplyChainError("pip-audit scope is not in policy")
        locked = _locked_requirements(
            _safe_path(root, project["lock"], "Python audit lock")
        )
        reported: dict[str, str] = {}
        for dependency in dependencies:
            if not isinstance(dependency, dict) or not isinstance(
                dependency.get("vulns"), list
            ):
                raise SupplyChainError("pip-audit report is malformed")
            name = dependency.get("name")
            version = dependency.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                raise SupplyChainError("pip-audit dependency identity is malformed")
            normalized = _normalize_package(name)
            if normalized in reported or locked.get(normalized) != version:
                raise SupplyChainError("pip-audit inventory does not match the lock")
            reported[normalized] = version
            for vuln in dependency["vulns"]:
                if not isinstance(vuln, dict) or not vuln.get("id"):
                    raise SupplyChainError("pip-audit vulnerability is malformed")
                findings.add(
                    Finding(
                        "python-vulnerability",
                        scope,
                        str(vuln["id"]),
                        name,
                        version,
                    )
                )
        if reported != locked:
            raise SupplyChainError(
                "pip-audit report does not cover the exact transitive lock"
            )
    elif scanner == "npm-audit":
        if (
            report.get("error")
            or report.get("auditReportVersion") != 2
            or not isinstance(report.get("vulnerabilities"), dict)
        ):
            raise SupplyChainError("npm-audit report is missing, errored, or malformed")
        fail = {
            str(value).lower()
            for value in policy["audit_policy"]["node_fail_severities"]
        }
        vulnerabilities = report["vulnerabilities"]
        project = next(
            (item for item in policy["node_projects"] if item["name"] == scope), None
        )
        if project is None:
            raise SupplyChainError("npm audit scope is not in policy")
        lock = _load_json(
            _safe_path(root, project["path"], "Node audit project")
            / "package-lock.json"
        )
        packages = lock.get("packages")
        metadata = report.get("metadata")
        if not isinstance(packages, dict) or not isinstance(metadata, dict):
            raise SupplyChainError("npm-audit inventory metadata is malformed")
        dependency_counts = metadata.get("dependencies")
        vulnerability_counts = metadata.get("vulnerabilities")
        severities = {"info", "low", "moderate", "high", "critical"}
        if (
            not isinstance(dependency_counts, dict)
            or dependency_counts.get("total") != len(packages) - 1
            or not isinstance(vulnerability_counts, dict)
            or set(vulnerability_counts) != severities | {"total"}
        ):
            raise SupplyChainError(
                "npm-audit inventory metadata does not match the lock"
            )
        observed = {severity: 0 for severity in severities}
        for value in vulnerabilities.values():
            if not isinstance(value, dict) or value.get("severity") not in severities:
                raise SupplyChainError("npm-audit vulnerability inventory is malformed")
            observed[value["severity"]] += 1
        if any(
            vulnerability_counts[key] != value for key, value in observed.items()
        ) or vulnerability_counts["total"] != sum(observed.values()):
            raise SupplyChainError("npm-audit vulnerability counts are inconsistent")

        def has_blocking_advisory(package: str, seen: frozenset[str]) -> bool:
            if package in seen:
                return False
            value = vulnerabilities.get(package)
            if not isinstance(value, dict):
                return False
            for via in value.get("via") or []:
                if (
                    isinstance(via, dict)
                    and str(via.get("severity", "")).lower() in fail
                ):
                    return bool(via.get("url") or via.get("source") or via.get("name"))
                if isinstance(via, str) and has_blocking_advisory(
                    via, seen | {package}
                ):
                    return True
            return False

        for package, value in vulnerabilities.items():
            if (
                not isinstance(value, dict)
                or str(value.get("severity", "")).lower() not in fail
            ):
                continue
            if not isinstance(package, str) or not package:
                raise SupplyChainError("critical npm finding is malformed")
            if not has_blocking_advisory(package, frozenset()):
                raise SupplyChainError(
                    "critical npm dependency chain has no blocking advisory identity"
                )
            # npm repeats impact through every transitive dependent. Emit only
            # the actual advisory-bearing package; validate the chain above.
            advisories: set[str] = set()
            for via in value.get("via") or []:
                if (
                    isinstance(via, dict)
                    and str(via.get("severity", "")).lower() in fail
                ):
                    advisory = str(
                        via.get("url") or via.get("source") or via.get("name") or ""
                    )
                    if advisory:
                        advisories.add(advisory)
            if not advisories:
                continue
            nodes = value.get("nodes") or []
            if not isinstance(nodes, list):
                raise SupplyChainError("critical npm finding is malformed")
            versions = _npm_versions(root, policy, scope, package, nodes)
            for version in versions:
                for advisory in advisories:
                    findings.add(
                        Finding("node-vulnerability", scope, advisory, package, version)
                    )
    elif scanner == "trivy":
        results = report.get("Results")
        if (
            report.get("SchemaVersion") != 2
            or not isinstance(report.get("ArtifactName"), str)
            or not report["ArtifactName"]
            or not isinstance(report.get("ArtifactType"), str)
            or not report["ArtifactType"]
            or not isinstance(results, list)
            or not results
        ):
            raise SupplyChainError("Trivy report is missing or malformed")
        vuln_fail = {
            str(value).upper()
            for value in policy["audit_policy"]["image_fail_severities"]
        }
        license_fail = {
            str(value).upper()
            for value in policy["audit_policy"]["license_fail_severities"]
        }
        for result in results:
            if not isinstance(result, dict):
                raise SupplyChainError("Trivy result is malformed")
            for vuln in result.get("Vulnerabilities") or []:
                if not isinstance(vuln, dict):
                    raise SupplyChainError("Trivy vulnerability is malformed")
                if str(vuln.get("Severity", "")).upper() in vuln_fail:
                    findings.add(
                        Finding(
                            "image-vulnerability",
                            scope,
                            str(vuln.get("VulnerabilityID", "")),
                            str(vuln.get("PkgName", "")),
                            str(vuln.get("InstalledVersion", "")),
                        )
                    )
            for license_item in result.get("Licenses") or []:
                if not isinstance(license_item, dict):
                    raise SupplyChainError("Trivy license finding is malformed")
                if str(license_item.get("Severity", "")).upper() in license_fail:
                    for package, version in _trivy_license_identities(
                        root, report, result, license_item
                    ):
                        findings.add(
                            Finding(
                                "license",
                                scope,
                                str(license_item.get("Name", "")),
                                package,
                                version,
                            )
                        )
    else:
        raise SupplyChainError("unsupported scanner")
    if any(not all(finding.key()) for finding in findings):
        raise SupplyChainError("scanner finding lacks an exact identity")
    return sorted(findings, key=Finding.key)


def evaluate_report(
    scanner: str,
    report_path: Path,
    *,
    scope: str,
    root: Path = REPO_ROOT,
    policy_path: Path = POLICY_PATH,
    exceptions_path: Path = EXCEPTIONS_PATH,
) -> int:
    policy = load_policy(policy_path)
    exceptions = load_exceptions(policy, exceptions_path)
    report = _load_json(report_path)
    findings = findings_from_report(
        scanner, report, scope=scope, root=root, policy=policy
    )
    unwaived = [finding for finding in findings if finding.key() not in exceptions]
    if unwaived:
        for finding in unwaived:
            print(
                f"BLOCKED control={finding.control} scope={finding.scope} advisory={finding.advisory_id} package={finding.package} version={finding.installed_version}",
                file=sys.stderr,
            )
        raise SupplyChainError(
            f"{len(unwaived)} unwaived blocking supply-chain finding(s)"
        )
    print(
        json.dumps(
            {
                "blocking_findings": 0,
                "scanner": scanner,
                "scope": scope,
                "waived_findings": len(findings),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def create_scan_predicate(
    report_path: Path,
    output_path: Path,
    *,
    scope: str,
    artifact_name: str,
    artifact_digest: str,
    artifact_type: str,
    report_artifact_name: str,
    source_git_sha: str,
    tree_hash: str,
) -> None:
    policy = load_policy()
    evaluate_report("trivy", report_path, scope=scope)
    report = _load_json(report_path)
    if (
        artifact_name not in INTERNAL_IMAGE_REPOSITORIES
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest)
        or artifact_type != "container_image"
        or report.get("ArtifactName") != report_artifact_name
        or report.get("ArtifactType") != artifact_type
        or not GIT_SHA_RE.fullmatch(source_git_sha)
        or not GIT_SHA_RE.fullmatch(tree_hash)
    ):
        raise SupplyChainError("scan predicate target or source binding is invalid")
    predicate = {
        "schema_version": 2,
        "artifact": {
            "digest": artifact_digest,
            "name": artifact_name,
            "type": artifact_type,
        },
        "scanner": {
            "license_confidence_level": policy["audit_policy"][
                "license_confidence_level"
            ],
            "license_full_scan": policy["audit_policy"]["license_full_scan"],
            "name": "trivy",
            "version": policy["audit_policy"]["trivy_version"],
        },
        "source": {"git_sha": source_git_sha, "tree_hash": tree_hash},
        "scope": scope,
        "result": "pass",
        "report_sha256": _sha256(report_path),
        "policy_sha256": _sha256(POLICY_PATH),
        "exceptions_sha256": _sha256(EXCEPTIONS_PATH),
    }
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(predicate, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    image = sub.add_parser("verify-image-ref")
    image.add_argument("reference")
    report = sub.add_parser("evaluate-report")
    report.add_argument(
        "--scanner", required=True, choices=("npm-audit", "pip-audit", "trivy")
    )
    report.add_argument("--scope", required=True)
    report.add_argument("--report", required=True, type=Path)
    predicate = sub.add_parser("create-scan-predicate")
    predicate.add_argument("--scope", required=True)
    predicate.add_argument("--report", required=True, type=Path)
    predicate.add_argument("--output", required=True, type=Path)
    predicate.add_argument("--artifact-name", required=True)
    predicate.add_argument("--artifact-digest", required=True)
    predicate.add_argument("--artifact-type", required=True)
    predicate.add_argument("--report-artifact-name", required=True)
    predicate.add_argument("--source-git-sha", required=True)
    predicate.add_argument("--tree-hash", required=True)
    materialized = sub.add_parser("verify-materialized-images")
    materialized.add_argument("--manifest", action="append", required=True)
    materialized.add_argument("--images-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            verify_repository()
            print('{"supply_chain_policy":"verified"}')
        elif args.command == "verify-image-ref":
            if (
                not DIGEST_REF_RE.fullmatch(args.reference)
                or _image_repository(args.reference) != BACKEND_IMAGE_REPOSITORY
            ):
                raise SupplyChainError(
                    "image reference must be the exact backend-v2 tag@sha256 repository"
                )
            print('{"image_reference":"verified"}')
        elif args.command == "evaluate-report":
            evaluate_report(args.scanner, args.report, scope=args.scope)
        elif args.command == "create-scan-predicate":
            create_scan_predicate(
                args.report,
                args.output,
                scope=args.scope,
                artifact_name=args.artifact_name,
                artifact_digest=args.artifact_digest,
                artifact_type=args.artifact_type,
                report_artifact_name=args.report_artifact_name,
                source_git_sha=args.source_git_sha,
                tree_hash=args.tree_hash,
            )
        else:
            verify_materialized_images(args.manifest, args.images_file, root=REPO_ROOT)
    except SupplyChainError as exc:
        parser.exit(2, f"supply-chain gate failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
