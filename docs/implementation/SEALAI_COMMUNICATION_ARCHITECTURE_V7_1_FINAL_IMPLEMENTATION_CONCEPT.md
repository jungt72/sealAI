# SealAI Communication Architecture V7.1 — Final Freeze Specification

**Status:** Finales Zielkonzept / Implementierungsgrundlage für Codex App  
**Projekt:** SealAI / SealingAI — digitale Dichtungstechnik-Plattform  
**Ziel:** Professionelle, natürliche, kontrollierte Kommunikation wie ein erfahrener Dichtungstechnik-Ingenieur, ohne technische Wahrheit an das LLM abzugeben.

---

## 0. Executive Summary

SealAI soll kein freier Chatbot und kein starres Formularsystem sein. SealAI soll ein **workflow-geführter digitaler Dichtungstechnik-Ingenieur** sein:

- Der User spricht natürlich.
- SealAI hält den technischen Hauptfaden.
- SealAI erkennt Zwischenfragen.
- SealAI beantwortet Zwischenfragen im Kontext.
- SealAI kehrt danach kontrolliert zur Auslegung zurück.
- Technische Wahrheit bleibt im Backend.
- Die sichtbare Antwort kommt aus einer kontrollierten finalen Antwortschicht.

Die zentrale Leitformel:

```text
Backend = technische Wahrheit
Conversation Controller = Gesprächs- und Aufgabensteuerung
FinalAnswerLayer = sichtbare Antwortentscheidung
LLM = professionelle Stimme
Hersteller = finale Freigabe
```

SealAI baut **kein eigenes LLM**. SealAI nutzt bestehende Modelle rollenbasiert:

```text
Small Router Model / nano-class LLM:
- Intent-/Mode-Klassifikation
- Side-Question-Erkennung
- keine finale Antwort
- keine Engineering-Wahrheit

Backend / LangGraph / Services:
- Case State
- Pflichtfelder
- Bedarfsanalyse
- Berechnungen
- Risiken
- Readiness
- RFQ-Grenzen
- Evidence/RAG
- Recompute/Stale-Logik

Final Composer:
- sichtbare Antwort
- professionelle Sprache
- Kontextführung
- keine State-Mutation
```

Das Ziel ist **nicht**, jede Antwort blind an ein LLM zu geben. Das Ziel ist:

```text
Jede sichtbare Antwort läuft durch genau eine finale Antwortentscheidung.
```

---

## 1. Produktziel

SealAI ist eine spezialisierte digitale Plattform für Dichtungstechnik. Sie bildet einen **digitalen Clone eines erfahrenen Dichtungstechnik-Ingenieurs** ab.

SealAI soll:

```text
- Dichtungssituationen verstehen
- unklare Anforderungen strukturieren
- technische Informationen im Dialog erheben
- Material- und Medienwissen erklären
- bestehende Lösungen analysieren
- Fehlerbilder einordnen
- RFQ-/Herstelleranfragen vorbereiten
- den User fachlich führen
```

SealAI soll nicht:

```text
- finale Dichtungslösungen freigeben
- Herstellerverantwortung ersetzen
- Materialeignung endgültig bestätigen
- RFQ-Readiness erfinden
- konkrete Grenzwerte ohne Quelle behaupten
- aktuelle Rechtslage ohne aktuelle Quelle verbindlich darstellen
- technische Werte halluzinieren
```

Der Hersteller bleibt die finale technische Freigabeinstanz.

---

## 2. Grundproblem im aktuellen Stack

Die bisherigen Audits zeigten: SealAI hat aktuell mehrere potenzielle finale Stimmen.

Mögliche sichtbare Antwortquellen:

```text
FastResponder
KnowledgeService
KnowledgeAnswerComposer
Governed output_contract
GovernedAnswerComposer
HCL
API Guards
Frontend Humanizer
Streaming text chunks
```

Das führt zu inkonsistenter UX:

```text
"hallo" → FastResponder
"was ist FKM?" → KnowledgeService / no-case Knowledge
"ich brauche eine Dichtungslösung" → Governed Graph / HCL / fallback
"warum fragst du das?" im aktiven Case → kann fälschlich wieder Intake triggern
"Wie muss die Rauheit der Welle aussehen?" im aktiven Case → kann den Case-Kontext verlieren
```

Das Hauptproblem ist also nicht nur Prompting. Es ist:

```text
fehlende finale Antwortverantwortung
+
fehlende Gesprächsaufgabensteuerung
```

---

## 3. Zielarchitektur im Überblick

```text
User Message
   ↓
Deterministic Pre-Checks
   ↓
Small Router Model / nano-class LLM
   ↓
Backend Policy Validation
   ↓
Conversation Controller / Task Stack
   ↓
Backend Domain Work
   ├─ Fast fallback
   ├─ KnowledgeService / RAG / Evidence
   ├─ MaterialComparisonProvider
   ├─ LangGraph governed case state
   ├─ Calculations
   ├─ Risk / Readiness
   └─ RFQ boundaries
   ↓
AnswerPlan Builder
   ↓
FinalAnswerLayer
   ├─ Tier A Micro Composer
   ├─ Tier B Standard Composer
   └─ deterministic fallback
   ↓
Claim Guard
   ↓
Output Contract
   ├─ reply = fallback
   ├─ answer_markdown = final visible answer
   ├─ answer_trace = source/provenance
   └─ ui_state = Cockpit
   ↓
Frontend
   ├─ Chat = Kommunikation
   └─ Cockpit = strukturierte technische Wahrheit
```

