# SealAI Architecture V8.0 — Governed Agentic RFQ Qualification Runtime

**Status:** Neues finales Zielkonzept / Codex-ready Architekturgrundlage  
**Projekt:** SealAI / SealingAI — digitale Dichtungstechnik-Plattform  
**Stand:** 04.05.2026  
**Ziel:** SealAI als kontrollierte agentische RFQ-Qualifikationsplattform für Dichtungstechnik professionalisieren — ohne finale technische Freigabe durch SealAI, ohne freie Agenten-Wildnis und ohne Umgehung der bestehenden Governance-/RFQ-Grenzen.

---

## 0. Executive Summary

SealAI ist kein generischer Chatbot, kein starres Formular und kein finales Auslegungssystem. SealAI ist eine **governed agentic RFQ qualification runtime** für Dichtungstechnik.

Das bedeutet:

```text
SealAI versteht Dichtungssituationen.
SealAI strukturiert unklare technische Anforderungen.
SealAI erklärt fachliche Zusammenhänge.
SealAI erkennt fehlende, unsichere und riskante Angaben.
SealAI erzeugt eine herstellerprüfbare Anfragebasis.
SealAI kann später passende Hersteller-/Spezialistenfähigkeiten zuordnen.
SealAI gibt keine finale technische Lösung frei.
```

Die neue Leitformel:

```text
Communication Runtime entscheidet.
Capability Registry liefert Fachkontext.
LangGraph qualifiziert governed technical state.
Governor/Services validieren technische Wahrheit.
FinalAnswerLayer formuliert sichtbar.
RFQ Layer erzeugt die Anfragebasis.
Hersteller gibt final frei.
```

SealAI soll sich für den Nutzer anfühlen wie ein erfahrener, ruhiger Dichtungstechnik-Berater. Architektur- und Haftungsgrenze bleibt aber eindeutig:

```text
SealAI = Anfragequalifikation und technische Orientierung
Hersteller/Spezialist = finale technische Prüfung und Freigabe
```

---

## 1. Warum V8.0 notwendig ist

Das bisherige V7.1-Konzept war für die Kommunikationsschicht richtig und wichtig. Seitdem hat sich der Stack jedoch deutlich weiterentwickelt. Die Architektur ist nicht mehr nur ein Kommunikationsproblem, sondern ein vollständiges Runtime-/RFQ-/Projection-/Capability-System.

Der aktuelle Stand enthält bereits:

```text
- Communication Runtime V7
- TurnDecision
- RuntimeAction vor LangGraph
- active-case process/help routing
- active-case side question routing
- Resume-Reevaluation
- Side Answer Claim Policy / SpeakableFacts
- Evidence-aware active-case side answers
- RFQ/readiness RuntimeActions
- rfq_readiness_projection
- explizite RFQ Preview Action Boundary
- RfqPreviewService als einzige Preview/Export-Grenze
- disabled legacy RFQ document bypass
- Frontend Cockpit/RFQ Pane Mapping
- SSE/BFF/Workspace Contract Gates
- erste read-only Capability Registry mit Medium Intelligence
```

Damit ist V7.1 zu eng geworden. Die neue Zielarchitektur muss das Produktzentrum sauber benennen:

```text
Nicht: Communication Architecture
Sondern: Governed Agentic RFQ Qualification Runtime
```

---

## 2. Produktziel

SealAI ist eine spezialisierte digitale Plattform für Dichtungstechnik.

SealAI soll:

```text
- Dichtungssituationen verstehen
- unklare Anforderungen strukturieren
- technische Informationen im Dialog erheben
- Medien-, Material-, Anwendungs- und Risikowissen erklären
- bestehende Lösungen oder Ausfallbilder einordnen
- offene Punkte sichtbar machen
- eine RFQ-/Anfragebasis vorbereiten
- eine Herstellerprüfung effizienter machen
- später passende Hersteller-/Spezialistenfähigkeiten identifizieren
```

SealAI soll nicht:

```text
- finale Dichtungslösungen freigeben
- Herstellerverantwortung ersetzen
- Materialeignung endgültig bestätigen
- technische Grenzwerte ohne Quelle behaupten
- RFQ-Readiness erfinden
- Hersteller automatisch kontaktieren
- Export/Versand ohne explizite Zustimmung auslösen
- freie autonome Agenten ohne Governance ausführen
```

