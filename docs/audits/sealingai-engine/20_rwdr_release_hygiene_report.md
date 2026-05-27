# RWDR MVP Release Hygiene Report 20

Date: 2026-05-27

## Readiness Verdict After Patch

Readiness verdict: `READY_FOR_INTERNAL_DEMO`

The patch improves release hygiene materially:

- AppleDouble artifacts no longer break architecture tests.
- Manual live scripts no longer execute network calls or `sys.exit` during pytest import for the two observed blockers.
- Frontend broad suite is green.
- Focused RWDR backend/frontend suites remain green.
- Markdown/PDF export now carries visible revision metadata more consistently.

The MVP is still not `READY_FOR_LIMITED_EXTERNAL_DEMO` because the broad backend suite still has unrelated collection/runtime drift outside the RWDR MVP.

## Repository Hygiene Discovery

Commands run:

```bash
pwd
git status --short
git branch --show-current
find . -name '._*' -print
git ls-files | grep '._' || true
git ls-files | grep -F '._' || true
```

Results:

- `pwd`: `/home/thorsten/sealai`
- branch: `redesign/sealai-cockpit-overview`
- Worktree remains broadly dirty from prior work.
- Exact `git ls-files | grep '._' || true` is regex-noisy because `.` matches any character. Literal check with `grep -F '._'` returned no tracked AppleDouble files.

## Cleaned Artifacts

Removed safe untracked AppleDouble/resource-fork artifacts from backend/frontend/docs code paths:

```text
backend/app/agent/communication/._rfq_intent.py
backend/app/agent/communication/._context.py
backend/app/agent/v92/._calculation_projection.py
backend/app/agent/tests/._test_calculation_state_ledger.py
backend/app/agent/state/._reducers.py
backend/app/agent/state/._projections.py
backend/app/api/v1/projections/._case_workspace.py
frontend/src/components/dashboard/._CaseScreen.tsx
frontend/src/components/dashboard/._SealCockpit.tsx
frontend/src/lib/._streamWorkspace.ts
frontend/src/lib/engineering/._buildSealCockpitViewModel.test.ts
frontend/src/lib/engineering/._buildSealCockpitViewModel.metrics.test.tsx
frontend/src/lib/engineering/._buildSealCockpitViewModel.ts
frontend/src/lib/._streamWorkspaceAdapter.test.ts
frontend/src/lib/._streamWorkspaceAdapter.ts
frontend/src/lib/._streamWorkspace.test.ts
frontend/src/app/api/bff/agent/chat/stream/._route.ts
frontend/src/app/api/bff/agent/chat/stream/._route.spec.ts
```

Remaining `find . -name '._*' -print` hit:

```text
./paperless/data/log/.__paperless.lock
```

This was not removed because it is under runtime data and is not a source-code AppleDouble file.

Added `.gitignore` rule:

```text
._*
```

## Files Changed

Changed in this patch:

- `.gitignore`
- `backend/scripts/test_audit_logger.py`
- `backend/scripts/test_hitl_resume.py`
- `backend/app/services/rwdr_mvp_brief.py`
- `frontend/src/lib/engineering/sealCockpitViewModel.ts`
- `frontend/src/lib/engineering/sealCockpitMock.ts`
- `docs/audits/sealingai-engine/20_rwdr_release_hygiene_report.md`

Previously touched but still relevant from the readiness pass:

- `backend/app/api/v1/renderers/rfq_pdf.py`

## test_audit_logger.py Hardening

Problem:

- `backend/scripts/test_audit_logger.py` was collected by pytest.
- It executed a live localhost SSE request during import.
- On failure it called `sys.exit(1)`, aborting broad pytest collection.

Fix:

- Moved live execution into `main()`.
- Kept `query_audit_log()` import-safe.
- Added `if __name__ == "__main__": sys.exit(main())`.
- Verified with `py_compile`.

Result:

- This script no longer aborts broad pytest collection.

## test_hitl_resume.py Hardening

After fixing `test_audit_logger.py`, broad pytest exposed the same issue in `backend/scripts/test_hitl_resume.py`.

Fix:

- Rewrote it as an import-safe manual integration script.
- All localhost calls now happen only in `main()`.
- Added `if __name__ == "__main__": sys.exit(main())`.
- Verified with `py_compile`.

Result:

- This script no longer aborts broad pytest collection.

## AppleDouble Test Failures

Before:

- `backend/tests/architecture/test_ssot_guardrails.py` failed with `UnicodeDecodeError` because AppleDouble binary files named `._*.py` were scanned as Python source.

After:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/architecture/test_ssot_guardrails.py
```

Result:

```text
8 passed
```

Classification:

- `AppleDouble issue`
- Fixed.

## Frontend Broad Drift

Problem:

- `npm --prefix frontend run test:run` failed in `CaseScreen.test.tsx`.
- Tests expected tabs `Berechnung` and `Anfragebasis`.
- The component already had render paths for `calculation` and `rfq`, but `sealCockpitTabs` and mock tabs omitted them.

Assessment:

- UI/test consistency drift.
- Not RWDR doctrine-related.
- Small safe fix: restore existing tabs in the view-model tab list and mock data.

Fix:

- Added `{ id: "calculation", label: "Berechnung" }`.
- Added `{ id: "rfq", label: "Anfragebasis" }`.

Verification:

```bash
npm --prefix frontend run test:run -- src/components/dashboard/CaseScreen.test.tsx
npm --prefix frontend run test:run
```

Results:

```text
CaseScreen.test.tsx: 9 passed
Frontend broad: 27 files passed, 139 tests passed
```

## PDF / Markdown Readiness

Demo case checked through golden tests and export code:

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

Readiness checks:

- Header: `sealing | Intelligence` in PDF renderer.
- Artifact: `Technical RWDR RFQ Brief`.
- `case_id`: visible in Markdown and PDF.
- Revision: now passed into Markdown content and PDF content from persisted export snapshot metadata.
- Status: visible.
- Sections: present through backend brief contract.
- Critical missing fields: present under `Kritisch fehlende Angaben`.
- Circumferential speed: generated after confirmed d1/rpm and tested by golden cases.
- Measurement hints: present under `Empfohlene Mess- und Prüfangaben für Herstellerbewertung`.
- Disclaimer: present.
- No material/product/manufacturer recommendation in focused tests.
- No final suitability/approval language except negating disclaimer.

Small export fix:

- `DbRWDRCaseStateRepository.export_markdown()` now calls `_brief_markdown(..., export_metadata=...)`.
- `DbRWDRCaseStateRepository.export_pdf_document()` now passes export metadata into `_rwdr_pdf_content(...)`.
- `_rwdr_pdf_content()` now exposes the export revision in the `revision.case_revision` payload consumed by the PDF renderer.

Remaining PDF limitation:

- PDF is still a basic text renderer. It is functionally acceptable for internal demo, but visual polish and pagination should be reviewed before limited external demo.

## Focused Test Results

Golden cases:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py
```

Result:

```text
13 passed
```

Focused backend RWDR/RFQ:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py
```

Result:

```text
86 passed
1 warning: HTTP_422_UNPROCESSABLE_ENTITY deprecation in test_rfq_endpoint.py
```

Focused frontend RWDR:

```bash
npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
```

Result:

```text
3 files passed
16 tests passed
```

Static hygiene:

```bash
git diff --check
```

Result:

```text
passed
```

## Broad Test Results

### Broad Backend: `backend`

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend
```

Result:

```text
failed: 4 collection errors
```

Collection errors:

| Test / file | Reason | Classification | Status |
| --- | --- | --- | --- |
| `backend/test_prompts.py` | Import-file mismatch with `backend/scripts/test_prompts.py` due duplicate module basename | environment/test-layout issue | remaining |
| `backend/test_upgrade.py` | Imports removed `app.langgraph_v2` | architecture expectation drift / legacy test | remaining |
| `backend/tests/agent/test_agent_logic.py` | Cannot import `HumanMessage` from current `langchain_core` test stub | environment/config issue | remaining |
| `backend/tests/agent/test_chat_history_legacy_owner_bridge.py` | Cannot import `AIMessage` / `HumanMessage` from current `langchain_core` test stub | environment/config issue | remaining |

Fixed compared with previous pass:

- `backend/scripts/test_audit_logger.py` no longer aborts collection.
- `backend/scripts/test_hitl_resume.py` no longer aborts collection.

