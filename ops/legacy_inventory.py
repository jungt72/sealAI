#!/usr/bin/env python3
"""Classify a sanitized local legacy inventory without querying or mutating it.

There are deliberately no Docker, SSH, PM2, Qdrant, network, archive, or delete
commands in this module.  Collection from production is a separate gated task;
this tool accepts only an explicit ``SANITIZED_LOCAL_FIXTURE`` document.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Sequence


SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_SCHEMA_BYTES = 512 * 1024
ASSET_TYPES = (
    "container",
    "image",
    "service",
    "frontend",
    "feature_flag",
    "prompt_family",
    "qdrant_collection",
    "volume",
    "pm2_process",
    "network_workload",
    "configuration",
    "backup",
    "port",
)
CLASSIFICATIONS = (
    "ACTIVE",
    "REQUIRED_FOR_ROLLBACK",
    "LEGACY_BUT_IN_USE",
    "ORPHANED",
    "SAFE_TO_ARCHIVE",
    "SAFE_TO_DELETE_AFTER_APPROVAL",
    "UNKNOWN",
)
CLASSIFICATION_REASONS = {
    "ACTIVE": {"The object or its known owner is active."},
    "REQUIRED_FOR_ROLLBACK": {
        "The object is in a documented rollback dependency closure."
    },
    "LEGACY_BUT_IN_USE": {"An active object depends on this legacy object."},
    "ORPHANED": {
        "The object is inactive but still has classified dependents.",
        "No active or rollback dependency exists, but cleanup gates are incomplete.",
    },
    "SAFE_TO_ARCHIVE": {"Archive gates, including approval, are complete."},
    "SAFE_TO_DELETE_AFTER_APPROVAL": {
        "Backup, dependency, and rollback evidence are complete; deletion still requires explicit approval."
    },
    "UNKNOWN": {
        "Evidence is incomplete, conflicting, or lifecycle is unknown.",
        "Ownership is not proven.",
        "The supplied evidence does not support a permitted classification.",
    },
}
_SECRET_PATTERNS = (
    re.compile(rb"sk-(?:ant|proj|live|test)-[A-Za-z0-9_-]{12,}", re.IGNORECASE),
    re.compile(rb"(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(rb"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
)


class InventoryError(RuntimeError):
    """Inventory input or output failed a local, fail-closed check."""


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            + b"\n"
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise InventoryError(
            "inventory cannot be represented as canonical JSON"
        ) from exc


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise InventoryError("inventory JSON contains a duplicate key")
        value[key] = item
    return value


def _parse_json(raw: bytes, *, label: str) -> Any:
    def reject_constant(_value: str) -> None:
        raise InventoryError(f"{label} contains a non-finite number")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=reject_constant,
        )
    except InventoryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InventoryError(f"{label} is not unambiguous UTF-8 JSON") from exc


def _assert_no_secret(raw: bytes, *, label: str) -> None:
    if any(pattern.search(raw) is not None for pattern in _SECRET_PATTERNS):
        raise InventoryError(f"secret canary detected in {label}")


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_directory(path: Path, *, label: str) -> int:
    absolute = path.absolute()
    if not absolute.is_absolute() or not absolute.anchor:
        raise InventoryError(f"{label} is not an absolute directory path")
    flags = _directory_flags()
    try:
        current_fd = os.open(absolute.anchor, flags)
    except OSError as exc:
        raise InventoryError(f"{label} root directory is unavailable") from exc
    try:
        for part in absolute.parts[1:]:
            next_fd: int | None = None
            try:
                next_fd = os.open(part, flags, dir_fd=current_fd)
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise InventoryError(f"{label} traverses a non-directory")
            except (OSError, InventoryError):
                if next_fd is not None:
                    os.close(next_fd)
                raise
            os.close(current_fd)
            assert next_fd is not None
            current_fd = next_fd
        return current_fd
    except (OSError, InventoryError) as exc:
        os.close(current_fd)
        if isinstance(exc, InventoryError):
            raise
        raise InventoryError(
            f"{label} traverses a symlink or unavailable directory"
        ) from exc


def _open_parent(path: Path, *, label: str) -> tuple[int, str]:
    absolute = path.absolute()
    if absolute.name in {"", ".", ".."}:
        raise InventoryError(f"{label} has no safe leaf name")
    return _open_directory(absolute.parent, label=f"{label} parent"), absolute.name


def _read_regular(path: Path, *, limit: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_fd, leaf = _open_parent(path, label=label)
    try:
        before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        fd = os.open(leaf, flags, dir_fd=parent_fd)
    except OSError as exc:
        os.close(parent_fd)
        raise InventoryError(f"{label} is unavailable or is a symlink") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or not (0 < opened.st_size <= limit):
            raise InventoryError(f"{label} is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        identities = {
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ),
            (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            ),
            (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ),
        }
        if len(identities) != 1 or not raw or len(raw) > limit:
            raise InventoryError(f"{label} changed during the bounded read")
        return raw
    except OSError as exc:
        raise InventoryError(f"{label} cannot be read safely") from exc
    finally:
        os.close(fd)
        os.close(parent_fd)


def _safe_repo_path(
    repo: Path, value: str | Path, *, label: str, must_exist: bool
) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = repo / candidate
    try:
        relative = candidate.relative_to(repo)
    except ValueError as exc:
        raise InventoryError(f"{label} escapes the repository") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise InventoryError(f"{label} is not canonical")
    current_fd = _open_directory(repo, label="repository root")
    try:
        for index, part in enumerate(relative.parts):
            final = index == len(relative.parts) - 1
            if final:
                try:
                    metadata = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
                except FileNotFoundError:
                    if must_exist:
                        raise InventoryError(f"{label} does not exist") from None
                    break
                if stat.S_ISLNK(metadata.st_mode):
                    raise InventoryError(f"{label} traverses a symlink")
                break
            try:
                next_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
            except OSError as exc:
                raise InventoryError(
                    f"{label} traverses a symlink or unavailable directory"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
    finally:
        os.close(current_fd)
    return candidate


def _atomic_write(path: Path, raw: bytes) -> None:
    dir_fd, leaf = _open_parent(path, label="inventory output")
    temp_name = f".{leaf}.tmp.{os.getpid()}.{secrets.token_hex(8)}"
    try:
        try:
            existing = os.stat(leaf, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise InventoryError("output target is not a regular file")
        fd = os.open(
            temp_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=dir_fd,
        )
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp_name, leaf, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
    except Exception:
        try:
            os.unlink(temp_name, dir_fd=dir_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(dir_fd)


def _load_jsonschema() -> Any:
    try:
        import jsonschema
    except ImportError as exc:
        raise InventoryError(
            "jsonschema is a required local dependency; no installer is invoked"
        ) from exc
    return jsonschema


def _validate_schema(value: Any, schema_path: Path, *, label: str) -> None:
    jsonschema = _load_jsonschema()
    schema = _parse_json(
        _read_regular(schema_path, limit=MAX_SCHEMA_BYTES, label="inventory schema"),
        label="inventory schema",
    )
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    except (jsonschema.SchemaError, RecursionError) as exc:
        raise InventoryError("inventory JSON schema is invalid") from exc
    if errors:
        path = ".".join(str(part) for part in errors[0].path) or "<root>"
        raise InventoryError(f"{label} fails schema validation at {path}")


def validate_input(value: Any, repo: Path) -> dict[str, Any]:
    schema = _safe_repo_path(
        repo,
        ".ai-remediation/schemas/legacy-inventory-input.schema.json",
        label="legacy inventory input schema",
        must_exist=True,
    )
    _validate_schema(value, schema, label="inventory input")
    assert isinstance(value, dict)
    objects = value["objects"]
    ids = [item["id"] for item in objects]
    if len(ids) != len(set(ids)):
        raise InventoryError("inventory object IDs are not unique")
    coverage = {item["asset_type"] for item in objects}
    if coverage != set(ASSET_TYPES):
        raise InventoryError(
            "inventory does not cover exactly all required asset types"
        )
    known = set(ids)
    for item in objects:
        dependencies = set(item["dependencies"])
        if item["id"] in dependencies:
            raise InventoryError("inventory contains a self-dependency")
        if not dependencies.issubset(known):
            raise InventoryError("inventory references a missing dependency")
        approval = item["approval"]
        if approval["required"] and approval["status"] == "NOT_REQUIRED":
            raise InventoryError("required approval cannot have NOT_REQUIRED status")
        if not approval["required"] and approval["status"] != "NOT_REQUIRED":
            raise InventoryError("optional approval must have NOT_REQUIRED status")
        backup = item["backup"]
        if backup["verified"] and not backup["available"]:
            raise InventoryError("verified backup must be available")
        if item["owner"]["in_use"] and not item["owner"]["known"]:
            raise InventoryError("an in-use owner must be known")
    return value


def validate_report(value: Any, repo: Path) -> dict[str, Any]:
    schema = _safe_repo_path(
        repo,
        ".ai-remediation/schemas/legacy-inventory-report.schema.json",
        label="legacy inventory report schema",
        must_exist=True,
    )
    _validate_schema(value, schema, label="inventory report")
    assert isinstance(value, dict)
    objects = value["objects"]
    ids = [item["id"] for item in objects]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise InventoryError("inventory report object IDs are not unique and sorted")
    known = set(ids)
    if value["coverage"] != list(ASSET_TYPES):
        raise InventoryError("inventory report coverage is not canonical")
    if {item["asset_type"] for item in objects} != set(ASSET_TYPES):
        raise InventoryError("inventory report objects do not match declared coverage")

    expected_summary = Counter(item["classification"] for item in objects)
    canonical_summary = {name: expected_summary[name] for name in CLASSIFICATIONS}
    if value["summary"] != canonical_summary or sum(value["summary"].values()) != len(
        objects
    ):
        raise InventoryError("inventory report summary does not match its objects")

    expected_edges: set[tuple[str, str]] = set()
    expected_dependents: dict[str, list[str]] = {object_id: [] for object_id in ids}
    for item in objects:
        dependencies = item["dependencies"]
        if dependencies != sorted(dependencies):
            raise InventoryError("inventory report dependencies are not canonical")
        if item["id"] in dependencies or not set(dependencies).issubset(known):
            raise InventoryError("inventory report has an invalid dependency")
        for dependency in dependencies:
            expected_edges.add((item["id"], dependency))
            expected_dependents[dependency].append(item["id"])

        gate = item["gate"]
        if item["reason"] not in CLASSIFICATION_REASONS[item["classification"]]:
            raise InventoryError(
                "inventory report reason does not match its classification"
            )
        expected_approval_ready = gate["approval_status"] in {
            "NOT_REQUIRED",
            "APPROVED",
        }
        expected_cleanup_ready = (
            gate["backup_ready"]
            and gate["dependency_evidence_complete"]
            and gate["rollback_ready"]
            and gate["approval_ready"]
        )
        if (
            gate["approval_ready"] != expected_approval_ready
            or gate["cleanup_ready"] != expected_cleanup_ready
        ):
            raise InventoryError("inventory report gate booleans are inconsistent")
        if item["classification"] == "SAFE_TO_ARCHIVE" and (
            item["candidate_action"] != "ARCHIVE"
            or item["dependents"]
            or not gate["cleanup_ready"]
        ):
            raise InventoryError("safe archive classification lacks complete gates")
        if item["classification"] == "SAFE_TO_DELETE_AFTER_APPROVAL" and (
            item["candidate_action"] != "DELETE"
            or item["dependents"]
            or not gate["backup_ready"]
            or not gate["dependency_evidence_complete"]
            or not gate["rollback_ready"]
            or gate["approval_status"] == "NOT_REQUIRED"
        ):
            raise InventoryError("safe delete classification lacks required gates")

    actual_edges = [(edge["from"], edge["to"]) for edge in value["dependencies"]]
    if actual_edges != sorted(expected_edges):
        raise InventoryError("inventory report edge list does not match its objects")
    for item in objects:
        expected = sorted(expected_dependents[item["id"]])
        if item["dependents"] != expected:
            raise InventoryError(
                "inventory report reverse dependencies are inconsistent"
            )
    return value


def _closure(roots: set[str], objects: dict[str, dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    pending = list(sorted(roots))
    while pending:
        object_id = pending.pop()
        if object_id in result:
            continue
        result.add(object_id)
        pending.extend(objects[object_id]["dependencies"])
    return result


def _gate(item: dict[str, Any]) -> dict[str, Any]:
    backup = item["backup"]
    rollback = item["rollback"]
    approval = item["approval"]
    backup_ready = not backup["required"] or (
        backup["available"] and backup["verified"]
    )
    rollback_ready = not rollback["required"] or (
        rollback["documented"] and rollback["tested"]
    )
    approval_ready = not approval["required"] or approval["status"] == "APPROVED"
    dependency_ready = item["dependency_evidence_complete"]
    return {
        "backup_ready": backup_ready,
        "dependency_evidence_complete": dependency_ready,
        "rollback_ready": rollback_ready,
        "approval_status": approval["status"],
        "approval_ready": approval_ready,
        "cleanup_ready": (
            backup_ready and dependency_ready and rollback_ready and approval_ready
        ),
    }


def _classify(
    item: dict[str, Any],
    *,
    active_closure: set[str],
    rollback_closure: set[str],
    dependents: list[str],
    gate: dict[str, Any],
) -> tuple[str, str]:
    object_id = item["id"]
    if item["evidence_state"] != "COMPLETE" or item["lifecycle"] == "UNKNOWN":
        return (
            "UNKNOWN",
            "Evidence is incomplete, conflicting, or lifecycle is unknown.",
        )
    if not item["owner"]["known"]:
        return "UNKNOWN", "Ownership is not proven."
    if object_id in active_closure:
        if item["lifecycle"] in {"LEGACY", "INACTIVE"}:
            return (
                "LEGACY_BUT_IN_USE",
                "An active object depends on this legacy object.",
            )
        return "ACTIVE", "The object or its known owner is active."
    if object_id in rollback_closure:
        return (
            "REQUIRED_FOR_ROLLBACK",
            "The object is in a documented rollback dependency closure.",
        )
    if dependents:
        return "ORPHANED", "The object is inactive but still has classified dependents."
    safety_without_approval = (
        gate["backup_ready"]
        and gate["dependency_evidence_complete"]
        and gate["rollback_ready"]
    )
    if item["candidate_action"] == "ARCHIVE" and gate["cleanup_ready"]:
        return "SAFE_TO_ARCHIVE", "Archive gates, including approval, are complete."
    if (
        item["candidate_action"] == "DELETE"
        and safety_without_approval
        and item["approval"]["required"]
    ):
        return (
            "SAFE_TO_DELETE_AFTER_APPROVAL",
            "Backup, dependency, and rollback evidence are complete; deletion still requires explicit approval.",
        )
    if item["lifecycle"] in {"LEGACY", "INACTIVE"}:
        return (
            "ORPHANED",
            "No active or rollback dependency exists, but cleanup gates are incomplete.",
        )
    return (
        "UNKNOWN",
        "The supplied evidence does not support a permitted classification.",
    )


def classify_inventory(
    value: dict[str, Any], repo: Path, *, generated_at: str | None = None
) -> dict[str, Any]:
    value = validate_input(value, repo)
    indexed = {item["id"]: item for item in value["objects"]}
    reverse: dict[str, list[str]] = {object_id: [] for object_id in indexed}
    edges: list[dict[str, str]] = []
    for item in value["objects"]:
        for dependency in item["dependencies"]:
            reverse[dependency].append(item["id"])
            edges.append({"from": item["id"], "to": dependency})
    active_roots = {
        item["id"]
        for item in value["objects"]
        if item["lifecycle"] == "ACTIVE" or item["owner"]["in_use"]
    }
    rollback_roots = {
        item["id"] for item in value["objects"] if item["rollback"]["required"]
    }
    active_closure = _closure(active_roots, indexed)
    rollback_closure = _closure(rollback_roots, indexed)
    output_objects: list[dict[str, Any]] = []
    for object_id in sorted(indexed):
        item = indexed[object_id]
        gate = _gate(item)
        classification, reason = _classify(
            item,
            active_closure=active_closure,
            rollback_closure=rollback_closure,
            dependents=sorted(reverse[object_id]),
            gate=gate,
        )
        output_objects.append(
            {
                "id": object_id,
                "asset_type": item["asset_type"],
                "classification": classification,
                "reason": reason,
                "dependencies": sorted(item["dependencies"]),
                "dependents": sorted(reverse[object_id]),
                "gate": gate,
                "candidate_action": item["candidate_action"],
                "mutation_authorized": False,
                "action_taken": False,
            }
        )
    counts = Counter(item["classification"] for item in output_objects)
    report = {
        "schema_version": SCHEMA_VERSION,
        "inventory_id": value["inventory_id"],
        "generated_at": generated_at or _utc_now(),
        "source": value["source"],
        "coverage": list(ASSET_TYPES),
        "summary": {name: counts[name] for name in CLASSIFICATIONS},
        "dependencies": sorted(edges, key=lambda edge: (edge["from"], edge["to"])),
        "objects": output_objects,
        "production_query_performed": False,
        "mutation_performed": False,
    }
    return validate_report(report, repo)


def _repository_root(path: Path) -> Path:
    if path.absolute().is_symlink():
        raise InventoryError("--repo must not be a symlink")
    root = path.resolve(strict=True)
    root_fd = _open_directory(root, label="repository root")
    try:
        try:
            git_metadata = os.stat(".git", dir_fd=root_fd, follow_symlinks=False)
        except OSError as exc:
            raise InventoryError("--repo is not a repository root") from exc
        # Worktrees have a regular .git pointer file, which is deliberately okay.
        if not (
            stat.S_ISDIR(git_metadata.st_mode) or stat.S_ISREG(git_metadata.st_mode)
        ):
            raise InventoryError("--repo has an unsafe .git entry")
    finally:
        os.close(root_fd)
    return root


def _load_input(repo: Path, input_arg: str) -> dict[str, Any]:
    path = _safe_repo_path(repo, input_arg, label="inventory input", must_exist=True)
    raw = _read_regular(path, limit=MAX_INPUT_BYTES, label="inventory input")
    _assert_no_secret(raw, label="inventory input")
    value = _parse_json(raw, label="inventory input")
    return validate_input(value, repo)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)
    classify = subparsers.add_parser("classify")
    classify.add_argument("--input", required=True)
    classify.add_argument("--output", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--input", required=True)
    validate.add_argument("--kind", choices=("input", "report"), default="input")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repo = _repository_root(Path(args.repo))
        if args.command == "classify":
            value = _load_input(repo, args.input)
            report = classify_inventory(value, repo)
            output = _safe_repo_path(
                repo, args.output, label="inventory output", must_exist=False
            )
            raw = _canonical_json(report)
            _assert_no_secret(raw, label="inventory report")
            _atomic_write(output, raw)
            result = {
                "status": "PASS",
                "objects": len(report["objects"]),
                "production_query_performed": False,
                "mutation_performed": False,
            }
        else:
            path = _safe_repo_path(
                repo, args.input, label="inventory document", must_exist=True
            )
            raw = _read_regular(path, limit=MAX_INPUT_BYTES, label="inventory document")
            _assert_no_secret(raw, label="inventory document")
            value = _parse_json(raw, label="inventory document")
            if args.kind == "input":
                validate_input(value, repo)
            else:
                validate_report(value, repo)
            result = {
                "status": "PASS",
                "production_query_performed": False,
                "mutation_performed": False,
            }
    except InventoryError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
