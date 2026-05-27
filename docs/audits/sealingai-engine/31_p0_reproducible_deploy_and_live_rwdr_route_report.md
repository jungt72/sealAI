# 31 P0 Reproducible Deploy and Live RWDR Route Report

Datum: 2026-05-27
Repo: `/home/thorsten/sealai`
Branch: `demo/rwdr-limited-external`

## 1. Commit Hash

Runtime-/Audit-Commit:

```text
916201548089af6daad9858388fafc3d187e6fb8
91620154 feat(rwdr): harden demo runtime and streaming contract
```

Der Report selbst wurde nach dem Runtime-Commit erzeugt und ist nicht Teil des deployed/runtime Commit-Nachweises.

## 2. Push Status

Push erfolgreich:

```text
origin/demo/rwdr-limited-external = 916201548089af6daad9858388fafc3d187e6fb8
HEAD                           = 916201548089af6daad9858388fafc3d187e6fb8
origin/demo/rwdr-limited-external..HEAD = leer
HEAD..origin/demo/rwdr-limited-external = leer
```

## 3. Git Ausgangszustand

Vor dem Commit:

- Arbeitsverzeichnis: `/home/thorsten/sealai`
- Branch: `demo/rwdr-limited-external`
- Upstream: `origin/demo/rwdr-limited-external`
- Ausgangs-HEAD: `42ee1cc8bf3dd2c25b3b50fea44d79e3c59b4508`
- Ausgangs-HEAD und Upstream waren synchron.
- Worktree war stark dirty mit vielen modified/untracked Dateien.

Nach dem Commit:

- Runtime-Commit ist lokal und remote synchron.
- Haupt-Worktree bleibt dirty mit bewusst nicht gestagten, nicht deployten Änderungen.
- Es wurde kein Force Push verwendet.

## 4. Staged Files Summary

Committed wurden 46 Dateien aus dem vorgesehenen RWDR/SSE/Challenge/Auth/Audit-Patchsatz:

- Backend SSE Contract: `backend/app/agent/api/sse_contract.py`
- Chat/SSE/turn_id Runtime-Pfade: `backend/app/agent/api/{governed_runtime.py,models.py,routes/chat.py,streaming.py}`
- Safety-Copy-Fix: `backend/app/agent/api/routes/review.py`
- `technical_case_challenge`: Runtime, Context, Composer, Graph-Propagation und Tests
- Frontend BFF/SSE/Auth-token Handling und Tests
- Auditberichte `01` bis `09` sowie `24` bis `30`

Nicht committed wurden bekannte unrelated Dirty-Änderungen, unter anderem Marketing/Branding, Package-/Nginx-/Compose-Drift, V10/Graph-Experimente, Backups und Env-Dateien.

## 5. Secrets / Safety

Secret-Dateisuche fand vorhandene Env-/Backup-/Zertifikat-/Token-namige Dateien im Repositorybaum. Keine dieser Dateien wurde gestaged oder committed.

Staged-Diff Secret-Scan:

- Kein Credential-/Private-Key-Treffer im staged Diff.
- Ein Treffer auf `suitability` in einem Audittext war kein Secret.

## 6. Tests/Gates

Grün vor Commit:

```text
bash scripts/check_rwdr_mvp_demo.sh
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests/test_sse_event_contract.py backend/app/agent/tests/test_governed_runtime_seam.py backend/app/agent/tests/test_conversation_runtime.py backend/app/agent/tests/test_governed_answer_composer.py backend/app/agent/tests/test_knowledge_answer_composer.py
npm --prefix frontend run test:run -- src/app/api/bff/agent/chat/stream/route.spec.ts src/hooks/useAgentStream.test.tsx src/lib/streamWorkspace.test.ts src/components/dashboard/ChatPane.test.tsx src/components/dashboard/ChatComposer.test.tsx src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
npm --prefix frontend run test:run
git diff --check
```

Ergebnisse:

- RWDR golden cases: 13 passed.
- RWDR/RFQ backend focused suite: 86 passed, 1 known deprecation warning.
- Agent/SSE focused suite: 147 passed.
- Frontend focused suite: 7 files passed, 66 tests passed.
- Frontend broad suite: 27 files passed, 149 tests passed.
- `git diff --check`: clean.

