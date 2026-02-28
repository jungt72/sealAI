# SealAI — Claude Code Projektbibel

## Was dieses Projekt ist
SealAI ist eine Engineering-Plattform für Dichtungstechnik.
Ziel-Architektur: v8 (Supervisor + 6 Agenten + Dual-Pane + Live-Berechnung)
Aktueller Stand: v8-Umbau läuft — Audit abgeschlossen Februar 2026

## Monorepo-Struktur
```
backend/          → FastAPI + LangGraph v2 (Python 3.11+)
  app/
    agents/       → 6 Spezialagenten (im Aufbau)
    mcp/          → Berechnungsmodule (deterministisch, KEIN LLM)
    sealai_state.py     → MASTER WorkingProfile — einzige Source of Truth
    sealai_graph_v2.py  → Supervisor-Graph (wird refactored)
    combinatorial_chemistry_guard.py  → NICHT ANFASSEN
    worm_evidence_node.py             → NICHT ANFASSEN
frontend/         → Next.js 16, React 18, TailwindCSS
  src/app/
    components/ChatInterface.tsx   → Haupt-Interface
    components/LiveCalcTile.tsx    → Berechnungskachel (im Aufbau)
```

## Architektur-Entscheidungen die NICHT geändert werden dürfen
1. Chemistry Guard läuft IMMER vor dem LLM-Call — niemals danach
2. Normtabellen werden NIEMALS per Vektorsuche abgefragt — nur SQL
3. Kein confidence_score — nur deterministischer Knowledge Coverage Check
4. Max 12 Turns Hard Limit — nicht verhandelbar
5. sealai_state.py ist der MASTER State — rag/state.py wird deprecatet

## Aktuelle Prioritäten (in dieser Reihenfolge)
1. State vereinheitlichen (TechnicalParameters → WorkingProfile)
2. 12-Turn Limit + Coverage Check fertigstellen
3. Knowledge Agent extrahieren
4. Calculation Engine Module implementieren

## Test-Befehl vor jedem Commit
```bash
cd backend && pytest tests/ -x -q
cd frontend && npm run build
```

## Was Claude Code NIE tun soll ohne explizite Anweisung
- combinatorial_chemistry_guard.py modifizieren
- worm_evidence_node.py modifizieren
- Datenbankmigrationen erstellen
- Docker-Konfiguration ändern
- .env Dateien anfassen
- frontend_legacy_v2/ oder frontend_backup/ anfassen
```

---

## Schritt 2: Session-Strategie

Jede Claude Code Session folgt diesem Schema:
```
1. Klares Ziel (eine Sache)
2. Explizite Grenzen (was nicht angefasst wird)  
3. Verifikationsschritt (wie wir wissen dass es funktioniert)
4. Commit-Punkt (sauberer Stand vor nächster Session)
```

---

## Die Prompts — in Reihenfolge

### Session 1 — State-Diagnose und Vereinheitlichung
```
Aufgabe: State-Modelle vereinheitlichen

Lies zuerst diese beiden Dateien vollständig:
- backend/app/sealai_state.py
- backend/app/rag/state.py (oder wo WorkingProfile definiert ist)

Dann:
1. Erstelle eine Diff-Analyse: Welche Felder existieren in TechnicalParameters 
   aber nicht in WorkingProfile, und umgekehrt?
2. Erweitere sealai_state.py um alle fehlenden Felder aus dem WorkingProfile:
   - dp_dt_bar_per_s: Optional[float]
   - side_load_kn: Optional[float]  
   - aed_required: Optional[bool]
   - medium_additives: Optional[str]
   - fluid_contamination_iso: Optional[str]
   - surface_hardness_hrc: Optional[float]
   - pressure_spike_factor: Optional[float]
   - user_persona: Optional[str]  # "erfahrener" | "einsteiger" | "entscheider"
   - knowledge_coverage: str = "limited"  # "full" | "partial" | "limited"
   - turn_count: int = 0
   - max_turns: int = 12
3. Füge oben in der Datei einen Kommentar ein: 
   "# MASTER STATE — rag/state.py ist deprecated, wird in Phase 2 entfernt"
4. Ändere NICHTS an combinatorial_chemistry_guard.py und worm_evidence_node.py

Verifikation: python3 -c "from app.sealai_state import SealAIState; print('OK')"
Committe mit: git commit -m "feat: unify state models, add WorkingProfile v2 fields"
```

---

### Session 2 — 12-Turn Limit und Coverage Check
```
Aufgabe: Deterministischen Loop-Terminator implementieren

Kontext: In sealai_graph_v2.py gibt es einen Router-Node. Wir ersetzen 
jeden confidence_score-basierten Check durch deterministischen Coverage Check.

