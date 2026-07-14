#!/usr/bin/env python3
"""Canonical, fail-closed release-candidate evidence for the V2 eval gate.

The evidence file is deliberately authentication-agnostic: its exact canonical
bytes are approved separately by Gate 10 and supplied to ``v2_deploy_gate.py``
as ``--rc-evidence-sha256``.  The in-file payload hash detects accidental
corruption; it is not treated as an approval or signature.

Pure stdlib and secret-free.  Database URLs, credentials, provider keys, and
production endpoints are intentionally outside this contract.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any


SCHEMA_VERSION = 1
EVIDENCE_TYPE = "sealai_v2_production_rc"
PROMOTION_EVIDENCE_TYPE = "sealai_v2_promotion_evidence"
MAX_EVIDENCE_BYTES = 256 * 1024
MAX_RESULTS_BYTES = 64 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DATABASE_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_QDRANT_COLLECTION_RE = re.compile(r"^sealai_rc_[a-z0-9_]{1,48}$")
_RUN_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ZERO_SHA256 = "0" * 64

_DOCUMENT_KEYS = frozenset(
    {"schema_version", "evidence_type", "payload", "payload_sha256"}
)
_PAYLOAD_KEYS = frozenset(
    {
        "authority_epoch",
        "candidate_image_config_digest",
        "candidate_image_digest",
        "candidate_image_digest_source",
        "database_migration_sha256",
        "isolation",
        "retriever",
        "runtime_profile",
        "runtime_profile_sha256",
        "served_tree_sha256",
        "source_git_sha",
    }
)
_ISOLATION_KEYS = frozenset({"postgres", "qdrant"})
_POSTGRES_KEYS = frozenset({"database", "mode", "snapshot_sha256"})
_QDRANT_KEYS = frozenset({"authentication", "collection", "mode", "snapshot_sha256"})
_RETRIEVER_KEYS = frozenset({"backend", "fallback_allowed"})
_RUNTIME_PROFILE_KEYS = frozenset({"schema_version", "behavior"})

MANIFEST_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "evidence_type",
        "evidence_sha256",
        "payload_sha256",
        "candidate_image_config_digest",
        "candidate_image_digest",
        "candidate_image_digest_source",
        "served_tree_sha256",
        "database_migration_sha256",
        "authority_epoch",
        "runtime_profile_sha256",
        "retriever_backend",
        "retriever_fallback_allowed",
        "postgres_database",
        "postgres_snapshot_sha256",
        "qdrant_collection",
        "qdrant_authentication",
        "qdrant_snapshot_sha256",
        "source_git_sha",
    }
)

_PROMOTION_PAYLOAD_KEYS = frozenset(
    {"rc_descriptor", "rc_descriptor_sha256", "results"}
)
_PROMOTION_RESULTS_KEYS = frozenset({"run_label", "results_sha256"})


class EvidenceError(ValueError):
    """The release-candidate evidence is absent, ambiguous, or inconsistent."""


def _canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, RecursionError) as exc:
        raise EvidenceError("value is not canonical JSON") from exc
    return rendered + (b"\n" if newline else b"")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("JSON contains a duplicate key")
        result[key] = value
    return result


def _parse_json(raw: bytes) -> Any:
    def reject_constant(_value: str) -> None:
        raise EvidenceError("JSON contains a non-finite number")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=reject_constant,
        )
    except EvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceError("file is not unambiguous UTF-8 JSON") from exc


def _read_regular_file(path: Path, *, limit: int = MAX_EVIDENCE_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EvidenceError("evidence input is unavailable") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise EvidenceError("evidence input is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > limit:
            raise EvidenceError("evidence input size is invalid")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if not raw or len(raw) > limit:
            raise EvidenceError("evidence input size is invalid")
        return raw
    except OSError as exc:
        raise EvidenceError("evidence input cannot be read") from exc
    finally:
        os.close(fd)


def _require_exact_keys(value: Any, expected: frozenset[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise EvidenceError(f"{label} keys are invalid")
    return value


def _require_sha256(value: Any, label: str, *, prefixed: bool = False) -> str:
    pattern = _DIGEST_RE if prefixed else _SHA256_RE
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise EvidenceError(f"{label} is not a canonical SHA-256")
    raw = value.removeprefix("sha256:")
    if raw == _ZERO_SHA256:
        raise EvidenceError(f"{label} is the zero SHA-256")
    return value


def _require_git_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _GIT_SHA_RE.fullmatch(value) is None:
        raise EvidenceError(f"{label} is not a full canonical Git SHA")
    if set(value) == {"0"}:
        raise EvidenceError(f"{label} is the zero Git SHA")
    return value


def _validate_json_tree(
    value: Any, *, depth: int = 0, budget: list[int] | None = None
) -> None:
    """Bound the extensible runtime profile before canonical serialization."""
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if budget[0] < 0 or depth > 12:
        raise EvidenceError("runtime profile structure is too large")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > 2**63 - 1:
            raise EvidenceError("runtime profile integer is out of range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvidenceError("runtime profile number is not finite")
        return
    if isinstance(value, str):
        if len(value) > 4096:
            raise EvidenceError("runtime profile string is too long")
        return
    if isinstance(value, list):
        if len(value) > 1024:
            raise EvidenceError("runtime profile list is too large")
        for item in value:
            _validate_json_tree(item, depth=depth + 1, budget=budget)
        return
    if isinstance(value, dict):
        if len(value) > 1024:
            raise EvidenceError("runtime profile object is too large")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise EvidenceError("runtime profile key is invalid")
            _validate_json_tree(item, depth=depth + 1, budget=budget)
        return
    raise EvidenceError("runtime profile contains a non-JSON value")


def validate_document(document: Any) -> dict:
    """Validate the exact v1 schema and all cross-field runtime invariants."""
    document = _require_exact_keys(document, _DOCUMENT_KEYS, "document")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != SCHEMA_VERSION
    ):
        raise EvidenceError("schema_version is unsupported")
    if document["evidence_type"] != EVIDENCE_TYPE:
        raise EvidenceError("evidence_type is not production RC evidence")

    payload = _require_exact_keys(document["payload"], _PAYLOAD_KEYS, "payload")
    _require_sha256(
        payload["candidate_image_digest"], "candidate_image_digest", prefixed=True
    )
    _require_sha256(
        payload["candidate_image_config_digest"],
        "candidate_image_config_digest",
        prefixed=True,
    )
    if payload["candidate_image_digest_source"] != "gate10_backend_registry_manifest":
        raise EvidenceError("candidate image digest is not sourced from Gate 10")
    _require_sha256(payload["served_tree_sha256"], "served_tree_sha256")
    _require_git_sha(payload["source_git_sha"], "source_git_sha")
    _require_sha256(payload["database_migration_sha256"], "database_migration_sha256")
    _require_sha256(payload["authority_epoch"], "authority_epoch", prefixed=True)
    _require_sha256(payload["runtime_profile_sha256"], "runtime_profile_sha256")

    retriever = _require_exact_keys(payload["retriever"], _RETRIEVER_KEYS, "retriever")
    if retriever != {"backend": "qdrant", "fallback_allowed": False}:
        raise EvidenceError("retriever must be qdrant with fallback disabled")

    isolation = _require_exact_keys(payload["isolation"], _ISOLATION_KEYS, "isolation")
    postgres = _require_exact_keys(isolation["postgres"], _POSTGRES_KEYS, "postgres")
    if postgres["mode"] != "isolated_snapshot":
        raise EvidenceError("Postgres evidence is not an isolated snapshot")
    if (
        not isinstance(postgres["database"], str)
        or _DATABASE_RE.fullmatch(postgres["database"]) is None
    ):
        raise EvidenceError("Postgres database identifier is invalid")
    _require_sha256(postgres["snapshot_sha256"], "postgres_snapshot_sha256")

    qdrant = _require_exact_keys(isolation["qdrant"], _QDRANT_KEYS, "qdrant")
    if qdrant["mode"] != "isolated_collection_snapshot":
        raise EvidenceError("Qdrant evidence is not an isolated collection snapshot")
    if qdrant["authentication"] != "api_key":
        raise EvidenceError("Qdrant RC evidence requires scoped API-key authentication")
    if (
        not isinstance(qdrant["collection"], str)
        or _QDRANT_COLLECTION_RE.fullmatch(qdrant["collection"]) is None
    ):
        raise EvidenceError("Qdrant RC collection identifier is invalid")
    _require_sha256(qdrant["snapshot_sha256"], "qdrant_snapshot_sha256")

    runtime_profile = _require_exact_keys(
        payload["runtime_profile"], _RUNTIME_PROFILE_KEYS, "runtime_profile"
    )
    if (
        type(runtime_profile["schema_version"]) is not int
        or runtime_profile["schema_version"] != 1
    ):
        raise EvidenceError("runtime profile schema is unsupported")
    behavior = runtime_profile["behavior"]
    if not isinstance(behavior, dict) or not behavior:
        raise EvidenceError("runtime profile behavior is empty")
    _validate_json_tree(runtime_profile)
    runtime_hash = hashlib.sha256(_canonical_json_bytes(runtime_profile)).hexdigest()
    if not hmac.compare_digest(runtime_hash, payload["runtime_profile_sha256"]):
        raise EvidenceError("runtime profile hash does not match its payload")
    if behavior.get("retriever_backend") != "qdrant":
        raise EvidenceError("runtime profile does not select qdrant")
    if behavior.get("ground_enabled") is not True:
        raise EvidenceError("runtime profile does not activate grounded retrieval")
    if behavior.get("qdrant_collection") != qdrant["collection"]:
        raise EvidenceError("runtime profile Qdrant collection does not match evidence")
    if behavior.get("knowledge_authority_epoch") != payload["authority_epoch"]:
        raise EvidenceError("runtime profile Authority Epoch does not match evidence")

    payload_hash = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    _require_sha256(document["payload_sha256"], "payload_sha256")
    if not hmac.compare_digest(payload_hash, document["payload_sha256"]):
        raise EvidenceError("payload hash does not match the evidence payload")
    return document


def validate_promotion_document(document: Any) -> dict:
    """Validate the post-adjudication manifest that Gate 10 approves."""
    document = _require_exact_keys(document, _DOCUMENT_KEYS, "promotion document")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != SCHEMA_VERSION
    ):
        raise EvidenceError("promotion schema_version is unsupported")
    if document["evidence_type"] != PROMOTION_EVIDENCE_TYPE:
        raise EvidenceError("evidence_type is not promotion evidence")
    payload = _require_exact_keys(
        document["payload"], _PROMOTION_PAYLOAD_KEYS, "promotion payload"
    )
    descriptor = validate_document(payload["rc_descriptor"])
    _require_sha256(payload["rc_descriptor_sha256"], "rc_descriptor_sha256")
    if not hmac.compare_digest(
        evidence_sha256(descriptor), payload["rc_descriptor_sha256"]
    ):
        raise EvidenceError("promotion evidence does not match its RC descriptor hash")
    results = _require_exact_keys(
        payload["results"], _PROMOTION_RESULTS_KEYS, "promotion results"
    )
    if (
        not isinstance(results["run_label"], str)
        or _RUN_LABEL_RE.fullmatch(results["run_label"]) is None
    ):
        raise EvidenceError("promotion run_label is invalid")
    _require_sha256(results["results_sha256"], "results_sha256")
    _require_sha256(document["payload_sha256"], "promotion payload_sha256")
    payload_hash = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    if not hmac.compare_digest(payload_hash, document["payload_sha256"]):
        raise EvidenceError("promotion payload hash does not match")
    return document


def canonical_evidence_bytes(document: dict) -> bytes:
    validate_document(document)
    return _canonical_json_bytes(document, newline=True)


def canonical_promotion_bytes(document: dict) -> bytes:
    validate_promotion_document(document)
    return _canonical_json_bytes(document, newline=True)


def evidence_sha256(document: dict) -> str:
    return hashlib.sha256(canonical_evidence_bytes(document)).hexdigest()


def promotion_evidence_sha256(document: dict) -> str:
    return hashlib.sha256(canonical_promotion_bytes(document)).hexdigest()


def build_document(
    *,
    candidate_image_digest: str,
    candidate_image_config_digest: str,
    served_tree_sha256: str,
    database_migration_sha256: str,
    authority_epoch: str,
    postgres_database: str,
    postgres_snapshot_sha256: str,
    qdrant_collection: str,
    qdrant_snapshot_sha256: str,
    runtime_profile: dict,
    source_git_sha: str,
) -> dict:
    """Build a canonical v1 document from already measured candidate inputs."""
    # Canonical round-trip provides a detached JSON-only copy and rejects values
    # that JSON would otherwise coerce or serialize ambiguously.
    detached_profile = _parse_json(_canonical_json_bytes(runtime_profile))
    runtime_hash = hashlib.sha256(_canonical_json_bytes(detached_profile)).hexdigest()
    payload = {
        "authority_epoch": authority_epoch,
        "candidate_image_config_digest": candidate_image_config_digest,
        "candidate_image_digest": candidate_image_digest,
        "candidate_image_digest_source": "gate10_backend_registry_manifest",
        "database_migration_sha256": database_migration_sha256,
        "isolation": {
            "postgres": {
                "database": postgres_database,
                "mode": "isolated_snapshot",
                "snapshot_sha256": postgres_snapshot_sha256,
            },
            "qdrant": {
                "authentication": "api_key",
                "collection": qdrant_collection,
                "mode": "isolated_collection_snapshot",
                "snapshot_sha256": qdrant_snapshot_sha256,
            },
        },
        "retriever": {"backend": "qdrant", "fallback_allowed": False},
        "runtime_profile": detached_profile,
        "runtime_profile_sha256": runtime_hash,
        "served_tree_sha256": served_tree_sha256,
        "source_git_sha": source_git_sha,
    }
    document = {
        "schema_version": SCHEMA_VERSION,
        "evidence_type": EVIDENCE_TYPE,
        "payload": payload,
        "payload_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return validate_document(document)


def build_promotion_document(
    *, rc_descriptor: dict, run_label: str, results_sha256: str
) -> dict:
    descriptor = validate_document(rc_descriptor)
    payload = {
        "rc_descriptor": _parse_json(_canonical_json_bytes(descriptor)),
        "rc_descriptor_sha256": evidence_sha256(descriptor),
        "results": {
            "run_label": run_label,
            "results_sha256": results_sha256,
        },
    }
    document = {
        "schema_version": SCHEMA_VERSION,
        "evidence_type": PROMOTION_EVIDENCE_TYPE,
        "payload": payload,
        "payload_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return validate_promotion_document(document)


def load_evidence(
    path: str | os.PathLike[str], *, expected_sha256: str | None = None
) -> tuple[dict, str]:
    """Load exact canonical bytes and optionally bind them to an external hash."""
    raw = _read_regular_file(Path(path))
    document = validate_document(_parse_json(raw))
    canonical = canonical_evidence_bytes(document)
    if not hmac.compare_digest(raw, canonical):
        raise EvidenceError("evidence file is not in canonical byte form")
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        _require_sha256(expected_sha256, "expected evidence SHA-256")
        if not hmac.compare_digest(actual_sha256, expected_sha256):
            raise EvidenceError(
                "evidence file does not match the externally approved hash"
            )
    return document, actual_sha256


def load_promotion_evidence(
    path: str | os.PathLike[str], *, expected_sha256: str | None = None
) -> tuple[dict, str]:
    raw = _read_regular_file(Path(path))
    document = validate_promotion_document(_parse_json(raw))
    canonical = canonical_promotion_bytes(document)
    if not hmac.compare_digest(raw, canonical):
        raise EvidenceError("promotion evidence is not in canonical byte form")
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        _require_sha256(expected_sha256, "expected promotion evidence SHA-256")
        if not hmac.compare_digest(actual_sha256, expected_sha256):
            raise EvidenceError(
                "promotion evidence does not match the externally approved hash"
            )
    return document, actual_sha256


def read_results_bytes(path: str | os.PathLike[str]) -> bytes:
    """Read a bounded, non-symlink results artifact for exact hashing."""
    return _read_regular_file(Path(path), limit=MAX_RESULTS_BYTES)


def parse_json_bytes(raw: bytes) -> Any:
    """Parse JSON with the contract's duplicate-key/non-finite rejection."""
    return _parse_json(raw)


