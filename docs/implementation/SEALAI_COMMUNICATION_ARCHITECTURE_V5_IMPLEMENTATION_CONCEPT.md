# SealAI Communication Architecture V5

**Ziel:** Eine umsetzbare, begrenzte und messbare Zielarchitektur für die Kommunikation von SealAI als spezialisierte digitale Dichtungstechnik-Plattform.

**Leitformel:**

```text
Backend steuert.
LLM kommuniziert.
Hersteller gibt final frei.
```

Operativ präziser:

```text
Backend = technische Wahrheit, State, Evidence, Reihenfolge, Grenzen
FinalAnswerLayer = einziger Owner der sichtbaren Antwortentscheidung
LLM = normale Stimme, wenn Policy erlaubt
Fallback = sichere Degradation, nicht Zielzustand
```

---

## 1. Produktziel

SealAI ist eine spezialisierte digitale Plattform für Dichtungstechnik. Ziel ist ein **digitaler Clone eines erfahrenen Dichtungstechnik-Ingenieurs**.

SealAI soll:

```text
- technisch tief antworten
- natürlich und professionell kommunizieren
- User durch eine Bedarfsanalyse führen
- Wissen erklären
- Materialvergleiche einordnen
- aktive Dichtungsfälle strukturieren
- RFQ-/Herstelleranfragen vorbereiten
```

SealAI soll nicht:

```text
- final technische Eignung freigeben
- Herstellerfreigaben ersetzen
- RFQ-Readiness erfinden
- konkrete Grenzwerte ohne Quelle behaupten
- aktuelle Regulierung ohne aktuelle Quelle als sicher darstellen
```

---

## 2. Zentrale V5-Architekturregel

### Bisheriges Problem

Heute gibt es viele mögliche Stimmen:

```text
FastResponder
KnowledgeService
Governed output_contract
KnowledgeAnswerComposer
GovernedAnswerComposer
HCL
API Guards
Frontend Humanizer
```

Das erzeugt inkonsistente UX.

### V5-Regel

```text
Alle sichtbaren Antworten laufen durch den FinalAnswerLayer.
```

Der FinalAnswerLayer entscheidet:

```text
- Composer nutzen
- Micro Composer nutzen
- Fallback nutzen
- block/safety response nutzen
```

Das bedeutet **nicht**, dass immer ein großes Modell laufen muss. Es bedeutet:

```text
Es gibt genau eine finale Antwortentscheidung.
```

---

## 3. FinalAnswerLayer als Policy Engine

Der FinalAnswerLayer ist keine Blackbox und kein riesiger Orchestrator. Er ist eine kleine, explizite Policy-Schicht.

### Input: FinalAnswerEnvelope

Jeder Pfad liefert ein `FinalAnswerEnvelope`:

```json
{
  "route": "fast | knowledge | governed | light | exploration",
  "answer_mode": "smalltalk | knowledge | governed_intake | active_case_side_question | meta | blocked",
  "latest_user_message": "...",
  "recent_history": [],
  "deterministic_fallback_reply": "...",
  "active_case_summary": {},
  "governed_answer_context": {},
  "knowledge_evidence": [],
  "cockpit_speakable_facts": [],
  "answer_plan": {},
  "claim_policy": {},
  "tone_policy": {},
  "answer_trace": {}
}
```

### Output

```json
{
  "reply": "deterministischer Fallback",
  "answer_markdown": "finale sichtbare Antwort",
  "answer_trace": {
    "reply_source": "knowledge_service",
    "answer_markdown_source": "final_composer",
    "final_visible_source": "answer_markdown",
    "composer_tier": "tier_b",
    "composer_attempted": true,
    "composer_succeeded": true,
    "fallback_reason": null
  }
}
```

### Auswahlregel

Composer wird nur genutzt, wenn:

```text
1. Feature Flag aktiv
2. Provider verfügbar
3. Route/Mode für aktuelle Migrationsphase freigeschaltet
4. Latenzbudget nicht überschritten
5. Safety-/Claim-Level kompatibel
```

Sonst:

