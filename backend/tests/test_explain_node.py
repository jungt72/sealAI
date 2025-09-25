# backend/tests/test_explain_node.py
from __future__ import annotations

from langchain_core.messages import HumanMessage, AIMessage

# Ziel: nur explain_node testen, ohne echte LLM-Aufrufe
from app.services.langgraph.graph.consult.nodes.explain import explain_node

def _fake_state_base():
    return {
        "params": {
            "falltyp": "ersatz",
            "wellen_mm": 25.0,
            "gehause_mm": 47.0,
            "breite_mm": 7.0,
            "medium": "Öl",
            "temp_max_c": 80.0,
            "druck_bar": 2.0,
            "drehzahl_u_min": 1500.0,
        },
        "derived": {"calculated": {"umfangsgeschwindigkeit_m_s": 1.96}, "flags": {}},
    }

def test_explain_node_always_outputs_message_when_recs_present():
    """
    Wenn recommendations im State vorhanden sind, muss explain_node immer eine AIMessage liefern
    (auch ohne Vergleichs-Intent). => Kein Echo, kein Leerlauf.
    """
    state = _fake_state_base()
    state["messages"] = [HumanMessage(content="Ich brauche Ersatz für BA 25x47x7")]
    state["recommendations"] = [
        {
            "typ": "BA 25x47x7",
            "werkstoff": "NBR",
            "begruendung": "Öl, 80°C, 2 bar, moderate Drehzahl → NBR geeignet.",
            "vorteile": ["gute Medienbeständigkeit", "kosteneffizient"],
            "einschraenkungen": ["nicht für >100°C"],
            "geeignet_fuer": ["Öl", "bis 80°C", "2 bar"],
        },
        {
            "typ": "BA 25x47x7",
            "werkstoff": "FKM",
            "begruendung": "Alternative für höhere Temperaturreserve.",
            "vorteile": ["hohe Temperaturbeständigkeit"],
            "einschraenkungen": ["teurer"],
            "geeignet_fuer": ["Öl", "höhere Temperaturen"],
        },
    ]

    out = explain_node(state)
    msgs = out.get("messages") or []
    assert msgs, "explain_node muss eine Nachricht erzeugen"
    assert isinstance(msgs[0], AIMessage), "Antwort muss AIMessage sein"
    content = (msgs[0].content or "").lower()
    # sollte kein Echo des Usertexts sein, sondern strukturierte Erklärung
    assert "meine empfehlung" in content or "typ:" in content, "Erwartete Empfehlung/Erklärung nicht gefunden"


def test_explain_node_comparison_table_when_user_asks_to_compare():
    """
    Wenn Nutzer:in 'vergleichen' wünscht, soll explain_node eine Tabelle liefern.
    Wir simulieren das, indem wir in den letzten HumanMessage-Text ein Vergleichs-Signal packen
    und eine vorherige AI-Antwort mit Empfehlung als Quelle bereitstellen.
    """
    state = _fake_state_base()
    state["messages"] = [
        AIMessage(content=(
            "🔎 **Meine Empfehlung – präzise und transparent:**\n\n"
            "**Typ:** BA 25x47x7\n"
            "**Werkstoff:** NBR\n"
            "**Vorteile:** gute Medienbeständigkeit, kosteneffizient\n"
            "**Einschränkungen:** nicht für >100 °C\n"
            "**Begründung:** Öl, 80°C, 2 bar, 1500 U/min → NBR passt.\n\n"
            "**Alternativen:**\n"
            "- BA 25x47x7 (FKM)\n"
        )),
        HumanMessage(content="Kannst du die Optionen bitte vergleichen?"),
    ]
    # recommendations optional für die Vergleichstabelle, wir nutzen hier die vorhandene AI-Passage
    state["recommendations"] = [
        {"typ": "BA 25x47x7", "werkstoff": "NBR"},
        {"typ": "BA 25x47x7", "werkstoff": "FKM"},
    ]

    out = explain_node(state)
    msgs = out.get("messages") or []
    assert msgs, "explain_node muss eine Nachricht erzeugen"
    assert isinstance(msgs[0], AIMessage)
    content = msgs[0].content or ""
    assert "| Option | Werkstoff |" in content, "Vergleichstabelle (Markdown) nicht gefunden"
