from __future__ import annotations

from sealai_v2.eval.__main__ import _git_sha, _tree_binding


def test_eval_identity_prefers_candidate_image_environment(monkeypatch) -> None:
    monkeypatch.setenv("SEALAI_EVAL_GIT_SHA", "abc123")
    monkeypatch.setenv("SEALAI_EVAL_TREE_HASH", "tree456")
    monkeypatch.setenv("SEALAI_EVAL_DIRTY", "false")

    assert _git_sha() == "abc123"
    assert _tree_binding() == ("tree456", False)


def test_eval_identity_parses_explicit_dirty_marker(monkeypatch) -> None:
    monkeypatch.setenv("SEALAI_EVAL_TREE_HASH", "tree456")
    monkeypatch.setenv("SEALAI_EVAL_DIRTY", "yes")

    assert _tree_binding() == ("tree456", True)
