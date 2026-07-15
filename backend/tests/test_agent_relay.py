"""Adversarial tests for the fail-closed local agent relay."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest
import yaml


REPO = Path(__file__).resolve().parents[2]


def _module():
    name = "agent_relay_test"
    spec = importlib.util.spec_from_file_location(name, REPO / "ops" / "agent_relay.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "relay-tests@example.invalid")
    _git(repo, "config", "user.name", "Relay Tests")
    schema_dir = repo / ".ai-remediation" / "schemas"
    schema_dir.mkdir(parents=True)
    for name in (
        "agent-relay-build-contract.schema.json",
        "agent-relay-audit-response.schema.json",
        "agent-relay-state.schema.json",
    ):
        shutil.copyfile(REPO / ".ai-remediation" / "schemas" / name, schema_dir / name)
    run_dir = repo / ".ai-remediation" / "runs" / "TEST"
    run_dir.mkdir(parents=True)
    (run_dir / "production-fingerprint.json").write_text(
        json.dumps({"schema_version": 1, "contains_secret_values": False}),
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(
        ".ai-remediation/relay-runs/\n.ai-remediation/local-contracts/\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "baseline")
    return repo


def _contract(baseline: str, contract_id: str = "test-contract") -> dict:
    plan = {"status": "NOT_APPLICABLE", "items": ["No migration is required."]}
    return {
        "schema_version": 1,
        "contract_id": contract_id,
        "run_id": "TEST-RUN",
        "objective": "Exercise the bounded local relay contract without remote mutations.",
        "repository": {
            "expected_base_commit": baseline,
            "base_branch": "main",
            "allowed_paths": ["README.md"],
        },
        "prerequisites": {
            "release_freeze_respected": True,
            "production_mutation_authorized": False,
            "required_local_packages": [],
        },
        "claude_audits": {
            "model": "claude-sonnet-4-5-20250929",
            "allowed_tools": [],
            "disallowed_tools": [
                "*",
                "Write",
                "Edit",
                "Bash",
                "NotebookEdit",
                "WebFetch",
                "WebSearch",
            ],
            "max_turns": 6,
            "max_budget_usd": 0.5,
            "max_review_loops": 2,
            "api_fallback_allowed": False,
        },
        "limits": {
            "max_changed_files": 4,
            "max_diff_bytes": 65536,
            "max_input_bytes": 65536,
            "max_test_seconds": 30,
            "max_process_output_bytes": 65536,
        },
        "deterministic_tests": [
            {
                "name": "local-pytest",
                "argv": ["python3", "-m", "pytest", "-q", "tests/test_smoke.py"],
            }
        ],
        "migration_plan": copy.deepcopy(plan),
        "security_impact": copy.deepcopy(plan),
        "rollback_plan": copy.deepcopy(plan),
        "known_risks": copy.deepcopy(plan),
        "draft_pr": {
            "title": "test: local relay contract",
            "body_file": f".ai-remediation/relay-runs/{contract_id}/draft-pr.md",
            "auto_merge": False,
            "auto_deploy": False,
        },
    }


def _audit_response(**overrides) -> dict:
    value = {
        "schema_version": 1,
        "phase": "CONTRACT_AUDIT",
        "verdict": "PASS",
        "summary": "The synthetic contract is bounded.",
        "findings": [],
        "resolved_finding_ids": [],
        "tools_used": [],
        "network_tools_used": False,
        "writes_performed": False,
        "scope_frozen": True,
    }
    value.update(overrides)
    return value


def _fake_claude(
    tmp_path: Path,
    stdout: str,
    *,
    reject_api_key: bool = False,
    assert_policy: bool = False,
) -> Path:
    path = tmp_path / "claude"
    script = [
        "#!/usr/bin/env python3",
        "import os",
        "import sys",
        "payload = sys.stdin.buffer.read()",
        "sys.exit(90) if not payload else None",
    ]
    if reject_api_key:
        script.append("sys.exit(91) if os.environ.get('ANTHROPIC_API_KEY') else None")
    if assert_policy:
        script.extend(
            [
                "allowed = sys.argv[sys.argv.index('--allowedTools') + 1]",
                "tools = sys.argv[sys.argv.index('--tools') + 1]",
                "settings = __import__('json').loads(sys.argv[sys.argv.index('--settings') + 1])",
                "denied = sys.argv[sys.argv.index('--disallowedTools') + 1].split(',')",
                "model = sys.argv[sys.argv.index('--model') + 1]",
                "sys.exit(92) if allowed != '' else None",
                "sys.exit(95) if tools != '' else None",
                "sys.exit(93) if not {'*','Write','Edit','Bash','WebFetch','WebSearch'}.issubset(set(denied)) else None",
                "sys.exit(94) if 'opus' in model.lower() else None",
                "required_flags = {'--safe-mode','--strict-mcp-config','--disable-slash-commands','--no-chrome','--no-session-persistence'}",
                "sys.exit(96) if not required_flags.issubset(set(sys.argv)) else None",
                "sys.exit(97) if not all(settings.get(key) is expected for key, expected in {'autoMemoryEnabled':False,'disableAllHooks':True,'disableArtifact':True,'disableClaudeAiConnectors':True,'disableRemoteControl':True,'disableWorkflows':True}.items()) else None",
            ]
        )
    script.append(f"sys.stdout.write({stdout!r})")
    path.write_text("\n".join(script) + "\n", encoding="utf-8")
    path.chmod(0o700)
    return path


def test_prepare_creates_every_required_file_from_a_clean_baseline(tmp_path):
    module = _module()
    repo = _init_repo(tmp_path)
    baseline = _git(repo, "rev-parse", "HEAD")
    contract = _contract(baseline)
    contract_dir = repo / ".ai-remediation" / "local-contracts"
    contract_dir.mkdir()
    contract_path = contract_dir / "test-contract.yaml"
    contract_path.write_text(yaml.safe_dump(contract, sort_keys=True), encoding="utf-8")

    state = module.prepare(
        repo,
        str(contract_path.relative_to(repo)),
        None,
        ".ai-remediation/runs/TEST/production-fingerprint.json",
    )

    bundle = repo / ".ai-remediation" / "relay-runs" / "test-contract"
    assert set(module.REQUIRED_BUNDLE_FILES).issubset(
        {path.name for path in bundle.iterdir()}
    )
    assert state["production_query_performed"] is False
    assert state["api_fallback_used"] is False
    assert _git(repo, "status", "--porcelain") == ""


def test_prepare_rejects_an_unexpected_dirty_baseline(tmp_path):
    module = _module()
    repo = _init_repo(tmp_path)
    baseline = _git(repo, "rev-parse", "HEAD")
    contract_dir = repo / ".ai-remediation" / "local-contracts"
    contract_dir.mkdir()
    path = contract_dir / "test-contract.yaml"
    path.write_text(yaml.safe_dump(_contract(baseline)), encoding="utf-8")
    (repo / "unexpected.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(module.RelayError, match="clean Git worktree"):
        module.prepare(
            repo,
            str(path.relative_to(repo)),
            None,
            ".ai-remediation/runs/TEST/production-fingerprint.json",
        )


def test_fake_claude_gets_read_only_policy_and_no_api_key_fallback(
    tmp_path, monkeypatch
):
    module = _module()
    repo = _init_repo(tmp_path)
    response = json.dumps({"result": json.dumps(_audit_response())})
    fake = _fake_claude(tmp_path, response, reject_api_key=True, assert_policy=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-forwarded-to-claude")

    parsed, process = module._invoke_claude(
        repo,
        _contract(_git(repo, "rev-parse", "HEAD")),
        str(fake),
        b'{"synthetic":"read-only contract audit"}\n',
        expected_phase="CONTRACT_AUDIT",
    )

    assert parsed["verdict"] == "PASS"
    assert process.returncode == 0
    assert module._claude_environment().get("ANTHROPIC_API_KEY") is None
    assert module._claude_environment()["CLAUDE_CODE_SKIP_PROMPT_HISTORY"] == "1"
    assert module._claude_environment()["DISABLE_AUTOUPDATER"] == "1"


@pytest.mark.parametrize(
    ("stdout", "message"),
    [
        ("not-json", "JSON"),
        (
            json.dumps(
                {"result": json.dumps(_audit_response(tools_used=["Read", "Bash"]))}
            ),
            "tool policy",
        ),
    ],
)
def test_fake_claude_invalid_json_and_tool_violation_fail_closed(
    tmp_path, stdout, message
):
    module = _module()
    repo = _init_repo(tmp_path)
    fake = _fake_claude(tmp_path, stdout)
    with pytest.raises(module.RelayError, match=message):
        module._invoke_claude(
            repo,
            _contract(_git(repo, "rev-parse", "HEAD")),
            str(fake),
            b'{"synthetic":"audit"}\n',
            expected_phase="CONTRACT_AUDIT",
        )


def test_secret_canary_in_claude_output_is_rejected_without_persisting(tmp_path):
    module = _module()
    repo = _init_repo(tmp_path)
    canary = "sk-" + "ant-" + "api03-" + "A" * 24
    response = _audit_response(summary=f"unsafe {canary}")
    fake = _fake_claude(tmp_path, json.dumps({"result": json.dumps(response)}))

    with pytest.raises(module.RelayError, match="secret canary"):
        module._invoke_claude(
            repo,
            _contract(_git(repo, "rev-parse", "HEAD")),
            str(fake),
            b'{"synthetic":"audit"}\n',
            expected_phase="CONTRACT_AUDIT",
        )


def test_output_limit_pauses_without_retry_or_model_escalation(tmp_path):
    module = _module()
    repo = _init_repo(tmp_path)
    contract = _contract(_git(repo, "rev-parse", "HEAD"))
    contract["limits"]["max_process_output_bytes"] = 1024
    fake = _fake_claude(tmp_path, "x" * 4096)

    with pytest.raises(module.ExternalBlocker, match="limit"):
        module._invoke_claude(
            repo,
            contract,
            str(fake),
            b'{"synthetic":"audit"}\n',
            expected_phase="CONTRACT_AUDIT",
        )


def test_diff_audit_enforces_two_loop_cap(tmp_path, monkeypatch):
    module = _module()
    repo = tmp_path / "repo"
    bundle = repo / ".ai-remediation" / "relay-runs" / "test-contract"
    bundle.mkdir(parents=True)
    baseline = "a" * 40
    contract_raw = b"contract"
    contract = _contract(baseline)
    diff = b"diff"
    state = {
        "schema_version": 1,
        "contract_id": "test-contract",
        "baseline_commit": baseline,
        "build_contract_sha256": hashlib.sha256(contract_raw).hexdigest(),
        "contract_audit": {"status": "APPROVED"},
        "implementation": {
            "status": "CAPTURED",
            "changed_files": ["README.md"],
            "diff_sha256": hashlib.sha256(diff).hexdigest(),
        },
        "tests": {"status": "PASS"},
        "diff_audits": [],
        "remediation_captures": [],
        "claude_invocations": 0,
        "ready_for_draft_pr": False,
    }
    process = module.ProcessResult(0, False, False, b"", b"", "0" * 64, "1" * 64, 0, 0)
    block = _audit_response(
        phase="DIFF_AUDIT",
        verdict="BLOCK",
        findings=[
            {
                "id": "F1",
                "severity": "MEDIUM",
                "path": "README.md",
                "description": "Synthetic bounded finding.",
                "required_action": "Fix only README.md.",
            }
        ],
    )
    invocations = []
    monkeypatch.setattr(
        module, "_load_contract", lambda *_: (contract, contract_raw, repo / "contract")
    )
    monkeypatch.setattr(module, "_load_state", lambda *_: state)
    monkeypatch.setattr(module, "_verify_state_contract", lambda *_: None)
    monkeypatch.setattr(module, "_head", lambda *_: baseline)
    monkeypatch.setattr(
        module, "_collect_implementation", lambda *_: (["README.md"], diff)
    )
    monkeypatch.setattr(module, "_bundle_audit_input", lambda *_args, **_kwargs: b"{}")
    monkeypatch.setattr(module, "_write_json", lambda *_: None)
    monkeypatch.setattr(module, "_persist_state", lambda *_: None)
    monkeypatch.setattr(
        module,
        "_validated_audit_file",
        lambda *_args, **_kwargs: (
            copy.deepcopy(block),
            module._canonical_json_bytes(block),
        ),
    )

    def invoke(*_args, **_kwargs):
        invocations.append(1)
        return copy.deepcopy(block), process

    monkeypatch.setattr(module, "_invoke_claude", invoke)

    with pytest.raises(module.RelayError, match="one bounded remediation"):
        module.diff_audit(repo, "contract", None, "claude-fake", 1)
    with pytest.raises(module.RelayError, match="captured remediation"):
        module.diff_audit(repo, "contract", None, "claude-fake", 2)
    state["remediation_captures"].append(
        {
            "replaced_at": "2026-07-15T00:00:00Z",
            "after_diff_audit_iteration": 1,
            "diff_sha256": "f" * 64,
            "test_status": "PASS",
        }
    )
    with pytest.raises(module.IterationLimit, match="two diff-audit loops"):
        module.diff_audit(repo, "contract", None, "claude-fake", 2)
    with pytest.raises(module.RelayError, match="exceeds two"):
        module.diff_audit(repo, "contract", None, "claude-fake", 3)
    assert len(invocations) == 2


def test_shell_payload_and_symlink_path_are_rejected(tmp_path):
    module = _module()
    with pytest.raises(module.RelayError, match="require python"):
        module._validate_test_argv(["python3", "-c", "__import__('os').remove('x')"])

    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("outside", encoding="utf-8")
    (repo / "linked").symlink_to(outside)
    with pytest.raises(module.RelayError, match="symlink"):
        module._safe_repo_path(repo, "linked", label="test path")

    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "value.txt").write_text("outside", encoding="utf-8")
    (repo / "linked-dir").symlink_to(outside_dir, target_is_directory=True)
    with pytest.raises(module.RelayError, match="symlink|unavailable"):
        module._read_regular(
            repo / "linked-dir" / "value.txt", limit=1024, label="parent swap probe"
        )
    with pytest.raises(module.RelayError, match="symlink|unavailable"):
        module._atomic_write(repo / "linked-dir" / "new.txt", b"blocked")
    assert not (outside_dir / "new.txt").exists()

    remediation_dir = repo / ".ai-remediation"
    remediation_dir.mkdir()
    relay_outside = tmp_path / "relay-outside"
    relay_outside.mkdir()
    (remediation_dir / "relay-runs").symlink_to(relay_outside, target_is_directory=True)
    with pytest.raises(module.RelayError, match="symlink|non-directory"):
        module._mkdir_under_repo(repo, remediation_dir / "relay-runs" / "test-contract")
    assert not (relay_outside / "test-contract").exists()


def test_test_argv_and_environment_are_repo_bound_and_scrubbed(tmp_path, monkeypatch):
    module = _module()
    repo = _init_repo(tmp_path)
    safe = ["python3", "-m", "pytest", "-q", "tests/test_smoke.py"]
    module._validate_test_argv(safe, repo=repo)
    hardened = module._hardened_test_argv(repo, safe)
    assert Path(hardened[0]).resolve() == Path(sys.executable).resolve()
    assert hardened[1:4] == ("-I", "-m", "pytest")
    assert ("-p", "no:cacheprovider") == hardened[6:8]
    assert "--confcutdir" in hardened

    with pytest.raises(module.RelayError, match="unsafe option"):
        module._validate_test_argv(
            ["python3", "-m", "pytest", "-p", "untrusted_plugin"], repo=repo
        )
    with pytest.raises(module.RelayError, match="repository-local"):
        module._validate_test_argv(
            ["python3", "-m", "pytest", "-q", "/tmp/untrusted_test.py"],
            repo=repo,
        )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-pass")
    monkeypatch.setenv("PYTHONPATH", "/tmp/untrusted")
    env = module._test_environment()
    assert "ANTHROPIC_API_KEY" not in env
    assert "PYTHONPATH" not in env
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["PYTHONNOUSERSITE"] == "1"


def test_process_drain_has_a_hard_deadline_without_spawning_a_child(
    tmp_path, monkeypatch
):
    module = _module()
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()

    class CompletedProcessWithOpenPipes:
        pid = 999_999
        stdin = None

        def __init__(self):
            self.stdout = os.fdopen(stdout_read, "rb", buffering=0)
            self.stderr = os.fdopen(stderr_read, "rb", buffering=0)

        @staticmethod
        def poll():
            return 0

        @staticmethod
        def wait(*, timeout):
            assert timeout > 0
            return 0

        @staticmethod
        def kill():
            raise AssertionError("a completed process must not be killed")

    fake = CompletedProcessWithOpenPipes()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(module, "PROCESS_DRAIN_GRACE_SECONDS", 0.05)
    started = time.monotonic()
    try:
        result = module._run_bounded(
            ("synthetic-completed-process",),
            cwd=tmp_path,
            timeout=1,
            output_limit=1024,
        )
    finally:
        os.close(stdout_write)
        os.close(stderr_write)
    assert time.monotonic() - started < 0.5
    assert result.returncode == 0
    assert result.stdout_bytes == 0
    assert result.stderr_bytes == 0


def test_state_and_bundle_tampering_fail_closed(tmp_path):
    module = _module()
    repo = _init_repo(tmp_path)
    baseline = _git(repo, "rev-parse", "HEAD")
    contract_dir = repo / ".ai-remediation" / "local-contracts"
    contract_dir.mkdir()
    contract_path = contract_dir / "test-contract.yaml"
    contract_path.write_text(
        yaml.safe_dump(_contract(baseline), sort_keys=True), encoding="utf-8"
    )
    state = module.prepare(
        repo,
        str(contract_path.relative_to(repo)),
        None,
        ".ai-remediation/runs/TEST/production-fingerprint.json",
    )
    bundle = repo / ".ai-remediation" / "relay-runs" / "test-contract"
    contract, contract_raw, _ = module._load_contract(
        repo, str(contract_path.relative_to(repo))
    )

    forged = copy.deepcopy(state)
    forged["ready_for_draft_pr"] = True
    with pytest.raises(module.RelayError, match="readiness"):
        module._validate_state(repo, forged)

    fingerprint = bundle / "repository-fingerprint.json"
    fingerprint.write_text('{"tampered":true}\n', encoding="utf-8")
    loaded = module._load_state(repo, bundle)
    with pytest.raises(module.RelayError, match="bundle changed"):
        module._verify_state_contract(repo, bundle, loaded, contract, contract_raw)


def test_second_audit_payload_contains_prior_block_and_resolution_contract(tmp_path):
    module = _module()
    repo = _init_repo(tmp_path)
    baseline = _git(repo, "rev-parse", "HEAD")
    contract = _contract(baseline)
    contract_dir = repo / ".ai-remediation" / "local-contracts"
    contract_dir.mkdir()
    contract_path = contract_dir / "test-contract.yaml"
    contract_path.write_text(yaml.safe_dump(contract, sort_keys=True), encoding="utf-8")
    module.prepare(
        repo,
        str(contract_path.relative_to(repo)),
        None,
        ".ai-remediation/runs/TEST/production-fingerprint.json",
    )
    bundle = repo / ".ai-remediation" / "relay-runs" / "test-contract"
    block = _audit_response(
        phase="DIFF_AUDIT",
        verdict="BLOCK",
        findings=[
            {
                "id": "F1",
                "severity": "MEDIUM",
                "path": "README.md",
                "description": "Synthetic finding.",
                "required_action": "Resolve F1.",
            }
        ],
    )
    raw = module._bundle_audit_input(
        repo,
        bundle,
        instruction="Synthetic iteration two.",
        max_input_bytes=contract["limits"]["max_input_bytes"],
        previous_block_audit=block,
    )
    payload = module._parse_json(raw, label="synthetic audit input")
    assert payload["previous_block_audit"] == block
    assert "resolved_finding_ids" in payload["response_schema"]["schema"]["required"]
    assert payload["security_boundary"]["local_tools_exposed"] == []

    resolved = _audit_response(
        phase="DIFF_AUDIT",
        resolved_finding_ids=["F1"],
    )
    parsed = module._parse_claude_response(
        module._canonical_json_bytes(resolved),
        repo=repo,
        expected_phase="DIFF_AUDIT",
        expected_resolved_finding_ids=frozenset({"F1"}),
    )
    assert parsed["verdict"] == "PASS"
    with pytest.raises(module.RelayError, match="resolve the expected findings"):
        module._parse_claude_response(
            module._canonical_json_bytes(resolved),
            repo=repo,
            expected_phase="DIFF_AUDIT",
            expected_resolved_finding_ids=frozenset({"F2"}),
        )


def test_untracked_implementation_diff_has_safe_applyable_paths(tmp_path):
    module = _module()
    repo = _init_repo(tmp_path)
    source = repo / "ops" / "new_tool.py"
    source.parent.mkdir()
    source.write_text("value = 1\n", encoding="utf-8")

    diff = module._implementation_diff(
        repo, _git(repo, "rev-parse", "HEAD"), ["ops/new_tool.py"]
    )
    assert b"a/./" not in diff
    assert b"b/./" not in diff
    patch = repo / ".ai-remediation" / "relay-runs" / "probe.diff"
    patch.parent.mkdir(parents=True)
    patch.write_bytes(diff)
    subprocess.run(
        ["git", "apply", "--check", "--reverse", str(patch)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    baseline = _git(repo, "rev-parse", "HEAD")
    _git(repo, "add", "ops/new_tool.py")
    _git(repo, "commit", "-qm", "add reviewed tool")
    paths, committed = module._committed_implementation(
        repo, baseline, _git(repo, "rev-parse", "HEAD")
    )
    assert paths == ["ops/new_tool.py"]
    assert committed == diff


def test_missing_claude_is_a_manual_external_blocker_without_install(monkeypatch):
    module = _module()
    with pytest.raises(module.RelayError, match="not allowlisted"):
        module._resolve_claude("claude-fake")
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    with pytest.raises(module.ExternalBlocker, match="manual"):
        module._resolve_claude("claude")


def test_wrapper_rejects_a_relative_python_override():
    env = os.environ.copy()
    env["SEALAI_RELAY_PYTHON"] = "python3"
    completed = subprocess.run(
        [str(REPO / "ops" / "relay.sh"), "--help"],
        cwd=REPO,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 3
    assert "must be an absolute path" in completed.stderr


def test_wrapper_runs_with_the_explicit_isolated_test_environment():
    env = os.environ.copy()
    env["SEALAI_RELAY_PYTHON"] = sys.executable
    completed = subprocess.run(
        [str(REPO / "ops" / "relay.sh"), "--help"],
        cwd=REPO,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout
