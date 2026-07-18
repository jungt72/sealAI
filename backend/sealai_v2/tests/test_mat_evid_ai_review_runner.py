from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from sealai_v2.core.material_evidence_ai_review import (
    AIReviewErrorCode,
    AIReviewSnapshotV1,
    AIReviewValidationError,
)
from sealai_v2.material_evidence_ai_review.runner import (
    ClaudeChallengeRunReceiptV1,
    run_claude_challenge,
)
from sealai_v2.material_evidence_ai_review.audit import CLAUDE_TASK_V1
from sealai_v2.tests.test_mat_evid_ai_review_domain import (
    BATCH_ID,
    _identity_evidence,
    _payload,
)


def _fake_claude(
    path: Path,
    *,
    invalid_transport: bool = False,
    wrong_model: bool = False,
    web_search_requests: int = 0,
    web_fetch_requests: int = 0,
    report_override: str | None = None,
) -> Path:
    script = path / "fake-claude"
    body = """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

if '--version' in sys.argv:
    print('fake-claude-cli 1.0.0')
    raise SystemExit(0)

audit = json.loads(sys.stdin.read())
pathlib.Path('args.json').write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
sensitive = [key for key in os.environ if any(marker in key.upper() for marker in ('API_KEY','TOKEN','SECRET','PASSWORD','CREDENTIAL','COOKIE'))]
claim_results = []
for claim in audit['claims']:
    claim_results.append({
        'claim_ref': claim['claim_ref'],
        'contradiction_assessment': 'No supplied contradiction.',
        'findings': [],
        'material_granularity_assessment': 'Exact supplied scope.',
        'missing_conditions_assessment': 'No missing condition found.',
        'positive_statement_assessment': 'No positive statement.',
        'scope_assessment': 'Scope matches frozen corpus.',
        'severity': 'NONE',
        'source_coverage': 'Exact supplied source and locator.',
        'source_independence_assessment': 'single_source',
        'source_overreach_assessment': 'No overreach found.',
        'verdict': 'PASS',
    })
report = {
    'audit_contract_version': 'MAT-EVID-AI-CHALLENGE.v1',
    'audit_schema_version': 1,
    'claim_results': claim_results,
    'overall_verdict': 'PASS',
    'review_content_sha256': audit['review_content_sha256'],
    'review_snapshot_id': audit['review_snapshot_id'],
    'transport_complete': True,
}
report_override = __REPORT_OVERRIDE__
if report_override is not None:
    report = json.loads(report_override)
envelope = {
    'type': 'result',
    'is_error': bool(sensitive),
    'result': json.dumps(report, separators=(',', ':'), sort_keys=True),
    'session_id': 'sensitive-session-id-never-persist-raw',
    'modelUsage': {'claude-sonnet-5': {'inputTokens': 10, 'outputTokens': 10}},
    'permission_denials': [],
    'web_search_requests': 0,
    'web_fetch_requests': 0,
}
print(json.dumps(envelope))
"""
    body = body.replace("__REPORT_OVERRIDE__", repr(report_override))
    body = body.replace(
        "'web_search_requests': 0", f"'web_search_requests': {web_search_requests}"
    )
    body = body.replace(
        "'web_fetch_requests': 0", f"'web_fetch_requests': {web_fetch_requests}"
    )
    if invalid_transport:
        body = body.replace(
            "'permission_denials': [],", "'permission_denials': ['unexpected'],"
        )
    if wrong_model:
        body = body.replace("'claude-sonnet-5':", "'claude-other-model':")
    script.write_text(body, encoding="utf-8")
    script.chmod(0o700)
    return script


