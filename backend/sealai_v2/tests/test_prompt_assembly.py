from __future__ import annotations

from sealai_v2.core.contracts import Flags
from sealai_v2.prompts.assembler import PromptAssembler


def test_flags_off_marks_allgemeinwissen_and_no_conditional_blocks():
    p = PromptAssembler().system_prompt(
        flags=Flags(compliance_hint=False, safety_critical=False)
    )
    assert "Allgemeinwissen" in p  # grounding else-branch fires (no grounding at M1)
    assert "Sicherheitskritischer Kontext" not in p
    assert "Compliance-Dimension beachten" not in p


def test_flags_on_lights_safety_and_compliance_blocks():
    p = PromptAssembler().system_prompt(
        flags=Flags(compliance_hint=True, safety_critical=True)
    )
    assert "Sicherheitskritischer Kontext" in p
    assert "explosive Dekompression" in p
    assert "Compliance-Dimension beachten" in p


def test_anrede_defaults_to_du():
    p = PromptAssembler().system_prompt()
    assert "in der Du-Form" in p
    assert "in der Sie-Form" not in p


def test_berechnungen_section_binds_fail_closed():
    """M8-B — the compute-constraint (owner-approved spec). The advisory wording demonstrably did
    not bind (the canonical saltwater briefing leak); the section must forbid self-computation of
    kern-owned quantities even with visible inputs, and bind the fail-closed narrative."""
    p = PromptAssembler().system_prompt()
    flat = " ".join(
        p.split()
    )  # template line-wrapping is not the contract; the wording is
    # kern-owned quantities are named; self-computation is forbidden EVEN with visible inputs
    assert (
        "Umfangsgeschwindigkeit" in flat and "PV-Wert" in flat and "Verpressung" in flat
    )
    assert "NIE selbst" in flat
    assert "auch wenn Wellendurchmesser und Drehzahl im Kontext sichtbar sind" in flat
    # injected values are referenced exactly
    assert "exakt wie injiziert" in flat
    # fail-closed: NO number, name the missing inputs, formula symbolic only (owner decision 6)
    assert "keinen Zahlenwert" in flat
    assert "fehlenden Eingaben" in flat
    assert "symbolisch" in flat
    # over-block guard: typical-range knowledge with caveat stays allowed (not parametric)
    assert "keine parametrische Berechnung" in flat


def test_berechnungen_same_message_inputs_and_provenance_label_ban():
    """FIX-FIRST B (owner decision 2026-06-11, branch (b)): the live turn-2 leak — inputs
    stated in the CURRENT message, kern fail-closed, L1 self-computed v=16,76 m/s and labeled
    it 'deterministisch berechnet'. The rule must (1) bind the fail-closed behavior EXPLICITLY
    for same-message inputs and (2) restrict the kern-provenance labels to injected values."""
    p = PromptAssembler().system_prompt()
    flat = " ".join(p.split())
    # (1) same-message inputs change nothing: behave exactly like the no-inputs turn
    assert "in der aktuellen Nachricht" in flat
    # (2) the kern-provenance labels are reserved for the injected block — never self-derived
    assert "ausschließlich" in flat and "selbst ermittelte Zahl" in flat
    assert "falsche Herkunftsangabe" in flat


def test_contract_renderer_mode_renders_complete_jinja_branch():
    contract = {
        "status": "COVERED_RECOMMENDATION",
        "allowed_claims": [
            {
                "severity": "disqualify",
                "text": "FKM ist gegen Heißdampf unverträglich.",
                "sources": ["Verträglichkeitsmatrix"],
            }
        ],
        "required_clauses": ["Finale Freigabe liegt beim Hersteller."],
        "missing_fields": ["Druck"],
        "allowed_materials": ["FKM"],
        "allowed_values": [
            {"name": "Umfangsgeschwindigkeit", "value": 12.3, "unit": "m/s"}
        ],
        "forbidden_phrases": ["freigegeben"],
    }

    p = PromptAssembler().system_prompt(flags=Flags(), contract=contract)

    assert "Renderer-Modus" in p
    assert "FKM ist gegen Heißdampf unverträglich." in p
    assert "Finale Freigabe liegt beim Hersteller." in p
    assert "Fehlende Angaben" in p and "Druck" in p
    assert "Umfangsgeschwindigkeit=12.3 m/s" in p
