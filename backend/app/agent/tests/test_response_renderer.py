"""
Tests for runtime/response_renderer.py — Phase F-A.3

Covers Umbauplan F-A.3:
  test_outward_contract_strips_uuids
  test_outward_contract_strips_governance_enums
  test_outward_contract_preserves_technical_values
  test_outward_contract_preserves_assumptions
  test_sse_chunks_filtered
  test_non_streaming_filtered
"""
from __future__ import annotations

import pytest

from app.agent.runtime.response_renderer import (
    RenderedResponse,
    _structural_scrub,
    render_chunk,
    render_response,
)


# ---------------------------------------------------------------------------
# _structural_scrub unit tests
# ---------------------------------------------------------------------------

class TestStructuralScrub:
    # ── UUID removal ────────────────────────────────────────────────────────

    def test_strips_uuid_v4(self):
        text = "Trace ID: 550e8400-e29b-41d4-a716-446655440000 — result follows."
        result = _structural_scrub(text)
        assert "550e8400" not in result
        assert "result follows" in result

    def test_strips_multiple_uuids(self):
        text = (
            "session=123e4567-e89b-12d3-a456-426614174000 "
            "case=987fbc97-4bed-5078-9f07-9941598255b3 OK"
        )
        result = _structural_scrub(text)
        assert "123e4567" not in result
        assert "987fbc97" not in result
        assert "OK" in result

    def test_uuid_adjacent_text_preserved(self):
        text = "Ergebnis (ID: 550e8400-e29b-41d4-a716-446655440000): FKM geeignet."
        result = _structural_scrub(text)
        assert "Ergebnis" in result
        assert "FKM geeignet" in result

    # ── Governance / state enum removal ─────────────────────────────────────

    def test_strips_governance_enum(self):
        text = "Status [governance:CLASS_B] — Anfrage qualifiziert."
        result = _structural_scrub(text)
        assert "[governance:" not in result
        assert "Anfrage qualifiziert" in result

    def test_strips_state_enum(self):
        text = "Zustand [state:NORMALIZED] verarbeitet."
        result = _structural_scrub(text)
        assert "[state:" not in result
        assert "verarbeitet" in result

    def test_strips_prompt_hash_tag(self):
        text = "Antwort generiert [prompt_hash:abc123def456] — Ende."
        result = _structural_scrub(text)
        assert "[prompt_hash:" not in result
        assert "Antwort generiert" in result

    def test_strips_version_tag(self):
        text = "Modell [version:v2.3.1] aktiv."
        result = _structural_scrub(text)
        assert "[version:" not in result

    def test_strips_hash_tag(self):
        text = "Signatur [hash:deadbeef1234] verifiziert."
        result = _structural_scrub(text)
        assert "[hash:" not in result

    def test_strips_trace_id_tag(self):
        text = "Anfrage [trace_id:xyz-987] abgeschlossen."
        result = _structural_scrub(text)
        assert "[trace_id:" not in result

    def test_strips_node_tag(self):
        text = "Verarbeitung [node:finalize_node] beendet."
        result = _structural_scrub(text)
        assert "[node:" not in result

    # ── Internal field-name prefixes ─────────────────────────────────────────

    def test_strips_sealing_state_prefix(self):
        text = "sealing_state: {'asserted': {'medium': 'Wasser'}} — OK"
        result = _structural_scrub(text)
        assert "sealing_state:" not in result

    def test_strips_asserted_state_prefix(self):
        text = "asserted_state = {'medium': 'Öl'} — geladen."
        result = _structural_scrub(text)
        assert "asserted_state" not in result

    def test_strips_system_governed_output_prefix(self):
        text = "system.governed_output: 'FKM empfohlen'"
        result = _structural_scrub(text)
        assert "system.governed_output" not in result

    # ── Internal JSON blob removal ────────────────────────────────────────────

    def test_strips_internal_json_blob(self):
        import json
        blob = json.dumps({
            "sealing_state": {"asserted": {}},
            "working_profile": {"medium": "Dampf"},
        })
        text = f"Analyse: {blob} — Ergebnis: OK"
        result = _structural_scrub(text)
        assert "sealing_state" not in result
        assert "Ergebnis: OK" in result

    def test_preserves_non_internal_json(self):
        blob = '{"temperature": 180, "pressure": 50, "material": "FKM"}'
        text = f"Parameter: {blob}"
        result = _structural_scrub(text)
        # Non-internal JSON (no internal keys) should pass through
        assert "temperature" in result or "Parameter" in result

    # ── Preservation of legitimate content ───────────────────────────────────

    def test_preserves_technical_values(self):
        text = "Betriebstemperatur: 180 °C, Druck: 50 bar, Wellendurchmesser: 35 mm."
        result = _structural_scrub(text)
        assert "180 °C" in result
        assert "50 bar" in result
        assert "35 mm" in result

    def test_preserves_material_names(self):
        text = "FKM eignet sich für Temperaturen bis 200 °C."
        result = _structural_scrub(text)
        assert "FKM" in result
        assert "200 °C" in result

    def test_preserves_assumptions_text(self):
        text = (
            "Annahme: Betrieb unter atmosphärischem Druck. "
            "Gültigkeitsgrenze: max. 180 °C Dauertemperatur."
        )
        result = _structural_scrub(text)
        assert "Annahme" in result
        assert "Gültigkeitsgrenze" in result

    def test_preserves_disclaimer_text(self):
        text = (
            "Hinweis: Diese Auslegung ist keine Herstellerfreigabe. "
            "Alle Angaben ohne Gewähr."
        )
        result = _structural_scrub(text)
        assert "Hinweis" in result
        assert "ohne Gewähr" in result

    def test_clean_text_unchanged(self):
        text = "O-Ringe sind Dichtelemente mit kreisförmigem Querschnitt."
        result = _structural_scrub(text)
        assert result == text

    def test_empty_string(self):
        assert _structural_scrub("") == ""

    def test_whitespace_only(self):
        # _structural_scrub no longer strips outer whitespace — that is the
        # responsibility of render_response (full text), not render_chunk (tokens).
        # A whitespace-only input passes through unchanged so that leading spaces
        # on streaming tokens (e.g. " world") are preserved.
        assert _structural_scrub("   \n\n  ") == "   \n\n  "


