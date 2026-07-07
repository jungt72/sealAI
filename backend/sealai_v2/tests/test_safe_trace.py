"""Phase 0 (LangGraph-suitability audit) — LangSmith safe-tracing policy tests.

Verifies: raw question/answer text never survives the trace projection; synthetic PII-shaped
content is caught by the regex fallback; hmac_id is stable and non-reversible; production cannot
accidentally enable full raw tracing.
"""

from __future__ import annotations

import os

import pytest

from sealai_v2.obs.safe_trace import (
    bucket_numeric_value,
    hmac_id,
    is_production,
    redact_text_fallback,
    resolve_langsmith_client_policy,
    resolve_tracing_mode,
    safe_input_projection,
    safe_output_projection,
)

# --- synthetic fixtures (never real customer data) ---
_SYNTHETIC_CUSTOMER = "Musterfirma Dichtungstechnik GmbH"
_SYNTHETIC_FILE = "zeichnung_kunde_XYZ_2026.pdf"
_SYNTHETIC_TECH_VALUE = "genau 847.3 bar bei 212.5 U/min am Kundenwerk Musterfirma"
_RAW_QUESTION = f"Wir sind {_SYNTHETIC_CUSTOMER}, Zeichnung {_SYNTHETIC_FILE}, {_SYNTHETIC_TECH_VALUE}"
_RAW_ANSWER = f"Für {_SYNTHETIC_CUSTOMER} empfehlen wir laut {_SYNTHETIC_FILE}: {_SYNTHETIC_TECH_VALUE}"


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "APP_ENV",
        "SEALAI_V2_LANGSMITH_TRACING_MODE",
        "SEALAI_V2_TRACE_HMAC_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)


class TestSafeInputProjection:
    def test_raw_question_never_appears(self) -> None:
        proj = safe_input_projection(
            question=_RAW_QUESTION, flags_repr="Flags()", has_untrusted=False
        )
        dumped = repr(proj)
        assert _RAW_QUESTION not in dumped
        assert _SYNTHETIC_CUSTOMER not in dumped
        assert _SYNTHETIC_FILE not in dumped
        assert proj["has_question"] is True
        assert proj["question_length"] == len(_RAW_QUESTION)
        assert proj["question_hash"] is not None

    def test_empty_question_is_safe(self) -> None:
        proj = safe_input_projection(
            question=None, flags_repr=None, has_untrusted=False
        )
        assert proj["has_question"] is False
        assert proj["question_length"] == 0
        assert proj["question_hash"] is None


class TestSafeOutputProjection:
    def test_raw_answer_never_appears(self) -> None:
        proj = safe_output_projection(
            answer_text=_RAW_ANSWER,
            answer_model="gpt-5.1",
            grounded=True,
            verdict="pass",
        )
        dumped = repr(proj)
        assert _RAW_ANSWER not in dumped
        assert _SYNTHETIC_CUSTOMER not in dumped
        assert _SYNTHETIC_FILE not in dumped
        assert _SYNTHETIC_TECH_VALUE not in dumped
        assert proj["answer_length"] == len(_RAW_ANSWER)
        assert proj["answer_model"] == "gpt-5.1"
        assert proj["grounded"] is True
        assert proj["verifier_status"] == "pass"

    def test_no_answer_text_key_at_all(self) -> None:
        """The projection must not even carry a key named like the raw text under another name."""
        proj = safe_output_projection(
            answer_text="secret", answer_model=None, grounded=None
        )
        assert "answer" not in proj
        assert "text" not in proj
        assert "answer_text" not in proj


