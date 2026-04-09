"""Tests fuer den PromptRegistry Singleton (W1.3 / W4.3).

Prueft:
  - PromptRegistry ladbar
  - Alle produktiven Templates renderbar ohne Fehler
  - base.j2 + preselection.j2 korrekt kombiniert
  - Disclaimer in base.j2 vorhanden
  - Singleton-Instanz
  - Unbekannte outward_class faellt zurueck auf conversational
"""

from __future__ import annotations

import pytest

from app.agent.prompts import PromptRegistry, prompts
from app.agent.prompts import PROMPTS_DIR, _RENDERER_TEMPLATE_MAP


# ── Alle bekannten Templates ───────────────────────────────────────────────

ALL_TEMPLATES = [
    "pdf/inquiry.html.j2",
    "pdf/styles.css",
    "renderer/base.j2",
    "renderer/conversational.j2",
    "renderer/clarification.j2",
    "renderer/state_update.j2",
    "renderer/preselection.j2",
    "renderer/candidate_list.j2",
    "renderer/inquiry_ready.j2",
    "gate/gate_classify.j2",
    "intake/observe.j2",
    "exploration/explore.j2",
    "exploration/compare.j2",
    "exploration/detail.j2",
]

# Minimaler Kontext damit StrictUndefined keine Fehler wirft
# (Variablen die in Templates als optional definiert sind muessen trotzdem
#  uebergeben werden, da StrictUndefined auch bei {% if %}-Checks prueft)
_EMPTY_CTX: dict = {}

# Kontext der alle in den Templates verwendeten optionalen Variablen abdeckt
_FULL_CTX: dict = {
    "outward_class": "technical_preselection",
    "allowed_claims": [],
    "forbidden_claims": [],
    "fallback_text": "",
    "missing_params": [],
    "preselection_candidates": [],
    "pv_value": None,
    "requirement_class": None,
    "candidates": [],
    "missing_for_inquiry": [],
    "rag_context": "",
    "topic": "",
    "norm_references": [],
    "candidates": [],
    "user_input": "",
    "case_id": None,
    "created_at": "",
    "basis_hash": "",
    "demand_analysis": [],
    "parameters": [],
    "calculations": [],
    "preselection_items": [],
    "assumptions": [],
    "open_points": [],
    "disclaimer": "",
    "styles_css": "",
}


# ── Singleton ───────────────────────────────────────────────────────────────


class TestSingleton:
    def test_prompts_is_prompt_registry(self):
        assert isinstance(prompts, PromptRegistry)

    def test_singleton_same_object(self):
        from app.agent.prompts import prompts as p2
        assert prompts is p2

    def test_prompts_dir_exists(self):
        assert PROMPTS_DIR.exists(), f"PROMPTS_DIR existiert nicht: {PROMPTS_DIR}"
        assert PROMPTS_DIR.is_dir()


# ── Alle Templates renderbar ────────────────────────────────────────────────


class TestAllTemplatesRenderable:
    @pytest.mark.parametrize("template_path", ALL_TEMPLATES)
    def test_template_exists(self, template_path: str):
        full_path = PROMPTS_DIR / template_path
        assert full_path.exists(), f"Template fehlt: {full_path}"
        assert full_path.is_file()

    @pytest.mark.parametrize("template_path", ALL_TEMPLATES)
    def test_template_renders_without_error(self, template_path: str):
        result = prompts.render(template_path, _FULL_CTX)
        assert isinstance(result, str)
        assert len(result.strip()) > 0, f"Template {template_path} rendert leeren String"

    def test_all_templates_in_list(self):
        templates = prompts.list_templates()
        for expected in ALL_TEMPLATES:
            assert expected in templates, f"Template fehlt in list_templates(): {expected}"


# ── base.j2 Pflichtinhalt ────────────────────────────────────────────────────


class TestBaseTemplate:
    def test_disclaimer_present(self):
        result = prompts.render("renderer/base.j2", _FULL_CTX)
        assert "SeaLAI erstellt eine technische Vorauswahl auf Basis der angegebenen Parameter" in result

    def test_finale_freigabe_hersteller_present(self):
        result = prompts.render("renderer/base.j2", _FULL_CTX)
        assert "Finale Freigabe: Hersteller" in result

    def test_fit_score_rule_present(self):
        result = prompts.render("renderer/base.j2", _FULL_CTX)
        assert "fit_score" in result

    def test_outward_class_rendered_when_provided(self):
        ctx = {**_FULL_CTX, "outward_class": "technical_preselection"}
        result = prompts.render("renderer/base.j2", ctx)
        assert "technical_preselection" in result

    def test_allowed_claims_rendered(self):
        ctx = {**_FULL_CTX, "allowed_claims": ["Claim A", "Claim B"]}
        result = prompts.render("renderer/base.j2", ctx)
        assert "Claim A" in result
        assert "Claim B" in result

    def test_forbidden_claims_rendered(self):
        ctx = {**_FULL_CTX, "forbidden_claims": ["Verboten X"]}
        result = prompts.render("renderer/base.j2", ctx)
        assert "Verboten X" in result

    def test_fallback_text_rendered(self):
        ctx = {**_FULL_CTX, "fallback_text": "Mein Fallback-Hinweis"}
        result = prompts.render("renderer/base.j2", ctx)
        assert "Mein Fallback-Hinweis" in result


