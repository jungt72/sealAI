# Technical Case Challenge Answer Mode Report

Datum: 2026-05-27  
Branch: `demo/rwdr-limited-external`  
Arbeitsverzeichnis: `/home/thorsten/sealai`

## Ziel

Der Backend-Kommunikationspfad soll technische Fallanalyse-Anfragen nicht mehr als generische Parameteraufnahme beantworten. Der neue explizite Answer-Mode `technical_case_challenge` wird deterministisch erkannt, in die bestehende governed Runtime geroutet und als strukturierter `TechnicalCaseChallengePlan` bis zum Governed Answer Composer getragen.

## Gefundene aktuelle Pfade

1. Intent/Route-Entscheidung:
   - `backend/app/agent/communication/communication_runtime_v8.py:101` entscheidet deterministisch vor LLM-Proposal.
   - `backend/app/agent/communication/conversation_controller_v7.py:48` ist die zentrale V7-Entscheidungsschicht.
   - `backend/app/agent/communication/conversation_controller_v7.py:218` trennt Knowledge/Side-Question vom governed Intake.

2. Answer-Mode-Contract:
   - `backend/app/agent/communication/v7_contracts.py:23` definiert `AnswerMode`.
   - `backend/app/agent/communication/v7_contracts.py:251` baut aus `TurnDecision` die `RuntimeAction`.

3. GovernedAnswerContext:
   - `backend/app/agent/communication/governed_answer_context.py:101` definiert den Composer-Kontext.
   - `backend/app/agent/communication/governed_answer_context.py:493` baut den Kontext aus governed State, Output Contract und Strategy.

4. LLM-Composer:
   - `backend/app/agent/communication/governed_answer_composer.py:511` rendert den sicheren Kontext-Fallback.
   - `backend/app/agent/communication/governed_answer_composer.py:549` entscheidet, ob ein Kontext-Fallback statt bloßer Intake-Frage genutzt wird.
   - `backend/app/agent/prompts/governed/answer_composer.j2:31` bindet `technical_case_challenge` promptseitig an den vorbereiteten Plan.

5. Deterministische RWDR-/Challenge-Basis:
   - Neu in `backend/app/agent/communication/technical_case_challenge.py:13` bis `backend/app/agent/communication/technical_case_challenge.py:48`: `RWDRChallengeSignals` und `TechnicalCaseChallengePlan`.
   - Neu in `backend/app/agent/communication/technical_case_challenge.py:321`: Umfangsgeschwindigkeit nach `v = pi x d1 x rpm / 60000`.

6. Output Guard:
   - `backend/app/agent/communication/governed_answer_composer.py:999` validiert sichtbares Markdown gegen interne Leaks und Freigabe-/Eignungssprache.
   - `backend/app/agent/communication/governed_answer_composer.py:1012` validiert vollständige Antworten gegen den V9.1 Final Answer Guard.

## Implementierter Answer-Mode

`technical_case_challenge` wurde als expliziter `AnswerMode` ergänzt:

- `backend/app/agent/communication/v7_contracts.py:29`
- Runtime-Mapping zu `ENTER_GOVERNED_GRAPH` mit `GOVERNED_OUTPUT_CONTRACT`: `backend/app/agent/communication/v7_contracts.py:330`
- V7-Erkennung vor Meta/Knowledge/Smalltalk: `backend/app/agent/communication/conversation_controller_v7.py:51`
- V8-Erkennung vor Knowledge-/Side-Question-Routing: `backend/app/agent/communication/communication_runtime_v8.py:110`
- V8 macht diesen deterministischen Mode sticky gegen LLM-Proposal-Override: `backend/app/agent/communication/communication_runtime_v8.py:252`

Auslösung:

- explizite Fallanalyse-/Challenge-Signale wie `analysiere`, `challenge`, `kritische Punkte`, `keine stumpfe Parameterabfrage`, `Gegenindikatoren`, `Prüfhypothesen`, `fehlende Blocker`, `nächste beste Rückfrage`;
- plus konkrete technische Fallmarker oder numerische Betriebsdaten.

Nicht-Auslösung:

- reine Knowledge-Fragen wie `Was ist der Unterschied zwischen PTFE und FKM?`;
- Greeting, Meta, Blocked und reine Knowledge-Pre-Gate-Klasse.

## Deterministische Challenge-Struktur

Die neue Zwischenform liegt in `backend/app/agent/communication/technical_case_challenge.py`.

`TechnicalCaseChallengePlan` enthält:

- `case_type`
- `detected_domain`
- `confirmed_or_extracted_facts`
- `computed_signals`
- `critical_points`
- `cautious_hypotheses`
- `counter_indicators`
- `missing_blockers`
- `next_best_question`
- `forbidden_claims`
- `disclaimer`
- optional `rwdr_signals`

`RWDRChallengeSignals` enthält:

- d1/D/b
- Medium
- Druck
- Temperatur
- Drehzahl
- Umfangsgeschwindigkeit
- Anwendung
- Gegenlauffläche
- Außermittigkeit
- Materialnennungen
- Review Flags
- Missing Critical Fields

RWDR-Beispiele:

- Salzwasser, d1=40 mm, 3000 rpm ergibt deterministisch ca. `6,28 m/s`.
- Druckluft, d1=5 mm, 3 bar, keine Drehzahl erzeugt eine Scope-Rückfrage zu rotierender RWDR-Anwendung vs. pneumatischer/statischer Abdichtung.
- NBR wird nur als Nutzerangabe/Wunschmaterial geführt, nicht als Materialentscheidung.

## Composer-Vertrag

Der Composer bekommt den Plan über `GovernedAnswerContext`:

- Kontext-Felder: `backend/app/agent/communication/governed_answer_context.py:101`
- Plan-Erzeugung im Context Builder: `backend/app/agent/communication/governed_answer_context.py:512`
- `answer_mode` wird auf `technical_case_challenge` gesetzt: `backend/app/agent/communication/governed_answer_context.py:534`

Bei `technical_case_challenge` rendert der Fallback exakt die Planstruktur:

- `backend/app/agent/communication/governed_answer_composer.py:557`
- `backend/app/agent/communication/governed_answer_composer.py:569`

Die LLM-Prompt-Schicht darf nur noch diese vorbereitete Struktur formulieren:

- `backend/app/agent/prompts/governed/answer_composer.j2:31`

Zielstruktur:

1. Kurzurteil
2. Kritische Punkte
3. Abgeleitete Signale
4. Vorsichtige Prüfhypothesen
5. Gegenindikatoren / Risiken
6. Fehlende Blocker
7. Nächste beste Rückfrage
8. Grenze der Aussage

## Geänderte Dateien

- `backend/app/agent/communication/technical_case_challenge.py`
- `backend/app/agent/communication/v7_contracts.py`
- `backend/app/agent/communication/conversation_controller_v7.py`
- `backend/app/agent/communication/communication_runtime_v8.py`
- `backend/app/agent/communication/governed_answer_context.py`
- `backend/app/agent/communication/governed_answer_composer.py`
- `backend/app/agent/prompts/governed/answer_composer.j2`
- `backend/app/agent/tests/test_governed_answer_composer.py`
- `backend/app/agent/tests/test_governed_answer_context.py`
- `backend/app/agent/tests/test_v8_communication_runtime.py`
- `backend/app/agent/tests/test_v7_communication_contracts.py`

Hinweis: Die Worktree enthielt bereits vor diesem Patch weitere Änderungen aus vorherigen Aufgaben. Diese wurden nicht zurückgesetzt.

## Testfälle

Ergänzt/abgedeckt:

- Router erkennt explizite RWDR-Challenge als `technical_case_challenge`.
- PTFE/FKM bleibt Knowledge/Material-Comparison und wird nicht in Challenge Mode geroutet.
- RuntimeAction für `technical_case_challenge` geht in den governed Graph mit `GOVERNED_OUTPUT_CONTRACT`.
- `GovernedAnswerContext` trägt `answer_mode` und `technical_case_challenge_plan`.
- Salzwasser/RWDR-Plan enthält d1=40, 3000 rpm, ca. 6,28 m/s, Salzwasser-/Korrosions-/Druck-/Gegenlaufflächen-Review und nächste beste Rückfrage.
- SBB/RWDR-Fallback enthält eine einzige strukturierte Antwort mit d1/D/b, Druckluft, 3 bar, NBR als Nutzerangabe/Wunschmaterial, Scope-Frage zu rotierender RWDR-Anwendung.
- Keine Dankesfloskel im Challenge-Fallback.
- Keine finale Materialentscheidung und keine finale Freigabeformulierung im Challenge-Fallback.

