"""One-shot Claude Sonnet 5 safe-mode runner for frozen audit corpora."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
from typing import Any

from sealai_v2.core.material_evidence_ai_review import (
    AIReviewErrorCode,
    AIReviewSnapshotV1,
    AIReviewValidationError,
    AgentExecutionIsolationV1,
    ChallengerAgentRunV1,
)
from sealai_v2.core.material_evidence_v2 import EvidenceManifestSnapshotV2
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.material_evidence_ai_review.audit import (
    AUDIT_OUTPUT_DOMAIN,
    CLAUDE_TASK_V1,
    ClaudeChallengeV1,
    build_claude_audit_input,
    parse_claude_audit_report,
)


RUN_RECEIPT_DOMAIN = b"sealai:mat-evid-ai-review:claude-run-receipt:v1\x00"
EXECUTABLE_ATTESTATION_DOMAIN = (
    b"sealai:mat-evid-ai-review:claude-executable-attestation:v1\x00"
)
_RUN_RECEIPT_TOKEN = object()
_PENDING_RUN_RECEIPTS: dict[str, int] = {}
_TRUST_MANIFEST_PATH = Path(__file__).with_name("claude-executable-trust-v1.json")
_TRUST_MANIFEST_FILE_SHA256 = (
    "af3a817c6dc4c9ce6e9c61bb18897470391ce795a68e3ceffa3e60e3cab20ae1"
)
_TRUST_MANIFEST_FIELDS = frozenset(
    {"contract_version", "installations", "schema_version"}
)
_TRUST_INSTALLATION_FIELDS = frozenset(
    {
        "entrypoint",
        "executable_sha256",
        "machine",
        "platform",
        "resolved_path",
        "version",
    }
)
_SHA256_HEX = frozenset("0123456789abcdef")
_ENVELOPE_FIELDS = frozenset(
    {
        "api_error_status",
        "duration_api_ms",
        "duration_ms",
        "fast_mode_state",
        "is_error",
        "modelUsage",
        "num_turns",
        "permission_denials",
        "result",
        "session_id",
        "stop_reason",
        "subtype",
        "terminal_reason",
        "time_to_request_ms",
        "total_cost_usd",
        "ttft_ms",
        "ttft_stream_ms",
        "type",
        "usage",
        "uuid",
    }
)
_MODEL_USAGE_FIELDS = frozenset(
    {
        "cacheCreationInputTokens",
        "cacheReadInputTokens",
        "contextWindow",
        "costUSD",
        "inputTokens",
        "maxOutputTokens",
        "outputTokens",
        "webSearchRequests",
    }
)
_USAGE_FIELDS = frozenset(
    {
        "cache_creation",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "inference_geo",
        "input_tokens",
        "iterations",
        "output_tokens",
        "server_tool_use",
        "service_tier",
        "speed",
    }
)

_SETTINGS = {
    "disableAgentView": True,
    "disableAllHooks": True,
    "disableAutoMode": "disable",
    "disableDeepLinkRegistration": "disable",
}
_PROMPT_VERSION = "mat-evid-ai-challenge.v1"
_PROMPT_BYTES = CLAUDE_TASK_V1.encode("utf-8")
_SENSITIVE_ENV_MARKERS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "COOKIE",
)
_TRUSTED_CHILD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
_EXECUTION_MODE = "private-object-verified-stage-v1"


@dataclass(frozen=True, slots=True)
class _TrustedClaudeExecutableV1:
    path: Path
    executable_bytes: bytes
    executable_sha256: str
    version: str
    canonical_attestation_bytes: bytes
    attestation_sha256: str


def _canonical_receipt_bytes(value: dict[str, Any]) -> bytes:
    if type(value) is not dict:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_JSON,
            "persisted Claude artifact must be a JSON object",
        )
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_JSON,
            "persisted Claude artifact is not canonical JSON",
        ) from exc


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_JSON,
                "Claude executable trust manifest contains a duplicate key",
            )
        result[key] = value
    return result


def _trusted_claude_executable() -> _TrustedClaudeExecutableV1:
    """Resolve the exact owner-reviewed CLI identity without consulting PATH."""

    try:
        metadata = _TRUST_MANIFEST_PATH.lstat()
        raw = _TRUST_MANIFEST_PATH.read_bytes()
    except OSError as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude executable trust manifest is unavailable",
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude executable trust manifest must be a regular non-symlink file",
        )
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    if manifest_sha256 != _TRUST_MANIFEST_FILE_SHA256:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "Claude executable trust manifest digest drift",
        )
    try:
        manifest = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_object_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_JSON,
            "Claude executable trust manifest is not strict UTF-8 JSON",
        ) from exc
    if type(manifest) is not dict or set(manifest) != _TRUST_MANIFEST_FIELDS:
        raise AIReviewValidationError(
            AIReviewErrorCode.UNKNOWN_FIELD,
            "Claude executable trust manifest fields are not exact",
        )
    if (
        manifest["contract_version"] != "MAT-EVID-AI-CLAUDE-EXECUTABLE-TRUST.v1"
        or type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or type(manifest["installations"]) is not list
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.UNKNOWN_SCHEMA,
            "Claude executable trust manifest version is unsupported",
        )
    platform_name = platform.system().lower()
    machine = platform.machine().lower()
    candidates = []
    for record in manifest["installations"]:
        if type(record) is not dict or set(record) != _TRUST_INSTALLATION_FIELDS:
            raise AIReviewValidationError(
                AIReviewErrorCode.UNKNOWN_FIELD,
                "Claude executable trust installation fields are not exact",
            )
        if any(type(record[field]) is not str for field in record):
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_TYPE,
                "Claude executable trust installation values must be strings",
            )
        if record["platform"] == platform_name and record["machine"] == machine:
            candidates.append(record)
    if len(candidates) != 1:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "exactly one owner-reviewed Claude installation must match this platform",
        )
    record = candidates[0]
    expected_digest = record["executable_sha256"]
    if len(expected_digest) != 64 or not set(expected_digest) <= _SHA256_HEX:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "trusted Claude executable digest is invalid",
        )
    entrypoint = Path(record["entrypoint"])
    expected_resolved = Path(record["resolved_path"])
    if not entrypoint.is_absolute() or not expected_resolved.is_absolute():
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "trusted Claude executable paths must be absolute",
        )
    try:
        entrypoint_metadata = entrypoint.lstat()
        resolved = entrypoint.resolve(strict=True)
        source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(resolved, source_flags)
    except OSError as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "trusted Claude executable installation is unavailable",
        ) from exc
    try:
        resolved_metadata = os.fstat(source_fd)
        chunks: list[bytes] = []
        while chunk := os.read(source_fd, 1024 * 1024):
            chunks.append(chunk)
        executable_bytes = b"".join(chunks)
    finally:
        os.close(source_fd)
    if (
        not (
            stat.S_ISLNK(entrypoint_metadata.st_mode)
            or stat.S_ISREG(entrypoint_metadata.st_mode)
        )
        or resolved != expected_resolved
        or not stat.S_ISREG(resolved_metadata.st_mode)
        or resolved_metadata.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(resolved_metadata.st_mode) & 0o022
        or not os.access(resolved, os.X_OK)
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "trusted Claude executable ownership, path or mode drift",
        )
    executable_sha256 = hashlib.sha256(executable_bytes).hexdigest()
    if executable_sha256 != expected_digest:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "trusted Claude executable digest drift",
        )
    attestation_value = {
        "execution_mode": _EXECUTION_MODE,
        "installation": record,
        "trust_manifest_file_sha256": manifest_sha256,
    }
    canonical_attestation = _canonical_receipt_bytes(attestation_value)
    return _TrustedClaudeExecutableV1(
        path=resolved,
        executable_bytes=executable_bytes,
        executable_sha256=executable_sha256,
        version=record["version"],
        canonical_attestation_bytes=canonical_attestation,
        attestation_sha256=hashlib.sha256(
            EXECUTABLE_ATTESTATION_DOMAIN + canonical_attestation
        ).hexdigest(),
    )


def _descriptor_sha256(file_descriptor: int) -> str:
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while chunk := os.read(file_descriptor, 1024 * 1024):
        digest.update(chunk)
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _verify_private_stage(
    path: Path, *, expected_sha256: str, expected_identity: tuple[int, int]
) -> None:
    read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        read_fd = os.open(path, read_flags)
    except OSError as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "private Claude executable stage is unavailable",
        ) from exc
    try:
        metadata = os.fstat(read_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != expected_identity
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o500
            or _descriptor_sha256(read_fd) != expected_sha256
        ):
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "private Claude executable stage failed object verification",
            )
    finally:
        os.close(read_fd)


@contextmanager
def _private_staged_executable(trusted: _TrustedClaudeExecutableV1, output: Path):
    """Yield a private, inode-bound stage containing only verified bytes."""

    stage_path = output / ".claude-executable-stage"
    create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    write_fd: int | None = None
    stage_created = False
    created_identity: tuple[int, int] | None = None
    try:
        write_fd = os.open(stage_path, create_flags, 0o500)
        stage_created = True
        initial_metadata = os.fstat(write_fd)
        created_identity = (initial_metadata.st_dev, initial_metadata.st_ino)
        remaining = memoryview(trusted.executable_bytes)
        while remaining:
            written = os.write(write_fd, remaining)
            if written <= 0:
                raise OSError("short write while staging Claude executable")
            remaining = remaining[written:]
        os.fchmod(write_fd, 0o500)
        os.fsync(write_fd)
        metadata = os.fstat(write_fd)
        if (metadata.st_dev, metadata.st_ino) != created_identity:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "private Claude executable stage identity changed while writing",
            )
        os.close(write_fd)
        write_fd = None
        _verify_private_stage(
            stage_path,
            expected_sha256=trusted.executable_sha256,
            expected_identity=created_identity,
        )
        directory_fd = os.open(output, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        yield stage_path, created_identity
        _verify_private_stage(
            stage_path,
            expected_sha256=trusted.executable_sha256,
            expected_identity=created_identity,
        )
    finally:
        try:
            if write_fd is not None:
                os.close(write_fd)
        finally:
            if stage_created:
                try:
                    metadata = stage_path.lstat()
                except FileNotFoundError:
                    metadata = None
                if (
                    metadata is not None
                    and created_identity is not None
                    and created_identity != (metadata.st_dev, metadata.st_ino)
                ):
                    raise AIReviewValidationError(
                        AIReviewErrorCode.INVALID_AGENT,
                        "private Claude executable stage identity changed before cleanup",
                    )
                if metadata is not None:
                    stage_path.unlink()


@dataclass(frozen=True, slots=True, init=False)
class ClaudeChallengeRunReceiptV1:
    challenge: ClaudeChallengeV1
    audit_input_path: str
    audit_input_file_sha256: str
    cli_result_path: str
    cli_result_file_sha256: str
    claude_executable_sha256: str
    claude_executable_attestation_bytes: bytes
    claude_executable_attestation_sha256: str
    process_returncode: int
    session_id_sha256: str
    runner_receipt_sha256: str

    def __init__(
        self,
        *,
        challenge: ClaudeChallengeV1,
        audit_input_path: str,
        audit_input_file_sha256: str,
        cli_result_path: str,
        cli_result_file_sha256: str,
        claude_executable_sha256: str,
        claude_executable_attestation_bytes: bytes,
        claude_executable_attestation_sha256: str,
        process_returncode: int,
        session_id_sha256: str,
        runner_receipt_sha256: str,
        _token: object,
    ) -> None:
        if _token is not _RUN_RECEIPT_TOKEN:
            raise TypeError(
                "ClaudeChallengeRunReceiptV1 may only be created by the one-shot runner"
            )
        for name, value in (
            ("challenge", challenge),
            ("audit_input_path", audit_input_path),
            ("audit_input_file_sha256", audit_input_file_sha256),
            ("cli_result_path", cli_result_path),
            ("cli_result_file_sha256", cli_result_file_sha256),
            ("claude_executable_sha256", claude_executable_sha256),
            (
                "claude_executable_attestation_bytes",
                claude_executable_attestation_bytes,
            ),
            (
                "claude_executable_attestation_sha256",
                claude_executable_attestation_sha256,
            ),
            ("process_returncode", process_returncode),
            ("session_id_sha256", session_id_sha256),
            ("runner_receipt_sha256", runner_receipt_sha256),
        ):
            object.__setattr__(self, name, value)
        self._validate_fields()

    def _validate_fields(self) -> None:
        if type(self.challenge) is not ClaudeChallengeV1:
            raise TypeError("challenge must be ClaudeChallengeV1")
        if type(self.process_returncode) is not int or self.process_returncode != 0:
            raise ValueError("successful receipt requires zero process return code")
        if type(self.claude_executable_attestation_bytes) is not bytes:
            raise ValueError("Claude executable attestation must be canonical bytes")
        for name, value in (
            ("audit_input_file_sha256", self.audit_input_file_sha256),
            ("cli_result_file_sha256", self.cli_result_file_sha256),
            ("claude_executable_sha256", self.claude_executable_sha256),
            (
                "claude_executable_attestation_sha256",
                self.claude_executable_attestation_sha256,
            ),
            ("session_id_sha256", self.session_id_sha256),
            ("runner_receipt_sha256", self.runner_receipt_sha256),
        ):
            if (
                type(value) is not str
                or len(value) != 64
                or not set(value) <= _SHA256_HEX
            ):
                raise ValueError(f"{name} must be 64 lowercase hex")
        for name, value in (
            ("audit_input_path", self.audit_input_path),
            ("cli_result_path", self.cli_result_path),
        ):
            if type(value) is not str or not Path(value).is_absolute():
                raise ValueError(f"{name} must be an absolute path")

    def validate_against(self, snapshot: AIReviewSnapshotV1) -> None:
        """Re-read and bind both immutable runner artifacts before persistence."""

        self._validated_artifacts(snapshot)

    def _validated_artifacts(
        self, snapshot: AIReviewSnapshotV1
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if type(snapshot) is not AIReviewSnapshotV1:
            raise TypeError("snapshot must be AIReviewSnapshotV1")
        self._validate_fields()
        audit_input = _read_private_receipt_file(
            self.audit_input_path,
            expected_sha256=self.audit_input_file_sha256,
        )
        try:
            audit_value = json.loads(audit_input.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_JSON,
                "runner audit-input artifact is not UTF-8 JSON",
            ) from exc
        if _canonical_receipt_bytes(audit_value) != audit_input:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_JSON,
                "runner audit-input artifact is not canonical JSON",
            )
        cli_result = _read_private_receipt_file(
            self.cli_result_path,
            expected_sha256=self.cli_result_file_sha256,
        )
        envelope = _load_cli_envelope(cli_result)
        if _canonical_receipt_bytes(envelope) != cli_result:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_JSON,
                "runner CLI receipt is not canonical JSON",
            )
        validate_persisted_claude_run_artifacts(
            snapshot=snapshot,
            challenge=self.challenge,
            canonical_audit_input_json=audit_value,
            canonical_cli_receipt_json=envelope,
            canonical_executable_attestation_json=json.loads(
                self.claude_executable_attestation_bytes.decode(
                    "utf-8", errors="strict"
                )
            ),
            audit_input_file_sha256=self.audit_input_file_sha256,
            cli_result_file_sha256=self.cli_result_file_sha256,
            claude_executable_sha256=self.claude_executable_sha256,
            claude_executable_attestation_sha256=(
                self.claude_executable_attestation_sha256
            ),
            process_returncode=self.process_returncode,
            session_id_sha256=self.session_id_sha256,
            runner_receipt_sha256=self.runner_receipt_sha256,
        )
        return audit_value, envelope

    def consume_for_persistence(
        self, snapshot: AIReviewSnapshotV1
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Consume exactly one receipt issued by this process after a CLI run."""

        if _PENDING_RUN_RECEIPTS.pop(self.runner_receipt_sha256, None) != id(self):
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "runner receipt was not issued by this process or was already consumed",
            )
        audit_input, cli_receipt = self._validated_artifacts(snapshot)
        executable_attestation = json.loads(
            self.claude_executable_attestation_bytes.decode("utf-8", errors="strict")
        )
        return audit_input, cli_receipt, executable_attestation


