# sealing | Intelligence V1.7 — Universal Sealing Case Platform

**Architecture Blueprint (Architektur-Schicht über V1.6)**

**Stand:** 2026-06-03
**Produkt:** sealing | Intelligence / sealingAI
**Produktidentität:** Engineering-Intelligence-Plattform für die **gesamte industrielle Dichtungstechnik**
**Erster produktionsreifer Domain Pack:** Radialwellendichtringe (RWDR)
**Zielgruppe dieses Dokuments:** Architektur-Review und Codex (Audit-first-Implementierung im bestehenden Monorepo)

---

## Verhältnis zu V1.6

V1.7 ersetzt V1.6 **nicht**, sondern legt die Architektur-Schicht darüber.

```text
V1.6  = operative Contracts (Mode-Contracts, Schemas, UX-Regeln, Golden Conversations) — bleiben in Kraft.
V1.7  = Architektur-Schicht: macht den Universal-Core/Domain-Pack-Schnitt explizit,
        führt die Wissensarchitektur als eigenständige Schicht ein,
        hebt Security/Tenant zum Fundament (P0) und ordnet die Umsetzungspriorität neu.
```

Alle in V1.6 definierten Mode-Contracts (Abschnitt 7), Knowledge-/Sheet-/RFQ-Contracts (8–9, 20), Schemas (11, 12, 28) und Golden Conversations (26) gelten unverändert als **operative Schicht**. Dieses Dokument ist die **verbindliche Zielarchitektur** darüber. Bei Konflikt gewinnt V1.7 auf Architekturebene, V1.6 auf Contract-Ebene.

---

## 0. Executive Summary

sealing | Intelligence ist ein **case-aware Engineering-Intelligence-Workspace für Dichtungstechnik**: kein Chatbot, kein Katalog, kein Konfigurator, kein automatisches Auslegungssystem und keine finale technische Freigabestelle.

Der Nutzer beschreibt eine reale, oft unscharfe Dichtungssituation — in eigenen Worten, mit Foto, Altteil oder Skizze. Das System **versteht** die Situation, **strukturiert** sie sichtbar, **prüft** Risiken und Lücken, **führt** den Nutzer wie ein erfahrener Dichtungstechniker und erzeugt daraus eine **herstellerbewertbare RFQ-Anfrage** mit klaren offenen Punkten.

Die zentrale Architekturentscheidung von V1.7:

```text
Eine universelle Sealing-Case-Plattform trägt beliebige Dichtungstypen.
Jeder Dichtungstyp ist ein austauschbarer Domain Pack.
RWDR ist der erste Pack — der Beweis, dass die Plattform Tiefe tragen kann, nicht ihre Grenze.
```

Die Produktidentität ist **breit** (gesamte Dichtungstechnik). Der Bau ist **diszipliniert**: Plattform breit, Domänen-Tiefe sequenziell.

---

## 1. Leitprinzipien

### 1.1 Produktidentität

```text
sealingAI ist die Intelligence-Plattform für industrielle Dichtungstechnik.
Sie erkennt Dichtungstyp, Anwendung, Medium, Betriebsbedingungen, Risiken und fehlende Parameter
und erzeugt daraus prüfbare technische Entscheidungs- und Anfrageunterlagen.
```

Nicht „KI für Radialwellendichtringe“. RWDR ist der erste tief umgesetzte Fall, weil er häufig, konkret, erklärbar und gut testbar ist.

### 1.2 Die zwei Breiten (zentrale Bauregel)

Es gibt zwei grundverschiedene Arten von Breite mit **gegensätzlichen** Bauregeln. Ihre Verwechslung ist die wichtigste Falle des Projekts.

```text
Plattform-Breite  → einmal bauen, für alle Dichtungstypen, von Anfang an.
                    (Engine, Case-Modell, State Gate, RFQ-Pipeline, Routing, Cockpit-Projektion,
                     querschnittliches Wissen, Tenant/Governance)

Domänen-Tiefe     → sequenziell bauen, ein Dichtungstyp nach dem anderen.
                    (Klassifikation, Vollständigkeitsregeln, Berechnungen, Ausfallmodi,
                     Parameter-Schema, Frageлogik, RFQ-Template je Typ)
```

Begründung der Sequenzierung: Jeder Dichtungstyp ist echtes, testbares Ingenieurwissen. Ein Team kann nicht zehn Typen gleichzeitig auf echte Tiefe bringen. Der Versuch erzeugt einen flachen Erkenner, der zehn Typen oberflächlich erkennt, aber keinen einzigen bis zu einer herstellerbewertbaren RFQ trägt — strikt schlechter als ChatGPT + Google, weil er Spezialisierung *vortäuscht*.

### 1.3 Safety-Formel

```text
sealingAI entscheidet nicht die Dichtung.
sealingAI macht die Dichtungssituation verständlich, strukturiert und herstellerbewertbar.
Der Hersteller bzw. der verantwortliche Ingenieur bewertet final.
```

### 1.4 Binding Product Rule

```text
Der Chat führt.
Das Cockpit dokumentiert.
Das Pocket Cockpit verdichtet.
Das Sheet strukturiert.
Knowledge erklärt.
Der RFQ-Brief übergibt.
Das State Gate entscheidet.
Jinja2 kontrolliert Output-Struktur, nicht Formulierungsvielfalt.
RAG belegt, schreibt aber keine Case-Wahrheit.
```

### 1.5 Diagnose statt Ausführung

sealingAI ist **diagnoseorientiert**, nicht ausführungsorientiert. Der Nutzer soll seine Situation *verstehen* und parallel eine verwertbare Anfrage erhalten — verstehen und liefern fallen zusammen. Das passt exakt zur Safety-Grenze (keine finale Freigabe) und unterscheidet das System von einem generischen Chatbot:

```text
Chatbot:    redet über den Fall.
sealingAI:  strukturiert den Fall sichtbar mit (Cockpit-first) und stellt nur die nächste wichtige Frage.
```

### 1.6 Implementierungsformel

```text
Master Blueprint ≠ Big-Bang-Implementation.
Audit-first → kleinster Patch → Tests → nächster Patch.
Bestehende Strukturen bevorzugen. Keine parallele Architektur erfinden.
```

---

## 2. Schichten-Referenzarchitektur

sealingAI folgt einem geschichteten „agentic operating system“-Modell. Jede Schicht hat eine universelle Funktion und eine dichtungstechnische Ausprägung.

```text
┌─────────────────────────────────────────────────────────────┐
│ 7. Oberflächen        Chat · Desktop-Cockpit · Pocket Cockpit │  ← grün: überträgt sauber
├─────────────────────────────────────────────────────────────┤
│ 6. Fach-Fähigkeiten   Impact-Agenten · Berechnungen · Normen  │  ← grün
├─────────────────────────────────────────────────────────────┤
│ 5. Wissen (Knowledge) Material · Medium · Norm · Fallhistorie │  ← gelb: Kaltstart-/Moat-Schicht
├─────────────────────────────────────────────────────────────┤
│ 4. Daten & Evidence   Foto · Altteil · Skizze · Sheet · PDF   │  ← gelb: Maschinenrealität
├─────────────────────────────────────────────────────────────┤
│ 3. Agentic Harness    Router · State Gate · Dirty Scheduler   │  ← grün
├─────────────────────────────────────────────────────────────┤
│ 2. LLM                versteht Sprache und Situation          │  ← grau: Fundament
├─────────────────────────────────────────────────────────────┤
│ 1. Sicherheit & Governance   Tenant-Trennung · keine Freigabe │  ← grau: Fundament (P0)
└─────────────────────────────────────────────────────────────┘
```

**Bewertungslegende:** grün = im V1.6-Runtime strukturell vorhanden, nur fertig verdrahten; gelb = echtes Kaltstart-/Realitätsproblem, bewusst aufzubauen; grau = Fundament.

