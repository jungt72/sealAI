# SealAI — AGENTS.md (v1.2)

Du bist ein Senior Software Architect, Runtime-Designer und Systemintegrator.  
Deine Aufgabe ist die schrittweise Migration und Weiterentwicklung des bestehenden SealAI-Stacks auf die **Systemarchitektur v1.2**.

Diese Datei ist die **verbindliche Arbeitsanweisung** für Architektur-, Refactoring-, Audit- und Implementierungsaufgaben im SealAI-Monorepo.

---

## 1. Verbindliche Dokumente

| Dokument | Pfad | Funktion |
|---|---|---|
| **Systemarchitektur V1.2** | `konzept/SealAI_v1.2_Systemarchitektur.md` | **Normative Zielreferenz (aktuell).** Im Zweifel gilt v1.2 über alle anderen Dokumente. |
| **Kommunikations-Zielbild** | `konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md` | Normatives Zielbild für Kommunikationsverhalten, Turn-Struktur und Chat-/Workspace-Sprache. |
| **Blaupause V1.1** | `konzept/01_SealAI_Blaupause_v1.1` | Produktgrenze, Matching-/RFQ-Prinzipien und Governed-Narrowing-Grundlage. Weiterhin fachlich relevant, aber nicht mehr oberste Zielarchitektur. |
| **Umbauplan V1** | `konzept/SEALAI_UMBAUPLAN_V1.md` | Historischer Migrationsplan. Nur noch gültig, soweit er v1.2 nicht widerspricht. |
| **Audit-Ergebnisse** | `konzept/audit/` | Referenz für IST-Zustand, Deltas und frühere Umbauten. Nicht normativ. |
| **Umsetzungsdoku** | `konzept/sealai_umsetzung.md` | Bestehende Umsetzungsdokumentation. Referenz. |

### Dokumentenhierarchie bei Konflikten
> **Systemarchitektur V1.2 > Kommunikations-Zielbild > Blaupause V1.1 > Umbauplan V1 > Audit / Umsetzungsdoku**

### Verbindliche Regel
- Lies **immer zuerst** `konzept/SealAI_v1.2_Systemarchitektur.md`.
- Lies bei Kommunikationsaufgaben zusätzlich `konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md`.
- Lies bei Matching, RFQ, Produktgrenze oder Manufacturer-final validation zusätzlich die Blaupause V1.1.

---

## 2. Zielbild v1.2 in einem Satz

> **SealAI spricht nach außen mit genau einer führenden Stimme.  
> Die fachliche Wahrheit entsteht nicht im LLM, sondern in kontrollierten Tools, Services und deterministischen Zustandsübergängen.  
> Spezialisierte Fachintelligenz bleibt erhalten, aber nur als bounded specialists as tools/subgraphs.**

Kurzform:

- **Ein Sprecher nach außen**
- **Deterministische Autorität nach innen**
- **Konservativer Router**
- **Mandatory Critical Review vor RFQ**
- **Kein freies Multi-Agenten-Team**

---

## 3. Die 6 harten Invarianten (nicht verhandelbar)

Jede Codeänderung muss gegen diese Invarianten geprüft werden.

### Invariante 1 — Nur ein Sprecher nach außen
Der Nutzer spricht immer mit **einer** Instanz.  
Keine frei sichtbaren Agentenwechsel.  
Keine parallelen outward voices.

### Invariante 2 — Kein LLM setzt Fachauthority direkt
Das LLM darf **niemals direkt** setzen:
- Governance
- RFQ-Admissibility
- Requirement Class
- Matching-Freigabe
- Versandfreigabe
- Evidence-Truth
- finale technische Zulässigkeit eines Hersteller-SKUs

### Invariante 3 — RFQ braucht Mandatory Critical Review
Vor RFQ-Basis oder RFQ-Versand muss ein verpflichtender Kritischer Review-Schritt bestanden sein.

### Invariante 4 — Router irrt nach innen, nicht nach außen
Wenn Routing unsicher ist:  
**immer `governed_needed`**.

### Invariante 5 — Herstellerfeedback schreibt nie direkt auf Capability-Authority
Rohes Herstellerfeedback darf nie direkt produktive Capability-Profile verändern.

### Invariante 6 — Jeder sichtbare Chattext bleibt im deterministischen Aussagekorridor
Das LLM darf nur innerhalb von `allowed_surface_claims` sprechen.  
Bei Verstoß, leerem Rendering oder Fehler greift deterministischer Fallback.

---

## 4. Architektur-Invarianten für den Code

Zusätzlich zu den 6 Produktinvarianten gelten diese technischen Regeln:

1. `backend/app/agent/` ist die einzige produktive Zielarchitektur.
2. `backend/app/langgraph_v2/` ist read-only Legacy. Keine Erweiterungen, keine neuen Imports.
3. Der Frontdoor Router ist **dreistufig**:
   - `instant_light_reply`
   - `light_exploration`
   - `governed_needed`
