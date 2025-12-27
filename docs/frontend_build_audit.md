# Frontend Build Audit (Ist-Zustand)

Datum: 2025-12-16

## Scope / Safety

Dieses Audit und alle folgenden Änderungen betreffen ausschließlich:

- `frontend/**`
- `docker-compose*.yml`
- `nginx/**` (nur falls nötig)
- `docs/**`

Backend-/Keycloak-Dateien werden nicht geändert.

## PHASE 1 – Ist-Zustand (vor Fixes)

### `frontend/package.json`

- Scripts: `dev` → `next dev`, `build` → `next build`, `start` → `next start`, `lint` → `next lint`
- Next.js: Dependency `"next": "^16.0.10"` (tatsächlich gepinnte Version kommt aus Lockfile)

### Lockfiles (Repo-Root und `frontend/`) – vor Fixes

- Repo-Root: `package-lock.json` existiert.
- `frontend/`: `package-lock.json` existierte zusätzlich zu `pnpm-lock.yaml` (Konflikt/Mehrdeutigkeit).

### Dockerfile Frontend – vor Fixes

- Vorhanden: `frontend/Dockerfile`
- Auffälligkeit: nutzte eine Fallback-Logik, die bei Lockfile-Problemen `package-lock.json` löscht und auf `npm install` zurückfällt. Das macht Builds potentiell **nicht reproduzierbar** und kann “zufällig neue/alte” Versionen ziehen.

### `docker-compose.yml` Frontend Build/Pull – vor Fixes

- Service `frontend` nutzte nur `image: ghcr.io/jungt72/sealai-frontend:latest` und hatte **kein** `build:`. Dadurch wird bei `docker compose up` typischerweise ein vorhandenes `latest` Image reused bzw. gepulled – ohne Garantie, dass ein Rebuild wirklich den aktuellen gepinnten Stand aus dem Repo nutzt.

### Next Config – vor Fixes

- `frontend/next.config.js` enthielt die Option `eslint` (laut Aufgabenstellung zu entfernen).
- Zusätzlich existierte auch `frontend/next.config.mjs` → potenziell uneindeutige/abweichende Konfiguration je nach Loader/Datei-Priorität.

## PHASE 2 – Ursachen (warum “neue Next-Version” nach rebuild nicht garantiert ist)

- `docker-compose.yml` referenziert ein Remote-Image mit Tag `latest` (kein lokaler Build) → ein “Rebuild” kann effektiv nur ein altes `latest` wiederverwenden.
- Frontend-Dockerfile hatte ein “Lockfile kaputt → löschen → `npm install`”-Fallback → dadurch kann die installierte Next-Version vom Lockfile abweichen.
- Mehrere Lockfiles im Frontend (`package-lock.json` + `pnpm-lock.yaml`) → Tooling/Developer-Flow nicht eindeutig.
- Zwei Next-Projekte im Repo (Repo-Root hat eigenes `package.json` + `package-lock.json`, Frontend ebenfalls) → ohne klaren Compose-Build-Context kann man versehentlich “falsches” Lockfile/Projekt bauen.

## PHASE 2 – Fixes (Best Practice)

### A) Next config

- Entfernt: unzulässige `next.config`-Option `eslint`.
- Vereinheitlicht: nur noch eine Config-Datei (`frontend/next.config.js`), um Konfigurations-Drift zu vermeiden.

### B) Lockfile-Strategie (npm Standard)

- Entfernt: `frontend/pnpm-lock.yaml`
- Frontend ist eigenständig: Builds nutzen ausschließlich `frontend/package-lock.json` + `npm ci`.

### C) Dockerfile (Frontend) – “immer die gepinnte Version”

- Node Image: weiterhin `node:20-alpine` (stabiler Major, reproduzierbar über Lockfile-Install).
- Reihenfolge: erst `package.json` + `package-lock.json`, dann `npm ci`, dann App-Code, dann `npm run build`.
- Kein Fallback mehr auf `npm install` → Build bricht ab, wenn Lockfile/Dependencies out-of-sync sind.
- Build-Identität: `BUILD_ID` als Build-Arg + `NEXT_VERSION` Datei; Next-Version wird im Build geloggt.

### D) docker-compose.yml

- `frontend` wird lokal gebaut (`build: context: ./frontend`) und bekommt ein nicht-stummes Image-Tag: `sealai-frontend:${BUILD_ID:-dev}`.
- Optionaler Build-Arg: `BUILD_ID` (z.B. Git SHA), um Image/Container eindeutig zu identifizieren.

### E) Version-Check (Build + Runtime)

- Build-Log: Dockerfile gibt `require('next/package.json').version` aus.
- Runtime: im Container verfügbar via `cat /app/NEXT_VERSION` oder `node -p \"require('next/package.json').version\"`.

## PHASE 3 – Tests (Outputs)

Build-ID (Beispiel): `9adee4f`

### Lokal (npm)

Command:

```bash
cd frontend
npm ci --no-audit --no-fund
node -p "require('next/package.json').version"
npm run build
```

Output (gekürzt):

```text
added 334 packages in 9s
16.0.10
▲ Next.js 16.0.10 (Turbopack)
✓ Compiled successfully
```

Hinweis: In dieser Umgebung brauchte `next build` außerhalb der Workspace-Sandbox erweiterte Rechte (Turbopack startet Build-Worker und bindet temporär an Ports).

### Docker (compose)

Commands:

```bash
BUILD_ID=9adee4f docker compose build --no-cache frontend
BUILD_ID=9adee4f docker compose up -d --force-recreate frontend
docker exec frontend node -p "require('next/package.json').version"
docker exec frontend cat /app/NEXT_VERSION
```

Output (gekürzt):

```text
naming to docker.io/library/sealai-frontend:9adee4f
BUILD_ID=9adee4f
16.0.10
...
16.0.10
16.0.10
```

## Runbook: sicherer Rebuild (ohne “alte Next-Version”)

Empfohlen (BUILD_ID z.B. Git SHA setzen):

1) `BUILD_ID=$(git rev-parse --short HEAD) docker compose build --no-cache frontend`
2) `docker compose up -d --force-recreate frontend`
3) Next-Version prüfen:
   - `docker exec frontend node -p \"require('next/package.json').version\"`
   - oder: `docker exec frontend cat /app/NEXT_VERSION`
