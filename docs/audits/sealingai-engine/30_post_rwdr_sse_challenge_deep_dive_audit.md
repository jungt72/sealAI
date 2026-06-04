# 30 Post RWDR/SSE/Challenge Deep-Dive Audit

Datum: 2026-05-27
Repo: `/home/thorsten/sealai`
Branch: `demo/rwdr-limited-external`
HEAD: `42ee1cc8bf3dd2c25b3b50fea44d79e3c59b4508`

## Executive Summary

Der aktuelle Code-Stand zeigt fokussiert grüne RWDR-, SSE-, BFF- und `technical_case_challenge`-Tests. Die jüngsten Architekturbausteine sind im Arbeitsbaum sichtbar: DB-backed RWDR Case-State, Evidence/Confirmation Gate, Technical RWDR RFQ Brief, `technical_case_challenge`, explizite `answer_mode`-Propagation, SSEEventBuilder, `turn_id`-Boundary und Mid-stream-Interruption Handling.

Die Live-/Deploy-Reife ist trotzdem nicht erreicht. Der Branch-HEAD ist zwar auf `origin/demo/rwdr-limited-external` gepusht, aber der auditierte Stand liegt in einem stark dirty Worktree mit vielen uncommitted und untracked Dateien. Zusätzlich ist der live/lokal laufende Backend-Container nicht auf dem auditierten Stand: `POST /api/v1/rfq/rwdr/analyze` liefert direkt gegen Backend/API `404`, obwohl der aktuelle Arbeitsbaum die Route enthält.

Kurz: Die fokussierte lokale Produktlogik wirkt demo-fähig, der aktuell laufende Live-/Container-Stand ist es für RWDR nicht.

## Readiness Verdict

| Ziel | Verdict | Begründung |
| --- | --- | --- |
| Geführte interne Demo | Bedingt bereit | Fokussierte RWDR/SSE/Challenge/Frontend-Tests sind grün. Nur mit klar markiertem lokalen/auditierten Stand und ohne Behauptung, dass Live bereits gleichzieht. |
| Begrenzte externe RWDR-Fach-Demo | Nicht bereit | Worktree ist nicht sauber, Änderungen sind nicht commit-/deploy-reproduzierbar, live/direct RWDR analyze ist `404`. |
| Späterer Live-Deploy des RWDR-Demo-Branches | Nicht bereit | Erst P0: Commit/Pushed State herstellen, Backend-Route live verifizieren, Container/Image Drift beheben, Broad-Drift triagieren. |

Klare Entscheidung: **patchen, nicht deployen**. Weiteres Audit ist nur nach P0-Fixes sinnvoll.

## Git/Branch/Worktree-Status

Ausgeführt:

```bash
pwd
git status --short
git status -sb
git branch --show-current
git log -5 --oneline --decorate
git remote -v
git worktree list
git rev-parse HEAD
git rev-parse --abbrev-ref --symbolic-full-name @{u} || true
git rev-parse @{u} || true
git log --oneline @{u}..HEAD || true
git log --oneline HEAD..@{u} || true
git branch --list demo/rwdr-limited-external origin/demo/rwdr-limited-external -vv
```

Befund:

- Aktueller Branch: `demo/rwdr-limited-external`.
- Upstream: `origin/demo/rwdr-limited-external`.
- HEAD und Upstream zeigen beide auf `42ee1cc8bf3dd2c25b3b50fea44d79e3c59b4508`.
- Kein Ahead/Behind sichtbar.
- Letzte Commits:
  - `42ee1cc8 docs(rwdr): record demo deploy verification`
  - `f1f11626 feat(rwdr): prepare limited external demo`
- Remote: `git@github.com:jungt72/sealAI.git`.
- Worktree: stark dirty.
- Wichtige untracked/auditierte Dateien enthalten unter anderem:
  - `backend/app/agent/api/sse_contract.py`
  - `backend/app/agent/communication/technical_case_challenge.py`
  - `backend/app/agent/tests/test_sse_event_contract.py`
  - mehrere Audit-Reports `24` bis `29`