Der Hersteller bzw. Spezialist bleibt die finale technische Freigabeinstanz.

---

## 3. Strategische Positionierung

### 3.1 Was SealAI wirklich verkauft

SealAI verkauft nicht „die richtige Dichtung“. SealAI verkauft bessere technische Anfragequalität.

```text
Unklare Dichtungssituation
→ strukturierte technische Klärung
→ herstellerprüfbare Anfragebasis
→ effizientere Herstellerprüfung
```

Der wirtschaftliche Kern:

```text
User bekommt Orientierung und Struktur.
Hersteller bekommt qualifizierte Anfragen.
SealAI verbindet beide Seiten über eine technisch verwertbare RFQ-Basis.
```

### 3.2 Richtige Sprache

Statt:

```text
Dichtungslösung freigegeben
finale Auslegung
Material ist geeignet
RFQ-ready im Sinne einer Freigabe
```

soll SealAI sagen:

```text
Anfragebasis
RFQ-Basis
Herstellerprüfung
technische Einordnung
offene Punkte
noch zu klären
prüfenswert
manufacturer-review-ready basis
```

---

## 4. Architekturübersicht

```text
User Message
   ↓
Request Bootstrap
   - Auth
   - Tenant
   - Active Case
   - Pending Question
   - Workspace Projection
   - RFQ Readiness Projection
   - Policy Context
   ↓
Communication Runtime
   - Deterministic Pre-Checks
   - Optional Small Router Signal
   - Conversation Controller
   - TurnDecision
   - RuntimeAction
   ↓
RuntimeAction Gate
   - ANSWER_ONLY
   - ANSWER_THEN_RESUME
   - ROUTE_SLOT_CANDIDATE
   - ENTER_GOVERNED_GRAPH
   - SHOW_RFQ_READINESS
   - ANSWER_RFQ_STATUS
   - DEFER_RFQ_UNTIL_REQUIRED_FIELDS
   ↓
Capability Registry
   - read-only Fachkontexte
   - candidate facts
   - context notes
   - risk notes
   - RFQ relevance notes
   - evidence refs
   ↓
Governed Technical Execution
   - LangGraph nur wenn RuntimeAction es erlaubt
   - normalize
   - assert
   - evidence
   - compute
   - risk/readiness
   - output contract
   ↓
Final Answer Boundary
   - answer_markdown
   - claim policy
   - speakable facts
   - evidence policy
   - deterministic fallback
   ↓
Output
   - answer_markdown
   - answer_trace
   - workspace/cockpit projection
   - rfq_readiness_projection
   - preview action metadata
```

---

## 5. Architekturprinzipien

### 5.1 Eine explizite Runtime-Entscheidung pro User-Turn

Jeder User-Turn muss eine nachvollziehbare Runtime-Entscheidung bekommen.

```text
User Turn
→ TurnDecision
→ RuntimeAction
→ genau definierter Pfad
```

Keine Route darf „zufällig“ in LangGraph fallen, nur weil ein aktiver Case existiert.

### 5.2 RuntimeAction schützt LangGraph

LangGraph bleibt die governed Fachmaschine. RuntimeAction sitzt davor.

```text
Nur RuntimeActionType.ENTER_GOVERNED_GRAPH darf graph_allowed=true setzen.
```

Alles andere ist bewusst graph-bypassed:

```text
- active_case_process_question
- active_case_side_question
- knowledge_override
- no-case knowledge
- RFQ readiness answer
- fast/light answer
```

### 5.3 Backend bleibt technische Wahrheit

LLM-/Composer-/Capability-Ausgaben dürfen keine technische Wahrheit direkt setzen.

Technische Wahrheit entsteht nur über:

```text
- validierte Case-Mutation
- deterministische Services
- governed LangGraph-Pfade
- Revision/Projection
- Evidence und Provenance
```

### 5.4 Chat erklärt, Cockpit strukturiert

```text
Cockpit = strukturierte technische Wahrheit
Chat = sprachliche Erklärung, Führung und Kontextualisierung
```

Der Chat darf Cockpit-Zustand erklären, aber nicht widersprechen oder eigene technische Wahrheit erzeugen.

### 5.5 RFQ ist Produktzentrum

RFQ ist kein später Export. RFQ ist ein laufender Produktzustand:

```text
Was wissen wir?
Was fehlt?
Was ist unsicher?
Was blockiert Herstellerprüfung?
Ist eine Preview möglich?
Welche Zustimmung fehlt?
```

---

## 6. Communication Runtime

Die Communication Runtime ist die Eingangskontrolle für jeden User-Turn.

Sie entscheidet:

```text
- Ist das eine Antwort auf die letzte Frage?
- Enthält der Turn eine technische Angabe?
- Ist es eine Side Question?
- Ist es eine Prozess-/Hilfefrage?
- Ist es Knowledge im aktiven Case?
- Ist es RFQ-/Anfrage-Intent?
- Muss LangGraph laufen?
- Muss nur geantwortet und resumed werden?
```

Sie erzeugt keine technische Wahrheit.

---

## 7. TurnDecision

Ein User-Turn kann mehrere Bedeutungen gleichzeitig haben.

Beispiel:

```text
„EPDM wäre für Wasser besser — wir hätten Wasser mit etwas Reinigerzusatz.“
```

Das ist gleichzeitig:

```text
- Wissens-/Vergleichsfrage
- Antwort auf pending_question = Medium
- neue technische Angabe
- mögliche falsche Annahme
- anwendungsrelevante Mediumspezifikation
```

Deshalb bleibt `TurnDecision` ein zentraler Baustein.

### 7.1 Entscheidungspriorität

```text
1. Safety / blocked
2. Explicit correction
3. Pending-slot answer
4. New technical facts
5. Active-case side question
6. Meta/process question
7. RFQ/readiness intent
8. No-case knowledge
9. Smalltalk
10. Unclear / clarification
```

Diese Reihenfolge priorisiert State-Aktionen. Die sichtbare Antwort darf zusätzliche Antwortpflichten erfüllen.

---

## 8. MutationPolicy

SealAI nutzt weiterhin vier Mutation Policies:

```text
forbidden
- Keine Case-Mutation.
- Side Question, Prozessfrage, Smalltalk, reine Erklärung.

proposed
- Mögliche technische Information.
- Als Kandidat behandeln, nicht final bestätigen.

allowed_by_validator
- Backend darf nach deterministischer Validierung State aktualisieren.

correction
- User korrigiert frühere Angabe.
- Konflikt, Stale Dependencies und Recompute auslösen.
```

Beispiele:

| User-Turn | mutation_policy |
|---|---|
| „Was bedeutet Medium?“ | forbidden |
| „Ist Ra 0,3 µm okay?“ | proposed |
| „Wasser“ nach Medium-Frage | allowed_by_validator |
| „Eigentlich ist es statisch, keine Welle.“ | correction |
| „Kann ich die Anfrage senden?“ | forbidden / RFQ boundary action |

---

## 9. RuntimeAction

`RuntimeAction` ist der operative Vertrag zwischen Communication Runtime und LangGraph.

### 9.1 Action Types

Erlaubte Action Types:

```text
ANSWER_ONLY
ANSWER_THEN_RESUME
ROUTE_SLOT_CANDIDATE
ENTER_GOVERNED_GRAPH
SHOW_RFQ_READINESS
ANSWER_RFQ_STATUS
DEFER_RFQ_UNTIL_REQUIRED_FIELDS
WAIT_FOR_USER
```

Optional später:

```text
BUILD_RFQ_PREVIEW_ACTION_AVAILABLE
CAPABILITY_CONTEXT_ONLY
```

### 9.2 Pflichtfelder

```json
{
  "action_type": "ANSWER_THEN_RESUME",
  "answer_mode": "active_case_side_question",
  "runtime_answer_builder": "active_case_side_answer",
  "graph_allowed": false,
  "graph_entry_reason": null,
  "graph_invocation_skipped_reason": "active_case_side_question_answer_only",
  "mutation_policy": "forbidden",
  "decision_source": "conversation_controller_v7",
  "operational_contract_version": "runtime_action_v1"
}
```

### 9.3 Graph-Regel

```text
RuntimeActionType.ENTER_GOVERNED_GRAPH
→ graph_allowed=true

Alle anderen Action Types
→ graph_allowed=false
```

Diese Regel darf nicht aufgeweicht werden.

---

## 10. LangGraph

LangGraph bleibt die governed technische Ausführungsschicht.

LangGraph ist zuständig für:

```text
- Intake Observation
- Unit Normalization
- Assertion / Validation
- Evidence Retrieval
- Deterministic Calculations
- Risk / Readiness
- Matching-Vorbereitung
- Output Contract
```

LangGraph darf nur laufen, wenn RuntimeAction es explizit erlaubt.

LangGraph soll nicht:

```text
- Smalltalk beantworten
- Prozessfragen beantworten
- aktive Side Questions erzwingen
- RFQ Preview außerhalb RfqPreviewService erzeugen
- finale sichtbare Antwort allein besitzen
```

---

## 11. Capability Registry

### 11.1 Zweck

Die Capability Registry ist ein read-only Fachfähigkeiten-Layer.

Sie macht vorhandene Fachservices auffindbar, typisiert und sicher nutzbar, ohne eine zweite Orchestrierungsschicht zu schaffen.

```text
Capability Registry = read-only Fachkontext
Nicht = autonomer Agenten-Orchestrator
```

### 11.2 Grundregel

Capability Outputs dürfen:

```text
- candidate facts liefern
- Kontext erklären
- Risiken notieren
- missing-field hints liefern
- RFQ-Relevanz notieren
- Evidence refs liefern
- Confidence/Validation Status angeben
```

Capability Outputs dürfen nicht:

```text
- Case State mutieren
- Engineering Truth erzeugen
- answer_markdown als finale Antwort bauen
- LangGraph aufrufen
- RfqPreviewService aufrufen
- Export/Dispatch/Contact auslösen
- finale Freigabe behaupten
```

### 11.3 Safety Flags

Jeder CapabilityResult enthält:

```json
{
  "mutates_case_state": false,
  "creates_engineering_truth": false,
  "final_approval_claim_allowed": false,
  "dispatch_allowed": false,
  "external_contact_allowed": false,
  "export_allowed": false
}
```

### 11.4 Erste Capabilities

Bereits begonnen:

```text
medium_intelligence
```

Nächste sinnvolle Capabilities:

```text
application_machine_context
risk_completeness
material_seal_type_context
manufacturer_capability_matching
```

---

## 12. Medium Intelligence Capability

Die Medium Intelligence Capability adaptiert den bestehenden MediumIntelligenceService.

Sie soll:

```text
- bekannte Medien einordnen
- unbekannte Medien als niedriges Vertrauen / unvalidiert markieren
- RFQ-relevante Hinweise liefern
- fehlende Details benennen
- Risiken vorsichtig nennen
```

Sie soll nicht:

```text
- Material endgültig empfehlen
- Medienbeständigkeit freigeben
- Werte erfinden
- Case-State schreiben
```

Beispiel Output:

```json
{
  "capability_id": "medium_intelligence",
  "input_summary": "HLP46",
  "candidate_facts": [
    {
      "field": "medium",
      "value": "HLP46",
      "status": "candidate",
      "validation_status": "registry_grounded"
    }
  ],
  "context_notes": [
    "HLP46 ist typischerweise ein Hydrauliköl-Kontext und für die Dichtungsauswahl RFQ-relevant."
  ],
  "missing_field_hints": [
    "Temperaturbereich",
    "Druck",
    "Drehzahl oder Bewegung",
    "Werkstoff-/Freigabeanforderungen"
  ],
  "rfq_relevance_notes": [
    "Das Medium sollte in der Anfragebasis mit möglichst genauer Spezifikation genannt werden."
  ],
  "safety": {
    "mutates_case_state": false,
    "creates_engineering_truth": false,
    "final_approval_claim_allowed": false,
    "dispatch_allowed": false,
    "external_contact_allowed": false,
    "export_allowed": false
  }
}
```

---

## 13. RFQ Readiness Projection

`rfq_readiness_projection` ist der zentrale Produktzustand für Anfragefähigkeit.

### 13.1 Pflichtfelder

```json
{
  "manufacturer_review_ready": false,
  "rfq_basis_ready": false,
  "known_missing_fields": [],
  "open_points": [],
  "blocking_reasons": [],
  "pending_question": {
    "question_text": "...",
    "target_field": "medium",
    "required_for_rfq": true
  },
  "consent_required": true,
  "dispatch_allowed": false,
  "external_contact_allowed": false,
  "final_approval_claim_allowed": false,
  "preview_available": false,
  "preview_possible": true,
  "preview_action_available": true,
  "preview_action_name": "create_preview",
  "preview_endpoint": "/api/bff/rfq/{caseId}/preview",
  "preview_creation_requires_explicit_user_intent": true,
  "preview_export_requires_consent": true,
  "preview_requires_explicit_endpoint": true,
  "preview_service_boundary": "RfqPreviewService.create_preview_for_case",
  "projection_version": "rfq_readiness_projection_v1"
}
```

