# 32 RWDR Gate Fix Live Deploy Report

Datum: 2026-05-27
Repo: `/home/thorsten/sealai`
Branch: `demo/rwdr-limited-external`

## Script-Fix

`scripts/check_rwdr_mvp_demo.sh` wurde reproduzierbarer gemacht, indem der
Python-Interpreter von außen überschreibbar ist:

```bash
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
PYTHONPATH=backend "$PYTHON_BIN" -m pytest ...
```

Default bleibt `.venv/bin/python`; frische Deploy-Worktrees können z. B. mit
`PYTHON_BIN=/usr/bin/python3` laufen.

## Commit Hash

Patch-Commit:

```text
35968090b8660fd77a9fe41b7872c3f2366f4261
35968090 fix(rwdr): allow deploy gate python override
```

Ausgangs-/Runtime-Commit vor dem Fix:

```text
916201548089af6daad9858388fafc3d187e6fb8
```

## Push Status

Push erfolgreich:

```text
origin/demo/rwdr-limited-external = 35968090b8660fd77a9fe41b7872c3f2366f4261
```

Kein Force Push wurde verwendet.

## Deploy Worktree Status

Deploy-Worktree:

```text
/home/thorsten/sealai-rwdr-demo-deploy
```

Status nach Update:

```text
HEAD = 35968090b8660fd77a9fe41b7872c3f2366f4261
origin/demo/rwdr-limited-external = 35968090b8660fd77a9fe41b7872c3f2366f4261
git status --short = clean
```

Der Haupt-Worktree `/home/thorsten/sealai` bleibt dirty mit nicht zu diesem
Patch gehoerenden Aenderungen. Committed wurde nur
`scripts/check_rwdr_mvp_demo.sh`.

## Gate-Ergebnis

Lokal im Haupt-Worktree lief das Gate mit vorhandenem Python gruen:

```bash
PYTHON_BIN=/usr/bin/python3 ./scripts/check_rwdr_mvp_demo.sh
```

Ergebnis:

- RWDR golden cases: 13 passed.
- RWDR/RFQ backend focused suite: 86 passed, 1 DeprecationWarning.
- RWDR frontend focused suite: 3 files passed, 16 tests passed.
- Frontend broad suite: 27 files passed, 149 tests passed.
- `git diff --check`: clean.
- Forbidden-language scan: bekannte Legacy-/Test-/Guard-/Knowledge-/Audit-Treffer.

Deploy-Worktree-Gate:

```bash
PYTHON_BIN=/usr/bin/python3 ./scripts/check_rwdr_mvp_demo.sh
```

Erster Versuch:

```text
sh: 1: vitest: not found
```

Danach wurden im Deploy-Worktree die Lockfile-gepinnten Frontend-Abhaengigkeiten
mit `npm --prefix frontend ci` hergestellt. Es wurden keine
`package.json`-/Lockfile-Aenderungen erzeugt; `git status --short` blieb clean.

Zweiter Gate-Lauf im Deploy-Worktree:

```text
RWDR golden cases: 13 passed
RWDR/RFQ backend focused suite: 86 passed, 1 DeprecationWarning
RWDR frontend focused suite: 3 files passed, 16 tests passed
Frontend broad suite: 3 failed, 24 passed; 5 failed, 145 passed
```

Fehlende breite Frontend-Tests auf exakt dem Deploy-Commit:

```text
src/components/dashboard/CaseScreen.test.tsx
  maps a real workspace fixture into the RFQ workspace view

src/components/dashboard/ChatComposer.test.tsx
  renders the ChatGPT-style composer controls

src/components/dashboard/ChatPane.test.tsx
  places message identity icons above the related text
  places the composer in a Gemini-style first-run state with sealing prompts
  renders a restrained streaming placeholder before text chunks arrive
```

Bewertung:

- Der eigentliche Python-Repro-Fix funktioniert.
- Die RWDR-fokussierten Backend- und Frontend-Gates sind im Deploy-Worktree gruen.
- Das vollstaendige Deploy-Worktree-Gate ist rot, weil der gepushte Commit nicht
  die im dirty Haupt-Worktree vorhandenen Frontend-Test-/UI-Drifts enthaelt.
- Nach den Deploy-Regeln wurde der Deploy gestoppt.

## Deploy-Befehl

Nicht ausgefuehrt, weil das Deploy-Worktree-Gate rot ist.

Der vorgesehene scoped Deploy-Befehl nach gruenem Gate waere:

```bash
docker compose --env-file .env.prod -p sealai -f docker-compose.yml -f docker-compose.deploy.yml build backend frontend
docker compose --env-file .env.prod -p sealai -f docker-compose.yml -f docker-compose.deploy.yml up -d backend frontend
```

Es wurde kein `docker compose down`, kein `docker prune`, keine Volume-Loeschung
und keine Production-Migration ausgefuehrt.

## Container/Service Status

Bestehender Live-Stand, ohne neuen Deploy:

```text
backend             sealai-backend:v10-local-20260526-rwdr-gates                 Up 16 hours (healthy)
sealai-frontend-1   sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2 Up 5 hours (healthy)
nginx               nginx:1.29.4                                                  Up 6 days (healthy)
keycloak            ghcr.io/jungt72/sealai-keycloak:2026.05.14-1                 Up 6 days
postgres            postgres:15                                                   Up 12 days (healthy)
redis               redis/redis-stack-server:7.4.0-v8                             Up 12 days (healthy)
qdrant              qdrant/qdrant:v1.16.0                                         Up 10 days (healthy)
gotenberg           gotenberg/gotenberg:8.15.0                                    Up 10 days
tika                apache/tika:2.9.2.1                                           Up 10 days
```

## Health Checks

Bestehender Live-Stand, ohne neuen Deploy:

```text
GET https://sealingai.com/api/health
HTTP/2 200
{"status":"ok"}

GET https://sealingai.com/api/agent/health
HTTP/2 200
{"status":"ok","service":"SSoT Agent Authority"}

GET http://127.0.0.1:8000/health
HTTP/1.1 200 OK
{"status":"healthy", ...}
```

## RWDR Analyze Smoke

Bestehender Live-Stand, ohne neuen Deploy:

Direct local backend:

```text
POST http://127.0.0.1:8000/api/v1/rfq/rwdr/analyze
HTTP/1.1 404 Not Found
{"detail":"Not Found"}
```

Public direct:

```text
POST https://sealingai.com/api/v1/rfq/rwdr/analyze
HTTP/2 404
{"detail":"Not Found"}
```

Bewertung:

- Live/direct RWDR analyze ist weiterhin nicht verfuegbar.
- Das ist erwartbar, weil kein neuer Deploy ausgefuehrt wurde.

## BFF Auth Gate

Bestehender Live-Stand, ohne neuen Deploy:

```text
POST https://sealingai.com/api/bff/rfq/rwdr/analyze
HTTP/2 401
{"error":{"code":"auth_error","message":"Unauthorized"}}
```

Bewertung:

- Die BFF-Route existiert.
- Unauthenticated Zugriff ist auth-gated.

## technical_case_challenge Smoke

Ein fachlicher Live-Smoke war ohne Token/Session nicht sicher moeglich.

Unauthenticated BFF stream:

```text
POST https://sealingai.com/api/bff/agent/chat/stream
HTTP/2 401
{"error":{"code":"auth_error","message":"Deine Sitzung ist abgelaufen. Bitte melde dich erneut an."}}
```

Unauthenticated direct backend:

```text
POST http://127.0.0.1:8000/api/agent/chat
HTTP/1.1 401 Unauthorized
{"detail":"Authorization header fehlt oder ungültig"}
```

Bewertung:

- Auth-Gate funktioniert.
- Kein technischer Challenge-Inhalt wurde live erzeugt.
- Es wurden keine Tokens oder Secrets verwendet oder ausgegeben.

## Live Commit/Build Proof

Kein Proof fuer Commit `35968090b8660fd77a9fe41b7872c3f2366f4261`, weil kein
Deploy ausgefuehrt wurde.

Bestehende Container-Images:

```text
backend image=sealai-backend:v10-local-20260526-rwdr-gates
frontend image=sealai-frontend:v10-local-20260521-compact-calculation-tiles-v2
```

`org.opencontainers.image.revision` und `/app/BUILD_ID` lieferten in den
laufenden App-Containern keinen Commit-Nachweis.

## Remaining Blockers

1. Deploy-Worktree-Gate ist auf Commit `35968090b8660fd77a9fe41b7872c3f2366f4261`
   rot wegen breiter Frontend-Testdrift.
2. Der Haupt-Worktree enthaelt viele dirty Aenderungen, unter anderem Frontend
   UI/Test-Aenderungen, die lokal die breite Frontend-Suite gruen machen, aber
   nicht Teil des gepushten Deploy-Commits sind.
3. Live/direct `/api/v1/rfq/rwdr/analyze` bleibt `404`, weil kein Deploy
   ausgefuehrt wurde.
4. Live commit/build provenance ist fuer den Ziel-Commit nicht erbracht.

## Next Step

Die fehlenden Frontend-Test-/UI-Aenderungen muessen sauber isoliert, reviewed,
committed und gepusht werden, oder die breite Frontend-Gate-Erwartung muss mit
expliziter Release-Verantwortung angepasst werden. Danach:

```bash
cd /home/thorsten/sealai-rwdr-demo-deploy
git fetch origin demo/rwdr-limited-external
git checkout --detach <new-green-commit>
PYTHON_BIN=/usr/bin/python3 ./scripts/check_rwdr_mvp_demo.sh
```

Erst bei gruenem Deploy-Worktree-Gate sollte der scoped Compose-Deploy fuer
`backend frontend` ausgefuehrt und der RWDR analyze Smoke wiederholt werden.
