# Workflow

How changes move from audit to merge in the V2 runtime (`backend/sealai_v2/`,
`frontend-v2/`). The binding rhythm is `AGENTS.md § Git / branch workflow` +
`§ Hard invariants`.

## Per-fix protocol
1. **Audit first, tight plan** — root `file:line`, affected eval dimension /
   Schranken, blast radius. No scope creep beyond the named change. Evidence =
   path + line.
2. **Verify the repro, don't trust the audit.** Define the concrete user-side
   reproduction (a real LangSmith trace where possible) and confirm it actually
   fails *before* fixing. An audit sibling is not the reported bug.
3. **Red-before-green** — reproduce the symptom as a failing test / failing eval
   case first, then fix. Build against the eval, not gut feeling.
4. **Never weaken a guard, catalog, or eval test** to get green (see
   `doctrine.md`). If green needs loosening what blocks → **HALT to human**.
5. **Atomic, honest commits.** Report the exact validation commands and results;
   never hide a failing test. Prove a flag-gated change is byte-identical when
   unset before merge.

## Branch & merge
- `main` is the **single active line** for `sealai_v2` / `frontend-v2` work. Work
  on a **short-lived branch off `main`**, open a PR, merge once green.
- The target check set is versioned in
  `.github/required-security-checks.json`, but its GitHub ruleset,
  code-owner-review, and admin-bypass enforcement is **`BLOCKED_EXTERNAL`**
  until independently verified. Local settings are defense in depth, not proof
  of server-side branch protection.
- One active branch per workstream — merged (or explicitly closed) before starting
  the next. **Delete a branch immediately once merged**
  (`git branch -d` / `git push origin --delete`); a stale merged branch causes
  "wrong branch" mistakes later.

## HALT-gate rhythm (never auto past a gate)
- **Plan → owner gate → build → review.** HALT after **every milestone (M1…M6)**
  with an **Eval-REPLAY** + owner gate (build-spec §10/§12). A milestone is reached
  only when its eval cases pass and the **Schranken-Quote is 100%**.
- Also HALT for: a doctrine/security design decision; a test that would only pass
  by weakening a guard (never weaken); a real FP / regression / ambiguity that
  can't be cleanly resolved; live behaviour contradicting tests; a finding
  **outside** the current scope (log + surface, do not silently action).
- **A self-caused production incident is itself a HALT point** — report and stop,
  do **not** self-commit a fix to `main` without checking back with the owner
  first, even when the fix is already tested and correct.
- Shared edge changes (nginx, `docker-compose.deploy.yml`, new bind mounts) need
  **explicit per-action owner go-ahead** — a confirmation must NAME the action,
  not just affirm.

## Review & the human oracle
A V2 PR that touches the trust spine (L1/L3), the live `core/output_guard.py`
guard, grounding correction, tenant security, or a mutation path must get an
**APPROVE from the read-only `.claude/agents/v2-doctrine-reviewer.md`** before
merge. Surface eval divergences as owner-final candidates; **never self-tick
verdicts or free-correct facts** (the TRAP-02 discipline; `eval/adjudicate.py`).
No production deployment is currently authorized: backend/Keycloak publication,
the deploy workflow, and the marketing publisher are `BLOCKED_EXTERNAL`.
Dashboard builds produce a candidate and are not release evidence.

## Retired (historical only)
The former V1 runtime targeted PRs at `demo/rwdr-limited-external`, gated on the
`agent-bff-guardrails` check, and used the read-only `doctrine-reviewer` agent for
V1 `output_guard`/`final_guard` changes. That runtime was **retired 2026-06-28**.
`main` is now the single line; the `doctrine-reviewer` is V1-scoped (it probes the
retired `backend/app` comparative-ranking lexicon) and does not apply to V2. V2
doctrine review = the eval hard-gate + L3 integrity (reviewed-only correction) +
the live `core/output_guard.py` contract guard + the `v2-doctrine-reviewer` agent
+ owner. See `doctrine.md`.