def compute_claude_run_receipt_sha256(
    *,
    challenge: ClaudeChallengeV1,
    audit_input_file_sha256: str,
    cli_result_file_sha256: str,
    claude_executable_sha256: str,
    claude_executable_attestation_sha256: str,
    process_returncode: int,
    session_id_sha256: str,
) -> str:
    value = {
        "audit_input_file_sha256": audit_input_file_sha256,
        "challenge_id": challenge.challenge_id,
        "cli_result_file_sha256": cli_result_file_sha256,
        "claude_executable_sha256": claude_executable_sha256,
        "claude_executable_attestation_sha256": (claude_executable_attestation_sha256),
        "process_returncode": process_returncode,
        "session_id_sha256": session_id_sha256,
    }
    return hashlib.sha256(
        RUN_RECEIPT_DOMAIN
        + json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def validate_persisted_claude_run_artifacts(
    *,
    snapshot: AIReviewSnapshotV1,
    challenge: ClaudeChallengeV1,
    canonical_audit_input_json: dict[str, Any],
    canonical_cli_receipt_json: dict[str, Any],
    canonical_executable_attestation_json: dict[str, Any],
    audit_input_file_sha256: str,
    cli_result_file_sha256: str,
    claude_executable_sha256: str,
    claude_executable_attestation_sha256: str,
    process_returncode: int,
    session_id_sha256: str,
    runner_receipt_sha256: str,
) -> None:
    """Reconstruct and validate the durable one-shot execution receipt."""

    if type(snapshot) is not AIReviewSnapshotV1:
        raise TypeError("snapshot must be AIReviewSnapshotV1")
    if type(challenge) is not ClaudeChallengeV1:
        raise TypeError("challenge must be ClaudeChallengeV1")
    for name, value in (
        ("audit_input_file_sha256", audit_input_file_sha256),
        ("cli_result_file_sha256", cli_result_file_sha256),
        ("claude_executable_sha256", claude_executable_sha256),
        (
            "claude_executable_attestation_sha256",
            claude_executable_attestation_sha256,
        ),
        ("session_id_sha256", session_id_sha256),
        ("runner_receipt_sha256", runner_receipt_sha256),
    ):
        if type(value) is not str or len(value) != 64 or not set(value) <= _SHA256_HEX:
            raise AIReviewValidationError(
                AIReviewErrorCode.HASH_MISMATCH,
                f"stored {name} is not a lowercase SHA-256 digest",
            )
    if type(process_returncode) is not int or process_returncode != 0:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "stored Claude process did not complete successfully",
        )

    attestation_bytes = _canonical_receipt_bytes(canonical_executable_attestation_json)
    if hashlib.sha256(
        EXECUTABLE_ATTESTATION_DOMAIN + attestation_bytes
    ).hexdigest() != claude_executable_attestation_sha256 or set(
        canonical_executable_attestation_json
    ) != {"execution_mode", "installation", "trust_manifest_file_sha256"}:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "persisted Claude executable attestation drift",
        )
    installation = canonical_executable_attestation_json["installation"]
    manifest_digest = canonical_executable_attestation_json[
        "trust_manifest_file_sha256"
    ]
    if (
        type(canonical_executable_attestation_json["execution_mode"]) is not str
        or canonical_executable_attestation_json["execution_mode"] != _EXECUTION_MODE
        or type(installation) is not dict
        or set(installation) != _TRUST_INSTALLATION_FIELDS
        or any(type(installation[field]) is not str for field in installation)
        or installation["executable_sha256"] != claude_executable_sha256
        or installation["version"] != challenge.challenger.agent_version
        or not Path(installation["entrypoint"]).is_absolute()
        or not Path(installation["resolved_path"]).is_absolute()
        or type(manifest_digest) is not str
        or len(manifest_digest) != 64
        or not set(manifest_digest) <= _SHA256_HEX
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "persisted Claude executable attestation is not owner-bound",
        )

    audit_bytes = _canonical_receipt_bytes(canonical_audit_input_json)
    if hashlib.sha256(audit_bytes).hexdigest() != audit_input_file_sha256:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "persisted audit-input file hash mismatch",
        )
    expected_input = build_claude_audit_input(snapshot)
    if audit_bytes != expected_input.canonical_bytes:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "persisted audit input differs from the frozen corpus",
        )

    envelope_bytes = _canonical_receipt_bytes(canonical_cli_receipt_json)
    if hashlib.sha256(envelope_bytes).hexdigest() != cli_result_file_sha256:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "persisted Claude CLI receipt file hash mismatch",
        )
    envelope = _load_cli_envelope(envelope_bytes)
    if (
        set(envelope) != _ENVELOPE_FIELDS
        or envelope["session_id"] != "<redacted>"
        or envelope["uuid"] != "<redacted>"
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "persisted Claude transport receipt is not the closed redacted envelope",
        )

    challenge.validate_against(snapshot)
    report = parse_claude_audit_report(envelope["result"], snapshot)
    if report != challenge.report or report.to_dict() != challenge.report.to_dict():
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "persisted Claude output differs from the challenge",
        )
    challenger = challenge.challenger
    if (
        challenger.run_id != f"claude-run-sha256:{session_id_sha256}"
        or challenger.prompt_version != _PROMPT_VERSION
        or challenger.prompt_sha256 != hashlib.sha256(_PROMPT_BYTES).hexdigest()
        or challenger.audit_input_sha256 != expected_input.audit_input_sha256
        or challenger.audit_output_sha256 != challenge.report_sha256
        or challenger.isolation
        != AgentExecutionIsolationV1(False, False, False, 0, 0, False)
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "persisted challenge provenance differs from the one-shot contract",
        )
    expected_receipt_hash = compute_claude_run_receipt_sha256(
        challenge=challenge,
        audit_input_file_sha256=audit_input_file_sha256,
        cli_result_file_sha256=cli_result_file_sha256,
        claude_executable_sha256=claude_executable_sha256,
        claude_executable_attestation_sha256=(claude_executable_attestation_sha256),
        process_returncode=process_returncode,
        session_id_sha256=session_id_sha256,
    )
    if runner_receipt_sha256 != expected_receipt_hash:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH,
            "persisted Claude runner receipt hash mismatch",
        )


