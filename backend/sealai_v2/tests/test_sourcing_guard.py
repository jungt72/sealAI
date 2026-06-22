"""Tests fuer sourcing_guard.strip_sourcing -- kein LLM, kein Netz, kein Mock."""

from __future__ import annotations

from sealai_v2.core.sourcing_guard import strip_sourcing


def test_positive_rfq_sentence_stripped():
    """Beschaffungs-Imperativ wird aus dem Text entfernt (INC-2 POSITIV-Fall)."""
    text = "Fordern Sie ein Angebot bei MuellerDicht an."
    result = strip_sourcing(text)
    assert "Fordern Sie" not in result


def test_negative_technical_sentence_unchanged():
    """Rein technische Norm-Nennung bleibt unveraendert (INC-2 NEGATIV-Fall)."""
    text = "Der Werkstoff FKM ist nach DIN 3760 spezifiziert."
    result = strip_sourcing(text)
    assert result == text


def test_bestellen_sie_bei_stripped():
    """'bestellen Sie bei ...' wird entfernt."""
    text = "Bitte bestellen Sie bei Freudenberg direkt."
    result = strip_sourcing(text)
    assert "bestellen Sie bei" not in result


def test_angebot_anfordern_stripped():
    """'Angebot anfordern' wird entfernt."""
    text = "Sie koennen das Angebot anfordern."
    result = strip_sourcing(text)
    assert "Angebot anfordern" not in result


def test_bezugsquelle_stripped():
    """'Bezugsquelle:' wird entfernt."""
    text = "Bezugsquelle: Trelleborg Sealing Solutions."
    result = strip_sourcing(text)
    assert "Bezugsquelle" not in result


def test_mixed_text_strips_only_sourcing_sentence():
    """Nur der Beschaffungs-Satz wird entfernt; technischer Inhalt bleibt."""
    text = "FKM eignet sich fuer Heissdampf. Fordern Sie ein Angebot bei ABC an. Grenztemperatur laut Datenblatt: 200 Grad C."
    result = strip_sourcing(text)
    assert "Fordern Sie" not in result
    assert "FKM eignet sich" in result
    assert "Grenztemperatur" in result


def test_technical_only_unchanged():
    """Reiner technischer Text wird nicht veraendert."""
    text = "FKM ist ein fluorierter Elastomer-Werkstoff (DIN ISO 1629)."
    result = strip_sourcing(text)
    assert result == text
