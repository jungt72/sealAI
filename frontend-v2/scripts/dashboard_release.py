#!/usr/bin/env python3
"""Prepare and verify immutable dashboard releases without activating them.

The CLI intentionally has no activation/apply command. It may materialize a
content-addressed release and produce an exact activation or rollback plan, but
only the separately installed GATE-08 deployment boundary may execute the
tested atomic symlink primitive.
"""

from __future__ import annotations

import argparse
import dataclasses
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping, Sequence


SCHEMA_VERSION = 1
MAX_FILES = 10_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_PATH_BYTES = 512
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TOOL_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
RELEASE_ID_RE = re.compile(
    r"^(?P<source>[0-9a-f]{40}(?:[0-9a-f]{24})?)-(?P<artifact>[0-9a-f]{64})$"
)
RESERVED_CANDIDATE_PATHS = frozenset({"release.json", "release-manifest.json"})


class ReleaseError(RuntimeError):
    """A safe, non-secret release validation error."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclasses.dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256}


@dataclasses.dataclass(frozen=True)
class Artifact:
    source_git_sha: str
    source_date_epoch: int
    npm_lock_sha256: str
    node_version: str
    npm_version: str
    artifact_sha256: str
    release_id: str
    total_bytes: int
    files: tuple[FileRecord, ...]

    def manifest(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "release_id": self.release_id,
            "source_git_sha": self.source_git_sha,
            "source_date_epoch": self.source_date_epoch,
            "npm_lock_sha256": self.npm_lock_sha256,
            "node_version": self.node_version,
            "npm_version": self.npm_version,
            "artifact_sha256": self.artifact_sha256,
            "total_bytes": self.total_bytes,
            "files": [record.as_dict() for record in self.files],
        }


def _manifest_bytes(artifact: Artifact) -> bytes:
    payload = (
        json.dumps(
            artifact.manifest(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        + b"\n"
    )
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ReleaseError("release_manifest_too_large")
    return payload


def _emit(payload: Mapping[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _normalized_absolute(path: Path) -> bool:
    return path.is_absolute() and str(path) == os.path.normpath(str(path))


def _safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and bool(path.parts)
        and value != "."
        and not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
        and str(path) == value
        and len(value.encode("utf-8")) <= MAX_PATH_BYTES
        and not any(
            ord(character) < 0x20 or ord(character) == 0x7F for character in value
        )
    )


def _open_directory(path: Path, *, reason: str) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise ReleaseError(reason) from None
    metadata = os.fstat(descriptor)
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or mode & 0o022
    ):
        os.close(descriptor)
        raise ReleaseError(reason)
    return descriptor


def _directory_identity(path: Path, *, reason: str) -> tuple[int, int]:
    descriptor = _open_directory(path, reason=reason)
    try:
        metadata = os.fstat(descriptor)
        return metadata.st_dev, metadata.st_ino
    finally:
        os.close(descriptor)


def _assert_same_directory(
    path: Path, identity: tuple[int, int], *, reason: str
) -> None:
    if _directory_identity(path, reason=reason) != identity:
        raise ReleaseError(reason)


def _open_relative_file(root: Path, relative: str, *, reason: str) -> int:
    """Open a regular-file path without following any intermediate symlink."""
    if not _safe_relative(relative):
        raise ReleaseError(reason)
    components = PurePosixPath(relative).parts
    directory_fd = _open_directory(root, reason=reason)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        for component in components[:-1]:
            try:
                next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            except OSError:
                raise ReleaseError(reason) from None
            metadata = os.fstat(next_fd)
            mode = stat.S_IMODE(metadata.st_mode)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or mode & 0o022
            ):
                os.close(next_fd)
                raise ReleaseError(reason)
            os.close(directory_fd)
            directory_fd = next_fd
        file_flags = (
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            return os.open(components[-1], file_flags, dir_fd=directory_fd)
        except OSError:
            raise ReleaseError(reason) from None
    finally:
        os.close(directory_fd)


def _read_file_record(
    root: Path, relative: str, *, tree: str = "candidate"
) -> FileRecord:
    if not _safe_relative(relative):
        raise ReleaseError(f"unsafe_{tree}_path")
    descriptor = _open_relative_file(root, relative, reason=f"unsafe_{tree}_file")
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_size > MAX_FILE_BYTES
            or stat.S_IMODE(before.st_mode) & 0o022
        ):
            raise ReleaseError(f"unsafe_{tree}_file")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ReleaseError(f"{tree}_file_too_large")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or total != before.st_size:
            raise ReleaseError(f"{tree}_changed_during_read")
        return FileRecord(path=relative, size=total, sha256=digest.hexdigest())
    finally:
        os.close(descriptor)


def _walk_candidate(root: Path) -> tuple[FileRecord, ...]:
    root_identity = _directory_identity(root, reason="unsafe_candidate_root")
    records: list[FileRecord] = []
    total_bytes = 0
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        current_metadata = current_path.lstat()
        if (
            not stat.S_ISDIR(current_metadata.st_mode)
            or stat.S_IMODE(current_metadata.st_mode) & 0o022
            or current_metadata.st_uid != os.geteuid()
        ):
            raise ReleaseError("unsafe_candidate_directory")
        directories.sort()
        files.sort()
        for name in tuple(directories):
            child = current_path / name
            child_metadata = child.lstat()
            if stat.S_ISLNK(child_metadata.st_mode) or not stat.S_ISDIR(
                child_metadata.st_mode
            ):
                raise ReleaseError("unsafe_candidate_directory")
        for name in files:
            relative = (current_path / name).relative_to(root).as_posix()
            if relative in RESERVED_CANDIDATE_PATHS:
                raise ReleaseError("reserved_candidate_path")
            record = _read_file_record(root, relative)
            records.append(record)
            total_bytes += record.size
            if len(records) > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                raise ReleaseError("candidate_tree_limit_exceeded")
    _assert_same_directory(root, root_identity, reason="candidate_root_changed")
    records.sort(key=lambda record: record.path)
    if not records or "index.html" not in {record.path for record in records}:
        raise ReleaseError("candidate_index_missing")
    return tuple(records)


def _artifact_digest_material(
    *,
    source_git_sha: str,
    source_date_epoch: int,
    npm_lock_sha256: str,
    node_version: str,
    npm_version: str,
    records: Sequence[FileRecord],
) -> bytes:
    material = {
        "schema_version": SCHEMA_VERSION,
        "source_git_sha": source_git_sha,
        "source_date_epoch": source_date_epoch,
        "npm_lock_sha256": npm_lock_sha256,
        "node_version": node_version,
        "npm_version": npm_version,
        "files": [record.as_dict() for record in records],
    }
    return json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def inspect_candidate(
    candidate: Path,
    *,
    source_git_sha: str,
    source_date_epoch: int,
    npm_lock_sha256: str,
    node_version: str,
    npm_version: str,
) -> Artifact:
    if (
        not _normalized_absolute(candidate)
        or not SOURCE_SHA_RE.fullmatch(source_git_sha)
        or not isinstance(source_date_epoch, int)
        or isinstance(source_date_epoch, bool)
        or not 0 <= source_date_epoch <= 4_102_444_800
        or not SHA256_RE.fullmatch(npm_lock_sha256)
        or not TOOL_VERSION_RE.fullmatch(node_version)
        or not TOOL_VERSION_RE.fullmatch(npm_version)
    ):
        raise ReleaseError("invalid_build_identity")
    records = _walk_candidate(candidate)
    digest = hashlib.sha256(
        _artifact_digest_material(
            source_git_sha=source_git_sha,
            source_date_epoch=source_date_epoch,
            npm_lock_sha256=npm_lock_sha256,
            node_version=node_version,
            npm_version=npm_version,
            records=records,
        )
    ).hexdigest()
    release_id = f"{source_git_sha}-{digest}"
    artifact = Artifact(
        source_git_sha=source_git_sha,
        source_date_epoch=source_date_epoch,
        npm_lock_sha256=npm_lock_sha256,
        node_version=node_version,
        npm_version=npm_version,
        artifact_sha256=digest,
        release_id=release_id,
        total_bytes=sum(record.size for record in records),
        files=records,
    )
    _manifest_bytes(artifact)
    return artifact


def _ensure_release_root(path: Path) -> tuple[Path, Path]:
    if not _normalized_absolute(path):
        raise ReleaseError("invalid_release_root")
    if not path.exists():
        try:
            path.mkdir(mode=0o755, parents=False)
        except OSError:
            raise ReleaseError("release_root_unavailable") from None
    root_identity = _directory_identity(path, reason="unsafe_release_root")
    if stat.S_IMODE(path.stat().st_mode) & 0o055 != 0o055:
        raise ReleaseError("release_root_not_traversable")
    artifacts = path / "artifacts"
    if not artifacts.exists():
        try:
            artifacts.mkdir(mode=0o755)
        except OSError:
            raise ReleaseError("artifact_root_unavailable") from None
    _directory_identity(artifacts, reason="unsafe_artifact_root")
    if stat.S_IMODE(artifacts.stat().st_mode) & 0o055 != 0o055:
        raise ReleaseError("artifact_root_not_traversable")
    _assert_same_directory(path, root_identity, reason="release_root_changed")
    return path, artifacts


def _existing_release_root(path: Path) -> tuple[Path, Path]:
    if not _normalized_absolute(path):
        raise ReleaseError("invalid_release_root")
    root_identity = _directory_identity(path, reason="unsafe_release_root")
    if stat.S_IMODE(path.stat().st_mode) & 0o055 != 0o055:
        raise ReleaseError("release_root_not_traversable")
    artifacts = path / "artifacts"
    _directory_identity(artifacts, reason="unsafe_artifact_root")
    if stat.S_IMODE(artifacts.stat().st_mode) & 0o055 != 0o055:
        raise ReleaseError("artifact_root_not_traversable")
    _assert_same_directory(path, root_identity, reason="release_root_changed")
    return path, artifacts


@contextmanager
def _publication_lock(root: Path) -> Iterator[None]:
    """Serialize publishers while retaining atomic O_EXCL no-clobber semantics."""
    root_fd = _open_directory(root, reason="unsafe_release_root")
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        try:
            lock_fd = os.open(".prepare.lock", flags, 0o600, dir_fd=root_fd)
        except OSError:
            raise ReleaseError("release_lock_unavailable") from None
        try:
            metadata = os.fstat(lock_fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise ReleaseError("unsafe_release_lock")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            path_metadata = os.stat(
                ".prepare.lock", dir_fd=root_fd, follow_symlinks=False
            )
            if (path_metadata.st_dev, path_metadata.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ):
                raise ReleaseError("release_lock_changed")
            yield
        finally:
            os.close(lock_fd)
    finally:
        os.close(root_fd)


def _remove_owned_tree(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    for current, directories, _files in os.walk(path, topdown=True, followlinks=False):
        try:
            os.chmod(current, 0o700)
        except OSError:
            pass
        for name in directories:
            child = Path(current) / name
            if not child.is_symlink():
                try:
                    os.chmod(child, 0o700)
                except OSError:
                    pass
    shutil.rmtree(path, ignore_errors=True)


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise ReleaseError("release_write_failed")
        view = view[written:]


def _copy_verified_candidate(
    candidate: Path, destination_root: Path, artifact: Artifact
) -> None:
    try:
        destination_root.mkdir(mode=0o700)
    except FileExistsError:
        raise ReleaseError("release_no_clobber_conflict") from None
    except OSError:
        raise ReleaseError("release_directory_creation_failed") from None
    try:
        for record in artifact.files:
            destination = destination_root / record.path
            destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            destination_flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            source_fd = _open_relative_file(
                candidate, record.path, reason="candidate_changed_before_copy"
            )
            destination_fd: int | None = None
            try:
                source_metadata = os.fstat(source_fd)
                if (
                    not stat.S_ISREG(source_metadata.st_mode)
                    or source_metadata.st_uid != os.geteuid()
                    or source_metadata.st_nlink != 1
                    or source_metadata.st_size != record.size
                    or stat.S_IMODE(source_metadata.st_mode) & 0o022
                ):
                    raise ReleaseError("candidate_changed_before_copy")
                destination_fd = os.open(destination, destination_flags, 0o600)
                digest = hashlib.sha256()
                copied = 0
                while True:
                    chunk = os.read(source_fd, 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    _write_all(destination_fd, chunk)
                    copied += len(chunk)
                source_after = os.fstat(source_fd)
                if (
                    (
                        source_metadata.st_dev,
                        source_metadata.st_ino,
                        source_metadata.st_size,
                        source_metadata.st_mtime_ns,
                    )
                    != (
                        source_after.st_dev,
                        source_after.st_ino,
                        source_after.st_size,
                        source_after.st_mtime_ns,
                    )
                    or copied != record.size
                    or digest.hexdigest() != record.sha256
                ):
                    raise ReleaseError("candidate_changed_during_copy")
                os.fsync(destination_fd)
                os.fchmod(destination_fd, 0o444)
            finally:
                os.close(source_fd)
                if destination_fd is not None:
                    os.close(destination_fd)
        manifest_path = destination_root / "release.json"
        manifest_bytes = _manifest_bytes(artifact)
        manifest_fd = os.open(
            manifest_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            _write_all(manifest_fd, manifest_bytes)
            os.fsync(manifest_fd)
            os.fchmod(manifest_fd, 0o444)
        finally:
            os.close(manifest_fd)
        directories = sorted(
            (path for path in destination_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            os.chmod(directory, 0o555)
            directory_fd = _open_directory(
                directory, reason="release_directory_finalize_failed"
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        os.chmod(destination_root, 0o555)
        destination_fd = _open_directory(
            destination_root, reason="release_directory_finalize_failed"
        )
        try:
            os.fsync(destination_fd)
        finally:
            os.close(destination_fd)
    except Exception:
        _remove_owned_tree(destination_root)
        raise


def _load_manifest(release: Path) -> Artifact:
    manifest_path = release / "release.json"
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(manifest_path, flags)
    except OSError:
        raise ReleaseError("release_manifest_unavailable") from None
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_size > MAX_MANIFEST_BYTES
            or stat.S_IMODE(before.st_mode) != 0o444
        ):
            raise ReleaseError("unsafe_release_manifest")
        raw = os.read(descriptor, MAX_MANIFEST_BYTES + 1)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or len(raw) != before.st_size:
            raise ReleaseError("release_manifest_changed_during_read")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReleaseError("invalid_release_manifest") from None
    expected = {
        "schema_version",
        "release_id",
        "source_git_sha",
        "source_date_epoch",
        "npm_lock_sha256",
        "node_version",
        "npm_version",
        "artifact_sha256",
        "total_bytes",
        "files",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value.get("schema_version") != 1
    ):
        raise ReleaseError("invalid_release_manifest")
    canonical = (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        + b"\n"
    )
    if raw != canonical:
        raise ReleaseError("noncanonical_release_manifest")
    files_raw = value.get("files")
    if not isinstance(files_raw, list) or not files_raw or len(files_raw) > MAX_FILES:
        raise ReleaseError("invalid_release_manifest")
    records: list[FileRecord] = []
    for item in files_raw:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise ReleaseError("invalid_release_manifest")
        relative = item.get("path")
        size = item.get("size")
        digest = item.get("sha256")
        if (
            not isinstance(relative, str)
            or not _safe_relative(relative)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 <= size <= MAX_FILE_BYTES
            or not isinstance(digest, str)
            or not SHA256_RE.fullmatch(digest)
        ):
            raise ReleaseError("invalid_release_manifest")
        records.append(FileRecord(relative, size, digest))
    record_paths = [record.path for record in records]
    if record_paths != sorted(record_paths) or len(record_paths) != len(
        set(record_paths)
    ):
        raise ReleaseError("noncanonical_release_manifest")
    source = value.get("source_git_sha")
    epoch = value.get("source_date_epoch")
    lock_hash = value.get("npm_lock_sha256")
    node_version = value.get("node_version")
    npm_version = value.get("npm_version")
    artifact_hash = value.get("artifact_sha256")
    release_id = value.get("release_id")
    total_bytes = value.get("total_bytes")
    if (
        not isinstance(source, str)
        or not SOURCE_SHA_RE.fullmatch(source)
        or not isinstance(epoch, int)
        or isinstance(epoch, bool)
        or not 0 <= epoch <= 4_102_444_800
        or not isinstance(lock_hash, str)
        or not SHA256_RE.fullmatch(lock_hash)
        or not isinstance(node_version, str)
        or not TOOL_VERSION_RE.fullmatch(node_version)
        or not isinstance(npm_version, str)
        or not TOOL_VERSION_RE.fullmatch(npm_version)
        or not isinstance(artifact_hash, str)
        or not SHA256_RE.fullmatch(artifact_hash)
        or not isinstance(release_id, str)
        or not RELEASE_ID_RE.fullmatch(release_id)
        or not isinstance(total_bytes, int)
        or isinstance(total_bytes, bool)
        or total_bytes != sum(record.size for record in records)
    ):
        raise ReleaseError("invalid_release_manifest")
    calculated = hashlib.sha256(
        _artifact_digest_material(
            source_git_sha=source,
            source_date_epoch=epoch,
            npm_lock_sha256=lock_hash,
            node_version=node_version,
            npm_version=npm_version,
            records=records,
        )
    ).hexdigest()
    if artifact_hash != calculated or release_id != f"{source}-{calculated}":
        raise ReleaseError("release_identity_mismatch")
    return Artifact(
        source,
        epoch,
        lock_hash,
        node_version,
        npm_version,
        calculated,
        release_id,
        total_bytes,
        tuple(records),
    )


def verify_release(release: Path) -> Artifact:
    if not _normalized_absolute(release) or not RELEASE_ID_RE.fullmatch(release.name):
        raise ReleaseError("invalid_release_path")
    release_identity = _directory_identity(release, reason="unsafe_release_directory")
    if stat.S_IMODE(release.stat().st_mode) != 0o555:
        raise ReleaseError("mutable_release_directory")
    artifact = _load_manifest(release)
    if artifact.release_id != release.name:
        raise ReleaseError("release_path_identity_mismatch")
    expected_paths = {record.path for record in artifact.files} | {"release.json"}
    expected_directories = {
        PurePosixPath(*PurePosixPath(path).parts[:index]).as_posix()
        for path in expected_paths
        for index in range(1, len(PurePosixPath(path).parts))
    }
    actual_paths: set[str] = set()
    actual_directories: set[str] = set()
    for current, directories, files in os.walk(
        release, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        for name in directories:
            directory = current_path / name
            metadata = directory.lstat()
            relative = directory.relative_to(release).as_posix()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o555
            ):
                raise ReleaseError("unsafe_release_directory")
            actual_directories.add(relative)
        for name in files:
            relative = (current_path / name).relative_to(release).as_posix()
            actual_paths.add(relative)
    if actual_paths != expected_paths or actual_directories != expected_directories:
        raise ReleaseError("release_file_set_mismatch")
    for record in artifact.files:
        actual = _read_file_record(release, record.path, tree="release")
        if (
            actual != record
            or stat.S_IMODE((release / record.path).stat().st_mode) != 0o444
        ):
            raise ReleaseError("release_file_mismatch")
    _assert_same_directory(
        release, release_identity, reason="release_changed_during_verify"
    )
    return artifact


def prepare_release(
    candidate: Path, release_root: Path, artifact: Artifact
) -> tuple[Path, bool]:
    if not _normalized_absolute(candidate) or not _normalized_absolute(release_root):
        raise ReleaseError("invalid_release_paths")
    candidate_real = Path(os.path.realpath(candidate))
    release_root_real = Path(os.path.realpath(release_root))
    if (
        candidate_real == release_root_real
        or candidate_real in release_root_real.parents
        or release_root_real in candidate_real.parents
    ):
        raise ReleaseError("candidate_release_path_overlap")
    fresh_artifact = inspect_candidate(
        candidate,
        source_git_sha=artifact.source_git_sha,
        source_date_epoch=artifact.source_date_epoch,
        npm_lock_sha256=artifact.npm_lock_sha256,
        node_version=artifact.node_version,
        npm_version=artifact.npm_version,
    )
    if fresh_artifact != artifact:
        raise ReleaseError("candidate_changed_before_prepare")
    root, artifacts_root = _ensure_release_root(release_root)
    root_identity = _directory_identity(root, reason="unsafe_release_root")
    final = artifacts_root / artifact.release_id
    with _publication_lock(root):
        _assert_same_directory(root, root_identity, reason="release_root_changed")
        if final.exists() or final.is_symlink():
            try:
                existing = verify_release(final)
            except ReleaseError:
                raise ReleaseError("release_no_clobber_conflict") from None
            if existing != artifact:
                raise ReleaseError("release_no_clobber_conflict")
            return final, False
        # mkdir(2) is the cross-platform no-clobber reservation. The directory
        # is never referenced by `current` while it is populated and verified.
        _copy_verified_candidate(candidate, final, artifact)
        _assert_same_directory(root, root_identity, reason="release_root_changed")
        artifacts_fd = _open_directory(artifacts_root, reason="unsafe_artifact_root")
        try:
            os.fsync(artifacts_fd)
        finally:
            os.close(artifacts_fd)
        verify_release(final)
        return final, True


def _read_release_link(root: Path, name: str, *, missing_ok: bool) -> str | None:
    path = root / name
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise ReleaseError(f"{name}_link_missing") from None
    if not stat.S_ISLNK(metadata.st_mode):
        raise ReleaseError(f"unsafe_{name}_link")
    target = os.readlink(path)
    expected_prefix = "artifacts/"
    if not target.startswith(expected_prefix) or not RELEASE_ID_RE.fullmatch(
        target.removeprefix(expected_prefix)
    ):
        raise ReleaseError(f"unsafe_{name}_target")
    release = root / target
    verify_release(release)
    return target


def activation_plan(release_root: Path, release_id: str) -> dict[str, object]:
    root, artifacts = _existing_release_root(release_root)
    if not RELEASE_ID_RE.fullmatch(release_id):
        raise ReleaseError("invalid_release_id")
    target = f"artifacts/{release_id}"
    artifact = verify_release(artifacts / release_id)
    current = _read_release_link(root, "current", missing_ok=True)
    rollback = _read_release_link(root, "rollback", missing_ok=True)
    if current == target:
        action = "already_current"
    else:
        action = "activate"
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "dashboard-activate-plan",
        "gate_required": "GATE-08",
        "mutation_performed": False,
        "action": action,
        "release_id": release_id,
        "source_git_sha": artifact.source_git_sha,
        "artifact_sha256": artifact.artifact_sha256,
        "current_target": current,
        "rollback_target": rollback,
        "ordered_atomic_steps": (
            []
            if action == "already_current"
            else [
                "atomically_set_rollback_to_verified_current_if_present",
                "atomically_set_current_to_verified_release",
                "fsync_release_root",
                "verify_current_release_manifest",
            ]
        ),
    }


def rollback_plan(release_root: Path) -> dict[str, object]:
    root, _artifacts = _existing_release_root(release_root)
    current = _read_release_link(root, "current", missing_ok=False)
    rollback = _read_release_link(root, "rollback", missing_ok=False)
    if current == rollback:
        raise ReleaseError("rollback_target_equals_current")
    release_id = rollback.removeprefix("artifacts/")
    artifact = verify_release(root / rollback)
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": "dashboard-rollback-plan",
        "gate_required": "GATE-08",
        "mutation_performed": False,
        "release_id": release_id,
        "source_git_sha": artifact.source_git_sha,
        "artifact_sha256": artifact.artifact_sha256,
        "current_target": current,
        "rollback_target": rollback,
        "ordered_atomic_steps": [
            "atomically_set_rollback_to_verified_current",
            "atomically_set_current_to_verified_rollback",
            "fsync_release_root",
            "verify_current_release_manifest",
        ],
    }


def _atomic_set_release_link(root: Path, name: str, target: str) -> None:
    """Tested primitive reserved for the installed GATE-08 executor."""
    if name not in {"current", "rollback"} or not target.startswith("artifacts/"):
        raise ReleaseError("invalid_atomic_link_request")
    release_id = target.removeprefix("artifacts/")
    if not RELEASE_ID_RE.fullmatch(release_id):
        raise ReleaseError("invalid_atomic_link_request")
    root, _artifacts = _existing_release_root(root)
    verify_release(root / target)
    root_identity = _directory_identity(root, reason="unsafe_release_root")
    _read_release_link(root, name, missing_ok=True)
    pending_name = f".{name}.{os.getpid()}.{secrets.token_hex(12)}.tmp"
    pending = root / pending_name
    try:
        os.symlink(target, pending)
        pending_metadata = pending.lstat()
        if not stat.S_ISLNK(pending_metadata.st_mode) or os.readlink(pending) != target:
            raise ReleaseError("atomic_link_staging_failed")
        _assert_same_directory(root, root_identity, reason="release_root_changed")
        os.replace(pending, root / name)
        root_fd = _open_directory(root, reason="unsafe_release_root")
        try:
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
    except OSError as error:
        if error.errno == errno.EEXIST:
            raise ReleaseError("atomic_link_conflict") from None
        raise ReleaseError("atomic_link_failed") from None
    finally:
        try:
            pending.unlink()
        except FileNotFoundError:
            pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Immutable dashboard release preparer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "prepare"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--candidate", required=True)
        subparser.add_argument("--source-git-sha", required=True)
        subparser.add_argument("--source-date-epoch", required=True, type=int)
        subparser.add_argument("--npm-lock-sha256", required=True)
        subparser.add_argument("--node-version", required=True)
        subparser.add_argument("--npm-version", required=True)
        if command == "prepare":
            subparser.add_argument("--release-root", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--release", required=True)
    activate = subparsers.add_parser("plan-activate")
    activate.add_argument("--release-root", required=True)
    activate.add_argument("--release-id", required=True)
    rollback = subparsers.add_parser("plan-rollback")
    rollback.add_argument("--release-root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    try:
        command = str(arguments.command)
        if command in {"inspect", "prepare"}:
            artifact = inspect_candidate(
                Path(arguments.candidate),
                source_git_sha=str(arguments.source_git_sha),
                source_date_epoch=int(arguments.source_date_epoch),
                npm_lock_sha256=str(arguments.npm_lock_sha256),
                node_version=str(arguments.node_version),
                npm_version=str(arguments.npm_version),
            )
            if command == "inspect":
                _emit(
                    {
                        "result": "ok",
                        "operation": "dashboard-inspect",
                        "mutation_performed": False,
                        **artifact.manifest(),
                    }
                )
                return 0
            release, created = prepare_release(
                Path(arguments.candidate), Path(arguments.release_root), artifact
            )
            _emit(
                {
                    "result": "ok",
                    "operation": "dashboard-prepare",
                    "release_created": created,
                    "live_activation_performed": False,
                    "gate_required_for_activation": "GATE-08",
                    "release_id": artifact.release_id,
                    "source_git_sha": artifact.source_git_sha,
                    "artifact_sha256": artifact.artifact_sha256,
                    "release_path_sha256": hashlib.sha256(
                        str(release).encode()
                    ).hexdigest(),
                }
            )
            return 0
        if command == "verify":
            artifact = verify_release(Path(arguments.release))
            _emit(
                {
                    "result": "ok",
                    "operation": "dashboard-verify",
                    "mutation_performed": False,
                    **artifact.manifest(),
                }
            )
            return 0
        if command == "plan-activate":
            _emit(
                activation_plan(Path(arguments.release_root), str(arguments.release_id))
            )
            return 0
        if command == "plan-rollback":
            _emit(rollback_plan(Path(arguments.release_root)))
            return 0
        raise ReleaseError("invalid_command")
    except ReleaseError as error:
        _emit(
            {
                "result": "error",
                "operation": getattr(arguments, "command", "unknown"),
                "reason_code": error.reason_code,
                "live_activation_performed": False,
            }
        )
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