Die beiden gelben Schichten sind die teuren. Sie tragen die wichtigste Disanalogie: Vergleichbare Legal-Plattformen leben davon, dass Kunden mit großen Dokumentenkorpora ankommen; der sealingAI-Nutzer kommt mit einer leckenden Maschine und einem schlechten Foto. Die Wissensschicht muss daher **selbst** aufgebaut werden (siehe Abschnitt 4).

---

## 3. Universal Sealing Core vs. Domain Pack

Dies ist der Kern der V1.7-Architektur und der Schnitt, der über die langfristige Tragfähigkeit entscheidet.

### 3.1 Universal Sealing Core (dichtungstyp-agnostisch)

Der Core kennt **keinen** spezifischen Dichtungstyp. Er stellt für alle Typen identisch bereit:

```text
- Case-Lifecycle und Persistenz (Event-Sourcing, Snapshots, Idempotency)
- Generisches Field-/State-Modell (Field Envelope, Status, Origin, Conflict Envelope)
- State Gate (inkl. Degradation-Regel)
- Evidence-/Vision-Intake (Foto, Altteil, Skizze, PDF → unsichere Kandidaten)
- RAG-Plumbing (Retrieval, Provenance, „keine Case-Wahrheit schreiben“)
- Routing und Mode-Erkennung
- Klassifikations-Orchestrierung (ruft die classification_signals der Packs auf)
- Cockpit- und Pocket-Cockpit-Projektion (generisch über Field Envelopes)
- RFQ-Dispatch-Policy (Readiness, DRAFT, Snapshot)
- Multi-Output-Envelope (AssistantTurnEnvelope, CockpitPatch, …)
- Tenant-Scoping und Governance
- Herstellerfeedback-Aufnahme
```

**Wichtig:** Der V1.6-Runtime ist auf dieser Ebene bereits generisch. `KnownField.field` ist ein String; die Modes heißen nach Interaktionstyp (`leakage_diagnosis`, `visual_evidence`, `rfq_brief_generation`), nicht nach Dichtungstyp. Der Core existiert also größtenteils — er muss nur als Core **benannt** und vom RWDR-Pack getrennt werden.

### 3.2 Domain Pack (pro Dichtungstyp)

Ein Domain Pack kapselt das gesamte typspezifische Wissen:

```text
- classification_signals : Hinweise zur Erkennung dieses Typs
- required_fields()       : Mindestkern für eine erste RFQ dieses Typs
- optional_fields()       : hilfreiche/optionale Parameter
- parameter_schema        : typisierte, typspezifische Felder
- calculations()          : domänenspezifische Berechnungen
- failure_modes()         : typische Ausfallmuster + Trigger
- question_policy()       : Next-Best-Question-Logik für diesen Typ
- risk_flags()            : domänenspezifische Review-Flags
- rfq_template_id         : Jinja2-Template für den One-Pager dieses Typs
```

### 3.3 Domain Pack Contract (Interface)

Jeder neue Dichtungstyp = eine Implementierung dieses Interface. Kein Umbau am Core.

```python
from typing import Protocol, Sequence

class DomainPack(Protocol):
    pack_id: str                      # z. B. "rwdr", "o_ring", "flat_gasket"
    display_name: str
    classification_signals: Sequence[str]

    def required_fields(self) -> list[str]: ...
    def optional_fields(self) -> list[str]: ...
    def parameter_schema(self) -> dict: ...
    def calculations(self, case) -> list["ComputedValue"]: ...
    def failure_modes(self, case) -> list["ReviewFlag"]: ...
    def question_policy(self, case) -> "PendingQuestion | None": ...
    def risk_flags(self, case) -> list["ReviewFlag"]: ...
    def rfq_template_id(self) -> str: ...
```

Vorgeschlagene Repo-Struktur (nur falls nicht bereits äquivalent vorhanden — Codex auditiert zuerst):

