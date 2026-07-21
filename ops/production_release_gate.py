#!/usr/bin/env python3
"""Fail-closed production release freeze gate.

The checked-in state is deliberately frozen.  GATE-10 documents are validated
so malformed or tampered future inputs remain testable, but lifting the freeze
is disabled until the P1 release path binds the exact deployed artifacts.
Environment variables are intentionally not consulted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "ops" / "production-release-state.json"
APPROVAL_PATH = REPO_ROOT / "ops" / "production-release-gate10-approval.json"
MANIFEST_PATH = REPO_ROOT / "ops" / "production-release-manifest.json"
REMEDIATION_APPROVAL_PATH = Path(
    "/etc/sealai/approvals/gate-08-remediation-control.json"
)
OPERATIONAL_CONTROL_APPROVAL_PATH = Path(
    "/etc/sealai/approvals/gate-08-operational-controls.json"
)
LOW_RISK_EMERGENCY_APPROVAL_PATH = Path(
    "/etc/sealai/approvals/gate-11-low-risk-emergency.json"
)
STAGING_BUILD_APPROVAL_PATH = Path("/etc/sealai/approvals/gate-12-staging-build.json")
LIVE_PRODUCTION_REPO = Path("/home/thorsten/sealai")
GATE10_LIFT_IMPLEMENTED = False
GATE_DOCUMENT_PATHS = frozenset(
    {
        "ops/production-release-state.json",
        "ops/production-release-gate10-approval.json",
        "ops/production-release-manifest.json",
    }
)

MUTATING_OPERATIONS = frozenset(
    {
        "build",
        "pull",
        "deploy",
        "migration",
        "dashboard-publish",
    }
)
RECOVERY_OPERATION = "recovery-start-existing"
REMEDIATION_CONTROL_OPERATION = "remediation-control-install"
OPERATIONAL_CONTROL_OPERATION = "operational-control-install"
LOW_RISK_EMERGENCY_OPERATION = "low-risk-emergency-deploy"
STAGING_BUILD_OPERATION = "staging-build"
OPERATIONS = MUTATING_OPERATIONS | {
    RECOVERY_OPERATION,
    REMEDIATION_CONTROL_OPERATION,
    OPERATIONAL_CONTROL_OPERATION,
    LOW_RISK_EMERGENCY_OPERATION,
    STAGING_BUILD_OPERATION,
}

# GATE-11 (scoped low-risk emergency corridor, owner decision 2026-07-18): a narrow,
# additive exception to the GATE-10 freeze for changes that are fully tested and that
# the owner has personally read and approved -- NOT a general deploy path. Any path
# matching one of these prefixes exactly, or nested under one of these directory
# prefixes, disqualifies the WHOLE diff from the corridor, regardless of what else it
# contains. This is a blocklist, not an allowlist: everything else is permitted,
# provided the diff is non-empty, the approval is valid, and the checkout is clean.
# Extending this list is an owner decision, never an agent judgment call.
GATE11_EXCLUDED_PATH_PREFIXES = (
    "ops/",
    ".github/workflows/",
    ".claude/",
    "docker-compose",  # docker-compose.yml, docker-compose.deploy.yml, docker-compose.*.yml
    "backend/sealai_v2/config/settings.py",
    "backend/sealai_v2/security/",
    "backend/sealai_v2/core/output_guard.py",
    "backend/sealai_v2/db/migrations/",
    "backend/Dockerfile",
    "frontend/Dockerfile",
    "frontend-v2/Dockerfile",
    "keycloak/",
)


def _path_excluded_from_low_risk_corridor(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in GATE11_EXCLUDED_PATH_PREFIXES)


REMEDIATION_CONTROL_ARTIFACTS = frozenset(
    {
        "docs/ops/docker-disk-guard.md",
        "docs/ops/production-release-freeze.md",
        "ops/bootstrap_gate08_remediation_control.py",
        "ops/disk-guard.example.json",
        "ops/docker-disk-guard.sh",
        "ops/docker_disk_guard.py",
        "ops/gate08_legacy_unit_retirement.py",
        "ops/hash_verified_python_loader.py",
        "ops/install-disk-guard.sh",
        "ops/production-deploy-remote-entrypoint.sh",
        "ops/production-release-gate-check.sh",
        "ops/production-release-state.json",
        "ops/production_release_gate.py",
        "ops/production-storage-lease.sh",
        "ops/sudoers/sealai-storage-preflight",
        "ops/schemas/gate08-legacy-units.schema.json",
        "ops/systemd/sealai-disk-guard.service",
        "ops/systemd/sealai-disk-guard.timer",
        "ops/tmpfiles/sealai-storage-mutation.conf",
    }
)

OPERATIONAL_CONTROL_ARTIFACTS = frozenset(
    {
        "docs/ops/operational-control-install.md",
        "docs/ops/p0-operational-gate-unblock.md",
        "docs/ops/production-release-freeze.md",
        "ops/bootstrap_gate08_operational_controls.py",
        "ops/credential_cutover.py",
        "ops/install-operational-controls.sh",
        "ops/permission_manifest.py",
        "ops/production-release-state.json",
        "ops/production_release_gate.py",
        "ops/schemas/credential-cutover-approval.schema.json",
        "ops/schemas/gate08-operational-controls.schema.json",
        "ops/schemas/permission-manifest.schema.json",
    }
)
OPERATIONAL_CONTROL_TARGETS = {
    "ops/credential_cutover.py": "/usr/local/libexec/sealai/credential-cutover.py",
    "ops/permission_manifest.py": "/usr/local/libexec/sealai/permission-manifest.py",
    "ops/schemas/credential-cutover-approval.schema.json": (
        "/usr/local/share/sealai/schemas/credential-cutover-approval.schema.json"
    ),
    "ops/schemas/permission-manifest.schema.json": (
        "/usr/local/share/sealai/schemas/permission-manifest.schema.json"
    ),
}
OPERATIONAL_CONTROL_MODES = {
    "/usr/local/libexec/sealai/credential-cutover.py": "0755",
    "/usr/local/libexec/sealai/permission-manifest.py": "0755",
    "/usr/local/share/sealai/schemas/credential-cutover-approval.schema.json": "0644",
    "/usr/local/share/sealai/schemas/permission-manifest.schema.json": "0644",
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
GIT_ENV = {
    "HOME": "/root",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_PROTOCOL_FROM_USER": "0",
    "GIT_ALLOW_PROTOCOL": "file",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}


class GateConfigurationError(RuntimeError):
    """The gate inputs cannot prove that a release is authorized."""


class GateDenied(RuntimeError):
    """The gate is valid but denies this operation."""


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    operation: str
    reason: str
    state_id: str
    required_gate: str
    source_git_sha: str | None = None
    approval_id: str | None = None
    artifact_sha256: dict[str, str] | None = None
    install_targets: dict[str, str] | None = None
    target_preconditions: dict[str, dict[str, object]] | None = None
    base_git_sha: str | None = None

    def as_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "allowed": self.allowed,
            "operation": self.operation,
            "reason": self.reason,
            "state_id": self.state_id,
            "required_gate": self.required_gate,
        }
        if self.source_git_sha is not None:
            value["source_git_sha"] = self.source_git_sha
        if self.approval_id is not None:
            value["approval_id"] = self.approval_id
        if self.artifact_sha256 is not None:
            value["artifact_sha256"] = self.artifact_sha256
        if self.install_targets is not None:
            value["install_targets"] = self.install_targets
        if self.target_preconditions is not None:
            value["target_preconditions"] = self.target_preconditions
        if self.base_git_sha is not None:
            value["base_git_sha"] = self.base_git_sha
        return value


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateConfigurationError(
            "required gate document is missing or invalid"
        ) from exc
    if not isinstance(value, dict):
        raise GateConfigurationError("gate document root must be an object")
    return value, raw


def _load_private_json(path: Path) -> tuple[dict[str, Any], bytes]:
    """Read one root-owned private receipt without following a symlink."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise GateConfigurationError(
            "required private approval is unavailable"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 64 * 1024
        ):
            raise GateConfigurationError("required private approval is unsafe")
        raw = os.read(descriptor, 64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            raise GateConfigurationError("required private approval is too large")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateConfigurationError("required private approval is invalid") from exc
    if not isinstance(value, dict):
        raise GateConfigurationError("private approval root must be an object")
    return value, raw


def _parse_utc_timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        raise GateConfigurationError(f"{label} must be an exact UTC timestamp")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:  # defensive: the regex is deliberately only structural
        raise GateConfigurationError(f"{label} is invalid") from exc


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateConfigurationError(f"{label} must be an object")
    return value


def _require_nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GateConfigurationError(f"{label} must be a non-empty string")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise GateConfigurationError(f"{label} contains missing or unexpected fields")


def _validate_active_state(
    state: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    _require_exact_keys(
        state,
        {"schema_version", "state_id", "freeze", "unfreeze_requirements"},
        "production release state",
    )
    if state.get("schema_version") != 1:
        raise GateConfigurationError("unsupported production release state schema")
    state_id = _require_nonempty(state.get("state_id"), "state_id")
    freeze = _require_mapping(state.get("freeze"), "freeze")
    _require_exact_keys(
        freeze,
        {"active", "activated_at", "required_gate", "reason_codes"},
        "freeze",
    )
    if not isinstance(freeze.get("active"), bool):
        raise GateConfigurationError("freeze.active must be a boolean")
    if freeze.get("required_gate") != "GATE-10":
        raise GateConfigurationError("freeze.required_gate must be GATE-10")
    if not UTC_RE.fullmatch(str(freeze.get("activated_at", ""))):
        raise GateConfigurationError(
            "freeze.activated_at must be an exact UTC timestamp"
        )
    reason_codes = freeze.get("reason_codes")
    if (
        not isinstance(reason_codes, list)
        or not reason_codes
        or any(not isinstance(reason, str) or not reason for reason in reason_codes)
        or len(reason_codes) != len(set(reason_codes))
    ):
        raise GateConfigurationError(
            "freeze.reason_codes must be unique non-empty strings"
        )
    requirements = _require_mapping(
        state.get("unfreeze_requirements"), "unfreeze_requirements"
    )
    _require_exact_keys(
        requirements,
        {
            "approval_file",
            "manifest_file",
            "approval_scope",
            "required_readiness_claims",
            "required_manifest_hashes",
        },
        "unfreeze_requirements",
    )
    if (
        requirements.get("approval_file")
        != "ops/production-release-gate10-approval.json"
    ):
        raise GateConfigurationError("approval path is not the fixed GATE-10 path")
    if requirements.get("manifest_file") != "ops/production-release-manifest.json":
        raise GateConfigurationError("manifest path is not the fixed release path")
    if requirements.get("approval_scope") != "production-release-freeze-lift":
        raise GateConfigurationError("approval scope is invalid")
    required_hashes = requirements.get("required_manifest_hashes")
    expected_hashes = {
        "served_tree_sha256",
        "backend_image_digest",
        "frontend_image_digest",
        "dashboard_artifact_sha256",
        "database_migration_sha256",
        "rollback_plan_sha256",
        "evidence_manifest_sha256",
    }
    if not isinstance(required_hashes, list) or set(required_hashes) != expected_hashes:
        raise GateConfigurationError(
            "required manifest hashes are not the fixed release set"
        )
    if len(required_hashes) != len(expected_hashes):
        raise GateConfigurationError("required manifest hashes contain duplicates")
    required_claims = requirements.get("required_readiness_claims")
    expected_claims = {
        "P0_SECRETS_CONTAINED",
        "P0_STORAGE_STABLE",
        "P0_REDIS_STABLE",
        "RELEASE_GATE_FAIL_CLOSED",
    }
    if not isinstance(required_claims, list) or set(required_claims) != expected_claims:
        raise GateConfigurationError(
            "required readiness claims are not the fixed P0 set"
        )
    if len(required_claims) != len(expected_claims):
        raise GateConfigurationError("required readiness claims contain duplicates")
    return state_id, freeze, requirements


def _validate_unfreeze_documents(
    *,
    state_id: str,
    requirements: dict[str, Any],
    approval: dict[str, Any],
    manifest: dict[str, Any],
    manifest_raw: bytes,
) -> None:
    _require_exact_keys(
        approval,
        {
            "schema_version",
            "gate_id",
            "approval_id",
            "decision",
            "scope",
            "freeze_state_id",
            "approved_by",
            "approved_at",
            "release_manifest_id",
            "release_manifest_sha256",
        },
        "approval",
    )
    if approval.get("schema_version") != 1 or approval.get("gate_id") != "GATE-10":
        raise GateConfigurationError("approval is not a GATE-10 v1 document")
    if approval.get("decision") != "APPROVED":
        raise GateConfigurationError("GATE-10 is not approved")
    if approval.get("scope") != requirements.get("approval_scope"):
        raise GateConfigurationError("GATE-10 approval scope does not match")
    if approval.get("freeze_state_id") != state_id:
        raise GateConfigurationError("GATE-10 approval is bound to a different freeze")
    _require_nonempty(approval.get("approval_id"), "approval.approval_id")
    _require_nonempty(approval.get("approved_by"), "approval.approved_by")
    if not UTC_RE.fullmatch(str(approval.get("approved_at", ""))):
        raise GateConfigurationError(
            "approval.approved_at must be an exact UTC timestamp"
        )

    _require_exact_keys(
        manifest,
        {
            "schema_version",
            "manifest_id",
            "freeze_state_id",
            "source_git_sha",
            "readiness",
            "hashes",
        },
        "release manifest",
    )
    if manifest.get("schema_version") != 1:
        raise GateConfigurationError("unsupported release manifest schema")
    manifest_id = _require_nonempty(manifest.get("manifest_id"), "manifest.manifest_id")
    if manifest.get("freeze_state_id") != state_id:
        raise GateConfigurationError("release manifest is bound to a different freeze")
    if approval.get("release_manifest_id") != manifest_id:
        raise GateConfigurationError("approval references a different release manifest")
    if not GIT_SHA_RE.fullmatch(str(manifest.get("source_git_sha", ""))):
        raise GateConfigurationError("release manifest source_git_sha is invalid")

    readiness = _require_mapping(manifest.get("readiness"), "manifest.readiness")
    required_claims = requirements["required_readiness_claims"]
    if set(readiness) != set(required_claims):
        raise GateConfigurationError(
            "release readiness claim set is incomplete or unexpected"
        )
    if any(readiness.get(claim) is not True for claim in required_claims):
        raise GateConfigurationError("every release readiness claim must be true")

    manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
    if approval.get("release_manifest_sha256") != manifest_hash:
        raise GateConfigurationError(
            "approval does not match the release manifest bytes"
        )

    hashes = _require_mapping(manifest.get("hashes"), "manifest.hashes")
    required_hashes = requirements["required_manifest_hashes"]
    if set(hashes) != set(required_hashes):
        raise GateConfigurationError(
            "release manifest hash set is incomplete or unexpected"
        )
    for name in required_hashes:
        value = hashes.get(name)
        pattern = DIGEST_RE if name.endswith("_image_digest") else SHA256_RE
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise GateConfigurationError(f"release manifest hash is invalid: {name}")


def _assert_committed_versioned(path: Path) -> None:
    try:
        relative = path.resolve().relative_to(REPO_ROOT)
    except ValueError as exc:
        raise GateConfigurationError("gate document is outside the repository") from exc
    tracked = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(REPO_ROOT),
            "ls-files",
            "--error-unmatch",
            "--",
            str(relative),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=GIT_ENV,
        check=False,
    )
    unchanged = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(REPO_ROOT),
            "diff",
            "--quiet",
            "HEAD",
            "--",
            str(relative),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=GIT_ENV,
        check=False,
    )
    if tracked.returncode != 0 or unchanged.returncode != 0:
        raise GateConfigurationError(
            "unfreeze documents must be committed and unchanged"
        )