def test_runner_uses_one_shot_safe_mode_and_hashes_sensitive_run_id(tmp_path) -> None:
    payload, ruleset, evidence = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    executable = _fake_claude(tmp_path)
    output = tmp_path / "audit-output"
    os.environ["SYNTHETIC_API_KEY"] = "must-not-reach-child"
    try:
        receipt = run_claude_challenge(
            snapshot,
            ruleset=ruleset,
            evidence=evidence,
            media_identity_evidence=(_identity_evidence(),),
            output_directory=output,
            claude_executable=executable,
        )
    finally:
        os.environ.pop("SYNTHETIC_API_KEY", None)
    assert receipt.process_returncode == 0
    assert receipt.challenge.challenger.agent_model == "claude-sonnet-5"
    assert receipt.challenge.challenger.agent_version == "fake-claude-cli 1.0.0"
    assert (
        receipt.challenge.challenger.prompt_sha256
        == hashlib.sha256(CLAUDE_TASK_V1.encode("utf-8")).hexdigest()
    )
    assert receipt.challenge.challenger.run_id.startswith("claude-run-sha256:")
    assert "sensitive-session-id" not in receipt.challenge.challenger.run_id
    assert Path(receipt.audit_input_path).stat().st_mode & 0o777 == 0o600
    assert Path(receipt.cli_result_path).stat().st_mode & 0o777 == 0o600
    stored_result = Path(receipt.cli_result_path).read_text(encoding="utf-8")
    assert "sensitive-session-id-never-persist-raw" not in stored_result
    assert json.loads(stored_result)["session_id"] == "<redacted>"
    args = json.loads((output / "args.json").read_text(encoding="utf-8"))
    for value in (
        "--allowedTools",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--no-chrome",
        "claude-sonnet-5",
    ):
        assert value in args
    assert args[args.index("--allowedTools") + 1] == ""

    with pytest.raises(TypeError, match="one-shot runner"):
        ClaudeChallengeRunReceiptV1(
            challenge=receipt.challenge,
            audit_input_path=receipt.audit_input_path,
            audit_input_file_sha256=receipt.audit_input_file_sha256,
            cli_result_path=receipt.cli_result_path,
            cli_result_file_sha256=receipt.cli_result_file_sha256,
            process_returncode=0,
            session_id_sha256=receipt.session_id_sha256,
            runner_receipt_sha256=receipt.runner_receipt_sha256,
            _token=object(),
        )


def test_runner_receipt_revalidation_rejects_artifact_drift(tmp_path) -> None:
    payload, ruleset, evidence = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    receipt = run_claude_challenge(
        snapshot,
        ruleset=ruleset,
        evidence=evidence,
        media_identity_evidence=(_identity_evidence(),),
        output_directory=tmp_path / "artifact-drift-output",
        claude_executable=_fake_claude(tmp_path),
    )
    Path(receipt.cli_result_path).write_text("{}", encoding="utf-8")
    with pytest.raises(AIReviewValidationError) as exc:
        receipt.validate_against(snapshot)
    assert exc.value.code is AIReviewErrorCode.HASH_MISMATCH


def test_runner_rejects_permission_denial_as_transport_failure(tmp_path) -> None:
    payload, ruleset, evidence = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    with pytest.raises(AIReviewValidationError) as exc:
        run_claude_challenge(
            snapshot,
            ruleset=ruleset,
            evidence=evidence,
            media_identity_evidence=(_identity_evidence(),),
            output_directory=tmp_path / "invalid-output",
            claude_executable=_fake_claude(tmp_path, invalid_transport=True),
        )
    assert exc.value.code is AIReviewErrorCode.INVALID_AGENT


def test_runner_rejects_output_directory_inside_repository(tmp_path) -> None:
    payload, ruleset, evidence = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    repository_output = Path(__file__).resolve().parents[3] / ".forbidden-ai-output"
    with pytest.raises(ValueError, match="outside the repository"):
        run_claude_challenge(
            snapshot,
            ruleset=ruleset,
            evidence=evidence,
            media_identity_evidence=(_identity_evidence(),),
            output_directory=repository_output,
            claude_executable=_fake_claude(tmp_path),
        )
    assert not repository_output.exists()


def test_runner_rejects_non_exact_model_usage(tmp_path) -> None:
    payload, ruleset, evidence = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    with pytest.raises(AIReviewValidationError) as exc:
        run_claude_challenge(
            snapshot,
            ruleset=ruleset,
            evidence=evidence,
            media_identity_evidence=(_identity_evidence(),),
            output_directory=tmp_path / "wrong-model-output",
            claude_executable=_fake_claude(tmp_path, wrong_model=True),
        )
    assert exc.value.code is AIReviewErrorCode.INVALID_AGENT


@pytest.mark.parametrize(
    "web_search_requests,web_fetch_requests",
    ((1, 0), (0, 1)),
)
def test_runner_rejects_nonzero_web_transport_receipt(
    tmp_path, web_search_requests: int, web_fetch_requests: int
) -> None:
    payload, ruleset, evidence = _payload()
    snapshot = AIReviewSnapshotV1.create(BATCH_ID, payload)
    with pytest.raises(AIReviewValidationError) as exc:
        run_claude_challenge(
            snapshot,
            ruleset=ruleset,
            evidence=evidence,
            media_identity_evidence=(_identity_evidence(),),
            output_directory=tmp_path / "web-enabled-output",
            claude_executable=_fake_claude(
                tmp_path,
                web_search_requests=web_search_requests,
                web_fetch_requests=web_fetch_requests,
            ),
        )
    assert exc.value.code is AIReviewErrorCode.INVALID_AGENT
