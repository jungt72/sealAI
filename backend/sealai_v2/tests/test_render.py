"""M4b render — deterministic artifact projection (briefing + calc-report).

Load-bearing properties (build-spec §4; owner gate): determinism (same snapshot → byte-identical),
no-invention (the template formats ONLY snapshot data — never adds a number/fact), provenance-visible
(computed: formula+source+estimate/stage+warnings; grounded: quelle+card_id; not_computed: reason),
claim-boundary (static wording stays scoped — orientation/screening + Hersteller-Prüfgrundlage; NO
release/approval/suitability phrasing), purity (I/O-free, no LLM/network). Render is a TERMINAL
projection — it never touches L1/L3, so it cannot change the measured answer.
"""

from __future__ import annotations

from sealai_v2.core.contracts import (
    Answer,
    ComputedValue,
    Flags,
    GroundingFact,
    NotComputed,
    PipelineResult,
    RenderSnapshot,
)
from sealai_v2.render import CLAIM_BOUNDARY, ArtifactRenderer, snapshot_from_result
from sealai_v2.render.renderer import _offene_punkte


def _snapshot() -> RenderSnapshot:
    return RenderSnapshot(
        question="Welle 80 mm, 3000 U/min — Standard-NBR-RWDR ok?",
        answer_text="Von der Umfangsgeschwindigkeit her grenzwertig, aber machbar.",
        computed=(
            ComputedValue(
                calc_id="umfangsgeschwindigkeit",
                name="v_m_s",
                value=12.5664,
                unit="m/s",
                stage=1,
                derivation_depth=1,
                formula="v = π · d1 · n / 60000",
                source="Freudenberg Simmerring-Handbuch; NBR-Grenze ~14 m/s (eval CALC-01)",
                assumptions=("Wellendurchmesser = Laufdurchmesser der Dichtkante",),
                inputs_used=("d1_mm", "rpm"),
                warnings=(),
                estimate=False,
            ),
        ),
        not_computed=(
            NotComputed("pv_wert", "nicht berechenbar: Eingaben fehlen (p_bar)"),
        ),
        calc_notes=(),
        grounding_facts=(),
        grounded=False,
    )


def _grounded_snapshot() -> RenderSnapshot:
    s = _snapshot()
    return RenderSnapshot(
        question=s.question,
        answer_text=s.answer_text,
        computed=s.computed,
        not_computed=s.not_computed,
        calc_notes=("Quellungshinweis: Reserve für Quellung/Wärmedehnung lassen.",),
        grounding_facts=(
            GroundingFact(
                text="Statische radiale Verpressung ~15–25 % (Richtwert).",
                quelle="Fachkarte FK-ORING-VERPRESSUNG (reviewed; eval:CALC-02, owner:nutauslegung)",
                card_id="FK-ORING-VERPRESSUNG",
            ),
        ),
        grounded=True,
    )


def test_calc_report_is_deterministic():
    r = ArtifactRenderer()
    s = _snapshot()
    assert r.calc_report(s).body == r.calc_report(s).body


def test_briefing_is_deterministic():
    r = ArtifactRenderer()
    s = _grounded_snapshot()
    assert r.briefing(s).body == r.briefing(s).body


def test_calc_report_shows_provenance():
    b = ArtifactRenderer().calc_report(_snapshot()).body
    assert "12.5664" in b and "m/s" in b  # value + unit
    assert "v = π · d1 · n / 60000" in b  # formula
    assert "Freudenberg" in b  # source
    assert "Stufe 1" in b  # cascade stage
    assert (
        "nicht berechenbar" in b and "p_bar" in b
    )  # not_computed reason (fail-closed)


def test_estimate_and_warning_marked():
    s = RenderSnapshot(
        question="q",
        answer_text="a",
        computed=(
            ComputedValue(
                "pv_wert",
                "pv",
                62.8,
                "bar·m/s",
                2,
                2,
                formula="PV = p · v",
                source="Tietze",
                warnings=("außerhalb des typischen Bereichs 0–50 bar·m/s",),
                estimate=True,
            ),
        ),
        not_computed=(),
        calc_notes=(),
        grounding_facts=(),
        grounded=False,
    )
    b = ArtifactRenderer().calc_report(s).body
    assert "Schätzwert" in b  # derived-of-derived → estimate marked
    assert "außerhalb des typischen Bereichs" in b  # warning surfaced


