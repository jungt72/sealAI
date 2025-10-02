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

# Kompatibilit\u00e4ts-Alias (einige Module importieren 'msgs_text')
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
      - 'kein/ohne \u00dcberdruck/Druck' -> druck_bar = 0
      - '... Druck: 5 bar'          -> druck_bar = 5
      - 'Drehzahl 1.200 U/min'      -> drehzahl_u_min = 1200
      - 'dauerhaft X U/min'         -> drehzahl_u_min = X
      - 'Geschwindigkeit 0.5 m/s'   -> geschwindigkeit_m_s = 0.5
    """
    t = (text or "").lower()
    merged: Dict[str, Any] = dict(params or {})

    # Druck
    if merged.get("druck_bar") in (None, "", "unknown"):
        if re.search(r"\b(kein|ohne)\s+(\u00fcberdruck|ueberdruck|druck)\b", t, re.I):
            merged["druck_bar"] = 0.0
        else:
            m = re.search(r"(?:\u00fcberdruck|ueberdruck|druck)\s*[:=]?\s*([0-9][\d\.\s,]*)\s*bar\b", t, re.I)
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
    # 0 bar ist g\u00fcltig
    if key == "druck_bar":
        try:
            float(val)
            return False
        except Exception:
            return True
    # Positive Gr\u00f6\u00dfen brauchen > 0
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

# \u00d6ffentlicher Alias (Pflicht)
missing_by_domain = _missing_by_domain

# ---------- Optional/empfohlen ----------
# Dom\u00e4nenspezifische Empfehl-Felder, die Qualit\u00e4t/Tragf\u00e4higkeit deutlich erh\u00f6hen
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


FIELD_LABELS_RWDR = {
    "falltyp": "Anwendungsfall (Ersatz/Neu/Optimierung)",
    "wellen_mm": "Welle (mm)",
    "gehause_mm": "Geh\u00e4use (mm)",
    "breite_mm": "Breite (mm)",
    "bauform": "Bauform/Profil",
    "medium": "Medium",
    "temp_min_c": "Temperatur min (\u00b0C)",
    "temp_max_c": "Temperatur max (\u00b0C)",
    "druck_bar": "Druck (bar)",
    "drehzahl_u_min": "Drehzahl (U/min)",
    "geschwindigkeit_m_s": "Relativgeschwindigkeit (m/s)",
    "umgebung": "Umgebung",
    "prioritaet": "Priorit\u00e4t (z. B. Preis, Lebensdauer)",
    "besondere_anforderungen": "Besondere Anforderungen",
    "bekannte_probleme": "Bekannte Probleme",
    "werkstoff_pref": "Werkstoffpr\u00e4ferenz",
    "welle_iso": "Welle ISO-Toleranz",
    "gehause_iso": "Geh\u00e4use ISO-Toleranz",
    "ra_welle_um": "Ra Welle (\u00b5m)",
    "rz_welle_um": "Rz Welle (\u00b5m)",
    "wellenwerkstoff": "Werkstoff Welle",
    "gehausewerkstoff": "Werkstoff Geh\u00e4use",
    "normen": "Normen/Vorgaben",
}
DISPLAY_ORDER_RWDR = [
    "falltyp",
    "wellen_mm",
    "gehause_mm",
    "breite_mm",
    "bauform",
    "medium",
    "temp_min_c",
    "temp_max_c",
    "druck_bar",
    "drehzahl_u_min",
    "geschwindigkeit_m_s",
    "umgebung",
    "prioritaet",
    "besondere_anforderungen",
    "bekannte_probleme",
]

FIELD_LABELS_HYD = {
    "falltyp": "Anwendungsfall (Ersatz/Neu/Optimierung)",
    "stange_mm": "Stange (mm)",
    "nut_d_mm": "Nut-\u00d8 D (mm)",
    "nut_b_mm": "Nutbreite B (mm)",
    "medium": "Medium",
    "temp_max_c": "Temperatur max (\u00b0C)",
    "temp_min_c": "Temperatur min (\u00b0C)",
    "druck_bar": "Druck (bar)",
    "geschwindigkeit_m_s": "Relativgeschwindigkeit (m/s)",
    "profil": "Profil/Bauform",
    "werkstoff_pref": "Werkstoffpr\u00e4ferenz",
    "stange_iso": "Stange ISO-Toleranz",
    "nut_toleranz": "Nut Toleranz",
    "ra_stange_um": "Ra Stange (\u00b5m)",
    "rz_stange_um": "Rz Stange (\u00b5m)",
    "stangenwerkstoff": "Werkstoff Stange",
    "normen": "Normen/Vorgaben",
    "umgebung": "Umgebung",
    "prioritaet": "Priorit\u00e4t (z. B. Preis, Lebensdauer)",
    "besondere_anforderungen": "Besondere Anforderungen",
    "bekannte_probleme": "Bekannte Probleme",
}
DISPLAY_ORDER_HYD = [
    "falltyp",
    "stange_mm",
    "nut_d_mm",
    "nut_b_mm",
    "medium",
    "temp_max_c",
    "temp_min_c",
    "druck_bar",
    "geschwindigkeit_m_s",
    "profil",
    "werkstoff_pref",
    "stange_iso",
    "nut_toleranz",
    "ra_stange_um",
    "rz_stange_um",
    "stangenwerkstoff",
    "normen",
    "umgebung",
    "prioritaet",
    "besondere_anforderungen",
    "bekannte_probleme",
]

def _labels_for_domain(domain: str) -> Dict[str, str]:
    d = (domain or "rwdr").strip().lower()
    return FIELD_LABELS_HYD if d == "hydraulics_rod" else FIELD_LABELS_RWDR

def _required_order_for_domain(domain: str) -> List[str]:
    d = (domain or "rwdr").strip().lower()
    return DISPLAY_ORDER_HYD if d == "hydraulics_rod" else DISPLAY_ORDER_RWDR

def _optional_order_for_domain(domain: str) -> List[str]:
    d = (domain or "rwdr").strip().lower()
    return _HYD_OPTIONAL if d == "hydraulics_rod" else _RWDR_OPTIONAL

def _friendly_from_keys(keys: List[str], labels: Dict[str, str], order: List[str]) -> List[str]:
    if not keys:
        return []
    seen = set()
    friendly: List[str] = []
    for key in order:
        if key in keys and key not in seen:
            friendly.append(labels.get(key, key))
            seen.add(key)
    for key in keys:
        if key not in seen:
            friendly.append(labels.get(key, key))
            seen.add(key)
    return friendly

def friendly_required_list(domain: str, keys: List[str]) -> str:
    if not keys:
        return ""
    labels = _labels_for_domain(domain)
    order = _required_order_for_domain(domain)
    friendly = _friendly_from_keys(list(keys), labels, order)
    return ", ".join(f"**{label}**" for label in friendly)

def friendly_optional_list(domain: str, keys: List[str], limit: int = 6) -> str:
    if not keys:
        return ""
    labels = _labels_for_domain(domain)
    order = _optional_order_for_domain(domain)
    friendly = _friendly_from_keys(list(keys), labels, order)
    if limit and limit > 0:
        friendly = friendly[:limit]
    return ", ".join(f"**{label}**" for label in friendly)

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
    Erzeugt R\u00fcckfragen basierend auf abgeleiteten Flags (domainabh\u00e4ngig).
    Erwartet 'derived' z. B.: {"flags": {...}, "warnings": [...], "requirements": [...]}
    """
    msgs: List[str] = []
    flags = (derived.get("flags") or {})

    # RWDR – Druckstufenfreigabe
    if flags.get("requires_pressure_stage") and not flags.get("pressure_stage_ack"):
        msgs.append(
            "Ein \u00dcberdruck >2 bar ist f\u00fcr Standard-Radialdichtringe kritisch. "
            "D\u00fcrfen Druckstufenl\u00f6sungen gepr\u00fcft werden?"
        )

    # Hohe Drehzahl/Geschwindigkeit
    if flags.get("speed_high"):
        msgs.append("Die Drehzahl/Umfangsgeschwindigkeit ist hoch – ist sie dauerhaft oder nur kurzzeitig (Spitzen)?")

    # Sehr hohe Temperatur
    if flags.get("temp_very_high"):
        msgs.append("Die Temperatur ist sehr hoch. Handelt es sich um Dauer- oder Spitzentemperaturen?")

    # Hydraulik Stange – Extrusions-/Back-up-Ring-Freigabe
    if (domain or "") == "hydraulics_rod" and flags.get("extrusion_risk") and not flags.get("extrusion_risk_ack"):
        msgs.append("Bei dem Druck besteht Extrusionsrisiko. Darf eine St\u00fctz-/Back-up-Ring-L\u00f6sung gepr\u00fcft werden?")

    return msgs