---

## 4. Kernkomponenten

### 4.1 Intent Router

Der Intent Router ist nicht die finale Antwortschicht. Er klassifiziert den Turn.

Empfohlen:

```text
Deterministic Pre-Checks
+ Small Router Model / nano-class LLM
+ Backend Policy Validation
```

Das konkrete Modell wird über die Model Registry konfiguriert. Das Konzept sollte nicht hart an einem Modellnamen hängen. Formulierung:

```text
Router-Small-Modell über Model Registry, z. B. nano-class LLM
```

Der Router erkennt:

```text
- intent
- answer_mode
- active_case_side_question
- mutation_suggestion
- case_relevance
- confidence
```

Beispiel:

```json
{
  "intent": "knowledge_question",
  "answer_mode": "active_case_side_question",
  "case_relevance": "active_case_context",
  "mutation_suggestion": "forbidden",
  "side_topic": "shaft_surface_roughness",
  "confidence": 0.82
}
```

Wichtig:

```text
Router routet.
Router antwortet nicht final.
Router setzt keine technische Wahrheit.
Backend validiert Router.
```

---

### 4.2 Conversation Controller

Der Conversation Controller ist die zentrale Schicht zwischen Routing und Antwort.

Er entscheidet:

```text
- Ist das eine Antwort auf die letzte Frage?
- Ist das eine neue technische Angabe?
- Ist das eine Wissensfrage zwischendurch?
- Ist es eine Korrektur?
- Darf State mutiert werden?
- Muss nach der Antwort zur Bedarfsanalyse zurückgekehrt werden?
```

Er erzeugt kein einzelnes Intent-Label, sondern eine **TurnDecision**.

---

### 4.3 Backend Domain Work

Das Backend ist technische Wahrheit.

Es kontrolliert:

```text
- Case State
- confirmed facts
- candidate facts
- ambiguous values
- conflicts
- stale dependencies
- required fields
- calculations
- risks
- readiness
- RFQ boundaries
- evidence/RAG
- material comparison evidence
- next question candidates
```

Das Backend darf deterministische Fallback-Texte erzeugen, aber diese sind **Fallback**, nicht Ziel-Stimme.

---

### 4.4 FinalAnswerLayer

Der FinalAnswerLayer ist der einzige Owner der sichtbaren Antwortentscheidung.

Er bekommt:

```text
- route
- answer_mode
- fallback_reply
- TurnDecision
- AnswerPlan
- Case Summary
- Evidence
- SpeakableFacts
- Claim Policy
- Tone Policy
- Latency Budget
```

Er entscheidet:

```text
- Composer nutzen
- Micro Composer nutzen
- Fallback nutzen
- Safety/block response nutzen
```

Wichtig:

```text
FinalAnswerLayer ist keine Blackbox.
FinalAnswerLayer ist eine explizite Policy Engine.
```

---

## 5. TurnDecision statt Single Intent

Reale User-Turns sind oft mehrdeutig und enthalten mehrere Dinge gleichzeitig.

Beispiel:

```text
„Ich habe gehört, EPDM wäre für Wasser besser — wir hätten Wasser mit etwas Reinigerzusatz.“
```

Das ist gleichzeitig:

```text
- Wissens-/Vergleichsfrage
- Antwort auf pending_question = Medium
- neue technische Angabe
- mögliche falsche Annahme
- anwendungsrelevante Mediumspezifikation
```

Deshalb nutzt V7.1 ein **TurnDecision**-Objekt.

### 5.1 TurnDecision Schema

```json
{
  "turn_kind": "mixed",
  "primary_interpretation": "pending_slot_answer_with_embedded_knowledge_question",
  "router_signals": {
    "nano_intent": "knowledge_question",
    "nano_confidence": 0.81,
    "deterministic_pending_slot_match": true,
    "deterministic_value_extraction": true,
    "active_case_exists": true
  },
  "state_actions": [
    {
      "type": "candidate_fact",
      "field": "medium",
      "value": "Wasser mit Reinigerzusatz",
      "mutation_policy": "proposed",
      "requires_confirmation": true
    }
  ],
  "answer_obligations": [
    "acknowledge_candidate_fact",
    "answer_or_correct_material_assumption",
    "ask_for_reiniger_details",
    "return_to_primary_task"
  ],
  "answer_mode": "pending_slot_answer",
  "resume_strategy": "reevaluate_after_answer",
  "resume_target_candidate": {
    "type": "pending_question",
    "target_field": "medium"
  }
}
```

Zentraler Punkt:

```text
Ein User-Turn kann gleichzeitig Wissen, State-Kandidat und Prozessfrage sein.
```

---

## 6. Conversation Controller: Entscheidungsregeln

### 6.1 Entscheidungspriorität

Der Controller prüft in dieser Reihenfolge:

```text
1. Safety / blocked
2. Explicit correction
3. Pending-slot answer
4. New technical facts
5. Active-case side question
6. Meta/process question
7. No-case knowledge
8. Smalltalk
9. Unclear / clarification
```

