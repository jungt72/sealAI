# RWDR MVP Repair Report

Datum: 2026-05-27

## Discovery Commands

- `pwd` -> `/home/thorsten/sealai`
- `git branch --show-current` -> `redesign/sealai-cockpit-overview`
- `git status --short` -> dirty worktree with existing backend, frontend and docs changes before this repair.
- `find . -maxdepth 3 -type f | sed 's#^\./##' | sort | head -300`

## Detected Stack

- Backend: Python, FastAPI-style API modules, Pydantic/domain services, pytest.
- Frontend: Next.js/React/TypeScript, Vitest.
- Existing calculation engine: `backend/app/services/calculation_engine.py`.
- Existing norm module: `backend/app/services/norm_modules/din_3760_iso_6194.py`.
- Existing RFQ preview: `backend/app/services/rfq_preview_service.py`.
- Existing PDF renderer: `backend/app/api/v1/renderers/rfq_pdf.py`.
- RWDR domain kernel: `backend/app/services/rwdr_mvp_brief.py`.

## Files Changed

- `backend/app/services/rwdr_mvp_brief.py`
- `backend/app/services/inquiry_extract_service.py`
- `backend/app/services/rfq_preview_service.py`
- `backend/app/api/v1/renderers/rfq_pdf.py`
- `backend/tests/unit/services/test_rwdr_mvp_brief.py`
- `frontend/src/components/dashboard/RfqPane.tsx`
- `frontend/src/components/dashboard/ManufacturerFitPanel.tsx`
- `frontend/src/components/dashboard/ManufacturerFitPanel.test.tsx`
- `frontend/src/lib/engineering/sealCockpitMock.ts`

## Files Created

- `docs/product/sealing-intelligence/rwdr_mvp_concept.md`
- `docs/product/sealing-intelligence/rwdr_module_map.md`
- `docs/product/sealing-intelligence/rwdr_brief_contract.md`
- `docs/product/sealing-intelligence/rwdr_forbidden_language.md`
- `docs/product/sealing-intelligence/rwdr_normative_backbone.md`
- `docs/product/sealing-intelligence/rwdr_measurement_verification.md`
- `docs/audits/sealingai-engine/12_rwdr_mvp_repair_report.md`

## P0/P1 Findings Closed

- Minimal RFQ kernel expanded; cases without `D` and `b` stay `NEEDS_CLARIFICATION`.
- Hard scope guard added for Gleitringdichtung, mechanical seal, ATEX, hydrogen and other hard exclusions.
- EvidenceField now carries `origin`, `confirmation_status`, `source_span`, `liability_bearing`, `allowed_in_brief`.
- LLM-extracted liability fields require confirmation plus source span.
- Explicit unknown values satisfy critical completeness only as unknowns and do not become confirmed facts.
- Forbidden-language helper added and tested.
- 31 named Intelligence modules exist as explicit components.
- Technical RWDR RFQ Brief has the required sections.
- Circumferential speed is calculated in the RWDR orchestrator.
- Normative reference metadata exists for ISO 6194-1/-3/-4/-5, ISO 16589 and DIN 3760 without compliance claim.
- Low-pressure boundary review flags are generated.
- Measurement and verification recommendations are integrated into the brief.
- RWDR-facing PDF/UI wording no longer says `geeignete Dichtungsloesung`, `Warum passend`, `Partner-Fit`, or `freigegeben` in the changed RWDR surfaces.

## Tests Added

Added focused tests in `backend/tests/unit/services/test_rwdr_mvp_brief.py` for:

- Minimal RFQ completeness
- Scope guard hard exclusions
- Evidence gate and explicit unknown handling
- Circumferential speed
- Low-pressure boundary
- Measurement recommendations
- Shaft/housing/material/leakage review flags
- Required brief sections
- Normative metadata
- Determinism
- Forbidden-language guard

## Commands Run

- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py`
- `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py`
- `npm --prefix frontend run test:run -- src/components/dashboard/ManufacturerFitPanel.test.tsx src/components/dashboard/RfqPane.test.tsx src/lib/unsafeProductCopy.spec.ts`
- `git diff --check`
- `rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified" backend frontend docs`

## Test Results

- RWDR MVP focused backend: passed, `16 passed`.
- RFQ/API focused backend: passed, `61 passed`.
- Focused frontend: passed, `3 files / 12 tests passed`.
- `git diff --check`: passed.
- Forbidden-language scan: still finds legacy guard/test/prompt/reference fixtures and the new forbidden-language documentation itself. The changed RWDR brief/PDF/UI strings no longer contain the target positive phrases; broader non-RWDR cleanup is separate.

## Known Rest Gaps

- The modules are MVP-light. Some produce flags/questions only and do not yet cover full engineering depth.
- Frontend confirmation UX is still not a complete field-by-field source-span review flow.
- Broad repo suites were not fully re-run after this repair because the worktree already contained unrelated dirty changes and prior broad-suite environment failures were present.
- The repository still contains non-RWDR legacy/test/reference strings such as approval language in guards, fixtures, prompts and knowledge data. The RWDR customer-facing surfaces touched here were cleaned; broader terminology cleanup should be a separate patch.

## Next Patch

Build the backend-to-frontend confirmation flow: render extracted liability fields with exact source spans and persist Confirm / Edit / Not stated decisions before brief generation.
