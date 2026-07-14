"""Production freeze must fail closed before any production mutation."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
sys.path.insert(0, str(OPS))

import production_release_gate as gate  # noqa: E402


STATE_PATH = OPS / "production-release-state.json"


def _write_remediation_control_approval(
    path: Path, *, overrides: dict[str, object] | None = None
) -> Path:
    now = gate.dt.datetime.now(gate.dt.timezone.utc).replace(microsecond=0)
    approval: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "GATE-08",
        "decision": "APPROVED",
        "scope": "p0-remediation-control-install",
        "approval_id": "gate08-test-approval-001",
        "approved_by": "test-owner",
        "approved_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + gate.dt.timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z"),
        "source_git_sha": _git(REPO, "rev-parse", "HEAD"),
        "artifact_sha256": {
            relative: gate._artifact_sha256(relative)
            for relative in sorted(gate.REMEDIATION_CONTROL_ARTIFACTS)
        },
    }
    if overrides:
        approval.update(overrides)
    path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _state(*, active: bool) -> dict[str, object]:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state["freeze"]["active"] = active
    return state


def _manifest(
    *,
    readiness: dict[str, bool] | None = None,
    source_git_sha: str = "a" * 40,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "manifest_id": "release-manifest-test-001",
        "freeze_state_id": "production-release-freeze-2026-07-14",
        "source_git_sha": source_git_sha,
        "readiness": readiness
        or {
            "P0_SECRETS_CONTAINED": True,
            "P0_STORAGE_STABLE": True,
            "P0_REDIS_STABLE": True,
            "RELEASE_GATE_FAIL_CLOSED": True,
        },
        "hashes": {
            "served_tree_sha256": "1" * 64,
            "backend_image_digest": "sha256:" + "2" * 64,
            "frontend_image_digest": "sha256:" + "3" * 64,
            "dashboard_artifact_sha256": "4" * 64,
            "database_migration_sha256": "5" * 64,
            "rollback_plan_sha256": "6" * 64,
            "evidence_manifest_sha256": "7" * 64,
        },
    }


def _write_unfreeze_documents(
    tmp_path: Path,
    *,
    manifest: dict[str, object] | None = None,
    approval_hash: str | None = None,
    source_git_sha: str = "a" * 40,
) -> tuple[Path, Path, Path]:
    state_path = tmp_path / "production-release-state.json"
    approval_path = tmp_path / "production-release-gate10-approval.json"
    manifest_path = tmp_path / "production-release-manifest.json"
    state_path.write_text(json.dumps(_state(active=False)) + "\n", encoding="utf-8")
    manifest_value = manifest or _manifest(source_git_sha=source_git_sha)
    manifest_raw = (json.dumps(manifest_value, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_raw)
    approval = {
        "schema_version": 1,
        "gate_id": "GATE-10",
        "approval_id": "gate10-test-approval-001",
        "decision": "APPROVED",
        "scope": "production-release-freeze-lift",
        "freeze_state_id": "production-release-freeze-2026-07-14",
        "approved_by": "test-owner",
        "approved_at": "2026-07-14T12:00:00Z",
        "release_manifest_id": "release-manifest-test-001",
        "release_manifest_sha256": approval_hash
        or hashlib.sha256(manifest_raw).hexdigest(),
    }
    approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    return state_path, approval_path, manifest_path


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_gate_control_repo(
    tmp_path: Path,
    *,
    source_override: str | None = None,
    extra_control_path: bool = False,
) -> tuple[Path, Path, Path, Path, str]:
    repo = tmp_path / "control-repo"
    ops = repo / "ops"
    ops.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Gate Test")
    _git(repo, "config", "user.email", "gate-test@example.invalid")
    (repo / "application.txt").write_text("release source\n", encoding="utf-8")
    (ops / "production-release-state.json").write_text(
        json.dumps(_state(active=True)) + "\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "source commit")
    source_sha = _git(repo, "rev-parse", "HEAD")

    state_path, approval_path, manifest_path = _write_unfreeze_documents(
        ops, source_git_sha=source_override or source_sha
    )
    if extra_control_path:
        (repo / "unrelated.txt").write_text("not gate control\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "gate control commit")
    return repo, state_path, approval_path, manifest_path, source_sha


def test_checked_in_freeze_is_active_and_requires_gate_10():
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    assert state["freeze"]["active"] is True
    assert state["freeze"]["required_gate"] == "GATE-10"
    assert set(state["unfreeze_requirements"]["required_readiness_claims"]) == {
        "P0_SECRETS_CONTAINED",
        "P0_STORAGE_STABLE",
        "P0_REDIS_STABLE",
        "RELEASE_GATE_FAIL_CLOSED",
    }
    assert not (OPS / "production-release-gate10-approval.json").exists()
    assert not (OPS / "production-release-manifest.json").exists()


@pytest.mark.parametrize("operation", sorted(gate.MUTATING_OPERATIONS))
def test_freeze_blocks_every_mutating_operation(operation: str):
    with pytest.raises(gate.GateDenied):
        gate.evaluate(operation)


def test_freeze_allows_starting_existing_recovery_artifacts():
    decision = gate.evaluate("recovery-start-existing")

    assert decision.allowed is True
    assert decision.reason == "freeze_recovery_start_existing_only"


def test_freeze_allows_only_hash_bound_gate08_control_install(tmp_path: Path):
    approval = _write_remediation_control_approval(tmp_path / "gate08.json")

    decision = gate.evaluate(
        "remediation-control-install",
        remediation_approval_path=approval,
        require_versioned=False,
    )

    assert decision.allowed is True
    assert decision.required_gate == "GATE-08"
    assert decision.reason == "gate08_hash_bound_remediation_control_install"
    assert decision.approval_id == "gate08-test-approval-001"


@pytest.mark.parametrize(
    "mutation",
    [
        {"source_git_sha": "0" * 40},
        {"expires_at": "2020-01-01T00:00:00Z"},
        {"unexpected": True},
    ],
)
def test_gate08_control_install_rejects_wrong_commit_expiry_or_schema(
    tmp_path: Path, mutation: dict[str, object]
):
    approval = _write_remediation_control_approval(
        tmp_path / "gate08.json", overrides=mutation
    )

    with pytest.raises(gate.GateConfigurationError):
        gate.evaluate(
            "remediation-control-install",
            remediation_approval_path=approval,
            require_versioned=False,
        )


def test_gate08_control_install_rejects_hash_drift_and_nonprivate_receipt(
    tmp_path: Path,
):
    approval = _write_remediation_control_approval(tmp_path / "gate08.json")
    value = json.loads(approval.read_text(encoding="utf-8"))
    first = sorted(gate.REMEDIATION_CONTROL_ARTIFACTS)[0]
    value["artifact_sha256"][first] = "0" * 64
    approval.write_text(json.dumps(value) + "\n", encoding="utf-8")

    with pytest.raises(gate.GateConfigurationError, match="hash mismatch"):
        gate.evaluate(
            "remediation-control-install",
            remediation_approval_path=approval,
            require_versioned=False,
        )

    _write_remediation_control_approval(approval)
    approval.chmod(0o640)
    with pytest.raises(gate.GateConfigurationError, match="unsafe"):
        gate.evaluate(
            "remediation-control-install",
            remediation_approval_path=approval,
            require_versioned=False,
        )


def test_environment_variables_cannot_bypass_the_cli_freeze():
    result = subprocess.run(
        [sys.executable, str(OPS / "production_release_gate.py"), "check", "deploy"],
        env={
            **os.environ,
            "SEALAI_RELEASE_FREEZE": "0",
            "SEALAI_OWNER_WAIVER_ACK": "I_ACCEPT_UNEVALUATED_PRODUCTION_DEPLOY",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 20
    assert '"allowed":false' in result.stderr
    assert "production_release_freeze_active" in result.stderr


def test_future_unfreeze_requires_hash_bound_gate10_manifest(tmp_path: Path):
    state_path, approval_path, manifest_path = _write_unfreeze_documents(tmp_path)

    with pytest.raises(
        gate.GateConfigurationError,
        match="GATE-10 lift remains disabled pending exact artifact binding",
    ):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
            require_versioned=False,
        )


def test_future_gate10_success_returns_every_exact_release_hash(
    tmp_path: Path, monkeypatch
):
    manifest = _manifest()
    state_path, approval_path, manifest_path = _write_unfreeze_documents(
        tmp_path, manifest=manifest
    )
    monkeypatch.setattr(gate, "GATE10_LIFT_IMPLEMENTED", True)

    decision = gate.evaluate(
        "deploy",
        state_path=state_path,
        approval_path=approval_path,
        manifest_path=manifest_path,
        require_versioned=False,
    )

    assert decision.allowed is True
    assert decision.release_hashes == manifest["hashes"]
    assert decision.as_dict()["release_hashes"] == manifest["hashes"]


@pytest.mark.parametrize(
    "readiness",
    [
        {
            "P0_SECRETS_CONTAINED": True,
            "P0_STORAGE_STABLE": True,
            "P0_REDIS_STABLE": False,
            "RELEASE_GATE_FAIL_CLOSED": True,
        },
        {
            "P0_SECRETS_CONTAINED": True,
            "P0_STORAGE_STABLE": True,
            "P0_REDIS_STABLE": True,
        },
        {
            "P0_SECRETS_CONTAINED": True,
            "P0_STORAGE_STABLE": True,
            "P0_REDIS_STABLE": True,
            "RELEASE_GATE_FAIL_CLOSED": True,
            "UNREVIEWED_EXTRA": True,
        },
    ],
)
def test_unfreeze_requires_exactly_four_true_readiness_claims(
    tmp_path: Path, readiness: dict[str, bool]
):
    state_path, approval_path, manifest_path = _write_unfreeze_documents(
        tmp_path, manifest=_manifest(readiness=readiness)
    )

    with pytest.raises(gate.GateConfigurationError):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
            require_versioned=False,
        )


def test_unfreeze_rejects_manifest_byte_hash_mismatch(tmp_path: Path):
    state_path, approval_path, manifest_path = _write_unfreeze_documents(
        tmp_path, approval_hash="0" * 64
    )

    with pytest.raises(gate.GateConfigurationError):
        gate.evaluate(
            "migration",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
            require_versioned=False,
        )


@pytest.mark.parametrize("document", ["state", "approval", "manifest"])
def test_gate_documents_reject_unexpected_schema_fields(tmp_path: Path, document: str):
    manifest = _manifest()
    if document == "manifest":
        manifest["unexpected"] = True
    state_path, approval_path, manifest_path = _write_unfreeze_documents(
        tmp_path, manifest=manifest
    )
    target = {"state": state_path, "approval": approval_path}.get(document)
    if target is not None:
        value = json.loads(target.read_text(encoding="utf-8"))
        value["owner_waiver" if document == "approval" else "unexpected"] = True
        target.write_text(json.dumps(value) + "\n", encoding="utf-8")

    with pytest.raises(gate.GateConfigurationError, match="unexpected fields"):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
            require_versioned=False,
        )


def test_unfreeze_rejects_uncommitted_documents(tmp_path: Path):
    state_path, approval_path, manifest_path = _write_unfreeze_documents(tmp_path)

    with pytest.raises(gate.GateConfigurationError):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )


def test_versioned_two_commit_unfreeze_binds_exact_source_parent(
    tmp_path: Path, monkeypatch
):
    repo, state_path, approval_path, manifest_path, source_sha = (
        _make_gate_control_repo(tmp_path)
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)

    with pytest.raises(
        gate.GateConfigurationError,
        match="GATE-10 lift remains disabled pending exact artifact binding",
    ):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )

    assert _git(repo, "rev-parse", "HEAD^") == source_sha


def test_two_commit_unfreeze_rejects_source_parent_mismatch(
    tmp_path: Path, monkeypatch
):
    repo, state_path, approval_path, manifest_path, _ = _make_gate_control_repo(
        tmp_path, source_override="b" * 40
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)

    with pytest.raises(gate.GateConfigurationError, match="different source parent"):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )


def test_two_commit_unfreeze_rejects_any_other_changed_path(
    tmp_path: Path, monkeypatch
):
    repo, state_path, approval_path, manifest_path, _ = _make_gate_control_repo(
        tmp_path, extra_control_path=True
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)

    with pytest.raises(gate.GateConfigurationError, match="exactly the three"):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )


def test_two_commit_unfreeze_rejects_merge_control_head(tmp_path: Path, monkeypatch):
    repo, state_path, approval_path, manifest_path, source_sha = (
        _make_gate_control_repo(tmp_path)
    )
    _git(repo, "branch", "side", source_sha)
    _git(repo, "checkout", "side")
    (repo / "side.txt").write_text("side change\n", encoding="utf-8")
    _git(repo, "add", "side.txt")
    _git(repo, "commit", "-m", "side commit")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "side", "-m", "merge control head")
    monkeypatch.setattr(gate, "REPO_ROOT", repo)

    with pytest.raises(gate.GateConfigurationError, match="exactly one parent"):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )


def test_release_entrypoints_gate_before_their_first_mutation():
    cases = {
        "release-backend.sh": "docker build",
        "release-frontend.sh": "> frontend/.env.production.local",
        "release-backend-v2.sh": 'mkdir -p "${RUNTIME_DIR}"',
        "promote-local-backend-image.sh": 'docker push "$BACKEND_IMAGE_TAG"',
        "upgrade_infra.sh": 'mkdir -p "$backup_dir"',
        "keycloak_upgrade_preflight.sh": 'docker pull "$IMAGE_REF"',
        "install_sealai_stack_service.sh": 'cp -- "$SERVICE_SRC"',
        "v2-flip.sh": 'TMP="$(mktemp',
    }
    for name, mutation in cases.items():
        script = (OPS / name).read_text(encoding="utf-8")
        helper = script.index("production-release-gate-check.sh")
        gate = script.index("production_release_gate_check", helper)
        assert helper < gate < script.index(mutation), name
        assert "readonly PATH=" in script, name


def test_boot_recovery_is_existing_artifacts_only_and_has_no_pull_path():
    script = (OPS / "up-prod.sh").read_text(encoding="utf-8")

    assert "recovery-start-existing" in script
    assert '"${COMPOSE[@]}" start "${SERVICES[@]}"' in script
    assert '"${COMPOSE[@]}" pull' not in script
    assert '"${COMPOSE[@]}" up' not in script
    assert "docker volume create" not in script
    assert "--remove-orphans" not in script
    assert script.index("production_release_gate_check") < script.index(
        '"${COMPOSE[@]}" start'
    )


def test_deploy_workflow_delegates_gate_and_digest_resolution_to_installed_boundary():
    workflow = (REPO / ".github" / "workflows" / "deploy.yml").read_text(
        encoding="utf-8"
    )

    assert "actions/checkout" not in workflow
    assert "production_release_gate_check" not in workflow
    assert "docker buildx imagetools inspect" not in workflow
    assert (
        "backend_image must be the canonical backend-v2 tag@sha256:digest" in workflow
    )
    assert workflow.index("Validate immutable promotion coordinates") < workflow.index(
        "appleboy/ssh-action"
    )
    assert "EXPECTED_CONTROL_SHA,EXPECTED_SOURCE_SHA,BACKEND_V2_IMAGE" in workflow
    assert (
        "/usr/local/libexec/sealai/production-deploy-remote-entrypoint.sh" in workflow
    )
    assert "/usr/bin/env -i" in workflow
    assert "/usr/bin/sudo -n --" in workflow
    assert "git fetch" not in workflow
    assert "git checkout" not in workflow
    assert "./ops/release-backend-v2.sh" not in workflow


def test_v2_release_verifies_image_against_approved_source_parent():
    script = (OPS / "release-backend-v2.sh").read_text(encoding="utf-8")

    assert 'SOURCE_GIT_SHA="${APPROVED_SOURCE_SHA}"' in script
    assert '"${IMAGE_REVISION}" == "${SOURCE_GIT_SHA}"' in script
    assert '"gate_control_git_sha": gate_control_git_sha' in script
    assert '"$("${GIT[@]}" rev-parse HEAD^)" == "${SOURCE_GIT_SHA}"' in script


def test_v2_release_binds_manifest_digest_to_compose_and_both_live_containers():
    script = (OPS / "release-backend-v2.sh").read_text(encoding="utf-8")

    assert (
        'APPROVED_BACKEND_IMAGE_DIGEST="$(release_hash backend_image_digest)"' in script
    )
    assert 'APPROVED_SERVED_TREE_SHA256="$(release_hash served_tree_sha256)"' in script
    assert '"${BACKEND_IMAGE_REF##*@}" == "${APPROVED_BACKEND_IMAGE_DIGEST}"' in script
    assert '"${COMPOSE_BACKEND_IMAGE}" == "${BACKEND_IMAGE_REF}"' in script
    assert '"${COMPOSE_WORKER_IMAGE}" == "${BACKEND_IMAGE_REF}"' in script
    assert '"${SERVED_TREE_SHA256}" == "${APPROVED_SERVED_TREE_SHA256}"' in script
    assert 'PREPARED_IMAGE_ID="$(docker image inspect' in script
    assert '"${IMAGE_SHA}" == "${PREPARED_IMAGE_ID}"' in script
    assert '"${WORKER_IMAGE_SHA}" == "${PREPARED_IMAGE_ID}"' in script
    assert script.index('"${IMAGE_SHA}" == "${PREPARED_IMAGE_ID}"') < script.index(
        'printf \'%s\\n\' "${LINE}" >> "${LEDGER}"'
    )


def test_v2_release_uses_complete_fixed_rc_evidence_before_database_or_activation():
    script = (OPS / "release-backend-v2.sh").read_text(encoding="utf-8")

    outer_gate = script.index("production_release_gate_check")
    lease = script.index("acquire_production_storage_lease")
    pull = script.index('docker pull "${BACKEND_IMAGE_REF}"')
    rc_gate = script.index("/usr/bin/python3 -I ops/v2_deploy_gate.py")
    backup = script.index("creating verified pre-migration backup")
    migration = script.index("applying V2 Alembic migrations")
    activation = script.index('"${COMPOSE[@]}" up -d')
    assert outer_gate < lease < pull < rc_gate < backup < migration < activation
    assert "RUNS_DIR=/var/lib/sealai/release-evidence/runs" in script
    assert (
        "PROMOTION_EVIDENCE_FILE=/var/lib/sealai/release-evidence/"
        "promotion-evidence.json" in script
    )
    for option in (
        "--rc-evidence",
        "--rc-evidence-sha256",
        "--candidate-image-digest",
        "--candidate-image-config-digest",
        "--served-tree-sha256",
        "--database-migration-sha256",
        "--authority-epoch",
        "--source-git-sha",
    ):
        assert option in script


def test_v2_release_verifies_every_gate10_exposure_hash_at_its_owner_path():
    script = (OPS / "release-backend-v2.sh").read_text(encoding="utf-8")
    remote = (OPS / "production-deploy-remote-entrypoint.sh").read_text(
        encoding="utf-8"
    )

    assert "APPROVED_FRONTEND_IMAGE_DIGEST" in script
    assert "docker inspect frontend --format '{{.Image}}'" in script
    assert "FRONTEND_REPO_DIGESTS_JSON" in script
    assert "database-migration-sha256.py" in script
    assert (
        '"${ACTUAL_ROLLBACK_PLAN_SHA256}" == "${APPROVED_ROLLBACK_PLAN_SHA256}"'
        in script
    )
    assert "/var/lib/sealai/dashboard-releases" in script
    assert '"${INSTALLED_CONTROL}" activate-dashboard' in remote
    assert remote.index('/bin/bash -p "${STAGED_RELEASE}" --final') < remote.index(
        '"${INSTALLED_CONTROL}" activate-dashboard'
    )


def test_normal_dashboard_build_cannot_target_live_production_bind_mount():
    vite_config = (REPO / "frontend-v2" / "vite.config.ts").read_text(encoding="utf-8")
    production_compose = (REPO / "docker-compose.deploy.yml").read_text(
        encoding="utf-8"
    )
    staging_compose = (
        REPO / "ops" / "staging" / "docker-compose.staging.yml"
    ).read_text(encoding="utf-8")

    assert 'const candidateOutput = ".build/dashboard-candidate"' in vite_config
    assert "if (resolvedOutput !== expectedOutput)" in vite_config
    assert "lstatSync(current).isSymbolicLink()" in vite_config
    assert "candidate.dev === live.dev && candidate.ino === live.ino" in vite_config
    assert "buildStart()" in vite_config
    assert (
        "/var/lib/sealai/dashboard-releases:/usr/share/nginx/dashboard-releases:ro"
        in production_compose
    )
    assert "./frontend-v2/dist:/usr/share/nginx/v2-client:ro" not in production_compose
    assert (
        "../../frontend-v2/.build/dashboard-candidate:"
        "/usr/share/nginx/dashboard-releases/current:ro" in staging_compose
    )


def _make_v2_flip_test_repo(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo = tmp_path / "v2 flip repo"
    ops = repo / "ops"
    production = repo / "nginx" / "default.conf"
    staging = ops / "staging" / "conf" / "default.conf"
    ops.mkdir(parents=True)
    production.parent.mkdir(parents=True)
    staging.parent.mkdir(parents=True)
    shutil.copy2(OPS / "v2-flip.sh", ops / "v2-flip.sh")
    shutil.copy2(
        OPS / "production-release-gate-check.sh",
        ops / "production-release-gate-check.sh",
    )
    gate_marker = ops / "gate.called"
    (ops / "production_release_gate.py").write_text(
        "from pathlib import Path\n"
        "Path(__file__).with_name('gate.called').write_text('called\\n')\n"
        "raise SystemExit(20)\n",
        encoding="utf-8",
    )
    base = "server {\n    server_name sealingai.com;\n}\n"
    production.write_text(base, encoding="utf-8")
    staging.write_text(base, encoding="utf-8")
    return repo, production, staging, gate_marker


def _run_v2_flip(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    temporary = repo / "tmp"
    temporary.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(repo / "ops" / "v2-flip.sh"), *arguments],
        cwd=repo,
        env={**os.environ, "TMPDIR": str(temporary), "NGINX_CONTAINER": "nginx"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_v2_flip_exact_production_target_is_gated_even_without_reload(tmp_path: Path):
    repo, production, _, gate_marker = _make_v2_flip_test_repo(tmp_path)
    before = production.read_bytes()

    result = _run_v2_flip(repo, "--apply", "--no-reload")

    assert result.returncode == 20
    assert production.read_bytes() == before
    assert gate_marker.is_file()


@pytest.mark.parametrize("alias_kind", ["hardlink", "symlink", "ordinary"])
def test_v2_flip_rejects_aliases_and_arbitrary_files_before_write(
    tmp_path: Path, alias_kind: str
):
    repo, production, _, gate_marker = _make_v2_flip_test_repo(tmp_path)
    target = repo / "alias.conf"
    if alias_kind == "hardlink":
        os.link(production, target)
    elif alias_kind == "symlink":
        target.symlink_to(production)
    else:
        target.write_text(production.read_text(encoding="utf-8"), encoding="utf-8")
    before = production.read_bytes()

    result = _run_v2_flip(
        repo,
        "--apply",
        "--file",
        str(target),
        "--container",
        "nginx",
        "--no-reload",
    )

    assert result.returncode == 2
    assert production.read_bytes() == before
    assert not gate_marker.exists()


def test_v2_flip_rejects_staging_file_with_production_container(tmp_path: Path):
    repo, _, staging, gate_marker = _make_v2_flip_test_repo(tmp_path)
    before = staging.read_bytes()

    result = _run_v2_flip(
        repo,
        "--apply",
        "--file",
        str(staging),
        "--container",
        "nginx",
        "--no-reload",
    )

    assert result.returncode == 2
    assert staging.read_bytes() == before
    assert not gate_marker.exists()


def test_v2_flip_allows_only_exact_staging_tuple_without_production_gate(
    tmp_path: Path,
):
    repo, _, staging, gate_marker = _make_v2_flip_test_repo(tmp_path)

    result = _run_v2_flip(
        repo,
        "--apply",
        "--file",
        str(staging),
        "--container",
        "nginx-staging",
        "--no-reload",
    )

    assert result.returncode == 0, result.stderr
    assert "include snippets/v2_dashboard.conf;" in staging.read_text(encoding="utf-8")
    assert not gate_marker.exists()


def test_v2_flip_restores_exact_bytes_when_nginx_reload_fails(tmp_path: Path):
    repo, _, staging, gate_marker = _make_v2_flip_test_repo(tmp_path)
    before = staging.read_bytes()
    fake_docker = repo / "fake-docker"
    reload_count = repo / "reload-count"
    fake_docker.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f"count_file={str(reload_count)!r}\n"
        'case "${1:-}" in\n'
        "  ps) printf '%s\\n' nginx-staging ;;\n"
        "  exec)\n"
        '    if [[ "${4:-}" == -t ]]; then exit 0; fi\n'
        '    if [[ "${4:-}" == -s && "${5:-}" == reload ]]; then\n'
        '      count=0; [[ ! -f "$count_file" ]] || count=$(<"$count_file")\n'
        '      count=$((count + 1)); printf \'%s\\n\' "$count" >"$count_file"\n'
        '      [[ "$count" -gt 1 ]]\n'
        "    fi\n"
        "    ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    script = repo / "ops" / "v2-flip.sh"
    script.write_text(
        script.read_text(encoding="utf-8").replace(
            "readonly DOCKER_BIN=/usr/bin/docker",
            f"readonly DOCKER_BIN={str(fake_docker)!r}",
        ),
        encoding="utf-8",
    )

    result = _run_v2_flip(
        repo,
        "--apply",
        "--file",
        str(staging),
        "--container",
        "nginx-staging",
    )

    assert result.returncode == 1
    assert staging.read_bytes() == before
    assert reload_count.read_text(encoding="utf-8").strip() == "2"
    assert "nginx reload FAILED" in result.stderr
    assert not gate_marker.exists()
