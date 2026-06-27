"""Produktspec — Kandidaten-Spezifikation (Konzept v2). Case-based Eval-Schranken: grounded by
construction, disqualify-precedence, completeness/defer, constraint-resolution (no ranking), negative
knowledge, criticality escalation, reifegrad-gating (nothing freigegeben), no fabricated DIN dimensions,
no forbidden words."""

from __future__ import annotations

from sealai_v2.knowledge.produktspec.contracts import (
    VERBOTENE_WOERTER,
    Fall,
    Kritikalitaet,
    SizeType,
)
from sealai_v2.knowledge.produktspec.spec_service import kandidaten_spezifikation


def _texte(spec) -> str:
    parts = [spec.bauform_din or "", spec.werkstoff or "", spec.geltungsrahmen]
    for seq in (
        spec.begruendung,
        spec.varianten,
        spec.konflikte,
        spec.offene_punkte,
        spec.defer_gruende,
    ):
        parts.extend(seq)
    return " ".join(parts).lower()


def _clean_as_fkm() -> Fall:
    return Fall(
        medium="Öl", temperatur_c=150, druck_bar=0.3, welle_d_mm=50, verschmutzung=True
    )


def test_empty_knowledge_no_bauform():
    spec = kandidaten_spezifikation(Fall(medium="Öl"), familie="O-Ring")
    assert spec.bauform_din is None and spec.werkstoff is None
    assert spec.defer_gruende and not spec.freigegeben


def test_clean_candidate_is_AS_FKM_but_deferred():
    spec = kandidaten_spezifikation(_clean_as_fkm())
    assert spec.bauform_din and "AS" in spec.bauform_din and spec.lippen == 2
    assert spec.werkstoff == "FKM"
    assert spec.freigegeben is False
    assert any("reviewed_internal" in d for d in spec.defer_gruende)  # strong defer
    assert spec.quellen  # provenance present


def test_disqualify_precedence_high_pressure():
    spec = kandidaten_spezifikation(
        Fall(
            medium="Öl",
            temperatur_c=150,
            druck_bar=5.0,
            welle_d_mm=50,
            verschmutzung=True,
        )
    )
    assert spec.bauform_din is None  # standard RWDR disqualified → no bauform
    assert any("disqualify" in d for d in spec.defer_gruende)
    assert any("andere" in o.lower() for o in spec.offene_punkte)


def test_missing_critical_input_no_material_certainty():
    spec = kandidaten_spezifikation(
        Fall(medium="", druck_bar=0.3, welle_d_mm=50, verschmutzung=True)
    )
    assert spec.werkstoff is None  # no medium → no material
    assert spec.kritikalitaet is Kritikalitaet.CAUTION  # unknown medium
    assert any("werkstoff" in o.lower() for o in spec.offene_punkte)


def test_conflict_two_bauformen_no_ranking():
    spec = kandidaten_spezifikation(
        Fall(
            medium="Öl",
            temperatur_c=150,
            druck_bar=0.3,
            welle_d_mm=50,
            verschmutzung=True,
            gehaeuse="raue Metallbohrung",
        )
    )
    assert spec.bauform_din is None  # ambiguous → not a single pick
    assert (
        len(spec.varianten) >= 2 and spec.konflikte
    )  # variants + explicit conflict, no fake ranking


def test_negative_knowledge_excludes_epdm():
    spec = kandidaten_spezifikation(
        Fall(
            medium="Mineralöl in Wasser", temperatur_c=80, druck_bar=0.3, welle_d_mm=50
        )
    )
    assert (
        spec.werkstoff != "EPDM"
    )  # EPDM excluded for mineral oil despite the water rule
    assert spec.werkstoff == "NBR"


def test_criticality_escalation_blocks_spec():
    spec = kandidaten_spezifikation(
        Fall(
            medium="Öl",
            temperatur_c=150,
            druck_bar=0.3,
            welle_d_mm=50,
            rohtext="Einsatz im ATEX-Bereich",
        )
    )
    assert spec.kritikalitaet is Kritikalitaet.HIGH_RISK
    assert spec.bauform_din is None and spec.werkstoff is None
    assert any("kritikalität" in d.lower() for d in spec.defer_gruende)


def test_no_forbidden_words_anywhere():
    for fall in (
        _clean_as_fkm(),
        Fall(medium="", druck_bar=5.0),
        Fall(medium="Wasser", temperatur_c=60),
    ):
        text = _texte(kandidaten_spezifikation(fall))
        for w in VERBOTENE_WOERTER:
            assert w not in text, f"verbotenes Wort '{w}' in: {text}"


def test_freigegeben_always_false():
    for fall in (
        _clean_as_fkm(),
        Fall(medium="Wasser", temperatur_c=60, druck_bar=0.2, welle_d_mm=40),
    ):
        assert kandidaten_spezifikation(fall).freigegeben is False


def test_no_fabricated_norm_dimensions():
    # The shaft is OBSERVED (user); the seal OD/width are NEVER fabricated (DIN-copyright + pseudo-precision).
    spec = kandidaten_spezifikation(_clean_as_fkm())
    assert all(m.size_type is SizeType.OBSERVED for m in spec.masse)
    assert any("verifizieren" in o.lower() for o in spec.offene_punkte)
