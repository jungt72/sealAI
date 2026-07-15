from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "ops" / "resolve-secret-scan-range.py"
SCANNER = ROOT / "ops" / "check-secret-hygiene.py"
ZERO = "0" * 40


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def commit(repo: Path, name: str) -> str:
    (repo / "content.txt").write_text(name, encoding="utf-8")
    git(repo, "add", "content.txt")
    git(repo, "commit", "-m", name)
    return git(repo, "rev-parse", "HEAD")


def repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "range-test@example.invalid")
    git(repo, "config", "user.name", "Range Test")
    return repo, commit(repo, "base")


def resolve(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(RESOLVER), "--repo", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def push_args(before: str, after: str, *, ref_name: str = "feature") -> list[str]:
    return [
        "--event",
        "push",
        "--before",
        before,
        "--after",
        after,
        "--default-ref",
        "main",
        "--ref-name",
        ref_name,
        "--default-branch",
        "main",
    ]


def test_fast_forward_push_uses_exact_before_after_range(tmp_path: Path) -> None:
    repo, before = repository(tmp_path)
    git(repo, "checkout", "-b", "feature")
    after = commit(repo, "feature-one")
    result = resolve(repo, *push_args(before, after))
    assert result.returncode == 0
    assert result.stdout.strip() == f"{before}..{after}"


def test_new_branch_uses_authoritative_merge_base(tmp_path: Path) -> None:
    repo, base = repository(tmp_path)
    git(repo, "checkout", "-b", "feature")
    after = commit(repo, "feature-one")
    result = resolve(repo, *push_args(ZERO, after))
    assert result.returncode == 0
    assert result.stdout.strip() == f"{base}..{after}"


def test_force_rebase_scans_only_feature_commits_from_current_main(
    tmp_path: Path,
) -> None:
    repo, _base = repository(tmp_path)
    git(repo, "checkout", "-b", "feature")
    old_tip = commit(repo, "old-feature")
    git(repo, "checkout", "main")
    current_main = commit(repo, "main-advance")
    git(repo, "checkout", "-B", "feature", "main")
    new_tip = commit(repo, "rebased-feature")
    result = resolve(repo, *push_args(old_tip, new_tip))
    assert result.returncode == 0
    assert result.stdout.strip() == f"{current_main}..{new_tip}"
    assert git(repo, "rev-list", result.stdout.strip()).splitlines() == [new_tip]


def test_force_rebase_with_unavailable_before_uses_authoritative_merge_base(
    tmp_path: Path,
) -> None:
    repo, base = repository(tmp_path)
    git(repo, "checkout", "-b", "feature")
    new_tip = commit(repo, "rebased-feature")
    unavailable_old_tip = "1" * 40
    result = resolve(repo, *push_args(unavailable_old_tip, new_tip))
    assert result.returncode == 0
    assert result.stdout.strip() == f"{base}..{new_tip}"


def test_non_fast_forward_main_is_rejected(tmp_path: Path) -> None:
    repo, base = repository(tmp_path)
    old_tip = commit(repo, "main-old")
    git(repo, "reset", "--hard", base)
    new_tip = commit(repo, "main-rewritten")
    result = resolve(repo, *push_args(old_tip, new_tip, ref_name="main"))
    assert result.returncode == 2
    assert result.stdout == ""
    unavailable_before = resolve(repo, *push_args("1" * 40, new_tip, ref_name="main"))
    assert unavailable_before.returncode == 2
    assert unavailable_before.stdout == ""


def test_invalid_or_missing_revision_fails_closed(tmp_path: Path) -> None:
    repo, base = repository(tmp_path)
    result = resolve(repo, *push_args(base, "not-a-revision"))
    assert result.returncode == 2
    after = git(repo, "rev-parse", "HEAD")
    malformed_before = resolve(repo, *push_args("not-a-revision", after))
    assert malformed_before.returncode == 2
    scan = subprocess.run(
        ["python3", str(SCANNER), "--range", "missing..also-missing"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert scan.returncode == 2
    assert "value=" not in scan.stderr


def test_unreachable_default_branch_fails_closed(tmp_path: Path) -> None:
    repo, _base = repository(tmp_path)
    git(repo, "checkout", "--orphan", "unrelated")
    git(repo, "rm", "-f", "content.txt")
    unrelated = commit(repo, "unrelated-root")
    result = resolve(repo, *push_args(ZERO, unrelated))
    assert result.returncode == 2
    assert result.stdout == ""