```text
core/
  sealing_case/       model.py · state.py · evidence.py · rfq.py · risk.py
  routing/            router.py · mode_detection.py · classification.py
  projection/         cockpit.py · pocket_cockpit.py
  persistence/        events.py · snapshot.py · idempotency.py

domains/
  registry.py         # DomainPack-Registry
  rwdr/               schema.py · classify.py · calculations.py · failure_modes.py · questions.py · rfq_template.j2
  # o_ring/ … später

knowledge/
  cross_cutting/      materials.py · media.py · standards.py     # alle Typen
  domain/             rwdr/ …                                    # typspezifisch

frontend/
  cockpit/            UniversalCaseCockpit.tsx · ParameterGrid.tsx · EvidenceChips.tsx
  pocket/             PocketCockpit.tsx
```

**Anti-Pattern (nicht bauen):** `rwdr_analyze.py`, `rwdr_confirm.py`, `rwdr_everything.py` — RWDR-Logik in der Plumbing. Ebenso wenig ein zweites, paralleles UI nur für RWDR.

### 3.4 RWDR Domain Pack V1 (erster Pack — konkret)

```text
classification_signals : Welle, rotierend, Radialwellendichtring, Simmerring, Leckage an Wellenaustritt
required_fields()      : Dichtungstyp/Foto · Maße d1/D/b oder Altteilfoto · Anwendung/Maschine ·
                         Medium oder Leckagebeschreibung · Anfrageziel
calculations()         : Umfangsgeschwindigkeit v = π · d1 · n / 60000  [m/s]
failure_modes()        : Einlaufspur · Wellenhärtung/Verschleiß · Staub/Abrasion · Trockenlauf ·
                         Mediumsangriff auf Elastomer · Über-/Unterdruck an Dichtkante
risk_flags()           : v über Werkstoffrichtwert · Staub ohne Schutzlippe · Mediuminkompatibilität (Richtung)
rfq_template_id        : rfq_rwdr_one_pager.v1
```

### 3.5 Erweiterungsregel: Rule of Three (Disziplin gegen Über-Abstraktion)

```text
Den Universal Core NICHT spekulativ über RWDR hinaus abstrahieren.
Der Core ist genau das, was im Runtime bereits typ-agnostisch ist.
Weitere gemeinsame Abstraktionen werden EXTRAHIERT, sobald Domain Pack #2 (O-Ring) gebaut wird —
dann ist bekannt, was wirklich geteilt wird. Nicht vorher raten.
```

Eine gute Abstraktion entsteht aus 2–3 konkreten Implementierungen, nicht aus einer. Sauberer, gut faktorierter RWDR-Code ist **keine** technische Schuld; ein spekulativer Universal-Layer auf einem einzigen Datenpunkt **ist** Schuld.

---

## 4. Wissensarchitektur (der Moat)

Die Wissensschicht ist der eigentliche langfristige Wert — und das härteste Kaltstart-Problem. Sie wird in V1.7 als eigenständige Schicht erster Klasse behandelt.

### 4.1 Querschnittliches Wissen (breit, ab Tag 1)

Gilt für **alle** Dichtungstypen und amortisiert sich über jede künftige Domäne:

```text
- Materialverträglichkeit (EPDM, FKM, FFKM, NBR, HNBR, PTFE, PU, VMQ, FVMQ, Graphit/Faser/Metall)
- Medienbeständigkeit (Öl, Wasser, Dampf, Chemikalien, Lebensmittel, Gas, abrasive/kontaminierte Medien)
- Temperatur- und Druckgrenzen je Werkstoff (als Richtung, nicht als Freigabe)
- Normen/Zulassungen als Dokumentationswissen (FDA, WRAS, KTW, DVGW, ATEX — erklärend, nicht freigebend)
```

In diese Schicht darf **breit** investiert werden, bevor weitere Domain Packs existieren.

### 4.2 Domänenspezifisches Wissen (sequenziell)

Gebunden an den jeweiligen Dichtungstyp, daher mit den Domain Packs sequenziert:

```text
- Geometrie- und Einbauwissen je Typ (Nut, Schnurstärke, Dichtfläche, Wellensitz, Flanschmaße)
- Ausfallmuster-Bibliothek je Typ
- typische Hersteller-Rückfragen je Typ
```

### 4.3 Kaltstart-Strategie

