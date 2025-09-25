# backend/app/services/langgraph/graph/consult/utils.py
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional

from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage, SystemMessage

log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Message utilities
# -------------------------------------------------------------------

def deserialize_message(x: Any) -> AnyMessage:
    """Robuste Konvertierung nach LangChain-Message-Objekten."""
    if isinstance(x, (HumanMessage, AIMessage, SystemMessage)):
        return x
    if isinstance(x, dict) and "role" in x:
        role = (x.get("role") or "").lower()
        content = x.get("content") or ""
        if role in ("user", "human"):
            return HumanMessage(content=content)
        if role in ("assistant", "ai"):
            return AIMessage(content=content)
        if role == "system":
            return SystemMessage(content=content)
    if isinstance(x, str):
        return HumanMessage(content=x)
    return HumanMessage(content=str(x))


def normalize_messages(seq: Iterable[Any]) -> List[AnyMessage]:
    return [deserialize_message(m) for m in (seq or [])]


def merge_messages(left: Iterable[Any], right: Iterable[Any]) -> List[AnyMessage]:
    return add_messages(normalize_messages(left), normalize_messages(right))


def last_user_text(msgs: List[AnyMessage]) -> str:
    for m in reversed(msgs or []):
        if isinstance(m, HumanMessage):
            return (m.content or "").strip()
    return ""


def messages_text(msgs: List[AnyMessage], *, only_user: bool = False) -> str:
    """
    Verkettet Text aller Messages.
    - only_user=True -> nur HumanMessage.
    """
    parts: List[str] = []
    for m in msgs or []:
        if only_user and not isinstance(m, HumanMessage):
            continue
        c = getattr(m, "content", None)
        if isinstance(c, str) and c:
            parts.append(c)
    return "\n".join(parts)

# Kompatibilitäts-Alias (einige Module importieren 'msgs_text')
msgs_text = messages_text

def only_user_text(msgs: List[AnyMessage]) -> str:
    """Nur die User-Texte zusammengefasst (ohne Lowercasing)."""
    return messages_text(msgs, only_user=True)

def only_user_text_lower(msgs: List[AnyMessage]) -> str:
    """Nur die User-Texte, zu Kleinbuchstaben normalisiert."""
    return only_user_text(msgs).lower()

# -------------------------------------------------------------------
# Numeric parsing & heuristics
# -------------------------------------------------------------------

def _num_from_str(raw: str) -> Optional[float]:
    """Float aus Strings wie '1 200,5' oder '1.200,5' oder '1200.5' extrahieren."""
    try:
        s = (raw or "").replace(" ", "").replace(".", "").replace(",", ".")
        return float(s)
    except Exception:
        return None


def apply_heuristics_from_text(params: Dict[str, Any], text: str) -> Dict[str, Any]:
    """
    Deterministische Fallbacks, falls das LLM Werte nicht gesetzt hat:
      - 'kein/ohne Überdruck/Druck' -> druck_bar = 0
      - '... Druck: 5 bar'          -> druck_bar = 5
      - 'Drehzahl 1.200 U/min'      -> drehzahl_u_min = 1200
      - 'dauerhaft X U/min'         -> drehzahl_u_min = X
      - 'Geschwindigkeit 0.5 m/s'   -> geschwindigkeit_m_s = 0.5
    """
    t = (text or "").lower()
    merged: Dict[str, Any] = dict(params or {})

    # Druck
    if merged.get("druck_bar") in (None, "", "unknown"):
        if re.search(r"\b(kein|ohne)\s+(überdruck|ueberdruck|druck)\b", t, re.I):
            merged["druck_bar"] = 0.0
        else:
            m = re.search(r"(?:überdruck|ueberdruck|druck)\s*[:=]?\s*([0-9][\d\.\s,]*)\s*bar\b", t, re.I)
            if m:
                val = _num_from_str(m.group(1))
                if val is not None:
                    merged["druck_bar"] = val

    # Drehzahl (generisch)
    if merged.get("drehzahl_u_min") in (None, "", "unknown"):
        m = re.search(r"drehzahl[^0-9]{0,12}([0-9][\d\.\s,]*)\s*(?:u\s*/?\s*min|rpm)\b", t, re.I)
        if m:
            val = _num_from_str(m.group(1))
            if val is not None:
                merged["drehzahl_u_min"] = int(round(val))

    # Spezifisch „dauerhaft“
    m_dauer = re.search(
        r"(dauerhaft|kontinuierlich)[^0-9]{0,12}([0-9][\d\.\s,]*)\s*(?:u\s*/?\s*min|rpm)\b",
        t,
        re.I,
    )
    if m_dauer:
        val = _num_from_str(m_dauer.group(2))
        if val is not None:
            merged["drehzahl_u_min"] = int(round(val))

    # Relativgeschwindigkeit in m/s
    if merged.get("geschwindigkeit_m_s") in (None, "", "unknown"):
        m_speed = re.search(r"(geschwindigkeit|v)[^0-9]{0,12}([0-9][\d\.\s,]*)\s*m\s*/\s*s", t, re.I)
        if m_speed:
            val = _num_from_str(m_speed.group(2))
            if val is not None:
                merged["geschwindigkeit_m_s"] = float(val)

    return merged

