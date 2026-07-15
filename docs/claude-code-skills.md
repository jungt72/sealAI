# Claude Code skills for sealingAI

This repo drives Claude Code with four cooperating primitives under `.claude/`.
They are deliberately **trennscharf** — each has one job. This doc explains the
boundaries, lists the skills, and shows how to add one.

## The four primitives (who does what)

| Primitive | Location | Invoked by | Loaded | Job |
|---|---|---|---|---|
| **Rules** | `.claude/rules/*.md` | — | **always** (via `CLAUDE.md`) | Short, always-on invariants — the "never cross" lines and the source-of-truth pointers. |
| **Commands** | `.claude/commands/*.md` | the user types `/audit`, `/patch`, `/test` | on invoke | Quick, user-triggered entry points with `$ARGUMENTS`. |
| **Agents** | `.claude/agents/*.md` | delegated | separate context | Isolated, adversarial reviewers. `v2-doctrine-reviewer` covers V2 trust-spine / `core/output_guard.py` / mutation changes (use it before merging such a PR). `doctrine-reviewer` is the **retired-scope V1** reviewer (probes the gone `backend/app` guards) — historical, kept only for old-commit context. |
| **Skills** | `.claude/skills/*/SKILL.md` | **the model, automatically** | **on demand** when the description matches | Deep, repo-specific, end-to-end **procedures** for the error-prone workflows — pulled into context only when relevant. |

The distinction that keeps them separate:

- A **rule** is a line you must never cross, loaded on every task. It is terse.
- A **command** is something the *human* fires to start a task.
- An **agent** runs in its own context to review, adversarially, without being
  swayed by the working context.
- A **skill** is a procedure the *model* pulls in by itself when the task matches
  — it holds the detailed, incident-hardened "how to actually do X here" that is
  too long to keep always-on and is only needed some of the time.

A skill must **not** restate a rule. It points at the rule and adds the executable
procedure, the concrete commands/paths, and the failure modes to avoid.

## The skills

Each earns its place by mapping to a real, recurring, error-prone workflow (most
are hardened against a specific past incident):

1. **`eval-replay-adjudication`** — run the live Eval-REPLAY and fold the owner's
   ticked adjudication worksheet. Human-is-oracle (never self-tick),
   targeted-not-full, secret hygiene for the transient key, model-cost guardrails.
2. **`backend-v2-deploy`** — deploy backend-v2 to prod only via
   `ops/release-backend-v2.sh`. The compose-passthrough allow-list invariant (the
   #1 recurring incident class), rollback anchors, flag discipline, post-incident
   HALT.
3. **`trust-layer-change`** — safely change the four-layer trust spine (L1
   generator, L3 verifier, response contract, trap catalog, Jinja2 prompts).
   Never weaken a guard; avoid the confident_wrong / destructive-hedge failure
   (recurred twice).
4. **`knowledge-fachkarten`** — grow/curate the reviewed-knowledge SSoT:
   Fachkarten seed-JSON, claim `kind` taxonomy, reviewed-vs-drafts provenance,
   the ingest CLI, the matrix.
5. **`retrieval-rag`** — operate the existing Qdrant hybrid retrieval stack
   (OpenAI-API embeddings only — never a local embedder; score-scale caution).
   Re-architecture is intentionally out of scope.
6. **`security-tenant`** — the P0 boundary: server-side tenant filters, the
   untrusted-content pipeline, no secrets in logs.
7. **`frontend-v2-dashboard`** — the product dashboard (Vite/React SPA under
   `/dashboard`). The footgun: `npm run build` in the VPS checkout IS a deploy
   (live `dist/` bind-mount); the no-V1-imports boundary; projection-of-backend-
   truth; the OIDC `?case=` / case-switch-race incidents.
8. **`frontend-marketing`** — the Next.js marketing site (`frontend/`, NOT the
   product UI). `frontend/DESIGN.md` is the design SoT; NextAuth/BFF is distinct
   from V2 OIDC. Its historical `ops/release-frontend.sh` publisher is currently
   `BLOCKED_EXTERNAL`.

### Coverage map (why these eight)

They cover the repo's full change surface — **backend and website**: **eval** (1),
**deploy** (2), **core pipeline / trust** (3), **knowledge growth** (4),
**retrieval** (5), **security** (6), **product dashboard** (7), **marketing site**
(8). Deliberately *not* separate skills: the general audit-first / smallest-patch
discipline (that is `rules/workflow.md` + the `/audit` command, always-on) and the
4-layer memory internals (mostly inert; covered under trust + security).

## How a skill gets loaded

Claude Code reads every `SKILL.md` frontmatter `description` at session start and
auto-loads the **body** when a task matches. So the `description` is the trigger:
write it in the third person, name the files/paths that signal relevance, and list
the "use when…" conditions. The body stays out of context until then — keep the
detail there, keep the description sharp.

## Adding or changing a skill

1. Create `.claude/skills/<kebab-name>/SKILL.md` with frontmatter:
   ```yaml
   ---
   name: <kebab-name>
   description: >-
     What it does + explicit "use when…" triggers, naming the files/paths that
     signal relevance. This is the auto-load trigger — make it specific.
   ---
   ```
2. In the body: point at the governing rule/`AGENTS.md` section (don't restate
   it), then the procedure, the concrete commands/paths, and the failure modes.
3. Keep it **trennscharf**: if it duplicates a rule or another skill, fold instead
   of adding. Prefer few sharp skills over many overlapping ones.
4. Ground it in reality — cite the real entry points from
   `AGENTS.md § Canonical Backend Entry Points`. A skill that names a file must
   name one that exists.
5. List it in `CLAUDE.md § Skills` and in this doc's skill list.

## Relationship to `AGENTS.md`

`AGENTS.md` is the contract and product-scope source of truth; the Leitbild V3
lives there. Skills are the *operational how-to* layer on top — they must never
contradict `AGENTS.md`, and when the contract changes, the affected skills are
updated in the same spirit as the code.