def _read_private_receipt_file(path_value: str, *, expected_sha256: str) -> bytes:
    path = Path(path_value)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT, "runner receipt artifact is unavailable"
        ) from exc
    repository = Path(__file__).resolve().parents[4]
    resolved = path.resolve(strict=True)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or resolved == repository
        or repository in resolved.parents
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "runner receipt artifact is not a private regular file outside the repository",
        )
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise AIReviewValidationError(
            AIReviewErrorCode.HASH_MISMATCH, "runner receipt artifact hash mismatch"
        )
    return raw


def _safe_environment() -> dict[str, str]:
    allowed = {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SHELL",
        "TERM",
        "TMPDIR",
        "USER",
    }
    result = {
        key: value
        for key, value in os.environ.items()
        if key in allowed
        and not any(marker in key.upper() for marker in _SENSITIVE_ENV_MARKERS)
    }
    result.update(
        {
            "CLAUDE_CODE_DISABLE_AGENT_VIEW": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
            "DISABLE_AUTOUPDATER": "1",
            "PATH": _TRUSTED_CHILD_PATH,
        }
    )
    return result


def _private_write(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def _load_cli_envelope(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_JSON, "Claude CLI result is not UTF-8 JSON"
        ) from exc
    if type(value) is not dict:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_JSON, "Claude CLI result must be an object"
        )
    if set(value) != _ENVELOPE_FIELDS:
        raise AIReviewValidationError(
            AIReviewErrorCode.UNKNOWN_FIELD,
            "Claude CLI result fields are not exact",
        )
    usage = value["usage"]
    model_usage = value["modelUsage"]
    model_receipt = (
        model_usage.get("claude-sonnet-5") if type(model_usage) is dict else None
    )
    server_tool_use = usage.get("server_tool_use") if type(usage) is dict else None
    cache_creation = usage.get("cache_creation") if type(usage) is dict else None
    if (
        value["type"] != "result"
        or value["subtype"] != "success"
        or value["is_error"] is not False
        or value["api_error_status"] is not None
        or type(value["result"]) is not str
        or type(value["session_id"]) is not str
        or not value["session_id"]
        or type(value["uuid"]) is not str
        or not value["uuid"]
        or type(value["permission_denials"]) is not list
        or value["permission_denials"]
        or type(model_usage) is not dict
        or set(model_usage) != {"claude-sonnet-5"}
        or type(model_receipt) is not dict
        or set(model_receipt) != _MODEL_USAGE_FIELDS
        or type(model_receipt["webSearchRequests"]) is not int
        or model_receipt["webSearchRequests"] != 0
        or type(usage) is not dict
        or set(usage) != _USAGE_FIELDS
        or type(server_tool_use) is not dict
        or set(server_tool_use) != {"web_fetch_requests", "web_search_requests"}
        or type(server_tool_use["web_search_requests"]) is not int
        or server_tool_use["web_search_requests"] != 0
        or type(server_tool_use["web_fetch_requests"]) is not int
        or server_tool_use["web_fetch_requests"] != 0
        or type(cache_creation) is not dict
        or set(cache_creation)
        != {"ephemeral_1h_input_tokens", "ephemeral_5m_input_tokens"}
        or type(value["num_turns"]) is not int
        or not 1 <= value["num_turns"] <= 20
        or value["stop_reason"] != "end_turn"
        or value["terminal_reason"] != "completed"
        or value["fast_mode_state"] != "off"
        or type(usage["iterations"]) is not list
        or usage["iterations"]
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude CLI transport, model usage or permission receipt is invalid",
        )
    for field in (
        "duration_api_ms",
        "duration_ms",
        "time_to_request_ms",
        "ttft_ms",
        "ttft_stream_ms",
    ):
        if type(value[field]) is not int or value[field] < 0:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "Claude CLI duration receipt is invalid",
            )
    for field in (
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "input_tokens",
        "output_tokens",
    ):
        if type(usage[field]) is not int or usage[field] < 0:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "Claude CLI usage receipt is invalid",
            )
    if (
        type(value["total_cost_usd"]) not in {int, float}
        or value["total_cost_usd"] < 0
        or any(
            type(usage[field]) is not str or not usage[field]
            for field in (
                "inference_geo",
                "service_tier",
                "speed",
            )
        )
        or any(
            type(cache_creation[field]) is not int or cache_creation[field] < 0
            for field in cache_creation
        )
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude CLI service or cache receipt is invalid",
        )
    usage = model_receipt
    if (
        type(usage.get("inputTokens")) is not int
        or usage["inputTokens"] <= 0
        or type(usage.get("outputTokens")) is not int
        or usage["outputTokens"] <= 0
        or any(
            type(usage[field]) is not int or usage[field] < 0
            for field in (
                "cacheCreationInputTokens",
                "cacheReadInputTokens",
                "contextWindow",
                "maxOutputTokens",
            )
        )
        or type(usage["costUSD"]) not in {int, float}
        or usage["costUSD"] < 0
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude Sonnet 5 content usage receipt is invalid",
        )
    return value