### 13.2 Regeln

```text
Workspace GET darf diese Projection liefern.
SSE darf diese Projection liefern.
BFF darf sie weiterreichen.
Frontend darf sie anzeigen.
Preview-Erstellung darf dadurch nicht automatisch ausgelöst werden.
```

---

## 14. RFQ Preview Boundary

RFQ Preview darf nur über die explizite Action Boundary entstehen.

### 14.1 Verboten

```text
Chat erzeugt Preview heimlich.
Workspace GET erzeugt Preview.
SSE erzeugt Preview.
Legacy document route liefert RFQ HTML.
Frontend dokumentUrl zeigt alten HTML-Export.
```

### 14.2 Erlaubter Pfad

```text
User explizit: Vorschau erstellen
↓
BFF POST /api/bff/rfq/{caseId}/preview
↓
Body:
{
  "action": "create_preview",
  "explicit_user_intent": true,
  "expected_case_revision": optional,
  "dispatch_allowed": false,
  "external_contact_allowed": false
}
↓
Backend Endpoint validiert
↓
RfqPreviewService.create_preview_for_case(...)
↓
Preview entsteht revision-aware und tenant/user-scoped
↓
Kein Export
↓
Kein Herstellerkontakt
```

### 14.3 Export / Versand

Export und Herstellerkontakt bleiben getrennte, explizit consent-gated Aktionen.

```text
Preview != Export
Export != Manufacturer Contact
Manufacturer Contact != automatic dispatch
```

---

## 15. Legacy RFQ Document Routes

Legacy RFQ document routes müssen dauerhaft deaktiviert bleiben.

Alte Pfade dürfen nicht mehr:

```text
- RFQ HTML rendern
- gespeicherte HTML Reports ausgeben
- documentUrl aus legacy has_html_report ableiten
```

Stattdessen:

```json
{
  "error": {
    "code": "rfq_document_legacy_disabled",
    "message": "Use the governed RFQ preview/export flow."
  },
  "dispatch_allowed": false,
  "external_contact_allowed": false,
  "export_requires_consent": true,
  "final_approval_claim_allowed": false,
  "preview_service_boundary": "RfqPreviewService.create_preview_for_case"
}
```

---

## 16. FinalAnswerLayer

Der FinalAnswerLayer bleibt die sichtbare Antwortgrenze.

### 16.1 Aufgabe

Er entscheidet:

```text
- Composer nutzen
- Fallback nutzen
- Claim Guard anwenden
- Safety Response nutzen
- answer_markdown setzen
```

### 16.2 Input

```json
{
  "answer_mode": "active_case_side_question",
  "runtime_action": {},
  "turn_decision": {},
  "deterministic_fallback_reply": "...",
  "case_summary": {},
  "evidence_items": [],
  "speakable_facts": [],
  "claim_policy": {},
  "rfq_readiness_projection": {},
  "capability_outputs": []
}
```

### 16.3 Output

```json
{
  "reply": "deterministic fallback",
  "answer_markdown": "final visible answer",
  "answer_trace": {
    "final_visible_source": "answer_markdown",
    "answer_mode": "active_case_side_question",
    "runtime_action_type": "ANSWER_THEN_RESUME",
    "composer_attempted": true,
    "composer_succeeded": true,
    "claim_policy_applied": true
  }
}
```

---

## 17. Claim Policy

Claim Policy gilt auf drei Ebenen:

```text
1. sichtbare Antworten
2. RFQ Readiness / Preview Copy
3. Capability Outputs
```

### 17.1 Claim Levels

```text
L1 — allgemeines Fachwissen
L2 — anwendungsnahe Orientierung
L3 — backend/evidence-gestützte Vorbewertung
L4 — finale Freigabe
```

L4 ist verboten.

### 17.2 Verbotene Formulierungen

```text
- freigegeben
- final approved
- approved solution
- certified recommendation
- garantiert geeignet
- garantiert beständig
- zertifiziert
- beste Lösung
- Material ist geeignet
- Herstellerkontakt wurde ausgelöst
- Auslegungsfreigabe
```