def _git(*args: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        env=GIT_ENV,
        check=False,
    )
    if result.returncode != 0:
        raise GateConfigurationError(
            "cannot establish the committed gate-control checkout"
        )
    return result.stdout


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(REPO_ROOT),
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=GIT_ENV,
        check=False,
    )
    return result.returncode == 0


def _assert_clean_checkout() -> None:
    tracked = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(REPO_ROOT),
            "diff",
            "--quiet",
            "HEAD",
            "--",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=GIT_ENV,
        check=False,
    )
    untracked = _git("ls-files", "--others", "--exclude-standard").splitlines()
    if tracked.returncode != 0 or untracked:
        raise GateConfigurationError("gate-control checkout must be clean")


def _assert_trusted_path(
    path: Path, *, leaf_directory: bool, root_only: bool = False
) -> None:
    """Reject symlinks, untrusted owners, and writable path components."""

    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    trusted_owners = {0} if root_only else {0, os.geteuid()}
    for index, part in enumerate((absolute.anchor, *absolute.parts[1:])):
        if index:
            current /= part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise GateConfigurationError(
                "trusted checkout path is unavailable"
            ) from exc
        is_leaf = current == absolute
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in trusted_owners
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise GateConfigurationError("trusted checkout path is unsafe")
        expected_directory = leaf_directory if is_leaf else True
        if expected_directory and not stat.S_ISDIR(metadata.st_mode):
            raise GateConfigurationError("trusted checkout directory is invalid")
        if not expected_directory and not stat.S_ISREG(metadata.st_mode):
            raise GateConfigurationError("trusted checkout artifact is invalid")