def manifest_binding(document: dict, *, file_sha256: str | None = None) -> dict:
    """Return the exact small descriptor stored in ``results.manifest``."""
    document = validate_document(document)
    canonical_file_sha256 = evidence_sha256(document)
    actual_file_sha256 = file_sha256 or canonical_file_sha256
    _require_sha256(actual_file_sha256, "evidence_sha256")
    if not hmac.compare_digest(actual_file_sha256, canonical_file_sha256):
        raise EvidenceError(
            "manifest binding hash does not match canonical evidence bytes"
        )
    payload = document["payload"]
    postgres = payload["isolation"]["postgres"]
    qdrant = payload["isolation"]["qdrant"]
    binding = {
        "schema_version": SCHEMA_VERSION,
        "evidence_type": EVIDENCE_TYPE,
        "evidence_sha256": actual_file_sha256,
        "payload_sha256": document["payload_sha256"],
        "candidate_image_config_digest": payload["candidate_image_config_digest"],
        "candidate_image_digest": payload["candidate_image_digest"],
        "candidate_image_digest_source": payload["candidate_image_digest_source"],
        "served_tree_sha256": payload["served_tree_sha256"],
        "database_migration_sha256": payload["database_migration_sha256"],
        "authority_epoch": payload["authority_epoch"],
        "runtime_profile_sha256": payload["runtime_profile_sha256"],
        "retriever_backend": "qdrant",
        "retriever_fallback_allowed": False,
        "postgres_database": postgres["database"],
        "postgres_snapshot_sha256": postgres["snapshot_sha256"],
        "qdrant_collection": qdrant["collection"],
        "qdrant_authentication": qdrant["authentication"],
        "qdrant_snapshot_sha256": qdrant["snapshot_sha256"],
        "source_git_sha": payload["source_git_sha"],
    }
    if set(binding) != MANIFEST_BINDING_KEYS:
        raise EvidenceError("internal manifest binding schema mismatch")
    return binding


