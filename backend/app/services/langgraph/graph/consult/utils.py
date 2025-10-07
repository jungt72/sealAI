from __future__ import annotations

import logging
import re
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple, Set

from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage, SystemMessage

log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Hashbare Hilfen für Dedup (dict/list -> stabile Schlüssel)
# -------------------------------------------------------------------

def _hashable_key(x: Any) -> Any:
    if isinstance(x, dict):
        # JSON-stabile, reihenfolgeunabhängige Repräsentation
        try:
            return json.dumps(x, sort_keys=True, ensure_ascii=False)
        except Exception:
            return tuple(sorted((str(k), _hashable_key(v)) for k, v in x.items()))
    if isinstance(x, (list, tuple, set)):
        return tuple(_hashable_key(v) for v in x)
    # Messages/Objekte -> auf Inhalt mappen, sonst str(x)
    if isinstance(x, (HumanMessage, AIMessage, SystemMessage)):
        return ("msg", x.__class__.__name__, getattr(x, "content", ""))
    return x if isinstance(x, (str, int, float, bool, type(None))) else str(x)

def dedup_stable(seq: Iterable[Any]) -> List[Any]:
    out: List[Any] = []
    seen: Set[Any] = set()
    for item in (seq or []):
        k = _hashable_key(item)
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out

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
# Domänenspezifische Empfehl-Felder
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

def _optional_fields_by_domain(domain: str) -> List[str]:
    if (domain or "rwdr") == "hydraulics_rod":
        return list(_HYD_OPTIONAL)
    return list(_RWDR_OPTIONAL)

def _optional_missing_by_domain(domain: str, params: Dict[str, Any]) -> List[str]:
    opt = _optional_fields_by_domain(domain or "rwdr")
    return [k for k in opt if _is_missing_value(k, (params or {}).get(k))]

# Öffentlicher Alias
optional_missing_by_domain = _optional_missing_by_domain

# -------------------------------------------------------------------
# Friendly-Namen & Anomalien
# -------------------------------------------------------------------

_FRIENDLY_RWDR = {
    "falltyp": "Falltyp",
    "wellen_mm": "Welle (mm)",
    "gehause_mm": "Gehäuse (mm)",
    "breite_mm": "Breite (mm)",
    "medium": "Medium",
    "temp_max_c": "Temperatur max (°C)",
    "druck_bar": "Überdruck (bar)",
    "drehzahl_u_min": "Drehzahl (U/min)",
    # optional
    "bauform": "Bauform",
    "werkstoff_pref": "Werkstoff-Präferenz",
    "welle_iso": "Welle ISO-Toleranz",
    "gehause_iso": "Gehäuse ISO-Toleranz",
    "ra_welle_um": "Rauheit Ra Welle (µm)",
    "rz_welle_um": "Rauheit Rz Welle (µm)",
    "wellenwerkstoff": "Wellenwerkstoff",
    "gehausewerkstoff": "Gehäusewerkstoff",
    "normen": "Normen",
    "umgebung": "Umgebung",
    "prioritaet": "Priorität",
    "besondere_anforderungen": "Besondere Anforderungen",
    "bekannte_probleme": "Bekannte Probleme",
}

_FRIENDLY_HYD = {
    "falltyp": "Falltyp",
    "stange_mm": "Stange (mm)",
    "nut_d_mm": "Nut-Ø (mm)",
    "nut_b_mm": "Nutbreite (mm)",
    "medium": "Medium",
    "temp_max_c": "Temperatur max (°C)",
    "druck_bar": "Druck (bar)",
    "geschwindigkeit_m_s": "Geschwindigkeit (m/s)",
    # optional
    "profil": "Profil",
    "werkstoff_pref": "Werkstoff-Präferenz",
    "stange_iso": "Stange ISO-Toleranz",
    "nut_toleranz": "Nut-Toleranz",
    "ra_stange_um": "Rauheit Ra Stange (µm)",
    "rz_stange_um": "Rauheit Rz Stange (µm)",
    "stangenwerkstoff": "Stangenwerkstoff",
    "normen": "Normen",
    "umgebung": "Umgebung",
    "prioritaet": "Priorität",
    "besondere_anforderungen": "Besondere Anforderungen",
    "bekannte_probleme": "Bekannte Probleme",
}

def _friendly_map(domain: str) -> Dict[str, str]:
    return _FRIENDLY_HYD if (domain or "rwdr") == "hydraulics_rod" else _FRIENDLY_RWDR

def friendly_required_list(domain: str, missing_keys: List[str]) -> str:
    fm = _friendly_map(domain)
    return ", ".join(fm.get(k, k) for k in (missing_keys or []))

def friendly_optional_list(domain: str, missing_keys: List[str]) -> str:
    fm = _friendly_map(domain)
    return ", ".join(fm.get(k, k) for k in (missing_keys or []))

def anomaly_messages(domain: str, params: Dict[str, Any], derived: Dict[str, Any] | None = None) -> List[str]:
    """Einfache Plausibilitätsprüfungen -> kurze Follow-up-Fragen."""
    msgs: List[str] = []
    d = (domain or "rwdr")
    p = params or {}

    def _f(name: str) -> Optional[float]:
        try:
            v = p.get(name)
            if v is None or v == "" or v == "unknown":
                return None
            return float(v)
        except Exception:
            return None

    if d == "rwdr":
        w = _f("wellen_mm"); g = _f("gehause_mm"); b = _f("breite_mm")
        if w and g and w >= g:
            msgs.append("Ist der Wellen-Ø möglicherweise kleiner als der Gehäuse-Ø?")
        if b and w and b > w * 0.8:
            msgs.append("Die Breite wirkt im Verhältnis zum Wellen-Ø ungewöhnlich hoch – bitte prüfen.")
        rpm = _f("drehzahl_u_min")
        if rpm is not None and rpm < 0:
            msgs.append("Drehzahl ist negativ – bitte prüfen.")
    else:  # hydraulics_rod
        s = _f("stange_mm"); nd = _f("nut_d_mm"); nb = _f("nut_b_mm")
        if s and nd and s >= nd:
            msgs.append("Ist der Stangen-Ø möglicherweise kleiner als der Nut-Ø?")
        v = _f("geschwindigkeit_m_s")
        if v is not None and v < 0:
            msgs.append("Geschwindigkeit ist negativ – bitte prüfen.")

    tmax = _f("temp_max_c")
    if tmax is not None and (tmax < -50 or tmax > 300):
        msgs.append("Die Temperatur liegt außerhalb des üblichen Bereichs (−50…300 °C) – korrekt?")

    return msgs

# -------------------------------------------------------------------
# Stable unique + sort for recent_user_texts (ohne set(dict)-Crash)
# -------------------------------------------------------------------
def recent_user_texts_sorted_unique(recent_user_texts: Iterable[Any]) -> List[str]:
    """
    Ersetzt 'sorted(set(recent_user_texts or []), ...)' durch eine sichere Variante.
    - Castet Elemente robust zu String
    - Dedup via Insertion-Order (dict.fromkeys)
    """
    texts = [str(u) for u in (recent_user_texts or [])]
    uniq = list(dict.fromkeys(texts))  # preserves order, no unhashable dict
    return sorted(uniq, key=len, reverse=True)