# ---------------------------------------------------------------------------
# render_response — non-streaming (Umbauplan test_non_streaming_filtered)
# ---------------------------------------------------------------------------

class TestRenderResponse:
    def test_outward_contract_strips_uuids(self):
        raw = "Trace 550e8400-e29b-41d4-a716-446655440000: Dichtung FKM."
        result = render_response(raw, path="GOVERNED")
        assert "550e8400" not in result.text
        assert "FKM" in result.text
        assert result.was_scrubbed is True

    def test_outward_contract_strips_governance_enums(self):
        raw = "Klasse [governance:CLASS_B] wurde ermittelt."
        result = render_response(raw, path="GOVERNED")
        assert "[governance:" not in result.text
        assert result.was_scrubbed is True

    def test_outward_contract_preserves_technical_values(self):
        raw = "Betriebstemperatur 180 °C, Druck 50 bar, Material FKM."
        result = render_response(raw, path="GOVERNED")
        assert "180 °C" in result.text
        assert "50 bar" in result.text
        assert result.policy_violation is None

    def test_outward_contract_preserves_assumptions(self):
        raw = "Annahme: atmosphärischer Druck. Gültigkeitsgrenze: 200 °C."
        result = render_response(raw, path="GOVERNED")
        assert "Annahme" in result.text
        assert "200 °C" in result.text

    def test_outward_contract_strips_unnecessary_integerish_float_suffixes(self):
        raw = "Betriebsdruck: 2.0 bar, Betriebstemperatur: 59.0 °C."
        result = render_response(raw, path="GOVERNED")
        assert "2.0 bar" not in result.text
        assert "59.0 °C" not in result.text
        assert "2 bar" in result.text
        assert "59 °C" in result.text

    def test_outward_contract_keeps_non_integer_decimals(self):
        raw = "Betriebsdruck: 2.5 bar, Temperaturfenster bis 59.5 °C."
        result = render_response(raw, path="GOVERNED")
        assert "2.5 bar" in result.text
        assert "59.5 °C" in result.text

    def test_governed_path_skips_content_policy_check(self):
        """Governed output is deterministic — content policy guard NOT applied."""
        # This text would fail output_guard but comes from governed (deterministic) path
        raw = "FKM ist bestens geeignet für 180 °C Dampf."
        result = render_response(raw, path="GOVERNED")
        # The text passes through — governed path doesn't apply output_guard
        assert result.policy_violation is None
        assert "FKM" in result.text

    def test_conversation_path_applies_content_policy(self):
        """Fast-path LLM output is checked by output_guard."""
        from app.agent.agent.output_guard import FAST_PATH_GUARD_FALLBACK
        raw = "Ich empfehle FKM für diese Anwendung."
        result = render_response(raw, path="CONVERSATION")
        assert result.policy_violation is not None
        assert result.text == FAST_PATH_GUARD_FALLBACK

    @pytest.mark.parametrize(
        "raw",
        [
            "Die Requirement Class ist PTFE10.",
            "Das Matching ist bereits erfolgt.",
            "Die Anfragebasis ist RFQ-ready.",
        ],
    )
    def test_conversational_answer_blocks_requirement_class_matching_and_rfq_readiness_language(self, raw):
        from app.agent.agent.output_guard import FAST_PATH_GUARD_FALLBACK

        result = render_response(raw, path="CONVERSATION")

        assert result.policy_violation is not None
        assert result.text == FAST_PATH_GUARD_FALLBACK

    def test_conversation_path_clean_text_passes(self):
        raw = "Ein O-Ring ist ein ringförmiges Dichtelement."
        result = render_response(raw, path="CONVERSATION")
        assert result.text == raw
        assert result.policy_violation is None
        assert result.was_scrubbed is False

    def test_rendered_response_is_frozen(self):
        result = render_response("Hallo", path="CONVERSATION")
        with pytest.raises((AttributeError, TypeError)):
            result.text = "changed"  # type: ignore[misc]

    def test_path_recorded_on_result(self):
        result = render_response("Text", path="GOVERNED")
        assert result.path == "GOVERNED"

    def test_both_uuid_and_enum_stripped(self):
        raw = (
            "Anfrage [governance:CLASS_A] mit ID "
            "123e4567-e89b-12d3-a456-426614174000 verarbeitet."
        )
        result = render_response(raw, path="GOVERNED")
        assert "[governance:" not in result.text
        assert "123e4567" not in result.text
        assert "verarbeitet" in result.text


