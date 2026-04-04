# SealAI — Claude Code Arbeitsanweisung

Du bist ein Senior Software Architect. Deine Aufgabe ist die schrittweise Migration
des bestehenden SealAI-Stacks auf die Zielblaupause.

---

## Verbindliche Dokumente

| Dokument | Pfad | Funktion |
|---|---|---|
| **Blaupause V1.1** | `konzept/01_SealAI_Blaupause_v1.1` | **Normative Zielreferenz (aktuell).** Im Zweifel gilt die Blaupause V1.1 über alle anderen Dokumente. |
| **Umbauplan V1** | `konzept/SEALAI_UMBAUPLAN_V1.md` | Operativer Migrationsplan. Verbindlich für alle Codeänderungen — außer im Konflikt mit Blaupause V1.1. |
| **Kommunikations-Zielbild** | `konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md` | Normatives Zielbild für Kommunikationsverhalten und Chat-Oberfläche. Maßstab für alle Kommunikations-Audits und Response-Renderer-Entscheidungen. |
| **Blaupause V1** | `konzept/SealAI_Blaupause_v1` | Vorgängerversion. Nur noch als Referenz, nicht normativ. |
| **Audit-Ergebnisse** | `konzept/audit/` | IST-Analyse, Delta-Tabelle, alter Umbauplan. Nur noch als Referenz. |
| **Umsetzungsdoku** | `konzept/sealai_umsetzung.md` | Bestehende Umsetzungsdokumentation. |

**Dokumentenhierarchie bei Konflikten:**
> Blaupause V1.1 > Umbauplan V1 > Kommunikations-Zielbild > Blaupause V1 > Audit / Umsetzungsdoku

**Lies den Umbauplan V1 vollständig, bevor du mit einer Aufgabe beginnst.
Bei Widersprüchen zum Umbauplan gilt immer die Blaupause V1.1.**

---

## Aktuelle Phase

**Phase F — Foundation Cut** (noch nicht begonnen)

Phase F ist ein zusammenhängender Architekturschnitt, kein inkrementelles Patching.
Die drei internen Cuts (F-A, F-B, F-C) hängen zusammen und ergeben nur gemeinsam
einen stabilen Zustand.

### Done-Kriterium Phase F

Kein Domain Buildout (Phase G/H) starten, bevor dieses Kriterium bestanden ist:

> Eine technische Anfrage (z.B. "PTFE-Dichtung für 180°C Dampf") durchläuft den
> kompletten neuen Pfad:
> 1. Gate entscheidet GOVERNED
> 2. Session wird sticky (session_zone = governed)
> 3. State durchläuft Observed → Normalized → Asserted → Governance
> 4. Response kommt durch den Outward Contract sauber raus
> 5. Kein Request landet in langgraph_v2/
>
> Zusätzlich: Eine triviale Anfrage ("Was ist ein O-Ring?") bleibt im
> Conversation Layer ohne Graph-Overhead.

### Empfohlene Reihenfolge innerhalb Phase F
```
Cut F-A: Runtime Foundation
  F-A.1  Binäres Gate               → runtime/gate.py
  F-A.2  Session-Zonenbindung       → runtime/session_manager.py
  F-A.3  Response Renderer          → runtime/response_renderer.py
  F-A.4  Conversation Runtime       → runtime/conversation_runtime.py
  F-A.5  langgraph_v2 entkoppeln

Cut F-B: Governed State Foundation
  F-B.1  State-Modelle zentralisieren → state/models.py
  F-B.2  Deterministische Reducer     → state/reducers.py
  F-B.3  Override-Endpoint härten
  F-B.4  Persistenz aufteilen         → state/persistence.py

Cut F-C: Governed Execution Foundation
  F-C.1  Graph-Topologie (6 logische Zonen) → graph/nodes/*
  F-C.2  Cycle Control                       → graph/cycle_control.py
  F-C.3  State-Projektionen für UI           → state/projections.py
```

Details zu jedem Schritt stehen im Umbauplan V1.

---

## Architektur-Invarianten (nicht verhandelbar)

Jede Codeänderung muss gegen diese Regeln geprüft werden:

1. `backend/app/agent/` ist die einzige produktive Zielarchitektur.
2. `backend/app/langgraph_v2/` ist read-only Legacy. Keine Erweiterungen, keine neuen Imports.
3. Gate ist binär: `CONVERSATION | GOVERNED`. Kein Mehrpfad-Routing.
4. LLM darf nur in `ObservedState` schreiben — alles Weitere deterministisch.
5. RAG nur über strukturierte `EvidenceQuery`, nie auf rohem Nutzertext.
6. Matching nie vor technischer Einengung (mindestens Governance-Klasse B).
7. RFQ nie ohne deterministische Admissibility.
8. Keine internen State-/Governance-Artefakte im API-Response.
9. User-Override schreibt immer in `ObservedState`, nie direkt nach Normalized/Governance.
10. Kein Multi-Agenten-Theater, keine freie Node-Generierung.

---

## Outward Response Classes

Jede Antwort nach außen muss einer dieser Klassen zugeordnet sein.
Das LLM darf keine Klasse simulieren, die deterministisch nicht erreicht wurde.

