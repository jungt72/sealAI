import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
HELPER = OPS / "production-release-gate-check.sh"
REMOTE = OPS / "production-deploy-remote-entrypoint.sh"
SOURCE_SHA = "a" * 40
GATED_ENTRYPOINTS = (
    "install_sealai_stack_service.sh",
    "keycloak_upgrade_preflight.sh",
    "promote-local-backend-image.sh",
    "release-backend-v2.sh",
    "release-backend.sh",
    "release-frontend.sh",
    "up-prod.sh",
    "upgrade_infra.sh",
    "v2-flip.sh",
)
PRIVILEGED_CHILD_SCRIPTS = (
    "check-env-drift.sh",
    "guard-nginx-reload.sh",
    "smoke-live-pilot-readiness.sh",
    "smoke-v2.sh",
    "stack_smoke.sh",
    "tree-hash.sh",
    "verify-image-attestations.sh",
)
PRIVILEGED_PRODUCTION_MUTATORS = (
    "backup_postgres.sh",
    "backup_qdrant.sh",
    "backup_run.sh",
    "backup_v2_database.sh",
    "docker_firewall_fix.sh",
    "docker-disk-guard.sh",
    "disk_safeguard.sh",
    "install-disk-guard.sh",
    "install_docker_firewall.sh",
    "issue-sealingai-cert.sh",
    "keycloak_ensure_roles.sh",
    "keycloak_recover_admin.sh",
    "production-deploy-remote-entrypoint.sh",
)


def _write_fake_gate(
    path: Path,
    marker: Path,
    *,
    decision: dict[str, object] | None = None,
    raw_output: str | None = None,
    status: int = 0,
    expected_operation: str = "deploy",
) -> None:
    rendered = raw_output if raw_output is not None else json.dumps(decision)
    path.write_text(
        "import json, os, pathlib, sys\n"
        f"pathlib.Path({str(marker)!r}).write_text("
        "json.dumps(dict(os.environ), sort_keys=True), encoding='utf-8')\n"
        f"assert sys.argv[1:] == ['check', {expected_operation!r}]\n"
        f"print({rendered!r})\n"
        f"raise SystemExit({status})\n",
        encoding="utf-8",
    )


def _run_helper(
    gate: Path, expected_source: str = SOURCE_SHA
) -> subprocess.CompletedProcess[str]:
    command = (
        'set -euo pipefail; source "$1"; '
        'production_release_gate_check "$2" deploy "$3"; '
        'printf "%s" "$PRODUCTION_RELEASE_APPROVED_SOURCE_SHA"'
    )
    poisoned = gate.parent / "poisoned-bin"
    poisoned.mkdir(exist_ok=True)
    return subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            command,
            "gate-test",
            str(HELPER),
            str(gate),
            expected_source,
        ],
        env={
            **os.environ,
            "HOME": str(gate.parent / "attacker-home"),
            "PATH": str(poisoned),
            "PYTHONPATH": str(gate.parent / "poisoned-python"),
            "PYTHONINSPECT": "1",
            "PYTHONWARNINGS": "error",
        },
        text=True,
        capture_output=True,
        check=False,
    )


def _allowed_decision(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "allowed": True,
        "operation": "deploy",
        "reason": "gate10_approved_manifest_bound",
        "state_id": "freeze-test",
        "required_gate": "GATE-10",
        "source_git_sha": SOURCE_SHA,
    }
    value.update(overrides)
    return value