def test_briefing_shows_grounding_provenance():
    b = ArtifactRenderer().briefing(_grounded_snapshot()).body
    assert "FK-ORING-VERPRESSUNG" in b  # card_id
    assert "reviewed" in b  # quelle carries provenance
    assert "~15–25 %" in b  # the grounded fact text


def test_briefing_vorlaeufig_when_ungrounded():
    b = ArtifactRenderer().briefing(_snapshot()).body  # grounded=False
    assert "vorläufig" in b.lower()


def test_no_invention_only_snapshot_facts():
    # the template must format ONLY snapshot data — never add a number/material/fact
    b = ArtifactRenderer().briefing(_snapshot()).body
    assert "EPDM" not in b and "20 m/s" not in b and "75–90" not in b
    assert "12.5664" in b  # the one computed value IS rendered, exactly


def test_claim_boundary_frame_present_and_scoped():
    b = ArtifactRenderer().briefing(_snapshot()).body
    assert "Orientierung" in b and "Hersteller-Prüfgrundlage" in b
    assert "Freigabe" in b  # appears in the NEGATED frame ("keine ... Freigabe")
    # NO affirmative release/approval/suitability phrasing emitted by the template
    for bad in (
        "ist freigegeben",
        "garantiert geeignet",
        "Eignung bestätigt",
        "zugelassen für",
        "Konformität bestätigt",
    ):
        assert bad not in b


def test_claim_boundary_constant_is_scoped():
    # the frame is owner-grounded doctrine wording — orientation/screening + manufacturer basis
    assert "Orientierung" in CLAIM_BOUNDARY
    assert "Hersteller-Prüfgrundlage" in CLAIM_BOUNDARY
    assert "keine" in CLAIM_BOUNDARY and "Freigabe" in CLAIM_BOUNDARY


def test_snapshot_from_result_roundtrip():
    res = PipelineResult(
        question="q",
        tenant_id="t",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="ans", model="m"),
        computed_values=(
            ComputedValue(
                "umfangsgeschwindigkeit",
                "v_m_s",
                12.5664,
                "m/s",
                1,
                1,
                formula="f",
                source="s",
            ),
        ),
        not_computed=(NotComputed("pv_wert", "Eingaben fehlen"),),
        calc_notes=("note",),
        grounding_facts=(),
        grounded=False,
    )
    snap = snapshot_from_result("q", res)
    assert snap.answer_text == "ans"
    assert snap.computed[0].value == 12.5664
    assert snap.not_computed[0].calc_id == "pv_wert"
    assert snap.calc_notes == ("note",)
    assert snap.grounded is False


def test_renderer_is_io_free():
    # no LLM, no network: a renderer built with zero external deps produces both artifacts
    r = ArtifactRenderer()
    assert r.calc_report(_snapshot()).body
    assert r.briefing(_snapshot()).body


# --- P3: Wissensstand-Referenz carried through the render seam (metadata, not rendered text) ---


def test_snapshot_from_result_carries_wissensstand():
    res = PipelineResult(
        question="q",
        tenant_id="t",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="ans", model="m"),
        wissensstand="fk:v1|mx:v2",
    )
    assert snapshot_from_result("q", res).wissensstand == "fk:v1|mx:v2"


def test_calc_report_artifact_carries_wissensstand():
    s = RenderSnapshot(question="q", answer_text="a", wissensstand="fk:v1")
    assert ArtifactRenderer().calc_report(s).wissensstand == "fk:v1"


def test_briefing_artifact_carries_wissensstand():
    s = RenderSnapshot(question="q", answer_text="a", wissensstand="fk:v1|trap:v3")
    assert ArtifactRenderer().briefing(s).wissensstand == "fk:v1|trap:v3"


