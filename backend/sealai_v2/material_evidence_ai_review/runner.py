"""One-shot Claude Sonnet 5 safe-mode runner for frozen audit corpora."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
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


@dataclass(frozen=True, slots=True)
class ClaudeChallengeRunReceiptV1:
    challenge: ClaudeChallengeV1
    audit_input_path: str
    audit_input_file_sha256: str
    cli_result_path: str
    cli_result_file_sha256: str
    process_returncode: int

    def __post_init__(self) -> None:
        if type(self.challenge) is not ClaudeChallengeV1:
            raise TypeError("challenge must be ClaudeChallengeV1")
        if self.process_returncode != 0:
            raise ValueError("successful receipt requires zero process return code")


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
    required = {
        "is_error",
        "modelUsage",
        "permission_denials",
        "result",
        "session_id",
        "type",
    }
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
    claude_executable: str | Path | None = None,
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
    executable = Path(
        claude_executable or shutil.which("claude") or "missing-claude"
    ).resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise FileNotFoundError("authenticated Claude CLI executable is unavailable")
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
    envelope = _load_cli_envelope(completed.stdout)
    redacted_envelope = {
        "is_error": False,
        "modelUsage": envelope["modelUsage"],
        "permission_denials": [],
        "result": envelope["result"],
        "session_id": "<redacted>",
        "type": "result",
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
    return ClaudeChallengeRunReceiptV1(
        challenge=challenge,
        audit_input_path=str(audit_input_path),
        audit_input_file_sha256=hashlib.sha256(
            audit_input_path.read_bytes()
        ).hexdigest(),
        cli_result_path=str(cli_result_path),
        cli_result_file_sha256=hashlib.sha256(cli_result_path.read_bytes()).hexdigest(),
        process_returncode=completed.returncode,
    )


__all__ = ["ClaudeChallengeRunReceiptV1", "run_claude_challenge"]
