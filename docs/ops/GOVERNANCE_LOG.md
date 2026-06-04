# Governance Activation Log

Append-only logbook for activation and verification of the SealAI governance
gates (doctrine-gate, deploy-gate, branch-guard, read-only reviewer). One entry
per activation/verification event. Newest on top.

---

## 2026-06-04 — Governance activated and mechanically verified

**Governance aktiv ab 2026-06-04T05:07Z** (Hooks hot-reloaded in-session),
durable auf `demo/rwdr-limited-external` via **PR #38** (merge `64f4bcc2`).
**Session:** `1b1be06d-dfd9-4cc6-895d-2ec7353181c6`.

Activation: the reviewed `.claude/settings.json.proposed` was renamed onto the
active `.claude/settings.json`, registering the `PreToolUse → Bash` hooks
(`ops/hooks/doctrine-gate.sh`, `ops/hooks/deploy-gate.sh`) and the tightened
permissions (main-push denies, release-script `ask`-gate). The previously active
settings had **no `hooks` block** — the gates were authored but not loaded. The
machinery, rules, and reviewer were untracked and are now committed
(`f25079d1`, `645e9f62`).

### Gate → Proof → Evidence

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | Hooks registered & live | **PASS** | `.claude/settings.json:94-110` hooks block (merged #38); `doctrine-gate.log` live PASS entries 05:06–05:16Z (one per real `git commit`/`git push`) |
| 2 | Doctrine-gate RED → commit BLOCKED | **BLOCK (correct)** | `05:13:46Z BLOCK — guard suite FAILED`; stderr `DOCTRINE GATE (fail-closed): fast doctrine guard suite FAILED`; synthetic `assert False` probe in `test_comparative_ranking_guard.py`; HEAD unchanged |
| 3 | Doctrine-gate GREEN → commit ALLOWED | **PASS** | `05:15:53Z PASS`; throwaway commit `2a149589` succeeded (`rc=0`) after the probe was removed |
| 4 | Branch-guard → push to `main` denied | **BLOCK (correct)** | `git push origin HEAD:main --dry-run` → `Permission to use Bash … has been denied` (settings deny, pre-execution; no real push) |
| 5 | Deploy-gate → release w/o sentinel denied | **BLOCK (correct)** | `bash ops/release-backend.sh --help` → `DEPLOY GATE (fail-closed): missing sentinel — full backend pytest exit 0`; no build started; `…/sentinels/` absent |
| 6 | Reviewer cannot Write/Edit | **PASS** | `doctrine-reviewer` subagent toolset = Read, Bash only; no `Write`/`Edit` tool to invoke |
| 7 | ops.md sentinel docs present & consistent | **PASS** | `.claude/rules/ops.md:6-19` documents `touch …/sentinels/{pytest-green,anchor-verified}` + <1h freshness, consistent with `deploy-gate.sh:24,50-51` |

Red-before-green integrity: the doctrine-gate proof reproduced a real RED (suite
failing) and a real GREEN (suite passing) on the same throwaway branch. All
synthetic artifacts (probe test, throwaway file, `proof/governance-gates` branch)
were fully removed; no sentinels were created; worktree left clean.

### Findings (surfaced, not auto-fixed — gate changes require their own plan)

- **F1 — Doctrine-gate over-matches the payload.** The hook greps the *whole*
  `PreToolUse` payload (incl. the Bash `description` field), not just
  `tool_input.command`. A benign `git restore` whose description merely contained
  the text "git commit" triggered a full suite run and was blocked
  (`05:14:24Z BLOCK`). Fix direction: parse `jq -r '.tool_input.command'` and
  match only the command.
- **F2 — Deploy-gate over-matches the payload.** It matches `ops/release-backend.sh`
  anywhere in the command string, so a `git commit` whose *message* referenced
  that path was falsely blocked. Same fix direction as F1.
- **F3 (low) — Reviewer has Bash.** The read-only guarantee is enforced for
  `Write`/`Edit` via the tool-list, but file mutation via Bash redirection is not
  tool-blocked; the read-only role for Bash is by convention (Bash is needed to
  run the guard suite).

Neither F1 nor F2 weakens a gate — both cause *over*-blocking (fail-closed in the
safe direction). They are robustness/usability findings, not security gaps.
