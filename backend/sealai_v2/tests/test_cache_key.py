"""Phase 1 (LangGraph-suitability audit) — hash-based prompt-cache key construction tests."""

from __future__ import annotations

from sealai_v2.llm.cache_key import (
    build_prompt_cache_key,
    normalize_prompt,
    static_prompt_hash,
)

_SYNTHETIC_TENANT = "tenant-musterfirma-42"
_SYNTHETIC_CASE = "case-2026-07-08-XYZ"
_SYNTHETIC_USER = "user-jane-doe"
_SYNTHETIC_SESSION = "session-abc123"
_SYNTHETIC_DATE = "2026-07-08"
_SYNTHETIC_CUSTOMER_TEXT = "Kunde Musterfirma Dichtungstechnik GmbH, Zeichnung xyz.pdf"


class TestSamePromptSameKey:
    def test_identical_static_prompt_yields_identical_key(self) -> None:
        prompt = "You are sealingAI. Never invent a value."
        k1 = build_prompt_cache_key("l1", "gpt-5.1", prompt)
        k2 = build_prompt_cache_key("l1", "gpt-5.1", prompt)
        assert k1 == k2

    def test_cosmetic_trailing_whitespace_does_not_change_the_key(self) -> None:
        k1 = build_prompt_cache_key("l1", "gpt-5.1", "line one\nline two")
        k2 = build_prompt_cache_key("l1", "gpt-5.1", "line one  \nline two\n\n")
        assert k1 == k2


class TestChangedPromptDifferentKey:
    def test_changed_static_prompt_yields_different_key(self) -> None:
        k1 = build_prompt_cache_key("l1", "gpt-5.1", "doctrine version A")
        k2 = build_prompt_cache_key("l1", "gpt-5.1", "doctrine version B")
        assert k1 != k2

    def test_changed_stage_yields_different_key(self) -> None:
        prompt = "same text"
        k1 = build_prompt_cache_key("l1", "gpt-5.1", prompt)
        k2 = build_prompt_cache_key("verifier", "gpt-5.1", prompt)
        assert k1 != k2

    def test_changed_model_yields_different_key(self) -> None:
        prompt = "same text"
        k1 = build_prompt_cache_key("l1", "gpt-5.1", prompt)
        k2 = build_prompt_cache_key("l1", "mistral-large-latest", prompt)
        assert k1 != k2


class TestKeyFormat:
    def test_matches_target_format(self) -> None:
        key = build_prompt_cache_key("l1", "gpt-5.1", "doctrine text")
        parts = key.split(":")
        assert parts[0] == "sealai"
        assert parts[1] == "global"
        assert parts[2] == "l1"
        assert parts[3] == "gpt-5.1"
        assert len(parts[4]) == 16  # static_prompt_hash length
        int(parts[4], 16)  # must be valid hex


class TestNoSensitiveDataInKey:
    def test_key_never_contains_raw_prompt_content(self) -> None:
        key = build_prompt_cache_key("l1", "gpt-5.1", _SYNTHETIC_CUSTOMER_TEXT)
        assert "Musterfirma" not in key
        assert "Kunde" not in key
        assert "xyz.pdf" not in key

    def test_key_never_contains_tenant_case_user_session_or_date(self) -> None:
        # A caller must never pass per-turn dynamic data as the "static_prompt" — this test proves
        # that even if such a string SNUCK in, its hash never re-exposes the raw substrings, and
        # the key's only literal components are the caller-controlled stage/model labels.
        dynamic_looking_text = (
            f"tenant={_SYNTHETIC_TENANT} case={_SYNTHETIC_CASE} user={_SYNTHETIC_USER} "
            f"session={_SYNTHETIC_SESSION} date={_SYNTHETIC_DATE}"
        )
        key = build_prompt_cache_key("l1", "gpt-5.1", dynamic_looking_text)
        for needle in (
            _SYNTHETIC_TENANT,
            _SYNTHETIC_CASE,
            _SYNTHETIC_USER,
            _SYNTHETIC_SESSION,
            _SYNTHETIC_DATE,
        ):
            assert needle not in key

    def test_stage_and_model_labels_are_the_only_plaintext_segments(self) -> None:
        key = build_prompt_cache_key("l1", "gpt-5.1", "anything")
        # everything after the 4th colon-segment is opaque hex — no further plaintext
        prefix = "sealai:global:l1:gpt-5.1:"
        assert key.startswith(prefix)
        suffix = key[len(prefix) :]
        assert suffix.isalnum()


class TestNormalizeAndHashHelpers:
    def test_normalize_prompt_strips_trailing_whitespace_per_line(self) -> None:
        assert normalize_prompt("a  \nb\t\n") == "a\nb"

    def test_normalize_prompt_drops_trailing_blank_lines(self) -> None:
        assert normalize_prompt("a\nb\n\n\n") == "a\nb"

    def test_static_prompt_hash_is_deterministic(self) -> None:
        assert static_prompt_hash("x") == static_prompt_hash("x")

    def test_static_prompt_hash_changes_with_content(self) -> None:
        assert static_prompt_hash("x") != static_prompt_hash("y")


# --- build_pipeline() wiring: confirm the real L1 ModelConfig uses the new hash-based key ---

from sealai_v2.config.settings import Settings
from sealai_v2.pipeline.pipeline import build_pipeline
from sealai_v2.tests._fakes import FakeLlmClient


def test_build_pipeline_wires_l1_with_hash_based_cache_key_and_stage() -> None:
    p = build_pipeline(Settings(), FakeLlmClient("x"))
    l1_cache_key = p.generator._model_config.cache_key
    assert l1_cache_key.startswith("sealai:global:l1:")
    assert p.generator._model_config.stage == "l1"
    # not the old literal anymore
    assert l1_cache_key != "sealai-v2-l1"


def test_build_pipeline_helper_key_unchanged_literal_but_now_labeled() -> None:
    """Phase 1 deliberately leaves the helper/verifier cache keys as literals this phase (no clean
    static-only prompt available without a prompt split) — only the stage label is new."""
    p = build_pipeline(Settings(), FakeLlmClient("x"))
    assert p.helper_model.cache_key == "sealai-v2-helper"
    assert p.helper_model.stage == "helper"


def test_build_pipeline_verifier_key_unchanged_literal_but_now_labeled() -> None:
    p = build_pipeline(Settings(), FakeLlmClient("x"))
    assert p.verifier is not None
    assert p.verifier._model_config.cache_key == "sealai-v2-verifier"
    assert p.verifier._model_config.stage == "verifier"


def test_l1_cache_key_changes_when_flags_default_changes() -> None:
    """Proves the hash genuinely reflects the static doctrine text: a settings change that alters
    the STATIC doctrine prompt (default_compliance_hint) must roll the L1 cache key."""
    on = build_pipeline(Settings(default_compliance_hint=True), FakeLlmClient("x"))
    off = build_pipeline(Settings(default_compliance_hint=False), FakeLlmClient("x"))
    assert on.generator._model_config.cache_key != off.generator._model_config.cache_key
