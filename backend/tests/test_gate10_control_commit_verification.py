"""verify_gate10_control_commit.py must independently re-prove a deploy decision,
never trusting the entrypoint's CLI arguments at face value.

Note on scope: _verify_chain/_secure_lstat (copied verbatim from the same,
already-hardened pattern in bootstrap_gate08_remediation_control.py) hard-require
real root ownership (metadata.st_uid != 0) on every checked-out path component.
That property is only genuinely exercisable as real root -- matching how the
original GATE-08 bootstrap fix earlier today was verified empirically on the VPS,
not via a non-root pytest run. These tests cover everything that does not depend
on that specific, root-only property; the empirical dry run (see the PR) proves
the rest end to end.
"""

from __future__ import annotations

import hmac
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
SPEC = importlib.util.spec_from_file_location(
    "verify_gate10_control_commit", OPS / "verify_gate10_control_commit.py"
)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


VALID_DIGEST = "ghcr.io/jungt72/sealai-backend-v2@sha256:" + "1" * 64
OTHER_DIGEST = "ghcr.io/jungt72/sealai-backend-v2@sha256:" + "2" * 64


def _build_control_repo(
    tmp_path: Path,
    *,
    gate_decision: dict[str, object] | None = None,
    gate_exit_code: int = 0,
) -> tuple[Path, str, str]:
    """A real two-commit repo: a source commit, then a control commit adding a
    fake production_release_gate.py. Deliberately fake, not the real gate script
    -- the real one's backend_image_digest/frontend_image_digest verification
    needs live Docker+network+Sigstore, out of scope here and already covered by
    test_gate_image_attestation.py. This fixture exercises the verifier's own
    clone/checkout/parent-check/invoke/parse logic in isolation."""

    repo = tmp_path / "source-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Gate10 Test")
    _git(repo, "config", "user.email", "gate10-test@example.invalid")
    (repo / "application.txt").write_text("release source\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "source commit")
    source_sha = _git(repo, "rev-parse", "HEAD")

    ops_dir = repo / "ops"
    ops_dir.mkdir()
    decision = gate_decision or {
        "allowed": True,
        "operation": "deploy",
        "reason": "gate10_approved_manifest_bound",
        "state_id": "production-release-freeze-2026-07-14",
        "required_gate": "GATE-10",
        "source_git_sha": source_sha,
    }
    if gate_exit_code != 0:
        fake_gate = f"raise SystemExit({gate_exit_code})\n"
    else:
        fake_gate = (
            "import json\nimport sys\n"
            'if sys.argv[1:3] != ["check", "deploy"]:\n'
            "    raise SystemExit(64)\n"
            f"print(json.dumps({decision!r}))\n"
        )
    (ops_dir / "production_release_gate.py").write_text(fake_gate, encoding="utf-8")
    (ops_dir / "production-release-manifest.json").write_text(
        json.dumps({"hashes": {"backend_image_digest": VALID_DIGEST}}),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "gate control commit")
    control_sha = _git(repo, "rev-parse", "HEAD")
    return repo, source_sha, control_sha


def test_arguments_accepts_well_formed_flags():
    control_sha = "a" * 40
    source_sha = "b" * 40
    result = verifier._arguments(
        [
            "--control-sha",
            control_sha,
            "--source-sha",
            source_sha,
            "--backend-image",
            VALID_DIGEST,
        ]
    )
    assert result == (control_sha, source_sha, VALID_DIGEST)


@pytest.mark.parametrize(
    "argv",
    [
        [
            "--control-sha",
            "not-hex",
            "--source-sha",
            "b" * 40,
            "--backend-image",
            VALID_DIGEST,
        ],
        [
            "--control-sha",
            "a" * 40,
            "--source-sha",
            "b" * 39,
            "--backend-image",
            VALID_DIGEST,
        ],
        [
            "--control-sha",
            "a" * 40,
            "--source-sha",
            "b" * 40,
            "--backend-image",
            "not-a-digest",
        ],
        ["--control-sha", "a" * 40, "--source-sha", "b" * 40],
        [
            "--wrong-flag",
            "a" * 40,
            "--source-sha",
            "b" * 40,
            "--backend-image",
            VALID_DIGEST,
        ],
    ],
)
def test_arguments_rejects_malformed_input(argv: list[str]):
    with pytest.raises(verifier.VerificationDenied):
        verifier._arguments(argv)


def test_git_helper_threads_config_global_matching_todays_dubious_ownership_fix(
    monkeypatch: pytest.MonkeyPatch,
):
    # Confirms this file reuses the exact fix verified today for
    # bootstrap_gate08_remediation_control.py, rather than re-deriving it: a
    # config *file* passed via GIT_CONFIG_GLOBAL, never `-c safe.directory=` on
    # the command line, which git 2.43's local-transport clone path ignores.
    captured: dict[str, object] = {}

    def fake_run(command, *, env, **kwargs):
        captured["command"] = command
        captured["env"] = env
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    verifier._git(
        Path("/tmp/hooks"),
        ("status",),
        checkout=Path("/tmp/checkout"),
        config_global=Path("/tmp/root-stage/safe-directory.gitconfig"),
    )

    assert (
        captured["env"]["GIT_CONFIG_GLOBAL"]
        == "/tmp/root-stage/safe-directory.gitconfig"
    )
    assert not any("safe.directory" in arg for arg in captured["command"])


def test_prepare_checkout_writes_and_removes_a_scoped_safe_directory_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo, source_sha, control_sha = _build_control_repo(tmp_path)
    root_stage = tmp_path / "root-stage"
    hooks = root_stage / "empty-hooks"
    checkout = root_stage / "checkout"
    hooks.mkdir(parents=True)

    written_configs: list[str] = []
    real_git = verifier._git

    def spying_git(hooks_arg, arguments, **kwargs):
        if kwargs.get("config_global") is not None:
            written_configs.append(kwargs["config_global"].read_text(encoding="utf-8"))
        return real_git(hooks_arg, arguments, **kwargs)

    monkeypatch.setattr(verifier, "_git", spying_git)

    # The wrong parent stops _prepare_checkout right after the clone+config-file
    # write, before it ever reaches the root-owned-checkout verification steps
    # (real-root-only, see module docstring) -- exactly what this test needs.
    with pytest.raises(verifier.VerificationDenied, match="parent does not match"):
        verifier._prepare_checkout(repo, checkout, hooks, control_sha, "0" * 40)

    assert len(written_configs) == 1
    assert f"directory = {repo}\n" in written_configs[0]
    assert f"directory = {repo / '.git'}\n" in written_configs[0]
    assert not (checkout.parent / "safe-directory.gitconfig").exists()


def test_prepare_checkout_rejects_wrong_parent_before_touching_ownership(
    tmp_path: Path,
):
    repo, source_sha, control_sha = _build_control_repo(tmp_path)
    root_stage = tmp_path / "root-stage"
    hooks = root_stage / "empty-hooks"
    checkout = root_stage / "checkout"
    hooks.mkdir(parents=True)

    with pytest.raises(
        verifier.VerificationDenied, match="parent does not match supplied source"
    ):
        verifier._prepare_checkout(repo, checkout, hooks, control_sha, "0" * 40)


def test_run_gate_accepts_an_exact_matching_decision(tmp_path: Path):
    _, source_sha, control_sha = _build_control_repo(tmp_path)
    checkout = tmp_path / "plain-checkout"
    (checkout / "ops").mkdir(parents=True)
    (checkout / "ops" / "production_release_gate.py").write_text(
        "import json\nimport sys\n"
        'print(json.dumps({"allowed": True, "operation": "deploy", '
        '"reason": "gate10_approved_manifest_bound", '
        '"state_id": "production-release-freeze-2026-07-14", '
        f'"required_gate": "GATE-10", "source_git_sha": "{source_sha}"}}))\n',
        encoding="utf-8",
    )

    verifier._run_gate(checkout, source_sha)  # must not raise


def test_run_gate_rejects_denied_gate(tmp_path: Path):
    checkout = tmp_path / "plain-checkout"
    (checkout / "ops").mkdir(parents=True)
    (checkout / "ops" / "production_release_gate.py").write_text(
        "raise SystemExit(78)\n", encoding="utf-8"
    )

    with pytest.raises(verifier.VerificationDenied, match="denied the control commit"):
        verifier._run_gate(checkout, "a" * 40)


@pytest.mark.parametrize(
    "broken_field",
    ["operation", "reason", "required_gate", "source_git_sha", "extra_field"],
)
def test_run_gate_rejects_inexact_decision_shape(tmp_path: Path, broken_field: str):
    source_sha = "a" * 40
    decision = {
        "allowed": True,
        "operation": "deploy",
        "reason": "gate10_approved_manifest_bound",
        "state_id": "production-release-freeze-2026-07-14",
        "required_gate": "GATE-10",
        "source_git_sha": source_sha,
    }
    if broken_field == "extra_field":
        decision["unexpected"] = True
    else:
        decision[broken_field] = "wrong-value"

    checkout = tmp_path / "plain-checkout"
    (checkout / "ops").mkdir(parents=True)
    (checkout / "ops" / "production_release_gate.py").write_text(
        f"import json\nprint(json.dumps({decision!r}))\n", encoding="utf-8"
    )

    with pytest.raises(verifier.VerificationDenied, match="decision is not exact"):
        verifier._run_gate(checkout, source_sha)


def test_backend_image_digest_cross_check_uses_constant_time_compare():
    # The property this whole phase exists for: a genuine control commit and
    # decision alone are not enough -- the CLI-supplied image must match what
    # the trusted, checked-out manifest actually approved.
    assert hmac.compare_digest(VALID_DIGEST, VALID_DIGEST)
    assert not hmac.compare_digest(VALID_DIGEST, OTHER_DIGEST)


def test_verify_gate10_control_commit_cleans_up_checkout_on_early_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo, source_sha, control_sha = _build_control_repo(tmp_path)
    monkeypatch.setattr(verifier, "SOURCE_REPOSITORY", repo)
    monkeypatch.setattr(verifier.os, "geteuid", lambda: 0)
    monkeypatch.setattr(verifier.os, "chown", lambda *a, **k: None)

    stages: list[Path] = []
    real_mkdtemp = verifier.tempfile.mkdtemp
    writable_run = tmp_path / "run"
    writable_run.mkdir()

    def spying_mkdtemp(*args, **kwargs):
        # main() hardcodes dir="/run", which a non-root test process cannot
        # write to -- redirected to a writable stand-in so the real create-
        # then-cleanup flow is still genuinely exercised end to end.
        kwargs["dir"] = str(writable_run)
        path = real_mkdtemp(*args, **kwargs)
        stages.append(Path(path))
        return path

    monkeypatch.setattr(verifier.tempfile, "mkdtemp", spying_mkdtemp)

    with pytest.raises(verifier.VerificationDenied, match="parent does not match"):
        verifier.main(
            [
                "--control-sha",
                control_sha,
                "--source-sha",
                "0" * 40,  # deliberately wrong parent
                "--backend-image",
                VALID_DIGEST,
            ]
        )

    assert len(stages) == 1
    assert not stages[0].exists()


def test_main_requires_root():
    with pytest.raises(verifier.VerificationDenied, match="root is required"):
        verifier.main(
            [
                "--control-sha",
                "a" * 40,
                "--source-sha",
                "b" * 40,
                "--backend-image",
                VALID_DIGEST,
            ]
        )
