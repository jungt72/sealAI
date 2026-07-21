"""GATE-10 P1 phase 1: source-derived artifact hashes (served_tree_sha256,
database_migration_sha256) actually verified against the real checked-out tree, not just
format-checked. Every unfreeze test here proves the gate does NOT trust the manifest's
own claim about these two hashes -- it independently recomputes them and rejects a
mismatch.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
sys.path.insert(0, str(OPS))

import production_release_gate as gate  # noqa: E402


# ── live-repo golden / perturbation tests (mirrors test_tree_hash.py's style: perturb a
# real tracked file, restore it in `finally`, no synthetic repo needed) ──────────────────


def _git_status() -> str:
    return subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=str(REPO), text=True
    )


@contextlib.contextmanager
def _probe_file(relpath: str):
    p = REPO / relpath
    p.write_text("probe\n", encoding="utf-8")
    try:
        yield
    finally:
        p.unlink(missing_ok=True)


@contextlib.contextmanager
def _perturb(relpath: str):
    p = REPO / relpath
    orig = p.read_bytes()
    p.write_bytes(orig + b"\n# gate10-artifact-binding-probe\n")
    try:
        yield
    finally:
        p.write_bytes(orig)


def _first_migration_file() -> Path:
    versions = REPO / "backend" / "sealai_v2" / "db" / "migrations" / "versions"
    candidates = sorted(versions.glob("*.py"))
    assert candidates, "expected at least one real migration file to perturb"
    return candidates[0]


def test_served_tree_hash_matches_tree_hash_script():
    """Golden cross-check: the in-process recipe and ops/tree-hash.sh must never drift
    apart -- both are used to compute the same manifest field, in different contexts
    (in-process inside the fail-closed gate vs. shelled out by CI/release scripts)."""

    shell_output = subprocess.check_output(
        ["/bin/bash", "-p", str(OPS / "tree-hash.sh")], cwd=str(REPO), text=True
    ).strip()
    expected = hashlib.sha256(shell_output.encode("ascii")).hexdigest()

    assert gate._served_tree_sha256() == expected


def test_served_tree_hash_moves_with_served_code():
    status_before = _git_status()
    base = gate._served_tree_sha256()
    with _probe_file("backend/sealai_v2/knowledge/__gate10_probe__.py"):
        assert gate._served_tree_sha256() != base
    assert gate._served_tree_sha256() == base
    assert _git_status() == status_before


def test_served_tree_hash_is_neutral_to_eval_and_tests_dirs():
    base = gate._served_tree_sha256()
    for sub in ("eval", "tests"):
        with _probe_file(f"backend/sealai_v2/{sub}/__gate10_probe__.py"):
            assert (
                gate._served_tree_sha256() == base
            ), f"{sub}/ change must be hash-neutral"


def test_database_migration_hash_moves_with_migration_content():
    status_before = _git_status()
    base = gate._database_migration_sha256()
    with _perturb(str(_first_migration_file().relative_to(REPO))):
        assert gate._database_migration_sha256() != base
    assert gate._database_migration_sha256() == base
    assert _git_status() == status_before


def test_database_migration_hash_is_neutral_outside_migrations():
    base = gate._database_migration_sha256()
    with _probe_file("backend/sealai_v2/knowledge/__gate10_probe__.py"):
        assert gate._database_migration_sha256() == base


def test_served_tree_hash_moves_with_migration_content_too():
    """database_migration_sha256 is a narrower scope carved out of the same served tree
    -- a migration change must move BOTH hashes, not just the narrow one."""

    base = gate._served_tree_sha256()
    with _perturb(str(_first_migration_file().relative_to(REPO))):
        assert gate._served_tree_sha256() != base


def test_rollback_plan_hash_moves_with_document_content():
    status_before = _git_status()
    base = gate._rollback_plan_sha256()
    with _perturb("docs/ops/GATE-10-ROLLBACK-PLAN.md"):
        assert gate._rollback_plan_sha256() != base
    assert gate._rollback_plan_sha256() == base
    assert _git_status() == status_before


def test_rollback_plan_hash_is_neutral_outside_its_own_file():
    base = gate._rollback_plan_sha256()
    with _probe_file("backend/sealai_v2/knowledge/__gate10_probe__.py"):
        assert gate._rollback_plan_sha256() == base


def test_evidence_manifest_hash_moves_with_document_content():
    status_before = _git_status()
    base = gate._evidence_manifest_sha256()
    with _perturb("docs/ops/GATE-10-EVIDENCE-MANIFEST.md"):
        assert gate._evidence_manifest_sha256() != base
    assert gate._evidence_manifest_sha256() == base
    assert _git_status() == status_before


def test_evidence_manifest_hash_is_neutral_outside_its_own_file():
    base = gate._evidence_manifest_sha256()
    with _probe_file("backend/sealai_v2/knowledge/__gate10_probe__.py"):
        assert gate._evidence_manifest_sha256() == base


def test_rollback_plan_and_evidence_manifest_hashes_are_independent():
    """Perturbing one of the two new fixed-file hashes must not move the other --
    each is its own single-file pathspec, not accidentally sharing scope."""

    base_rollback = gate._rollback_plan_sha256()
    with _perturb("docs/ops/GATE-10-EVIDENCE-MANIFEST.md"):
        assert gate._rollback_plan_sha256() == base_rollback


# ── synthetic-repo tests (mirrors test_gate11_low_risk_emergency.py /
# test_gate12_staging_build.py style: throwaway git repo, monkeypatched REPO_ROOT, full
# gate.evaluate() integration) ────────────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _state(*, active: bool = True) -> dict[str, object]:
    state = json.loads(
        (OPS / "production-release-state.json").read_text(encoding="utf-8")
    )
    state["freeze"]["active"] = active
    return state


def _dummy_hashes(**overrides: str) -> dict[str, str]:
    hashes = {
        "served_tree_sha256": "1" * 64,
        "backend_image_digest": "sha256:" + "2" * 64,
        "frontend_image_digest": "sha256:" + "3" * 64,
        "dashboard_artifact_sha256": "4" * 64,
        "database_migration_sha256": "5" * 64,
        "rollback_plan_sha256": "6" * 64,
        "evidence_manifest_sha256": "7" * 64,
    }
    hashes.update(overrides)
    return hashes


def _make_minimal_source_commit(repo: Path) -> str:
    """A source commit carrying real stub inputs for every SERVED_TREE_PATHSPECS /
    DATABASE_MIGRATION_PATHSPECS / ROLLBACK_PLAN_PATHSPECS / EVIDENCE_MANIFEST_PATHSPECS
    entry -- same fixture shape as test_production_release_gate.py's
    _make_gate_control_repo, kept independent here so this file has no cross-file import
    dependency."""

    ops = repo / "ops"
    ops.mkdir(parents=True)
    backend = repo / "backend"
    migrations = backend / "sealai_v2" / "db" / "migrations" / "versions"
    migrations.mkdir(parents=True)
    docs_ops = repo / "docs" / "ops"
    docs_ops.mkdir(parents=True)
    (backend / "sealai_v2" / "__init__.py").write_text("", encoding="utf-8")
    (migrations / "20260101_0000_stub.py").write_text(
        "# stub migration\n", encoding="utf-8"
    )
    (backend / "requirements-v2.txt").write_text("stub==1.0\n", encoding="utf-8")
    (backend / ".dockerignore").write_text("__pycache__\n", encoding="utf-8")
    (backend / "Dockerfile.v2").write_text("FROM scratch\n", encoding="utf-8")
    (backend / "docker-entrypoint-v2.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (docs_ops / "GATE-10-ROLLBACK-PLAN.md").write_text(
        "stub rollback plan\n", encoding="utf-8"
    )
    (docs_ops / "GATE-10-EVIDENCE-MANIFEST.md").write_text(
        "stub evidence manifest\n", encoding="utf-8"
    )
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Gate Test")
    _git(repo, "config", "user.email", "gate-test@example.invalid")
    (ops / "production-release-state.json").write_text(
        json.dumps(_state(active=True)) + "\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "source commit")
    return _git(repo, "rev-parse", "HEAD")


def _write_control_commit(
    repo: Path, *, source_sha: str, hashes: dict[str, str]
) -> tuple[Path, Path, Path]:
    ops = repo / "ops"
    # The source commit's state.json carries the checked-in default (freeze active) --
    # a real GATE-10 unfreeze attempt flips it to inactive in the control commit, exactly
    # like _write_unfreeze_documents does in test_production_release_gate.py. Without
    # this, evaluate() never leaves the "freeze active" branch and every operation here
    # falls through to the unconditional GateDenied at the end of that branch.
    (ops / "production-release-state.json").write_text(
        json.dumps(_state(active=False)) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "manifest_id": "release-manifest-test-001",
        "freeze_state_id": "production-release-freeze-2026-07-14",
        "source_git_sha": source_sha,
        "readiness": {
            "P0_SECRETS_CONTAINED": True,
            "P0_STORAGE_STABLE": True,
            "P0_REDIS_STABLE": True,
            "RELEASE_GATE_FAIL_CLOSED": True,
        },
        "hashes": hashes,
    }
    manifest_raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    manifest_path = ops / "production-release-manifest.json"
    manifest_path.write_bytes(manifest_raw)
    now = gate.dt.datetime.now(gate.dt.timezone.utc).replace(microsecond=0)
    approval = {
        "schema_version": 1,
        "gate_id": "GATE-10",
        "approval_id": "gate10-test-approval-001",
        "decision": "APPROVED",
        "scope": "production-release-freeze-lift",
        "freeze_state_id": "production-release-freeze-2026-07-14",
        "approved_by": "test-owner",
        "approved_at": now.isoformat().replace("+00:00", "Z"),
        "release_manifest_id": "release-manifest-test-001",
        "release_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
    }
    approval_path = ops / "production-release-gate10-approval.json"
    approval_path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    state_path = ops / "production-release-state.json"
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "gate control commit")
    return state_path, approval_path, manifest_path


def test_unfreeze_rejects_forged_served_tree_hash(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    source_sha = _make_minimal_source_commit(repo)
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    real_hashes = _dummy_hashes(
        served_tree_sha256=gate._served_tree_sha256(),
        database_migration_sha256=gate._database_migration_sha256(),
    )
    forged = dict(real_hashes, served_tree_sha256="9" * 64)
    state_path, approval_path, manifest_path = _write_control_commit(
        repo, source_sha=source_sha, hashes=forged
    )

    with pytest.raises(
        gate.GateConfigurationError,
        match="does not match the real artifact: served_tree_sha256",
    ):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )


def test_unfreeze_rejects_forged_database_migration_hash(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    source_sha = _make_minimal_source_commit(repo)
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    real_hashes = _dummy_hashes(
        served_tree_sha256=gate._served_tree_sha256(),
        database_migration_sha256=gate._database_migration_sha256(),
    )
    forged = dict(real_hashes, database_migration_sha256="8" * 64)
    state_path, approval_path, manifest_path = _write_control_commit(
        repo, source_sha=source_sha, hashes=forged
    )

    with pytest.raises(
        gate.GateConfigurationError,
        match="does not match the real artifact: database_migration_sha256",
    ):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )


def test_unfreeze_rejects_forged_rollback_plan_hash(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    source_sha = _make_minimal_source_commit(repo)
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    real_hashes = _dummy_hashes(
        served_tree_sha256=gate._served_tree_sha256(),
        database_migration_sha256=gate._database_migration_sha256(),
        rollback_plan_sha256=gate._rollback_plan_sha256(),
        evidence_manifest_sha256=gate._evidence_manifest_sha256(),
    )
    forged = dict(real_hashes, rollback_plan_sha256="9" * 64)
    state_path, approval_path, manifest_path = _write_control_commit(
        repo, source_sha=source_sha, hashes=forged
    )

    with pytest.raises(
        gate.GateConfigurationError,
        match="does not match the real artifact: rollback_plan_sha256",
    ):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )


def test_unfreeze_rejects_forged_evidence_manifest_hash(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    source_sha = _make_minimal_source_commit(repo)
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    real_hashes = _dummy_hashes(
        served_tree_sha256=gate._served_tree_sha256(),
        database_migration_sha256=gate._database_migration_sha256(),
        rollback_plan_sha256=gate._rollback_plan_sha256(),
        evidence_manifest_sha256=gate._evidence_manifest_sha256(),
    )
    forged = dict(real_hashes, evidence_manifest_sha256="0" * 64)
    state_path, approval_path, manifest_path = _write_control_commit(
        repo, source_sha=source_sha, hashes=forged
    )

    with pytest.raises(
        gate.GateConfigurationError,
        match="does not match the real artifact: evidence_manifest_sha256",
    ):
        gate.evaluate(
            "deploy",
            state_path=state_path,
            approval_path=approval_path,
            manifest_path=manifest_path,
        )


def test_unfreeze_accepts_real_source_derived_hashes_up_to_the_lift_flag(
    tmp_path: Path, monkeypatch
):
    """The positive path: with BOTH real hashes correctly bound, the gate must get all
    the way to the (still hardcoded False) GATE10_LIFT_IMPLEMENTED check -- proving
    Phase 1 does not accidentally block a genuinely correct manifest, and does not
    accidentally lift the freeze either."""

    repo = tmp_path / "repo"
    source_sha = _make_minimal_source_commit(repo)
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    real_hashes = _dummy_hashes(
        served_tree_sha256=gate._served_tree_sha256(),
        database_migration_sha256=gate._database_migration_sha256(),
        rollback_plan_sha256=gate._rollback_plan_sha256(),
        evidence_manifest_sha256=gate._evidence_manifest_sha256(),
    )
    state_path, approval_path, manifest_path = _write_control_commit(
        repo, source_sha=source_sha, hashes=real_hashes
    )
    # backend_image_digest/frontend_image_digest attestation needs real
    # Docker+network+Sigstore -- out of scope for this source-derived-hash test (see
    # test_gate_image_attestation.py for that).
    monkeypatch.setattr(
        gate,
        "_IMAGE_ATTESTATION_HASH_VERIFIERS",
        {"backend_image_digest": lambda digest, source_git_sha: None},
    )

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


def test_unfreeze_fails_closed_when_required_build_input_is_missing(
    tmp_path: Path, monkeypatch
):
    """A source commit missing one of the fixed SERVED_TREE_PATHSPECS inputs (here:
    Dockerfile.v2) must fail closed with a clear staging error, never silently hash an
    incomplete tree."""

    repo = tmp_path / "repo"
    ops = repo / "ops"
    ops.mkdir(parents=True)
    backend = repo / "backend"
    backend.mkdir(parents=True)
    # Deliberately omit Dockerfile.v2, requirements-v2.txt, .dockerignore,
    # docker-entrypoint-v2.sh, and sealai_v2/ entirely.
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Gate Test")
    _git(repo, "config", "user.email", "gate-test@example.invalid")
    (ops / "production-release-state.json").write_text(
        json.dumps(_state(active=True)) + "\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "incomplete source commit")
    monkeypatch.setattr(gate, "REPO_ROOT", repo)

    with pytest.raises(
        gate.GateConfigurationError,
        match="cannot stage the real release artifact for hashing",
    ):
        gate._served_tree_sha256()


def test_status_document_lists_source_derived_verifiers_as_registered():
    # Not a manifest field -- a targeted regression guard that the registry itself
    # stays wired to exactly these four fields, no silent drift.
    assert set(gate._SOURCE_DERIVED_HASH_VERIFIERS) == {
        "served_tree_sha256",
        "database_migration_sha256",
        "rollback_plan_sha256",
        "evidence_manifest_sha256",
    }


def test_gate10_lift_implemented_is_still_false():
    assert gate.GATE10_LIFT_IMPLEMENTED is False