Diese Reihenfolge bedeutet nicht, dass nur eine Kategorie gewinnt. Sie priorisiert State-Aktionen.

Beispiel:

```text
User: „EPDM wäre für Wasser besser — wir hätten Wasser mit Reinigerzusatz.“
```

Für den State gewinnt:

```text
pending_slot_answer / candidate_fact
```

Die Antwort darf zusätzlich die EPDM-Annahme fachlich einordnen.

---

### 6.2 Router Confidence

Confidence-Werte sind initial heuristisch und werden später anhand realer Turns kalibriert.

```text
confidence >= 0.80
→ starkes Router-Signal, aber Backend-Regeln können ergänzen oder überschreiben.

0.55 <= confidence < 0.80
→ unsicheres Signal. Pending Slots, deterministische Extraktion und aktive Case-Policy haben Vorrang.

confidence < 0.55
→ keine automatische Mutation. Conservative clarification oder Fallback.
```

### 6.3 Disagreement-Regeln

| Konflikt | Entscheidung |
|---|---|
| Pending Slot erkennt gültige Antwort, Nano sagt Knowledge | Slot gewinnt für State; Antwort darf Knowledge-Aspekt zusätzlich behandeln |
| Nano sagt Mutation, Backend findet keinen validen Wert | Keine Mutation |
| Nano sagt Side Question, User liefert konkreten technischen Wert | Side Question + candidate_fact |
| Nano unsicher, Backend erkennt nichts | Klärungsfrage |
| Safety/Blocked schlägt an | Safety gewinnt immer |
| User korrigiert explizit frühere Angabe | Correction gewinnt |
| Nano sagt Smalltalk, aktiver pending_slot wird beantwortet | Pending slot gewinnt |
| Nano sagt Knowledge, kein aktiver Case | no_case_knowledge |
| Nano sagt Knowledge, aktiver Case vorhanden | active_case_side_question, mutation default forbidden/proposed |

Diese Tabelle ist verpflichtende Implementierungsvorgabe für Codex.

---

## 7. MutationPolicy

Das alte Boolean `mutation_allowed` ist zu grob. V7.1 nutzt vier Zustände:

```text
forbidden
Keine Case-Mutation. Nur Erklärung, Meta, Smalltalk oder reine Side Question.

proposed
Mögliche technische Information. Als Kandidat speichern oder zur Bestätigung anbieten.

allowed_by_validator
Backend darf nach deterministischer Validierung State aktualisieren.

correction
User korrigiert vorhandene Angabe. Konflikt, stale dependencies und recompute auslösen.
```

### 7.1 Zuordnung

| User-Turn | Beispiel | mutation_policy |
|---|---|---|
| Reine Side Question | „Wie rau muss die Welle sein?“ | forbidden |
| Side Question mit Wert | „Ist Ra 0,3 µm okay?“ | proposed |
| Beiläufige neue Info | „Bei uns ist die Welle geschliffen.“ | proposed |
| Antwort auf Pending Slot | „Wasser“ nach Medium-Frage | allowed_by_validator |
| Ambige Antwort auf Pending Slot | „Chlor“ nach Medium-Frage | proposed oder allowed_by_validator mit needs_clarification |
| Korrektur | „Eigentlich ist es statisch, keine Welle.“ | correction |
| Smalltalk | „Danke“ | forbidden |
| Prozessfrage | „Warum fragst du das?“ | forbidden |

---

## 8. Task Stack und Side Questions

### 8.1 Primary Task

Beispiel: laufende Dichtungsauslegung.

```json
{
  "primary_task": {
    "type": "governed_seal_design",
    "case_id": "case_123",
    "phase": "medium_intake",
    "pending_question": {
      "target_field": "medium",
      "question": "Welches Medium soll abgedichtet werden?"
    }
  },
  "active_side_task": null
}
```

### 8.2 Side Task

User fragt während der Auslegung:

```text
Wie genau muss die Rauheit der Welle aussehen?
```

Dann:

```json
{
  "primary_task": {
    "type": "governed_seal_design",
    "case_id": "case_123",
    "phase": "medium_intake",
    "pending_question": {
      "target_field": "medium",
      "question": "Welches Medium soll abgedichtet werden?"
    }
  },
  "active_side_task": {
    "type": "active_case_side_question",
    "topic": "shaft_surface_roughness",
    "mutation_policy": "forbidden",
    "return_to": {
      "type": "pending_question",
      "target_field": "medium"
    }
  }
}
```

### 8.3 Side-Task-Tiefe

V7.1 unterstützt bewusst keine beliebig tiefe Side-Task-Verschachtelung.

```text
Maximale Side-Task-Tiefe: 1
```

Wenn während einer Side Question eine weitere Side Question kommt, wird sie als `side_task_continuation` behandelt.

Definition:

```text
side_task_continuation bedeutet:
- primary_task bleibt unverändert
- original_resume_target bleibt unverändert
- active_side_task.topic kann erweitert werden
- active_side_task.history bekommt die Folgefrage
- resume_strategy bleibt reevaluate_after_answer
```

Beispiel:

```text
User: „Wie rau muss die Welle sein?“
Assistant erklärt.
User: „Und wie messe ich das?“
```

Dann:

```json
{
  "active_side_task": {
    "type": "active_case_side_question",
    "topic": "shaft_surface_roughness",
    "continuation": true,
    "subtopic": "measurement_method",
    "original_resume_target": {
      "type": "pending_question",
      "target_field": "medium"
    }
  }
}
```

Wenn die zweite Side Question fachlich eine Korrektur enthält, wird sie als `correction` behandelt.

---

## 9. ResumeStrategy

Resume bedeutet nicht blind zurückspringen. Resume wird neu bewertet.

### 9.1 Resume-Entscheidungstabelle

| Bedingung nach Side Question | Resume-Variante |
|---|---|
| Keine neuen Fakten, keine Korrektur | Zur ursprünglichen pending_question zurückkehren |
| Neuer candidate_fact erkannt, pending_question weiterhin gültig | Kandidat kurz bestätigen/klären, dann zurück |
| Neuer candidate_fact beantwortet pending_question | pending_question schließen, nächste Frage neu bestimmen |
| mutation_policy = correction | Recompute auslösen, neue next_best_question bestimmen |
| pending_question wurde durch neue Info ungültig | pending_question ersetzen |
| User stellt Side-Continuation | active_side_task fortführen, original_resume_target behalten |
| User wechselt explizit Thema | primary_task pausieren oder neue Route nach Policy |
| Unsicherheit hoch | Klärungsfrage stellen, keine Mutation |

### 9.2 Patch-1-Übergang

Patch 1 darf als Übergang zunächst ein minimales Restore-Verhalten nutzen:

```text
resume = restore_to_pending_question
```

Das muss aber in `answer_trace` oder intern als Übergangsmodus markiert werden:

```text
resume_strategy = "restore_to_pending_question_v1"
```

Patch 2 ersetzt dieses Verhalten durch:

```text
resume_strategy = "reevaluate_after_answer"
```

---

## 10. AnswerPlan

Der AnswerPlan beschreibt, was die Antwort leisten soll.

Er ist kein Information-Gain-Optimierer, sondern ein pragmatischer Gesprächsplan.

### Beispiel: Active Case Side Question

```json
{
  "answer_mode": "active_case_side_question",
  "primary_task": {
    "type": "governed_seal_design",
    "phase": "medium_intake",
    "pending_question": {
      "target_field": "medium",
      "question": "Welches Medium soll abgedichtet werden?"
    }
  },
  "side_task": {
    "topic": "shaft_surface_roughness",
    "user_question": "Wie genau muss die Rauheit der Welle aussehen?",
    "answer_goal": "explain relevance and how to verify shaft roughness",
    "mutation_policy": "forbidden"
  },
  "response_obligations": [
    "answer_side_question_directly",
    "connect_to_active_case",
    "do_not_set_unprovided_values",
    "return_to_primary_task"
  ],
  "resume_target": {
    "type": "pending_question",
    "target_field": "medium",
    "question": "Welches Medium soll abgedichtet werden?"
  },
  "allowed_claim_level": ["L1", "L2"],
  "forbidden_claims": [
    "final_material_suitability",
    "manufacturer_release",
    "rfq_ready",
    "invented_surface_requirement"
  ]
}
```

---

## 11. SpeakableFacts

SpeakableFacts sind die Brücke zwischen Cockpit und Chat.

Sie bestehen aus strukturierten Werten und sicheren Phrasen.

### 11.1 SpeakableFact Format

```json
{
  "fact_id": "medium_chlor_candidate",
  "field": "medium",
  "status": "candidate",
  "claim_level_max": "L2",
  "structured_value": {
    "value": "chlor",
    "needs_clarification": true
  },
  "safe_phrases": [
    "Ich habe Chlor als Medium verstanden, aber die genaue Form ist noch offen.",
    "Chlor ist als Medium ein Kandidat; für die Auslegung muss die Chlorform geklärt werden."
  ],
  "forbidden_phrases": [
    "Chlor ist für den Werkstoff geeignet.",
    "Die Medienbeständigkeit ist geklärt."
  ],
  "source": "slot_binding",
  "visible_in_cockpit": true
}
```

### 11.2 Auswahlregel

Der Composer darf:

```text
- eine safe_phrase direkt verwenden
- safe_phrases leicht paraphrasieren
- strukturierte Werte erklären
- mehrere SpeakableFacts kombinieren, wenn claim_level_max nicht überschritten wird
```

Bei mehreren passenden safe_phrases:

```text
1. Nutze die kontextpassendste.
2. Bei Gleichstand nutze die erste.
3. Wiederhole nicht in zwei aufeinanderfolgenden Turns denselben Wortlaut, wenn eine Alternative vorhanden ist.
```

Der Composer darf nicht:

```text
- candidate als confirmed formulieren
- claim_level_max überschreiten
- Cockpit widersprechen
- aus Rohdaten neue technische Wahrheit ableiten
```

---

## 12. FinalAnswerLayer

### 12.1 Input

```json
{
  "answer_mode": "active_case_side_question",
  "deterministic_fallback_reply": "...",
  "turn_decision": {},
  "answer_plan": {},
  "case_summary": {},
  "evidence_items": [],
  "speakable_facts": [],
  "claim_policy": {},
  "tone_policy": {},
  "latency_budget": {},
  "answer_trace": {}
}
```

### 12.2 Output