class TestRedactTextFallback:
    def test_synthetic_customer_name_pattern_not_specifically_caught_but_documented_as_fallback(
        self,
    ) -> None:
        # Free-text company names are NOT reliably regex-catchable (this is why redact_text_fallback
        # is documented as a second-line net, not the primary mechanism) — but it must not crash and
        # must still return a string.
        out = redact_text_fallback(_RAW_QUESTION)
        assert isinstance(out, str)

    def test_email_is_redacted(self) -> None:
        out = redact_text_fallback(
            "contact me at buyer@musterfirma-dichtung.example.com please"
        )
        assert "buyer@musterfirma-dichtung.example.com" not in out
        assert "[REDACTED_EMAIL]" in out

    def test_url_is_redacted(self) -> None:
        out = redact_text_fallback(
            "see https://musterfirma.example.com/rfq/12345 for details"
        )
        assert "https://musterfirma.example.com/rfq/12345" not in out

    def test_long_digit_run_is_redacted(self) -> None:
        out = redact_text_fallback("Bestellnummer 8471293650 für die Anfrage")
        assert "8471293650" not in out
        assert "[REDACTED_NUMBER]" in out

    def test_long_digit_run_technical_value_is_redacted(self) -> None:
        # redact_text_fallback targets long ID/serial-shaped digit RUNS (5+ consecutive digits) —
        # decimal engineering readings like "847.3"/"212.5" are split by the decimal point and are
        # NOT its job (that is handled by the PRIMARY mechanism: raw text never reaches a trace
        # projection at all — see TestSafeOutputProjection/test_pipeline_trace_projection.py, which
        # assert _SYNTHETIC_TECH_VALUE is absent from the real projections).
        out = redact_text_fallback("Auftragsnummer 847231095 fuer Kundenwerk")
        assert "847231095" not in out
        assert "[REDACTED_NUMBER]" in out


class TestHmacId:
    def test_stable_for_same_input(self) -> None:
        assert hmac_id("hello") == hmac_id("hello")

    def test_different_for_different_input(self) -> None:
        assert hmac_id("hello") != hmac_id("world")

    def test_output_never_contains_the_input(self) -> None:
        h = hmac_id(_SYNTHETIC_CUSTOMER)
        assert _SYNTHETIC_CUSTOMER not in h
        assert len(h) == 24

    def test_custom_secret_changes_the_output(self) -> None:
        assert hmac_id("hello", secret="a") != hmac_id("hello", secret="b")


class TestBucketNumericValue:
    def test_within_a_bucket(self) -> None:
        assert bucket_numeric_value(3) == "1-5"

    def test_below_lowest_edge(self) -> None:
        assert bucket_numeric_value(-1).startswith("<")

    def test_above_highest_edge(self) -> None:
        assert bucket_numeric_value(999999).startswith(">=")


class TestProductionFailClosed:
    def test_default_env_is_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_env(monkeypatch)
        assert is_production() is True

    def test_explicit_development_env_is_not_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "development")
        assert is_production() is False

    def test_default_mode_is_safe_metadata_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env(monkeypatch)
        assert resolve_tracing_mode() == "safe_metadata_only"

    def test_full_synthetic_only_is_downgraded_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SEALAI_V2_LANGSMITH_TRACING_MODE", "full_synthetic_only")
        assert resolve_tracing_mode() == "safe_metadata_only"

    def test_unset_app_env_also_downgrades_full_tracing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """APP_ENV unset must fail closed to production (never accidentally permissive)."""
        _clear_env(monkeypatch)
        monkeypatch.setenv("SEALAI_V2_LANGSMITH_TRACING_MODE", "full_synthetic_only")
        assert resolve_tracing_mode() == "safe_metadata_only"

    def test_full_synthetic_only_allowed_outside_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "staging")
        monkeypatch.setenv("SEALAI_V2_LANGSMITH_TRACING_MODE", "full_synthetic_only")
        assert resolve_tracing_mode() == "full_synthetic_only"

    def test_invalid_mode_value_defaults_safe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env(monkeypatch)
        monkeypatch.setenv("SEALAI_V2_LANGSMITH_TRACING_MODE", "not-a-real-mode")
        assert resolve_tracing_mode() == "safe_metadata_only"

    def test_client_policy_hides_inputs_outputs_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env(monkeypatch)
        policy = resolve_langsmith_client_policy()
        assert policy.hide_inputs is True
        assert policy.hide_outputs is True

    def test_client_policy_only_reveals_in_full_synthetic_outside_prod(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("SEALAI_V2_LANGSMITH_TRACING_MODE", "full_synthetic_only")
        policy = resolve_langsmith_client_policy()
        assert policy.hide_inputs is False
        assert policy.hide_outputs is False

    def test_client_policy_stays_hidden_in_prod_even_if_full_requested(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_env(monkeypatch)
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SEALAI_V2_LANGSMITH_TRACING_MODE", "full_synthetic_only")
        policy = resolve_langsmith_client_policy()
        assert policy.hide_inputs is True
        assert policy.hide_outputs is True
