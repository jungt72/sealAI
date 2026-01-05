# Frontend: Build-Reproduzierbarkeit + Security (Next.js)

## Problem/Risiken (Ist-Zustand)

- Im Repo existieren mehrere Node-Projekte inkl. Lockfiles (u.a. `package-lock.json` im Repo-Root und `frontend/package-lock.json`). Wenn der Frontend-Docker-Build versehentlich mit falschem Build-Context ausgeführt wird, kann er das falsche `package.json`/Lockfile verwenden (und damit eine andere Next-Version installieren).
- Docker-Cache ist grundsätzlich okay (Lockfile-unverändert ⇒ gleicher Layer), aber “Rebuild nutzt neue Version” klappt nur zuverlässig, wenn der Build wirklich auf dem richtigen Lockfile basiert und nicht aus Versehen ein altes/bereits gebautes Image reused/pulled wird (z.B. `:latest`).

## Änderungen (Fixes)

### Reproduzierbarer Frontend-Container-Build

- `frontend/Dockerfile`: Fail-fast Guard, der sicherstellt, dass der Build-Context wirklich `./frontend` ist (prüft `package.json.name`), damit nicht versehentlich das Repo-Root-Projekt gebaut wird.
- `frontend/Dockerfile`: entfernt den “Lock kaputt → löschen → `npm install`”-Fallback. Der Build nutzt deterministisch `npm ci` (Lockfile ist Quelle der Wahrheit; bei Drift bricht der Build ab).
- `docker-compose.yml`: Frontend wird lokal gebaut und eindeutig getaggt (`sealai-frontend:${BUILD_ID:-dev}`) + `pull_policy: build`, damit `docker compose up` nicht still ein vorhandenes Image reused.
- `frontend/Dockerfile`: schreibt die tatsächlich installierte Next-Version nach `/app/NEXT_VERSION` (bereits vorhanden) und übernimmt diese Datei ins Runtime-Image.
- `frontend/next.config.js`: entfernt das deprecated `eslint`-Key und setzt `turbopack.root`, damit Next nicht “aus Versehen” das Repo-Root als Workspace-Root/Lockfile heranzieht.

### Dependency-Versionierung (bewusste Bumps)

- `frontend/package.json`: `next` ist exakt gepinnt (`16.0.10`) statt `^…`, um “zufällige” Minor/Patch-Upgrades außerhalb des Lockfiles zu vermeiden.

## Verifikation (Build + Runtime)

Manuell:

```bash
BUILD_ID=$(git rev-parse --short HEAD)
BUILD_ID=$BUILD_ID docker compose build --no-cache frontend
BUILD_ID=$BUILD_ID docker compose up -d --force-recreate frontend
docker exec frontend node -p "require('next/package.json').version"
docker exec frontend cat /app/NEXT_VERSION
```

Automatisiert (Smoke):

```bash
./scripts/verify_frontend_rebuild.sh
```

## Security Audit (npm)

Audit-Quelle: `cd frontend && npm audit --json`

### Findings (4 total)

- **critical**: `node-extend` (direct) – Code Injection (kein Fix verfügbar) → entfernt, da im Frontend-Code nicht verwendet.
- **high**: `glob` (transitiv via `tailwindcss -> sucrase -> glob`) – Command injection im CLI-Flag `--cmd` → via npm `overrides` auf `glob@10.5.0`.
- **moderate**: `mdast-util-to-hast` (transitiv via `react-markdown`/`rehype-raw`) – unsanitized `class` attribute → via npm `overrides` auf `mdast-util-to-hast@13.2.1`.
- **moderate**: `next-auth` (direct) – Email misdelivery vulnerability → bump auf `4.24.12`.

Audit nach Fixes: `total: 0` (siehe `npm audit --json`).

### Empfehlung

- `npm ci` im Dockerfile beibehalten (kein Fallback auf `npm install`), damit das Lockfile die tatsächliche Next-/Dependency-Version deterministisch festlegt.
- Für Deployments, die **nur** Images ziehen (z.B. `docker-compose.deploy.yml`), ist die verwendete Version ausschließlich durch den Image-Tag bestimmt (nicht durch lokale Lockfiles). Dafür Tags bewusst/immutable wählen (z.B. Git-SHA statt `latest`).
- Hinweis: `next-auth@4.x` deklariert Next-Peer-Support bis `^15` (nicht `^16`). Installation läuft hier bewusst mit `legacy-peer-deps`; wenn das in Zukunft Probleme macht, ist ein geplanter Umstieg auf `next-auth@5` die sauberere (potenziell breaking) Lösung.
