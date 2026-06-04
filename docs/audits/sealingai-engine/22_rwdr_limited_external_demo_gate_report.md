# RWDR Limited External Demo Gate Report

Date: 2026-05-27

## Verdict

`READY_FOR_LIMITED_EXTERNAL_RWDR_DEMO`

This verdict is scoped strictly to a guided RWDR demo with 3-5 selected manufacturers, distributors, application engineers, or technical sales experts.

Full app release readiness remains `NOT READY`.

## Exact Demo Scope

Allowed demo surface:

- RWDR raw inquiry input.
- Source-span confirmation for liability-bearing extracted fields.
- Confirm / edit / not stated / reject flow.
- Backend-owned RWDR case-state.
- `case_state_snapshots` revision history.
- Read-only revision diff.
- `Technical RWDR RFQ Brief`.
- Markdown export.
- PDF export.
- The documented golden demo case:

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

Demo framing:

- Guided session only.
- No public launch.
- No self-service release.
- No claim that the whole application is release-ready.

## Explicitly Out Of Scope

- Manufacturer marketplace.
- Manufacturer routing.
- Paid listings.
- Partner matching.
- Material recommendations.
- Product recommendations.
- Manufacturer recommendations.
- Final suitability or technical approval.
- Non-RWDR V10/Graph workflows.
- Broad legacy application release.

## Test Evidence

### RWDR Golden Cases

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py
```

Result: `13 passed`.

### RWDR / RFQ Backend Focused Suite

Command:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py
```

Result: `86 passed`; one deprecation warning for `HTTP_422_UNPROCESSABLE_ENTITY`.

### RWDR Frontend Focused Suite

Command:

```bash
npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
```

Result: `3 files passed`, `16 tests passed`.

### Frontend Broad Suite

Command:

```bash
npm --prefix frontend run test:run
```

Result: `27 files passed`, `139 tests passed`.

### Static Hygiene

Command:

```bash
git diff --check
```

Result: passed.

### Bundled RWDR Demo Gate

Created script:

```bash
scripts/check_rwdr_mvp_demo.sh
```

The script runs RWDR golden cases, focused backend RWDR/RFQ tests, focused frontend RWDR tests, frontend broad tests, `git diff --check`, and the scoped forbidden-language scan. It intentionally does not require backend broad to be fully green because the remaining failures are documented non-RWDR V10/Graph drift.

Run result: script completed successfully.

## Demo Artifacts

Generated under:

```text
docs/product/sealing-intelligence/demo-artifacts/
```

Files:

- `rwdr_demo_sample.md`
- `rwdr_demo_sample.pdf`
- `rwdr_demo_sample_metadata.txt`

Generation metadata:

```text
status=NEEDS_CLARIFICATION
revision_count=13
pdf_header=b'%PDF-'
```

The Markdown sample includes:

- `Technical RWDR RFQ Brief`
- real generated `Case-ID`
- revision
- status
- confirmed data
- missing critical fields
- computed circumferential speed
- measurement hints
- manufacturer questions
- source overview
- disclaimer

## PDF Visual / Readability Review

Review method:

- Generated PDF from backend-persisted RWDR brief path.
- Verified binary header starts with `%PDF-`.
- Inspected PDF text stream with `strings` because `pdftotext` / `pdfinfo` are not installed in the environment.
- Verified Markdown export for equivalent sections and forbidden terms.

Readiness checklist:

| Check | Result |
|---|---|
| Header contains `sealing \| Intelligence` | Pass |
| Title contains `Technical RWDR RFQ Brief` | Pass |
| Case-ID visible | Pass |
| Revision visible | Pass |
| Status visible | Pass |
| Confirmed data visible | Pass |
| Missing critical fields prominent | Pass |
| Circumferential speed visible | Pass |
| Measurement hints visible | Pass |
| Manufacturer questions visible | Pass |
| Disclaimer visible | Pass |
| No material recommendation | Pass |
| No product recommendation | Pass |
| No manufacturer recommendation | Pass |
| No final approval/suitability wording except negating disclaimer | Pass |

Small hardening fix:

- `backend/app/api/v1/renderers/rfq_pdf.py` now normalizes PDF text to deterministic ASCII-safe German transliterations (`Ö` -> `Oe`, `ü` -> `ue`, etc.) before writing PDF strings. This prevents broken text fragments in the simple dependency-free PDF renderer.

Known PDF limitation:

- The renderer is functional and readable but still basic. It is acceptable for a guided expert feedback session, not for a polished public launch.

## Demo Script Hardening

Updated:

```text
docs/product/sealing-intelligence/rwdr_demo_script.md
```

It now includes:

- 5-minute demo flow.
- 10-minute demo flow.
- exact demo input.
- click path.
- talk track.
- what to emphasize.
- what not to claim.
- expected reviewer questions and safe answers.

Required talk track included:

```text
sealing | Intelligence gibt keine Dichtung frei. Es macht die Anfrage für Hersteller bewertbar.
```

Also included:

```text
Das System strukturiert bestätigte Angaben, fehlende Informationen, berechnete Werte und Herstellerfragen.
Material-, Bauform- und Herstellerbewertung bleiben beim Hersteller, Händler oder verantwortlichen Experten.
```