### 17.3 Erlaubte sichere Formulierungen

```text
- technische Einordnung
- vorläufige Orientierung
- Anfragebasis
- RFQ-Basis
- Herstellerprüfung
- offene Punkte
- noch zu klären
- prüfenswert
- abhängig von Medium, Temperatur, Druck, Drehzahl, Welle und Einbauraum
```

---

## 18. Evidence / RAG Strategy

### 18.1 Modellwissen reicht für

```text
- allgemeine Grundlagen
- Materialfamilien
- Dichtungsprinzipien
- typische Risiken
- Begriffserklärungen
```

### 18.2 Evidence erforderlich für

```text
- Herstellerdatenblätter
- konkrete Compound-Daten
- Normen
- Zulassungen
- PFAS/REACH/ECHA-Aktualität
- kundenspezifische Dokumente
- Lieferantenfähigkeiten
```

Bei aktueller Regulierung ohne Quelle:

```text
technische Orientierung ja,
verbindliche rechtliche Bewertung nein.
```

---

## 19. Chat / Cockpit UX

### 19.1 Chat

Chat ist:

```text
- natürlich
- technisch präzise
- kurz erklärend
- fallbezogen
- resume-fähig
```

Chat ist nicht:

```text
- die technische Wahrheit selbst
- ein freier LLM-Raum
- ein Ersatz für Cockpit
```

### 19.2 Cockpit

Cockpit zeigt:

```text
- strukturierte Case-Felder
- Feldstatus
- RFQ Readiness
- offene Punkte
- fehlende Angaben
- Vorschau-Aktion
- keine Versand-/Kontakt-Aktion ohne Consent
```

### 19.3 RfqPane

RfqPane muss anzeigen:

```text
- Anfragebasis-Status
- Herstellerprüfung-Readiness
- fehlende Felder
- offene Punkte
- blocking reasons
- Preview möglich?
- Vorschau erstellen
- noch nicht versendet
- Zustimmung für Export erforderlich
```

---

## 20. Contract Gates

RFQ Readiness muss dauerhaft durch Contract Gates geschützt bleiben.

Abgesicherte Pfade:

```text
Backend builder
→ shared fixture
→ durable workspace projection
→ backend SSE state_update
→ frontend BFF chat stream
→ frontend BFF workspace reload
→ frontend mapping
→ streamWorkspace
→ RfqPane
```

Die Fixture:

```text
contracts/rfq_readiness_projection_v1.fixture.json
```

muss dauerhaft als Drift-Schutz bleiben.

---

## 21. Testing Strategy

### 21.1 Permanente Testgruppen

```text
RuntimeAction / LangGraph Gate
RFQ Readiness RuntimeAction
RFQ Projection Contract
RFQ Preview Endpoint
Legacy RFQ Document Disabled
BFF Preview Contract
BFF Workspace Reload Contract
BFF Stream Contract
RfqPane Rendering
Capability Registry Tests
Capability Architecture Guards
```

### 21.2 Golden Conversations

Das V7.1 Golden Set bleibt gültig, muss aber auf V8 erweitert werden.

Pflichtfälle:

```text
1. neue Dichtungssituation starten
2. pending medium: Wasser
3. pending medium: Chlor
4. side question: Wellenrauheit
5. side question with value: Ra 0,3 µm
6. correction: eigentlich statisch, keine Welle
7. FKM vs EPDM no-case
8. PFAS
9. Salzwasser
10. RWDR leckt nach 6 Monaten
11. warum fragst du das?
12. was ist FKM im aktiven Case?
13. ist meine Anfrage vollständig?
14. was fehlt noch für den Hersteller?
15. erstelle mir eine Anfrage
16. kann ich das an Hersteller schicken?
17. Vorschau erstellen
18. Preview ja, Export nein
19. unbekanntes Medium
20. HLP46 Medium Intelligence
```

---

## 22. Patch Roadmap ab V8

### Phase A — Stabilisierung abgeschlossen

Bereits erreicht oder nahezu erreicht:

```text
- active-case routing
- resume reevaluation
- side answer safety
- evidence-aware side answers
- RuntimeAction before LangGraph
- RFQ readiness runtime actions
- RFQ projection
- preview service boundary
- legacy RFQ bypass disabled
- frontend/bff/reload contract gates
```