# ── renderer_system_prompt: base + class-specific kombiniert ────────────────


class TestRendererSystemPrompt:
    def test_preselection_contains_base_disclaimer(self):
        result = prompts.renderer_system_prompt("technical_preselection", _FULL_CTX)
        assert "Finale Freigabe: Hersteller" in result

    def test_preselection_contains_class_specific_content(self):
        result = prompts.renderer_system_prompt("technical_preselection", _FULL_CTX)
        # preselection.j2 enthaelt "fit_score" im Pflichtbestandteile-Abschnitt
        assert "fit_score" in result

    def test_base_and_class_both_present(self):
        result = prompts.renderer_system_prompt("technical_preselection", _FULL_CTX)
        # Aus base.j2
        assert "SeaLAI erstellt eine technische Vorauswahl" in result
        # Aus preselection.j2
        assert "Technische Vorauswahl" in result

    def test_clarification_contains_class_content(self):
        result = prompts.renderer_system_prompt("structured_clarification", _FULL_CTX)
        assert "Strukturierte Rueckfrage" in result or "Rueckfrage" in result

    def test_conversational_renders(self):
        result = prompts.renderer_system_prompt("conversational_answer", _FULL_CTX)
        assert len(result.strip()) > 0

    def test_inquiry_ready_renders(self):
        result = prompts.renderer_system_prompt("inquiry_ready", _FULL_CTX)
        assert "Inquiry Ready" in result or "Anfrage" in result

    def test_candidate_shortlist_renders(self):
        result = prompts.renderer_system_prompt("candidate_shortlist", _FULL_CTX)
        assert len(result.strip()) > 0

    def test_governed_state_update_renders(self):
        result = prompts.renderer_system_prompt("governed_state_update", _FULL_CTX)
        assert len(result.strip()) > 0

    def test_unknown_outward_class_falls_back_to_conversational(self):
        result = prompts.renderer_system_prompt("unknown_class_xyz", _FULL_CTX)
        # Kein Fehler, faellt auf conversational zurueck
        assert len(result.strip()) > 0
        # base.j2 Disclaimer muss trotzdem drin sein
        assert "Finale Freigabe: Hersteller" in result

    def test_outward_class_injected_into_context(self):
        result = prompts.renderer_system_prompt("technical_preselection", {})
        # outward_class wird automatisch in den Kontext injiziert
        assert "technical_preselection" in result


# ── gate/gate_classify.j2 ───────────────────────────────────────────────────


class TestGateTemplate:
    def test_gate_template_renders(self):
        result = prompts.render("gate/gate_classify.j2", {})
        assert len(result.strip()) > 0

    def test_gate_template_contains_routing_modes(self):
        result = prompts.render("gate/gate_classify.j2", {})
        assert "CONVERSATION" in result
        assert "EXPLORATION" in result
        assert "GOVERNED" in result

    def test_gate_template_requires_json_response(self):
        result = prompts.render("gate/gate_classify.j2", {})
        assert "JSON" in result

    def test_gate_template_explains_GOVERNED(self):
        result = prompts.render("gate/gate_classify.j2", {})
        assert "Zahlen" in result or "Einheiten" in result


# ── gate.py Migration ────────────────────────────────────────────────────────


class TestGateMigration:
    def test_gate_py_has_no_hardcoded_string_prompt(self):
        """Stelle sicher dass _GATE_SYSTEM_PROMPT nicht mehr existiert."""
        import app.agent.runtime.gate as gate_module
        assert not hasattr(gate_module, "_GATE_SYSTEM_PROMPT"), (
            "_GATE_SYSTEM_PROMPT ist noch in gate.py — Migration unvollstaendig"
        )

    def test_gate_py_has_get_gate_system_prompt_function(self):
        from app.agent.runtime.gate import _get_gate_system_prompt
        result = _get_gate_system_prompt()
        assert isinstance(result, str)
        assert "GOVERNED" in result

    def test_get_gate_system_prompt_returns_same_content_as_template(self):
        from app.agent.runtime.gate import _get_gate_system_prompt
        gate_prompt = _get_gate_system_prompt()
        template_render = prompts.render("gate/gate_classify.j2", {})
        assert gate_prompt == template_render


# ── RendererTemplateMap vollstaendig ─────────────────────────────────────────


class TestRendererTemplateMap:
    def test_all_outward_classes_have_templates(self):
        expected_classes = {
            "conversational_answer",
            "structured_clarification",
            "governed_state_update",
            "technical_preselection",
            "candidate_shortlist",
            "inquiry_ready",
        }
        assert set(_RENDERER_TEMPLATE_MAP.keys()) == expected_classes

    def test_all_mapped_templates_exist(self):
        for outward_class, template_path in _RENDERER_TEMPLATE_MAP.items():
            full_path = PROMPTS_DIR / template_path
            assert full_path.exists(), (
                f"{outward_class} → {template_path} existiert nicht"
            )

    def test_no_forbidden_names_in_map(self):
        forbidden = {"governed_recommendation", "rfq_ready"}
        for key in _RENDERER_TEMPLATE_MAP:
            assert key not in forbidden, f"Verbotener Name gefunden: {key}"
