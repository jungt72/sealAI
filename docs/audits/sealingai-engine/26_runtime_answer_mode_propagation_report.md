# Runtime Answer Mode Propagation Report

Datum: 2026-05-27  
Branch: `demo/rwdr-limited-external`  
Arbeitsverzeichnis: `/home/thorsten/sealai`

## Ziel

`technical_case_challenge` soll nicht nur aus der letzten User Message erkannt werden. Der Mode wird jetzt als explizite Runtime-Entscheidung von `RuntimeAction.answer_mode` bis in `GraphState`, Output Assembly und `GovernedAnswerContext` getragen.

## Aktueller Pfad von answer_mode

1. Router / TurnDecision:
   - `AnswerMode.TECHNICAL_CASE_CHALLENGE` existiert in `backend/app/agent/communication/v7_contracts.py`.
   - `ConversationControllerV7` und `CommunicationRuntimeV8` setzen den Mode bei expliziten technischen Challenge-Fällen.
   - `build_runtime_action_from_turn_decision()` übernimmt den Mode in `RuntimeAction.answer_mode`.

2. Runtime / GraphState:
   - `run_governed_graph_turn()` liest `RuntimeAction.answer_mode`: `backend/app/agent/api/governed_runtime.py:70`.
   - `build_governed_graph_input()` schreibt den Wert in `GraphState.runtime_answer_mode`: `backend/app/agent/api/governed_runtime.py:248`.
   - `GraphState` enthält jetzt `runtime_answer_mode` und `runtime_answer_mode_source`: `backend/app/agent/graph/__init__.py:98`.

3. Output Contract Assembly:
   - `_build_output_public_base()` übernimmt `runtime_answer_mode` in `output_public["answer_mode"]`: `backend/app/agent/graph/output_contract_assembly.py:827`.
   - `output_contract_node()` reicht `output_public` an `build_governed_answer_context()` weiter: `backend/app/agent/graph/output_contract_assembly.py:1888`.

4. GovernedAnswerContext:
   - `GovernedAnswerContext` trägt `answer_mode` und `answer_mode_source`: `backend/app/agent/communication/governed_answer_context.py:101`.
   - `_explicit_answer_mode()` priorisiert `output_public.answer_mode`, danach `state.runtime_answer_mode`: `backend/app/agent/communication/governed_answer_context.py:486`.
   - Der technische Challenge-Plan wird bei explizitem `technical_case_challenge` mit `force=True` gebaut: `backend/app/agent/communication/governed_answer_context.py:526`.

## Wo answer_mode vorher verloren ging

Vor diesem Patch endete `answer_mode` praktisch in der Dispatch-/RuntimeAction-Schicht. `build_governed_graph_input()` bekam nur Message, User, Session und Pre-Gate-Klasse, aber keinen RuntimeAction-Mode. Dadurch musste `GovernedAnswerContext` den Challenge-Mode erneut aus der letzten User Message ableiten.

## Erweiterte Felder / States

- `GraphState.runtime_answer_mode`
- `GraphState.runtime_answer_mode_source`
- `output_public["answer_mode"]`
- `output_public["answer_mode_source"]`
- `GovernedAnswerContext.answer_mode`
- `GovernedAnswerContext.answer_mode_source`

## Zurückgestufte Fallback-Inferenz

Die Text-Inferenz aus der letzten User Message bleibt nur als Kompatibilitätsfallback:

- Wenn ein expliziter `answer_mode` vorhanden ist, gewinnt dieser.
- Wenn `answer_mode == technical_case_challenge`, wird der Challenge-Plan gebaut.
- Wenn ein anderer expliziter Mode vorhanden ist, wird keine Challenge aus dem User-Text inferiert.
- Nur wenn kein expliziter Mode vorhanden ist, darf die alte User-Message-Erkennung greifen.
- Dieser Fall wird im Context mit `answer_mode_source="fallback_latest_user_message"` markiert.

## Geänderte Dateien

