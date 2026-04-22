# SeaLAI Architecture Cleanup Plan

This plan is intentionally incremental. The goal is to reduce bug surface without breaking the running PTFE-RWDR V3 stack.

## Phase 0 - Guardrails First (implemented in this cut)

- Add `docs/architecture/SSOT_REGISTRY.md` as the binding patch map.
- Add `docs/architecture/DEPRECATED_MAP.md` for compatibility and historical areas.
- Add architecture guardrail tests under `backend/tests/architecture/`.
- Keep historical folders untouched, but documented as non-canonical.
- Correct the frontend fallback routing order so PTFE-RWDR markers beat generic hydraulic wording when no backend cockpit is available.

## Phase 1 - Projection Decomposition

Target file: `backend/app/api/v1/projections/case_workspace.py`.

Current risk: this file owns too many responsibilities and is the highest-risk patch target.

Proposed extraction order:

1. `backend/app/api/v1/projections/workspace_routing.py`
   - `_derive_request_type`
   - `_derive_engineering_path`
   - path coercion helpers

2. `backend/app/api/v1/projections/ptfe_rwdr_enrichment.py`
   - PTFE family inference
   - PTFE-RWDR service adapter
   - deterministic derivation/advisory/matching enrichment

3. `backend/app/api/v1/projections/cockpit_projection.py`
   - cockpit sections
   - cockpit checks
   - parameter snapshot rendering

4. `backend/app/api/v1/projections/workspace_synthesis.py`
   - governed-state to four-pillar compatibility shape
   - SSoT-state to four-pillar compatibility shape

5. Keep `case_workspace.py` as a thin public facade until all imports are migrated.

Exit criteria:

- Existing response schema unchanged.
- `backend/tests/test_ptfe_rwdr_workspace_enrichment.py` remains green.
- `backend/app/agent/tests/test_case_workspace_projection.py` is either included in normal CI or mirrored under `backend/tests`.

## Phase 2 - Test Surface Cleanup

Current risk: `backend/pytest.ini` only discovers `backend/tests`, while active agent tests live under `backend/app/agent/tests`.

Steps:

1. Run collection for `backend/app/agent/tests` and classify failures:
   - productive current tests
   - compatibility tests
   - stale tests
2. Move productive tests to `backend/tests/agent/` or add a second test path after fixing collection/runtime issues.
3. Move stale tests to a clearly named legacy test folder or delete them in a dedicated commit.
4. Keep architecture guardrails in default test path permanently.

## Phase 3 - Legacy Contract Migration

Current risk: `backend/tests/contract/*` still imports `app.langgraph_v2`, which no longer exists in `backend/app`.

Steps:

1. For every `app.langgraph_v2` import, decide:
   - migrate to `app.agent.*`
   - replace with projection/service contract test
   - delete as obsolete
2. Add a guard that fails if new tests import `app.langgraph_v2` outside a clearly marked legacy quarantine.
3. Remove or rename misleading `langgraph` wording in productive health/docs where it no longer describes runtime truth.

## Phase 4 - Frontend Authority Tightening

Current risk: frontend fallback functions can accidentally look like business logic.

Steps:

1. Prefer backend `workspace.cockpit` and `workspace.engineeringPath` everywhere.
2. Keep fallback reconstruction only for transient stream states and label it as fallback.
3. Add tests for PTFE-RWDR precedence over generic hydraulic wording.
4. Remove fallback path inference once streaming always carries backend workspace truth.

## Phase 5 - Repository Quarantine

Current risk: old folders are easy to patch accidentally.

Steps:

1. Keep `archive`, `_trash`, `_local_keep`, `backups`, and `langgraph_backup` out of product imports and tests.
2. Move bulky historical assets out of the product repo if deployment size or search noise becomes a problem.
3. Add CODEOWNERS or path comments for high-risk modules.

## Definition of Done

- One documented SSoT map exists and is enforced by tests.
- Productive imports cannot point to removed LangGraph v2 code.
- `/api/agent` remains the single runtime mount.
- Compatibility routes are read-only unless explicitly listed otherwise.
- PTFE-RWDR routing cannot be overridden by generic hydraulic wording.
- Large projection file is split into smaller modules with stable public facade.
