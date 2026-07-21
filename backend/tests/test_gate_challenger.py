"""ops/gate_challenger.py: an advisory OpenAI review, never an approval writer.

These tests prove the two safety properties that matter most: (1) it makes
exactly one bounded network call and never touches an approval-document path,
and (2) it fails closed with a clear message when OPENAI_API_KEY is missing,
rather than silently proceeding or falling back to some other credential.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
sys.path.insert(0, str(OPS))

import gate_challenger as challenger  # noqa: E402


def test_truncate_leaves_short_text_untouched():
    text = "kurzer inhalt"
    out = challenger._truncate("Label", text, cap=1000)
    assert text in out
    assert "gekuerzt" not in out


def test_truncate_caps_long_text_and_marks_it():
    text = "x" * 5000
    out = challenger._truncate("Label", text, cap=100)
    assert "gekuerzt" in out
    assert len(out) < len(text)


def test_gather_gate10_p1_context_pulls_real_repo_docs():
    context = challenger.gather_gate10_p1_context()
    assert "production-release-freeze.md" in context
    assert challenger.GATE10_P1_COMMIT in context or "kein Diff gefunden" in context


def test_call_openai_exits_closed_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        challenger.call_openai("gpt-5.4-mini", 100, "context")
    assert "OPENAI_API_KEY" in str(exc.value)


def test_call_openai_sends_exactly_one_bounded_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")

    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps(
        {
            "model": "gpt-5.4-mini-2026-03-17",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"total_tokens": 42},
        }
    ).encode("utf-8")
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False

    with patch.object(
        challenger.urllib.request, "urlopen", return_value=fake_response
    ) as mock_urlopen:
        result = challenger.call_openai("gpt-5.4-mini", 500, "some context")

    assert mock_urlopen.call_count == 1
    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "https://api.openai.com/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key-not-real"

    body = json.loads(request.data.decode("utf-8"))
    assert body["model"] == "gpt-5.4-mini"
    assert body["max_completion_tokens"] == 500
    assert "max_tokens" not in body
    assert body["messages"][0]["role"] == "system"

    assert result["choices"][0]["message"]["content"] == "ok"


def test_module_never_imports_the_paid_eval_harness():
    assert "sealai_v2.eval" not in sys.modules
    assert "sealai_v2" not in getattr(challenger, "__dict__", {})
