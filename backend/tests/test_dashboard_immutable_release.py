from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "frontend-v2" / "scripts" / "dashboard_release.py"
SPEC = importlib.util.spec_from_file_location(
    "dashboard_release_test_module", TOOL_PATH
)
assert SPEC is not None and SPEC.loader is not None
release_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_tool
SPEC.loader.exec_module(release_tool)

SOURCE_A = "a" * 40
SOURCE_B = "b" * 40
LOCK_SHA = "c" * 64
NODE_VERSION = "v24.15.0"
NPM_VERSION = "11.12.1"


@pytest.fixture
def scratch(tmp_path: Path):
    yield tmp_path
    # Prepared releases are deliberately 0555/0444; restore owner write bits so
    # pytest can remove the temporary tree on both Linux and macOS.
    for current, directories, _files in os.walk(tmp_path, topdown=True):
        try:
            Path(current).chmod(0o700)
        except FileNotFoundError:
            pass
        for name in directories:
            child = Path(current) / name
            if not child.is_symlink():
                try:
                    child.chmod(0o700)
                except FileNotFoundError:
                    pass


def make_candidate(root: Path, marker: str = "one") -> Path:
    candidate = root / "candidate"
    candidate.mkdir(mode=0o755)
    (candidate / "assets").mkdir(mode=0o755)
    (candidate / "index.html").write_text(
        f"<!doctype html><script src='/dashboard/assets/{marker}.js'></script>",
        encoding="utf-8",
    )
    (candidate / "assets" / f"{marker}.js").write_text(
        f"globalThis.marker={marker!r};\n", encoding="utf-8"
    )
    return candidate


def inspect(candidate: Path, source: str = SOURCE_A):
    return release_tool.inspect_candidate(
        candidate,
        source_git_sha=source,
        source_date_epoch=1_700_000_000,
        npm_lock_sha256=LOCK_SHA,
        node_version=NODE_VERSION,
        npm_version=NPM_VERSION,
    )


def prepare(candidate: Path, release_root: Path, source: str = SOURCE_A):
    artifact = inspect(candidate, source)
    release, created = release_tool.prepare_release(candidate, release_root, artifact)
    return artifact, release, created


def test_digest_is_deterministic_and_binds_build_identity(scratch: Path) -> None:
    candidate = make_candidate(scratch)
    first = inspect(candidate)
    os.utime(candidate / "index.html", None)
    assert inspect(candidate) == first

    changed_source = inspect(candidate, SOURCE_B)
    changed_node = release_tool.inspect_candidate(
        candidate,
        source_git_sha=SOURCE_A,
        source_date_epoch=1_700_000_000,
        npm_lock_sha256=LOCK_SHA,
        node_version="v24.16.0",
        npm_version=NPM_VERSION,
    )
    assert changed_source.artifact_sha256 != first.artifact_sha256
    assert changed_node.artifact_sha256 != first.artifact_sha256
    assert first.release_id == f"{SOURCE_A}-{first.artifact_sha256}"
    assert [record.path for record in first.files] == sorted(
        record.path for record in first.files
    )


def test_prepare_creates_inert_immutable_release_with_visible_identity(
    scratch: Path,
) -> None:
    candidate = make_candidate(scratch)
    release_root = scratch / "releases"
    artifact, release, created = prepare(candidate, release_root)

    assert created is True
    assert release == release_root / "artifacts" / artifact.release_id
    assert not (release_root / "current").exists()
    assert not (release_root / "rollback").exists()
    assert stat.S_IMODE(release.stat().st_mode) == 0o555
    assert stat.S_IMODE((release / "index.html").stat().st_mode) == 0o444
    assert stat.S_IMODE((release / "release.json").stat().st_mode) == 0o444
    assert release_tool.verify_release(release) == artifact

    manifest = json.loads((release / "release.json").read_bytes())
    assert manifest["source_git_sha"] == SOURCE_A
    assert manifest["artifact_sha256"] == artifact.artifact_sha256
    assert manifest["release_id"] == artifact.release_id
    assert manifest["npm_lock_sha256"] == LOCK_SHA
    assert manifest["node_version"] == NODE_VERSION
    assert manifest["npm_version"] == NPM_VERSION


def test_prepare_is_idempotent_but_never_clobbers_a_tampered_release(
    scratch: Path,
) -> None:
    candidate = make_candidate(scratch)
    release_root = scratch / "releases"
    artifact, release, created = prepare(candidate, release_root)
    assert created is True
    assert release_tool.prepare_release(candidate, release_root, artifact) == (
        release,
        False,
    )

    release.chmod(0o755)
    manifest = release / "release.json"
    manifest.chmod(0o644)
    original = manifest.read_bytes()
    manifest.write_bytes(original.replace(SOURCE_A.encode(), SOURCE_B.encode(), 1))
    manifest.chmod(0o444)
    release.chmod(0o555)

    with pytest.raises(release_tool.ReleaseError, match="release_no_clobber_conflict"):
        release_tool.prepare_release(candidate, release_root, artifact)
    assert SOURCE_B.encode() in manifest.read_bytes()