```text
Tag 1:    kuratierte Seed-Basis (querschnittliches Material-/Medien-/Norm-Wissen) + RWDR-Domänenwissen.
Laufend:  Herstellerfeedback-Schleife verwandelt jede bewertete RFQ in strukturiertes Wissen.
Effekt:   Wissen kompoundiert pro abgeschlossenem Fall — analog zu Firm-Playbooks/Präzedenz in Legal-Plattformen.
```

### 4.4 RAG-Contract

```text
- Single-Collection-Retrieval mit Pflicht-Payload (Quelle, Typ, Norm, Gültigkeit, Domäne/Querschnitt-Flag).
- Scoped Retrieval je Mode/Tier (kein Full-Retrieval auf Tier 0/1).
- RAG erzeugt ausschließlich rag_supported_note — niemals confirmed facts, niemals Material-/Produktfreigabe.
- Source-Display mit Herkunfts-/Status-Chips im Cockpit.
```

### 4.5 Kompoundierung

```text
Partner/Hersteller bewertet RFQ
   → strukturiertes Feedback (welche Daten fehlten, welche Annahme war falsch, welche Lösung passte)
   → fließt in domänenspezifisches Wissen + querschnittliche Richtwerte
   → verbessert künftige RFQ-Qualität und Next-Best-Question-Logik
```

Diese Schleife ist in V1.6 (Abschnitt 21) zu dünn angelegt und in V1.7 ausdrücklich als P2-Priorität markiert (Abschnitt 9).

---

## 5. Produkt- und UX-Contracts (verdichtet)

Die detaillierten Mode-Contracts, Beispiele und Golden Conversations aus V1.6 (Abschnitte 7–9, 26) bleiben **vollständig in Kraft**. Hier nur die verbindlichen Leitcontracts.

### 5.1 Oberflächenrollen

```text
Chat            führt, fragt nur die nächste wichtige Frage, spiegelt den Case NICHT zurück.
Desktop-Cockpit dokumentiert ausführlich (bekannte/berechnete/offene/widersprüchliche Felder).
Pocket Cockpit  verdichtet mobil radikal (recognized · critical · next_step · rfq_status).
Sheet           strukturierte Eingabe, läuft durch State Gate.
Knowledge       erklärt fachlich, mutiert Case nur bei neuen technischen Fakten.
RFQ-Brief       herstellerfreundlicher One-Pager, kein langer KI-Report.
```

### 5.2 Mobile-First Oily-Hands Contract

```text
- Action Chips statt unnötiger Texteingabe.
- Kein leerer Spinner: jeder längere Tier liefert <1 s ersten verwertbaren Fortschritt.
- Degraded-useful-output: schlechte Fotos → Mess-/Foto-Führung, nicht Scheitern.
- Mobile North Star: aus „sifft“ + schlechtem Foto in < 4 min ein brauchbarer nächster Schritt
  oder erster RFQ-Entwurf mit klaren offenen Punkten.
```

### 5.3 Mode-Übersicht (typ-agnostisch)

Die Modes beschreiben **Interaktionstypen**, nicht Dichtungstypen. RWDR erscheint nur in Test-Fixtures, nicht in Mode-Namen:

```text
smalltalk · ui_help · mobile_leakage_triage · visual_low_confidence_guidance ·
pending_slot_answer(_micro) · case_building · leakage_diagnosis · unknown_seal_scoping ·
visual_evidence · sketch_to_case · measurement_guidance · knowledge_general/case_aware/case_mutating ·
technical_comparison_general/case_aware · why_question_active_case · norm_documentation_knowledge ·
document_analysis · manufacturer_question_simulation · partner_profile_suggestion ·
rfq_brief_generation · rfq_draft_insufficient · blocked_boundary · complex_review_required · out_of_scope
```

### 5.4 No-Go-Phrasen in normalen Case-Building-Turns

```text
- "Ich verstehe den Fall aktuell als …"
- "Technisch relevant sind hier vor allem …"
- "Als Nächstes wäre die wichtigste Frage …"
- "Grenze:" (in normalen Turns)
- jede finale Eignungs-/Freigabe-Formulierung
```