## External Feedback Checklist

Created:

```text
docs/product/sealing-intelligence/rwdr_external_feedback_checklist.md
```

The checklist asks reviewers whether the brief speeds up response, which fields are still missing, which questions matter, whether the PDF is professional enough, whether anything looks like a recommendation, and what would make the brief quote-ready.

## Forbidden-Language Result

Command:

```bash
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

Result: noisy by design, with test fixtures, guards, historical docs, legacy non-RWDR surfaces, and audit reports.

Classification:

| Class | Meaning | Result |
|---|---|---|
| A | Allowed negating disclaimer / non-release wording | Present |
| B | Tests, guards, fixtures, prompts, audit docs | Present |
| C | Legacy non-RWDR or internal workflow vocabulary | Present |
| D | Active RWDR customer-facing must-fix | None identified |

Additional artifact check:

```bash
rg -n "recommended material|recommended product|best manufacturer|final solution|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung|FKM empfohlen|NBR geeignet" docs/product/sealing-intelligence/demo-artifacts/rwdr_demo_sample.md
```

Result: no hits.

## Non-RWDR Failure Isolation

Report 21 established:

- Backend collection is green.
- Backend broad execution still has 11 failures.
- The 11 failures are V10/Graph/Runtime/Expectation Drift.
- No failures are in:
  - RWDR MVP Brief
  - RWDR API
  - RWDR Case-State
  - RWDR Golden Cases
  - RWDR Export path
  - RWDR Frontend flow

Remaining non-RWDR failure areas:

- `normalize_node` expectation drift around `ambiguous_pressure_bar`.
- Knowledge debug trace composer/passthrough drift.
- Phase-F streaming / governed graph path drift.
- Governed turn-context summary wording drift.
- V7 runtime dispatch expectation drift.
- V9.2 engineering/orchestrator expectation drift.

These are not blockers for a scoped, guided RWDR demo, but they are blockers for full-app release readiness.

## Worktree Grouping

The worktree remains very dirty. A limited RWDR demo branch/PR should group changes deliberately.

| Group | Representative files | Needed for RWDR demo | Risk |
|---|---|---:|---|
| 1. RWDR core/domain changes | `backend/app/services/rwdr_mvp_brief.py` | Yes | Medium, core demo logic |
| 2. RWDR API/persistence/snapshot changes | `backend/app/api/v1/endpoints/rfq.py`, `backend/app/api/v1/renderers/rfq_pdf.py`, `backend/app/api/tests/test_rfq_endpoint.py` | Yes | Medium |
| 3. RWDR frontend/confirmation changes | `frontend/src/components/dashboard/RfqPane.tsx`, RWDR BFF routes under `frontend/src/app/api/bff/rfq/rwdr/` | Yes | Medium |
| 4. RWDR tests/golden cases | `backend/app/api/tests/test_rwdr_golden_cases.py`, `backend/tests/fixtures/rwdr_golden_cases.json`, `backend/tests/unit/services/test_rwdr_mvp_brief.py` | Yes | Low |
| 5. RWDR docs/demo/audits | `docs/product/sealing-intelligence/**`, `docs/audits/sealingai-engine/12-22*` | Yes | Low |
| 6. Release-hygiene changes | `.gitignore`, `backend/scripts/test_audit_logger.py`, `backend/scripts/test_hitl_resume.py`, `backend/scripts/__init__.py`, root legacy test gates | Useful | Low/Medium |
| 7. Unrelated V10/Graph/frontend/legacy dirty files | many `backend/app/agent/**`, prompt, runtime, projection and dashboard files | No for scoped RWDR demo unless depended on by current branch | High |
| 8. Untracked/generated files | `_deploy_backups/`, `docs/product/sealing-intelligence/demo-artifacts/rwdr_demo_sample.pdf`, broad new tests/docs/routes | Mixed | Review required |

Recommendation:

- Prepare a review branch that includes groups 1-6 and only the group-7 files actually required by the RWDR UI/BFF integration.
- Do not present the dirty worktree itself as release-clean.

## Recommended Demo Audience

Use a guided session with:

- 1-2 RWDR manufacturers.
- 1 distributor or technical inside-sales reviewer.
- 1 application engineer.
- Optional: 1 maintenance / MRO user who sends real-world incomplete inquiries.

Avoid:

- Public self-service users.
- Procurement-only users without technical context.
- Safety-critical or regulated applications.

## Demo Risks

- PDF is basic and should be framed as MVP export.
- Broad backend has documented non-RWDR failures; avoid non-RWDR flows.
- Worktree is not release-clean.
- Demo must be moderated so no one interprets `COMPLETE` as technical approval.
- German umlauts in PDF are transliterated for renderer stability.

## Next Patch Recommendation

1. Split RWDR demo branch into reviewable commits by the worktree grouping above.
2. Run a human visual PDF review with the generated sample.
3. Create an external-demo facilitation sheet using the feedback checklist.
4. Stabilize V10/Graph non-RWDR drift separately.
5. Improve PDF layout after the first external feedback round, but keep it inside the `Technical RWDR RFQ Brief` scope.