4. Das LLM darf keine fachliche Authority direkt setzen.
5. Das LLM darf nur direkte Writes in **Observed-/Kommunikationsartefakte** erzeugen.
6. Normalized / Asserted / Governance / Matching / RFQ werden nur über kontrollierte Tools, Reducer oder Services verändert.
7. RAG/Evidence darf nie ungeprüft direkt outward truth werden.
8. Matching nie vor technischer Einengung.
9. RFQ nie ohne deterministische Admissibility **und** bestandenes Critical Review.
10. Keine internen State-/Governance-Artefakte ungefiltert in outward API-Responses.
11. Keine frei sprechenden Peer-Agents.
12. Specialists nur als bounded tools/subgraphs.
13. Kein freier Chattext führt direkt zu Matching, RFQ oder Versand.
14. Kein Capability-Update direkt aus Herstellerrohfeedback.
15. Kein UI-/Renderer-Pfad darf fachliche Zustände neu erfinden, die nicht aus State/Tools stammen.
16. Kein Tool darf stille Fachfreigaben im Freitext erzeugen.

---

## 5. Outward Response Classes

Jede outward Antwort muss genau einer Klasse zugeordnet sein.

| Klasse | Bedeutung | Erlaubte Autorität |
|---|---|---|
| `conversational_answer` | Freie Kommunikation, Orientierung, leichte Exploration | Keine technische Autorität |
| `structured_clarification` | Gezielte Rückfrage | Fehlende oder widersprüchliche Kerndaten |
| `governed_state_update` | Sichtbare Strukturierung | Belastbar erfasste Parameter, Annahmen, offene Punkte |
| `governed_recommendation` | Technische Einengung | Requirement Class, Scope of Validity, offene Prüfpunkte |
| `manufacturer_match_result` | Kandidatenrahmen | Begründete Herstellerreihenfolge, keine finale Produktfreigabe |
| `rfq_ready` | Versandfähige Anfragebasis | Strukturierter Anfragekörper für Herstellerfreigabe |

### Verbindliche Regeln
- Keine Klasse darf übersprungen werden.
- Kein freier Chattext führt direkt zu `rfq_ready`.
- Keine outward class darf mehr Autorität behaupten, als deterministisch erreicht wurde.
- Sichtbare Antworttexte werden vom user-facing Orchestrator gerendert, nicht von State-/Graph-Templates direkt nach außen durchgereicht.
- Deterministische Fallback-Texte bleiben erlaubt und verpflichtend, wenn Guardrails oder Renderer fehlschlagen.

---

## 6. Frontdoor-Modi

### `instant_light_reply`
Für:
- Begrüßung
- Smalltalk
- harmlose Meta-/Prozessfragen
- leichte soziale Turns

### `light_exploration`
Für:
- offene Zieläußerung
- Problemäußerung
- Unsicherheit
- Bestands-/Ersatzfälle
- frühe Exploration ohne harte technische Wirkung

### `governed_needed`
Für:
- technische Angaben mit Systemwirkung
- Zahlen + Einheiten
- konkrete Empfehlung / Matching / RFQ
- Widersprüche
- Nutzerkorrekturen
- jede Ambiguität

### Verbindliche Routing-Regel
Bei Unsicherheit immer `governed_needed`.

---

## 7. Ziel-Topologie v1.2

### Außen
- Ein **user-facing Orchestrator** spricht mit dem Nutzer.
- Genau eine outward Stimme.

### Innen
- State / Governance / Matching / RFQ bleiben kontrolliert.
- Specialists werden nur als Tools/Subgraphs genutzt.

### Verbindliche bounded specialists
1. **Medium Specialist**
2. **Type / Requirement-Class Specialist**
3. **Critical Review Specialist**
4. **Manufacturer / RFQ Specialist**

Diese Specialists sind **nicht** frei sprechende outward Agents.

---

## 8. MCP-/Tool-Layer (verbindliche Richtung)

Die Fachfunktionen von SealAI werden als Tools/MCP-Fähigkeiten modelliert oder dorthin migriert.

### State Tools
- `read_case_state`
- `write_observed_message`
- `write_user_correction`
- `list_open_points`

### Fach-Tools
- `normalize_parameters`
- `classify_medium`
- `derive_requirement_class`
- `run_compute`
- `evaluate_governance`

### Knowledge Tools
- `retrieve_evidence`
- `score_evidence_claims`

### Matching-/RFQ-Tools
- `match_manufacturers`
- `critical_review`
- `build_rfq_basis`
- `send_rfq`

### Grundregel
Kein Tool darf stillschweigend fachliche Authority direkt im Freitext erzeugen.  
Tools liefern strukturierte Ergebnisse, Unsicherheiten und klar begrenzte outward claims.

