from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[2] / "ops" / "check-secret-hygiene.py"
    spec = importlib.util.spec_from_file_location("secret_hygiene", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sensitive_key_classifier_uses_token_boundaries() -> None:
    pattern = _module().ENV_SENSITIVE_KEY_RE

    assert pattern.search("PAPERLESS_TOKEN")
    assert pattern.search("OPENAI_API_KEY")
    assert pattern.search("POSTGRES_PASSWORD")
    assert not pattern.search("SEALAI_V2_EVAL_JUDGE_MAX_OUTPUT_TOKENS")
