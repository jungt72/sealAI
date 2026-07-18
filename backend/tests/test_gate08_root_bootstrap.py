"""The GATE-08 trust transition must never sudo candidate checkout code."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
BOOTSTRAP = OPS / "bootstrap_gate08_remediation_control.py"
INSTALLER = OPS / "install-disk-guard.sh"
RUNBOOK = REPO / "docs" / "ops" / "production-release-freeze.md"
sys.path.insert(0, str(OPS))

import production_release_gate as gate  # noqa: E402
import bootstrap_gate08_remediation_control as root_bootstrap  # noqa: E402


def _bash_array(script: str, name: str) -> set[str]:
    match = re.search(
        rf"readonly -a {re.escape(name)}=\(\n(?P<body>.*?)\n\)",
        script,
        flags=re.DOTALL,
    )
    assert match is not None
    return {
        line.strip()
        for line in match.group("body").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_gate_bootstrap_and_installer_share_the_exact_artifact_set():
    installer = INSTALLER.read_text(encoding="utf-8")
    expected = set(gate.REMEDIATION_CONTROL_ARTIFACTS)

    assert _bash_array(installer, "ARTIFACTS") == expected
    assert "ops/bootstrap_gate08_remediation_control.py" in expected
    assert "ops/hash_verified_python_loader.py" in expected
    assert "ops/production-release-state.json" in expected
    assert root_bootstrap.SELF_ARTIFACT in expected
    assert root_bootstrap.GATE_ARTIFACT in expected
    assert root_bootstrap.STATE_ARTIFACT in expected


def test_bootstrap_clones_with_fixed_tools_and_no_candidate_execution_first():
    script = BOOTSTRAP.read_text(encoding="utf-8")
    main = script.index("def main(")
    clone = script.index("_prepare_checkout(source", main)
    trusted_verifier = script.index("for trusted in", clone)
    checked_out_execution = script.index("_run_gate(checkout", trusted_verifier)
    installer_execution = script.index('str(checkout / "ops/install-disk-guard.sh")')

    assert clone < trusted_verifier < checked_out_execution < installer_execution
    assert "/usr/bin/git" in script
    assert '"GIT_CONFIG_NOSYSTEM": "1"' in script
    assert '"GIT_CONFIG_GLOBAL": "/dev/null"' in script
    assert '"GIT_NO_LAZY_FETCH": "1"' in script
    assert "core.hooksPath={hooks}" in script
    assert "core.alternateRefsCommand=/bin/false" in script
    assert '"GIT_ALLOW_PROTOCOL": "file"' in script
    assert all(flag in script for flag in ("--depth=1", "--single-branch", "--no-tags"))
    assert "candidate HEAD does not match receipt" in script
    assert '(checkout / ".git/objects/info/alternates").lstat()' in script
    assert "/usr/bin/sudo" not in script


def test_bootstrap_verifier_checks_git_tree_artifacts_and_ownership():
    script = BOOTSTRAP.read_text(encoding="utf-8")

    for contract in (
        "metadata.st_uid != 0",
        "stat.S_IMODE(metadata.st_mode) & 0o022",
        "stat.S_ISLNK(metadata.st_mode)",
        "followlinks=False",
        "_safe_digest(checkout / trusted) != receipt_hashes[trusted]",
        'decision.get("artifact_sha256") != receipt_hashes',
        '"status", "--porcelain=v1", "--untracked-files=all"',
        'line.startswith("160000 ")',
    ):
        assert contract in script


def test_isolated_git_clone_flags_do_not_run_candidate_checkout_hook(tmp_path: Path):
    source = tmp_path / "user writable source"
    source.mkdir()
    subprocess.run(
        ["/usr/bin/git", "init", "-b", "main", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["/usr/bin/git", "-C", str(source), "config", "user.name", "Gate Test"],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(source),
            "config",
            "user.email",
            "gate@example.invalid",
        ],
        check=True,
    )
    (source / "approved.txt").write_text("approved\n", encoding="utf-8")
    subprocess.run(
        ["/usr/bin/git", "-C", str(source), "add", "approved.txt"], check=True
    )
    subprocess.run(
        ["/usr/bin/git", "-C", str(source), "commit", "-m", "approved"],
        check=True,
        capture_output=True,
        text=True,
    )
    approved_sha = subprocess.run(
        ["/usr/bin/git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    hook_marker = tmp_path / "candidate-hook-ran"
    candidate_hook = source / ".git" / "hooks" / "post-checkout"
    candidate_hook.write_text(
        f"#!/bin/sh\n/usr/bin/touch {hook_marker}\n", encoding="utf-8"
    )
    candidate_hook.chmod(0o755)

    root_stage = tmp_path / "root stage"
    empty_hooks = root_stage / "empty-hooks"
    checkout = root_stage / "checkout"
    empty_hooks.mkdir(parents=True, mode=0o700)
    git_environment = {
        "HOME": "/root",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_PROTOCOL_FROM_USER": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    git_prefix = [
        "/usr/bin/git",
        "-c",
        f"core.hooksPath={empty_hooks}",
        "-c",
        "core.alternateRefsCommand=/bin/false",
        "-c",
        "protocol.file.allow=always",
    ]
    subprocess.run(
        [
            *git_prefix,
            "clone",
            "--no-local",
            "--no-checkout",
            "--no-recurse-submodules",
            "--depth=1",
            "--single-branch",
            "--no-tags",
            "--",
            str(source),
            str(checkout),
        ],
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            *git_prefix,
            "-C",
            str(checkout),
            "checkout",
            "--detach",
            "--force",
            approved_sha,
            "--",
        ],
        env=git_environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert not hook_marker.exists()
    assert not (checkout / ".git" / "objects" / "info" / "alternates").exists()
    assert (
        subprocess.run(
            [*git_prefix, "-C", str(checkout), "rev-parse", "HEAD"],
            env=git_environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == approved_sha
    )


def test_documented_loader_copies_as_data_then_hashes_before_execution():
    runbook = RUNBOOK.read_text(encoding="utf-8")
    start = runbook.index(
        "```bash\nCANDIDATE_REPOSITORY='/absolute/local/path/to/candidate-repository'"
    )
    end = runbook.index("\n```", start)
    loader = runbook[start + len("```bash\n") : end]

    copied_data = loader.index(
        'readonly STAGED_BOOTSTRAP="${LOADER_STAGE}/bootstrap.data"'
    )
    copied_mode = loader.index("0o600", copied_data)
    hash_match = loader.index("hmac.compare_digest", copied_mode)
    executable_mode = loader.index(
        '/usr/bin/chmod 0700 "${STAGED_BOOTSTRAP}"', hash_match
    )
    execution = loader.index('"${STAGED_BOOTSTRAP}" \\', executable_mode)

    assert copied_data < copied_mode < hash_match < executable_mode < execution
    assert 'getattr(os, "O_NOFOLLOW", 0)' in loader
    assert "receipt_stat.st_uid != 0" in loader
    assert "stat.S_IMODE(receipt_stat.st_mode) != 0o600" in loader
    assert "approval is expired or over-broad" in loader
    assert "Never run `sudo` on the bootstrap" in runbook
    syntax = subprocess.run(
        ["/bin/bash", "-n"], input=loader, text=True, capture_output=True
    )
    assert syntax.returncode == 0, syntax.stderr


def test_all_trusted_inline_python_blocks_compile():
    blocks: list[tuple[Path, str]] = []
    for path in (INSTALLER, RUNBOOK):
        text = path.read_text(encoding="utf-8")
        blocks.extend(
            (path, body)
            for body in re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", text, re.DOTALL)
        )

    assert len(blocks) == 4
    for index, (path, body) in enumerate(blocks, start=1):
        compile(body, f"{path}:inline-python-{index}", "exec")


def test_gate_rejects_symlink_and_writable_checkout_components(tmp_path: Path):
    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    artifact = safe / "artifact"
    artifact.write_text("safe\n", encoding="utf-8")
    artifact.chmod(0o600)
    symlink = safe / "link"
    symlink.symlink_to(artifact)

    with pytest.raises(gate.GateConfigurationError, match="unsafe"):
        gate._assert_trusted_path(symlink, leaf_directory=False)

    unsafe = safe / "writable"
    unsafe.mkdir(mode=0o770)
    unsafe.chmod(0o770)
    nested = unsafe / "artifact"
    nested.write_text("unsafe\n", encoding="utf-8")
    nested.chmod(0o600)
    try:
        with pytest.raises(gate.GateConfigurationError, match="unsafe"):
            gate._assert_trusted_path(nested, leaf_directory=False)
    finally:
        unsafe.chmod(0o700)


def test_installer_rejects_unsafe_source_before_executing_the_gate():
    installer = INSTALLER.read_text(encoding="utf-8")

    topology_check = installer.index("source checkout topology is unsafe")
    gate_execution = installer.index("production_release_gate_check")
    assert topology_check < gate_execution
    assert 'verify(repo / ".git", leaf_directory=True)' in installer
    assert "for relative in artifacts:" in installer
    helper = (OPS / "production-release-gate-check.sh").read_text(encoding="utf-8")
    assert "/usr/bin/env -i" in helper
    assert '/usr/bin/python3 -I "${gate_path}"' in helper
    assert 'value.get("allowed") is not True' in helper


def test_bootstrap_help_and_python_syntax_are_safe_without_root(tmp_path: Path):
    compile(BOOTSTRAP.read_text(encoding="utf-8"), str(BOOTSTRAP), "exec")
    staged = tmp_path / "bootstrap.data"
    shutil.copyfile(BOOTSTRAP, staged)
    staged.chmod(0o700)
    help_result = subprocess.run(
        [str(staged), "--help"],
        env={
            "HOME": "/root",
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
        },
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--source-repository ABSOLUTE_LOCAL_PATH --apply" in help_result.stdout
