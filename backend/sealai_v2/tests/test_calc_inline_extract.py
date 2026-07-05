"""INC-3a — Akzeptanztests fuer extract_inline (deterministisch, kein LLM).

Alle sieben Akzeptanzkriterien aus INC-3a werden als eigenstaendige Tests abgebildet.
"""

from __future__ import annotations


from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.calc.inline_extract import extract_inline


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------


def _by_feld(facts, feld: str):
    """Gibt das erste Fact mit passendem feld zurueck oder None."""
    return next((f for f in facts if f.feld == feld), None)


# ---------------------------------------------------------------------------
# AC-1: Einzelner Druck → genau ein Fact
# ---------------------------------------------------------------------------


def test_single_druck_fact():
    """'Ich fahre mit 16 bar.' → genau ein druck-Fact, wert enthaelt '16 bar'."""
    facts = extract_inline("Ich fahre mit 16 bar.")
    druck = _by_feld(facts, "druck")
    assert druck is not None, "Kein druck-Fact emittiert"
    assert "16" in druck.wert
    assert "bar" in druck.wert
    assert druck.provenance == "chat-inline"
    # Kein weiteres Fact fuer druck
    druck_facts = [f for f in facts if f.feld == "druck"]
    assert len(druck_facts) == 1


# ---------------------------------------------------------------------------
# AC-2: Vier Felder in einer Nachricht → vier Facts
# ---------------------------------------------------------------------------


def test_four_fields_one_message():
    """'16 bar bei 3000 U/min, Welle 80 mm, 2 m/s.' → vier Facts."""
    facts = extract_inline("16 bar bei 3000 U/min, Welle 80 mm, 2 m/s.")
    felder = {f.feld for f in facts}
    assert felder == {"druck", "drehzahl", "wellendurchmesser", "geschwindigkeit"}

    druck = _by_feld(facts, "druck")
    assert druck is not None and "16" in druck.wert and "bar" in druck.wert

    drehzahl = _by_feld(facts, "drehzahl")
    assert drehzahl is not None and "3000" in drehzahl.wert

    welle = _by_feld(facts, "wellendurchmesser")
    assert welle is not None and "80" in welle.wert and "mm" in welle.wert

    speed = _by_feld(facts, "geschwindigkeit")
    assert speed is not None and "2" in speed.wert and "m/s" in speed.wert


# ---------------------------------------------------------------------------
# AC-3: Multiplizitaet derselben Einheit → kein Emit
# ---------------------------------------------------------------------------


def test_multiplizitaet_kein_druck_fact():
    """'von 10 bar auf 16 bar' → KEIN druck-Fact (zwei Vorkommen, Multiplizitaets-Guard)."""
    facts = extract_inline("von 10 bar auf 16 bar")
    assert _by_feld(facts, "druck") is None


# ---------------------------------------------------------------------------
# AC-4: Cross-Unit-Multiplizitaet → kein Emit
# ---------------------------------------------------------------------------


def test_cross_unit_multiplizitaet_kein_druck_fact():
    """'16 bar oder 5 MPa' → KEIN druck-Fact (bar akzeptiert + MPa known-other = 2 Vorkommen)."""
    facts = extract_inline("16 bar oder 5 MPa")
    assert _by_feld(facts, "druck") is None


# ---------------------------------------------------------------------------
# AC-5: Nackte Zahl ohne Einheit → keine Facts
# ---------------------------------------------------------------------------


def test_nackte_zahl_keine_facts():
    """'ungefaehr 16' → keine Facts (keine Einheit erkannt)."""
    facts = extract_inline("ungefaehr 16")
    assert len(facts) == 0


# ---------------------------------------------------------------------------
# AC-6: Known-other allein → kein Emit (defer)
# ---------------------------------------------------------------------------


def test_known_other_allein_kein_druck_fact():
    """'1,6 MPa' → KEIN druck-Fact (MPa ist known-other, defer an LLM-Distiller)."""
    facts = extract_inline("1,6 MPa")
    assert _by_feld(facts, "druck") is None


# ---------------------------------------------------------------------------
# AC-7: Gegenprobe Binder — extract_inline → bind_params
# ---------------------------------------------------------------------------


def test_gegenprobe_binder():
    """bind_params(extract_inline('16 bar')).params == {'p_bar': 16.0}."""
    facts = extract_inline("16 bar")
    result = bind_params(facts)
    assert result.params == {"p_bar": 16.0}


# ---------------------------------------------------------------------------
# Zusaetzliche Randfall-Tests
# ---------------------------------------------------------------------------


def test_provenance_ist_chat_inline():
    """Jedes emittierte Fact hat provenance='chat-inline'."""
    facts = extract_inline("16 bar bei 3000 U/min, Welle 80 mm, 2 m/s.")
    for f in facts:
        assert f.provenance == "chat-inline", (
            f"Falsche provenance bei {f.feld}: {f.provenance}"
        )


def test_leere_nachricht_keine_facts():
    """Leere Nachricht → keine Facts."""
    assert extract_inline("") == ()


def test_nur_text_keine_facts():
    """Nachricht ohne Zahlen → keine Facts."""
    assert extract_inline("Hallo, wie kann ich helfen?") == ()


def test_drehzahl_umin_synonym():
    """'3000 U/min' → drehzahl-Fact (U/min ist akzeptiertes Synonym)."""
    facts = extract_inline("Drehzahl betraegt 3000 U/min.")
    drehzahl = _by_feld(facts, "drehzahl")
    assert drehzahl is not None and "3000" in drehzahl.wert


def test_wellendurchmesser_mm():
    """'Wellendurchmesser 80 mm' → wellendurchmesser-Fact."""
    facts = extract_inline("Wellendurchmesser 80 mm im Betrieb.")
    welle = _by_feld(facts, "wellendurchmesser")
    assert welle is not None and "80" in welle.wert


def test_kein_emit_fuer_unmapped_einheit():
    """'5 kPa' → kein druck-Fact (kPa ist known-other, allein → defer)."""
    facts = extract_inline("Druck liegt bei 5 kPa.")
    assert _by_feld(facts, "druck") is None


def test_multiplizitaet_drehzahl():
    """'1000 rpm und 2000 U/min' → KEIN drehzahl-Fact (beide akzeptiert = 2 Vorkommen)."""
    facts = extract_inline("zwischen 1000 rpm und 2000 U/min")
    assert _by_feld(facts, "drehzahl") is None


def test_wellendurchmesser_gegenprobe_binder():
    """bind_params(extract_inline('80 mm')).params == {'d1_mm': 80.0}."""
    facts = extract_inline("Welle 80 mm.")
    result = bind_params(facts)
    assert result.params == {"d1_mm": 80.0}
