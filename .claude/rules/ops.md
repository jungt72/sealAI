# Ops

Production is gated. These rules are enforced by Claude Code PreToolUse hooks
(`ops/hooks/*.sh`) and permissions (`.claude/settings.json`); they are also the
contract for humans. The single production backend is `backend/sealai_v2/`
(`backend-v2`); the former `backend/app/` V1 runtime was retired 2026-06-28. Full
contract: `AGENTS.md`.

> **Current release status: `BLOCKED_EXTERNAL`.** Repository hooks are local
> defense in depth, not proof of GitHub ruleset or independent approval. Current
> workflows retain unprivileged OCI evidence only and do not publish; production
> deploy and marketing publication are disabled. The procedural sections below
> are future operator contracts, not current authorization.

## Branch model — `main` is the single line

`main` is the single active line for `sealai_v2` / `frontend-v2` work. The target
check set is `.github/required-security-checks.json`; external GitHub ruleset,
code-owner-review, strict-check, and admin-bypass enforcement remain
`BLOCKED_EXTERNAL` until independently verified. Work on a short-lived branch →
PR → merge once green → delete the branch. One active branch per workstream.

## Backend-v2 production deploy — future operator path, currently blocked

A backend-v2 deploy runs **only** through this wrapper. It binds the deploy to the
exact served tree and fails closed. Never `docker compose … up backend-v2` by hand
(the hooks + the image TEETH block it — see below). The chain:

1. **`TREE_HASH = ops/tree-hash.sh`** — the served-runtime content hash (single
   source of truth for "what is being shipped").
2. **Served L1** — resolved from `.env.prod` (`SEALAI_V2_L1_PROVIDER`/`_L1_MODEL`,
   defaults `openai/gpt-5.1`) so an `.env`-only model swap can't ship on a stale
   eval.
3. **Eval gate** — `ops/v2_deploy_gate.py <runs_dir> <tree_hash> <served_l1>`
   requires an **adjudicated** eval-REPLAY for that exact tree **and** L1 with
   **every GATED axis** at `schranken_quota_final == 1.0`; else exit 2 (refuse).
   > **Currently `###EVAL-GATE-DISABLED-TEMP###`** (owner-authorized 2026-06-30 —
   > per-iteration REPLAY is too costly). A no-eval fallback ships instead. **To
   > restore:** delete the fallback block and uncomment the
   > `###EVAL-GATE-ORIGINAL-BEGIN###`…`###EVAL-GATE-ORIGINAL-END###` block. Disabled
   > ≠ skip — run a **targeted** REPLAY on the touched dimension yourself (see the
   > `eval-replay-adjudication` skill).
4. **Rollback rung** — tag the **running** image read from the daemon
   (`docker inspect backend-v2 --format '{{.Image}}'`, **never memory**) as
   `sealai-backend-v2:rollback-pre-<label>-<ts>` before the flip.
5. **Build + recreate only backend-v2** — `build --build-arg GATE_TREE_HASH=…`
   then `up -d --no-deps --force-recreate backend-v2`.
6. **Smoke (RED anywhere → HALT, no ledger line, prints the rollback path):**
   health (internal `:8001/health` + public `https://sealingai.com/api/v2/health`),
   kern one-shot (`umfangsgeschwindigkeit`=16.755 / `pv_wert`=50.0),
   restart-survival.
7. **Ledger + log** — append `ops/deploy-ledger.jsonl` (machine-readable
   commit→deploy index) and print a `GOVERNANCE_LOG` paste-block (prose stays
   owner-authored).

**Authoritative gate logic** = `ops/v2_deploy_gate.py` (pure stdlib, JSON-only,
network-free, unit-tested offline). The `GATED` set = the four deterministic
Schranken (`memory`, `exfiltration`, `parametric_{multiturn,singleturn}`) **plus**
every column with `n_gate_cases > 0`, each fully adjudicated at
`schranken_quota_final == 1.0`.

**TEETH against a raw deploy:** the build bakes `GATE_TREE_HASH` and
`backend/docker-entrypoint-v2.sh` refuses to start a raw build (empty hash) run
outside the wrapper; the `v2-deploy-deny` hook blocks the raw compose shapes
in-CC. Do not try to route around them.

## Dashboard deploy (`frontend-v2`) — a different mechanism

The dashboard has **no release script**: `frontend-v2/dist` is a live read-only
bind-mount into nginx (`docker-compose.deploy.yml:93`), so `npm run build` on the
VPS checkout **is** the deploy. Be explicit that you're deploying. Details +
footguns: the `frontend-v2-dashboard` skill.

## Marketing deploy (`frontend`) — `ops/release-frontend.sh`

