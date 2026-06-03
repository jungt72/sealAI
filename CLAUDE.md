@AGENTS.md

# CLAUDE.md

## Purpose

This file contains Claude Code-specific operating rules for the SealAI repository.

Project-wide authority, in order:

1. `AGENTS.md` — the main coding-agent contract.
2. The current product & architecture concept files named in `AGENTS.md`
   (currently `docs/implementation/SEALAI_RWDR_MVP_PRODUCT_CONCEPT.md` and the
   architecture concept it references).
3. `frontend/DESIGN.md` — for UI/frontend work.
4. this `CLAUDE.md`.

`AGENTS.md` is the source of truth for product scope. Do not duplicate the full
product concept here.

> **Precedence:** The binding target architecture is **V1.7 — Universal Sealing
> Case Platform** (`docs/sealing_intelligence_v1_7_universal_sealing_case_platform_blueprint.md`),
> layered over the **V1.6** operative contracts
> (`docs/sealing_intelligence_v1_6_mobile_first_complete_architecture_blueprint.md`).
> V1.7 wins on architecture, V1.6 wins on contracts. The runtime is still the
> governed V10 conversational runtime; product focus stays **RWDR MVP** (the
> first Domain Pack). If any wording below (e.g. legacy "Phase-1" framing)
> conflicts with `AGENTS.md`, `AGENTS.md` wins.

---

## Startup rule

At the start of any non-trivial task:

1. Read `AGENTS.md`.
2. Read the concept files `AGENTS.md` points to.
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

Current product lens (per `AGENTS.md`): **RWDR MVP / Technical RWDR RFQ Brief**.
Stay focused on chat intake, pre-gate routing, governed case-state, field
envelopes, provenance, unit normalization, conflict/stale handling, lightweight
calculations, readiness, Decision Understanding, cockpit projection, RFQ
preview/export, RFQ freeze/consent, and upload evidence candidates.

Do not treat matching, Seal Passport, reorder, FEM, payment, ERP/CRM
integration, or manufacturer dashboards as in-scope unless explicitly instructed.

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

## Repository map

- `backend/app/agent/` — agent runtime: `api/` (dispatch, routes, streaming),
  `communication/` (runtime, governed answer composer).
- `backend/app/{api,domain,llm,mcp,services,schemas,core,observability}/` —
  governed runtime, domain logic, LLM + MCP integration.
- `backend/app/tests/` and `backend/tests/` — backend tests.
- `frontend/src/{app,components,lib,hooks}/` — Next.js app (App Router).
- `keycloak/`, `nginx/`, `paperless/` — infrastructure/auth/ingest.
- `_archive/` — local backups (gitignored, do not touch).

---

## Safety language

SealAI must not claim final engineering approval, manufacturer release,
guaranteed suitability, compliance approval without evidence, validated
operation before post-RFQ feedback exists, or current reorder price without
manufacturer confirmation.

Use cautious technical language. Make uncertainty, provenance, missing data, and
manufacturer-review needs visible.

Final product principle (RWDR): SealingAI does not decide the seal — it makes the
inquiry decidable. AI extracts. User confirms. SealingAI structures. Manufacturer
or responsible engineer evaluates.

---

## Validation

Prefer focused tests first. Never hide failing tests — report the exact command
and failure summary.

Backend (pytest config lives in `backend/pytest.ini`, `testpaths = tests`):

```bash
cd /home/thorsten/sealai/backend && pytest -q                    # full suite
cd /home/thorsten/sealai/backend && pytest tests/<file>.py -q    # focused
```

Frontend (from `frontend/`):

```bash
cd /home/thorsten/sealai/frontend && npm run test:run    # vitest (CI mode)
cd /home/thorsten/sealai/frontend && npm run test:node   # node/tsx unit tests
cd /home/thorsten/sealai/frontend && npm run test:all    # node + vitest
cd /home/thorsten/sealai/frontend && npm run lint        # eslint
cd /home/thorsten/sealai/frontend && npm run build       # next build (type-check)
```

---

## V1.7 architecture discipline (Universal Core vs Domain Pack)

When implementing V1.7, keep these rules (full detail in the V1.7 blueprint
§3, §3.5, §8, §10):

- **Core vs Pack:** the Universal Sealing Core is dichtungstyp-agnostic
  (case lifecycle, field/state model, State Gate, evidence intake, RAG plumbing,
  routing/mode detection, cockpit projection, RFQ dispatch, tenant/governance).
  RWDR-specific logic (completeness rules, surface-speed calc, shaft/housing
  agents, RFQ template) belongs in a Domain Pack, never in the plumbing.
- **First audit, then name:** much of the runtime is already type-agnostic
  (`KnownField.field` is a string; modes are interaction types, not seal types).
  Identify what is already Core and what is RWDR-specific before moving code.
- **Rule of Three:** do not build a speculative universal abstraction on the
  single RWDR datapoint. Extract shared abstractions only when Domain Pack #2
  (O-Ring) is built. Clean RWDR code is not debt; a speculative layer is.
- **Tenant isolation is P0:** any cross-tenant/IDOR exposure on
  case/file/evidence/RFQ operations is a blocker, not a backlog item.
- **No parallel flows:** one governed runtime, one router, one RWDR/RFQ flow
  (see AGENTS.md Clean-Code Rules). A Domain Pack is added, the Core is not
  rebuilt.

## Final rule

When in doubt, follow `AGENTS.md`.