def test_gate_invocation_uses_isolated_system_python_and_exact_success_json(
    tmp_path: Path,
) -> None:
    gate = tmp_path / "fake_gate.py"
    marker = tmp_path / "gate-environment.json"
    poison_dir = tmp_path / "poisoned-python"
    poison_dir.mkdir()
    poison_marker = tmp_path / "sitecustomize-ran"
    (poison_dir / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(poison_marker)!r}).touch()\n",
        encoding="utf-8",
    )
    _write_fake_gate(gate, marker, decision=_allowed_decision())

    result = _run_helper(gate)

    assert result.returncode == 0, result.stderr
    assert result.stdout == SOURCE_SHA
    environment = json.loads(marker.read_text(encoding="utf-8"))
    assert environment["HOME"] == "/nonexistent"
    assert environment["PATH"] == "/usr/sbin:/usr/bin:/sbin:/bin"
    assert "PYTHONPATH" not in environment
    assert "PYTHONINSPECT" not in environment
    assert "PYTHONWARNINGS" not in environment
    assert not poison_marker.exists()


@pytest.mark.parametrize(
    "decision,expected_source",
    [
        (_allowed_decision(allowed=False), SOURCE_SHA),
        (_allowed_decision(operation="pull"), SOURCE_SHA),
        (_allowed_decision(reason="some_other_success"), SOURCE_SHA),
        (_allowed_decision(extra="unexpected"), SOURCE_SHA),
        (_allowed_decision(source_git_sha="b" * 40), SOURCE_SHA),
    ],
)
def test_gate_invocation_rejects_zero_exit_with_non_exact_decision(
    tmp_path: Path,
    decision: dict[str, object],
    expected_source: str,
) -> None:
    gate = tmp_path / "fake_gate.py"
    marker = tmp_path / "gate-environment.json"
    _write_fake_gate(gate, marker, decision=decision)

    result = _run_helper(gate, expected_source)

    assert result.returncode == 78
    assert "invalid_success_decision" in result.stderr