### Broad Backend: canonical agent/tests path

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests backend/tests
```

Result:

```text
failed: 11 failures
```

Failure classification:

| Test | Reason summary | Classification | Status |
| --- | --- | --- | --- |
| `backend/app/agent/tests/graph/test_normalize_node.py::TestNoLLM::test_openai_never_called` | Normalizer now produces extra `ambiguous_pressure_bar` parameter; test expects 3 parameters | architecture expectation drift | remaining |
| `backend/app/agent/tests/test_knowledge_debug_trace.py::test_knowledge_debug_trace_enabled_with_composer_success` | Composer path not invoked; captured request absent | V10/knowledge runtime drift | remaining |
| `backend/app/agent/tests/test_knowledge_debug_trace.py::test_knowledge_debug_trace_enabled_with_composer_fallback` | Debug source is `reply_passthrough` not `composer_fallback` | V10/knowledge runtime drift | remaining |
| `backend/app/agent/tests/test_phase_f_streaming_cut.py::TestFlagOffUsesGovernedAuthority::test_gate_flag_off_uses_governed_path` | Expected governed stream path not called | architecture expectation drift | remaining |
| `backend/app/agent/tests/test_phase_f_streaming_cut.py::TestGateFlagOnConvFlagOffUsesGovernedAuthority::test_gate_flag_on_conv_flag_off_uses_governed_path` | Expected governed stream path not called | architecture expectation drift | remaining |
| `backend/app/agent/tests/test_phase_f_streaming_cut.py::TestGovernedUsesNewGraphPath::test_governed_uses_canonical_governed_graph_path` | Governed graph path expectation drift | architecture expectation drift | remaining |
| `backend/app/agent/tests/test_phase_f_streaming_cut.py::TestLegacyFacadeUsesCanonicalAuthority::test_legacy_facade_uses_governed_authority_when_flags_are_off` | Legacy facade expectation drift | architecture expectation drift | remaining |
| `backend/app/agent/tests/test_turn_context.py::test_build_governed_turn_context_stays_small_and_compatible` | Open-point wording no longer contains expected conflict/pressure label | test expectation drift | remaining |
| `backend/app/agent/tests/test_v7_runtime_dispatch.py::test_chat_endpoint_enters_governed_graph_for_enter_graph_runtime_action` | Response markdown empty, expected mocked graph response | V7/V10 dispatch drift | remaining |
| `backend/app/agent/tests/v92/test_v92_orchestrator.py::test_v92_engineering_node_builds_rwdr_ledger_from_compute_results` | Next action now `collect_missing_inputs`, expected dossier review | architecture/domain expectation drift | remaining |
| `backend/app/agent/tests/v92/test_v92_orchestrator.py::test_v92_engineering_node_runs_oring_screening_without_release_claims` | O-ring screening now insufficient data, expected ok | unrelated O-ring expectation drift | remaining |

Fixed compared with previous pass:

- AppleDouble-related architecture failures are gone.

### Broad Frontend

Command:

```bash
npm --prefix frontend run test:run
```

Result:

```text
27 files passed
139 tests passed
```

Classification:

- frontend broad is now green.

## Forbidden-Language Triage

Command:

```bash
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

Result:

```text
457 hits
```

Classification:

| Category | Meaning | Examples | Action |
| --- | --- | --- | --- |
| A | allowed disclaimer / explicit negation | RWDR disclaimer with `keine finale technische Eignungsfreigabe`, `keine Materialfreigabe`, `keine Produktempfehlung` | allowed |
| B | tests / guard / prompt / audit documentation | golden fixtures, forbidden-language tests, output guards, audit reports, prompt safety rules | allowed |
| C | legacy non-RWDR surface or internal workflow vocabulary | `approved` review states, manufacturer-fit tests, historical V8/V9 docs, knowledge data with `suitable` in source material | not changed in this RWDR hygiene pass |
| D | RWDR customer-facing must-fix | none found in current RWDR MVP UI/export paths | no D fixes required |

Notes:

- `backend/scripts/test_hitl_resume.py` contains `Freigabe erteilt` in reviewer notes for a manual HITL integration script. This is not RWDR customer-facing output.
- `frontend/content/wissen/...` contains negating/non-final educational wording around `freigegeben`; not part of RWDR MVP flow.
- `backend/app/services/rwdr_mvp_brief.py` contains forbidden terms as guard configuration.

## Remaining Blockers

For internal demo:

- No RWDR-specific blocker remains after this hygiene pass.

For limited external demo:

- Broad backend still has 4 collection errors under `pytest -q backend`.
- Canonical backend suite still has 11 non-RWDR failures.
- Worktree remains very dirty from many parallel product/runtime changes.
- PDF still needs a visual/readability pass with generated sample files.

## Next Recommendation

Next patch should focus on backend broad-suite closure, not RWDR features:

1. Resolve duplicate `test_prompts.py` collection by renaming or moving manual script/test file according to repo convention.
2. Remove or update legacy `app.langgraph_v2` import expectations in `backend/test_upgrade.py`.
3. Fix `langchain_core` test stubs to expose `AIMessage` and `HumanMessage` where broad legacy tests still need them.
4. Decide whether V10/Graph failures represent intended behavior or stale tests; update tests only after architecture owner confirmation.
5. Generate and visually inspect one sample RWDR PDF artifact for demo packaging.
