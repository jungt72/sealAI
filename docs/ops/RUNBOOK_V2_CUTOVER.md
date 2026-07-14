# RUNBOOK — V2 prod cutover (sealingai.com `/dashboard` + `/api/v2`)

> **Owner-executed.** CC prepares + validates (Phase 1 code gates, Phase 2 staging); the prod
> flip (Phase 3) is run by the owner against this runbook, low-traffic, rollback-ready.
> **Load-bearing safety property: at every step, ONE action reverts to the current V1-serving
> state.** V1 keeps running (dormant) through the proving period — it IS the rollback target.
> Decisions baked in (2026-06-10): owner-only users today → legal gate moves to the FIRST PILOT;
> FULL `/dashboard/*` takeover (V1 seo/analytics/case-detail routes are dead — no carve-outs);
> V1 decommission is a separate later phase.

## How the cutover works (one paragraph)

The live nginx bind-mounts the worktree file `nginx/default.conf`. The flip is ONE include line
(`include snippets/v2_dashboard.conf;` after `server_name sealingai.com;`), inserted/removed by
`ops/v2-flip.sh` (in-place edit — the file is a single-file bind mount, the inode must survive;
the script handles this and `nginx -t`-gates every reload). The snippet serves the static SPA
(`frontend-v2/dist`, mounted at `/usr/share/nginx/v2-client`) under `/dashboard/` with strict CSP,
and proxies `/api/v2/` to `backend-v2:8001` (variable proxy_pass — an absent backend-v2 never
breaks nginx). V1's post-login redirect (`/login` → `/dashboard/new`) lands on the SPA via
`try_files`; the SPA normalizes the URL and logs in via Keycloak SSO (client `sealai-v2`, PKCE,
in-memory token) — zero V1 code changes.

## Phase 1 — code gates (CC, done on `feat/v2-cutover`)

- Claim-boundary single source: `backend/sealai_v2/core/framing.py` → `GET /api/v2/framing`
  (public, `Cache-Control: max-age=300`); SPA fetches at boot, falls back to build-time constants;
  fallback contract-pinned to `contracts/framing.v2.json` by BOTH suites. The lawyer-reviewed text
  (pilot gate) lands in `core/framing.py` only.
- `/dashboard/new` → SPA URL normalization (non-callback subpaths → `/dashboard/`).
- reject-no-kid: `security/auth.py` requires a `kid` header + exact JWKS match (red-before-green).
- `backend/Dockerfile.v2` ships the FULL /api/v2 app (pins: `backend/requirements-v2.txt`,
  build-time import keystone); `GET /api/v2/health` alias added (the proxy preserves paths).
- `docker-compose.deploy.yml`: nginx gains two INERT ro mounts (`./nginx/snippets`,
  `./frontend-v2/dist`); `backend-v2` defined behind `profiles: [v2]` (orphan-proof vs
  `up -d --remove-orphans`), auth env preset, secrets via `--env-file` interpolation only.
- `ops/v2-flip.sh` (the switch + rollback), `ops/smoke-v2.sh` (unauthed + authed legs),
  `ops/guard-nginx-reload.sh` wired into both release scripts (blocks a reload that would
  silently drop live V2 routing — the branch-drift guard).

Validation: V2 offline suite + import-boundary keystone + `frontend-v2 npm run verify` +
`docker build -f backend/Dockerfile.v2 backend/` — all green before Phase 2.

## Phase 2 — staging validation (no prod mutation)