### 5.5 RFQ One-Pager Contract

```text
Readiness:  DRAFT (Mindestkern fehlt) · MINIMAL · RFQ_WITH_OPEN_POINTS
Mindestkern: domänenspezifisch (Domain Pack definiert required_fields()).
Offene Punkte priorisiert: kritisch / hilfreich / optional.
RFQ Snapshot je case_revision. Herstellerfreundliche Struktur, nicht KI-Report.
```

---

## 6. Daten- und Zustandsmodell (Core, typ-agnostisch)

Unverändert aus V1.6, hier als Core-Bestandteil markiert.

### 6.1 Field Envelope

```json
{
  "field": "speed_rpm",
  "label": "Drehzahl",
  "value": 3000,
  "unit": "rpm",
  "status": "confirmed",
  "origin": "user_direct_answer",
  "approximate": true,
  "confidence": "high",
  "requires_confirmation": false,
  "revision": 4
}
```

### 6.2 Status / Origin (Auszug)

```text
status : confirmed · pending_confirmation · explicitly_unknown · rejected · conflicting ·
         not_applicable · visual_candidate · sketch_candidate · rag_supported_note ·
         calculated · agent_inferred_review_flag
origin : user_direct_input · action_chip_answer · sheet_field_edit · sheet_bulk_input ·
         llm_extracted · rag_supported · visual_candidate · calculated · manufacturer_response
```

### 6.3 Conflict Envelope + State Gate Degradation

```json
{ "field": "temperature_operating_c", "existing_value": 90, "new_value": 190,
  "status": "conflicting",
  "resolution_question": "Soll 190 °C den bisherigen Wert ersetzen oder ist das ein Spitzenwert?",
  "case_blocking": false, "rfq_open_point": true }
```

```text
Normale Feldkonflikte → nur Feldstatus conflicting, restlicher Case bleibt nutzbar, RFQ ggf. mit offenem Punkt.
Human Escalation nur bei hoher Risiko-/Safety-/Compliance-Relevanz.
```

### 6.4 Multi-Output Envelope

```text
AssistantTurnEnvelope = ChatReply + CockpitPatch + PocketCockpitPatch +
                        CaseUnderstandingPatch + RFQBriefPatch + ActionChips + PendingQuestion + Trace
```

---

## 7. Agenten- und Orchestrierungsmodell

Agenten werden in V1.7 explizit in Core-Agenten und Domain-Pack-Agenten getrennt.

### 7.1 Core-/Querschnitt-Agenten (alle Dichtungstypen)

```text
MediumImpactAgent · ApplicationImpactAgent · OperatingConditionImpactAgent ·
MaterialCompatibilityImpactAgent · RegulatoryDocumentationImpactAgent · DataQualityEvidenceAgent ·
VisualEvidenceAgent · SketchToCaseAgent · MeasurementGuidanceAgent · DevilsAdvocateImpactAgent ·
RFQQualityAgent · ManufacturerQuestionAgent · CaseExplanationAgent · KnowledgeExplainerAgent ·
TechnicalComparisonAgent · SheetValidationAgent · ConflictResolutionAgent · MobileTriageAgent ·
PocketCockpitProjectionAgent · SmalltalkFastResponder · UIHelpResponder · PartnerProfileSuggestionAgent ·
SealTypeImpactAgent (Klassifikation: wählt den Domain Pack)
```

### 7.2 Domain-Pack-Agenten (typspezifisch, vom Pack geliefert)

```text
RWDR-Pack: ShaftCounterfaceImpactAgent · InstallationHousingImpactAgent · FailureModeImpactAgent(RWDR)
```

### 7.3 Dirty Module Scheduler

```text
medium changed       → MediumImpactAgent, MaterialCompatibilityImpactAgent
speed_rpm changed    → OperatingConditionImpactAgent, CalculationEngine (Pack)
photo + mobile + kurz → MobileTriageAgent, VisualEvidenceAgent (low conf., async), PocketCockpitProjectionAgent
rfq requested        → RFQQualityAgent, ManufacturerQuestionAgent, RFQOnePagerComposer (Pack-Template)
```

