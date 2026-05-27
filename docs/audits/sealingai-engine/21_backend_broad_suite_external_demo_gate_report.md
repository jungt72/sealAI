# RWDR MVP Backend Broad Suite External Demo Gate Report

Date: 2026-05-27

## Readiness Verdict

`READY_FOR_INTERNAL_DEMO`

The RWDR MVP remains green on focused backend, golden-case, frontend, export, and static checks. Backend broad collection is now unblocked, but the backend broad execution still has 11 non-RWDR V10/Graph/Runtime expectation-drift failures. For `READY_FOR_LIMITED_EXTERNAL_DEMO`, these failures need an explicit architecture-owner waiver or a follow-up V10 runtime stabilization patch. The PDF export is functional and sample-generated, but still needs a human visual review before external use.

## Starting Context

- Repository: `/home/thorsten/sealai`
- Branch: `redesign/sealai-cockpit-overview`
- Worktree: very dirty before this patch, with broad V10/runtime/frontend/RWDR changes already present.
- Active goal: close or isolate backend broad collection blockers without adding RWDR product features.

## Backend Broad Collection Blockers Before

| Blocker | Location | Root cause | RWDR-related | Safe fix |
|---|---|---:|---:|---:|
| Duplicate `test_prompts.py` module | `backend/scripts/test_prompts.py`, `backend/test_prompts.py` | Pytest imported both as `test_prompts` because scripts directory was not package-scoped | No | Yes |
| Missing `app.langgraph_v2` | `backend/test_upgrade.py` | Legacy root smoke test imports removed LangGraph v2 runtime | No | Yes, legacy gate |
| Missing `AIMessage` in test stub | Broad collection after old scripts import | `backend/simple_test.py` / `backend/e2e_test.py` mutated `sys.modules` at import time | No | Yes |
| Missing `HumanMessage` in test stub | Broad collection after old scripts import | Same import-time stub pollution | No | Yes |

## Blockers Fixed

- Added `backend/scripts/__init__.py` so `backend/scripts/test_prompts.py` no longer collides with root `backend/test_prompts.py`.
- Made `backend/simple_test.py` import-safe by moving stub mutation into `main()` guarded by `if __name__ == "__main__"`.
- Made `backend/e2e_test.py` import-safe by moving legacy stub mutation into the direct-execution block.
- Gated `backend/test_upgrade.py` with `pytest.importorskip("app.langgraph_v2", ...)` because this is a removed legacy LangGraph v2 smoke path.
- Gated root `backend/test_prompts.py` with an explicit module-level skip because it expects removed `/root/sealai/backend/app/services/langgraph/prompts` templates.
- Gated `backend/app/api/tests/test_legacy_v2_mount_flag.py` with an explicit module-level skip because the legacy V2 chat router is intentionally removed; health diagnostics remain the supported legacy signal.
- Adjusted RWDR Markdown/PDF export metadata precedence so persisted export metadata `case_id` is displayed instead of the transient draft case id.

## Files Changed In This Patch

- `backend/scripts/__init__.py`
- `backend/simple_test.py`
- `backend/e2e_test.py`
- `backend/test_upgrade.py`
- `backend/test_prompts.py`
- `backend/app/api/tests/test_legacy_v2_mount_flag.py`
- `backend/app/services/rwdr_mvp_brief.py`
- `docs/audits/sealingai-engine/21_backend_broad_suite_external_demo_gate_report.md`

## Backend Broad Results

### Collection

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend --collect-only
```

Result: passed collection with exit code `0`.

Impact: the four prior collection blockers are closed or explicitly legacy-gated. Backend broad can now execute.

### Full Backend Broad

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend
```

Result: failed with 11 failures. No collection errors.

Remaining failures:

| Test | Classification | Reason |
|---|---|---|
| `backend/app/agent/tests/graph/test_normalize_node.py::TestNoLLM::test_openai_never_called` | C: architecture expectation drift | Runtime now adds `ambiguous_pressure_bar`; test still expects exactly 3 normalized params. |
| `backend/app/agent/tests/test_knowledge_debug_trace.py::test_knowledge_debug_trace_enabled_with_composer_success` | C: V10 knowledge runtime drift | Composer patch is not reached; response uses current passthrough path. |
| `backend/app/agent/tests/test_knowledge_debug_trace.py::test_knowledge_debug_trace_enabled_with_composer_fallback` | C: V10 knowledge runtime drift | Debug source is `reply_passthrough`, test expects `composer_fallback`. |
| `backend/app/agent/tests/test_phase_f_streaming_cut.py::TestFlagOffUsesGovernedAuthority::test_gate_flag_off_uses_governed_path` | C/E: V10 streaming/governed path drift | Patched governed stream is not called; route uses current streaming/runtime path. |
| `backend/app/agent/tests/test_phase_f_streaming_cut.py::TestGateFlagOnConvFlagOffUsesGovernedAuthority::test_gate_flag_on_conv_flag_off_uses_governed_path` | C/E: V10 streaming/governed path drift | Same class of governed routing expectation drift. |
| `backend/app/agent/tests/test_phase_f_streaming_cut.py::TestGovernedUsesNewGraphPath::test_governed_uses_canonical_governed_graph_path` | C/E: V10 streaming/governed path drift | Same class of governed graph path expectation drift. |
| `backend/app/agent/tests/test_phase_f_streaming_cut.py::TestLegacyFacadeUsesCanonicalAuthority::test_legacy_facade_uses_governed_authority_when_flags_are_off` | C/E: V10 streaming/governed path drift | Same class of legacy facade expectation drift. |
| `backend/app/agent/tests/test_turn_context.py::test_build_governed_turn_context_stays_small_and_compatible` | C: governed context wording/selection drift | Open-points summary no longer contains expected conflict/pressure wording. |
| `backend/app/agent/tests/test_v7_runtime_dispatch.py::test_chat_endpoint_enters_governed_graph_for_enter_graph_runtime_action` | C/E: V7/V10 dispatch expectation drift | Test expects mocked graph path; current runtime returns empty guarded answer path under stubbed DB persistence. |
| `backend/app/agent/tests/v92/test_v92_orchestrator.py::test_v92_engineering_node_builds_rwdr_ledger_from_compute_results` | C: V9.2 engineering expectation drift | Next action is `collect_missing_inputs`; test expects dossier review. |
| `backend/app/agent/tests/v92/test_v92_orchestrator.py::test_v92_engineering_node_runs_oring_screening_without_release_claims` | C: V9.2 O-ring screening expectation drift | O-ring result is `insufficient_data`; test expects `ok`. |