- Wichtige modified Dateien enthalten unter anderem:
  - `backend/app/agent/api/models.py`
  - `backend/app/agent/api/streaming.py`
  - `backend/app/agent/api/governed_runtime.py`
  - `backend/app/agent/communication/v7_contracts.py`
  - `backend/app/agent/communication/conversation_controller_v7.py`
  - `backend/app/agent/communication/communication_runtime_v8.py`
  - `backend/app/agent/communication/governed_answer_context.py`
  - `backend/app/agent/communication/governed_answer_composer.py`
  - `frontend/src/app/api/bff/agent/chat/stream/route.ts`
  - `frontend/src/hooks/useAgentStream.ts`

Status:

- committed: **NEIN für den auditierten aktuellen Arbeitsbaum**. HEAD selbst ist committed.
- pushed: **NEIN für den auditierten aktuellen Arbeitsbaum**. HEAD selbst ist gepusht.
- worktree clean: **NEIN**.
- deployable branch available: **UNKLAR/NEIN für aktuellen Stand**. Branch existiert, aber der relevante Audit-Stand ist dirty und nicht reproduzierbar.

## RWDR End-to-End Audit

Geprüfte Pfade:

- `backend/app/services/rwdr_mvp_brief.py`
- `backend/app/api/v1/endpoints/rfq.py`
- `backend/app/api/v1/renderers/rfq_pdf.py`
- `backend/app/api/tests/test_rwdr_golden_cases.py`
- `backend/tests/unit/services/test_rwdr_mvp_brief.py`
- `frontend/src/components/dashboard/RfqPane.tsx`
- `frontend/src/app/api/bff/rfq/rwdr/`
- `frontend/src/lib/bff/workspace.ts`
- `docs/product/sealing-intelligence/`

Codebelege:

- `backend/app/api/v1/endpoints/rfq.py:106` definiert `POST /rwdr/analyze`.
- `backend/app/api/v1/endpoints/rfq.py:245` definiert `POST /rwdr/cases/{case_id}/evaluate`.
- `backend/app/api/v1/endpoints/rfq.py:259` definiert `GET /rwdr/cases/{case_id}/brief`.
- `backend/app/api/v1/endpoints/rfq.py:273` definiert `GET /rwdr/cases/{case_id}/export.md`.
- `backend/app/api/v1/endpoints/rfq.py:287` definiert `GET /rwdr/cases/{case_id}/export.pdf`.
- `backend/app/services/rwdr_mvp_brief.py:295` definiert `EvidenceField` mit `confirmation_status`, `source_span`, `liability_bearing`, `allowed_in_brief`, `blocked_reason`.
- `backend/app/services/rwdr_mvp_brief.py:492` baut `EvidenceConfirmationIntelligence`.
- `backend/app/services/rwdr_mvp_brief.py:516` blockiert unbestätigte oder unsichere haftungsrelevante Felder.
- `backend/app/services/rwdr_mvp_brief.py:796` implementiert `DbRWDRCaseStateRepository`.
- `backend/app/services/rwdr_mvp_brief.py:827` schreibt `case_created_after_analyze`.
- `backend/app/services/rwdr_mvp_brief.py:852` wendet Confirmation Decisions an.
- `backend/app/services/rwdr_mvp_brief.py:886` erzeugt Evaluation/Brief/Exports und Revisionen.
- `backend/app/services/rwdr_mvp_brief.py:995` stellt Snapshots/Diff bereit.
- `frontend/src/lib/bff/workspace.ts:58` mappt `analyzeRwdrBff` auf `/api/bff/rfq/rwdr/analyze`.
- `frontend/src/lib/bff/workspace.ts:59` mappt `analyzeRwdrBackend` auf `/api/v1/rfq/rwdr/analyze`.

Antwort auf Audit-Fragen:

1. Vollständiger Flow vorhanden: **Ja im Arbeitsbaum**. `analyze -> confirm -> evaluate -> brief -> export.md -> export.pdf -> snapshots -> diff` ist code- und testseitig vorhanden.
2. DB-backed Case-State: **Ja**, über `DbRWDRCaseStateRepository`.
3. EvidenceFields Persistenz: **Ja**, in Case-State/Snapshots.
4. Confirmation Decisions: **Ja**, werden angewendet und revisioniert.
5. Unconfirmed liability-bearing fields: **Ja**, werden aus confirmed facts ausgeschlossen.
6. `explicitly_unknown`: **Ja**, wird als expliziter Status behandelt und nicht als bestätigte technische Wahrheit hochgezogen.
7. Keine Material-/Produkt-/Herstellerempfehlung: **Im RWDR-MVP-Pfad ja**, mit Forbidden-Term Guard und Export-Metadaten.
8. Golden Cases: **Aktuell grün**.
9. PDF/Markdown Sections: **Vorhanden und testgedeckt**, Polishing bleibt P2.
10. Demo-Flow dokumentiert: **Teilweise**, aber Live-/Deploy-Nachweis ist nicht konsistent mit laufendem Backend.

## technical_case_challenge Audit

Geprüfte Pfade:

- `backend/app/agent/communication/v7_contracts.py`
- `backend/app/agent/communication/conversation_controller_v7.py`
- `backend/app/agent/communication/communication_runtime_v8.py`
- `backend/app/agent/communication/technical_case_challenge.py`
- `backend/app/agent/communication/governed_answer_context.py`
- `backend/app/agent/communication/governed_answer_composer.py`
- `backend/app/agent/prompts/governed/answer_composer.j2`
- `backend/app/agent/graph/__init__.py`
- `backend/app/agent/api/governed_runtime.py`
- `backend/app/agent/graph/output_contract_assembly.py`

Codebelege:

- `backend/app/agent/communication/v7_contracts.py:24` enthält `AnswerMode.TECHNICAL_CASE_CHALLENGE`.
- `backend/app/agent/communication/v7_contracts.py:198` trägt `RuntimeAction.answer_mode`.
- `backend/app/agent/communication/v7_contracts.py:330` mapped Challenge/Governed Intake auf den governed graph path.
- `backend/app/agent/communication/conversation_controller_v7.py:351` erzeugt TurnDecision für `technical_case_challenge`.
- `backend/app/agent/communication/communication_runtime_v8.py:104` prüft die Challenge-Route vor dem normalen Question-Pfad.
- `backend/app/agent/api/governed_runtime.py:70` liest `runtime_action.answer_mode`.
- `backend/app/agent/api/governed_runtime.py:258` schreibt `runtime_answer_mode` in GraphState.
- `backend/app/agent/graph/__init__.py:98` definiert `GraphState.runtime_answer_mode`.
- `backend/app/agent/graph/output_contract_assembly.py:827` übernimmt `answer_mode` ins `output_public`.
- `backend/app/agent/communication/governed_answer_context.py:486` bevorzugt expliziten Mode aus `output_public`.
- `backend/app/agent/communication/governed_answer_context.py:524` baut bei explizitem `technical_case_challenge` den Plan mit `force=True`.
- `backend/app/agent/communication/governed_answer_context.py:534` erlaubt Fallback-Inferenz nur ohne expliziten Mode.
- `backend/app/agent/communication/technical_case_challenge.py:13` definiert `RWDRChallengeSignals`.
- `backend/app/agent/communication/technical_case_challenge.py:33` definiert `TechnicalCaseChallengePlan`.
- `backend/app/agent/communication/technical_case_challenge.py:322` berechnet Umfangsgeschwindigkeit mit `pi * d1 * rpm / 60000`.
- `backend/app/agent/communication/governed_answer_composer.py:569` rendert bei Challenge den deterministischen Plan.

Audit-Ergebnis:

- Explizite Erkennung: **Ja**.
- `RuntimeAction.answer_mode`: **Ja**.
- Propagation durch GraphState: **Ja**.
- Übernahme in `output_public`: **Ja**.
- GovernedAnswerContext nutzt expliziten Mode vor Fallback: **Ja**.
- Deterministischer Plan: **Ja**.
- RWDR-Signale: **Ja**, inklusive d1/D/b, Medium, Druck, Temperatur, Drehzahl, Umfangsgeschwindigkeit, Anwendung, Gegenlauffläche, Materialnennungen, Review Flags und Missing Critical Fields.
- SBB/Salzwasser-Fälle: **Testseitig grün**.
- PTFE/FKM bleibt Knowledge Mode: **Testseitig grün**.
- Fallback-Risiko: **Begrenzt**, Fallback-Inferenz existiert weiterhin für Legacy-Pfade ohne expliziten Mode.

## SSE Contract Audit

Geprüfte Pfade:

- `backend/app/agent/api/sse_contract.py`
- `backend/app/agent/api/streaming.py`
- `backend/app/agent/api/routes/chat.py`
- `backend/app/agent/api/governed_runtime.py`
- `backend/app/agent/tests/test_sse_event_contract.py`
- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- `frontend/src/hooks/useAgentStream.ts`

Codebelege:

- `backend/app/agent/api/sse_contract.py:12` definiert sichtbare Event-Typen.
- `backend/app/agent/api/sse_contract.py:22` validiert `turn_id` ohne User-Text.
- `backend/app/agent/api/sse_contract.py:30` erzeugt UUID-Fallback `turn:<uuid>`.
- `backend/app/agent/api/sse_contract.py:77` übernimmt `request.turn_id` oder `request.request_id`.
- `backend/app/agent/api/sse_contract.py:98` schützt `final_emitted`.
- `backend/app/agent/api/sse_contract.py:102` erhöht `sequence` monoton.
- `backend/app/agent/api/sse_contract.py:104` bildet `event_id = <turn_id>:<sequence>`.
- `backend/app/agent/api/sse_contract.py:108` serialisiert `event_type`, `is_final`, `error_code`, `data`.
- `backend/app/agent/api/streaming.py:1052` erstellt den Builder pro Stream-Request.
- `backend/app/agent/api/streaming.py:327` nutzt den Builder auch im Fast-Response-Pfad.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:336` löst `turn_id` aus Client-Payload oder `crypto.randomUUID`.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:346` sendet `turn_id` an Backend.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:312` reicht Backend-Metadaten weiter.
- `frontend/src/hooks/useAgentStream.ts:220` erzeugt pro Send einen Client-Turn.
- `frontend/src/hooks/useAgentStream.ts:531` dedupliziert Events.
- `frontend/src/hooks/useAgentStream.ts:509` behandelt `[DONE]` ohne Assistant-Finalisierung.

Audit-Ergebnis:

1. `turn_id` an Route Boundary: **Ja**, frontend/BFF erzeugen oder übernehmen.
2. `turn_id` Quelle: **Client bevorzugt, BFF-Fallback, Backend-Fallback für Legacy**.
3. Backend UUID-Fallback statt session/message hash: **Ja**.
4. Konstant pro Turn: **Ja**, contractseitig.
5. Gleiche User Messages unterschiedliche `turn_id`: **Ja**, bei Frontend/BFF UUID-Erzeugung und Backend-Fallback.
6. `event_id = <turn_id>:<sequence>`: **Ja**.
7. `sequence` monoton: **Ja**.
8. Genau ein erfolgreiches `is_final=true`: **Ja**, über `final_emitted`.
9. `error/interrupted` mit `error_code`: **Ja**, soweit über Contract/BFF-Pfad erzeugt.
10. Token/Secret-Leak in Events: **Kein konkreter Leak gefunden**; Error-Events werden strukturiert/sanitized.
11. Legacy Events: **Ja**, `[DONE]` bleibt.
12. `[DONE]` harmlos: **Aktuell ja**, Hook finalisiert darauf nicht.
13. BFF-Synthetik: **Ja**, BFF erzeugt weiter `answer.stream.*` aus finalem `state_update`.
14. Synthetische Events metadatiert: **Teilweise ausreichend**, aber nicht backend-originär. Das bleibt P1.

## Auth/Token Expiry Audit

Geprüfte Pfade:

- `frontend/src/lib/bff/auth-token.ts`
- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- `frontend/src/lib/bff/http.test.ts`
- `frontend/src/app/api/bff/agent/chat/stream/route.spec.ts`
- `frontend/src/hooks/useAgentStream.ts`

Codebelege:

- `frontend/src/lib/bff/auth-token.ts:187` implementiert Refresh über `refresh_token`.
- `frontend/src/lib/bff/auth-token.ts:286` liefert `getAccessTokenResult` mit optionalem `forceRefresh`.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:369` holt initialen Access Token.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:390` macht bei Start-401/`token_expired` einen einmaligen Force-Refresh-Retry.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:610` erzeugt bei Reader-Fehlern ein strukturiertes `interrupted` Event.
- `frontend/src/hooks/useAgentStream.ts:180` mapped Auth/Error Codes.
- `frontend/src/hooks/useAgentStream.ts:623` behandelt `error/interrupted` als unterbrochen, nicht final.