def _assert_root_checkout() -> None:
    if os.geteuid() != 0:
        raise GateConfigurationError("remediation control install requires root")
    _assert_trusted_path(REPO_ROOT, leaf_directory=True, root_only=True)
    _assert_trusted_path(REPO_ROOT / ".git", leaf_directory=True, root_only=True)


def _artifact_sha256(relative_path: str) -> str:
    path = REPO_ROOT / relative_path
    _assert_trusted_path(path, leaf_directory=False)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise GateConfigurationError(
            "remediation control artifact is unavailable"
        ) from exc
    digest = hashlib.sha256()
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise GateConfigurationError("remediation control artifact is unsafe")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


# GATE-10 P1 phase 1 (source-derived hashes, owner decision 2026-07-20): the two
# required_manifest_hashes fields verifiable with zero new trust surface -- no Docker, no
# network, no owner document, just the committed tree. This is the exact recipe
# ops/tree-hash.sh already uses and tests (backend/tests/test_tree_hash.py), reimplemented
# in-process so it can run inside the gate's fail-closed, empty-environment invocation
# instead of shelling out to a second script. Extending SERVED_TREE_PATHSPECS or adding a
# new pathspec set here must stay in lockstep with ops/tree-hash.sh -- see
# test_served_tree_hash_matches_tree_hash_script, which cross-checks the two by golden
# comparison so they can never silently drift apart.
SERVED_TREE_PATHSPECS: tuple[str, ...] = (
    "backend/sealai_v2",
    ":(exclude)backend/sealai_v2/eval",
    ":(exclude)backend/sealai_v2/tests",
    "backend/requirements-v2.txt",
    "backend/.dockerignore",
    "backend/Dockerfile.v2",
    "backend/docker-entrypoint-v2.sh",
)
DATABASE_MIGRATION_PATHSPECS: tuple[str, ...] = ("backend/sealai_v2/db/migrations",)