def promotion_summary(document: dict, *, file_sha256: str | None = None) -> dict:
    document = validate_promotion_document(document)
    canonical_hash = promotion_evidence_sha256(document)
    actual_hash = file_sha256 or canonical_hash
    _require_sha256(actual_hash, "promotion_evidence_sha256")
    if not hmac.compare_digest(actual_hash, canonical_hash):
        raise EvidenceError("promotion summary hash does not match canonical bytes")
    payload = document["payload"]
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_type": PROMOTION_EVIDENCE_TYPE,
        "evidence_sha256": actual_hash,
        "rc_descriptor_sha256": payload["rc_descriptor_sha256"],
        "run_label": payload["results"]["run_label"],
        "results_sha256": payload["results"]["results_sha256"],
    }


def _write_new_file(path: Path, content: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    fd: int | None = None
    created = False
    try:
        fd = os.open(path, flags, 0o600)
        created = True
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
    except OSError as exc:
        if created:
            try:
                path.unlink()
            except OSError:
                pass
        raise EvidenceError("evidence output cannot be created exclusively") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _load_runtime_profile(path: str) -> dict:
    raw = _read_regular_file(Path(path))
    value = _parse_json(raw)
    if not isinstance(value, dict):
        raise EvidenceError("runtime profile file is not a JSON object")
    _validate_json_tree(value)
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="v2_rc_evidence.py")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create a new canonical evidence file")
    create.add_argument("--output", required=True)
    create.add_argument("--candidate-image-digest", required=True)
    create.add_argument("--candidate-image-config-digest", required=True)
    create.add_argument("--served-tree-sha256", required=True)
    create.add_argument("--database-migration-sha256", required=True)
    create.add_argument("--authority-epoch", required=True)
    create.add_argument("--postgres-database", required=True)
    create.add_argument("--postgres-snapshot-sha256", required=True)
    create.add_argument("--qdrant-collection", required=True)
    create.add_argument("--qdrant-snapshot-sha256", required=True)
    create.add_argument("--runtime-profile-file", required=True)
    create.add_argument("--source-git-sha", required=True)

    finalize = commands.add_parser(
        "finalize", help="create post-adjudication promotion evidence"
    )
    finalize.add_argument("--output", required=True)
    finalize.add_argument("--rc-descriptor", required=True)
    finalize.add_argument("--run-label", required=True)
    finalize.add_argument("--results-file", required=True)

    verify = commands.add_parser(
        "verify", help="validate and summarize canonical evidence"
    )
    verify.add_argument("evidence_file")
    verify.add_argument("--expected-sha256")

    verify_promotion = commands.add_parser(
        "verify-promotion", help="validate final Gate-10 promotion evidence"
    )
    verify_promotion.add_argument("evidence_file")
    verify_promotion.add_argument("--expected-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            document = build_document(
                candidate_image_digest=args.candidate_image_digest,
                candidate_image_config_digest=args.candidate_image_config_digest,
                served_tree_sha256=args.served_tree_sha256,
                database_migration_sha256=args.database_migration_sha256,
                authority_epoch=args.authority_epoch,
                postgres_database=args.postgres_database,
                postgres_snapshot_sha256=args.postgres_snapshot_sha256,
                qdrant_collection=args.qdrant_collection,
                qdrant_snapshot_sha256=args.qdrant_snapshot_sha256,
                runtime_profile=_load_runtime_profile(args.runtime_profile_file),
                source_git_sha=args.source_git_sha,
            )
            content = canonical_evidence_bytes(document)
            _write_new_file(Path(args.output), content)
            summary = manifest_binding(
                document, file_sha256=hashlib.sha256(content).hexdigest()
            )
        elif args.command == "finalize":
            descriptor, _descriptor_hash = load_evidence(args.rc_descriptor)
            results_raw = read_results_bytes(args.results_file)
            results_value = _parse_json(results_raw)
            if not isinstance(results_value, dict):
                raise EvidenceError("results file is not a JSON object")
            manifest = results_value.get("manifest")
            if not isinstance(manifest, dict):
                raise EvidenceError("results manifest is unavailable")
            if manifest.get("run_label") != args.run_label:
                raise EvidenceError(
                    "results run_label does not match finalization input"
                )
            if manifest.get("release_candidate_evidence") != manifest_binding(
                descriptor
            ):
                raise EvidenceError("results do not bind the exact RC descriptor")
            document = build_promotion_document(
                rc_descriptor=descriptor,
                run_label=args.run_label,
                results_sha256=hashlib.sha256(results_raw).hexdigest(),
            )
            content = canonical_promotion_bytes(document)
            _write_new_file(Path(args.output), content)
            summary = promotion_summary(
                document, file_sha256=hashlib.sha256(content).hexdigest()
            )
        elif args.command == "verify":
            document, file_hash = load_evidence(
                args.evidence_file, expected_sha256=args.expected_sha256
            )
            summary = manifest_binding(document, file_sha256=file_hash)
        else:
            document, file_hash = load_promotion_evidence(
                args.evidence_file, expected_sha256=args.expected_sha256
            )
            summary = promotion_summary(document, file_sha256=file_hash)
    except EvidenceError as exc:
        print(f"v2_rc_evidence: {exc}", file=sys.stderr)
        return 2
    print(_canonical_json_bytes(summary).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