Audit-Ergebnis:

1. Pre-stream 401 -> Force refresh + einmaliger Retry: **Ja**.
2. Gleiche `turn_id` beim Retry: **Ja**, `turnId` wird vor Request erzeugt und wiederverwendet.
3. Mid-stream token expiry/interrupted: **Ja**, kontrollierter Interrupted-Pfad, kein Blind-Retry.
4. Keine Teilantwort finalisiert: **Ja**, Hook finalisiert nur bei finalem State.
5. Kein automatischer Blind-Retry nach Streamstart: **Ja**.
6. Re-Login/Retry-Hinweis: **Kontrolliert vorgesehen**, genauer UX-Text sollte weiter produktseitig geprüft werden.
7. Tokens nie geloggt: **Kein konkreter Token-Log gefunden**.
8. Rohes `expired token`: **Nicht im geprüften Pfad als User-Text nachweisbar**, Restrisiko bei unbekannten Backend-/Proxy-Errors bleibt.

## BFF/Frontend Stream Audit

Geprüfte Pfade:

- `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- `frontend/src/hooks/useAgentStream.ts`
- `frontend/src/lib/streamWorkspace.ts`
- `frontend/src/components/dashboard/ChatPane.tsx`
- `frontend/src/components/dashboard/ChatComposer.tsx`

Codebelege:

- `frontend/src/app/api/bff/agent/chat/stream/route.ts:86` erzeugt synthetische `answer.stream.*` Events aus finalem Text.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:502` streamt finalen `state_update` plus synthetische Answer Events.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:466` reicht `[DONE]` weiter.
- `frontend/src/hooks/useAgentStream.ts:386` schützt gegen doppelte identische Assistant-Finalisierung.
- `frontend/src/hooks/useAgentStream.ts:526` ignoriert Events mit falscher/alter `turn_id`.
- `frontend/src/hooks/useAgentStream.ts:531` dedupliziert per `event_id` oder `turn_id:sequence`.
- `frontend/src/hooks/useAgentStream.ts:584` behandelt `state_update` als finale Assistant-Quelle.
- `frontend/src/hooks/useAgentStream.ts:509` behandelt `[DONE]` nur als Stream-Ende, nicht als Antwortfinalisierung.

Audit-Ergebnis:

- Doppelte Assistant Messages: **Tests grün**, Hook schützt zentrale Fälle.
- Doppelte final events: **Backend final guard vorhanden; Frontend finalisiert nur einmal**.
- `state_update` plus `[DONE]`: **Kein doppeltes Finalisieren im Hook**.
- BFF-Synthetik plus Backend-Event: **Restlücke**, solange BFF `answer.stream.*` aus `state_update` erzeugt.
- Dedupe nach `event_id`: **Ja**.
- Fehlende `event_id`: **Fallback über `turn_id:sequence`**, ansonsten begrenzter Schutz über finalisierte Inhalte.
- Alte `turn_id` Events: **werden ignoriert**.

## Output/Forbidden-Language Audit

Ausgeführt:

```bash
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

Ergebnis: 472 Treffer.

Grobe Trefferverteilung:

- `backend/app`: 264
- `backend/tests`: 74
- `docs/implementation`: 53
- `docs/product`: 33
- `docs/audits`: 27
- `frontend/src`: 15
- `frontend/content`: 2
- `docs/communication`: 2
- einzelne Backend-Alt-/Skriptdateien: 2

Klassifikation:

- A. Erlaubter Disclaimer/Negation: **Viele Treffer**, z. B. RWDR-Brief-Disclaimer und Guards, die finale Freigabe ausdrücklich untersagen.
- B. Tests/Guards/Prompts/Audit-Doku: **Viele Treffer**, insbesondere Forbidden-Term-Listen und negative Assertions.
- C. Legacy non-RWDR intern: **Vorhanden**, z. B. interne `approved` Workflow-/Review-States.
- D. RWDR customer-facing must-fix: **Kein klarer aktiver RWDR-MVP-Treffer gefunden**. RWDR-Pfad wirkt produktdoktrin-konform.
- E. Challenge/Chat customer-facing must-fix: **Ein relevanter Treffer**: `backend/app/agent/api/routes/review.py:168` formuliert `Die technische Überprüfung ist für den definierten Anfrageumfang freigegeben.` Das ist nicht der RWDR-MVP-Flow, aber customer-facing und sollte vor externer Demo entschärft werden.

## Deploy/Live Readiness Audit

Ausgeführt:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' || true
docker compose ps || true
pm2 list || true
systemctl --type=service --state=running | grep -Ei "seal|sealai|frontend|backend|uvicorn|gunicorn|node|next|nginx" || true
ss -tulpn | grep -Ei "80|443|3000|8000|8080|5000" || true
curl -I https://sealingai.com || true
curl -s https://sealingai.com/api/health || true
curl -s https://sealingai.com/api/agent/health || true
```

Befund:

- Docker läuft:
  - `sealai-frontend-1`: Image `sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2`, healthy.
  - `backend`: Image `sealai-backend:v10-local-20260526-rwdr-gates`, healthy, `127.0.0.1:8000->8000`.
  - `nginx`, `keycloak`, `postgres`, `redis`, `qdrant` und weitere Services laufen.
- `pm2` zeigt keinen SealAI-Prozess.
- Public:
  - `https://sealingai.com`: `200`.
  - `https://sealingai.com/api/health`: `{"status":"ok"}`.
  - `https://sealingai.com/api/agent/health`: `{"status":"ok","service":"SSoT Agent Authority"}`.
- Lokal Backend:
  - `http://127.0.0.1:8000/api/agent/health`: `200`.
  - `http://127.0.0.1:8000/api/v1/ping`: `200`.
  - `http://127.0.0.1:8000/api/health`: `404`.

RWDR Smoke:

- Direkter lokaler Backend-POST `http://127.0.0.1:8000/api/v1/rfq/rwdr/analyze`: **404**.
- Direkter public POST `https://sealingai.com/api/v1/rfq/rwdr/analyze`: **404**.
- Public BFF POST `https://sealingai.com/api/bff/rfq/rwdr/analyze` ohne Auth: **401**, Route existiert und auth-gated.
- Authentifizierter BFF-RWDR-Flow wurde nicht ausgeführt, weil der Audit read-only war und `analyze` DB-Case-State erzeugen würde.

Live-Bewertung:

- live RWDR analyze: **404 direkt gegen Backend/API; authentifiziert via BFF unbewiesen und wegen Backend-404 kritisch**.
- live commit nachweisbar: **Nein für den auditierten Worktree**.
- deploy status: **running, aber nicht aktueller Audit-Stand**.

## Test Matrix

Ausgeführt:

```bash
bash scripts/check_rwdr_mvp_demo.sh || true
```

Ergebnis:

- RWDR golden cases: **13 passed**.
- RWDR/RFQ backend focused: **86 passed**, 1 DeprecationWarning.
- RWDR frontend focused: **16 passed**.
- Frontend broad innerhalb des Scripts: **149 passed**.
- Static diff hygiene im Script: **grün**.

Ausgeführt:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py
```

Ergebnis: **13 passed**.

Ausgeführt:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py
```