1. Suche alle Vorkommen von "confidence_score" oder "confidence" in:
   - backend/app/sealai_graph_v2.py
   - backend/app/conversation_memory.py
   Liste sie mir zuerst auf, ändere noch nichts.

2. Implementiere diese Funktion in sealai_state.py:

def compute_knowledge_coverage(state: SealAIState, intent: str) -> str:
    """Deterministisch — kein LLM, kein confidence_score"""
    critical = [state.medium, state.pressure_bar, state.temp_range, state.dynamic_type]
    
    if intent in ["greeting", "info"]:
        return "full"
    if not all(critical):
        return "limited"
    if intent in ["complex", "safety_critical"]:
        dynamic = [state.dp_dt_bar_per_s, state.aed_required, state.medium_additives]
        if sum(1 for f in dynamic if f is None) > 1:
            return "partial"
    return "full"

3. Implementiere das Hard Limit in conversation_memory.py:

def check_turn_limit(state: SealAIState) -> dict:
    if state.turn_count >= state.max_turns:
        return {
            "output_blocked": True,
            "output_blocked_reason": (
                f"Turn-Limit ({state.max_turns}) erreicht. "
                f"Fehlende Parameter: {state.missing_critical_fields()}"
            )
        }
    return {"output_blocked": False}

4. Integriere beide Checks in sealai_graph_v2.py — NACH dem Chemistry Guard, 
   VOR dem LLM-Call. Zeig mir die Änderung bevor du sie schreibst.

Verifikation: pytest tests/ -x -q -k "coverage or turn_limit"
Commit: git commit -m "feat: deterministic coverage check, 12-turn hard limit"
```

---

### Session 3 — Knowledge Agent extrahieren
```
Aufgabe: Knowledge Agent als eigenständigen Modul extrahieren

Dies ist ein reines Refactoring — keine neue Logik.

1. Lies sealai_graph_v2.py vollständig.
2. Identifiziere alle Nodes und Branches die mit Fachfragen, 
   Norm-Erklärungen oder allgemeinem Wissen befasst sind 
   (NICHT Dichtungsauslegung, NICHT Parameterextraktion).
3. Erstelle backend/app/agents/__init__.py (leer)
4. Erstelle backend/app/agents/knowledge_agent.py mit:

   class KnowledgeAgent:
       """
       Beantwortet freie Fachfragen, Norm-Erklärungen, 
       Doktorarbeit-Recherche, Hersteller-Vergleiche.
       Kein Auslegungs-Reasoning — reines Wissen.
       Auslegungsstand bleibt beim Supervisor erhalten.
       """
       
       async def run(self, state: SealAIState, llm) -> dict:
           ...

5. Ersetze in sealai_graph_v2.py die bisherige Knowledge-Logik 
   durch einen Aufruf von KnowledgeAgent().run(state, llm)
6. Alle bisherigen Tests müssen weiterhin grün sein.

Wichtig: Wenn du unsicher bist ob ein Node zum Knowledge Agent gehört,
frage mich bevor du ihn verschiebst.

Verifikation: pytest tests/ -x -q && python3 -c "from app.agents.knowledge_agent import KnowledgeAgent; print('OK')"
Commit: git commit -m "refactor: extract KnowledgeAgent from graph"
```

---

### Session 4 — Calculation Engine, Modul 1: Umlaufgeschwindigkeit
```
Aufgabe: Erstes deterministisches Berechnungsmodul implementieren

WICHTIG: Diese Funktion verwendet KEIN LLM. Reine Mathematik nach DIN 3760.

Erstelle backend/app/mcp/calculations/__init__.py (leer)
Erstelle backend/app/mcp/calculations/rotary_speed.py:

"""
Umlaufgeschwindigkeit — DIN 3760
Kein LLM. Deterministische Berechnung.
"""
import math
from dataclasses import dataclass
from typing import Optional

@dataclass
class RotarySpeedResult:
    velocity_m_per_s: float
    shaft_diameter_mm: float
    rpm: float
    material_limits: dict[str, dict]
    recommendation: str
    norm_ref: str = "DIN 3760"

MATERIAL_VELOCITY_LIMITS = {
    "FKM":  {"max_m_per_s": 8.0,  "note": "je nach Compound 4-12 m/s"},
    "NBR":  {"max_m_per_s": 6.0,  "note": "Standard-Compound"},
    "PTFE": {"max_m_per_s": 15.0, "note": "PTFE-Lip"},
    "EPDM": {"max_m_per_s": 4.0,  "note": "eingeschränkt rotierend"},
}