**Owner (additive to live Keycloak — V1's `nextauth` client untouched):** ✅ **DONE 2026-06-10** —
client `sealai-v2` created (uuid `b7a2dd0a-fd95-4e3c-af3d-f7e04997ae85`) via the owner's
interactively-authenticated kcadm session (no credentials handled by the agent). Verified by
read-back + example-token: public, PKCE S256, standard flow only, both redirect URIs/web origins,
`aud=sealai-v2`, `tenant_id=sealai`, `sid`/`sub` present, lifespan 1800 s. Rollback anchor:
`kcadm delete clients/b7a2dd0a-fd95-4e3c-af3d-f7e04997ae85 -r sealAI`. Spec was:
- Standard Flow ON, PKCE S256 required, no client secret.
- Redirect URIs: `https://sealingai.com/dashboard/*` AND `https://sealingai.com:8443/dashboard/*`.
- Web Origins: `https://sealingai.com` AND `https://sealingai.com:8443` (CORS for the staging
  cross-port token POST; remove both `:8443` entries after cutover).
- Audience mapper → tokens carry `aud=sealai-v2`; `tenant_id` claim mapper
  (precedent: `docs/ops/KEYCLOAK_TENANT_ID_MAPPER.md`).
- Recommended: access-token lifespan 15–30 min on this client (no silent renew in the SPA yet —
  one-click SSO re-login until the pilot-gate renewal work).

**CC:** staging stack under `ops/staging/` — `nginx-staging` on `0.0.0.0:8443:443` (real cert;
generated copy of `default.conf` with the include applied; snippets copy with the documented
staging-only CSP delta for the cross-port token POST; the isolated
`frontend-v2/.build/dashboard-candidate` artifact) +
`backend-v2-staging` (alias `sealai-backend-v2` on the staging network ONLY — prod nginx can
never resolve it). Optional hardening: firewall :8443 to the owner IP for the window.

The staging compose build/up has exactly one entrypoint:

```bash
./ops/staging/gen-staging-conf.sh
./ops/staging/up-staging-v2.sh
```

The wrapper checks the production release gate for operation `build`, then acquires the installed
global storage lease before Docker starts. The active production freeze therefore denies staging
builds on the production VPS too; use a separately controlled staging host or wait for the gated
freeze-lift workflow. A raw compose build/up is not an alternative.

**E2e checklist (all green, dated):** browser login → callback → URL normalizes; chat with
citations + vorläufig/candidate badges; memory view→edit→forget-one→forget-all; briefing with
Geltungsrahmen + provenance; banner text == `/api/v2/framing`; authed
`GET /api/v2/conversations/current/memory` → 200 (proves aud/iss/exp/tenant_id/sid/sub alignment);
`nginx -t`; `BASE_URL=https://sealingai.com:8443 ops/smoke-v2.sh` green; observe token-expiry UX.
*(Owner decision 2026-06-10: the devtools RUNTIME checks — no token in local/sessionStorage,
zero CSP violations — moved to pilot tracker item 5 as a HARD pilot gate; XSS-token-theft is a
multi-user threat model, low-impact owner-only, and the CSP header itself is machine-verified in
smoke. They no longer block the owner-only flip.)*

**Rollback dry-run (mandatory, rehearses the prod commands):**
1. `ops/v2-flip.sh --revert --file ops/staging/conf/default.conf --container nginx-staging`
   → `/dashboard/` serves the V1 response again, `/api/v2/*` 404s into the V1 catch-all
   (== current prod behavior). Re-apply.
2. `docker stop backend-v2-staging` → `/api/v2/*` 502, static SPA + V1 paths unaffected;
   restart recovers ≤ ~10 s WITHOUT reload (resolver `valid=10s`).
3. Orphan probe: `up -d --remove-orphans` with/without `--profile v2` — backend-v2 survives.

**HALT** with the dated validation report → owner gate before Phase 3.

## Phase 3 — the prod flip (OWNER, low-traffic window)

**Step 0 — preconditions (all must hold):**
- Pre-flip gate checklist below fully green.
- Worktree clean, on the flip ref; record `FLIP_REF=$(git rev-parse HEAD)` and the live anchors
  from the daemon (never memory): `docker inspect backend --format '{{.Config.Image}}'` etc.
- **`V1_ANCHOR` = the ROLLBACK TARGET, NOT the flip ref.** It is the CURRENT V1-serving prod git
  HEAD, re-read from the daemon at flip time: the git-sha prefix of the running backend image tag
  (`docker inspect backend --format '{{.Config.Image}}'` → `…sealai-backend:<sha>-…` →
  `V1_ANCHOR=<sha>`; cross-check the frontend tag carries the same sha). Verify it is the
  V1-serving ref by construction: `git show "$V1_ANCHOR":docker-compose.deploy.yml | grep -cE
  'v2-client|snippets|backend-v2'` → **0** (the flip ref has these mounts; V1_ANCHOR must NOT).
  At flip time the prod worktree state moves from that V1 ref to the flip ref — rollbacks
  check out FROM `$V1_ANCHOR`.
- The immutable dashboard artifact must be built outside the live bind mount,
  content-addressed, and bound to the exact GATE-10 manifest. This P1 contract
  is not implemented yet; a local `npm run verify` is evidence for candidate
  bytes only and cannot make them production-eligible.
- `docker exec nginx nginx -T | grep -cE '^\s*include snippets/v2_dashboard'` → 0, and the loaded
  config matches the worktree file.

**Step 1 — nginx recreate with the inert mounts (BLOCKED).**

There is currently no sanctioned production entrypoint for this recreate. A
raw Compose command would bypass both the release gate and the global storage
lease, so it is forbidden even if the mounts appear inert. P1 must provide an
exact-artifact, GATE-10-bound entrypoint with an attested rollback manifest and
lease acquisition before this step can be scheduled. The active freeze denies
this step; do not recreate Nginx manually.

**Step 2 — Gate-10-bound backend-v2 artifact promotion (BLOCKED).**

The old raw compose build/up path is retired. Production promotion is permitted only through the
Gate-10 workflow and the sanctioned release entrypoint:

```bash
BACKEND_V2_IMAGE='ghcr.io/jungt72/sealai-backend-v2@sha256:<approved-digest>' \
  ./ops/release-backend-v2.sh --final
```

While the production freeze is active—and until the P1 release-integrity work binds the exact
selected artifact digest—this step stays deliberately blocked. Do not replace the denied
entrypoint with a direct Docker or compose command.

Verify: `curl -fsS --max-time 10 http://127.0.0.1:8001/health`; then
`curl -s --max-time 10 -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8001/api/v2/chat -H 'Content-Type: application/json' -d '{"message":"x"}'` → **401** (503 = auth env missing → STOP, fix env).
**TIMEOUT case (neither 200 nor 503 — curl exits 28/7):** network/bridge/publish issue, NOT an
app issue — this host's firewall is known to drop host→container traffic on freshly created
bridges (2026-06-10 staging finding). backend-v2 must be on the EXISTING `sealai_default`
network (verify: `docker inspect backend-v2 --format '{{range $n,$c := .NetworkSettings.Networks}}{{$n}} {{end}}'`
→ `sealai_default`; the compose config pins it). **STOP + diagnose — do NOT proceed to step 4**;
nothing is routed yet. Any rollback must be performed by the same sanctioned,
GATE-10-bound release transaction using its attested rollback artifact; a
direct container stop is not an authorized substitute.

**Step 3 — Keycloak client probe (read-only).**
```bash
curl -s -o /tmp/kc.html -w '%{http_code}\n' "https://sealingai.com/realms/sealAI/protocol/openid-connect/auth?client_id=sealai-v2&response_type=code&scope=openid&redirect_uri=https%3A%2F%2Fsealingai.com%2Fdashboard%2Fcallback&state=p&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256"
grep -ci invalid /tmp/kc.html   # expect 200 + 0
```
On failure: STOP before step 4 (nothing to roll back).

**Step 4 — THE FLIP.**
```bash
./ops/v2-flip.sh --apply
```
Verify: `/dashboard` → 308; `/dashboard/` → 200 + CSP header; `/api/v2/health` → 200;
`/api/v2/framing` → 200; V1: `/` + `/api/health` → 200.
**Rollback (one step, dry-run-proven, valid at ANY later moment): `./ops/v2-flip.sh --revert`.**

**Step 5 — final smoke + watch.**
```bash
BASE_URL=https://sealingai.com ./ops/smoke-v2.sh            # + TOKEN=<browser bearer> for the authed leg
./ops/smoke-live-pilot-readiness.sh
```
One real browser login e2e. Watch 30–60 min: `docker logs -f backend-v2`,
`docker logs nginx --since 10m | grep -E 'api/v2|dashboard'`.
Rollback: step-4 revert; backend artifact rollback remains part of the same
sanctioned GATE-10 release transaction (SPA fails closed, V1 untouched).

**Step 6 — drift-proofing + governance log.**
- Commit the one-line include on the clean tree; PR `feat/v2` → `demo/rwdr-limited-external`;
  owner carry-over PR demo → main. Until both merges land, `ops/guard-nginx-reload.sh` (wired
  into both release scripts) blocks a reload that would drop live V2 routing.
- `docs/ops/GOVERNANCE_LOG.md` entry (no exceptions): backend-v2 image id, dist sha256 manifest +
  build SHA, rollback anchors (from the daemon), gate results, smoke outcomes.

**Explicitly accepted at flip time:** V1 dashboard UI paths (`/dashboard/seo`, `/dashboard/analytics`,
`/dashboard/[caseId]`) are dead (full takeover); in-flight V1 sessions keep cookies + all
`/api/*`/`/api/bff/*` — they lose only the V1 dashboard UI at next navigation; backend-v2 memory is
in-process (restart wipes conversations — pilot prerequisite below).

## Pre-flip gate (Phase 3 BLOCKED until all green)

> **FLIP HELD (owner decision 2026-06-11, FIX-FIRST).** Branch (b) confirmed from the captured
> staging session history: on the input-statement (lag) turn the kern was fail-closed by
> construction, L1 self-computed v = 16,76 m/s and labeled it "deterministisch berechnet /
> vom Rechenkern" (false provenance), and the leak detector missed the symbol-form assertion
> ("v = 16,76 m/s" with the trigger word sentences back). **Blocker C** = leak-detector
> hardening (symbol+unit self-trigger with negative-context guard, window-2 own-token gate,
> zero-new-FP sweep) **+ B** = L1-prompt same-message-inputs rule + kern-provenance label ban
> (branch `feat/v2-fixfirst-c-leak`). The flip stays HELD until C lands (owner-adjudicated
> Eval-REPLAY) and this gate re-validates on the new flip ref. Turns after the lag turn were
> legitimate kern fires.

- [x] **C landed (flip blocker):** leak-detector hardening + B prompt rule merged to the flip
      path after the owner-adjudicated `fixfirst-c-leak` Eval-REPLAY; gate re-validated on the
      new flip ref (CI all-four, staging rebuild + behavior re-smoke incl. the two-turn 40/8000
      repro: lag turn shows no fabricated kern label, following turn kern fires).
      ✅ **RE-VALIDATED 2026-06-11 on flip ref `6322eb9c`** (runtime byte-identical to the
      REPLAY-validated `3c598542`: `3c598542..6322eb9c` is docs + test-file-formatting only —
      zero runtime files; in-image `leak_detector.py`/`system_l1.jinja` hash-match the worktree).
      CI **5/5** green; flip-mechanism diff **empty** (the 2026-06-10 3-leg rollback dry-run
      carries); dist manifest **unchanged** (`index.html ec3d3a85…`, `index-D9NA13qp.js c532057c…`,
      `index--S9mhwd9.css 4040237c…`); live `:8443` smoke **10/10**; live 40/8000 repro **lag-turn
      live-green** (the live (b) lag shape — no fabricated kern label, fail-closed honest, zero
      parametric leaks). Turn-3 kern non-fire = **item-8 distiller unit-drop** (pilot-tier,
      owner-adjudicated **NON-gating**). Anchors re-read from the daemon: **V1_ANCHOR=`ab586f30`**
      (= `main`; 0 v2-mount markers in its `deploy.yml`). **Flip stays HELD** (Phase 3 owner-executed).
- [ ] Phase 1 validation green (V2 suite incl. red-before-green kid tests, keystone, npm verify, image build).
- [ ] Staging e2e checklist green (dated report) + all 3 rollback dry-run legs done.
- [ ] Keycloak `sealai-v2` client live (mappers + prod redirect URIs); step-3 probe green.
- [ ] Legal: owner-only users today → lawyer review gates the FIRST PILOT, not this flip (recorded).
- [ ] dist built at flip ref + sha256 recorded; worktree clean; anchors read from the daemon.
- [ ] Low-traffic window scheduled; GOVERNANCE_LOG entry drafted.

## Pilot-prerequisite tracker (gates the FIRST PILOT, not the flip)

1. Lawyer-reviewed CLAIM_BOUNDARY + Haftungsausschluss merged into `backend/sealai_v2/core/framing.py`.
2. Persistent memory adapters (M5-deferred) — a backend-v2 restart must not wipe conversations.
3. SPA silent token renewal (`prompt=none` path exists in `auth/oidc.ts::authorizeUrl`, nothing
   calls it); interim: 15–30 min access-token lifespan on the `sealai-v2` client.
4. Remove the `:8443` staging redirect URIs + Web Origins from the `sealai-v2` client.
5. **Devtools runtime checks (HARD gate, owner decision 2026-06-10):** in a real browser session
   against the live `/dashboard` — NO token in localStorage/sessionStorage (in-memory only) and
   ZERO CSP violations in the console. Rationale: the XSS-token-theft threat model is multi-user;
   the CSP *header* is already machine-verified in `ops/smoke-v2.sh`, but the runtime proof must
   land before real users do.
6. **Single-turn calc binding (owner decision 2026-06-11, FLIP-FIRST):** the kern value must
   appear on the SAME turn the inputs are stated — currently one-turn-lag: facts bind only after
   M5 post-answer distillation, so the kern fires from remembered facts one turn later (value
   correct, one turn late — UX, owner-only-acceptable; same classification as item 5). Proper
   fix = its own milestone with a design pass (safe same-turn deterministic extraction vs the
   owner-gated M5 distill-after-answer decision) + Eval-REPLAY. Gates the FIRST PILOT, not the
   owner-only flip. *Update 2026-06-11 (branch (b)): the false-provenance leak ON the lag turn
   (L1 self-computing + claiming the kern label) was confirmed live and is fixed flip-blocking
   (blocker C + B, see Pre-flip gate). The lag itself — kern value one turn late — remains this
   pilot-tracked item; the FIX-FIRST decision supersedes FLIP-FIRST for the leak only, not for
   the lag.*
7. **Per-turn provenance record (owner-filed 2026-06-11, the branch-(b) HALT instrument gap):**
   the live chat path persists no per-turn provenance — `chat_response` drops
   `computed_values`/`not_computed`/`verifier`, and the V2 runtime has no logging outside
   `eval/`, so "did the kern emit / what were the input_origins / did the verifier act?" was
   unanswerable server-side during the HALT. Minimal scope (route-layer only, zero core change):
   one structured stdout JSON line per `pipeline.run` from `routes/chat.py` + `routes/briefing.py`
   carrying surface, tenant/session ids, kern_fired, computed `{calc_id, value, unit, stage,
   input_origins}`, `not_computed` reasons, binding notes, verifier action + finding kinds +
   `regenerated`, answer length+hash — NO question/answer text, no finding excerpts, no secrets
   (V1 lesson: explicitly handler-configured stdout, `routing_debug` went dark in prod). Tests:
   three result shapes + a privacy guard asserting no user text in the record. Gates the FIRST
   PILOT, not the flip; do not implement before its own owner gate.
8. **Distiller unit-fidelity (owner-filed 2026-06-11, `fixfirst-c-leak` REPLAY finding):** the
   distiller sometimes stores a numeric WITHOUT the unit the user provided ("8000" from a terse
   "8000" reply in a U/min context — and the live session shows the same phrasing CAN normalize
   to a unit-bearing wert, i.e. it is LLM-variant). The declared binding grammar then correctly
   fail-closes (number + unit required) and the answer re-asks for a unit effectively already
   given — honest but redundant UX, and the kern misses a turn it could have served.
   Binding/distiller robustness work (e.g. distill-prompt unit-carry rule, or a deterministic
   unit-adoption rule for the declared felder — design pass needed, fail-closed semantics must
   not weaken). **Pilot-tier, distinct from item 6** (item 6 = same-turn binding lag; this item =
   unit fidelity of what gets distilled at all). Do not implement before its own owner gate.

## Phase 4 — V1 dashboard decommission (separate, owner-gated)

After the proving period: remove dead V1 dashboard routes/components, evaluate V1 service
teardown. Own plan, own verification, own GOVERNANCE_LOG entry. Until then V1 runs dormant as
the rollback target — do NOT stop/tear down V1 during or right after the flip.

## Appendix — GOVERNANCE_LOG draft (complete at flip time, then append to docs/ops/GOVERNANCE_LOG.md)

> Fill every `⟨…⟩` AT FLIP TIME — anchors come from the daemon and `git rev-parse HEAD` in the
> moment, never from memory or this prep (ops rule).

```markdown
### ⟨YYYY-MM-DDTHH:MMZ⟩ — V2 cutover flip: /dashboard + /api/v2 live (owner-executed)

- **Change:** nginx include `snippets/v2_dashboard.conf` enabled via `ops/v2-flip.sh --apply`
  (one line after default.conf `server_name sealingai.com;`); backend-v2 up (profile `v2`);
  V1 untouched and running (rollback target). Runbook: docs/ops/RUNBOOK_V2_CUTOVER.md.
- **Flip ref:** ⟨git rev-parse HEAD⟩ (worktree clean: ⟨yes⟩)
  — gate-locked runtime ref `6322eb9c` (re-validated 2026-06-11; runtime byte-identical to the
  REPLAY-validated `3c598542`; later docs-only commits may ride on top without re-validation).
- **backend-v2 image:** ⟨docker inspect backend-v2 --format '{{.Image}}'⟩
- **immutable dashboard artifact:** ⟨content-addressed artifact ID and complete SHA-256 manifest
  from the exact GATE-10 approval⟩. Candidate bytes under `.build/dashboard-candidate` are not
  production evidence until P1 packages, attests, and independently reproduces them.
- **Rollback anchors (from the daemon at flip time):**
  - routing: `ops/v2-flip.sh --revert` (dry-run-proven on staging 2026-06-10)
  - V1 backend: ⟨docker inspect backend --format '{{.Config.Image}}'⟩ (status/health: ⟨…⟩)
  - V1 frontend: ⟨docker inspect sealai-frontend-1 --format '{{.Config.Image}}'⟩
  - keycloak: ⟨docker inspect keycloak --format '{{.Config.Image}}'⟩
  - V1_ANCHOR (git, roll-TO — the V1-serving ref from the daemon image tag, NOT the flip ref;
    no-V2-mounts deploy.yml verified per step 0): ⟨…⟩
- **Pre-flip gate:** Phase 1 suites green; staging machine-side e2e + 3-leg rollback dry-run
  green (2026-06-10); owner browser leg green (⟨date⟩); CI all-four green @ ⟨flip ref⟩;
  Keycloak sealai-v2 client verified (b7a2dd0a-…); legal gate = first pilot (owner-only users).
- **Flip smoke:** `BASE_URL=https://sealingai.com ops/smoke-v2.sh` → ⟨result⟩; authed leg →
  ⟨result⟩; `ops/smoke-live-pilot-readiness.sh` → ⟨result⟩; browser login e2e → ⟨result⟩.
- **Post-flip watch:** ⟨30–60 min, findings⟩
- **Follow-ups:** flip commit → PR feat/v2→demo → owner carry-over demo→main (reload guard
  covers the window); staging teardown + remove :8443 Keycloak entries; pilot tracker items 1–7.
```