RWDR relation: none of the 11 failures are in the RWDR MVP brief, RWDR case-state, RWDR API, RWDR golden-case, PDF/export, or frontend RWDR flow.

## Agent/Backend Drift Results

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests backend/tests
```

Result: failed with the same 11 failures listed above. This confirms the remaining failures are the already-known V10/Graph/Runtime expectation drift set, not collection artifacts and not RWDR-specific regressions.

## Focused RWDR Results

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py
```

Result: `13 passed`.

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py
```

Result: `86 passed`; one unrelated deprecation warning for `HTTP_422_UNPROCESSABLE_ENTITY`.

## Frontend Results

Focused command:

```bash
npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
```

Result: `3 passed`, `16 tests passed`.

Broad command:

```bash
npm --prefix frontend run test:run
```

Result: `27 passed`, `139 tests passed`.

## Static Hygiene

Command:

```bash
git diff --check
```

Result: passed.

AppleDouble/resource-fork check:

```bash
find . -name '._*' -print
git ls-files | grep -F '._' || true
```

Result:

- One runtime lock-like file remains: `./paperless/data/log/.__paperless.lock`.
- No tracked AppleDouble files were found with fixed-string `git ls-files | grep -F '._'`.
- The remaining `paperless` lock was not removed because it is not an obvious source artifact such as `._*.py`, `._*.tsx`, or `._*.md`.

## Forbidden-Language Triage

Command:

```bash
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

Classification:

| Class | Meaning | Current result |
|---|---|---|
| A | Allowed disclaimer / negating non-release wording | Present in RWDR disclaimer and educational non-final wording. |
| B | Tests, guards, fixtures, prompts, audit docs | Present, including RWDR golden-case forbidden phrase fixtures and guard tests. |
| C | Legacy non-RWDR/internal surfaces | Present in manufacturer-fit tests/services, old V8/V9 docs, internal `approved` workflow states, knowledge source data. |
| D | RWDR customer-facing must-fix | None found in the active RWDR MVP surfaces checked by focused tests and golden cases. |

No RWDR customer-facing D-hit was fixed in this patch because none was identified.

## PDF / Markdown Demo Sample

Demo input:

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

Generated sample artifacts:

- Markdown: `/tmp/sealai_rwdr_demo_sample.md`
- PDF: `/tmp/sealai_rwdr_demo_sample.pdf`

Sample generation result:

- Status: `NEEDS_CLARIFICATION`
- Revision count in fake persisted test session: `13`
- PDF header: `%PDF-`
- PDF size: `13791` bytes
- Markdown includes `Technical RWDR RFQ Brief`, real persisted `Case-ID`, `Kritisch fehlende Angaben`, `Umfangsgeschwindigkeit`, and `Disclaimer`.
- Markdown forbidden phrase scan for material/product/manufacturer recommendation terms returned no hits.

Readiness note: functional export is acceptable for internal demo. Before limited external demo, open the PDF visually and confirm layout/readability with a real browser/PDF viewer.

## Dirty Worktree Summary

The worktree remains very dirty and should not be treated as release-clean.

Observed categories:

- RWDR intentional changes: RWDR brief service, RWDR API tests, RWDR fixtures/docs, RWDR PDF renderer, frontend RWDR/BFF files.
- V10/runtime intentional or prior changes: many `backend/app/agent/**`, prompt, runtime, projection, and service files.
- Frontend broad-stabilization changes: dashboard tests/components, workspace mapping, cockpit view model files.
- Hygiene changes from this gate: legacy root test gating, script import-safety, `backend/scripts/__init__.py`.
- Untracked generated/work areas: `_deploy_backups/`, many RWDR/docs/test files, frontend BFF RWDR routes, brand components, stream workspace adapter files.
- Deleted `.codex` marker remains in status as `D .codex`.

External-demo recommendation: commit/stash intentionally grouped changes before external demo. Do not ship this dirty tree as-is.

## External Demo Recommendation

Not ready for `READY_FOR_LIMITED_EXTERNAL_DEMO` without an explicit waiver.

The RWDR-specific system is demoable internally and technically isolated from the remaining broad failures. The limiting issues are:

1. Backend broad execution still fails 11 non-RWDR V10/Graph/Runtime tests.
2. Worktree is very dirty and needs release grouping.
3. PDF has functional test coverage and sample generation but still needs manual visual review.

## Next Recommended Patch

Run a dedicated V10/Graph runtime stabilization patch:

1. Decide canonical behavior for binary-gate-off streaming and governed fallback.
2. Update or retire stale V7/V9.2 expectation tests with architecture-owner approval.
3. Fix knowledge debug trace source expectations against current composer/passthrough runtime.
4. Normalize the `ambiguous_pressure_bar` test expectation.
5. Perform visual PDF sample review and record a checked-in non-sensitive sample only if repo policy allows it.
6. Split the dirty worktree into reviewable commits before any limited external demo.

