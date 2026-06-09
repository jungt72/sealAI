# Workflow

How changes move from audit to merge. Derived from the standing governance in
`docs/runtime-audit-fixmap.md`.

## Per-fix protocol
1. **Tight plan** — root `file:line`, affected ACs, blast radius. No scope creep
   beyond the named change.
2. **Verify the repro, don't trust the audit.** Define the concrete user-side
   reproduction and confirm it actually fails *before* fixing. Lesson: an audit
   sibling is not the reported bug (e.g. Group B did not reproduce post-D — it was
   closed by the routing fix, not by the audited resume-seam).
3. **Red-before-green** — reproduce the symptom as a failing test first, then fix.
4. **Zero-FP proof** if a guard / lexicon / doctrine path is touched (see
   `doctrine.md`).
5. **Atomic, conventional commits**, honest messages. Report the exact validation
   commands and results; never hide a failing test.

## Branch & merge
- Work on a feature branch. **PRs target `demo/rwdr-limited-external` — never
  `main`.** Direct pushes to `main` are denied (see permissions).
- CI `agent-bff-guardrails` must be green before merge.
- `gh pr merge --merge --delete-branch` → `git switch demo/rwdr-limited-external`
  → `git pull`.
- **No merge without a `doctrine-reviewer` approval** when the change touches the
  output doctrine, guards, streaming, or mutation paths. The reviewer is read-only
  and adversarial (see `.claude/agents/doctrine-reviewer.md`).

## Blast-radius gating (when to HALT to the human)
- Changes to **live enforcement / streaming / mutation / `runtime_contract`** may
  go autonomously **to demo**, then **HALT before prod** with a risk summary
  (what changed `file:line`, AC8 no-over-block proof, how the streaming flash is
  handled, proof L1 is unchanged, verified rollback anchor, test coverage).
- Also HALT for: a doctrine/security design decision; a test that would only pass
  by weakening a guard (never weaken); a real FP / regression / ambiguity that
  can't be cleanly resolved; live behaviour contradicting tests; a finding
  **outside** the current scope (log + surface, do not silently action).
- Low-blast-radius fixes (composition, routing collapse, docs) may run autonomously
  including deploy, still behind the deploy gate.

## V2 build rhythm (`backend/sealai_v2/`, `feat/v2*`)

> Applies to the green-field V2 tree only — not cut over to demo/main. The V1
> per-fix protocol + branch/merge + blast-radius rules above are unchanged. Full
> V2 doctrine: `AGENTS.md § "V2.0 green-field track"`.

- **Gate rhythm:** plan → **owner gate** → build → review; **never auto past a gate.**
  HALT after **every milestone (M1…M6)** with an **Eval-REPLAY** + owner gate
  (build-spec §10/§12). The milestone is reached only when the relevant eval cases
  pass and the **Schranken-Quote is 100 %**.
- **Build against the eval, not gut feeling.** Red-before-green here = a failing eval
  case / unit test first, then the change.
- **The human is the factual-correctness oracle.** Surface eval divergences as
  owner-final candidates; **never self-tick verdicts or free-correct facts** (the
  TRAP-02 discipline; `eval/adjudicate.py`).
- **Branch:** work on the `feat/v2*` line; V2 does **not** target
  `demo/rwdr-limited-external`/`main` until an explicit, owner-gated cutover.
- **Reviewer scope:** the read-only `doctrine-reviewer` is **V1-scoped** (L1/L2
  `output_guard`/`final_guard`) — it does not apply to V2, which has no such guards.
  V2 doctrine review = the eval hard-gate + L3 integrity (reviewed-only correction)
  + owner. See `.claude/rules/doctrine.md § "V2 doctrine mechanism"`.