### 7.4 Agenten dürfen nicht

```text
- finale Chat-Antwort direkt schreiben (Composer/Jinja2 tut das)
- State direkt mutieren (nur State Gate)
- RAG-Notes als confirmed facts ausgeben
- Material-/Produktfreigabe geben oder Hersteller als beste Lösung ranken
- wegen normaler Lücken automatisch Human Escalation auslösen
```

---

## 8. Sicherheit, Tenant und Governance (Fundament, P0)

In V1.7 zum Fundament gehoben. Eine Tenant-Isolationslücke ist in einem B2B-Engineering-Tool ein Show-Stopper, kein Backlog-Item.

```text
- Tenant Scope auf jeder Case-, Datei-, Evidence- und RFQ-Operation. IDOR-/Cross-Tenant-Zugriff = P0-Blocker.
- Vollständige Audit-Trails über Tool-Calls, Dateizugriffe und Agentenaktionen.
- Prompt-Injection-Hardening (Uploads/Dokumente sind nicht vertrauenswürdig).
- Secrets niemals in Logs; keine Nutzung vertraulicher Kundendaten für Modelltraining.
- Governance-Grenze als Produktversprechen sichtbar: keine finale technische/Material-/Compliance-Freigabe;
  ATEX/FDA/WRAS/KTW/DVGW nur erklärend; Herstellerbewertung bleibt final.
- Liability-Disclaimer als dauerhafter UI-Hinweis unter dem Chat-Input, nicht als Anhängsel an jeden Turn.
```

---

## 9. Sequenzierung & Roadmap

Ehrliche Reihenfolge. Plattform breit, Tiefe sequenziell, Fundament zuerst.

```text
P0 — Fundament & grüner Stack
     • Tenant-Scoping/IDOR schließen (Blocker).
     • Conversational-/Pocket-Cockpit-Schicht live an den Runtime verdrahten.
     • RWDR-Killer-Flow (Chat → Cockpit → Pocket Cockpit → State Gate → RFQ One-Pager) durchgängig.
     Beweis: ein realer RWDR-Fall ist schneller, verständlicher und besser als ChatGPT + Google + Herstellerformular.

P1 — RWDR auf echte Tiefe
     • RFQ One-Pager perfektionieren; Berechnungen, Ausfallmodi, Risiko-Flags belastbar.
     • Golden Conversations als Regressionstests stabil.
     Beweis: die universelle Engine trägt einen Dichtungstyp bis zur herstellerbewertbaren RFQ.

P2 — Wissens-Moat
     • Querschnittliches Material-/Medien-/Norm-Wissen breit aufbauen.
     • Herstellerfeedback-Schleife stärken (Kompoundierung).
     Beweis: Wissen verbessert sich messbar pro abgeschlossenem Fall.

P3+ — Domänen-Expansion (ein Pack nach dem anderen)
     O-Ring → Flachdichtung/Flansch → Hydraulik/Pneumatik → Gleitringdichtung → Profile/Formteile/Packung.
     Bei Pack #2: gemeinsame Abstraktionen aus RWDR + O-Ring EXTRAHIEREN (Rule of Three).

P4 — Partner-/Hersteller-Workspace (Portal)
     Kontrollierter B2B-Bereich: strukturierte, reviewfähige RFQ-Fälle statt roher Leads;
     Matching-Logik und interne Wissensbasis bleiben geschützt.
```

---

## 10. Codex Implementation Discipline

```text
- Immer audit-first: bestehende Strukturen, Response-Contracts, Frontend-Rendering, State Gate, Routing, Tests kartieren.
- Keine parallele Architektur erfinden, wenn äquivalente Strukturen existieren.
- Nie „baue alles“ in einem Patch. Jeder Patch enthält Tests oder begründet deren Fehlen.
- API/SSE-Kompatibilität je Änderung prüfen. Jede DTO-Erweiterung serialisierbar und frontend-kompatibel.
- Jede UI-Änderung darf Desktop und Mobile nicht brechen.
- Core und Domain Pack als getrennte Einheiten halten; RWDR-Spezifik nie in die Plumbing.
```