```json
{
  "reply": "deterministic fallback",
  "answer_markdown": "LLM final answer or fallback",
  "answer_trace": {
    "reply_source": "knowledge_service",
    "answer_markdown_source": "final_composer",
    "answer_mode": "active_case_side_question",
    "composer_tier": "tier_b",
    "composer_attempted": true,
    "composer_succeeded": true,
    "fallback_reason": null
  }
}
```

### 12.3 Entscheidung

Composer wird versucht, wenn:

```text
- Feature Flag aktiv
- Mode für Migration aktiviert
- Fallback vorhanden
- Provider verfügbar
- Latenzbudget verfügbar
- Guard-Kontext vollständig genug
```

Passthrough wird genutzt, wenn:

```text
- Provider fehlt
- Budget überschritten
- Mode nicht migriert
- Guard-Kontext unvollständig
- Composer output rejected
```

---

## 13. Composer Tiers

### 13.1 Tier A — Micro Composer

Nur für:

```text
- smalltalk
- meta_question ohne technische Fachklärung
- kurze Bestätigung ohne State-Mutation
- einfache Rückführung zur pending_question ohne Fachinhalt
```

Beispiele:

```text
„Hallo“
„Danke“
„Okay“
„Weiter“
```

Zielwerte:

```text
TTFT P50 < 400 ms
TTFT P95 < 1200 ms
```

### 13.2 Tier B — Standard Composer

Für:

```text
- knowledge
- material comparison
- governed_intake
- pending_slot_answer mit technischer Bedeutung
- pending_slot_answer mit Ambiguität
- active_case_side_question
- correction explanation
- PFAS / Regulierung / Compliance-Orientierung
```

Zielwerte:

```text
TTFT P50 < 800 ms
TTFT P95 < 2000 ms
```

### 13.3 Entscheidungsregeln

```text
Wenn answer_mode = active_case_side_question → Tier B
Wenn evidence_items vorhanden → Tier B
Wenn claim_level_max >= L2 → Tier B
Wenn pending_slot_answer technische Bedeutung hat → Tier B
Wenn pending_slot_answer rein bestätigend ohne Fachinhalt → Tier A möglich
Wenn unklar → Tier B oder Fallback, nicht Tier A
```

---

## 14. Jinja2 Prompt-Struktur

Kein Mega-Prompt.

Mode-spezifische Templates:

```text
final_smalltalk.j2
final_knowledge.j2
final_governed_intake.j2
final_pending_slot_answer.j2
final_active_case_side_question.j2
final_meta_question.j2
final_blocked.j2
```

Shared Includes:

```text
_tone_policy.j2
_claim_policy.j2
_evidence_policy.j2
_question_policy.j2
```

### 14.1 Regeln für active_case_side_question

```text
1. Beantworte die Side-Frage direkt.
2. Nutze allgemeines Dichtungstechnik-Wissen und verfügbare Evidence.
3. Beziehe die Antwort auf den aktiven Fall, aber erfinde keine Werte.
4. Setze keine neuen technischen Fakten, wenn der User keine konkreten Werte genannt hat.
5. Wenn resume_target vorhanden ist, kehre am Ende dorthin zurück.
6. Stelle maximal eine Hauptfrage.
7. Keine finale Freigabe, keine Materialeignung, keine RFQ-Readiness.
```

---

## 15. Claim Policy

### 15.1 L1 — Allgemeines Fachwissen

Erlaubt.

```text
FKM ist ein Fluorelastomer, das häufig bei Ölen, Kraftstoffen und höheren Temperaturen geprüft wird.
```

### 15.2 L2 — Anwendungsnahe Orientierung

Erlaubt mit Vorsicht.

```text
Bei wasserbasierten Medien wird EPDM häufig geprüft. Für deine Anwendung fehlen aber noch Temperatur, Druck und Mediumdetails.
```

### 15.3 L3 — Backend-gestützte Vorbewertung

Nur wenn Backend/Evidence explizit erlaubt.

```text
Auf Basis der bisherigen Angaben markiert SealAI EPDM als prüfenswert. Die finale Medienfreigabe ist offen.
```

### 15.4 L4 — Finale Freigabe

Verboten.

```text
FKM ist geeignet.
Diese Lösung ist freigegeben.
RFQ-ready.
```

---

## 16. Output Guard

V7.1 nutzt keinen LLM-Judge.

Guard v1 ist regelbasiert.

### 16.1 Guard-Reihenfolge

```text
1. Empty/invalid/internal leakage check
2. Hard forbidden patterns
3. Semantic risk patterns
4. Claim-level consistency
5. Evidence/SpeakableFact consistency
```

Early Exit:

```text
Wenn eine Stufe blockt, wird sofort Fallback ausgelöst.
```

### 16.2 Blockierte Muster

```text
- finale Eignung
- Freigabe
- RFQ-ready
- Herstellerfreigabe
- erfundene Werte
- aktuelle Rechtsbehauptungen ohne Quelle
- interne State-/JSON-/Modellnamen
```

Semantische Risk Patterns:

```text
„X passt für deinen Fall.“
„X kannst du einsetzen.“
„X ist die richtige Lösung.“
„Damit ist die Materialfrage geklärt.“
„Das ist unkritisch.“
„Das funktioniert sicher.“
```

Wenn Guard blockt:

```json
{
  "answer_markdown": "reply",
  "answer_trace": {
    "answer_markdown_source": "guard_fallback"
  }
}
```

---

## 17. MaterialComparisonProvider

`material_comparison.py` ist sinnvoll als Evidence Provider, aber nicht als finale Stimme.

### Evidence Item

```json
{
  "evidence_type": "material_comparison",
  "source": "material_comparison_provider",
  "claim_level_max": "L2",
  "materials": ["FKM", "EPDM"],
  "safe_points": [
    "FKM ist häufig naheliegend bei Ölen, Kraftstoffen und vielen Kohlenwasserstoffen.",
    "EPDM wird häufig bei Wasser, Dampf und Witterung geprüft."
  ],
  "forbidden_phrasings": [
    "FKM ist geeignet für diese Anwendung.",
    "EPDM passt sicher.",
    "Material ist freigegeben."
  ]
}
```

---

## 18. RAG / Evidence-Strategie

### Modellwissen reicht für

```text
- allgemeine Grundlagen
- Materialfamilien
- Dichtungsprinzipien
- typische Risiken
- technische Erklärungen
```

### RAG/Evidence erforderlich für

```text
- Herstellerdatenblätter
- konkrete Compound-Daten
- PFAS/REACH/ECHA aktuell
- Normen/Zulassungen
- kundenspezifische Dokumente
- Lieferantenfähigkeiten
```

Bei aktueller Regulierung ohne Quelle:

```text
technische Orientierung, keine verbindliche rechtliche Bewertung
```

---

## 19. Mixed UX: Chat und Cockpit

Regel:

```text
Cockpit-State ist strukturierte technische Wahrheit.
Chat ist sprachliche Erklärung dieser Wahrheit.
```

Composer darf sprechen aus:

```text
- AnswerPlan
- SpeakableFacts
- EvidenceItems
- confirmed/candidate facts mit Status
```

Nicht aus beliebigen Rohdaten.

Wenn Cockpit sagt:

```json
{
  "medium": "chlor",
  "medium_status": "needs_clarification"
}
```

Chat darf sagen:

```text
Ich habe Chlor als Medium verstanden, aber die genaue Form ist noch offen.
```

Nicht:

```text
Chlor ist für FKM kritisch und EPDM wäre besser.
```

außer Evidence/Claim Policy erlaubt diese Einordnung.

---

## 20. Persönlichkeit

SealAI spricht wie ein erfahrener technischer Berater.

```text
- sachlich
- ruhig
- präzise
- technisch kompetent
- nicht kumpelhaft
- keine künstliche Emotionalität
- kein KI-Selbstbezug
- keine Übertreibung
- kurze Erklärung, dann klare nächste Frage
```

### Smalltalk

Nicht:

```text
Mir geht es gut, danke.
```

Sondern:

```text
Guten Morgen. Ich bin bereit — wobei kann ich dich technisch unterstützen?
```

### Falsche User-Annahme

User:

```text
FKM ist doch das Beste für Wasser, oder?
```

Antwort:

```text
Nicht pauschal. FKM ist oft stark bei Öl, Kraftstoffen und vielen Kohlenwasserstoffen. Bei Wasser, Heißwasser oder Dampf wird häufig eher EPDM geprüft. Entscheidend sind aber Temperatur, Druck, Mediumdetails und die konkrete Dichtstelle.
```

---

## 21. Output Contract

```json
{
  "reply": "deterministischer Fallback",
  "answer_markdown": "finale sichtbare Antwort",
  "answer_trace": {
    "reply_source": "governed_output_contract",
    "answer_markdown_source": "final_composer",
    "final_visible_source": "answer_markdown",
    "answer_mode": "active_case_side_question",
    "composer_tier": "tier_b",
    "composer_attempted": true,
    "composer_succeeded": true,
    "fallback_reason": null
  },
  "ui_state": {},
  "proposed_case_delta": null
}
```

Regel:

```text
Frontend rendert answer_markdown.
Cockpit rendert ui_state.
Frontend schreibt keine fachliche Antwort um.
```

---

## 22. Provenance für Patch 1

Patch 1 braucht kein vollständiges Event-Sourcing.

Minimum:

```json
{
  "event_type": "candidate_fact_created",
  "field": "medium",
  "value": "chlor",
  "source": "user_message",
  "turn_id": "turn_123",
  "actor": "backend_slot_binder",
  "status": "ambiguous"
}
```

Für Patch 1:

```text
event_type
field
value
source
turn_id
actor
status
```

Noch nicht in Patch 1:

```text
invalidates
full correction graph
full reconstruction
retention policy
```

---

## 23. Latenz- und Passthrough-Budgets

### Latenz

```text
Tier A:
TTFT P50 < 400 ms
TTFT P95 < 1200 ms

Tier B:
TTFT P50 < 800 ms
TTFT P95 < 2000 ms
```

### Passthrough-Quote

Messfenster:

```text
rolling 7 days, Mindeststichprobe n >= 50 Turns pro Modus
```

Zielquoten:

```text
smalltalk/meta: passthrough < 5 %
knowledge: passthrough < 15 %
governed_spike: passthrough < 25 %
active_case_side_question: passthrough < 25 %
```

Bei kleiner Stichprobe wird die Quote nur informativ angezeigt, nicht als Gate verwendet.

