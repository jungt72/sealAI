# V1.8 Audit — Phase 0 Inventory (read-only)

**Date:** 2026-06-06
**Scope:** Orientation map of the sealAI monorepo + full existing-test-suite run, as the
basis for the Phase 1 deep audit against
`docs/sealing_intelligence_v1_8_universal_sealing_lifecycle_platform_blueprint.md` (V1.8).
**Method:** Read-only. A source-only mirror of the repo (backend/app, backend/tests,
backend/agents, prompts, core, contracts, frontend/src, docs — `__pycache__`/`.venv`/
`node_modules`/data excluded) was analysed locally; **all tests were executed on the VPS**
(`/home/thorsten/sealai`) where the Python venv + Postgres/Qdrant stubs live. Evidence is
cited repo-relative as `path:line`.

---

## 1. Repository shape

| Area | Path | Size / count |
|---|---|---|
| Backend app code | `backend/app/` | 593 `.py` |
| Backend tests | `backend/tests/` + `backend/app/agent/tests/` + `backend/app/api/tests/` | 333 `test_*.py` |
| Frontend | `frontend/src/` | 166 `.ts/.tsx` |
| Prompt templates (Jinja2) | `backend/app/agent/prompts`, `backend/app/prompts`, `backend/app/agent/templates`, `backend/prompts`, `backend/app/services/rag/templates` | ~101 `.j2` |
| Root deterministic core | `core/` (`parameters.py`, `engine_result.py`, `deterministic_state.py`, `enums.py`) | small |
| Blueprints | `docs/sealing_intelligence_v1_6_*.md`, `docs/architecture/BLUEPRINT_V1_7_FINAL_CLOSEOUT.md`, `docs/sealing_intelligence_v1_8_*.md` | — |

The product runtime is the **"V10 governed conversational" architecture** (per `AGENTS.md`):
a deterministic LangGraph pipeline with embedded LLM observation/composition, fronted by a
semantic pre-gate router that separates free knowledge dialogue from governed case intake.

## 2. Canonical entrypoints (verified present)

| Concern | File |
|---|---|
| Chat REST | `backend/app/agent/api/routes/chat.py` |
| Chat SSE streaming | `backend/app/agent/api/streaming.py` |
| Pre-gate dispatch / routing | `backend/app/agent/api/dispatch.py`, `backend/app/services/semantic_intent_router.py`, `backend/app/services/pre_gate_classifier.py` |
| Governed graph invocation seam | `backend/app/agent/api/governed_runtime.py` |
| LangGraph topology | `backend/app/agent/graph/topology.py` (400 lines) |
| Graph nodes | `backend/app/agent/graph/nodes/*.py` (21 nodes, 4162 lines total) |
| Cycle control | `backend/app/agent/graph/cycle_control.py` (167 lines) |
| State models | `backend/app/agent/state/models.py` (1363), `state/case_state.py` (2023) |
| State Gate (reducers / single writer) | `backend/app/agent/state/reducers.py`, `backend/app/services/case_service.py` |
| Event store | `backend/app/domain/mutation_events.py`, `backend/app/models/mutation_event_model.py`, `backend/app/models/outbox_model.py`, `backend/app/services/history/persist.py` |
| Governed-state persistence | `backend/app/agent/state/persistence.py` (826) |
| RAG / retrieval | `backend/app/services/rag/rag_orchestrator.py`, `backend/app/agent/services/real_rag.py`, `backend/app/agent/graph/nodes/evidence_node.py` |
| RFQ brief / preview | `backend/app/services/rwdr_mvp_brief.py`, `backend/app/services/rfq_preview_service.py`, `backend/app/agent/communication/rfq_one_pager.py`, `backend/app/api/v1/endpoints/rfq.py` |
| Domain Pack seam | `backend/app/domain/domain_pack.py`, `backend/app/domain/seal_packs.py` |
| No-Go linter | `backend/app/agent/templates/no_go_guard.py`, `backend/app/agent/communication/governed_answer_composer.py` |
| Observability / trace | `backend/app/agent/v92/contracts.py` (`TraceSummary`, `PromptTrace`), `backend/app/agent/runtime/turn_timing.py`, `backend/app/observability/` |
| Frontend SSE hook / BFF | `frontend/src/hooks/useAgentStream.ts`, `frontend/src/app/api/bff/agent/chat/stream/route.ts`, `frontend/src/lib/contracts/agent.ts` |

## 3. Graph topology as built (anchor for ORC)

`backend/app/agent/graph/topology.py:312-393` compiles a **single linear StateGraph** with one
bounded cycle — not the V1.8 §7.3 fan-out DAG:

```
turn_boundary → intake_observe → normalize → assert → medium_intelligence → evidence
   → compute → v92_engineering → challenge → governance ─decide_cycle()─┐
        ▲                                                                │ CONTINUE
        └────────────── cycle_increment ◄───────────────────────────────┤
                                                                          │ TERMINATE
   matching → rfq_handover → dispatch → norm → export_profile →
   manufacturer_mapping → dispatch_contract → v92_dossier →
   output_contract → governed_answer_composer → END
```

- The cycle (`governance → cycle_increment → intake_observe`) is bounded by
  `SEALAI_MAX_CYCLES` (default 3), `cycle_control.py:51,74-98`.
- Only `intake_observe_node.py:473` and the composer call an LLM inside the graph; all other
  nodes are deterministic (`topology.py:55-62`).
- No `Send` / parallel fan-out; edges are sequential (`topology.py:353-376`).

## 4. State worlds (anchor for STA)

- **Business truth** is loaded per turn from an app-managed live store and re-committed after
  the graph — `governed_runtime.py:331` (`_load_live_governed_state`) and `:419`
  (`_update_governed_state_post_graph`), backed by Postgres (`case_record`,
  `case_state_snapshot`, immutable `mutation_events`) + a 24h-TTL Redis session.
- **Execution state** is the LangGraph checkpointer (`topology.py:197-250`, Redis in
  prod/staging, else `InMemorySaver`/None). `thread_id = sealai:{tenant}:{owner}:{session}`
  (`governed_runtime.py:108`).
- No `get_state`/`aget_state` reads of business data from the checkpointer were found.
- Caveat: `GraphState` extends `GovernedSessionState` (`graph/__init__.py:41`), so when the
  checkpointer is enabled it persists the full business state as a side effect (see audit
  report STA-01).

## 5. Test suites — exact commands and results

All run on the VPS (`/home/thorsten/sealai`) with `../.venv/bin/python` (Python 3.12).
`backend/pytest.ini`: `testpaths = tests`, `pythonpath = backend langchain_core_stub`,
`asyncio_mode = auto`. Note `langchain_core_stub` + a `conftest.py` `langgraph`/`openai` stub
mean the suite exercises node/service logic **without compiling the real graph or calling
real models** (relevant to TST-01).

| Suite | Command | Result |
|---|---|---|
| Broad backend | `cd backend && python -m pytest app/agent/tests tests -q` | **4688 passed, 9 skipped, 401 warnings** in 143s — exit 0 ✓ |
| Architecture + governed-seam guardrails | `cd backend && python -m pytest tests/architecture app/agent/tests/test_governed_runtime_seam.py -q` | **23 passed** in 5.68s — exit 0 ✓ |
| Frontend (vitest) | `npm --prefix frontend run test:run` | **198 passed, 1 failed** (31/32 files pass) — exit 1 ⚠️ |

No failures in the backend suites. Warnings are deprecation noise (SQLAlchemy date adapter,
Alembic `path_separator`), not test failures.

**One pre-existing frontend failure** (not introduced by this read-only audit):
`src/test/workspaceMapping.test.tsx > mapWorkspaceView > maps the shared backend RFQ readiness
contract fixture without dropping fields` — `AssertionError: expected [ …(20) ] to deeply equal
[ …(19) ]`. This is a **contract-fixture drift** between the frontend workspace mapping and
`contracts/rfq_readiness_projection_v1.fixture.json` (one field count mismatch). It is unrelated
to V1.8 and predates this audit; flagged here for the backlog.

## 6. CI / scripts note

> **CORRECTION (post-Phase-1):** an earlier draft said `.github/workflows/` was "empty".
> That was a **mirror artifact** — the read-only analysis mirror excluded root dotfiles
> (`.github/`), so the sub-agent could not see the workflows. The VPS repo **does have CI**.

- `.github/workflows/` on the VPS contains: `backend-contracts.yml` (architecture enforcers
  via `--noconftest` + a light "doctrine fast suite" of pydantic-only guard tests),
  `langgraph-v2-guardrails.yml` (v2-only code guard, frontend build + BFF smoke, ruff-format),
  `build-and-push.yml`, `deploy.yml`, `secret-scan.yml`. CI runs on `push` + `pull_request`.
- The backend CI is **deliberately light** (pinned `pytest`/`pydantic` only; the heavy
  runtime suite + full golden REPLAY are explicitly deferred to a "future full-stack job" per
  the workflow comments). So §7.11/AC5 "golden REPLAY per PR" is **partially** enforced
  (selected goldens run; the broad suite does not). See the corrected TST-01 in the audit
  report.
- `scripts/check_rwdr_mvp_demo.sh` referenced in `AGENTS.md` is not present in the mirrored
  tree; re-confirm on the VPS before relying on the demo gate.

## 7. What Phase 1 measures next

The deep audit (companion file `v18_audit_report.md`) works through all 30 Annex-A IDs with
status + `path:line` evidence, the Core/Pack and state-world maps, the prompt/mode
inventories, and the §11 (18 criteria) gap list with severity + blast radius.