def _invoke_trusted_claude(
    *,
    trusted: _TrustedClaudeExecutableV1,
    output: Path,
    empty_mcp: Path,
    audit_input: bytes,
    max_turns: int,
    max_budget_usd: str,
) -> tuple[str, subprocess.CompletedProcess[bytes]]:
    with _private_staged_executable(trusted, output) as (
        executable,
        stage_identity,
    ):
        _verify_private_stage(
            executable,
            expected_sha256=trusted.executable_sha256,
            expected_identity=stage_identity,
        )
        version_process = subprocess.run(
            [str(executable), "--version"],
            cwd=output,
            env=_safe_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        if version_process.returncode != 0:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "Claude CLI version could not be established",
            )
        _verify_private_stage(
            executable,
            expected_sha256=trusted.executable_sha256,
            expected_identity=stage_identity,
        )
        try:
            agent_version = version_process.stdout.decode(
                "utf-8", errors="strict"
            ).strip()
        except UnicodeDecodeError as exc:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "Claude CLI version is not UTF-8",
            ) from exc
        if not agent_version or "\n" in agent_version or len(agent_version) > 128:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "Claude CLI version receipt is invalid",
            )
        if agent_version != trusted.version:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "Claude CLI version differs from the owner-reviewed attestation",
            )
        command = [
            str(executable),
            "-p",
            "--model",
            "claude-sonnet-5",
            "--output-format",
            "json",
            "--allowedTools",
            "",
            "--permission-mode",
            "plan",
            "--strict-mcp-config",
            "--mcp-config",
            str(empty_mcp),
            "--settings",
            json.dumps(_SETTINGS, separators=(",", ":"), sort_keys=True),
            "--no-session-persistence",
            "--no-chrome",
            "--max-turns",
            str(max_turns),
            "--max-budget-usd",
            max_budget_usd,
        ]
        completed = subprocess.run(
            command,
            cwd=output,
            env=_safe_environment(),
            input=audit_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=1800,
        )
        if completed.returncode != 0:
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                f"Claude transport failed with exit {completed.returncode}",
            )
        _verify_private_stage(
            executable,
            expected_sha256=trusted.executable_sha256,
            expected_identity=stage_identity,
        )
        return agent_version, completed