---

## 24. Eval

### 24.1 Golden Conversations

Mindestens 12:

```text
1. Neue Dichtungsauslegung starten
2. pending medium answer: wasser
3. pending medium answer: chlor
4. side question: Wellenrauheit
5. side question with value: Ra 0,3 µm
6. correction: eigentlich statisch, keine Welle
7. FKM vs EPDM no-case
8. PFAS
9. Salzwasser
10. RWDR leckt nach 6 Monaten
11. warum fragst du das?
12. was ist FKM im aktiven Case?
```

### 24.2 Bewertungsmethode

V7.1 nutzt noch keinen LLM-Judge.

Bewertung durch Owner/Tech Lead mit 0/1/2 Score.

### 24.3 Rubrik

Allgemein:

```text
0 = falsch / nicht erfüllt / gefährlich / User-Ziel verfehlt
1 = akzeptabel, aber mit klaren Mängeln
2 = gut, fachlich hilfreich und produktreif genug
```

#### Letzte User-Nachricht beantwortet

```text
0: ignoriert die Frage oder antwortet auf alten Kontext
1: teilweise beantwortet, aber unvollständig oder umständlich
2: beantwortet direkt und im Kontext
```

#### Primary Task gehalten

```text
0: verliert aktiven Case oder wechselt falsch in no-case
1: hält Case teilweise, aber Rückführung schwach
2: hält Hauptfaden sauber und führt zurück
```

#### Side Question erkannt

```text
0: nicht erkannt
1: erkannt, aber falsche Mutation/Resume
2: korrekt erkannt, beantwortet, sauber zurückgeführt
```

#### MutationPolicy korrekt

```text
0: mutiert falsch oder ignoriert echte Korrektur
1: setzt Kandidat, aber unscharf
2: korrekte Policy forbidden/proposed/allowed/correction
```

#### Guard / Claims

```text
0: verbotene Freigabe/Eignung/RFQ-Claim sichtbar
1: keine harte Verletzung, aber zu selbstsicher
2: sicher, fachlich sauber, richtige Claim-Ebene
```

#### Ton

```text
0: zu kumpelhaft, roboterhaft oder unprofessionell
1: akzeptabel, aber nicht senior-engineer-like
2: ruhig, präzise, technisch kompetent
```

Erfolg:

```text
Mittelwert >= 1.5 / 2 auf Golden Set
Keine L4-/RFQ-/Freigabe-Verletzung
```

### 24.4 Für Patch 1 nicht verwenden

Diese Metriken werden in Patch 1 nicht als Gate verwendet:

```text
- Turns bis Ziel
- User-Korrekturen
```

Sie sind Live-/Session-Metriken und kommen später.

---

## 25. Phase 0

Phase 0 findet **vor Patch 1** oder eng gekoppelt mit einem isolierten Prototype statt.

Nicht monatelang. Maximal 1–2 Wochen.

Ziel:

```text
Kernhypothese prüfen:
Verbessert die LLM-gestützte, task-stack-aware Kommunikation die Engineering-UX messbar?
```

Mindestens:

```text
8–12 Sessions oder Golden Conversation Runs
aktueller Output vs echter Composer-Output
keine handkuratierten Antworten
```

---

## 26. Patch-Reihenfolge

### Patch 0 — Specs + Golden Set

Keine Runtime-Änderung.

Artefakte:

```text
docs/communication/conversation_controller_v7.md
docs/communication/turn_decision_schema_v7.md
docs/communication/side_question_taxonomy_v7.md
docs/communication/mutation_policy_v7.md
docs/communication/resume_policy_v7.md
docs/communication/speakable_fact_contract_v7.md
docs/communication/golden_conversations_v7.md
```

### Patch 1 — Thin Visible Spike

Enthält bewusst:

```text
- active_case_side_question detection
- minimaler Task Stack
- FinalAnswerLayer für diesen Modus
- answer_trace
- minimal restore zu pending_question
- Eval hook
```

Wichtig: Patch 1 darf als Übergang zunächst `resume = restore_to_pending_question` nutzen, aber muss es sichtbar als Übergang markieren.

### Patch 2 — Resume Re-Evaluation

Ersetzt minimal restore durch:

```text
resume_strategy = "reevaluate_after_answer"
```

Mit Entscheidungstabelle aus V7.1.

### Patch 3 — Knowledge / Material Evidence

```text
- MaterialComparisonProvider als Evidence
- no-case knowledge
- active-case knowledge mit context
```

### Patch 4a — SpeakableFacts

```text
- SpeakableFact contract
- cockpit_speakable_facts
- Composer darf nur daraus fachlich sprechen
```

### Patch 4b — Guard-Härtung

```text
- Claim-level consistency
- SpeakableFact consistency
- semantische Risk Patterns
```

### Patch 5 — breiterer Rollout

Nur wenn Gate erfüllt:

```text
- side-question precision >= 80 %
- mutation_policy correctness >= 80 %
- resume correctness >= 80 %
- keine L4-Verletzung
- passthrough unter Zielquote
- Eval-Mittelwert >= 1.5/2
```

---

## 27. Akzeptanzkriterien

V7.1 ist erfolgreich, wenn:

```text
1. TurnDecision unterstützt mehrere Aktionen pro Turn.
2. Disagreement Nano vs Backend wird regelbasiert gelöst.
3. Side Question Precision >= 80 % auf Golden Set.
4. mutation_policy correctness >= 80 %.
5. Keine State-Mutation ohne validator/proposed/correction-Event.
6. Resume correctness >= 80 %.
7. FinalAnswerLayer ist einziger finaler Antwort-Owner.
8. answer_trace zeigt source, mode, tier, fallback_reason.
9. Composer nutzt nur SpeakableFacts/Evidence/AnswerPlan für fachliche Aussagen.
10. Chat/Cockpit consistency violations = 0 auf Golden Set.
11. Guard blockt L4-/RFQ-/Freigabe-Claims.
12. Provider-Fallback funktioniert.
13. Passthrough-Quote unter Ziel pro Modus.
14. Latenz P95 innerhalb Tier-Budget.
15. Eval-Mittelwert >= 1.5 / 2.
```

---

## 28. Bewusst nicht enthalten

```text
- kein Full-LangGraph-Rewrite
- kein Information-Gain-Scoring
- kein Tier C
- kein LLM-Judge
- kein verpflichtendes Understanding LLM
- kein Web Search
- kein Frontend-Redesign
- keine eigene Modellentwicklung
- kein beliebig tiefer Side-Task-Stack
```

---

## 29. Finales Architektur-Fazit

Die optimale SealAI-Architektur ist:

```text
Ein Conversation Controller klassifiziert jeden Turn als potenziell mehrdeutig und erzeugt eine TurnDecision mit State-Aktionen, Antwortpflichten, MutationPolicy und ResumeStrategy.

Das Backend validiert und aktualisiert technische Wahrheit über Events, Candidates, Confirmed State und Derived State.

Der FinalAnswerLayer ist die einzige finale Antwortentscheidung und nutzt mode-spezifische LLM-Composers oder Fallback nach klarer Policy.

Der Chat spricht nur aus AnswerPlan, Evidence und SpeakableFacts. Das Cockpit bleibt strukturierte Wahrheit.

Side Questions werden im aktiven Case-Kontext beantwortet und danach kontrolliert in den Hauptpfad zurückgeführt.
```

Das ist die freeze-reife Architekturgrundlage für Codex.

---

## 30. Codex-App-Prompt für Patch 0

```text
TASK SUMMARY
Implement Patch 0 for SealAI Communication Architecture V7.1.

This is a documentation/specification patch only. Do not change runtime behavior. Do not modify production code. Do not refactor. Do not add LLM calls. Do not change frontend. Do not change backend routes.

The goal is to add the V7.1 communication specifications and Golden Conversations so later runtime patches can be implemented without ad-hoc architecture decisions.

REPOSITORY ROOT
Work from:

/home/thorsten/sealai

CREATE THESE FILES

docs/communication/conversation_controller_v7.md
docs/communication/turn_decision_schema_v7.md
docs/communication/side_question_taxonomy_v7.md
docs/communication/mutation_policy_v7.md
docs/communication/resume_policy_v7.md
docs/communication/speakable_fact_contract_v7.md
docs/communication/golden_conversations_v7.md

CONTENT REQUIREMENTS

1. conversation_controller_v7.md
Include:
- role of Conversation Controller
- decision priority
- nano router as signal only
- backend validation
- disagreement rules
- confidence bands
- examples

2. turn_decision_schema_v7.md
Include:
- TurnDecision schema
- state_actions
- answer_obligations
- router_signals
- resume_strategy
- examples for mixed turns

3. side_question_taxonomy_v7.md
Include:
- pure side question
- side question with value
- hidden correction
- process question
- concept question
- side_task_continuation
- max side-task depth = 1

4. mutation_policy_v7.md
Include:
- forbidden
- proposed
- allowed_by_validator
- correction
- mapping table
- examples

5. resume_policy_v7.md
Include:
- restore_to_pending_question_v1 for Patch 1
- reevaluate_after_answer for Patch 2
- decision table
- examples

6. speakable_fact_contract_v7.md
Include:
- SpeakableFact schema
- safe_phrases
- forbidden_phrases
- claim_level_max
- selection rules
- chat/cockpit consistency rules

7. golden_conversations_v7.md
Include 12 Golden Conversations:
- new sealing design
- pending medium wasser
- pending medium chlor
- side question shaft roughness
- side question with Ra 0.3 µm
- correction static not rotating
- FKM vs EPDM no-case
- PFAS
- Salzwasser
- RWDR leaks after 6 months
- why do you ask that
- what is FKM in active case

Each Golden Conversation must include:
- user turns
- expected answer_mode
- expected mutation_policy
- expected resume behavior
- forbidden claims
- expected pass/fail criteria
- manual eval rubric 0/1/2

CONSTRAINTS
- Documentation only.
- Do not edit production code.
- Do not add tests unless they are documentation-only snapshots already used by the project.
- Do not commit.

VALIDATION
Run:

git diff --check
git diff --stat
git status --short

EXPECTED FINAL RESPONSE
Return:
1. Files created
2. Short summary of each file
3. Confirmation no runtime code changed
4. Validation commands/results
5. Remaining work:
"Patch 1 — Thin Visible Spike for active_case_side_question with minimal restore_to_pending_question_v1."
```