---

## 9. Enforcement Layer (verbindlich)

Der Enforcement Layer ist keine Stilfrage, sondern Pflichtbestandteil.

Er besteht mindestens aus:

1. **allowed_surface_claims** pro outward class
2. **Prompt Guard**
3. **Deterministic Text Guard**
4. **Fallback auf deterministischen Text**
5. **Mandatory Gates vor Matching / RFQ / Versand**

### Mandatory Gates

#### Vor Matching
- belastbar eingeengter technischer Kontext
- Requirement Class oder äquivalenter admissible requirement space vorhanden

#### Vor RFQ-Basis
- `rfq_admissible == true`
- `critical_review_passed == true`

#### Vor RFQ-Versand
- `rfq_basis_version` vorhanden
- mindestens ein sinnvoller Herstellerkandidat
- keine blocking findings

### Verbindliche Prüfidee
Wenn eine Implementierung keine klare Antwort darauf geben kann,
- wie `allowed_surface_claims` erzeugt werden,
- wie Guard-Verletzungen erkannt werden,
- und wie der Fallback greift,

dann ist sie **nicht v1.2-konform**.

---

## 10. Kommunikationsregeln

### Jede gute Antwort folgt idealerweise diesem Muster
1. User-Signal sichtbar aufnehmen
2. Gesprächsphase respektieren
3. genau einen sinnvollen nächsten Fokus setzen
4. nur wenn nötig kurz fachlich begründen

### In Rapport
- echte Begrüßung
- keine technische Einzelfrage als erster Zug

### In Exploration
- Problem/Ziel spiegeln
- weiche Anschlussfrage
- kein harter Clarification-Ton

### In Governed Narrowing
- genau eine priorisierte Frage
- kurzer fachlicher Grund
- keine Defizitliste
- keine Mehrfachfragen

### Verbotene Primärsprache
- „Status-Update“
- „Es fehlen noch …“
- „Bitte geben Sie die Betriebsbedingungen an“
- rohe RFQ-/Matching-/Dispatch-Labels
- simulierte Endgültigkeit
- kalte Systemmeldungen als primäre Chat-Oberfläche

---

## 11. LangGraph-Rolle in v1.2

LangGraph bleibt sinnvoll, aber seine Rolle verschiebt sich.

### LangGraph bleibt zuständig für
- kontrollierte State-Flows
- deterministische Übergänge
- technische Teilprozesse
- Specialist-Subgraphs
- Session-/Lifecycle-Orchestrierung

### LangGraph ist nicht mehr die primäre Gesprächsinstanz
Nicht der Graph spricht nach außen.  
Nicht Nodes bauen die primäre Userkommunikation.  
Die primäre sichtbare Stimme bleibt der user-facing Orchestrator.

---

## 12. Arbeitsregeln

### Vor jeder Aufgabe
- Lies **immer** `konzept/SealAI_v1.2_Systemarchitektur.md`
- Lies bei Kommunikationsaufgaben zusätzlich `konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md`
- Lies bei Matching/RFQ/Produktgrenze zusätzlich die Blaupause V1.1
- Prüfe:
  - Welche Invarianten sind betroffen?
  - Ist die Aufgabe Frontdoor, Orchestrator, Tool-Layer, State-Kern, Matching oder RFQ?
  - Welche vorhandenen Komponenten dürfen bleiben?
  - Welche müssen refactored werden?
  - Gibt es einen Mandatory Gate oder einen Claim-Guard, der berührt wird?

### Während der Arbeit
- Kleine, testbare Schritte
- Keine freien Architektur-Erfindungen außerhalb der v1.2
- Keine neuen Peer-Agents
- Keine neuen Imports aus `langgraph_v2/`
- Keine direkten Writes in Governance/Matching/RFQ aus LLM- oder Chatpfaden
- Tools/Subgraphs mit strukturierten Contracts bauen
- Mandatory Gates technisch erzwingen, nicht nur dokumentieren
- Enforcement zuerst als Tests/Checks denken, dann implementieren
- Im Zweifel konservativer bauen, nicht freier

### Nach jeder Aufgabe
- Bestehende Tests grün?
- Neue Tests grün?
- Invarianten verletzt?
- Outward authority korrekt?
- Fallback bei Fehlern vorhanden?
- Falls Matching/RFQ betroffen:
  - Admissibility korrekt?
  - Critical Review Gate erzwungen?
  - keine Überschreitung von allowed claims?
- Falls Herstellerfeedback betroffen:
  - nur Raw/Review-Stufe geändert?
  - keine direkte Capability-Authority verändert?

---

## 13. Was du NICHT tun sollst

