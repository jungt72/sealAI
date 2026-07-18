"""One-shot Claude Sonnet 5 safe-mode runner for frozen audit corpora."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
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
_RUN_RECEIPT_TOKEN = object()
_PENDING_RUN_RECEIPTS: dict[str, int] = {}
_SHA256_HEX = frozenset("0123456789abcdef")
_ENVELOPE_FIELDS = frozenset(
    {
        "is_error",
        "modelUsage",
        "permission_denials",
        "result",
        "session_id",
        "type",
        "web_fetch_requests",
        "web_search_requests",
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


@dataclass(frozen=True, slots=True, init=False)
class ClaudeChallengeRunReceiptV1:
    challenge: ClaudeChallengeV1
    audit_input_path: str
    audit_input_file_sha256: str
    cli_result_path: str
    cli_result_file_sha256: str
    claude_executable_sha256: str
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
        for name, value in (
            ("audit_input_file_sha256", self.audit_input_file_sha256),
            ("cli_result_file_sha256", self.cli_result_file_sha256),
            ("claude_executable_sha256", self.claude_executable_sha256),
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
            audit_input_file_sha256=self.audit_input_file_sha256,
            cli_result_file_sha256=self.cli_result_file_sha256,
            claude_executable_sha256=self.claude_executable_sha256,
            process_returncode=self.process_returncode,
            session_id_sha256=self.session_id_sha256,
            runner_receipt_sha256=self.runner_receipt_sha256,
        )
        return audit_value, envelope

    def consume_for_persistence(
        self, snapshot: AIReviewSnapshotV1
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Consume exactly one receipt issued by this process after a CLI run."""

        if _PENDING_RUN_RECEIPTS.pop(self.runner_receipt_sha256, None) != id(self):
            raise AIReviewValidationError(
                AIReviewErrorCode.INVALID_AGENT,
                "runner receipt was not issued by this process or was already consumed",
            )
        return self._validated_artifacts(snapshot)


def compute_claude_run_receipt_sha256(
    *,
    challenge: ClaudeChallengeV1,
    audit_input_file_sha256: str,
    cli_result_file_sha256: str,
    claude_executable_sha256: str,
    process_returncode: int,
    session_id_sha256: str,
) -> str:
    value = {
        "audit_input_file_sha256": audit_input_file_sha256,
        "challenge_id": challenge.challenge_id,
        "cli_result_file_sha256": cli_result_file_sha256,
        "claude_executable_sha256": claude_executable_sha256,
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
    audit_input_file_sha256: str,
    cli_result_file_sha256: str,
    claude_executable_sha256: str,
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
    if set(envelope) != _ENVELOPE_FIELDS or envelope["session_id"] != "<redacted>":
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
        "PATH",
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
    required = _ENVELOPE_FIELDS
    if not required <= set(value):
        raise AIReviewValidationError(
            AIReviewErrorCode.UNKNOWN_FIELD,
            f"Claude CLI result missing {sorted(required - set(value))}",
        )
    if (
        value["type"] != "result"
        or value["is_error"] is not False
        or type(value["result"]) is not str
        or type(value["session_id"]) is not str
        or type(value["permission_denials"]) is not list
        or value["permission_denials"]
        or type(value["modelUsage"]) is not dict
        or set(value["modelUsage"]) != {"claude-sonnet-5"}
        or type(value["web_search_requests"]) is not int
        or value["web_search_requests"] != 0
        or type(value["web_fetch_requests"]) is not int
        or value["web_fetch_requests"] != 0
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude CLI transport, model usage or permission receipt is invalid",
        )
    usage = value["modelUsage"]["claude-sonnet-5"]
    if (
        type(usage) is not dict
        or type(usage.get("inputTokens")) is not int
        or usage["inputTokens"] <= 0
        or type(usage.get("outputTokens")) is not int
        or usage["outputTokens"] <= 0
    ):
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude Sonnet 5 content usage receipt is invalid",
        )
    return value


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
    executable = Path(shutil.which("claude") or "missing-claude").resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise FileNotFoundError("authenticated Claude CLI executable is unavailable")
    claude_executable_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
    output = Path(output_directory).expanduser().resolve()
    repository = Path(__file__).resolve().parents[4]
    if output == repository or repository in output.parents:
        raise ValueError("Claude audit output must be outside the repository")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    empty_mcp = output / "empty-mcp.json"
    audit_input_path = output / "audit-input.json"
    cli_result_path = output / "claude-result.json"
    _private_write(empty_mcp, b"{}\n")
    audit_input = build_claude_audit_input(snapshot)
    _private_write(audit_input_path, audit_input.canonical_bytes)
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
    if hashlib.sha256(executable.read_bytes()).hexdigest() != claude_executable_sha256:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude CLI executable changed during version verification",
        )
    try:
        agent_version = version_process.stdout.decode("utf-8", errors="strict").strip()
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
        input=audit_input.canonical_bytes,
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
    if hashlib.sha256(executable.read_bytes()).hexdigest() != claude_executable_sha256:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_AGENT,
            "Claude CLI executable changed during the one-shot run",
        )
    envelope = _load_cli_envelope(completed.stdout)
    redacted_envelope = {
        "is_error": False,
        "modelUsage": envelope["modelUsage"],
        "permission_denials": [],
        "result": envelope["result"],
        "session_id": "<redacted>",
        "type": "result",
        "web_fetch_requests": 0,
        "web_search_requests": 0,
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