Marketing ships only via this script: a Next.js standalone build → recreate the
`frontend` container → health check (`:3000/api/health`) → **nginx reload guarded
by `ops/guard-nginx-reload.sh`** (refuses a reload that would silently drop live
V2 routing — the cutover-drift guard) → live pilot smoke
(`ops/smoke-live-pilot-readiness.sh`). Rollback via the `.env.prod.rollback-<ts>`
file it writes. Details: the `frontend-marketing` skill.

## nginx / cutover — owner-gated per action

Shared-edge nginx changes and the `/dashboard` + `/api/v2` cutover
(`ops/v2-flip.sh`, `nginx/snippets/v2_dashboard.conf`) are **owner-gated per
action** — a rate-limit rollout once broke Keycloak login for real. A confirmation
must NAME the action, not just affirm. Never flip the edge yourself.

## GOVERNANCE_LOG — every prod deploy logged

**Every prod deploy is logged in `docs/ops/GOVERNANCE_LOG.md` — no exceptions**
(backend, frontend, doctrine or brand; owner rule). One entry per deploy: the new
pinned `@sha256`/image, the rollback target (read from the running daemon, never
memory), the gate result, and the live-smoke outcome. The machine-readable index
is `ops/deploy-ledger.jsonl`.

## Claude Code enforcement hooks (PreToolUse, matcher `Bash`, fail-closed)

- **`doctrine-gate.sh`** — blocks `git commit` / `git push` unless the **V2
  doctrine guard suite** passes (`pytest backend/sealai_v2 --noconftest -q`; the
  suite was re-pointed to the V2 tree 2026-06-25 — it no longer runs the retired
  V1 tests). Emergency override `SEALAI_DOCTRINE_GATE_BYPASS=1` — allowed but
  **logged**, never silent; use only when the gate itself is broken.
- **`v2-deploy-deny.sh`** — blocks a **raw** backend-v2 compose deploy (every
  bypass shape: named service, `--profile v2`, `--profile=v2`, `COMPOSE_PROFILES`,
  profile-wide), anchored to a genuine invocation so a trailing-comment can't
  smuggle past. In-CC counterpart to the image TEETH.
- **`relay-deny.sh`** — blocks `git merge`, `git push`, `v2-flip`,
  `release-backend*`, and `docker compose up` in-CC: **merges to `main` and prod
  deploys are owner-triggered only.** An agent must not self-merge or self-deploy
  from inside Claude Code — surface the ready action and let the owner trigger it.
- **`deploy-gate.sh`** — gates `ops/release-backend.sh` (the **retired V1** deploy
  script) via two fresh (<1h) sentinels (`pytest-green`, `anchor-verified`).
  **Legacy / effectively inert** for current work: `release-backend.sh` is the V1
  path and is not used to deploy `backend-v2`. Kept until the V1 script is removed.

**Parsing is fail-closed:** jq missing, malformed payload, or an undeterminable
`.tool_input.command` → BLOCK. Matching is on the executed command only and only at
a command position — a commit message or prose that merely *mentions* a gated path
does not trigger. **Residual gaps** (`sh -c "…"`, aliases/functions, variable
expansion, a path chained mid-line inside a quoted string) are a **discipline
anchor, not a sandbox** — accepted by design. Hooks **hot-reload in-session** (no
restart needed; verified 2026-06-04).

## Secrets & untouchables

- `.env*` files are never read, printed, or committed (denied in permissions).
- **V2 eval key hygiene:** offline tests use a **fake LLM client (no key)**. A live
  eval REPLAY sources `OPENAI_API_KEY` **transiently from `~/sealai/.env` for that
  run only** — never persisted into the agent env, never echoed to logs, never
  committed.
- Never push to `main`; never `git push --force`, `git clean`, or
  `docker compose down/rm` against prod (all denied).
- `.claude/.gate-logs/` holds runtime gate logs + sentinels — gitignored, not
  committed.

## HALT-gate rhythm

Plan → owner gate → build → review; never auto past a gate. A self-caused
production incident is itself a HALT point — report and stop, do not self-commit a
fix to `main`. See `.claude/rules/workflow.md`.

## Retired (historical only)

- **Branch model `demo/rwdr-limited-external`** (all-PRs-target-demo, per-milestone
  `demo→main` carry-over) — gone; `main` is the single line.
- **V1 `ops/release-backend.sh`** + its pre-deploy pytest sentinel + the
  `docker inspect backend` (V1 service) rollback anchor — targeted the retired
  runtime. The `deploy-gate.sh` hook still guards that dead script (see above).
- **`SEALAI_TIER0_RETRIEVAL_GUARD`** kill-switch on `rag_orchestrator.hybrid_retrieve`
  — a **V1-only** guard (`rag_orchestrator` does not exist in `sealai_v2`); dead.
  V2 retrieval fail-open behavior lives in `knowledge/qdrant_retrieval.py` (see the
  `retrieval-rag` skill).