def _git_write_tree(pathspecs: tuple[str, ...]) -> str:
    """The ops/tree-hash.sh throwaway-index recipe, in-process: a private
    GIT_INDEX_FILE in a fresh 0700 temp directory, `git add -A` the fixed pathspecs into
    it, `git write-tree`. Never touches the real index or working tree. Returns the raw
    git tree-object id (40 hex chars in this repo -- it is a SHA-1 repository, verified
    via `git rev-parse --show-object-format` -- NOT a SHA-256; callers that need a
    SHA256_RE-shaped value must wrap the result, see _served_tree_sha256)."""

    stage = tempfile.mkdtemp(prefix="sealai-gate10-index-")
    try:
        env = {**GIT_ENV, "GIT_INDEX_FILE": os.path.join(stage, "index")}
        add = subprocess.run(
            ["/usr/bin/git", "-C", str(REPO_ROOT), "add", "-A", "--", *pathspecs],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            check=False,
        )
        if add.returncode != 0:
            raise GateConfigurationError(
                "cannot stage the real release artifact for hashing"
            )
        tree = subprocess.run(
            ["/usr/bin/git", "-C", str(REPO_ROOT), "write-tree"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        tree_id = tree.stdout.strip()
        if tree.returncode != 0 or not GIT_SHA_RE.fullmatch(tree_id):
            raise GateConfigurationError(
                "cannot compute the real release artifact tree hash"
            )
        return tree_id
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _served_tree_sha256() -> str:
    return hashlib.sha256(
        _git_write_tree(SERVED_TREE_PATHSPECS).encode("ascii")
    ).hexdigest()


def _database_migration_sha256() -> str:
    return hashlib.sha256(
        _git_write_tree(DATABASE_MIGRATION_PATHSPECS).encode("ascii")
    ).hexdigest()


# Registry, not a hardcoded if/elif chain -- naturally extensible for later phases (e.g. an
# _IMAGE_ATTESTATION_HASH_VERIFIERS registry once Docker/network verification is added).
# Named for what each entry does now; "phase" is planning vocabulary, not domain language.
_SOURCE_DERIVED_HASH_VERIFIERS: dict[str, Callable[[], str]] = {
    "served_tree_sha256": _served_tree_sha256,
    "database_migration_sha256": _database_migration_sha256,
}


def _verify_source_derived_artifact_hashes(hashes: dict[str, Any]) -> None:
    """Recompute each source-derived manifest hash from the real checked-out tree and
    compare -- never trust the manifest's own claim. Must only be called after
    _assert_two_commit_binding has already proven HEAD is the exact control commit over a
    clean checkout (see its call site in evaluate()); hashing an unproven checkout would
    let a dirty or manipulated tree be hashed instead of the real released one."""

    for name, verifier in _SOURCE_DERIVED_HASH_VERIFIERS.items():
        if verifier() != hashes.get(name):
            raise GateConfigurationError(
                f"release manifest hash does not match the real artifact: {name}"
            )


# GATE-10 P1 phase 2 (backend image attestation, owner decision 2026-07-21): binds
# backend_image_digest to a real GitHub Actions build-provenance + SBOM attestation,
# verified through Sigstore/Rekor by the existing ops/verify-image-attestations.sh +
# ops/verify_attestation_payload.py pipeline -- the same one ops/release-backend-v2.sh
# already runs before a candidate image is promoted. Unlike the phase 1 source-derived
# hashes, this genuinely needs Docker and network: verifying a supply-chain signature
# means reaching the transparency log, there is no local recomputation that proves
# provenance. frontend_image_digest stays format-checked only -- no attested build
# workflow exists for the frontend image at all yet (build-and-push.yml only builds
# backend-v2), so there is nothing here to verify against until that pipeline exists.
_BACKEND_IMAGE_NAME = "ghcr.io/jungt72/sealai-backend-v2"
_BACKEND_IMAGE_WORKFLOW = ".github/workflows/build-and-push.yml"
_VERIFY_IMAGE_ATTESTATIONS_SCRIPT = (
    Path(__file__).resolve().parent / "verify-image-attestations.sh"
)


def _verify_backend_image_attestation(digest: str, source_git_sha: str) -> None:
    if not DIGEST_RE.fullmatch(str(digest)):
        raise GateConfigurationError(
            "release manifest hash is not a valid digest: backend_image_digest"
        )
    image_ref = f"{_BACKEND_IMAGE_NAME}@{digest}"
    result = subprocess.run(
        [
            "/bin/bash",
            "-p",
            str(_VERIFY_IMAGE_ATTESTATIONS_SCRIPT),
            image_ref,
            source_git_sha,
            _BACKEND_IMAGE_WORKFLOW,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise GateConfigurationError(
            "backend_image_digest failed provenance/SBOM attestation verification"
            + (f": {detail}" if detail else "")
        )


# Registry, matching _SOURCE_DERIVED_HASH_VERIFIERS's shape but keyed to verifiers that
# take the claimed value plus the already-proven source_git_sha -- attestation
# verification checks *provenance* of a claimed digest rather than recomputing it.
_IMAGE_ATTESTATION_HASH_VERIFIERS: dict[str, Callable[[str, str], None]] = {
    "backend_image_digest": _verify_backend_image_attestation,
}


def _verify_image_attestation_hashes(
    hashes: dict[str, Any], source_git_sha: str
) -> None:
    """Verify each attestation-backed manifest hash's provenance. Must only be called
    after _assert_two_commit_binding has already proven source_git_sha is the exact,
    clean control commit -- same precondition as _verify_source_derived_artifact_hashes,
    for the same reason: an unproven source_git_sha would let a forged commit stand in
    for the real one during attestation verification."""

    for name, verifier in _IMAGE_ATTESTATION_HASH_VERIFIERS.items():
        verifier(hashes[name], source_git_sha)


def _validate_remediation_control_approval(
    approval_path: Path, *, require_versioned: bool
) -> tuple[str, str, dict[str, str]]:
    if REPO_ROOT.resolve() == LIVE_PRODUCTION_REPO:
        raise GateConfigurationError(
            "remediation control install must run from a non-live root-owned checkout"
        )
    if require_versioned:
        _assert_root_checkout()
        _assert_trusted_path(
            approval_path,
            leaf_directory=False,
            root_only=True,
        )
    approval, _ = _load_private_json(approval_path)
    _require_exact_keys(
        approval,
        {
            "schema_version",
            "gate_id",
            "decision",
            "scope",
            "approval_id",
            "approved_by",
            "approved_at",
            "expires_at",
            "source_git_sha",
            "artifact_sha256",
        },
        "GATE-08 remediation approval",
    )
    if (
        approval.get("schema_version") != 1
        or approval.get("gate_id") != "GATE-08"
        or approval.get("decision") != "APPROVED"
        or approval.get("scope") != "p0-remediation-control-install"
    ):
        raise GateConfigurationError(
            "approval does not authorize remediation control install"
        )
    approval_id = _require_nonempty(approval.get("approval_id"), "approval_id")
    _require_nonempty(approval.get("approved_by"), "approved_by")
    approved_at = _parse_utc_timestamp(approval.get("approved_at"), "approved_at")
    expires_at = _parse_utc_timestamp(approval.get("expires_at"), "expires_at")
    now = dt.datetime.now(dt.timezone.utc)
    if approved_at > now + dt.timedelta(minutes=5):
        raise GateConfigurationError("remediation approval is future-dated")
    if expires_at <= now or expires_at > approved_at + dt.timedelta(hours=4):
        raise GateConfigurationError("remediation approval is expired or over-broad")

    source_git_sha = str(approval.get("source_git_sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", source_git_sha):
        raise GateConfigurationError("remediation approval source commit is invalid")
    current_head = _git("rev-parse", "HEAD").strip()
    if source_git_sha != current_head:
        raise GateConfigurationError("remediation approval is bound to another commit")

    artifact_hashes = _require_mapping(
        approval.get("artifact_sha256"), "artifact_sha256"
    )
    if set(artifact_hashes) != REMEDIATION_CONTROL_ARTIFACTS:
        raise GateConfigurationError("remediation approval artifact set is not exact")
    for relative_path in sorted(REMEDIATION_CONTROL_ARTIFACTS):
        expected = artifact_hashes.get(relative_path)
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise GateConfigurationError(
                "remediation approval artifact hash is invalid"
            )
        if require_versioned:
            _assert_committed_versioned(REPO_ROOT / relative_path)
        if expected != _artifact_sha256(relative_path):
            raise GateConfigurationError("remediation control artifact hash mismatch")
    if require_versioned:
        _assert_clean_checkout()
    return (
        approval_id,
        source_git_sha,
        {
            relative_path: str(artifact_hashes[relative_path])
            for relative_path in sorted(REMEDIATION_CONTROL_ARTIFACTS)
        },
    )


def _validate_operational_target_preconditions(
    value: Any,
) -> dict[str, dict[str, object]]:
    preconditions = _require_mapping(value, "target_preconditions")
    expected_targets = set(OPERATIONAL_CONTROL_TARGETS.values())
    if set(preconditions) != expected_targets:
        raise GateConfigurationError("operational target precondition set is not exact")
    normalized: dict[str, dict[str, object]] = {}
    for target in sorted(expected_targets):
        item = _require_mapping(preconditions.get(target), "target precondition")
        if item.get("state") == "ABSENT":
            _require_exact_keys(item, {"state"}, "absent target precondition")
        elif item.get("state") == "PRESENT":
            _require_exact_keys(
                item,
                {"state", "type", "sha256", "uid", "gid", "mode"},
                "present target precondition",
            )
            if (
                item.get("type") != "file"
                or item.get("uid") != 0
                or item.get("gid") != 0
                or item.get("mode") != OPERATIONAL_CONTROL_MODES[target]
                or not isinstance(item.get("sha256"), str)
                or not SHA256_RE.fullmatch(str(item["sha256"]))
            ):
                raise GateConfigurationError(
                    "present operational target precondition is unsafe"
                )
        else:
            raise GateConfigurationError("operational target state is invalid")
        normalized[target] = dict(item)
    return normalized


def _validate_operational_control_approval(
    approval_path: Path, *, require_versioned: bool
) -> tuple[
    str,
    str,
    dict[str, str],
    dict[str, str],
    dict[str, dict[str, object]],
]:
    if REPO_ROOT.resolve() == LIVE_PRODUCTION_REPO:
        raise GateConfigurationError(
            "operational control install must run from a non-live root-owned checkout"
        )
    if require_versioned:
        _assert_root_checkout()
        _assert_trusted_path(approval_path, leaf_directory=False, root_only=True)
    approval, _ = _load_private_json(approval_path)
    _require_exact_keys(
        approval,
        {
            "schema_version",
            "gate_id",
            "operation",
            "decision",
            "scope",
            "approval_id",
            "owner",
            "approved_at",
            "expires_at",
            "source_git_sha",
            "artifact_sha256",
            "install_targets",
            "target_preconditions",
        },
        "GATE-08 operational controls approval",
    )
    if (
        approval.get("schema_version") != 1
        or approval.get("gate_id") != "GATE-08"
        or approval.get("operation") != OPERATIONAL_CONTROL_OPERATION
        or approval.get("decision") != "APPROVED"
        or approval.get("scope") != "p0-operational-control-install"
    ):
        raise GateConfigurationError(
            "approval does not authorize operational control install"
        )
    approval_id = _require_nonempty(approval.get("approval_id"), "approval_id")
    _require_nonempty(approval.get("owner"), "owner")
    approved_at = _parse_utc_timestamp(approval.get("approved_at"), "approved_at")
    expires_at = _parse_utc_timestamp(approval.get("expires_at"), "expires_at")
    now = dt.datetime.now(dt.timezone.utc)
    if approved_at > now + dt.timedelta(minutes=5):
        raise GateConfigurationError("operational approval is future-dated")
    if expires_at <= now or expires_at > approved_at + dt.timedelta(hours=4):
        raise GateConfigurationError("operational approval is expired or over-broad")

    source_git_sha = str(approval.get("source_git_sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", source_git_sha):
        raise GateConfigurationError("operational approval source commit is invalid")
    if source_git_sha != _git("rev-parse", "HEAD").strip():
        raise GateConfigurationError("operational approval is bound to another commit")

    install_targets = _require_mapping(
        approval.get("install_targets"), "install_targets"
    )
    if install_targets != OPERATIONAL_CONTROL_TARGETS:
        raise GateConfigurationError("operational install target set is not exact")
    preconditions = _validate_operational_target_preconditions(
        approval.get("target_preconditions")
    )
    artifact_hashes = _require_mapping(
        approval.get("artifact_sha256"), "artifact_sha256"
    )
    if set(artifact_hashes) != OPERATIONAL_CONTROL_ARTIFACTS:
        raise GateConfigurationError("operational approval artifact set is not exact")
    normalized_hashes: dict[str, str] = {}
    for relative_path in sorted(OPERATIONAL_CONTROL_ARTIFACTS):
        expected = artifact_hashes.get(relative_path)
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise GateConfigurationError("operational artifact hash is invalid")
        if require_versioned:
            _assert_committed_versioned(REPO_ROOT / relative_path)
        if expected != _artifact_sha256(relative_path):
            raise GateConfigurationError("operational control artifact hash mismatch")
        normalized_hashes[relative_path] = expected
    if require_versioned:
        _assert_clean_checkout()
    return (
        approval_id,
        source_git_sha,
        normalized_hashes,
        dict(OPERATIONAL_CONTROL_TARGETS),
        preconditions,
    )


def _validate_low_risk_emergency_approval(
    approval_path: Path, *, require_versioned: bool
) -> tuple[str, str, str]:
    """GATE-11: a narrow, additive exception to the GATE-10 freeze. Unlike the GATE-08
    install operations, this does not require a non-live root-owned checkout -- it is
    meant to run from the live production checkout, exactly like a normal deploy. It
    never trusts the approval's own claims about which paths changed: it independently
    diffs ``base_git_sha..source_git_sha`` and rejects the whole batch if any changed
    path matches ``GATE11_EXCLUDED_PATH_PREFIXES``, regardless of what the approval
    document asserts."""

    if require_versioned:
        _assert_trusted_path(approval_path, leaf_directory=False, root_only=True)
    approval, _ = _load_private_json(approval_path)
    _require_exact_keys(
        approval,
        {
            "schema_version",
            "gate_id",
            "decision",
            "scope",
            "approval_id",
            "approved_by",
            "approved_at",
            "expires_at",
            "base_git_sha",
            "source_git_sha",
            "owner_read_diff_confirmation",
            "test_evidence_sha256",
        },
        "GATE-11 low-risk emergency approval",
    )
    if (
        approval.get("schema_version") != 1
        or approval.get("gate_id") != "GATE-11"
        or approval.get("decision") != "APPROVED"
        or approval.get("scope") != "low-risk-emergency-deploy"
    ):
        raise GateConfigurationError(
            "approval does not authorize the low-risk emergency corridor"
        )
    approval_id = _require_nonempty(approval.get("approval_id"), "approval_id")
    _require_nonempty(approval.get("approved_by"), "approved_by")
    if approval.get("owner_read_diff_confirmation") is not True:
        raise GateConfigurationError(
            "GATE-11 approval must confirm the owner read the diff"
        )
    test_evidence = approval.get("test_evidence_sha256")
    if not isinstance(test_evidence, str) or not SHA256_RE.fullmatch(test_evidence):
        raise GateConfigurationError("GATE-11 approval test evidence hash is invalid")

    approved_at = _parse_utc_timestamp(approval.get("approved_at"), "approved_at")
    expires_at = _parse_utc_timestamp(approval.get("expires_at"), "expires_at")
    now = dt.datetime.now(dt.timezone.utc)
    if approved_at > now + dt.timedelta(minutes=5):
        raise GateConfigurationError("GATE-11 approval is future-dated")
    if expires_at <= now or expires_at > approved_at + dt.timedelta(hours=4):
        raise GateConfigurationError("GATE-11 approval is expired or over-broad")

    base_git_sha = str(approval.get("base_git_sha", ""))
    source_git_sha = str(approval.get("source_git_sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", base_git_sha):
        raise GateConfigurationError("GATE-11 approval base commit is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", source_git_sha):
        raise GateConfigurationError("GATE-11 approval source commit is invalid")
    if base_git_sha == source_git_sha:
        raise GateConfigurationError("GATE-11 approval covers an empty commit range")
    current_head = _git("rev-parse", "HEAD").strip()
    if source_git_sha != current_head:
        raise GateConfigurationError("GATE-11 approval is bound to another commit")
    if not _git_is_ancestor(base_git_sha, source_git_sha):
        raise GateConfigurationError(
            "GATE-11 approval base commit is not an ancestor of the source commit"
        )

    changed_paths = [
        line
        for line in _git(
            "diff",
            "--name-only",
            "--no-renames",
            base_git_sha,
            source_git_sha,
            "--",
        ).splitlines()
        if line
    ]
    if not changed_paths:
        raise GateConfigurationError("GATE-11 approval covers an empty diff")
    excluded_hits = [
        path for path in changed_paths if _path_excluded_from_low_risk_corridor(path)
    ]
    if excluded_hits:
        raise GateConfigurationError(
            "GATE-11 diff touches an excluded path: " + ", ".join(sorted(excluded_hits))
        )
    if require_versioned:
        _assert_clean_checkout()
    return approval_id, base_git_sha, source_git_sha


def _validate_staging_build_approval(
    approval_path: Path, *, require_versioned: bool
) -> tuple[str, str, str]:
    """GATE-12: a narrow, additive exception to the GATE-10 freeze, scoped to exactly
    one operation -- rebuilding and restarting the local VPS staging stack
    (``ops/staging/up-staging-v2.sh``). Structurally identical to GATE-11
    (``_validate_low_risk_emergency_approval`` above): runs from the live checkout,
    never trusts the approval's own claims about which paths changed, independently
    diffs ``base_git_sha..source_git_sha`` and rejects the whole batch if any changed
    path matches ``GATE11_EXCLUDED_PATH_PREFIXES`` -- deliberately the SAME excluded-
    path list GATE-11 uses, not a separate one to independently maintain and review.
    Since that list excludes ``ops/`` wholesale, this corridor can never approve a
    change to itself, to ``ops/staging/*``, or to the release gate -- exactly GATE-11's
    own self-widening prohibition. Unlike GATE-11, this never authorizes ``deploy``,
    ``pull``, or ``migration`` for production -- only ``staging-build`` -- and does not
    require ``test_evidence_sha256`` (it builds a non-production sandbox, not a
    release)."""

    if require_versioned:
        _assert_trusted_path(approval_path, leaf_directory=False, root_only=True)
    approval, _ = _load_private_json(approval_path)
    _require_exact_keys(
        approval,
        {
            "schema_version",
            "gate_id",
            "decision",
            "scope",
            "approval_id",
            "approved_by",
            "approved_at",
            "expires_at",
            "base_git_sha",
            "source_git_sha",
            "owner_read_diff_confirmation",
        },
        "GATE-12 staging build approval",
    )
    if (
        approval.get("schema_version") != 1
        or approval.get("gate_id") != "GATE-12"
        or approval.get("decision") != "APPROVED"
        or approval.get("scope") != "staging-build"
    ):
        raise GateConfigurationError(
            "approval does not authorize the staging build corridor"
        )
    approval_id = _require_nonempty(approval.get("approval_id"), "approval_id")
    _require_nonempty(approval.get("approved_by"), "approved_by")
    if approval.get("owner_read_diff_confirmation") is not True:
        raise GateConfigurationError(
            "GATE-12 approval must confirm the owner read the diff"
        )

    approved_at = _parse_utc_timestamp(approval.get("approved_at"), "approved_at")
    expires_at = _parse_utc_timestamp(approval.get("expires_at"), "expires_at")
    now = dt.datetime.now(dt.timezone.utc)
    if approved_at > now + dt.timedelta(minutes=5):
        raise GateConfigurationError("GATE-12 approval is future-dated")
    if expires_at <= now or expires_at > approved_at + dt.timedelta(hours=4):
        raise GateConfigurationError("GATE-12 approval is expired or over-broad")

    base_git_sha = str(approval.get("base_git_sha", ""))
    source_git_sha = str(approval.get("source_git_sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", base_git_sha):
        raise GateConfigurationError("GATE-12 approval base commit is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", source_git_sha):
        raise GateConfigurationError("GATE-12 approval source commit is invalid")
    if base_git_sha == source_git_sha:
        raise GateConfigurationError("GATE-12 approval covers an empty commit range")
    current_head = _git("rev-parse", "HEAD").strip()
    if source_git_sha != current_head:
        raise GateConfigurationError("GATE-12 approval is bound to another commit")
    if not _git_is_ancestor(base_git_sha, source_git_sha):
        raise GateConfigurationError(
            "GATE-12 approval base commit is not an ancestor of the source commit"
        )

    changed_paths = [
        line
        for line in _git(
            "diff",
            "--name-only",
            "--no-renames",
            base_git_sha,
            source_git_sha,
            "--",
        ).splitlines()
        if line
    ]
    if not changed_paths:
        raise GateConfigurationError("GATE-12 approval covers an empty diff")
    excluded_hits = [
        path for path in changed_paths if _path_excluded_from_low_risk_corridor(path)
    ]
    if excluded_hits:
        raise GateConfigurationError(
            "GATE-12 diff touches an excluded path: " + ", ".join(sorted(excluded_hits))
        )
    if require_versioned:
        _assert_clean_checkout()
    return approval_id, base_git_sha, source_git_sha


def _assert_two_commit_binding(manifest: dict[str, Any]) -> str:
    lineage = _git("rev-list", "--parents", "-n", "1", "HEAD").strip().split()
    if len(lineage) != 2:
        raise GateConfigurationError("gate-control HEAD must have exactly one parent")
    control_head, source_parent = lineage
    if not GIT_SHA_RE.fullmatch(control_head) or not GIT_SHA_RE.fullmatch(
        source_parent
    ):
        raise GateConfigurationError("gate-control commit lineage is invalid")
    if manifest.get("source_git_sha") != source_parent:
        raise GateConfigurationError(
            "release manifest is bound to a different source parent"
        )

    changed = set(
        line
        for line in _git(
            "diff",
            "--name-only",
            "--no-renames",
            source_parent,
            control_head,
            "--",
        ).splitlines()
        if line
    )
    if changed != GATE_DOCUMENT_PATHS:
        raise GateConfigurationError(
            "gate-control commit must change exactly the three fixed gate documents"
        )
    _assert_clean_checkout()
    return source_parent


def evaluate(
    operation: str,
    *,
    state_path: Path = STATE_PATH,
    approval_path: Path = APPROVAL_PATH,
    manifest_path: Path = MANIFEST_PATH,
    remediation_approval_path: Path = REMEDIATION_APPROVAL_PATH,
    operational_approval_path: Path = OPERATIONAL_CONTROL_APPROVAL_PATH,
    low_risk_emergency_approval_path: Path = LOW_RISK_EMERGENCY_APPROVAL_PATH,
    staging_build_approval_path: Path = STAGING_BUILD_APPROVAL_PATH,
    require_versioned: bool = True,
) -> GateDecision:
    if operation not in OPERATIONS:
        raise GateConfigurationError("unknown production operation")

    state, _ = _load_json(state_path)
    state_id, freeze, requirements = _validate_active_state(state)
    required_gate = freeze["required_gate"]

    if freeze["active"]:
        if operation == RECOVERY_OPERATION:
            return GateDecision(
                True,
                operation,
                "freeze_recovery_start_existing_only",
                state_id,
                required_gate,
            )
        if operation == REMEDIATION_CONTROL_OPERATION:
            approval_id, source_git_sha, artifact_hashes = (
                _validate_remediation_control_approval(
                    remediation_approval_path,
                    require_versioned=require_versioned,
                )
            )
            return GateDecision(
                True,
                operation,
                "gate08_hash_bound_remediation_control_install",
                state_id,
                "GATE-08",
                source_git_sha,
                approval_id,
                artifact_hashes,
            )
        if operation == OPERATIONAL_CONTROL_OPERATION:
            (
                approval_id,
                source_git_sha,
                artifact_hashes,
                install_targets,
                target_preconditions,
            ) = _validate_operational_control_approval(
                operational_approval_path,
                require_versioned=require_versioned,
            )
            return GateDecision(
                True,
                operation,
                "gate08_hash_bound_operational_control_install",
                state_id,
                "GATE-08",
                source_git_sha,
                approval_id,
                artifact_hashes,
                install_targets,
                target_preconditions,
            )
        if operation == LOW_RISK_EMERGENCY_OPERATION:
            approval_id, base_git_sha, source_git_sha = (
                _validate_low_risk_emergency_approval(
                    low_risk_emergency_approval_path,
                    require_versioned=require_versioned,
                )
            )
            return GateDecision(
                allowed=True,
                operation=operation,
                reason="gate11_scoped_low_risk_emergency_corridor",
                state_id=state_id,
                required_gate="GATE-11",
                source_git_sha=source_git_sha,
                approval_id=approval_id,
                base_git_sha=base_git_sha,
            )
        if operation == STAGING_BUILD_OPERATION:
            approval_id, base_git_sha, source_git_sha = (
                _validate_staging_build_approval(
                    staging_build_approval_path,
                    require_versioned=require_versioned,
                )
            )
            return GateDecision(
                allowed=True,
                operation=operation,
                reason="gate12_scoped_staging_build_corridor",
                state_id=state_id,
                required_gate="GATE-12",
                source_git_sha=source_git_sha,
                approval_id=approval_id,
                base_git_sha=base_git_sha,
            )
        raise GateDenied("production release freeze is active")

    approval, _ = _load_json(approval_path)
    manifest, manifest_raw = _load_json(manifest_path)
    if require_versioned:
        for path in (state_path, approval_path, manifest_path):
            _assert_committed_versioned(path)
    _validate_unfreeze_documents(
        state_id=state_id,
        requirements=requirements,
        approval=approval,
        manifest=manifest,
        manifest_raw=manifest_raw,
    )
    source_git_sha = str(manifest["source_git_sha"])
    if require_versioned:
        source_git_sha = _assert_two_commit_binding(manifest)
        _verify_source_derived_artifact_hashes(manifest["hashes"])
        _verify_image_attestation_hashes(manifest["hashes"], source_git_sha)
    if not GATE10_LIFT_IMPLEMENTED:
        raise GateConfigurationError(
            "GATE-10 lift remains disabled pending exact artifact binding"
        )
    return GateDecision(
        True,
        operation,
        "gate10_approved_manifest_bound",
        state_id,
        required_gate,
        source_git_sha,
    )


def _status_document() -> dict[str, object]:
    state, _ = _load_json(STATE_PATH)
    state_id, freeze, _ = _validate_active_state(state)
    return {
        "state_id": state_id,
        "freeze_active": freeze["active"],
        "freeze_lift_implemented": GATE10_LIFT_IMPLEMENTED,
        "required_gate": freeze["required_gate"],
        "mutating_operations": sorted(MUTATING_OPERATIONS),
        "freeze_recovery_operation": RECOVERY_OPERATION,
        "freeze_remediation_operation": REMEDIATION_CONTROL_OPERATION,
        "freeze_operational_control_operation": OPERATIONAL_CONTROL_OPERATION,
        "freeze_low_risk_emergency_operation": LOW_RISK_EMERGENCY_OPERATION,
        "freeze_staging_build_operation": STAGING_BUILD_OPERATION,
    }


def _print_json(value: dict[str, object], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check", help="authorize one classified operation")
    check.add_argument("operation", choices=sorted(OPERATIONS))
    subparsers.add_parser("status", help="print the non-sensitive freeze status")
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            _print_json(_status_document())
            return 0
        decision = evaluate(args.operation)
    except GateDenied:
        state_id = "unknown"
        try:
            state, _ = _load_json(STATE_PATH)
            state_id = str(state.get("state_id") or "unknown")
        except GateConfigurationError:
            pass
        _print_json(
            {
                "allowed": False,
                "operation": args.operation,
                "reason": "production_release_freeze_active",
                "state_id": state_id,
                "required_gate": "GATE-10",
            },
            stream=sys.stderr,
        )
        return 20
    except GateConfigurationError:
        _print_json(
            {
                "allowed": False,
                "operation": getattr(args, "operation", "status"),
                "reason": "production_release_gate_invalid",
                "required_gate": "GATE-10",
            },
            stream=sys.stderr,
        )
        return 21

    _print_json(decision.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