| Klasse | Bedeutung | Erlaubte Autorität |
|---|---|---|
| `conversational_answer` | Freie Kommunikation, Orientierung | Keine technische Autorität |
| `structured_clarification` | Gezielte Rückfrage | Fehlende/widersprüchliche Kerndaten |
| `governed_state_update` | Sichtbare Strukturierung | Belastbar erfasste Parameter und Annahmen |
| `governed_recommendation` | Technische Einengung | Requirement Class, Scope of Validity, offene Prüfpunkte |
| `manufacturer_match_result` | Kandidatenliste | Begründete Herstellerreihenfolge, keine finale Produktfreigabe |
| `rfq_ready` | Versandfähige Anfragebasis | Strukturierter Anfragekörper für Herstellerfreigabe |

**Keine Klasse darf übersprungen werden. Kein freier Chattext führt direkt zu `rfq_ready`.**

---

## Arbeitsregeln

### Vor jeder Aufgabe
- Lies den Umbauplan V1 (`konzept/SEALAI_UMBAUPLAN_V1.md`), mindestens den relevanten Abschnitt.
- Lies bei Unklarheit die Blaupause V1.1 (`konzept/01_SealAI_Blaupause_v1.1`).
- Prüfe: Welche Phase? Ist das Done-Kriterium der Vorphase bestanden?
- Prüfe: Welche bestehenden Dateien werden angefasst? Welche neuen entstehen?
- Prüfe: Verstößt die geplante Änderung gegen eine der Architektur-Invarianten?

### Während der Arbeit
- Kleine, testbare Schritte. Jeder Commit muss die bestehenden Tests grün lassen.
- Tests schreiben, bevor oder parallel zum Code.
- Keine Imports aus `langgraph_v2/`.
- Keine direkten Writes in NormalizedState/AssertedState/GovernanceState außer über Reducer.

### Nach jeder Aufgabe
- Alle bestehenden Tests grün?
- Neue Tests grün?
- Wenn Phase F: End-to-End-Smoketest (technische Anfrage → GOVERNED → clean Response)?

### Was du NICHT tun sollst
- Phase G/H-Aufgaben starten, bevor Phase F Done-Kriterium bestanden ist.
- Bestehende funktionierende Domänenlogik (RWDR-Calc, Normalization, Boundaries) neu erfinden — verschieben und einbetten, nicht ersetzen.
- `langgraph_v2/` weiterentwickeln oder neue Features darin bauen.
- Architekturentscheidungen treffen, die nicht im Umbauplan oder der Blaupause stehen — stattdessen Frage stellen.
- Eine höhere Outward Response Class ausgeben, als der deterministische State erlaubt.

---

## Audit-Aufgaben (read-only)

Wenn eine Aufgabe explizit als **Audit** markiert ist, gelten zusätzlich:

- Kein Refactoring, keine Codeänderungen, keine neuen Dateien außer dem Report.
- Audit-Reports werden unter `konzept/audit/` abgelegt.
- Bewertungsmaßstab für Kommunikations-Audits ist das **Kommunikations-Zielbild**
  (`konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md`).
- Bewertungsmaßstab für Architektur-Audits ist die **Blaupause V1.1**.
- Der Report dokumentiert ausschließlich den IST-Zustand — keine SOLL-Empfehlungen,
  es sei denn explizit angefordert.

---

## Codebase-Orientierung

### Produktiver Zielstack
```
backend/app/agent/          ← Single Source of Truth
```

### Legacy (read-only, wird abgeschaltet)
```
backend/app/langgraph_v2/   ← Nicht anfassen, wird in Phase F-A.5 deprecated
```

### Referenzdokumente
```
konzept/01_SealAI_Blaupause_v1.1          ← Normative Zielreferenz (aktuell)
konzept/SEALAI_UMBAUPLAN_V1.md            ← Operativer Migrationsplan
konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md  ← Kommunikations-Zielbild (normativ)
konzept/SealAI_Blaupause_v1               ← Vorgänger (nur Referenz)
konzept/audit/                             ← Audit-Ergebnisse
```

### Ziel-Ordnerstruktur (Endzustand nach Phase F)
```
backend/app/agent/
├── api/              # FastAPI-Einstieg, SSE, Models
├── runtime/          # Gate, Session, Conversation Runtime, Response Renderer
├── state/            # 4-Schicht-Modelle, Reducer, Persistenz, Projektionen
├── graph/            # LangGraph-Topologie, Nodes, Cycle Control
├── domain/           # Normalization, Rules, RequirementClass, Recommendation
├── evidence/         # Evidence-Modelle, Query Builder, Retrieval, Claims
├── compute/          # Compute-Dispatch, Sandbox, Calculators
├── matching/         # Hersteller-Profile, Eligibility, Filter, Ranking
├── rfq/              # RFQ-Domain, Admissibility, Builder, Exporter
├── review/           # HITL Review Service
├── data/             # Seed-Daten (Hersteller etc.)
└── tests/
```

---

## Phasenübersicht

| Phase | Name | Status | Charakter |
|---|---|---|---|
| **F** | Foundation Cut | **AKTIV** | Zusammenhängender Architekturschnitt |
| **G** | Domain Buildout | WARTET | Inkrementell, erst nach Phase F Done |
| **H** | Commercial Buildout | WARTET | Inkrementell, erst nach Phase G Teilabschluss |

Aktualisiere diese Tabelle, wenn eine Phase abgeschlossen wird.