- `backend/app/agent/api/governed_runtime.py`
- `backend/app/agent/api/routes/chat.py`
- `backend/app/agent/api/streaming.py`
- `backend/app/agent/graph/__init__.py`
- `backend/app/agent/graph/output_contract_assembly.py`
- `backend/app/agent/communication/governed_answer_context.py`
- `backend/app/agent/communication/technical_case_challenge.py`
- `backend/app/agent/tests/test_governed_answer_context.py`
- `backend/app/agent/tests/test_governed_answer_composer.py`
- `backend/app/agent/tests/test_governed_runtime_seam.py`

Hinweis: Der Worktree enthielt bereits viele Änderungen vor diesem Patch. Diese wurden nicht zurückgesetzt.

## Tests

Ergänzt/erweitert:

- `build_governed_graph_input()` trägt `runtime_action_answer_mode` nach `GraphState`.
- `output_public` enthält `answer_mode` und `answer_mode_source`.
- `GovernedAnswerContext` nutzt expliziten `technical_case_challenge` und baut den Plan.
- Fallback-Inferenz wird als `fallback_latest_user_message` markiert.
- Expliziter Knowledge-Mode verhindert Challenge-Inferenz aus Vergleichs-/Analyse-Wording.
- Bestehende Salzwasser/RWDR- und SBB/RWDR-Challenge-Tests bleiben grün.

## Testbefehle

Ausgeführt:

```bash
pwd
git status --short
git branch --show-current
rg -n "RuntimeAction|answer_mode|technical_case_challenge|GraphState|OutputContract|output_contract|assembly|GovernedAnswerContext|context_builder|last user message|infer" backend/app backend/tests
python -m compileall -q backend/app/agent/api/governed_runtime.py backend/app/agent/api/routes/chat.py backend/app/agent/api/streaming.py backend/app/agent/graph/__init__.py backend/app/agent/graph/output_contract_assembly.py backend/app/agent/communication/governed_answer_context.py backend/app/agent/communication/technical_case_challenge.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_governed_answer_context.py backend/app/agent/tests/test_governed_answer_composer.py backend/app/agent/tests/test_governed_runtime_seam.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_conversation_runtime.py backend/app/agent/tests/test_governed_answer_composer.py backend/app/agent/tests/test_knowledge_answer_composer.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/app/api/tests/test_rwdr_golden_cases.py backend/app/api/tests/test_rfq_endpoint.py
npm --prefix frontend run test:run -- src/components/dashboard/ChatPane.test.tsx src/components/dashboard/ChatComposer.test.tsx src/hooks/useAgentStream.test.tsx src/app/api/bff/agent/chat/stream/route.spec.ts
git diff --check
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

## Testergebnisse

- Neue/fokussierte Propagation-Tests: grün.
- Gefordertes Backend-Composer/Knowledge/Runtime-Kommando: grün.
- Gefordertes RWDR/RFQ-Kommando: grün, mit bestehender Deprecation-Warnung in `test_rfq_endpoint.py`.
- Gefordertes Frontend-Kommando: grün, 4 Dateien / 41 Tests.
- `git diff --check`: grün.
- Forbidden-Language-Scan: bekannte Alt-/Test-/Dokumentations-Treffer bleiben sichtbar. Dieser Patch führt keine neue Material-, Produkt-, Hersteller- oder Freigabesprache ein.

## Restlücken

- Die Propagation ist für governed Graph-Aufrufe umgesetzt. Antwort-only Knowledge-Pfade nutzen weiterhin ihre eigene RuntimeAction/Run-Meta-Spur und gehen nicht durch `GraphState`.
- Der technische Challenge-Plan selbst nutzt weiterhin die kleine deterministische Extraktion aus dem letzten Turn plus State-Snapshot. Das ist bewusst begrenzt und kein Ersatz für volle Domain-Normalisierung.
- Bestehende Legacy-/Dokumentations-Treffer im Forbidden-Language-Scan bleiben außerhalb dieses Patches.

## Nächste Empfehlung

Als nächster sinnvoller Patch: mid-stream token expiry / SSE resilience isoliert härten, ohne Auth-Security oder governed final guard zu schwächen.