def calculate_rotary_speed(
    shaft_diameter_mm: float,
    rpm: float,
    candidate_materials: list[str] | None = None,
) -> RotarySpeedResult:
    """
    v = π × d × n / 60.000 [m/s]
    d: Wellendurchmesser [mm]
    n: Drehzahl [1/min]
    """
    v = math.pi * shaft_diameter_mm * rpm / 60_000
    
    limits = {}
    if candidate_materials:
        for mat in candidate_materials:
            mat_upper = mat.upper()
            for key, data in MATERIAL_VELOCITY_LIMITS.items():
                if key in mat_upper:
                    status = "OK" if v <= data["max_m_per_s"] else "ÜBERSCHRITTEN"
                    limits[mat] = {**data, "calculated_v": round(v, 2), "status": status}
    
    recommendation = _build_recommendation(v, limits)
    
    return RotarySpeedResult(
        velocity_m_per_s=round(v, 3),
        shaft_diameter_mm=shaft_diameter_mm,
        rpm=rpm,
        material_limits=limits,
        recommendation=recommendation,
    )

def _build_recommendation(v: float, limits: dict) -> str:
    if not limits:
        return f"Umlaufgeschwindigkeit: {v:.2f} m/s — Materialprüfung ausstehend"
    blocked = [m for m, d in limits.items() if d.get("status") == "ÜBERSCHRITTEN"]
    ok = [m for m, d in limits.items() if d.get("status") == "OK"]
    parts = []
    if ok: parts.append(f"Geeignet: {', '.join(ok)}")
    if blocked: parts.append(f"Limit überschritten: {', '.join(blocked)}")
    return " | ".join(parts)

Schreibe Tests in backend/tests/test_calculations.py:
- test_rotary_speed_basic(): 80mm, 1450rpm → erwartet ~6.07 m/s
- test_rotary_speed_fkm_ok(): 50mm, 1000rpm → FKM OK
- test_rotary_speed_nbr_exceeded(): 80mm, 1500rpm → NBR ÜBERSCHRITTEN

Verifikation: pytest tests/test_calculations.py -v
Commit: git commit -m "feat: calculation engine - rotary speed DIN 3760"
```

---

### Session 5 — Persona Detection
```
Aufgabe: Persona Detection in conversation_memory.py integrieren

Basis: Regex-basiert, kein LLM, genau wie in v8-Konzept spezifiziert.

Füge in backend/app/conversation_memory.py hinzu:

import re

EXPERT_PATTERNS = [
    r"\bdp/dt\b", r"\bdruckaufbaurate\b", r"\baed\b", r"\brgd\b",
    r"\bcompound\b", r"\ba7[0-9]\b", r"\bextrusion\b", r"\bshore\b",
    r"\bhnbr\b", r"\bffkm\b", r"\bblistering\b", r"\bgalling\b",
    r"\bside.?load\b", r"\bseitenzug\b", r"\bnorsok\b",
]
BEGINNER_PATTERNS = [
    r"\bwas ist\b", r"\bwas bedeutet\b", r"\bwie funktioniert\b",
    r"\bich weiß nicht\b", r"\bkeine ahnung\b", r"\bwelche dichtung\b",
    r"\bwas.*nehme ich\b", r"\bkann ich.*nehmen\b",
]
DECIDER_PATTERNS = [
    r"\banlage steht\b", r"\bdringend\b", r"\bsofort\b",
    r"\bwas nehmen wir\b", r"\bnotfall\b", r"\bschnellste\b",
    r"\bkeine zeit\b",
]

def detect_persona(conversation_history: list[str]) -> tuple[str, float]:
    """
    Returns: (persona, confidence)
    persona: "erfahrener" | "einsteiger" | "entscheider" | "unknown"
    """
    combined = " ".join(conversation_history).lower()
    
    scores = {
        "erfahrener":  sum(1 for p in EXPERT_PATTERNS   if re.search(p, combined)),
        "einsteiger":  sum(1 for p in BEGINNER_PATTERNS  if re.search(p, combined)),
        "entscheider": sum(1 for p in DECIDER_PATTERNS   if re.search(p, combined)),
    }
    
    total = sum(scores.values())
    if total == 0:
        return "unknown", 0.0
    
    best = max(scores, key=lambda k: scores[k])
    return best, round(scores[best] / total, 2)

Rufe detect_persona() nach jedem Turn auf und speichere das Ergebnis 
in state.user_persona.

Tests:
- test_persona_expert(): FKM A75 + dp/dt + AED → "erfahrener"
- test_persona_beginner(): "was ist eine dichtung" → "einsteiger"  
- test_persona_decider(): "anlage steht sofort" → "entscheider"

Commit: git commit -m "feat: persona detection in memory manager"