```text
answer_markdown = deterministic_fallback_reply
answer_trace.answer_markdown_source = "passthrough" oder "composer_fallback"
```

---

## 4. V5-Tier-Strategie

V5 nutzt nur zwei Tiers. Kein Tier C.

### Tier A — Micro Composer

Für:

```text
- Smalltalk
- Meta-Fragen
- kurze Bestätigungen
- kurze Übergänge
```

Beispiele:

```text
"hallo"
"hallo, wie geht es dir heute morgen"
"ok"
"weiter"
"warum fragst du das?"
```

Ziel:

```text
- sehr kurze Antwort
- professioneller Ton
- niedrige Latenz
- kein tiefes Reasoning
```

### Tier B — Standard Composer

Für:

```text
- Knowledge
- Materialvergleich
- PFAS-Orientierung
- Bedarfsanalyse
- Governed Intake
- aktive Case-Rückfragen
```

Kein Tier C in V5. Große Deep-Dive-Modelle kommen erst später, wenn Evals zeigen, dass Tier B nicht reicht.

---

## 5. Latenz- und Kostenbudget

V5 braucht konkrete Budgets.

### Zielwerte

```text
Tier A:
Time-to-first-token P50 < 400 ms
Time-to-first-token P95 < 1200 ms

Tier B:
Time-to-first-token P50 < 800 ms
Time-to-first-token P95 < 2000 ms
```

Wenn das Budget überschritten oder Provider nicht verfügbar ist:

```text
Fallback
```

### Kostenkontrolle V5

V5 implementiert noch keine perfekte Kostenabrechnung. Aber es muss messen:

```text
- composer_tier
- composer_attempted
- composer_latency_ms
- model_role
- fallback_reason
```

Session-Cost-Caps können später folgen.

---

## 6. AnswerPlan V5: pragmatisch, nicht pseudo-mathematisch

Kein Analysegraph mit Information-Gain-Scoring in V5.

Stattdessen:

```text
AnswerPlan v1 = handwerklicher Gesprächsplan mit Prioritäten.
```

Beispiel:

```json
{
  "answer_mode": "governed_intake",
  "response_obligations": [
    "acknowledge_new_information",
    "clarify_ambiguous_medium",
    "ask_one_next_question"
  ],
  "new_information": [
    {
      "field": "medium",
      "value": "chlor",
      "status": "ambiguous"
    }
  ],
  "next_question_candidates": [
    {
      "id": "medium_form",
      "priority": 100,
      "target_field": "medium_form",
      "canonical_question": "Welche Chlorform liegt vor?",
      "allowed_options": [
        "Chlorgas",
        "Chlorwasser",
        "Natriumhypochlorit / Chlorbleichlauge",
        "chlorhaltiges Reinigungsmedium"
      ],
      "why_this_now": "Die Chlorform beeinflusst Werkstoffverträglichkeit und Sicherheitsbewertung wesentlich."
    },
    {
      "id": "pressure",
      "priority": 60,
      "target_field": "pressure",
      "canonical_question": "Welcher Betriebsdruck liegt an?",
      "why_this_now": "Druck beeinflusst Dichtprinzip, Spaltrisiko und Auslegung."
    }
  ]
}
```

Der Composer darf aus den Kandidaten formulieren, aber nicht frei ein anderes fachliches Ziel erfinden.

---

## 7. Understanding LLM in V5

V5 baut **kein verpflichtendes Understanding LLM**.

Reihenfolge:

```text
1. Deterministic parsing
2. pending_question / slot_binding
3. bekannte Domain-Parser
4. LLM Understanding erst später bei Bedarf
```

V5 Composer bekommt also Backend-Interpretationen und formuliert. Er interpretiert nicht selbst neu.

Regel:

```text
Der Speaking Composer darf extrahierte Werte sprachlich einbauen, aber nicht fachlich umdeuten.
```

---

## 8. Claim Policy V5

V5 nutzt eine kleine, harte Claim Policy.

### L1 — Allgemeines Fachwissen

Erlaubt.

Beispiel:

```text
EPDM wird häufig bei Wasser, Dampf und witterungsnahen Anwendungen geprüft.
```

