# AUDIT: CVE-2025-55182 (React RSC RCE) / CVE-2025-66478 (Next.js App Router)

## A) Repository discovery
- The root `package.json` is a Next.js 15 project (`dependencies.next` was upgraded to **15.3.6**) and pulls React 19.1.1/React DOM 19.1.1 via `package-lock.json`. `npm ls` (see section D) shows Next 15.3.6 as the resolved runtime; there are no direct `react-server-dom-webpack/parcel/turbopack` entries outside of Next itself.
- The actual application sitting in `frontend/` ships a separate Next.js workspace which depends on **Next 16.0.10** and React 18.2.0 (both pinned in `frontend/package.json` and confirmed by `frontend/package-lock.json` via `python3 - <<'PY' ...` returning `next 16.0.10`, `react 18.2.0`, `react-dom 18.2.0`).
- App Router usage is obvious inside `frontend/src/app/` (the only `pages/` folder is absent). Notably `frontend/src/app/dashboard/ccx/page.tsx` is a server component (`// Server Component – KEIN "use client" …`), so React Server Components are active in the production bundle.
- No `next@canary` artifacts exist anywhere in `package.json` or nested `package-lock.json` entries (`rg '@next/canary'` returns nothing).

## B) Betroffenheits-Check
- **Next.js 15.3.1 (root workspace)** fell into the advisory window for CVE-2025-66478. The patched releases are 15.0.5, 15.1.9, 15.2.6, 15.3.6, 15.4.8, etc. We have updated the root project to **Next 15.3.6**, which is the minimum patched build for that minor line. The `package-lock.json` now lists `node_modules/next` as 15.3.6, so future installs will pull the patched code.
- **Next.js 16.0.10 (frontend workspace)** is already above 16.0.7, so it stayed unaffected by CVE-2025-66478.
- **React RSC RCE (CVE-2025-55182)** targets `react-server-dom-webpack/parcel/turbopack` versions shipping in the React 19 ecosystem. None of those packages are declared directly in this repo, and the `npm ls next react react-dom react-server-dom-webpack react-server-dom-parcel react-server-dom-turbopack` run produces zero such entries outside Next’s own dependency tree. React 19.1.1 remains in place but is bundled through the patched Next release, so there is no need for separate overrides/resolutions.
- App Router + server components are active across the build (see `frontend/src/app`), so the only mitigation path is to keep Next.js in the patched release window.

## C) Runtime / Docker / Deploy check
- `frontend/Dockerfile` (used by `docker-compose.yml`) runs `npm ci --include=dev --no-audit --no-fund --legacy-peer-deps` before `npm run build`. Because it copies `frontend/package-lock.json` before installing, the pinned Next/React versions are reproduced inside the container.
- `docker-compose.yml` still publishes ports 3000/8000 and builds the same `frontend` target—no changes were required there.
- `ops/sealai-stack.service` (covered in the stack hardening work) now runs the same compose command (`docker compose -f /root/sealai/docker-compose.yml -f /root/sealai/docker-compose.deploy.yml up -d --remove-orphans backend frontend`) so the patched Next version will always be deployed via the new systemd unit.

## D) Fix plan + Umsetzung
- **Versions**: root `package.json` now pins `next` to `15.3.6` and the lockfile updates describe `next@15.3.6`, `react@19.1.1`, `react-dom@19.1.1`. `frontend` remains on Next 16.0.10.
- **Verification commands executed**:
  1. `node -v && npm -v` → `v20.18.3` / `11.6.3`.
  2. `npm ci --legacy-peer-deps` after the pinning step (success).
  3. `npm ls next react react-dom react-server-dom-webpack react-server-dom-parcel react-server-dom-turbopack` → tree shows `next@15.3.6` resolving from this workspace and no additional `react-server-dom-*` packages, even though the command exits with ELSPROBLEMS because React 19.1.1 disagrees with some peer deps. The lack of `react-server-dom-*` entries is proof there are no direct vulnerable packages.
  4. `python3 - <<'PY'; import json; data=json.load(open('frontend/package-lock.json')); print(data['packages']['node_modules/next']['version'])` to capture `16.0.10` for the frontend workspace.
- **Manual lockfile edit avoided**: all changes to `package-lock.json` were produced by `npm install --package-lock-only --legacy-peer-deps` and `npm ci --legacy-peer-deps`, so the tree is consistent with the current npm client.

## E) Verification commands to repeat on VPS
1. `node -v && npm -v` (ensures the build host uses Node 20.x / npm 11.x).
2. `npm ci --legacy-peer-deps` (reinstalls dependencies according to the lockfile).
3. `npm ls next react react-dom react-server-dom-webpack react-server-dom-parcel react-server-dom-turbopack` (should print `next@15.3.6` and no RSC packages, even if npm complains about invalid React 19).
4. `cd frontend && npm ls next react react-dom react-server-dom-webpack react-server-dom-parcel react-server-dom-turbopack` (confirms the frontend workspace still resolves to Next 16.0.10/React 18.2.0).
5. `docker compose -f /root/sealai/docker-compose.yml -f /root/sealai/docker-compose.deploy.yml build frontend` (validates the Docker image uses the new lockfile).

## Deploy checklist
1. `npm ci --legacy-peer-deps` in the root workspace before building Docker images.
2. `docker compose -f /root/sealai/docker-compose.yml -f /root/sealai/docker-compose.deploy.yml up -d --remove-orphans backend frontend`.
3. `systemctl restart sealai-stack.service` (or `systemctl enable --now sealai-stack.service` when bootstrapping) to ensure the patched image is launched after the hardening work.
4. Run `./ops/stack_smoke.sh` to confirm backend+frontend stay reachable on 8000/3000.
5. Because this is a security patch, redeploy, confirm logs show no RSC errors, and rotate secrets if any token leakage is suspected downstream (standard post-security-deploy discipline).