### Phase B — Capability Registry read-only

```text
B1 — Medium Intelligence Capability Registry
B2 — Capability Registry Architecture Guard
B3 — Application/Machine Context Capability
B4 — Risk/Completeness Capability
B5 — Material/Seal-Type Context Capability
```

### Phase C — Controlled Integration

Erst wenn Phase B stabil ist:

```text
- RuntimeAction kann Capability Outputs lesen
- Side Answer kann Capability Context bekommen
- LangGraph kann Capability Outputs als candidate/context nutzen
- FinalAnswerLayer kann capability_speakable_facts nutzen
```

Regel:

```text
Capability Output wird nie automatisch technische Wahrheit.
```

### Phase D — Manufacturer Capability Matching

Später:

```text
Problem Signature
→ Required Capabilities
→ Manufacturer Capability Fit
→ Transparent Gaps
→ Sponsored visibility separate
→ no ranking ambiguity
```

---

## 23. Akzeptanzkriterien V8

V8 ist erfolgreich, wenn:

```text
1. RuntimeAction ist expliziter Pre-LangGraph Contract.
2. Nur ENTER_GOVERNED_GRAPH erlaubt graph_allowed=true.
3. LangGraph bleibt governed technical engine.
4. RFQ Readiness ist über Chat/SSE/Workspace/BFF/Frontend stabil.
5. RFQ Preview läuft nur über RfqPreviewService.
6. Legacy RFQ Document Routes bleiben disabled.
7. Capability Registry ist read-only und bounded.
8. Capability Outputs mutieren keinen Case-State.
9. FinalAnswerLayer bleibt sichtbare Antwortgrenze.
10. Claim Policy blockt Freigabe-/Eignungs-/Guarantee-Claims.
11. RfqPane zeigt Anfragebasis, offene Punkte und Preview-Aktion sicher.
12. Keine Dispatch-/Contact-Aktion ohne explizite Zustimmung.
13. Contract Fixtures verhindern Schema-Drift.
14. Golden Conversations erreichen Mittelwert >= 1.5 / 2.
15. Keine L4-/Freigabe-Verletzung im Golden Set.
```

---

## 24. Nicht-Ziele

```text
- kein Greenfield-Rewrite
- kein Full-LangGraph-Rewrite
- keine freien autonomen Agenten
- kein beliebig tiefer Side-Task-Stack
- kein automatischer Herstellerkontakt
- kein RFQ-Export ohne Consent
- keine finale technische Freigabe
- kein LLM-Judge als Pflicht
- kein Web-Search-Zwang für jeden Turn
- kein Frontend-Redesign als Teil der Architektur
- keine eigene Modellentwicklung
```

---

## 25. Codex Arbeitsregel ab V8

Jeder Codex-Patch muss beantworten:

```text
1. Welche Boundary wird verändert?
2. Bleibt RuntimeAction vor LangGraph intakt?
3. Wird LangGraph nur bei ENTER_GOVERNED_GRAPH betreten?
4. Wird technische Wahrheit nur governed erzeugt?
5. Bleibt RfqPreviewService die einzige Preview/Export-Grenze?
6. Gibt es neue User-visible Claims?
7. Bleibt answer_markdown die sichtbare Antwort?
8. Sind Chat/SSE/Workspace/BFF/Frontend Contracts betroffen?
9. Gibt es Tests für die Boundary?
10. Wurde kein Herstellerkontakt/Export/Dispatch hinzugefügt?
```

---

## 26. Finales Fazit

SealAI ist auf dem richtigen Weg.

Die Architektur hat sich sinnvoll weiterentwickelt:

```text
V7.1 Communication Architecture
→ V8 Governed Agentic RFQ Qualification Runtime
```

Der Fokus ist jetzt klarer, sicherer und geschäftlich besser:

```text
SealAI entwickelt nicht die finale Dichtungslösung.
SealAI erzeugt die bestmögliche technische Anfragebasis für die Herstellerprüfung.
```

Das ist der Sweet Spot:

```text
hochwertige technische Beratung
+
strukturierte Case-/RFQ-Daten
+
kontrollierte Agentik
+
klare Herstellerfreigabegrenze
```

Diese Spezifikation ist die neue Codex-Arbeitsgrundlage für alle weiteren Architektur- und Capability-Patches.