### L2 — Anwendungsnahe Orientierung

Erlaubt, wenn vorsichtig formuliert.

Beispiel:

```text
Bei einem wasserbasierten Medium wäre EPDM naheliegend zu prüfen. Für eine belastbare Auswahl fehlen aber Temperatur, Druck und Mediumdetails.
```

### L3 — Backend-gestützte Vorbewertung

Nur erlaubt, wenn Backend/Evidence dies explizit erlaubt.

Beispiel:

```text
Auf Basis der bisher bekannten Angaben markiert SealAI EPDM als prüfenswert. Die finale Medienfreigabe ist offen.
```

### L4 — Finale Freigabe

Verboten.

Verbotene Muster:

```text
- ist geeignet
- ist freigegeben
- kann bedenkenlos eingesetzt werden
- ist die richtige Lösung
- RFQ-ready
- Herstellerfreigabe liegt vor
```

---

## 9. Output Guard V5

Kein LLM-Self-Check als Sicherheitsbasis.

V5 Guard besteht aus:

```text
1. Regelbasierte harte Verbote
2. Semantische Risiko-Muster
3. Fallback bei Verletzung
```

Kein LLM-as-Judge in V5.

Der Guard prüft unter anderem:

```text
- finale Materialeignung
- Herstellerfreigabe
- RFQ-Readiness
- erfundene Werte
- erfundene Grenzwerte
- aktuelle Rechtslage ohne Quelle
- internes JSON / State / Modellnamen
```

Wenn Guard blockt:

```text
answer_markdown = reply
answer_trace.answer_markdown_source = "guard_fallback"
```

---

## 10. MaterialComparisonProvider V5

Das parallel entstandene `material_comparison.py` ist sinnvoll, aber nur als Evidence Provider.

### Rolle

```text
MaterialComparisonProvider liefert:
- strukturierte Werkstoffprofile
- Stärken
- Grenzen
- typische Medienorientierung
- typische Prüfpunkte
- Claim-Level-Maximum
```

Nicht:

```text
finale sichtbare Antwort
```

### Evidence-Format

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

Composer darf diese Evidence sprachlich nutzen, aber nicht darüber hinaus freigeben.

---

## 11. Mixed UX: Chat und Cockpit müssen konsistent bleiben

V5-Regel:

```text
Cockpit-State ist strukturierte technische Wahrheit.
Chat ist sprachliche Erklärung dieser Wahrheit.
```

Composer darf fachliche Aussagen nur aus `cockpit_speakable_facts`, `evidence_items` und `answer_plan` ableiten.

Nicht direkt aus Rohzustand.

### Beispiel

Cockpit:

```json
{
  "medium": "chlor",
  "medium_status": "needs_clarification",
  "missing_fields": ["pressure", "temperature", "seal_principle"]
}
```

Chat darf sagen:

```text
Ich habe Chlor als Medium verstanden, aber die Form ist noch offen.
```

Chat darf nicht sagen:

```text
Chlor ist für FKM kritisch und EPDM wäre besser.
```

außer Evidence/Claim Policy erlaubt diese Einordnung.

---

## 12. Persönlichkeit V5

Kein Companion-Ton.

SealAI spricht wie ein erfahrener technischer Berater.

### Ton

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

### Smalltalk-Beispiel

Nicht:

```text
Mir geht es gut, danke!
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

SealAI:

```text
Nicht pauschal. FKM ist oft stark bei Öl, Kraftstoffen und vielen Kohlenwasserstoffen. Bei Wasser, Heißwasser oder Dampf wird häufig eher EPDM geprüft. Entscheidend sind aber Temperatur, Druck, Mediumdetails und die konkrete Dichtstelle.
```

---

## 13. Jinja2 V5

Kein Mega-Prompt.

V5 nutzt mode-spezifische Templates:

```text
final_smalltalk.j2
final_knowledge.j2
final_governed_intake.j2
final_active_case_side_question.j2
final_blocked.j2
```

Shared Includes:

```text
_tone_policy.j2
_claim_policy.j2
_evidence_policy.j2
_question_policy.j2
```

Die Templates bekommen nur vorbereiteten, sicheren Kontext.

---

## 14. Eval V5: primitiv, aber ehrlich

V5 baut keine perfekte Eval-Plattform.

V5 startet mit 12 Golden Conversations und einer manuellen Bewertung durch Owner/Tech Lead.

### Bewertet werden Outcome-Metriken

```text
- beantwortet letzte User-Nachricht
- nutzt Kontext korrekt
- führt fachlich sinnvoll weiter
- keine verbotenen Claims
- weniger User-Korrekturen
- weniger „warum fragst du das?“-Momente
- professioneller Ton
- akzeptable Länge
```

Keine Judge-LLMs in V5. Später kann LLM-Judge kommen, aber nicht jetzt.

---

## 15. Phase-0-Hypothesenprüfung

Vor produktiver Migration wird ein Spike getestet.

### Aufgaben

Mindestens 8 Sessions, ideal 12.

Aufgaben:

```text
1. Neue Dichtungslösung starten
2. User antwortet kurz auf Medium
3. FKM vs EPDM
4. PFAS-Orientierung
5. Salzwasser-Risiko
6. bestehender RWDR leckt
7. User fragt „warum fragst du das?“
8. aktive Case-Wissensfrage
```

### Vergleich

Nicht handkuratiert.

```text
aktueller Output
vs.
echter Composer-Output mit geplantem Tier-B-Modell
```

### Erfolgskriterien

Composer ist nur erfolgreich, wenn er in mindestens 3 von 4 Kriterien besser ist:

```text
- weniger Turns bis Ziel
- weniger User-Korrekturen
- höhere subjektive Vertrauensbewertung
- bessere fachliche Gesprächsführung
```

---

## 16. V5-Migrationsstrategie

Nicht Smalltalk-only. Nicht Big Bang.

### Schritt 1 — Thin End-to-End Spike

Pfad:

```text
User: ich brauche eine Dichtungslösung
SealAI: Einstieg / nächste Frage
User: chlor oder wasser
SealAI: greift Antwort auf und fragt sinnvoll weiter
```

Dieser Spike testet:

```text
- AnswerPlan
- pending_question
- slot_binding
- FinalAnswerLayer
- Composer
- Guard
- Trace
```

### Schritt 2 — Knowledge Spike

```text
FKM vs EPDM
PFAS
Salzwasser
RWDR
```

### Schritt 3 — Fast/Meta

Smalltalk, Meta, „warum fragst du das?“

### Schritt 4 — Governed breiter ausrollen

Erst wenn Spike und Knowledge stabil sind.

---

## 17. V5 bewusst nicht enthalten

V5 enthält bewusst nicht:

```text
- kein Information-Gain-Analysegraph
- kein Tier-C-Modell
- kein LLM-as-Judge
- kein Pflicht-Understanding-LLM
- kein automatisiertes Eval in CI
- kein Full-LangGraph-Rewrite
- kein Frontend-Redesign
- kein Web Search
- keine neue RFQ-Logik
```

Das schützt vor Overengineering.

---

## 18. V5-Akzeptanzkriterien

V5 ist erfolgreich, wenn:

```text
1. FinalAnswerLayer ist einziger Owner der finalen Antwortentscheidung.
2. answer_trace zeigt pro Turn eindeutig die Quelle.
3. Thin governed Spike funktioniert mit Composer.
4. Passthrough-Quote im Spike < 25%.
5. Guard blockt klare L4-/RFQ-/Freigabe-Claims.
6. Composer mutiert keinen State.
7. Keine Frontend-/Cockpit-Regression.
8. Latenzbudget wird in 95 % der Spike-Turns eingehalten.
9. Golden Conversation Eval zeigt Verbesserung in mindestens 3 von 4 Outcome-Metriken.
```

---

## 19. Codex-App-Prompt für V5-Implementierung

Dieser Prompt ist bewusst **kein** „baue alles fertig“-Prompt, sondern implementiert einen begrenzten, messbaren V5-Spike.

```text
TASK SUMMARY
Implement SealAI Communication Architecture V5 as a limited, feature-flagged FinalAnswerLayer spike.