Ergebnis: **86 passed**, 1 DeprecationWarning.

Ausgeführt:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_sse_event_contract.py backend/app/agent/tests/test_governed_runtime_seam.py backend/app/agent/tests/test_conversation_runtime.py backend/app/agent/tests/test_governed_answer_composer.py backend/app/agent/tests/test_knowledge_answer_composer.py
```

Ergebnis: **147 passed**.

Ausgeführt:

```bash
npm --prefix frontend run test:run -- src/app/api/bff/agent/chat/stream/route.spec.ts src/hooks/useAgentStream.test.tsx src/lib/streamWorkspace.test.ts src/components/dashboard/ChatPane.test.tsx src/components/dashboard/ChatComposer.test.tsx src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
```

Ergebnis: **7 files, 66 tests passed**.

Ausgeführt:

```bash
npm --prefix frontend run test:run
```

Ergebnis: **27 files, 149 tests passed**.

Ausgeführt:

```bash
git diff --check
```

Ergebnis: **grün**.

Optional backend broad:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend
```

Ergebnis: **11 failed**, rest passed.

Fehlerklassifikation:

- `backend/app/agent/tests/graph/test_normalize_node.py::TestNoLLM::test_openai_never_called`: Erwartungsdrift durch zusätzliches `ambiguous_pressure_bar`.
- `backend/app/agent/tests/test_knowledge_debug_trace.py::*`: Knowledge debug trace/composer fallback drift.
- `backend/app/agent/tests/test_phase_f_streaming_cut.py::*`: Governed authority/canonical path drift.
- `backend/app/agent/tests/test_turn_context.py::test_build_governed_turn_context_stays_small_and_compatible`: Turn-context contract drift.
- `backend/app/agent/tests/test_v7_runtime_dispatch.py::test_chat_endpoint_enters_governed_graph_for_enter_graph_runtime_action`: v7 dispatch/runtime persistence stub drift.
- `backend/app/agent/tests/v92/test_v92_orchestrator.py::*`: v92 engineering node/O-ring/RWDR-ledger drift.

Bewertung: Nicht alle Fehler sind RWDR-MVP-Endpunkte, SSE-Contract oder Challenge-Fokus. Sie sind aber relevante V10/Graph/Runtime-Drift und verhindern ein sauberes Deploy-Gate.

## P0 Findings

### P0-1: Auditierter Stand ist nicht commit-/deploy-reproduzierbar

Der Branch-HEAD ist gepusht, aber zentrale aktuelle Änderungen liegen uncommitted/untracked im Worktree. Dazu gehören unter anderem `sse_contract.py`, `technical_case_challenge.py`, SSE-/Challenge-Tests und mehrere Audit-Reports. Ein Deploy von `origin/demo/rwdr-limited-external` würde daher nicht sicher den auditierten Stand enthalten.

Auswirkung: Externe Demo oder Live-Deploy wäre nicht reproduzierbar und könnte ohne die geprüften Fixes laufen.

Empfehlung: Dirty Worktree aufteilen, relevante RWDR/SSE/Challenge/Auth-Dateien committen, danach frischen Clone/Worktree testen.

### P0-2: Live/direct RWDR analyze ist nicht verfügbar

Der aktuelle Arbeitsbaum enthält `POST /api/v1/rfq/rwdr/analyze`, aber der laufende Backend/API-Pfad liefert direkt lokal und public `404`. Die public BFF-Route existiert, endet unauthentifiziert aber korrekt mit `401`; der authentifizierte BFF-Pfad würde nach Code auf den Backend-Pfad zeigen, der live/direct `404` liefert.

Auswirkung: Die externe RWDR-Fach-Demo kann am ersten Schritt `analyze` blockieren.

Empfehlung: Container/Image-/Route-Drift beheben, neu bauen/deployen, `POST /api/v1/rfq/rwdr/analyze` im Ziel-Stack mit authentifiziertem oder sicherem Testkontext verifizieren.

## P1 Findings

### P1-1: Backend Broad Suite hat V10/Graph/Runtime-Drift