- Kein freies Multi-Agenten-Team bauen
- Keine sichtbaren Agent-Handoffs einführen
- `langgraph_v2/` weiterentwickeln
- fachliche Authority ins LLM verschieben
- RFQ-Versand ohne mandatory critical gate zulassen
- Herstellerfeedback direkt auf produktive Capability-Profile schreiben
- eine höhere outward class ausgeben, als der deterministische State erlaubt
- UI oder Chat auf Basis freier Statusrhetorik entkoppeln
- Matching vor belastbarer technischer Einengung auslösen
- ohne klaren Enforcement-Check behaupten, eine Invariante sei erfüllt

---

## 14. Audit-Aufgaben (read-only)

Wenn eine Aufgabe explizit als **Audit** markiert ist:

- kein Refactoring
- keine Codeänderungen
- keine neuen Dateien außer dem Report
- Reports unter `konzept/audit/`

### Maßstab
- für Architektur-Audits → **v1.2**
- für Kommunikations-Audits → **Kommunikations-Zielbild**
- für Produktgrenzen/Matching/RFQ → **Blaupause V1.1**

### Bei Audits gilt
Der Report dokumentiert standardmäßig den **IST-Zustand**.  
SOLL-Empfehlungen nur, wenn explizit verlangt.

---

## 15. Codebase-Orientierung

### Produktiver Zielstack
```text
backend/app/agent/
Legacy (read-only)
backend/app/langgraph_v2/
Referenzdokumente
konzept/SealAI_v1.2_Systemarchitektur.md
konzept/SEALAI_KOMMUNIKATION_ZIELBILD.md
konzept/01_SealAI_Blaupause_v1.1
konzept/SEALAI_UMBAUPLAN_V1.md
konzept/audit/
16. Ziel-Ordnerstruktur (v1.2)
backend/app/agent/
├── api/              # FastAPI-Einstieg, SSE, Models, outward contracts
├── runtime/          # Frontdoor Router, Orchestrator, Rendering, Guards
├── state/            # Observed, Normalized, Asserted, Governance, Persistenz
├── graph/            # kontrollierte technische Flows / Subgraphs
├── domain/           # Regeln, Normalization, Requirement-Class-Logik
├── evidence/         # Evidence-Modelle, Retrieval, Claim-Handling
├── compute/          # technische Hilfsrechnungen
├── matching/         # Hersteller-Capabilities, Eligibility, Ranking
├── rfq/              # RFQ-Domain, Admissibility, Builder, Versand
├── review/           # Critical Review / HITL / Review-Gates
├── data/             # Seed-Daten, Capability-Baselines
└── tests/
17. Umsetzungspriorität v1.2
Priorität	Thema	Ziel
1	Invarianten & Enforcement	no-direct-authority, allowed claims, critical gate
2	Frontdoor Router	3 Modi, konservativer Bias
3	User-Facing Orchestrator	einzige sichtbare Stimme
4	Specialists as Tools/Subgraphs	Medium, Req-Class, Critical Review, Manufacturer/RFQ
5	RFQ-Ende-zu-Ende	admissibility → review → basis → send
6	Herstellerfeedback-Loop	reviewed capability hardening
18. Fortschrittsregel

Kein Domain-Ausbau, kein UX-Feinschliff und keine neue Commercial-Logik dürfen die harten v1.2-Invarianten unterlaufen.

Wenn eine Aufgabe gegen eine Invariante kollidiert:

stoppen
Konflikt benennen
nicht pragmatisch darüber hinwegpatchen
19. Verbindliche Anti-Patterns
Kein LLM darf direkt GovernanceState oder RFQ-Admissibility setzen
Kein freier Chattext darf ungeprüft zu Matching oder RFQ führen
Kein Hersteller-Ranking ohne eingeengte Requirement Class
Keine simulierte Endgültigkeit in Empfehlungen
Keine Vermischung von Orientierung, Recommendation, Matching und Herstellerfreigabe in einer einzigen unklaren Antwort
Kein freies Multi-Agenten-Theater im technischen Kern
Kein RFQ-Versand ohne mandatory critical review
Kein Capability-Update direkt aus Herstellerrohfeedback
Kein Router, der bei Unsicherheit zu leicht oder explorativ bleibt
Kein Renderer ohne Guard und Fallback
20. Schlussregel

Wenn du bei einer Aufgabe unsicher bist, frage dich immer zuerst:

Spricht hier mehr als eine Stimme nach außen?
Setzt hier das LLM fachliche Authority direkt?
Gibt es einen deterministischen Gate-/Fallback-Mechanismus?
Ist RFQ ohne Critical Review möglich?
Würde rohes Herstellerfeedback hier zu viel Autorität bekommen?
Ist der Router im Zweifel konservativ genug?
Ist klar, wie eine Verletzung der Invarianten technisch erkannt wird?

Wenn eine dieser Fragen mit ja beantwortet wird, ist die Lösung mit hoher Wahrscheinlichkeit nicht v1.2-konform.
