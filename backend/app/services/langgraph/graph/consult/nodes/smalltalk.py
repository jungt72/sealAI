# backend/app/services/langgraph/graph/consult/nodes/smalltalk.py
from __future__ import annotations

import random
import re
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from ..utils import normalize_messages

RE_HELLO = re.compile(r"\b(hi|hallo|hello|hey|servus|moin)\b", re.I)
RE_HOWAREYOU = re.compile(r"wie\s+geht'?s|how\s+are\s+you", re.I)
RE_BYE = re.compile(r"\b(tsch(ü|u)ss|ciao|bye)\b", re.I)

GREETINGS = [
    "Hi! 👋 Wie kann ich dir helfen?",
    "Hallo! 😊 Was steht an?",
    "Servus! Was kann ich für dich tun?",
    "Moin! Womit kann ich dich unterstützen?",
]
HOW_ARE_YOU = [
    "Danke der Nachfrage – mir geht's gut! Wie kann ich dir helfen?",
    "Alles gut hier 🙌 Was brauchst du?",
    "Läuft! Sag gern, worum es geht.",
]
GOODBYES = [
    "Tschüss! 👋 Melde dich jederzeit wieder.",
    "Ciao! Bis zum nächsten Mal.",
    "Bis bald! 😊",
]


def _last_user_text(msgs: List) -> str:
    for m in reversed(msgs):
        role = (getattr(m, "type", "") or getattr(m, "role", "")).lower()
        content = getattr(m, "content", "")
        if isinstance(m, dict):
            role = (m.get("type") or m.get("role") or "").lower()
            content = m.get("content")
        if role in ("human", "user") and isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def smalltalk_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Leichte, determ. Smalltalk-Antwort ohne LLM.
    Antwort wird als Assistant-Message in `messages` gelegt; der Flow führt
    anschließend (per Edge) nach `respond`.
    """
    msgs = normalize_messages(state.get("messages", []))
    text = _last_user_text(msgs)

    if RE_BYE.search(text):
        reply = random.choice(GOODBYES)
    elif RE_HOWAREYOU.search(text):
        reply = random.choice(HOW_ARE_YOU)
    elif RE_HELLO.search(text):
        reply = random.choice(GREETINGS)
    else:
        reply = "Alles klar! 🙂 Womit kann ich dir helfen?"

    new_msgs = list(msgs) + [AIMessage(content=reply)]
    return {**state, "messages": new_msgs, "phase": "smalltalk_done"}