### 10.1 Direct Codex Task Prompt (V1.7)

```text
Task
Refactor and extend sealingAI toward the V1.7 Universal Sealing Case Platform from
docs/sealing_intelligence_v1_7_universal_sealing_case_platform_blueprint.md, on top of the V1.6 contracts.

Goal
Make the runtime an explicit Universal Sealing Core with RWDR as the first Domain Pack, a first-class
knowledge layer (cross-cutting vs domain-specific), tenant isolation as foundation, and a manufacturer-friendly
RFQ one-pager. Chat guides; desktop cockpit documents; pocket cockpit compresses; State Gate decides.

Required behavior
1. Identify which existing modules are already type-agnostic (Core) and which are RWDR-specific (Domain Pack).
2. Introduce/confirm a DomainPack interface; move RWDR completeness rules, surface-speed calc, shaft/housing agents
   and rfq template into domains/rwdr/ without changing the generic runtime contracts.
3. Do NOT build a speculative universal abstraction beyond RWDR. Extract shared abstractions only when O-Ring lands.
4. Close any cross-tenant/IDOR exposure on case/file/evidence/RFQ operations (P0 blocker).
5. Wire the conversational + pocket-cockpit layer end-to-end so RWDR foto+"sifft" yields <1s useful progress.
6. Keep all V1.6 mode contracts, schemas and golden conversations in force.

Implementation
1. Read-only audit with path + line evidence. 2. Minimal patch path. 3. Preserve API/SSE compatibility.
4. Small patches only. 5. Run backend + frontend tests. 6. Report exact commands and results.

Expected artifacts
Audit summary · Core/Pack boundary map · Gap list · Patch plan · Changed files · Tests · Validation · Remaining gaps.
```

---

## 11. Acceptance Criteria V1.7

Erfüllt V1.6 (Abschnitt 32) **plus**:

```text
1.  Core und RWDR Domain Pack sind im Code sichtbar getrennt; RWDR-Spezifik liegt nicht in der Plumbing.
2.  Ein DomainPack-Interface existiert; ein zweiter Typ wäre durch Hinzufügen eines Packs (kein Core-Umbau) ergänzbar.
3.  Eine Klassifikationsstufe (SealTypeImpactAgent) wählt den Domain Pack.
4.  required_fields() / Mindestkern sind domänenspezifisch deklariert (RWDR liefert die erste Implementierung).
5.  Querschnittliches Wissen (Material/Medium/Norm) ist von domänenspezifischem Wissen getrennt organisiert.
6.  Tenant-Scoping ist auf allen Case-/Datei-/Evidence-/RFQ-Operationen durchgesetzt; kein Cross-Tenant-Zugriff.
7.  Der RWDR-Killer-Flow ist durchgängig live (Chat → Cockpit → Pocket Cockpit → State Gate → RFQ One-Pager).
8.  Foto + „sifft“ liefert mobil < 1 s sichtbaren Fortschritt; schlechte Fotos erzeugen Mess-/Foto-Führung.
9.  Keine spekulative Universal-Abstraktion über RWDR hinaus gebaut.
10. Herstellerfeedback wird strukturiert aufgenommen und ist als Wissensquelle vorgesehen.
```

---

## 12. Final Product Sentence

```text
sealingAI ist die Plattform für die gesamte Dichtungstechnik.
Eine universelle Engine versteht jede Dichtungssituation, ein austauschbarer Domain Pack liefert die fachliche Tiefe.
RWDR ist der erste Beweis, nicht die Grenze.
Das System wirkt professionell, weil es schnell führt, mobil verdichtet, sauber dokumentiert,
Unsicherheit sichtbar macht — und aus einem chaotischen Dichtungsfall eine herstellerbewertbare Anfrage erzeugt.
```

```text
Chat führt. Pocket Cockpit verdichtet. Cockpit dokumentiert. Sheet strukturiert.
Knowledge erklärt. RFQ übergibt. State Gate entscheidet. Hersteller bewertet final.
```
