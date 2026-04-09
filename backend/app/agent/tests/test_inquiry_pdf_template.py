from __future__ import annotations

from app.agent.documents.pdf_generator import render_inquiry_pdf_html
from app.agent.prompts import PROMPTS_DIR, prompts
from app.agent.state.models import (
    DecisionState,
    DerivedState,
    GovernedSessionState,
    NormalizedParameter,
    NormalizedState,
    RequirementClass,
    SealaiNormIdentity,
    SealaiNormState,
)


def _state() -> GovernedSessionState:
    return GovernedSessionState(
        normalized=NormalizedState.model_validate(
            {
                "parameters": {
                    "medium": NormalizedParameter(
                        field_name="medium",
                        value="Salzwasser NaCl ~5%",
                        confidence="confirmed",
                        source="llm",
                    ),
                    "temperature_c": NormalizedParameter(
                        field_name="temperature_c",
                        value=80.0,
                        unit="°C",
                        confidence="confirmed",
                        source="llm",
                    ),
                    "installation": NormalizedParameter(
                        field_name="installation",
                        value="horizontal",
                        confidence="inferred",
                        source="default",
                    ),
                },
                "parameter_status": {
                    "medium": "observed",
                    "temperature_c": "observed",
                    "installation": "assumed",
                },
            }
        ),
        derived=DerivedState(
            pv_value=15.71,
            velocity=15.71,
            applicable_norms=["DIN EN 12756", "API 682 Category 2"],
            field_status={"pv_value": "derived", "velocity": "derived"},
        ),
        decision=DecisionState(
            requirement_class=RequirementClass(
                class_id="STS-RS-CHEM-B1",
                description="Chemical service",
                seal_type="Gleitringdichtung",
            ),
            gov_class="B",
            decision_basis_hash="abc123def4567890",
            assumptions=["Einbaulage horizontal (nicht bestaetigt)"],
            open_validation_points=["Chloridgehalt bestaetigen", "Wellentoleranz pruefen"],
            preselection={
                "type": "Gleitring Cartridge",
                "material": "SiC/SiC",
                "elastomer": "FKM Standard",
                "fit_score": 0.89,
            },
        ),
        sealai_norm=SealaiNormState(
            application_summary="Kreiselpumpe, Chemie",
            identity=SealaiNormIdentity(seal_family="Gleitringdichtung"),
        ),
    )


def test_inquiry_template_files_exist() -> None:
    assert (PROMPTS_DIR / "pdf" / "inquiry.html.j2").exists()
    assert (PROMPTS_DIR / "pdf" / "styles.css").exists()


def test_inquiry_template_renders_with_minimal_governed_state() -> None:
    html = render_inquiry_pdf_html(_state())

    assert "<!DOCTYPE html>" in html
    assert "1. Bedarfsanalyse" in html
    assert "2. Parameter" in html
    assert "3. Berechnungen" in html
    assert "5. Technische Vorauswahl" in html
    assert "6. Annahmen" in html
    assert "7. Offene Pruefpunkte fuer Hersteller" in html
    assert "Technische Vorauswahl auf Basis der angegebenen Parameter" in html
    assert "fit_score" in html
    assert "0.89" in html
    assert "bestaetigt" in html
    assert "angenommen" in html
    assert "Wahrscheinlichkeit" not in html


def test_pdf_prompt_template_renders_from_explicit_context() -> None:
    html = prompts.render(
        "pdf/inquiry.html.j2",
        {
            "case_id": "STS-INQ-001",
            "created_at": "2026-04-09T17:00:00Z",
            "basis_hash": "sha256:a3f9",
            "demand_analysis": [{"label": "Anwendung", "value": "Kreiselpumpe, Chemie"}],
            "parameters": [
                {
                    "label": "Medium",
                    "value": "Salzwasser NaCl ~5%",
                    "status_label": "bestaetigt",
                    "status_class": "observed",
                }
            ],
            "calculations": [
                {
                    "label": "PV-Wert",
                    "formula": "π×50×6000/60000",
                    "value": "15.71 m/s",
                }
            ],
            "norm_references": ["DIN EN 12756"],
            "preselection_items": [
                {"label": "Material", "value": "SiC/SiC", "fit_score": "0.89"}
            ],
            "assumptions": ["Einbaulage horizontal (nicht bestaetigt)"],
            "open_points": ["Chloridgehalt bestaetigen"],
            "disclaimer": "Technische Vorauswahl, Hersteller entscheidet final.",
            "styles_css": "body { color: #111; }",
        },
    )

    assert "SeaLAI Technical Inquiry" in html
    assert "STS-INQ-001" in html
    assert "Chloridgehalt bestaetigen" in html
    assert "Technische Vorauswahl, Hersteller entscheidet final." in html
