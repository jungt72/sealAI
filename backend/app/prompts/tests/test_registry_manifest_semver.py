from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import UndefinedError

from app.prompts.registry import PromptRegistry


@pytest.fixture(autouse=True)
def _reset_prompt_registry_singleton() -> None:
    PromptRegistry._instance = None
    yield
    PromptRegistry._instance = None


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_manifest_default_semver_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "prompts"
    _write(base / "_manifest.yml", "prompts:\n  greeting/system:\n    default: '1.2.3'\n")
    _write(base / "greeting" / "system_1.2.3.j2", "Hello {{ name }}")

    monkeypatch.setenv("SEALAI_PROMPT_DIR", str(base))
    registry = PromptRegistry(base_dir=str(base))

    content, fp, ver = registry.render("greeting/system", {"name": "Ada"})

    assert content == "Hello Ada"
    assert fp
    assert ver == "1.2.3"


def test_semver_falls_back_to_legacy_major(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "prompts"
    _write(base / "_manifest.yml", "prompts:\n  greeting/system:\n    default: '1.0.0'\n")
    _write(base / "greeting" / "system_v1.j2", "Legacy {{ who }}")

    monkeypatch.setenv("SEALAI_PROMPT_DIR", str(base))
    registry = PromptRegistry(base_dir=str(base))

    content, _, ver = registry.render("greeting/system", {"who": "path"})

    assert content == "Legacy path"
    assert ver == "v1"


def test_backward_compatible_explicit_legacy_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "prompts"
    _write(base / "greeting" / "reply_v1.j2", "Reply {{ value }}")

    monkeypatch.setenv("SEALAI_PROMPT_DIR", str(base))
    registry = PromptRegistry(base_dir=str(base))

    content, _, ver = registry.render("greeting/reply_v1", {"value": "ok"})

    assert content == "Reply ok"
    assert ver == "v1"


def test_render_is_strict_undefined(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = tmp_path / "prompts"
    _write(base / "greeting" / "system_1.0.0.j2", "Hello {{ missing_var }}")

    monkeypatch.setenv("SEALAI_PROMPT_DIR", str(base))
    registry = PromptRegistry(base_dir=str(base))

    with pytest.raises(UndefinedError):
        registry.render("greeting/system_1.0.0", {})