# -------------------------------------------------------------------
# Validation & anomaly messages
# -------------------------------------------------------------------

def _is_missing_value(key: str, val: Any) -> bool:
    if val is None or val == "" or val == "unknown":
        return True
    # 0 bar ist gültig
    if key == "druck_bar":
        try:
            float(val)
            return False
        except Exception:
            return True
    # Positive Größen brauchen > 0
    if key in (
        "wellen_mm", "gehause_mm", "breite_mm", "drehzahl_u_min", "geschwindigkeit_m_s",
        "stange_mm", "nut_d_mm", "nut_b_mm"
    ):
        try:
            return float(val) <= 0
        except Exception:
            return True
    # temp_max_c: nur presence check
    if key == "temp_max_c":
        try:
            float(val)
            return False
        except Exception:
            return True
    return False


def _required_fields_by_domain(domain: str) -> List[str]:
    # Hydraulik-Stange nutzt stange_mm / nut_d_mm / nut_b_mm
    if (domain or "rwdr") == "hydraulics_rod":
        return [
            "falltyp",
            "stange_mm",
            "nut_d_mm",
            "nut_b_mm",
            "medium",
            "temp_max_c",
            "druck_bar",
            "geschwindigkeit_m_s",
        ]
    # default: rwdr
    return [
        "falltyp",
        "wellen_mm",
        "gehause_mm",
        "breite_mm",
        "medium",
        "temp_max_c",
        "druck_bar",
        "drehzahl_u_min",
    ]


def _missing_by_domain(domain: str, params: Dict[str, Any]) -> List[str]:
    req = _required_fields_by_domain(domain or "rwdr")
    return [k for k in req if _is_missing_value(k, (params or {}).get(k))]

# Öffentlicher Alias (Pflicht)
missing_by_domain = _missing_by_domain

# ---------- Optional/empfohlen ----------
# Domänenspezifische Empfehl-Felder, die Qualität/Tragfähigkeit deutlich erhöhen
_RWDR_OPTIONAL = [
    "bauform", "werkstoff_pref",
    "welle_iso", "gehause_iso",
    "ra_welle_um", "rz_welle_um",
    "wellenwerkstoff", "gehausewerkstoff",
    "normen", "umgebung", "prioritaet", "besondere_anforderungen", "bekannte_probleme",
]
_HYD_OPTIONAL = [
    "profil", "werkstoff_pref",
    "stange_iso", "nut_toleranz",
    "ra_stange_um", "rz_stange_um",
    "stangenwerkstoff",
    "normen", "umgebung", "prioritaet", "besondere_anforderungen", "bekannte_probleme",
]

def _is_unset(x: Any) -> bool:
    return x in (None, "", [], "unknown")

def optional_missing_by_domain(domain: str, params: Dict[str, Any]) -> List[str]:
    p = params or {}
    fields = _HYD_OPTIONAL if (domain or "") == "hydraulics_rod" else _RWDR_OPTIONAL
    missing: List[str] = []
    for k in fields:
        if _is_unset(p.get(k)):
            missing.append(k)
    return missing

# ---- Anomalie-/Follow-up-Meldungen (FEHLTE zuvor!) --------------------------

def _anomaly_messages(domain: str, params: Dict[str, Any], derived: Dict[str, Any]) -> List[str]:
    """
    Erzeugt Rückfragen basierend auf abgeleiteten Flags (domainabhängig).
    Erwartet 'derived' z. B.: {"flags": {...}, "warnings": [...], "requirements": [...]}
    """
    msgs: List[str] = []
    flags = (derived.get("flags") or {})

    # RWDR – Druckstufenfreigabe
    if flags.get("requires_pressure_stage") and not flags.get("pressure_stage_ack"):
        msgs.append(
            "Ein Überdruck >2 bar ist für Standard-Radialdichtringe kritisch. "
            "Dürfen Druckstufenlösungen geprüft werden?"
        )

    # Hohe Drehzahl/Geschwindigkeit
    if flags.get("speed_high"):
        msgs.append("Die Drehzahl/Umfangsgeschwindigkeit ist hoch – ist sie dauerhaft oder nur kurzzeitig (Spitzen)?")

    # Sehr hohe Temperatur
    if flags.get("temp_very_high"):
        msgs.append("Die Temperatur ist sehr hoch. Handelt es sich um Dauer- oder Spitzentemperaturen?")

    # Hydraulik Stange – Extrusions-/Back-up-Ring-Freigabe
    if (domain or "") == "hydraulics_rod" and flags.get("extrusion_risk") and not flags.get("extrusion_risk_ack"):
        msgs.append("Bei dem Druck besteht Extrusionsrisiko. Darf eine Stütz-/Back-up-Ring-Lösung geprüft werden?")

    return msgs

