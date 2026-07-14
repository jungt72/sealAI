"""Root-trusted release staging and one-shot deployment authorization tests."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
sys.path.insert(0, str(OPS))

import production_release_control as control  # noqa: E402


def _load_dashboard_module():
    path = REPO / "frontend-v2" / "scripts" / "dashboard_release.py"
    spec = importlib.util.spec_from_file_location("dashboard_release_for_control", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DASHBOARD = _load_dashboard_module()
CONTROL_SHA = "c" * 40
SOURCE_SHA = "a" * 40
BACKEND_DIGEST = "sha256:" + "2" * 64
BACKEND_IMAGE = f"ghcr.io/jungt72/sealai-backend-v2:rc@{BACKEND_DIGEST}"
NOW = dt.datetime(2026, 7, 14, 20, 0, tzinfo=dt.timezone.utc)


def _receipt(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "GATE-08",
        "decision": "APPROVED",
        "scope": "production-deployment",
        "approval_id": "gate08-deploy-test-001",
        "approved_by": "test-owner",
        "approved_at": "2026-07-14T19:55:00Z",
        "expires_at": "2026-07-14T20:30:00Z",
        "deployment_target": "sealingai-production",
        "operation": "backend-v2-promote",
        "single_use": True,
        "control_git_sha": CONTROL_SHA,
        "source_git_sha": SOURCE_SHA,
        "release_manifest_sha256": "8" * 64,
        "promotion_evidence_sha256": "7" * 64,
        "backend_image_digest": BACKEND_DIGEST,
    }
    value.update(overrides)
    return value


def _write_private(path: Path, value: dict[str, object]) -> bytes:
    raw = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return raw


def _trusted() -> frozenset[int]:
    return frozenset({0, os.geteuid()})


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_receipt_requires_exact_short_lived_source_manifest_and_operation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "receipt.json"
    raw = _write_private(path, _receipt())

    value, observed, digest = control.load_receipt(
        path,
        now=NOW,
        control_sha=CONTROL_SHA,
        source_sha=SOURCE_SHA,
        backend_image=BACKEND_IMAGE,
        trusted_uids=_trusted(),
    )

    assert value["operation"] == "backend-v2-promote"
    assert observed == raw
    assert digest == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"expires_at": "2026-07-14T19:59:59Z"}, "expired"),
        ({"expires_at": "2026-07-14T21:00:01Z"}, "over-broad"),
        (
            {
                "approved_at": "2026-07-14T20:05:00Z",
                "expires_at": "2026-07-14T20:01:00Z",
            },
            "expired",
        ),
        ({"operation": "arbitrary-command"}, "operation"),
        ({"source_git_sha": "b" * 40}, "source"),
        ({"unexpected": True}, "schema"),
    ],
)
def test_receipt_rejects_expiry_scope_source_and_schema(
    tmp_path: Path, overrides: dict[str, object], match: str
) -> None:
    path = tmp_path / "receipt.json"
    _write_private(path, _receipt(**overrides))

    with pytest.raises(control.ControlDenied, match=match):
        control.load_receipt(
            path,
            now=NOW,
            control_sha=CONTROL_SHA,
            source_sha=SOURCE_SHA,
            backend_image=BACKEND_IMAGE,
            trusted_uids=_trusted(),
        )


def test_private_receipt_rejects_symlink_and_writable_path(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    _write_private(receipt, _receipt())
    alias = tmp_path / "receipt-link.json"
    alias.symlink_to(receipt)

    with pytest.raises(control.ControlDenied, match="topology"):
        control.load_receipt(
            alias,
            now=NOW,
            control_sha=CONTROL_SHA,
            source_sha=SOURCE_SHA,
            backend_image=BACKEND_IMAGE,
            trusted_uids=_trusted(),
        )

    receipt.chmod(0o620)
    with pytest.raises(control.ControlDenied, match="unsafe"):
        control.load_receipt(
            receipt,
            now=NOW,
            control_sha=CONTROL_SHA,
            source_sha=SOURCE_SHA,
            backend_image=BACKEND_IMAGE,
            trusted_uids=_trusted(),
        )


def test_gate10_decision_rejects_arbitrary_image_and_missing_evidence() -> None:
    receipt = _receipt()
    hashes = {
        "served_tree_sha256": "1" * 64,
        "backend_image_digest": BACKEND_DIGEST,
        "frontend_image_digest": "sha256:" + "3" * 64,
        "dashboard_artifact_sha256": "4" * 64,
        "database_migration_sha256": "5" * 64,
        "rollback_plan_sha256": "6" * 64,
        "evidence_manifest_sha256": "7" * 64,
    }
    decision = {
        "allowed": True,
        "operation": "deploy",
        "reason": "gate10_approved_manifest_bound",
        "state_id": "freeze-test",
        "required_gate": "GATE-10",
        "source_git_sha": SOURCE_SHA,
        "release_hashes": hashes,
    }

    assert (
        control.validate_gate10_decision(
            decision,
            receipt=receipt,
            source_sha=SOURCE_SHA,
            backend_image=BACKEND_IMAGE,
        )
        == hashes
    )

    with pytest.raises(control.ControlDenied, match="requested image"):
        control.validate_gate10_decision(
            decision,
            receipt=receipt,
            source_sha=SOURCE_SHA,
            backend_image="ghcr.io/jungt72/sealai-backend-v2:other@sha256:" + "9" * 64,
        )
    assert (
        control.IMAGE_RE.fullmatch("ghcr.io/attacker/arbitrary:rc@" + BACKEND_DIGEST)
        is None
    )
    without_evidence = {**decision, "release_hashes": {**hashes}}
    del without_evidence["release_hashes"]["evidence_manifest_sha256"]
    with pytest.raises(control.ControlDenied, match="not exact"):
        control.validate_gate10_decision(
            without_evidence,
            receipt=receipt,
            source_sha=SOURCE_SHA,
            backend_image=BACKEND_IMAGE,
        )


def test_fixed_evidence_bundle_binds_root_owned_result_and_rejects_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence_root = tmp_path / "release-evidence"
    runs = evidence_root / "runs"
    run = runs / "production-rc-001"
    run.mkdir(parents=True, mode=0o755)
    results_raw = b'{"result":"passed"}\n'
    results = run / "results.json"
    results.write_bytes(results_raw)
    promotion = evidence_root / "promotion-evidence.json"
    promotion_raw = (
        json.dumps(
            {
                "payload": {
                    "results": {
                        "run_label": run.name,
                        "results_sha256": hashlib.sha256(results_raw).hexdigest(),
                    }
                }
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    promotion.write_bytes(promotion_raw)
    rollback = evidence_root / "rollback-plan.json"
    rollback_raw = b'{"rollback":"reviewed"}\n'
    rollback.write_bytes(rollback_raw)
    monkeypatch.setattr(control, "EVIDENCE_ROOT", evidence_root)
    monkeypatch.setattr(control, "PROMOTION_EVIDENCE", promotion)
    monkeypatch.setattr(control, "ROLLBACK_PLAN", rollback)
    monkeypatch.setattr(control, "RUNS_DIR", runs)
    hashes = {
        "evidence_manifest_sha256": hashlib.sha256(promotion_raw).hexdigest(),
        "rollback_plan_sha256": hashlib.sha256(rollback_raw).hexdigest(),
    }

    control.verify_evidence_bundle(hashes, trusted_uids=_trusted())
    external = tmp_path / "external-results.json"
    external.write_bytes(results_raw)
    results.unlink()
    results.symlink_to(external)

    with pytest.raises(control.ControlDenied, match="topology"):
        control.verify_evidence_bundle(hashes, trusted_uids=_trusted())


def _make_control_repo(tmp_path: Path) -> tuple[Path, str, str, dict[str, object]]:
    repo = tmp_path / "source"
    (repo / "ops").mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Release Test")
    _git(repo, "config", "user.email", "release@example.invalid")
    (repo / "application.txt").write_text("source\n", encoding="utf-8")
    for name in (
        "production-release-state.json",
        "production-release-gate10-approval.json",
        "production-release-manifest.json",
    ):
        (repo / "ops" / name).write_text("{}\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "source")
    source = _git(repo, "rev-parse", "HEAD")
    manifest = {
        "source_git_sha": source,
        "hashes": {
            "served_tree_sha256": "1" * 64,
            "backend_image_digest": BACKEND_DIGEST,
            "frontend_image_digest": "sha256:" + "3" * 64,
            "dashboard_artifact_sha256": "4" * 64,
            "database_migration_sha256": "5" * 64,
            "rollback_plan_sha256": "6" * 64,
            "evidence_manifest_sha256": "7" * 64,
        },
    }
    (repo / "ops/production-release-state.json").write_text(
        '{"freeze":{"active":false}}\n', encoding="utf-8"
    )
    (repo / "ops/production-release-gate10-approval.json").write_text(
        '{"decision":"APPROVED"}\n', encoding="utf-8"
    )
    manifest_raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    (repo / "ops/production-release-manifest.json").write_bytes(manifest_raw)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "control")
    control_sha = _git(repo, "rev-parse", "HEAD")
    receipt = _receipt(
        control_git_sha=control_sha,
        source_git_sha=source,
        release_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
    )
    return repo, source, control_sha, receipt


def test_staging_copies_only_exact_two_commit_control_without_executing_source(
    tmp_path: Path,
) -> None:
    repo, source, control_sha, receipt = _make_control_repo(tmp_path)
    upload_pack_marker = tmp_path / "untrusted-upload-pack-hook-ran"
    _git(
        repo,
        "config",
        "uploadpack.packObjectsHook",
        f"/usr/bin/touch {upload_pack_marker}",
    )
    releases = tmp_path / "releases"
    releases.mkdir(mode=0o755)
    destination = releases / control_sha

    control.stage_control(
        repo,
        destination,
        control_sha=control_sha,
        source_sha=source,
        receipt=receipt,
        trusted_uid=os.geteuid(),
    )

    manifest = control.verify_stage(
        destination,
        control_sha=control_sha,
        source_sha=source,
        receipt=receipt,
        trusted_uids=_trusted(),
    )
    assert manifest["source_git_sha"] == source
    assert stat.S_IMODE((destination / "application.txt").stat().st_mode) == 0o644
    assert (destination / "application.txt").stat().st_mode & 0o022 == 0
    assert not upload_pack_marker.exists()


def test_root_staging_never_runs_upload_pack_or_fetch_against_user_repository() -> None:
    source = (OPS / "production_release_control.py").read_text(encoding="utf-8")
    export = source[
        source.index("def _export_git_pack(") : source.index(
            "def _index_git_pack(", source.index("def _export_git_pack(")
        )
    ]
    stage = source[
        source.index("def stage_control(") : source.index(
            "def validate_gate10_decision(", source.index("def stage_control(")
        )
    ]

    assert '"/usr/bin/setpriv"' in export
    assert all(
        item in export
        for item in (
            '"--clear-groups"',
            '"--no-new-privs"',
            '"--bounding-set=-all"',
            '"pack-objects"',
        )
    )
    assert '"fetch"' not in export
    assert "_export_git_pack(" in stage
    assert "_index_git_pack(" in stage


def test_consumed_receipt_is_exclusive_and_not_replayable(tmp_path: Path) -> None:
    consumed = tmp_path / "consumed"
    consumed.mkdir(mode=0o700)
    receipt = _receipt()
    raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()

    control.consume_receipt(
        receipt,
        raw,
        expected_receipt_sha256=digest,
        consumed_root=consumed,
        trusted_uid=os.geteuid(),
    )
    with pytest.raises(control.ControlDenied, match="already consumed"):
        control.consume_receipt(
            receipt,
            raw,
            expected_receipt_sha256=digest,
            consumed_root=consumed,
            trusted_uid=os.geteuid(),
        )


def test_consumed_receipt_handles_partial_kernel_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumed = tmp_path / "consumed"
    consumed.mkdir(mode=0o700)
    receipt = _receipt(approval_id="gate08-partial-write")
    raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()
    real_write = os.write
    calls = 0

    def partial_write(descriptor: int, payload: bytes | memoryview) -> int:
        nonlocal calls
        calls += 1
        limit = max(1, len(payload) // 2)
        return real_write(descriptor, payload[:limit])

    monkeypatch.setattr(control.os, "write", partial_write)
    path = control.consume_receipt(
        receipt,
        raw,
        expected_receipt_sha256=hashlib.sha256(raw).hexdigest(),
        consumed_root=consumed,
        trusted_uid=os.geteuid(),
    )

    assert calls > 1
    assert (
        json.loads(path.read_text(encoding="ascii"))["approval_id"]
        == receipt["approval_id"]
    )


def _prepare_dashboard_release(
    tmp_path: Path, release_root: Path, source: str, content: str
):
    candidate = tmp_path / f"candidate-{source[0]}-{len(content)}"
    candidate.mkdir(mode=0o755)
    (candidate / "index.html").write_text(content, encoding="utf-8")
    artifact = DASHBOARD.inspect_candidate(
        candidate,
        source_git_sha=source,
        source_date_epoch=1_700_000_000,
        npm_lock_sha256="9" * 64,
        node_version="22.17.0",
        npm_version="10.9.2",
    )
    DASHBOARD.prepare_release(candidate, release_root, artifact)
    return artifact


def test_dashboard_activation_consumes_exact_source_and_hash_and_rolls_back(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "dashboard-releases"
    release_root.mkdir(mode=0o755)
    first = _prepare_dashboard_release(tmp_path, release_root, "a" * 40, "first")
    second = _prepare_dashboard_release(tmp_path, release_root, "b" * 40, "second")
    tool = REPO / "frontend-v2/scripts/dashboard_release.py"

    result = control.activate_dashboard_release(
        source_git_sha=first.source_git_sha,
        artifact_sha256=first.artifact_sha256,
        trusted_uids=_trusted(),
        release_root=release_root,
        tool=tool,
    )
    assert result["changed"] is True
    assert os.readlink(release_root / "current") == f"artifacts/{first.release_id}"

    control.activate_dashboard_release(
        source_git_sha=second.source_git_sha,
        artifact_sha256=second.artifact_sha256,
        trusted_uids=_trusted(),
        release_root=release_root,
        tool=tool,
    )
    assert os.readlink(release_root / "current") == f"artifacts/{second.release_id}"
    assert os.readlink(release_root / "rollback") == f"artifacts/{first.release_id}"

    rollback = control.rollback_dashboard_release(
        trusted_uids=_trusted(), release_root=release_root, tool=tool
    )
    assert rollback["release_id"] == first.release_id
    assert os.readlink(release_root / "current") == f"artifacts/{first.release_id}"
    assert os.readlink(release_root / "rollback") == f"artifacts/{second.release_id}"

    with pytest.raises(control.ControlDenied, match="unavailable"):
        control.verify_dashboard_release(
            source_git_sha=first.source_git_sha,
            artifact_sha256="f" * 64,
            trusted_uids=_trusted(),
            release_root=release_root,
            tool=tool,
        )


def test_dashboard_activation_refuses_corrupt_current_as_rollback(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "dashboard-releases"
    release_root.mkdir(mode=0o755)
    first = _prepare_dashboard_release(tmp_path, release_root, "a" * 40, "first")
    second = _prepare_dashboard_release(tmp_path, release_root, "b" * 40, "second")
    tool = REPO / "frontend-v2/scripts/dashboard_release.py"
    control.activate_dashboard_release(
        source_git_sha=first.source_git_sha,
        artifact_sha256=first.artifact_sha256,
        trusted_uids=_trusted(),
        release_root=release_root,
        tool=tool,
    )
    current_before = os.readlink(release_root / "current")
    corrupt = release_root / current_before / "index.html"
    corrupt.chmod(0o644)
    corrupt.write_text("tampered", encoding="utf-8")

    with pytest.raises(control.ControlDenied, match="denied the artifact"):
        control.activate_dashboard_release(
            source_git_sha=second.source_git_sha,
            artifact_sha256=second.artifact_sha256,
            trusted_uids=_trusted(),
            release_root=release_root,
            tool=tool,
        )

    assert os.readlink(release_root / "current") == current_before
    assert not (release_root / "rollback").exists()


def test_dashboard_failed_switch_restores_both_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_root = tmp_path / "dashboard-releases"
    release_root.mkdir(mode=0o755)
    first = _prepare_dashboard_release(tmp_path, release_root, "a" * 40, "first")
    second = _prepare_dashboard_release(tmp_path, release_root, "b" * 40, "second")
    tool = REPO / "frontend-v2/scripts/dashboard_release.py"
    control.activate_dashboard_release(
        source_git_sha=first.source_git_sha,
        artifact_sha256=first.artifact_sha256,
        trusted_uids=_trusted(),
        release_root=release_root,
        tool=tool,
    )
    original_switch = control._atomic_dashboard_link
    denied_target = f"artifacts/{second.release_id}"

    def fail_new_current(root: Path, name: str, target: str) -> None:
        if name == "current" and target == denied_target:
            raise control.ControlDenied("simulated current switch failure")
        original_switch(root, name, target)

    monkeypatch.setattr(control, "_atomic_dashboard_link", fail_new_current)
    with pytest.raises(control.ControlDenied, match="simulated"):
        control.activate_dashboard_release(
            source_git_sha=second.source_git_sha,
            artifact_sha256=second.artifact_sha256,
            trusted_uids=_trusted(),
            release_root=release_root,
            tool=tool,
        )

    assert os.readlink(release_root / "current") == f"artifacts/{first.release_id}"
    assert not (release_root / "rollback").exists()