Forbidden-language scan:

- Liefert weiterhin bekannte Legacy-/Test-/Guard-/Knowledge-Daten-/Audit-Treffer.
- Der P1 customer-facing Treffer in `review.py` wurde entschärft.
- Nicht-RWDR broad failures wurden dokumentiert, nicht breit umgebaut.

## 7. Deploy Worktree

Deploy-Worktree:

```text
/home/thorsten/sealai-rwdr-demo-deploy
```

Status:

```text
git status --short = clean
HEAD = 916201548089af6daad9858388fafc3d187e6fb8
origin/demo/rwdr-limited-external = 916201548089af6daad9858388fafc3d187e6fb8
```

Deploy-Worktree-Gate:

```text
bash scripts/check_rwdr_mvp_demo.sh
```

Ergebnis:

```text
scripts/check_rwdr_mvp_demo.sh: line 8: .venv/bin/python: No such file or directory
```

Bewertung:

- Der Deploy-Worktree ist sauber und auf dem richtigen Commit.
- Der vorgeschriebene Gate-Mechanismus ist im frischen Deploy-Worktree nicht reproduzierbar, weil `.venv` nicht Teil des Worktrees ist.
- Nach der Vorgabe "Wenn fehlschlägt: STOP. Nicht deployen." wurde kein Deploy ausgeführt.

## 8. Deploy Mechanism

Erkannter laufender Compose-Pfad aus Container-Labels:

```text
Project: sealai
Compose files: /home/thorsten/sealai/docker-compose.yml,/home/thorsten/sealai/docker-compose.deploy.yml
WorkingDir: /home/thorsten/sealai
Backend service/container: backend / backend
Frontend service/container: frontend / sealai-frontend-1
Nginx service/container: nginx / nginx
Keycloak service/container: keycloak / keycloak
```

Aktuelle laufende App-Images vor einem Deploy:

```text
backend: sealai-backend:v10-local-20260526-rwdr-gates
frontend: sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2
```

Geplanter, aber nicht ausgeführter scoped Deploy-Befehl wäre nur nach grünem Deploy-Worktree-Gate zulässig gewesen, zum Beispiel:

```text
docker compose --env-file .env.prod -p sealai -f docker-compose.yml -f docker-compose.deploy.yml build backend frontend
docker compose --env-file .env.prod -p sealai -f docker-compose.yml -f docker-compose.deploy.yml up -d backend frontend
```

Dieser Befehl wurde nicht ausgeführt.

## 9. Deploy Result

Kein Deploy ausgeführt.

Grund:

- Clean Deploy Worktree Gate schlägt wegen fehlender `.venv/bin/python` fehl.
- Die Hard Rule "Kein Deploy aus dirty Worktree" wurde eingehalten.
- Die Stop-Regel nach fehlgeschlagenem Deploy-Worktree-Gate wurde eingehalten.

## 10. Health Results

Bestehender Live-Stand, ohne neuen Deploy:

```text
curl -I https://sealingai.com
HTTP/2 200

curl -s https://sealingai.com/api/health
{"status":"ok"}

curl -s https://sealingai.com/api/agent/health
{"status":"ok","service":"SSoT Agent Authority"}
```

## 11. RWDR Analyze Smoke

Bestehender Live-/Container-Stand, ohne neuen Deploy:

Direct local backend:

```text
POST http://127.0.0.1:8000/api/v1/rfq/rwdr/analyze
HTTP 404
{"detail":"Not Found"}
```

Public direct:

```text
POST https://sealingai.com/api/v1/rfq/rwdr/analyze
HTTP 404
{"detail":"Not Found"}
```

Bewertung:

- P0-2 ist nicht geschlossen.
- Die Live-/Container-Route ist weiterhin nicht verfügbar, weil nicht deployed wurde.

## 12. BFF Auth Gate

Bestehender Live-/Container-Stand, ohne neuen Deploy:

```text
POST https://sealingai.com/api/bff/rfq/rwdr/analyze
HTTP 401
{"error":{"code":"auth_error","message":"Unauthorized"}}
```

