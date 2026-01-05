# backend/app/services/langgraph/graph/consult/io.py
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver  # Typkompatibel

from .build import build_consult_graph

log = logging.getLogger(__name__)

OFFLINE_MODE = os.getenv("OFFLINE_MODE", "0") == "1"

# Caches (prozessweit)
_graph_no_cp = None
_graph_by_cp_id: dict[int, Any] = {}  # id(checkpointer) -> compiled graph


def _last_ai_text(msgs) -> str:
    for m in reversed(msgs or []):
        if isinstance(m, AIMessage) and isinstance(getattr(m, "content", None), str):
            return (m.content or "").strip()
    return ""


# ––– Fallback ohne LLM –––
_DIM_RX = re.compile(r"(\d{1,3})\s*[xX]\s*(\d{1,3})\s*[xX]\s*(\d{1,3})")
_BAR_RX = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*bar", re.I)

def _local_fallback_reply(user_text: str) -> str:
    t = (user_text or "").strip()
    tl = t.lower()

    dims = None
    m = _DIM_RX.search(t)
    if m:
        dims = f"{int(m.group(1))}x{int(m.group(2))}x{int(m.group(3))}"

    if "öl" in tl or "oel" in tl or "oil" in tl:
        medium = "Öl"
        material_hint = "FKM"
        vorteile = "hohe Temperatur- und Ölbeständigkeit, gute Alterungsbeständigkeit"
        einschraenkungen = "nicht ideal für Wasser/Heißwasser"
    elif "wasser" in tl or "water" in tl:
        medium = "Wasser"
        material_hint = "EPDM (alternativ HNBR, je nach Temperatur)"
        vorteile = "gute Wasser-/Dampfbeständigkeit (EPDM)"
        einschraenkungen = "nicht ölbeständig (EPDM)"
    else:
        medium = "nicht angegeben"
        material_hint = "NBR (Preis/Leistung) oder FKM (Temperatur/Öl)"
        vorteile = "solide Beständigkeit je nach Materialwahl"
        einschraenkungen = "Materialwahl abhängig von Medium/Temperatur"

    pbar = None
    mp = _BAR_RX.search(tl)
    if mp:
        try:
            pbar = float(mp.group(1).replace(",", "."))
        except Exception:
            pbar = None

    druck_hinweis = ""
    if pbar is not None and pbar > 2:
        druck_hinweis = (
            "\n- **Hinweis:** Überdruck >2 bar ist für Standard-Radialdichtringe kritisch. "
            "Bitte Druckstufen-/Entlastungslösungen prüfen."
        )

    typ = f"BA {dims}" if dims else "BA (Standard-Profil)"

    return (
        "🔎 **Empfehlung (Fallback – LLM temporär nicht erreichbar)**\n\n"
        f"**Typ:** {typ}\n"
        f"**Werkstoff (Hint):** {material_hint}\n"
        f"**Medium:** {medium}\n\n"
        f"**Vorteile:** {vorteile}\n"
        f"**Einschränkungen:** {einschraenkungen}\n"
        f"{druck_hinweis}\n\n"
        "**Nächste Schritte:**\n"
        "- Wenn du **Maße (Welle/Gehäuse/Breite)**, **Medium**, **Tmax**, **Druck** und **Drehzahl/Relativgeschwindigkeit** angibst,\n"
        "  erstelle ich eine präzisere Empfehlung inkl. Alternativen.\n"
        "_(Dies ist eine lokale Antwort ohne LLM; die Detailberatung folgt automatisch, sobald der Dienst wieder verfügbar ist.)_"
    )


def _get_graph(checkpointer: BaseCheckpointSaver | None):
    """
    Liefert einen kompilierten Consult-Graphen.
    - Ohne Checkpointer: Singleton.
    - Mit Checkpointer: pro-Saver gecachter Graph (id(checkpointer) als Key).
    """
    global _graph_no_cp, _graph_by_cp_id

    if checkpointer is None:
        if _graph_no_cp is None:
            g = build_consult_graph()
            _graph_no_cp = g.compile()
            log.info("[consult.io] Graph compiled WITHOUT checkpointer.")
        return _graph_no_cp

    key = id(checkpointer)
    if key not in _graph_by_cp_id:
        try:
            g = build_consult_graph()
            _graph_by_cp_id[key] = g.compile(checkpointer=checkpointer)
            log.info("[consult.io] Graph compiled WITH provided checkpointer.")
        except Exception as e:
            log.warning("[consult.io] Failed to compile with provided checkpointer: %s. Falling back.", e)
            if _graph_no_cp is None:
                g = build_consult_graph()
                _graph_no_cp = g.compile()
            return _graph_no_cp

    return _graph_by_cp_id[key]


def invoke_consult(
    text: str,
    *,
    thread_id: str,
    checkpointer: BaseCheckpointSaver | None = None,
) -> str:
    """
    Führt eine Consult-Anfrage aus.
    - checkpointer: Optionaler externer Saver (z. B. aus app.state).
    """
    user_text = (text or "").strip()
    if not user_text:
        return ""

    if OFFLINE_MODE:
        return _local_fallback_reply(user_text)

    try:
        graph = _get_graph(checkpointer)
        cfg: Dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        initial = {"messages": [HumanMessage(content=user_text)]}
        result = graph.invoke(initial, config=cfg)

        out = _last_ai_text((result or {}).get("messages", []))
        if out:
            return out

        log.warning("[consult.io] Graph returned no AI text; using local fallback.")
        return _local_fallback_reply(user_text)

    except Exception as e:
        log.error("[consult.io] Graph invocation failed, using fallback. Error: %s", e)
        return _local_fallback_reply(user_text)
