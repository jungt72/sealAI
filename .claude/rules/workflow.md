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