Bewertung:

- BFF-Route existiert und ist unauthenticated auth-gated.
- Der direkte Backend-RWDR-Analyze-Pfad bleibt im laufenden Container `404`.

## 13. technical_case_challenge Smoke

Kein Live-Smoke nach Deploy möglich, weil kein Deploy durchgeführt wurde.

Nachweis vor Commit:

- Agent/SSE/Challenge focused suite grün:
  - `backend/app/agent/tests/test_sse_event_contract.py`
  - `backend/app/agent/tests/test_governed_runtime_seam.py`
  - `backend/app/agent/tests/test_conversation_runtime.py`
  - `backend/app/agent/tests/test_governed_answer_composer.py`
  - `backend/app/agent/tests/test_knowledge_answer_composer.py`

Erwartete Live-Prüfung nach erfolgreichem Deploy:

```text
Salzwasser; Temperatur 50 °C; Druck 2 bar; Drehzahl 3000 rpm; Wellendurchmesser 40 mm; Boot; RWDR; Gegenlauffläche 0,2. Bitte als technical_case_challenge analysieren.
```

Zu prüfen:

- Keine Materialfreigabe.
- Keine Produktempfehlung.
- Umfangsgeschwindigkeit ca. 6,28 m/s.
- Nächste beste Rückfrage.
- Keine doppelte Antwort.

## 14. Live Commit/Build Proof

Nicht erbracht.

Begründung:

- Kein Deploy ausgeführt.
- Laufende Container stammen aus bestehenden Images:
  - `sealai-backend:v10-local-20260526-rwdr-gates`
  - `sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2`
- Container-Labels zeigen weiterhin WorkingDir `/home/thorsten/sealai`, nicht den frischen Deploy-Worktree.
- Direct RWDR analyze bleibt `404`.

## 15. Review.py Safety Copy

Geändert in `backend/app/agent/api/routes/review.py`:

```text
alt: Die technische Überprüfung ist für den definierten Anfrageumfang freigegeben.
neu: Die technische Überprüfung ist für den definierten Anfrageumfang vorbereitet.
```

Zusätzlich wurde die negative Alternative entschärft:

```text
alt: Die technische Überprüfung ist noch nicht freigegeben; offene Punkte bleiben sichtbar.
neu: Die technische Überprüfung ist noch nicht abgeschlossen; offene Punkte bleiben sichtbar.
```

Keine Freigabe-, Suitable-, Approved- oder finale Eignungssprache wurde eingeführt.

## 16. Remaining Blockers

P0 verbleibend:

1. Deploy-Worktree-Gate ist nicht reproduzierbar, weil `scripts/check_rwdr_mvp_demo.sh` hart `.venv/bin/python` im Worktree erwartet.
2. Kein Deploy wurde ausgeführt.
3. Live/direct RWDR analyze bleibt `404`.
4. Kein Live-Commit-/Build-Proof für `916201548089af6daad9858388fafc3d187e6fb8`.
5. `technical_case_challenge` wurde nicht live gesmoked, nur lokal testseitig verifiziert.

P1/P2 verbleibend:

- Bekannte breite Legacy-/Test-/Guard-/Knowledge-Daten-Treffer im Forbidden-Language-Scan.
- Nicht-RWDR broad failures wurden bewusst nicht breit umgebaut.

## 17. Next Step

Nächster Patch:

1. `scripts/check_rwdr_mvp_demo.sh` reproduzierbar für frische Worktrees machen, ohne Secrets oder Dependency-Drift zu erzeugen. Konservativer Ansatz: Python-Interpreter via `PYTHON_BIN` überschreibbar machen und Default `.venv/bin/python` beibehalten.
2. Patch committen und pushen.
3. Frischen Deploy-Worktree auf den neuen Commit setzen.
4. Deploy-Worktree-Gate mit explizitem, vorhandenem Interpreter ausführen, ohne den Worktree zu dirtien.
5. Erst danach Backend/Frontend aus dem Deploy-Worktree rebuilden/updaten.
6. RWDR analyze direct local/public, BFF auth gate und `technical_case_challenge` live smoken.