# --- Output-Cleaner etc. (unver\u00e4ndert) --------------------------------------

def _strip(s: str) -> str:
    return (s or "").strip()

def _normalize_newlines(text: str) -> str:
    """Normalisiert Zeilenenden und trimmt \u00fcberfl\u00fcssige Leerzeichen am Zeilenende."""
    if not isinstance(text, str):
        return text
    t = re.sub(r"\r\n?|\r", "\n", text)
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    return t

def strip_leading_meta_blocks(text: str) -> str:
    """
    Entfernt am *Anfang* der Antwort Meta-Bl\u00f6cke wie:
      - f\u00fchrende JSON-/YAML-Objekte
      - ```…``` fenced code blocks
      - '# QA-Notiz …' bis zur n\u00e4chsten Leerzeile
    Wir iterieren, bis kein solcher Block mehr vorne steht.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    t = text.lstrip()

    changed = True
    # max. 5 Durchl\u00e4ufe als Sicherung
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

        # F\u00fchrendes JSON-/YAML-Objekt (heuristisch, nicht perfekt balanciert)
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

        # QA-Notiz-Block bis zur n\u00e4chsten Leerzeile
        m = re.match(r"^\s*#\s*QA-Notiz[^\n]*\n[\s\S]*?(?:\n\s*\n|$)", t, flags=re.IGNORECASE)
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue

    return t

def clean_ai_output(ai_text: str, recent_user_texts: List[str]) -> str:
    """
    Entfernt angeh\u00e4ngte Echos zuletzt gesagter User-Texte am Ende der AI-Ausgabe.
    - vergleicht trim-normalisiert (Suffix)
    - entfernt ganze trailing Bl\u00f6cke, falls sie exakt einem der recent_user_texts entsprechen
    """
    if not isinstance(ai_text, str) or not ai_text:
        return ai_text

    out = ai_text.rstrip()

    # Pr\u00fcfe Kandidaten in abnehmender L\u00e4nge (stabil gegen Teilmengen)
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
    """Normierungs-Schl\u00fcssel f\u00fcr Block-Vergleich (whitespace-/case-insensitiv)."""
    return re.sub(r"\s+", " ", (block or "").strip()).lower()

def dedupe_text_blocks(text: str) -> str:
    """
    Entfernt doppelte inhaltlich identische Abs\u00e4tze/Bl\u00f6cke, robust gegen CRLF
    und gemischte Leerzeilen. Als Absatztrenner gilt: ≥1 (auch nur whitespace-) Leerzeile.
    Zus\u00e4tzlich werden identische, aufeinanderfolgende Einzelzeilen entfernt.
    """
    if not isinstance(text, str) or not text.strip():
        return text

    t = _normalize_newlines(text)

    # Abs\u00e4tze anhand *mindestens* einer Leerzeile trennen (auch wenn nur Whitespace in der Leerzeile steht)
    parts = [p.strip() for p in re.split(r"\n\s*\n+", t.strip()) if p.strip()]

    seen = set()
    out_blocks = []
    for p in parts:
        k = _norm_key(p)
        if k in seen:
            continue
        seen.add(k)
        out_blocks.append(p)

    # Zusammensetzen mit Leerzeile zwischen Abs\u00e4tzen
    merged = "\n\n".join(out_blocks)

    # Zus\u00e4tzlicher Schutz: identische direkt aufeinanderfolgende Zeilen entfernen
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
      1) F\u00fchrende Meta-Bl\u00f6cke entfernen
      2) Trailing User-Echos abschneiden
      3) Identische Abs\u00e4tze/Zeilen de-dupen
    """
    head_clean = strip_leading_meta_blocks(ai_text)
    tail_clean = clean_ai_output(head_clean, recent_user_texts)
    return dedupe_text_blocks(tail_clean)

# \u00d6ffentlicher Alias
anomaly_messages = _anomaly_messages
