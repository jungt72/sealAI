"""GATE-12 scoped staging-build corridor: additive, narrow, fail-closed.

Structurally identical to GATE-11 (test_gate11_low_risk_emergency.py) in most respects:
every test proves the gate does NOT trust the approval document's own claims about
which paths changed -- it independently diffs base_git_sha..source_git_sha via git
itself. Unlike GATE-11, GATE-12 never authorizes deploy/pull/migration for production
-- only the single staging-build operation -- and its approval carries no
test_evidence_sha256 (it builds a non-production sandbox, not a release).

Owner decision, 2026-07-21: unlike GATE-11, GATE-12 does NOT reject diffs touching
GATE11_EXCLUDED_PATH_PREFIXES (ops/, .github/workflows/, etc.) -- see the docstring on
gate._validate_staging_build_approval for why (staging carries zero production
traffic, so GATE-11's production-self-widening protection doesn't apply here).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
sys.path.insert(0, str(OPS))

import production_release_gate as gate  # noqa: E402


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


def _make_repo_with_diff(
    tmp_path: Path, *, changed_files: dict[str, str]
) -> tuple[Path, str, str]:
    """A base commit with only an unrelated file, then one source commit that adds/
    changes exactly ``changed_files`` (relative path -> content). Returns
    (repo, base_sha, source_sha)."""

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Gate Test")
    _git(repo, "config", "user.email", "gate-test@example.invalid")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base commit")
    base_sha = _git(repo, "rev-parse", "HEAD")

    for relative, content in changed_files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "candidate change")
    source_sha = _git(repo, "rev-parse", "HEAD")
    return repo, base_sha, source_sha


def _approval(
    *,
    base_git_sha: str,
    source_git_sha: str,
    overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    now = gate.dt.datetime.now(gate.dt.timezone.utc).replace(microsecond=0)
    value: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "GATE-12",
        "decision": "APPROVED",
        "scope": "staging-build",
        "approval_id": "gate12-test-001",
        "approved_by": "test-owner",
        "approved_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + gate.dt.timedelta(hours=2))
        .isoformat()
        .replace("+00:00", "Z"),
        "base_git_sha": base_git_sha,
        "source_git_sha": source_git_sha,
        "owner_read_diff_confirmation": True,
    }
    if overrides:
        value.update(overrides)
    return value


def _write_approval(path: Path, approval: dict[str, object]) -> Path:
    path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def test_freeze_blocks_staging_build_without_approval(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"README.md": "changed\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")

    with pytest.raises(gate.GateConfigurationError, match="unavailable"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=tmp_path / "missing.json",
            require_versioned=False,
        )


def test_staging_build_accepts_scoped_docs_and_code_diff(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path,
        changed_files={
            "docs/example.md": "docs change\n",
            "backend/sealai_v2/pipeline/pipeline.py": "# a real code change\n",
        },
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(base_git_sha=base_sha, source_git_sha=source_sha),
    )

    decision = gate.evaluate(
        "staging-build",
        state_path=state_path,
        staging_build_approval_path=approval_path,
        require_versioned=False,
    )

    assert decision.allowed is True
    assert decision.required_gate == "GATE-12"
    assert decision.reason == "gate12_scoped_staging_build_corridor"
    assert decision.source_git_sha == source_sha
    assert decision.base_git_sha == base_sha
    assert decision.approval_id == "gate12-test-001"


@pytest.mark.parametrize(
    "formerly_excluded_path",
    [
        "ops/release-backend-v2.sh",
        "ops/staging/up-staging-v2.sh",
        ".github/workflows/deploy.yml",
        ".claude/settings.json",
        "docker-compose.yml",
        "docker-compose.deploy.yml",
        "backend/sealai_v2/config/settings.py",
        "backend/sealai_v2/security/auth.py",
        "backend/sealai_v2/core/output_guard.py",
        "backend/sealai_v2/db/migrations/versions/x.py",
        "backend/Dockerfile.v2",
        "keycloak/certs/key.pem",
    ],
)
def test_staging_build_accepts_paths_gate11_would_exclude(
    tmp_path: Path, monkeypatch, formerly_excluded_path: str
):
    """Owner decision, 2026-07-21: GATE-12 no longer applies
    GATE11_EXCLUDED_PATH_PREFIXES (see the docstring on
    gate._validate_staging_build_approval for the reasoning -- staging is not
    production-facing, so GATE-11's self-widening protection doesn't apply here).
    Every path that used to be rejected must now be accepted."""

    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path,
        changed_files={
            "docs/example.md": "docs change\n",
            formerly_excluded_path: "ordinary change\n",
        },
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(base_git_sha=base_sha, source_git_sha=source_sha),
    )

    decision = gate.evaluate(
        "staging-build",
        state_path=state_path,
        staging_build_approval_path=approval_path,
        require_versioned=False,
    )

    assert decision.allowed is True


def test_staging_build_ignores_approvals_own_path_claim(tmp_path: Path, monkeypatch):
    """The gate must independently diff base..source -- an approval cannot simply
    assert the excluded path is absent when it is, in fact, present in the diff."""

    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"ops/sneaky.sh": "echo hi\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(
            base_git_sha=base_sha,
            source_git_sha=source_sha,
            overrides={"excluded_paths_confirmed_absent": True},
        ),
    )

    # The extra field is simply rejected by the exact-keys check -- the approval
    # cannot even add a self-assertion field, let alone have it trusted.
    with pytest.raises(gate.GateConfigurationError, match="missing or unexpected"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_rejects_source_mismatch(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(base_git_sha=base_sha, source_git_sha="a" * 40),
    )

    with pytest.raises(gate.GateConfigurationError, match="bound to another commit"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_rejects_non_ancestor_base(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    # A syntactically valid but unrelated 40-hex sha that is not an ancestor.
    fake_base = "b" * 40
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(base_git_sha=fake_base, source_git_sha=source_sha),
    )

    with pytest.raises(gate.GateConfigurationError, match="not an ancestor"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_rejects_empty_commit_range(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(base_git_sha=source_sha, source_git_sha=source_sha),
    )

    with pytest.raises(gate.GateConfigurationError, match="empty commit range"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_rejects_missing_owner_confirmation(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(
            base_git_sha=base_sha,
            source_git_sha=source_sha,
            overrides={"owner_read_diff_confirmation": False},
        ),
    )

    with pytest.raises(gate.GateConfigurationError, match="owner read the diff"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_rejects_expired_approval(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    now = gate.dt.datetime.now(gate.dt.timezone.utc).replace(microsecond=0)
    approval = _approval(base_git_sha=base_sha, source_git_sha=source_sha)
    approval["approved_at"] = (
        (now - gate.dt.timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    )
    approval["expires_at"] = (
        (now - gate.dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    )
    approval_path = _write_approval(tmp_path / "approval.json", approval)

    with pytest.raises(gate.GateConfigurationError, match="expired or over-broad"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_rejects_over_broad_expiry(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    now = gate.dt.datetime.now(gate.dt.timezone.utc).replace(microsecond=0)
    approval = _approval(base_git_sha=base_sha, source_git_sha=source_sha)
    approval["expires_at"] = (
        (now + gate.dt.timedelta(hours=8)).isoformat().replace("+00:00", "Z")
    )
    approval_path = _write_approval(tmp_path / "approval.json", approval)

    with pytest.raises(gate.GateConfigurationError, match="expired or over-broad"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_rejects_wrong_gate_id(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(
            base_git_sha=base_sha,
            source_git_sha=source_sha,
            overrides={"gate_id": "GATE-11"},
        ),
    )

    with pytest.raises(gate.GateConfigurationError, match="staging build corridor"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_rejects_wrong_scope(tmp_path: Path, monkeypatch):
    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(
            base_git_sha=base_sha,
            source_git_sha=source_sha,
            overrides={"scope": "low-risk-emergency-deploy"},
        ),
    )

    with pytest.raises(gate.GateConfigurationError, match="staging build corridor"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_staging_build_never_accepts_test_evidence_field(tmp_path: Path, monkeypatch):
    """GATE-12's schema has no test_evidence_sha256 -- adding GATE-11's field must be
    rejected by the exact-keys check, not silently ignored."""

    repo, base_sha, source_sha = _make_repo_with_diff(
        tmp_path, changed_files={"docs/example.md": "docs change\n"}
    )
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(_state()) + "\n", encoding="utf-8")
    approval_path = _write_approval(
        tmp_path / "approval.json",
        _approval(
            base_git_sha=base_sha,
            source_git_sha=source_sha,
            overrides={"test_evidence_sha256": "a" * 64},
        ),
    )

    with pytest.raises(gate.GateConfigurationError, match="missing or unexpected"):
        gate.evaluate(
            "staging-build",
            state_path=state_path,
            staging_build_approval_path=approval_path,
            require_versioned=False,
        )


def test_status_document_lists_staging_build_operation():
    status = gate._status_document()
    assert status["freeze_staging_build_operation"] == "staging-build"


def test_staging_build_operation_in_operations_set():
    assert gate.STAGING_BUILD_OPERATION in gate.OPERATIONS
    assert gate.STAGING_BUILD_OPERATION not in gate.MUTATING_OPERATIONS


def test_gate11_exclusion_list_is_unaffected_by_the_gate12_change():
    """The 2026-07-21 owner decision only touches GATE-12's own validation function --
    GATE11_EXCLUDED_PATH_PREFIXES and _path_excluded_from_low_risk_corridor still exist
    and still work exactly as before, because GATE-11 (a real production corridor)
    still uses them. This is a regression guard that relaxing GATE-12 never touched the
    shared constant/helper GATE-11 depends on."""

    assert "ops/" in gate.GATE11_EXCLUDED_PATH_PREFIXES
    assert gate._path_excluded_from_low_risk_corridor("ops/staging/up-staging-v2.sh")