# ---------------------------------------------------------------------------
# render_chunk — SSE streaming (Umbauplan test_sse_chunks_filtered)
# ---------------------------------------------------------------------------

class TestRenderChunk:
    def test_sse_chunks_filtered_uuid(self):
        chunk = "ID: 550e8400-e29b-41d4-a716-446655440000"
        result = render_chunk(chunk, path="GOVERNED")
        assert "550e8400" not in result

    def test_sse_chunks_filtered_governance_tag(self):
        chunk = "Klasse [governance:B] "
        result = render_chunk(chunk, path="GOVERNED")
        assert "[governance:" not in result

    def test_sse_chunk_technical_content_preserved(self):
        chunk = "Temperatur: 180 °C, "
        result = render_chunk(chunk, path="GOVERNED")
        assert "180 °C" in result

    def test_sse_chunk_strips_unnecessary_integerish_float_suffixes(self):
        chunk = "Druck: 2.0 bar, Temperatur: 59.0 °C"
        result = render_chunk(chunk, path="GOVERNED")
        assert "2.0 bar" not in result
        assert "59.0 °C" not in result
        assert "2 bar" in result
        assert "59 °C" in result

    def test_sse_chunk_clean_passes_through(self):
        chunk = "FKM hat eine hohe Temperaturbeständigkeit."
        result = render_chunk(chunk, path="CONVERSATION")
        assert result == chunk

    def test_sse_chunk_empty_string(self):
        assert render_chunk("", path="GOVERNED") == ""

    def test_sse_chunk_returns_string(self):
        result = render_chunk("Hallo Welt", path="CONVERSATION")
        assert isinstance(result, str)

    def test_sse_chunk_governed_path_no_policy_check(self):
        """Chunks are not checked by output_guard — tokens are not meaningful alone."""
        # "empfehle" alone in a chunk should NOT trigger fallback substitution for chunks
        chunk = "empfehle"
        result = render_chunk(chunk, path="CONVERSATION")
        # render_chunk does NOT apply output_guard, so "empfehle" passes through
        assert result == chunk

    def test_sse_chunk_preserves_leading_whitespace(self):
        """Leading space on tokens must NOT be stripped (OpenAI tokenizes 'world' as ' world')."""
        result = render_chunk(" world", path="CONVERSATION")
        assert result == " world"

    def test_sse_chunk_strips_multiple_artifacts(self):
        chunk = "[state:NORM] abc12345-1234-1234-1234-123456789abc "
        result = render_chunk(chunk, path="GOVERNED")
        assert "[state:" not in result
        assert "abc12345" not in result


# ---------------------------------------------------------------------------
# Integration: render_response produces RenderedResponse correctly
# ---------------------------------------------------------------------------

class TestRenderedResponseContract:
    def test_was_scrubbed_false_for_clean_text(self):
        result = render_response("Was ist PTFE?", path="CONVERSATION")
        assert result.was_scrubbed is False
        assert result.policy_violation is None

    def test_was_scrubbed_true_when_artifact_removed(self):
        result = render_response(
            "ID 550e8400-e29b-41d4-a716-446655440000 — fertig",
            path="GOVERNED",
        )
        assert result.was_scrubbed is True

    def test_policy_violation_none_for_governed(self):
        result = render_response("Ergebnis: FKM.", path="GOVERNED")
        assert result.policy_violation is None

    def test_policy_violation_set_for_conversation_violation(self):
        raw = "Ich empfehle NBR für diese Dichtung."
        result = render_response(raw, path="CONVERSATION")
        assert result.policy_violation in (
            "recommendation", "manufacturer", "suitability"
        )