def test_wissensstand_defaults_to_empty_string_and_is_never_rendered_into_body():
    s = _snapshot()  # no wissensstand passed
    assert s.wissensstand == ""
    art = ArtifactRenderer().briefing(s)
    assert art.wissensstand == ""
    assert "wissensstand" not in art.body.lower()  # metadata field, not template output


# --- P5: "Offene Punkte" — consolidating already-live open-item signals (audit L8) -------------


def _result(**overrides) -> PipelineResult:
    base = dict(
        question="q",
        tenant_id="t",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="ans", model="m"),
    )
    base.update(overrides)
    return PipelineResult(**base)


def test_offene_punkte_collects_not_computed_and_calc_notes():
    res = _result(
        not_computed=(NotComputed("pv_wert", "Eingaben fehlen (p_bar)"),),
        calc_notes=("Quellungshinweis: Reserve lassen.",),
    )
    assert _offene_punkte(res) == (
        "pv_wert: Eingaben fehlen (p_bar)",
        "Quellungshinweis: Reserve lassen.",
    )


def test_offene_punkte_includes_the_bedingt_gegencheck_condition():
    res = _result(
        gegencheck={
            "disqualified": False,
            "basis": "matrix_conditional",
            "condition": "Nur bei Wellendrehzahl < 10 m/s einsetzen.",
            "source": "Verträglichkeitsmatrix · MX-VMQ-DYNAMISCH (reviewed)",
        }
    )
    assert _offene_punkte(res) == ("Nur bei Wellendrehzahl < 10 m/s einsetzen.",)


def test_offene_punkte_stays_silent_for_a_disqualified_verdict():
    # E4-1: disqualified is a hard verdict, not an "open point" — and must not be silently
    # softened into "just something to verify" alongside genuinely open items.
    res = _result(
        gegencheck={
            "disqualified": True,
            "reason": "FKM hydrolysiert in Heißdampf.",
            "source": "Verträglichkeitsmatrix · MX-FKM-DAMPF (reviewed)",
        }
    )
    assert _offene_punkte(res) == ()


def test_offene_punkte_stays_silent_for_non_conditional_bases():
    for basis in ("matrix_compatible", "no_matrix_data", "no_medium"):
        res = _result(gegencheck={"disqualified": False, "basis": basis})
        assert _offene_punkte(res) == ()


def test_offene_punkte_includes_kandidaten_spec_offene_punkte():
    res = _result(kandidaten_spec={"offene_punkte": ["Sonderwerkstoff-Freigabe klären."]})
    assert _offene_punkte(res) == ("Sonderwerkstoff-Freigabe klären.",)


def test_offene_punkte_empty_when_no_signal_present():
    assert _offene_punkte(_result()) == ()


def test_snapshot_from_result_carries_offene_punkte():
    res = _result(calc_notes=("note",))
    assert snapshot_from_result("q", res).offene_punkte == ("note",)


def test_briefing_renders_the_offene_punkte_section_when_present():
    s = RenderSnapshot(
        question="q", answer_text="a", offene_punkte=("Sonderwerkstoff-Freigabe klären.",)
    )
    body = ArtifactRenderer().briefing(s).body
    assert "## Offene Punkte" in body
    assert "Sonderwerkstoff-Freigabe klären." in body


def test_briefing_omits_the_offene_punkte_section_when_empty():
    s = _snapshot()  # offene_punkte defaults to ()
    body = ArtifactRenderer().briefing(s).body
    assert "Offene Punkte" not in body


def test_calc_report_never_gets_an_offene_punkte_section():
    # the section is briefing-only; calc_report is a separate, standalone artifact elsewhere
    # (e.g. the /compute panel) and must stay byte-identical to before this increment.
    s = RenderSnapshot(
        question="q", answer_text="a", offene_punkte=("should not appear here",)
    )
    body = ArtifactRenderer().calc_report(s).body
    assert "should not appear here" not in body
    assert "Offene Punkte" not in body