def test_gate_invocation_rejects_malformed_json_and_propagates_gate_denial(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "malformed_gate.py"
    malformed_marker = tmp_path / "malformed-called"
    _write_fake_gate(malformed, malformed_marker, raw_output="not-json")
    malformed_result = _run_helper(malformed)
    assert malformed_result.returncode == 78
    assert "invalid_success_decision" in malformed_result.stderr

    denied = tmp_path / "denied_gate.py"
    denied_marker = tmp_path / "denied-called"
    _write_fake_gate(
        denied,
        denied_marker,
        decision=_allowed_decision(allowed=False),
        status=20,
    )
    denied_result = _run_helper(denied)
    assert denied_result.returncode == 20
    assert denied_marker.is_file()


def test_gate_invocation_rejects_oversized_success_output(tmp_path: Path) -> None:
    gate = tmp_path / "oversized_gate.py"
    marker = tmp_path / "oversized-called"
    _write_fake_gate(gate, marker, raw_output="x" * 65537)

    result = _run_helper(gate)

    assert result.returncode == 78
    assert "oversized_success_decision" in result.stderr


def test_gate_invocation_rejects_argument_injection_before_gate_execution(
    tmp_path: Path,
) -> None:
    gate = tmp_path / "fake_gate.py"
    marker = tmp_path / "gate-called"
    _write_fake_gate(gate, marker, decision=_allowed_decision())
    command = (
        'set -euo pipefail; source "$1"; '
        'production_release_gate_check "$2" "deploy --help"'
    )

    result = subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            command,
            "gate-test",
            str(HELPER),
            str(gate),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 64
    assert not marker.exists()


def test_production_entrypoint_privileged_shell_ignores_bash_env(
    tmp_path: Path,
) -> None:
    ops = tmp_path / "ops"
    ops.mkdir()
    entrypoint = ops / "up-prod.sh"
    entrypoint.write_bytes((OPS / "up-prod.sh").read_bytes())
    entrypoint.chmod(0o755)
    (ops / "production-release-gate-check.sh").write_bytes(HELPER.read_bytes())
    gate_marker = tmp_path / "gate-called"
    gate = ops / "production_release_gate.py"
    _write_fake_gate(
        gate,
        gate_marker,
        decision=_allowed_decision(allowed=False),
        status=20,
        expected_operation="recovery-start-existing",
    )
    bash_env_marker = tmp_path / "bash-env-ran"
    bash_env = tmp_path / "attacker-bash-env"
    bash_env.write_text(
        f"/usr/bin/touch {str(bash_env_marker)!r}\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [str(entrypoint)],
        env={
            **os.environ,
            "BASH_ENV": str(bash_env),
            "PATH": str(tmp_path / "attacker-path"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 20
    assert gate_marker.is_file()
    assert not bash_env_marker.exists()


def test_all_gated_shell_entrypoints_use_fixed_privileged_bash() -> None:
    for relative in GATED_ENTRYPOINTS:
        script = (OPS / relative).read_text(encoding="utf-8")
        assert script.startswith("#!/bin/bash -p\n"), relative
    staging = (OPS / "staging" / "up-staging-v2.sh").read_text(encoding="utf-8")
    assert staging.startswith("#!/bin/bash -p\n")

    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )
    privileged_runner = "shell: /bin/bash --noprofile --norc -p -e -o pipefail {0}"
    assert workflow.count(privileged_runner) == 3
    assert "shell: bash" not in workflow


def _exported_function_parent_command(child_command: str) -> str:
    return f"""
set -euo pipefail
poison_marker() {{ /usr/bin/printf '%s\\n' "$1" >> "$POISON_MARKER"; }}
source() {{ poison_marker source; return 0; }}
production_release_gate_check() {{ poison_marker gate; return 0; }}
acquire_production_storage_lease() {{ poison_marker lease; return 0; }}
docker() {{ poison_marker docker; return 0; }}
git() {{ poison_marker git; return 1; }}
mkdir() {{ poison_marker mkdir; return 1; }}
export -f poison_marker source production_release_gate_check
export -f acquire_production_storage_lease docker git mkdir
{child_command}
"""


def test_real_entrypoint_ignores_exported_gate_lease_and_command_functions(
    tmp_path: Path,
) -> None:
    ops = tmp_path / "ops"
    ops.mkdir()
    entrypoint = ops / "release-backend.sh"
    entrypoint.write_bytes((OPS / "release-backend.sh").read_bytes())
    entrypoint.chmod(0o755)
    (ops / "production-release-gate-check.sh").write_bytes(HELPER.read_bytes())
    gate_marker = tmp_path / "gate-called"
    gate = ops / "production_release_gate.py"
    _write_fake_gate(
        gate,
        gate_marker,
        decision=_allowed_decision(allowed=False),
        status=20,
    )
    poison_marker = tmp_path / "poison-called"

    result = subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            _exported_function_parent_command('exec "$1"'),
            "function-parent",
            str(entrypoint),
        ],
        env={**os.environ, "POISON_MARKER": str(poison_marker)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 20
    assert gate_marker.is_file()
    assert not poison_marker.exists()


def test_privileged_child_imports_none_of_the_exported_attack_functions(
    tmp_path: Path,
) -> None:
    poison_marker = tmp_path / "poison-called"
    check = (
        "for fn in source production_release_gate_check "
        "acquire_production_storage_lease docker git mkdir; do "
        'if declare -F "$fn" >/dev/null; then exit 23; fi; done'
    )
    result = subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            _exported_function_parent_command(f"/bin/bash -p -c {check!r}"),
        ],
        env={**os.environ, "POISON_MARKER": str(poison_marker)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not poison_marker.exists()


def test_privileged_parent_and_real_child_do_not_reimport_exported_git_function(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "child-repo"
    (repo / "ops").mkdir(parents=True)
    (repo / "backend" / "sealai_v2").mkdir(parents=True)
    shutil.copy2(OPS / "tree-hash.sh", repo / "ops" / "tree-hash.sh")
    for relative in (
        "backend/requirements-v2.txt",
        "backend/.dockerignore",
        "backend/Dockerfile.v2",
        "backend/docker-entrypoint-v2.sh",
    ):
        target = repo / relative
        target.write_text(f"fixture for {relative}\n", encoding="utf-8")
    (repo / "backend" / "sealai_v2" / "app.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    subprocess.run(
        ["/usr/bin/git", "init", "-q", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    poison_marker = tmp_path / "child-poison-called"

    result = subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            _exported_function_parent_command(
                '/bin/bash -p -c \'/bin/bash -p "$1"\' privileged-parent "$1"'
            ),
            "function-parent",
            str(repo / "ops" / "tree-hash.sh"),
        ],
        cwd=repo,
        env={**os.environ, "POISON_MARKER": str(poison_marker)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) == 40
    assert not poison_marker.exists()


def test_release_child_chain_uses_privileged_bash_at_every_boundary() -> None:
    for relative in PRIVILEGED_CHILD_SCRIPTS:
        script = (OPS / relative).read_text(encoding="utf-8")
        assert script.startswith("#!/bin/bash -p\n"), relative

    v2_release = (OPS / "release-backend-v2.sh").read_text(encoding="utf-8")
    assert "/bin/bash -p ops/tree-hash.sh" in v2_release
    assert "/bin/bash -p ops/verify-image-attestations.sh" in v2_release
    assert "/bin/bash -p ops/backup_v2_database.sh" in v2_release
    assert "$(bash " not in v2_release
    assert "\n  bash ops/" not in v2_release

    for relative in PRIVILEGED_PRODUCTION_MUTATORS:
        script = (OPS / relative).read_text(encoding="utf-8")
        assert script.startswith("#!/bin/bash -p\n"), relative
    disk_guard_installer = (OPS / "install-disk-guard.sh").read_text(encoding="utf-8")
    assert "sudo -u thorsten /bin/bash -p -c" in disk_guard_installer
    assert "sudo -u thorsten /bin/bash -c" not in disk_guard_installer
    staging_generator = (OPS / "staging" / "gen-staging-conf.sh").read_text(
        encoding="utf-8"
    )
    assert staging_generator.startswith("#!/bin/bash -p\n")


def test_release_evidence_and_root_service_shell_boundaries_are_privileged() -> None:
    for relative in ("gate.sh", "run_eval.sh", "run_targeted_remediation_eval.sh"):
        script = (OPS / relative).read_text(encoding="utf-8")
        assert script.startswith("#!/bin/bash -p\n"), relative
        assert "/bin/bash -p ops/tree-hash.sh" in script, relative

    targeted = (OPS / "run_targeted_remediation_eval.sh").read_text(encoding="utf-8")
    assert "exec /bin/bash -p ops/run_eval.sh" in targeted
    lease = (OPS / "production-storage-lease.sh").read_text(encoding="utf-8")
    assert lease.startswith("#!/bin/bash -p\n")

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "\t/bin/bash -p ops/tree-hash.sh" in makefile
    build_workflow = (ROOT / ".github" / "workflows" / "build-and-push.yml").read_text(
        encoding="utf-8"
    )
    privileged_runner = "shell: /bin/bash --noprofile --norc -p -e -o pipefail {0}"
    assert build_workflow.count(privileged_runner) == 4
    assert "shell: bash" not in build_workflow
    assert 'tree_hash="$(/bin/bash -p ops/tree-hash.sh)"' in build_workflow
    build_freeze = build_workflow.index("production_release_gate_check")
    assert build_freeze < build_workflow.index("docker/login-action")
    assert build_freeze < build_workflow.index("docker/build-push-action")

    keycloak_workflow = (ROOT / ".github" / "workflows" / "keycloak.yml").read_text(
        encoding="utf-8"
    )
    assert keycloak_workflow.count(privileged_runner) == 4
    assert "shell: bash" not in keycloak_workflow
    keycloak_freeze = keycloak_workflow.index(
        "production_release_gate_check", keycloak_workflow.index("publish:")
    )
    assert keycloak_freeze < keycloak_workflow.index(
        "docker/login-action", keycloak_workflow.index("publish:")
    )
    assert keycloak_freeze < keycloak_workflow.index(
        "docker/build-push-action", keycloak_workflow.index("publish:")
    )
    eval_entrypoint = (
        ROOT / "backend" / "sealai_v2" / "eval" / "__main__.py"
    ).read_text(encoding="utf-8")
    assert '["/bin/bash", "-p", str(repo / "ops" / "tree-hash.sh")]' in eval_entrypoint

    firewall_service = (
        OPS / "abuse_10D287D_2C" / "firewall" / "docker-egress-harden.service"
    ).read_text(encoding="utf-8")
    assert firewall_service.count("ExecStart=/bin/bash -p ") == 2
    assert "ExecStart=/bin/bash /root/" not in firewall_service
    for relative in (
        Path("abuse_10D287D_2C/firewall/README.md"),
        Path("abuse_10D287D_2C/REMEDIATION.md"),
    ):
        guidance = (OPS / relative).read_text(encoding="utf-8")
        assert "sudo /bin/bash -p " in guidance
        assert "sudo bash " not in guidance


def test_sanctioned_release_guidance_and_claude_hooks_preserve_privileged_bash() -> (
    None
):
    settings_path = ROOT / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    ask = settings["permissions"]["ask"]
    assert not any(value.startswith("Bash(bash ops/release-") for value in ask)
    for relative in (
        "release-backend.sh",
        "release-backend-v2.sh",
        "release-frontend.sh",
    ):
        assert f"Bash(./ops/{relative}:*)" in ask
        assert not any(
            value.startswith(f"Bash(/bin/bash -p ops/{relative}") for value in ask
        )

    hook_commands = [
        hook["command"]
        for matcher in settings["hooks"]["PreToolUse"]
        for hook in matcher["hooks"]
    ]
    assert hook_commands
    assert all(
        command.startswith('/bin/bash -p "$CLAUDE_PROJECT_DIR/')
        for command in hook_commands
    )

    for relative in (
        Path(".claude/skills/backend-v2-deploy/SKILL.md"),
        Path(".claude/skills/frontend-marketing/SKILL.md"),
    ):
        guidance = (ROOT / relative).read_text(encoding="utf-8")
        assert "bash ops/release-" not in guidance
        assert "./ops/release-" in guidance

    for relative in (
        "deploy-gate.sh",
        "doctrine-gate.sh",
        "relay-deny.sh",
        "v2-deploy-deny.sh",
    ):
        script = (OPS / "hooks" / relative).read_text(encoding="utf-8")
        assert script.startswith("#!/bin/bash -p\n"), relative


@pytest.mark.parametrize(
    "command",
    (
        "./ops/release-backend.sh",
        "bash ops/release-backend.sh",
        "/bin/bash -p ops/release-backend.sh",
    ),
)
def test_legacy_deploy_sentinel_denies_every_supported_invocation_spelling(
    tmp_path: Path, command: str
) -> None:
    payload = json.dumps({"tool_input": {"command": command}})
    result = subprocess.run(
        ["/bin/bash", "-p", str(OPS / "hooks" / "deploy-gate.sh")],
        input=payload,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "missing sentinel" in result.stderr


def test_installed_remote_boundary_holds_lease_and_stays_hard_denied() -> None:
    script = REMOTE.read_text(encoding="utf-8")

    lease = script.index("acquire_production_storage_lease")
    hard_denial = script.index("p1_exact_artifact_promotion_not_implemented")
    assert lease < hard_denial
    assert "/usr/local/libexec/sealai/production-storage-lease.sh" in script
    assert "/usr/local/libexec/sealai/production-release-gate-check.sh" in script
    assert "git fetch" not in script
    assert "git checkout" not in script
    assert "/usr/bin/git" not in script
    assert "production_release_gate.py" not in script
    assert "release-backend-v2.sh" not in script
    assert "docker " not in script