This is not a full migration. Do not rewrite the architecture globally. The goal is to create a production-safe, disabled-by-default V5 spike that proves the target communication architecture on a thin end-to-end path.

REPOSITORY ROOT
Work from:

/home/thorsten/sealai

CORE PRODUCT GOAL
SealAI should behave like a digital clone of an experienced sealing technology engineer.

Architecture principle:

Backend controls:
- technical truth
- route
- state
- pending questions
- slot binding
- evidence
- cockpit state
- missing fields
- risks/readiness
- RFQ boundaries
- answer plan

FinalAnswerLayer controls:
- final visible answer decision
- composer vs fallback policy
- answer_markdown
- answer_trace

LLM controls:
- natural professional language
- explanation
- contextual response
- wording of the next question

LLM must not:
- mutate case truth
- approve material suitability
- create RFQ readiness
- invent missing values
- set calculations/risk/readiness
- override backend state

IMPORTANT V5 SCOPE
Implement a limited V5 spike only.

Include:
- FinalAnswerLayer policy engine
- FinalAnswerEnvelope
- FinalAnswerContext
- Tier A / Tier B composer selection policy
- mode-specific Jinja2 templates for the spike modes
- rule-based Claim Guard v1
- answer_trace integration
- spike tests for governed intake, knowledge, and smalltalk/meta
- no behavior change when flag disabled

Do NOT include:
- no Information-Gain analysis graph
- no Tier C model
- no LLM-as-Judge
- no mandatory Understanding LLM
- no frontend redesign
- no cockpit redesign
- no web search
- no RFQ logic changes
- no risk/readiness changes
- no global LangGraph rewrite
- no phrase-specific fixes
- no commits

FEATURE FLAG
Add:

SEALAI_ENABLE_FINAL_ANSWER_LAYER=true

Default:
false.

When disabled:
- current behavior remains unchanged.

When enabled:
- eligible routes pass through FinalAnswerLayer.
- reply remains deterministic fallback.
- answer_markdown is produced by composer on success.
- fallback is used on provider/guard/timeout failure.
- answer_trace proves the source.

MODEL ROLES
Use existing LLM registry/factory.

Add roles if needed:

final_answer_tier_a
final_answer_tier_b

Env overrides:

SEALAI_FINAL_ANSWER_TIER_A_MODEL
SEALAI_FINAL_ANSWER_TIER_B_MODEL

Do not hardcode model IDs in business logic.

TIER POLICY V5
Tier A:
- smalltalk
- meta
- short acknowledgements
- no technical deep reasoning
- no case mutation

Tier B:
- knowledge
- material comparison
- governed intake
- active case side question
- PFAS technical orientation
- sealing technology explanation

No Tier C in V5.

FINAL ANSWER POLICY
Composer is attempted only if:

- feature flag enabled
- route/mode is enabled for V5 spike
- deterministic fallback reply exists
- provider/model can be called
- latency timeout not already exceeded
- input context is safe

Otherwise:
- answer_markdown remains fallback
- answer_trace.answer_markdown_source = "passthrough" or "composer_fallback"

INITIAL ENABLED MODES FOR SPIKE
Implement support for these modes:

1. smalltalk/meta
Example:
"hallo, wie geht es dir heute morgen"

2. knowledge
Examples:
"Was ist der Unterschied zwischen FKM und EPDM?"
"Was bedeutet PFAS für Dichtungen?"
"Was ist bei Salzwasser kritisch?"

3. governed intake thin path
Example:
"ich brauche eine Dichtungslösung"
then pending medium answer:
"chlor" or "wasser"

Do not attempt to solve every possible active-case side question in this patch.
It may be represented in context, but full side-question handling can stay future work.

WORKTREE SAFETY
Before editing, run:

git status --short
git diff --stat
git diff --check

If unexpected dirty files exist, stop and report them.
Do not mix unrelated material_comparison changes unless explicitly already committed or intentionally scoped.

PHASE 1 — READ CURRENT ARCHITECTURE
Inspect:

backend/app/agent/runtime/answer_trace.py
backend/app/agent/api/dispatch.py
backend/app/agent/api/assembly.py
backend/app/agent/api/routes/chat.py
backend/app/agent/api/streaming.py
backend/app/agent/runtime/user_facing_reply.py
backend/app/services/fast_responder_service.py
backend/app/services/knowledge_service.py
backend/app/agent/communication/answer_composer.py
backend/app/agent/communication/governed_answer_composer.py
backend/app/agent/communication/governed_answer_context.py
backend/app/agent/graph/output_contract_assembly.py
backend/app/agent/state/models.py
backend/app/llm/registry.py
backend/app/agent/prompts

PHASE 2 — CREATE FINAL ANSWER LAYER
Add a focused module, for example:

backend/app/agent/communication/final_answer_layer.py

It should define:

- FinalAnswerEnvelope
- FinalAnswerContext
- FinalAnswerPolicy
- FinalAnswerResult
- FinalAnswerLayer

The layer should:
- accept route output/fallback/context
- select tier
- render mode-specific prompt
- call composer
- run guard
- return final answer result
- update answer_trace

PHASE 3 — JINJA2 PROMPTS
Add mode-specific templates:

backend/app/agent/prompts/final/smalltalk.j2
backend/app/agent/prompts/final/knowledge.j2
backend/app/agent/prompts/final/governed_intake.j2

Shared includes if project convention supports:

backend/app/agent/prompts/final/_tone_policy.j2
backend/app/agent/prompts/final/_claim_policy.j2

Tone:
- professional
- calm
- precise
- no companion tone
- no artificial emotional self-reference
- German
- at most one main question

Smalltalk example style:
"Guten Morgen. Ich bin bereit — wobei kann ich dich technisch unterstützen?"

Do not say:
"Mir geht es gut."

PHASE 4 — CLAIM GUARD V1
Add a small independent guard.

Reject/fallback if output claims:
- final material suitability
- manufacturer release
- RFQ-ready
- guaranteed suitability
- invented values
- current legal/regulatory certainty without source
- internal JSON/state/model names

No LLM-as-Judge in V5.
No LLM self-check as guard input.

PHASE 5 — ROUTE INTEGRATION
Integrate after existing route-specific processing and before final response assembly.

Fast:
- fallback from FastResponder remains reply
- FinalAnswerLayer may compose answer_markdown when enabled

Knowledge:
- fallback from KnowledgeService remains reply
- evidence/context is passed if available
- FinalAnswerLayer may compose answer_markdown when enabled

Governed:
- fallback from governed output/HCL path remains reply
- GovernedAnswerContext/AnswerPlan is passed if available
- FinalAnswerLayer may compose answer_markdown when enabled

HCL:
- when FinalAnswerLayer succeeds, HCL must not overwrite it
- when FinalAnswerLayer disabled/fails, legacy HCL/fallback may remain

PHASE 6 — ANSWER TRACE
Use existing answer_trace.

Set:

answer_markdown_source:
- final_composer on success
- composer_fallback on composer/guard/provider failure
- passthrough when not attempted

composer_tier:
- tier_a
- tier_b
- none

composer_attempted:
true/false

composer_succeeded:
true/false

fallback_reason:
safe bounded string only

Do not include:
- full prompt
- full user text
- evidence body
- provider payload
- stack trace
- secrets

PHASE 7 — TESTS
Add focused tests.

Required tests:

1. Feature flag disabled
- existing behavior unchanged
- answer_markdown source remains previous source
- no final composer call

2. Smalltalk Tier A
Input:
"hallo, wie geht es dir heute morgen"

With mocked Tier A success:
- route remains fast
- reply_source remains fast_responder
- answer_markdown_source == final_composer
- composer_tier == tier_a
- output does not say "mir geht es gut"
- no case mutation

3. Knowledge Tier B
Input:
"Was ist der Unterschied zwischen FKM und EPDM?"

With mocked Tier B success:
- route remains knowledge
- reply_source remains knowledge_service
- answer_markdown_source == final_composer
- composer_tier == tier_b
- no final material suitability claim