# --- Output-Cleaner etc. (unverändert) --------------------------------------

def _strip(s: str) -> str:
    return (s or "").strip()

def _normalize_newlines(text: str) -> str:
    """Normalisiert Zeilenenden und trimmt überflüssige Leerzeichen am Zeilenende."""
    if not isinstance(text, str):
        return text
    t = re.sub(r"\r\n?|\r", "\n", text)
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    return t

def strip_leading_meta_blocks(text: str) -> str:
    """
    Entfernt am *Anfang* der Antwort Meta-Blöcke wie:
      - führende JSON-/YAML-Objekte
      - ```…``` fenced code blocks
      - '# QA-Notiz …' bis zur nächsten Leerzeile
    Wir iterieren, bis kein solcher Block mehr vorne steht.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    t = text.lstrip()

    changed = True
    # max. 5 Durchläufe als Sicherung
    for _ in range(5):
        if not changed:
            break
        changed = False

        # Fenced code block (beliebiges fence, inkl. json/yaml)
        m = re.match(r"^\s*```[\s\S]*?```\s*", t)
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue

        # Führendes JSON-/YAML-Objekt (heuristisch, nicht perfekt balanciert)
        m = re.match(r"^\s*\{[\s\S]*?\}\s*(?=\n|$)", t)
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue
        m = re.match(r"^\s*---[\s\S]*?---\s*(?=\n|$)", t)  # YAML frontmatter
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue

        # QA-Notiz-Block bis zur nächsten Leerzeile
        m = re.match(r"^\s*#\s*QA-Notiz[^\n]*\n[\s\S]*?(?:\n\s*\n|$)", t, flags=re.IGNORECASE)
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue

    return t

def clean_ai_output(ai_text: str, recent_user_texts: List[str]) -> str:
    """
    Entfernt angehängte Echos zuletzt gesagter User-Texte am Ende der AI-Ausgabe.
    - vergleicht trim-normalisiert (Suffix)
    - entfernt ganze trailing Blöcke, falls sie exakt einem der recent_user_texts entsprechen
    """
    if not isinstance(ai_text, str) or not ai_text:
        return ai_text

    out = ai_text.rstrip()

    # Prüfe Kandidaten in abnehmender Länge (stabil gegen Teilmengen)
    for u in sorted(set(recent_user_texts or []), key=len, reverse=True):
        u_s = _strip(u)
        if not u_s:
            continue

        # Work on a normalized working copy for suffix check
        norm_out = _strip(out)
        if norm_out.endswith(u_s):
            # schneide die letzte (nicht-normalisierte) Vorkommen-Stelle am Ende ab
            raw_idx = out.rstrip().rfind(u_s)
            if raw_idx != -1:
                out = out[:raw_idx].rstrip()

    return out

def _norm_key(block: str) -> str:
    """Normierungs-Schlüssel für Block-Vergleich (whitespace-/case-insensitiv)."""
    return re.sub(r"\s+", " ", (block or "").strip()).lower()

def dedupe_text_blocks(text: str) -> str:
    """
    Entfernt doppelte inhaltlich identische Absätze/Blöcke, robust gegen CRLF
    und gemischte Leerzeilen. Als Absatztrenner gilt: ≥1 (auch nur whitespace-) Leerzeile.
    Zusätzlich werden identische, aufeinanderfolgende Einzelzeilen entfernt.
    """
    if not isinstance(text, str) or not text.strip():
        return text

    t = _normalize_newlines(text)

    # Absätze anhand *mindestens* einer Leerzeile trennen (auch wenn nur Whitespace in der Leerzeile steht)
    parts = [p.strip() for p in re.split(r"\n\s*\n+", t.strip()) if p.strip()]

    seen = set()
    out_blocks = []
    for p in parts:
        k = _norm_key(p)
        if k in seen:
            continue
        seen.add(k)
        out_blocks.append(p)

    # Zusammensetzen mit Leerzeile zwischen Absätzen
    merged = "\n\n".join(out_blocks)

    # Zusätzlicher Schutz: identische direkt aufeinanderfolgende Zeilen entfernen
    final_lines = []
    prev_key = None
    for line in merged.split("\n"):
        key = _norm_key(line)
        if key and key == prev_key:
            continue
        final_lines.append(line)
        prev_key = key

    return "\n".join(final_lines)

def clean_and_dedupe(ai_text: str, recent_user_texts: List[str]) -> str:
    """
    Reihenfolge:
      1) Führende Meta-Blöcke entfernen
      2) Trailing User-Echos abschneiden
      3) Identische Absätze/Zeilen de-dupen
    """
    head_clean = strip_leading_meta_blocks(ai_text)
    tail_clean = clean_ai_output(head_clean, recent_user_texts)
    return dedupe_text_blocks(tail_clean)

# Öffentlicher Alias
anomaly_messages = _anomaly_messages