Die fokussierten Demo-Gates sind grün, aber `PYTHONPATH=backend .venv/bin/python -m pytest -q backend` hat 11 Fehler. Besonders relevant sind Governed Authority Path, v7 runtime dispatch, turn context und v92 engineering node drift.

Auswirkung: Chat-/Graph-/Runtime-Verhalten kann außerhalb des schmalen RWDR-MVP-Pfads instabil sein.

Empfehlung: Failures triagieren und mindestens alle deploy-relevanten V10/Governed Runtime Failures vor externer Demo schließen oder ausdrücklich aus dem Demo-Scope nehmen.

### P1-2: BFF erzeugt weiter synthetische `answer.stream.*` Events

`frontend/src/app/api/bff/agent/chat/stream/route.ts:86` erzeugt synthetische Stream-Events aus finalem `state_update`. Die Events sind inzwischen metadatiert und frontendseitig dedupliziert, bleiben aber nicht backend-originär.

Auswirkung: Contract-Verantwortung ist noch geteilt; zukünftige Backend-Event-Änderungen können Dedupe/Finalisierung wieder schwächen.

Empfehlung: Als nächster Streaming-Patch backend-originäre `answer.stream.*`/final events liefern und BFF-Synthetik reduzieren oder isolieren.

### P1-3: Customer-facing Review-Route enthält Freigabesprache

`backend/app/agent/api/routes/review.py:168` enthält: `Die technische Überprüfung ist für den definierten Anfrageumfang freigegeben.`

Auswirkung: Nicht RWDR-MVP-spezifisch, aber produktdoktrin-kritische Sprache in einem potentiell sichtbaren technischen Pfad.

Empfehlung: In einem kleinen Safety-Copy-Patch auf "für die weitere Bewertung vorbereitet" oder äquivalent entschärfen.

### P1-4: `[DONE]` bleibt Legacy

`[DONE]` wird weiterhin gesendet und weitergereicht. Frontend finalisiert darauf nicht, daher aktuell harmlos, aber nicht Teil des neuen typed SSE-Contracts.

Auswirkung: Legacy-Kompatibilität bleibt als Fehlerquelle erhalten.

Empfehlung: Nach P0/P1-Deploy-Fixes `[DONE]` isolieren oder durch typed `done` Event mit Contract-Metadaten ablösen.

## P2 Findings

- Forbidden-language Scan erzeugt viel Rauschen durch Tests, Guards, Prompts, historische Doku und interne Workflow-States.
- `/openapi.json` liefert `404`, was Route-Discovery im Audit erschwert.
- Direktes Backend `/api/health` liefert `404`; canonical health ist `/api/agent/health`.
- PDF/Markdown-Brief wirkt funktional, aber Layout-/Polish-Prüfung bleibt offen.
- Docs enthalten historische V8/V9/V10-Altformulierungen, die nicht automatisch produktive Pfade bedeuten.

## Konkrete nächste Patch-Empfehlung

Nächster Patch sollte kein neues Produktfeature bauen. Er sollte genau diese Reihenfolge haben:

1. Worktree konsolidieren: relevante RWDR/SSE/Challenge/Auth-Änderungen identifizieren, committen und gegen frischen Worktree testen.
2. Live-Route-Drift beheben: sicherstellen, dass der deployte Backend-Stack `POST /api/v1/rfq/rwdr/analyze` enthält.
3. Kleinen Safety-Copy-Patch für `backend/app/agent/api/routes/review.py:168`.
4. Backend Broad Failures triagieren, besonders Governed Runtime/v7/v92.
5. Danach erst BFF-Synthetik reduzieren und `[DONE]` Legacy isolieren.

## Entscheidung

Nicht deployen.

Nicht weiter breit auditieren, bevor P0 geschlossen ist.

Jetzt patchen:

- Reproduzierbarkeit herstellen.
- Live-RWDR analyze route reparieren/verifizieren.
- Freigabesprache in Review-Route entfernen.
- Broad Runtime Drift triagieren.

Erst danach ist eine begrenzte externe RWDR-Fach-Demo vertretbar.