def test_existing_partial_release_path_is_preserved_on_collision(scratch: Path) -> None:
    candidate = make_candidate(scratch)
    artifact = inspect(candidate)
    release_root = scratch / "releases"
    collision = release_root / "artifacts" / artifact.release_id
    collision.mkdir(parents=True)
    sentinel = collision / "do-not-overwrite"
    sentinel.write_text("preserved", encoding="utf-8")

    with pytest.raises(release_tool.ReleaseError, match="release_no_clobber_conflict"):
        release_tool.prepare_release(candidate, release_root, artifact)
    assert sentinel.read_text(encoding="utf-8") == "preserved"


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink", "writable"])
def test_candidate_rejects_unsafe_file_topology(
    scratch: Path, unsafe_kind: str
) -> None:
    candidate = make_candidate(scratch)
    target = candidate / "assets" / "one.js"
    if unsafe_kind == "symlink":
        target.unlink()
        outside = scratch / "outside.js"
        outside.write_text("outside", encoding="utf-8")
        target.symlink_to(outside)
    elif unsafe_kind == "hardlink":
        os.link(target, scratch / "second-link.js")
    else:
        target.chmod(0o666)

    with pytest.raises(release_tool.ReleaseError):
        inspect(candidate)


def test_candidate_rejects_reserved_metadata_and_overlapping_release_root(
    scratch: Path,
) -> None:
    candidate = make_candidate(scratch)
    (candidate / "release.json").write_text("{}", encoding="utf-8")
    with pytest.raises(release_tool.ReleaseError, match="reserved_candidate_path"):
        inspect(candidate)
    (candidate / "release.json").unlink()
    artifact = inspect(candidate)
    with pytest.raises(
        release_tool.ReleaseError, match="candidate_release_path_overlap"
    ):
        release_tool.prepare_release(candidate, candidate / "releases", artifact)


def test_candidate_and_release_roots_must_not_be_symlinks(scratch: Path) -> None:
    candidate = make_candidate(scratch)
    candidate_link = scratch / "candidate-link"
    candidate_link.symlink_to(candidate, target_is_directory=True)
    with pytest.raises(release_tool.ReleaseError, match="unsafe_candidate_root"):
        inspect(candidate_link)

    artifact = inspect(candidate)
    actual_release_root = scratch / "actual-releases"
    actual_release_root.mkdir()
    release_root_link = scratch / "release-root-link"
    release_root_link.symlink_to(actual_release_root, target_is_directory=True)
    with pytest.raises(release_tool.ReleaseError, match="unsafe_release_root"):
        release_tool.prepare_release(candidate, release_root_link, artifact)


def test_verifier_rejects_unmanifested_directory_and_path_identity_drift(
    scratch: Path,
) -> None:
    candidate = make_candidate(scratch)
    release_root = scratch / "releases"
    _artifact, release, _created = prepare(candidate, release_root)

    release.chmod(0o755)
    (release / "empty-extra").mkdir(mode=0o555)
    release.chmod(0o555)
    with pytest.raises(release_tool.ReleaseError, match="release_file_set_mismatch"):
        release_tool.verify_release(release)
    release.chmod(0o755)
    (release / "empty-extra").rmdir()
    release.chmod(0o555)

    renamed = release.with_name(f"{SOURCE_A}-{'d' * 64}")
    release.rename(renamed)
    with pytest.raises(
        release_tool.ReleaseError, match="release_path_identity_mismatch"
    ):
        release_tool.verify_release(renamed)


def test_plans_are_read_only_and_require_gate_08(scratch: Path) -> None:
    candidate = make_candidate(scratch)
    release_root = scratch / "releases"
    artifact, _release, _created = prepare(candidate, release_root)

    before = sorted(path.name for path in release_root.iterdir())
    plan = release_tool.activation_plan(release_root, artifact.release_id)
    after = sorted(path.name for path in release_root.iterdir())
    assert plan["gate_required"] == "GATE-08"
    assert plan["mutation_performed"] is False
    assert plan["action"] == "activate"
    assert plan["current_target"] is None
    assert before == after

    absent = scratch / "absent-release-root"
    with pytest.raises(release_tool.ReleaseError):
        release_tool.activation_plan(absent, artifact.release_id)
    assert not absent.exists()

    parser = release_tool._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["activate"])
    with pytest.raises(SystemExit):
        parser.parse_args(["apply"])