4. PFAS limitation
Input:
"Was bedeutet PFAS für Dichtungen?"

Assert:
- if no current source exists, output is technical orientation only
- no legal deadlines invented
- no binding legal assessment

5. Governed intake spike
Input:
"ich brauche eine Dichtungslösung"

With mocked Tier B success:
- route remains governed
- reply remains fallback
- answer_markdown_source == final_composer
- no state mutation by composer
- no RFQ readiness

6. Pending medium spike
Given pending medium and user says "chlor":
- backend slot binding happens before composer
- composer receives ambiguous medium context
- output asks for Chlorform
- no "Medium angeben" as if absent
- no material suitability approval

7. Composer failure fallback
Mock provider error:
- request succeeds
- answer_markdown == reply/fallback
- answer_markdown_source == composer_fallback
- safe fallback_reason

8. Guard fallback
Mock composer output:
"FKM ist für deinen Fall geeignet und RFQ-ready."

Assert:
- guard rejects
- answer_markdown falls back
- no forbidden claim visible

9. Trace safety
answer_trace contains no raw prompt, no user text, no evidence text, no secrets, no stack trace.

10. Existing tests unchanged
Run existing focused tests.

PHASE 8 — VALIDATION COMMANDS
Run:

python -m pytest backend/app/agent/tests/test_governed_answer_composer.py -q
python -m pytest backend/app/agent/tests/test_governed_answer_context.py -q
python -m pytest backend/app/agent/tests/test_pending_medium_short_answer_binding.py -q
python -m pytest backend/app/agent/tests/test_pre_gate_runtime_dispatch.py backend/tests/unit/services/test_v083_conversation_routing.py -q
python -m pytest backend/tests/unit/services/test_knowledge_evidence_relevance.py -q
python -m pytest backend/app/agent/tests/test_knowledge_answer_composer.py -q
python -m pytest backend/app/agent/tests/test_knowledge_debug_trace.py -q
python -m pytest backend/app/agent/tests/test_governed_runtime_seam.py -q

Run new V5 final answer layer tests.

If frontend files are touched:
npm --prefix frontend test -- --run src/hooks/useAgentStream.test.tsx src/components/dashboard/ChatPane.test.tsx src/app/api/bff/agent/chat/stream/route.spec.ts
npm --prefix frontend run lint

Also run:

git diff --check
git diff --stat
git status --short

EXPECTED FINAL RESPONSE
Return:

1. Worktree safety
Report initial status and whether unrelated dirty files existed.

2. Diagnosis
Explain where FinalAnswerLayer was inserted and why.

3. Files changed
List exact files.

4. FinalAnswerLayer behavior
Explain:
- disabled
- enabled success
- enabled fallback
- tier selection

5. Route behavior
Explain:
- smalltalk/meta
- knowledge
- governed intake spike

6. Guard behavior
Explain what Guard v1 blocks and what it does not claim to solve.

7. Contract behavior
Confirm:
- reply remains deterministic fallback
- answer_markdown comes from final layer only on success
- answer_trace proves source

8. Safety boundaries
Confirm:
- no engineering truth mutation
- no material suitability approval
- no RFQ readiness
- no frontend/cockpit change unless actually touched
- no web search
- no Tier C
- no LLM Judge

9. Tests run
List exact commands and results.

10. Remaining work
List only:
Run V5 Phase-0 smoke/eval sessions with real provider credentials and compare against baseline.
```

---

## 20. Finales V5-Fazit

V5 ist der pragmatische Kompromiss:

```text
- klare finale Antwortentscheidung
- LLM als normale Stimme
- Backend als technische Wahrheit
- kein Big-Bang
- kein Full-LangGraph-Rewrite
- keine überzogene Eval-Plattform
- kein LLM-Judge
- keine Pseudo-Mathematik
- keine deterministische Formularsprache als Zielzustand
```

V5 ist nicht das Endsystem. V5 ist der **kleinste belastbare Spike**, der beweist, ob SealAI als digitaler Dichtungstechnik-Ingenieur wirklich funktioniert.
