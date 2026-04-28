@AGENTS.md

# CLAUDE.md

## Purpose

This file contains Claude Code-specific operating rules for the SeaLAI repository.

Project-wide authority remains:

1. `konzept/konzept_sealing.md`
2. `frontend/DESIGN.md`
3. `AGENTS.md`
4. this `CLAUDE.md`

`AGENTS.md` is the main coding-agent contract. Do not duplicate the full product concept here.

---

## Startup rule

At the start of any non-trivial task:

1. Read `AGENTS.md`.
2. Read `konzept/konzept_sealing.md`.
3. Read relevant implementation files and tests.
4. For UI/frontend work, also read `frontend/DESIGN.md`.
5. Check repository state:

```bash
cd /home/thorsten/sealai && git status --short
```

If the worktree is dirty, stop and report the open changes unless the task explicitly concerns those changes.

---

## Operating mode

Default mode:

- Audit first.
- Patch second.
- Keep patches small.
- Preserve existing seams unless there is clear evidence they are wrong.
- Do not invent parallel architecture.
- Do not implement later-phase features unless explicitly tasked.

Phase-1 work should stay focused on chat intake, pre-gate routing, governed case-state, field envelopes, provenance, unit normalization, conflict/stale handling, lightweight calculations, readiness, Decision Understanding, cockpit projection, RFQ preview/export, RFQ freeze/consent, and upload evidence candidates.

Do not treat matching, Seal Passport, reorder, FEM, payment, ERP/CRM integration, or manufacturer dashboards as Phase-1 MVP unless explicitly instructed.

---

## Claude Code behavior

When working in this repo:

- Prefer read-only investigation before changing files.
- Cite concrete files, functions, and line ranges in audit output.
- Make the smallest useful patch.
- Do not rewrite broad areas without a scoped task.
- Do not create new workflows when existing seams can be tightened.
- Keep frontend as a projection of backend truth.
- Do not let frontend compute authoritative engineering truth.
- Respect Keycloak user/tenant scoping.
- Do not expose or invent secrets.
- Report validation commands and results.

---

## Safety language

SeaLAI must not claim final engineering approval, manufacturer release, guaranteed suitability, compliance approval without evidence, validated operation before post-RFQ feedback exists, or current reorder price without manufacturer confirmation.

Use cautious technical language. Make uncertainty, provenance, missing data, and manufacturer-review needs visible.

---

## Validation

For code changes, prefer focused tests first.

Useful command pattern:

```bash
cd /home/thorsten/sealai && pytest <relevant-test-file-or-directory> -q
```

For frontend changes, use the repo's existing build/test commands from the repository root.

Never hide failing tests. Report failures with the exact command and failure summary.

---

## Final rule

When in doubt, follow `AGENTS.md`.