def test_atomic_link_primitive_supports_verified_activation_and_rollback(
    scratch: Path,
) -> None:
    candidate = make_candidate(scratch)
    release_root = scratch / "releases"
    first, first_release, _created = prepare(candidate, release_root, SOURCE_A)

    (candidate / "index.html").write_text("second", encoding="utf-8")
    second, second_release, _created = prepare(candidate, release_root, SOURCE_B)
    first_target = f"artifacts/{first.release_id}"
    second_target = f"artifacts/{second.release_id}"

    assert not (release_root / "current").exists()
    release_tool._atomic_set_release_link(release_root, "current", first_target)
    assert (release_root / "current").is_symlink()
    assert os.readlink(release_root / "current") == first_target
    assert (
        release_tool.verify_release(
            release_root / os.readlink(release_root / "current")
        )
        == first
    )

    release_tool._atomic_set_release_link(release_root, "rollback", first_target)
    release_tool._atomic_set_release_link(release_root, "current", second_target)
    rollback = release_tool.rollback_plan(release_root)
    assert rollback["gate_required"] == "GATE-08"
    assert rollback["release_id"] == first.release_id

    # Exercise the documented rollback ordering using snapshotted targets.
    old_current = os.readlink(release_root / "current")
    old_rollback = os.readlink(release_root / "rollback")
    release_tool._atomic_set_release_link(release_root, "rollback", old_current)
    release_tool._atomic_set_release_link(release_root, "current", old_rollback)
    assert (release_root / "current").resolve() == first_release.resolve()
    assert (release_root / "rollback").resolve() == second_release.resolve()


def test_atomic_link_refuses_to_replace_an_unsafe_regular_entry(scratch: Path) -> None:
    candidate = make_candidate(scratch)
    release_root = scratch / "releases"
    artifact, _release, _created = prepare(candidate, release_root)
    current = release_root / "current"
    current.write_text("sentinel", encoding="utf-8")

    with pytest.raises(release_tool.ReleaseError, match="unsafe_current_link"):
        release_tool._atomic_set_release_link(
            release_root, "current", f"artifacts/{artifact.release_id}"
        )
    assert current.read_text(encoding="utf-8") == "sentinel"


def test_dashboard_mount_and_nginx_contract_has_no_mutable_live_dist() -> None:
    production = (ROOT / "docker-compose.deploy.yml").read_text(encoding="utf-8")
    staging = (ROOT / "ops/staging/docker-compose.staging.yml").read_text(
        encoding="utf-8"
    )
    nginx = (ROOT / "nginx/snippets/v2_dashboard.conf").read_text(encoding="utf-8")

    assert (
        "/var/lib/sealai/dashboard-releases:/usr/share/nginx/dashboard-releases:ro"
        in production
    )
    assert "./frontend-v2/dist:/usr/share/nginx/v2-client:ro" not in production
    assert (
        "../../frontend-v2/.build/dashboard-candidate:"
        "/usr/share/nginx/dashboard-releases/current:ro" in staging
    )
    assert "alias /usr/share/nginx/dashboard-releases/current/;" in nginx
    assert "alias /usr/share/nginx/dashboard-releases/current/release.json;" in nginx
    assert 'add_header Cache-Control "no-store" always;' in nginx


def test_build_wrapper_proves_two_builds_before_inert_prepare() -> None:
    wrapper = ROOT / "frontend-v2/scripts/prepare-dashboard-release.sh"
    content = wrapper.read_text(encoding="utf-8")

    install = content.index(" ci --ignore-scripts --no-audit --no-fund")
    first_build = content.index("\nrun_build\n", install)
    first_inspect = content.index('inspect_candidate > "${INSPECTION_ONE}"')
    second_build = content.index("\nrun_build\n", first_inspect)
    second_inspect = content.index('inspect_candidate > "${INSPECTION_TWO}"')
    comparison = content.index("/usr/bin/cmp -s", second_inspect)
    prepare_call = content.rindex('"${RELEASE_TOOL}" prepare')

    assert content.startswith("#!/bin/bash -p\n")
    assert wrapper.stat().st_mode & 0o111
    assert "readonly PATH=" in content
    assert "production_build_forbidden" in content
    assert "vite_env_file_forbidden" in content
    assert '"${FRONTEND_DIR}"/.env.*' in content
    assert "/home/thorsten/sealai" in content
    assert "SOURCE_DATE_EPOCH=" in content
    assert "--source-git-sha" in content
    assert "--npm-lock-sha256" in content
    assert "--node-version" in content
    assert "--npm-version" in content
    assert "NPM_VERSION_FILE=" in content
    assert "npm_version_mismatch" in content
    assert 'live_activation_performed":false' in content
    assert install < first_build < first_inspect < second_build < second_inspect
    assert second_inspect < comparison < prepare_call
    assert '"${RELEASE_TOOL}" activate' not in content
    assert "frontend-v2/dist" not in content