## Testbefehle

Ausgeführt:

```bash
pwd
git status --short
git branch --show-current
rg -n "answer_mode|mode|challenge|technical_case|case_challenge|answer_plan|TurnDecision|route|intent|pre_gate|semantic" backend/app backend/tests
rg -n "governed_answer|GovernedAnswer|answer_composer|AnswerPlan|composer|final_answer|answer_markdown|assistant_message" backend/app/agent backend/app/services backend/tests
rg -n "RWDR|rwdr|Radialwellendichtring|Technical RWDR|circumferential|Umfangsgeschwindigkeit|review_flags|missing_critical" backend/app backend/tests
python -m compileall -q backend/app/agent/communication/technical_case_challenge.py backend/app/agent/communication/v7_contracts.py backend/app/agent/communication/conversation_controller_v7.py backend/app/agent/communication/communication_runtime_v8.py backend/app/agent/communication/governed_answer_context.py backend/app/agent/communication/governed_answer_composer.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_governed_answer_composer.py backend/app/agent/tests/test_governed_answer_context.py backend/app/agent/tests/test_v8_communication_runtime.py backend/app/agent/tests/test_v7_communication_contracts.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_governed_answer_composer.py backend/app/agent/tests/test_knowledge_answer_composer.py backend/app/agent/tests/test_conversation_runtime.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/app/api/tests/test_rwdr_golden_cases.py backend/app/api/tests/test_rfq_endpoint.py
npm --prefix frontend run test:run -- src/components/dashboard/ChatPane.test.tsx src/components/dashboard/ChatComposer.test.tsx src/hooks/useAgentStream.test.tsx src/app/api/bff/agent/chat/stream/route.spec.ts
git diff --check
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

## Testergebnisse

- Neue/fokussierte Backend-Tests: grün.
- Gefordertes Backend-Composer/Knowledge/Runtime-Kommando: grün.
- Gefordertes RWDR/RFQ-Kommando: grün, mit bestehender Deprecation-Warnung in `test_rfq_endpoint.py`.
- Gefordertes Frontend-Kommando: grün, 4 Dateien / 41 Tests.
- `git diff --check`: grün.
- Forbidden-Language-Scan: liefert viele bekannte Alt-/Test-/Dokumentations-Treffer, unter anderem historische Konzepte, Guard-Tests, Fixture-Forbidden-Phrasen und interne `approved` Workflow-States. Kein neuer produktiver Challenge-Antwortpfad wurde als Recommendation-/Freigabe-Pfad eingeführt.

## Bekannte Restlücken

- Die neue Extraktion im Challenge-Builder ist bewusst klein und deckt die Zielbeispiele ab. Sie ersetzt nicht die volle Normalize-/Assertion-Domainlogik.
- `technical_case_challenge` wird im Context Builder zusätzlich aus der letzten User Message inferiert. Das ist robust für Graph-Ausgabe, aber der nächste Patch sollte den `RuntimeAction.answer_mode` explizit bis in den GraphState/Output-Contract mitschreiben.
- Der LLM-Composer wird promptseitig gebunden, aber nicht schema-seitig gezwungen, exakt alle Abschnittsüberschriften auszugeben. Der deterministic fallback tut das bereits.
- Die bestehenden Forbidden-Language-Treffer im Repo sind nicht Teil dieses Patches und bleiben Release-Hygiene-Schulden.
- Mid-stream token expiry/SSE resilience wurde hier bewusst nicht bearbeitet.

## Nächste Empfehlung

Als nächster Patch sollte `RuntimeAction.answer_mode` als explizites Feld in den governed GraphState beziehungsweise Output-Assembly-Kontext übernommen werden. Danach kann der SSE-/mid-stream-token-expiry-Pfad isoliert gehärtet werden.