def run_claude_challenge(
    snapshot: AIReviewSnapshotV1,
    *,
    ruleset: MaterialRulesetSnapshotV1,
    evidence: EvidenceManifestSnapshotV2,
    media_identity_evidence: tuple[EvidenceManifestSnapshotV2, ...],
    output_directory: str | Path,
    max_turns: int = 20,
    max_budget_usd: str = "5.00",
) -> ClaudeChallengeRunReceiptV1:
    """Execute exactly one challenge without retry or repository writes."""

    if type(snapshot) is not AIReviewSnapshotV1:
        raise TypeError("snapshot must be AIReviewSnapshotV1")
    snapshot.payload.validate_against(ruleset, evidence, media_identity_evidence)
    failures = snapshot.payload.eligibility_failures()
    if failures:
        raise AIReviewValidationError(
            AIReviewErrorCode.SOURCE_BLOCKED,
            f"challenge preflight blocked: {failures}",
        )
    if type(max_turns) is not int or not 1 <= max_turns <= 20:
        raise ValueError("max_turns must be between 1 and 20")
    if max_budget_usd not in {"5.00", "10.00"}:
        raise ValueError("max_budget_usd must use an owner-bounded value")
    trusted_executable = _trusted_claude_executable()
    claude_executable_sha256 = trusted_executable.executable_sha256
    output = Path(output_directory).expanduser().resolve()
    repository = Path(__file__).resolve().parents[4]
    if output == repository or repository in output.parents:
        raise ValueError("Claude audit output must be outside the repository")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    empty_mcp = output / "empty-mcp.json"
    audit_input_path = output / "audit-input.json"
    cli_result_path = output / "claude-result.json"
    _private_write(empty_mcp, b'{"mcpServers":{}}\n')
    audit_input = build_claude_audit_input(snapshot)
    _private_write(audit_input_path, audit_input.canonical_bytes)
    agent_version, completed = _invoke_trusted_claude(
        trusted=trusted_executable,
        output=output,
        empty_mcp=empty_mcp,
        audit_input=audit_input.canonical_bytes,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
    )
    envelope = _load_cli_envelope(completed.stdout)
    redacted_envelope = {
        **envelope,
        "session_id": "<redacted>",
        "uuid": "<redacted>",
    }
    _private_write(
        cli_result_path,
        json.dumps(
            redacted_envelope,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    report = parse_claude_audit_report(envelope["result"], snapshot)
    canonical_report = json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    report_sha256 = hashlib.sha256(AUDIT_OUTPUT_DOMAIN + canonical_report).hexdigest()
    run_id = (
        "claude-run-sha256:"
        + hashlib.sha256(envelope["session_id"].encode("utf-8")).hexdigest()
    )
    challenger = ChallengerAgentRunV1(
        agent_version=agent_version,
        prompt_version=_PROMPT_VERSION,
        prompt_sha256=hashlib.sha256(_PROMPT_BYTES).hexdigest(),
        run_id=run_id,
        audit_input_sha256=audit_input.audit_input_sha256,
        audit_output_sha256=report_sha256,
        isolation=AgentExecutionIsolationV1(
            tools_enabled=False,
            mcp_enabled=False,
            hooks_enabled=False,
            web_search_requests=0,
            web_fetch_requests=0,
            session_persistence_enabled=False,
        ),
    )
    challenge = ClaudeChallengeV1.create(snapshot, challenger, report)
    session_id_sha256 = hashlib.sha256(
        envelope["session_id"].encode("utf-8")
    ).hexdigest()
    audit_input_file_sha256 = hashlib.sha256(audit_input_path.read_bytes()).hexdigest()
    cli_result_file_sha256 = hashlib.sha256(cli_result_path.read_bytes()).hexdigest()
    runner_receipt_sha256 = compute_claude_run_receipt_sha256(
        challenge=challenge,
        audit_input_file_sha256=audit_input_file_sha256,
        cli_result_file_sha256=cli_result_file_sha256,
        claude_executable_sha256=claude_executable_sha256,
        claude_executable_attestation_sha256=(trusted_executable.attestation_sha256),
        process_returncode=completed.returncode,
        session_id_sha256=session_id_sha256,
    )
    receipt = ClaudeChallengeRunReceiptV1(
        challenge=challenge,
        audit_input_path=str(audit_input_path),
        audit_input_file_sha256=audit_input_file_sha256,
        cli_result_path=str(cli_result_path),
        cli_result_file_sha256=cli_result_file_sha256,
        claude_executable_sha256=claude_executable_sha256,
        claude_executable_attestation_bytes=(
            trusted_executable.canonical_attestation_bytes
        ),
        claude_executable_attestation_sha256=(trusted_executable.attestation_sha256),
        process_returncode=completed.returncode,
        session_id_sha256=session_id_sha256,
        runner_receipt_sha256=runner_receipt_sha256,
        _token=_RUN_RECEIPT_TOKEN,
    )
    _PENDING_RUN_RECEIPTS[runner_receipt_sha256] = id(receipt)
    return receipt


__all__ = [
    "ClaudeChallengeRunReceiptV1",
    "compute_claude_run_receipt_sha256",
    "run_claude_challenge",
    "validate_persisted_claude_run_artifacts",
]
