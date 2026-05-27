# RWDR MVP Readiness Report 19

Date: 2026-05-27

## Verdict

Readiness verdict: `READY_FOR_INTERNAL_DEMO`

The RWDR MVP is ready for a controlled internal demo with product, engineering, technical sales, selected application engineers, and manufacturer/distributor reviewers in a guided setting.

It is not yet classified as `READY_FOR_LIMITED_EXTERNAL_DEMO` because the broad backend/frontend suites still contain unrelated failures, the worktree is very dirty, AppleDouble artifacts break architecture scans, and PDF rendering is functional but visually basic.

## Critical Blockers

No RWDR-specific critical blockers were found in the focused readiness pass.

For broader release readiness, the following blockers remain:

- Broad backend collection via `PYTHONPATH=backend .venv/bin/python -m pytest -q backend` fails because `backend/scripts/test_audit_logger.py` executes a live localhost HTTP check at import time and calls `sys.exit(1)`.
- Canonical broad backend suite has 13 unrelated failures across graph/runtime/architecture tests. Two architecture failures are caused by AppleDouble binary files named `._*.py`.
- Frontend broad suite has 2 unrelated dashboard tab-name expectation failures in `CaseScreen.test.tsx`.
- The repository has 153 dirty status entries; this is not clean enough for an external demo release branch.

## Non-Critical Issues

- PDF export is functional and sectioned, but remains a simple dependency-free PDF renderer. It has not had a visual/pixel-level review.
- Forbidden-language search is intentionally noisy because it scans tests, guard fixtures, historical concepts, prompts, and legacy non-RWDR surfaces.
- Generated artifacts are present, including `frontend/.next`, `__pycache__`, `backend/error.log`, and AppleDouble files.
- Some legacy non-RWDR surfaces still use `approved`, `no_suitable_partner`, or `freigegeben` as internal workflow/test vocabulary.

## Product Doctrine Readiness

Status: pass for RWDR-focused paths.

Verified doctrine:

```text
AI extracts.
User confirms.
sealing | Intelligence structures.
Manufacturer / distributor / responsible engineer evaluates.
```

The RWDR service, UI tests, brief/export tests, and golden cases preserve these product boundaries:

- No material recommendation.
- No product recommendation.
- No manufacturer recommendation.
- No manufacturer routing or partner matching in the RWDR flow.
- `COMPLETE` remains an RFQ-brief completeness status for manufacturer/responsible-engineer evaluation, not a technical approval.

## Evidence Gate Readiness

Status: pass for focused RWDR tests.

Verified behavior:

- Liability-bearing fields require confirmation before entering confirmed facts.
- Extracted fields keep source spans.
- Extracted liability-bearing fields without source spans are blocked from trusted confirmation.
- `explicitly_unknown` fields are preserved as unknown/missing, not confirmed facts.
- Rejected and unconfirmed fields do not enter confirmed facts.
- Backend case-state remains authoritative for brief and export generation.

## Technical RWDR RFQ Brief Readiness

Status: pass for focused RWDR tests.

Markdown and PDF generation use the persisted backend brief. Required sections are covered:

- Status
- Anfrageart
- Bestätigte Angaben
- Nicht bestätigte Angaben
- Kritisch fehlende Angaben
- Hilfreich fehlende Angaben
- Berechnete Werte
- Engineering Review-Themen
- Empfohlene Mess- und Prüfangaben für Herstellerbewertung
- Herstellerfragen
- Dokumentations-/Regulatorikanforderungen
- Leckage- und Standzeiterwartungen
- Quellenübersicht
- Disclaimer
- Export metadata

Required disclaimer is present:

```text
Dieser Technical RWDR RFQ Brief strukturiert die Anfrage. Er enthält keine finale technische Eignungsfreigabe, keine Materialfreigabe, keine Produktempfehlung und keine Herstellerfreigabe. Die finale technische Bewertung erfolgt durch Hersteller, Händler oder eine verantwortliche technische Stelle.
```

Small hardening fix applied:

- `backend/app/api/v1/renderers/rfq_pdf.py` now uses `sealing | Intelligence` in the PDF header, replaces awkward `governeden SealAI-Fallstand` wording with `backend-eigenen Fallstand`, and labels RWDR sections as `RWDR Brief-Abschnitte`.

## Golden-Case Readiness

Status: pass.

Golden cases exist in `backend/tests/fixtures/rwdr_golden_cases.json` and are executed by `backend/app/api/tests/test_rwdr_golden_cases.py`.

Covered scenarios include:

- Simple gearbox replacement
- Complete gearbox case
- Missing D and b
- Chocolate mixer / food paste
- Pump ambiguity
- Mechanical face seal hard out-of-scope
- ATEX / explosive environment out-of-scope
- Hydrogen out-of-scope
- Shaft groove / repair sleeve review
- No shaft disassembly / split-seal review topic
- Material mention safety
- Pressure boundary case

The golden runner validates analyze, confirmation decisions, evaluate, brief, Markdown export, PDF export, snapshots, revision diff, expected status/missing/review/computed/question behavior, forbidden language absence, and deterministic rerun behavior.

## Demo-Flow Readiness

Status: ready for guided internal demo.

Demo case:

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

Verified expected flow:

1. Paste inquiry.
2. Extracted fields appear with source spans.
3. User can confirm d1/D/b/speed/application where available.
4. User can mark pressure, temperature, and shaft condition as unknown where appropriate.
5. Backend generates Technical RWDR RFQ Brief.
6. Missing critical fields remain visible.
7. Circumferential speed is shown after confirmed d1 and rpm.
8. PDF and Markdown export use persisted backend brief.
9. Snapshot history exists.
10. Revision diff exists and is read-only.
11. Manufacturer matching is not rendered in the RWDR flow.

Recommended talk track:

```text
sealing | Intelligence gibt keine Dichtung frei. Es macht die Anfrage für Hersteller bewertbar.
```

## PDF / Markdown Readiness

Status: functionally ready for internal demo.

Markdown:

- Uses `Technical RWDR RFQ Brief` header.
- Includes case id, revision, export format, status, and German section titles.
- Includes source/evidence section and disclaimer.

PDF:

- Uses persisted brief payload.
- Includes required disclaimer.
- Includes RWDR section output and export/case metadata.
- No material/product/manufacturer recommendation was found in focused export tests.

Limitation:

- PDF is a simple text-layout renderer. Visual polish, pagination quality, typography, and long-section overflow deserve a dedicated pass before limited external demo.

## UX Readiness

Status: ready for internal demo.

Verified through focused frontend tests:

- Source-span confirmation cards render.
- Confirm/Edit/Unknown/Reject actions are covered.
- Missing critical fields and measurement hints render.
- Brief generation renders required backend sections.
- Snapshot history and revision diff are discoverable.
- RWDR flow does not render `ManufacturerFitPanel`.
- Forbidden RWDR customer-facing copy is guarded in focused tests.

Known UX limitation:

- Full browser/manual demo was not run in this audit; validation is test-based plus code/readiness inspection.

## Persistence / Recovery / Revision Readiness

Status: pass for focused RWDR tests.

Verified capabilities:

- Backend-owned case id is created during analyze.
- RWDR case-state is persisted in `CaseRecord.payload`.
- Confirmation decisions are persisted.
- Snapshots are append-only with monotonic revision numbers.
- Frontend stores only case id as pointer and recovers state from backend.
- Revision diff is read-only.
- Markdown/PDF export uses persisted brief content.
- Audit timestamps are excluded from deterministic evaluation/diff behavior.

## Forbidden-Language Triage

Command run:

```bash
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

Result: 455 hits.

Classification:

| Category | Classification | Examples | Action |
| --- | --- | --- | --- |
| A | Allowed disclaimer / explicit negation | RWDR disclaimer containing `keine finale technische Eignungsfreigabe`, `keine Materialfreigabe`, `keine Produktempfehlung` | Allowed |
| B | Tests, guards, fixtures, prompts, audit docs | `backend/tests/fixtures/rwdr_golden_cases.json`, `backend/tests/unit/services/test_rwdr_mvp_brief.py`, `frontend/src/lib/unsafeProductCopy.spec.ts`, audit reports 12-18, prompt guard rules | Allowed as safety tests/documentation |
| C | Legacy non-RWDR/internal surfaces | V8/V9 docs, manufacturer-fit service/tests, state/review internals using `approved`, knowledge data containing `suitable`, legacy content pages discussing not-final language | Not fixed in this RWDR readiness pass |
| D | RWDR customer-facing must-fix | None found in current RWDR MVP UI/export paths during this pass | No D fixes required |

Notes:

- `backend/app/services/rwdr_mvp_brief.py` contains forbidden terms as guard configuration and test assertions. That is expected.
- Historical concept docs intentionally contain examples of forbidden language and do not represent current RWDR customer-facing output.
- Legacy manufacturer-fit components remain in the repository, but focused RWDR UI tests verify they are not rendered in the RWDR flow.

## Dirty Worktree / Artifact Hygiene

Observed:

- `git status --short | wc -l`: 153 entries.
- AppleDouble files: 18 under `backend`, `frontend`, and `docs`.
- Logs: `backend/error.log`, `frontend/.next/dev/logs/next-development.log`.
- Generated artifacts: `frontend/.next`, `__pycache__`.

AppleDouble examples:

- `backend/app/agent/communication/._rfq_intent.py`
- `backend/app/agent/state/._projections.py`
- `frontend/src/components/dashboard/._CaseScreen.tsx`
- `frontend/src/app/api/bff/agent/chat/stream/._route.ts`

Action taken:

- No cleanup was performed in this pass to avoid deleting unrelated user/generated artifacts in a dirty worktree.

Recommendation:

- Before an external demo branch, remove AppleDouble files and generated artifacts in a dedicated hygiene commit. The AppleDouble files currently break architecture tests because they are binary files matched as Python source.

## Commands Run

Discovery:

```bash
pwd
git status --short
git branch --show-current
find backend frontend docs/product/sealing-intelligence docs/audits/sealingai-engine -maxdepth 4 -type f | sort | rg "rwdr|rfq|case_state|pdf|golden|forbidden|demo|report" | sed -n '1,220p'
find backend frontend docs -name '._*' -type f | sed -n '1,120p'
find backend frontend docs -name '*.log' -o -name '.DS_Store' | sed -n '1,120p'
git status --short | wc -l
find backend frontend docs -name '._*' -type f | wc -l
```

Focused tests:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py
npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
git diff --check
```

Broad tests:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests backend/tests
npm --prefix frontend run test:run
```

Forbidden-language search:

```bash
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

## Test Results

Focused RWDR golden cases:

```text
13 passed
```

Focused backend RWDR/RFQ tests:

```text
86 passed
1 warning: HTTP_422_UNPROCESSABLE_ENTITY deprecation in test_rfq_endpoint.py
```

Focused frontend tests:

```text
3 files passed
16 tests passed
```

`git diff --check`:

```text
passed
```

Broad backend command `PYTHONPATH=backend .venv/bin/python -m pytest -q backend`:

```text
failed during collection
```

Reason:

- `backend/scripts/test_audit_logger.py` performs a live request to `http://localhost:8000/api/v1/agent/chat/stream`, receives `404`, and calls `sys.exit(1)` at import time.

Classification:

- Unrelated to RWDR MVP readiness.
- Broad-suite hygiene blocker.

Broad backend command `PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/agent/tests backend/tests`:

```text
failed: 13 failures
```

Failure groups:

- V10 graph/runtime/composer expectation drift.
- V92 engineering node expectation drift.
- Architecture guardrail tests failing on AppleDouble binary `._*.py` artifacts.
- Async DB stub warnings in non-RWDR governed runtime tests.

Classification:

- Not caused by the RWDR MVP focused paths in this pass.
- Must be resolved before broader release confidence.

Broad frontend command `npm --prefix frontend run test:run`:

```text
26 files passed
1 file failed
137 tests passed
2 tests failed
```

Failure group:

- `src/components/dashboard/CaseScreen.test.tsx` expects tab names `Berechnung` and `Anfragebasis`; rendered dashboard tabs currently expose `Übersicht`, `Parameter`, `Medium`, `Anwendung`, `Werkstoff`, `Briefing`.

Classification:

- Unrelated to RWDR flow focused tests.
- Dashboard broad-test expectation drift.

## Files Changed In This Readiness Pass

- `backend/app/api/v1/renderers/rfq_pdf.py`
- `docs/audits/sealingai-engine/19_rwdr_mvp_readiness_report.md`

## Recommended Demo Audience

Recommended for:

- Internal product/engineering review.
- Internal technical sales enablement.
- Selected application engineers.
- Selected manufacturer/distributor reviewers in a guided session with clear disclaimer framing.

Not yet recommended for:

- Unguided external self-serve users.
- Public launch.
- Any workflow implying manufacturer selection, product selection, or technical approval.

## Recommended Demo Setup

Use the manual demo flow from `docs/product/sealing-intelligence/rwdr_demo_script.md`.

Avoid seed endpoints unless a safe environment-gating convention is established.

Before a demo branch:

1. Start from a clean branch or isolate RWDR changes.
2. Remove generated `.next`, `__pycache__`, log, and AppleDouble artifacts.
3. Re-run focused RWDR tests.
4. Re-run broad frontend/backend tests or document accepted broad-test failures.
5. Generate one sample PDF and visually inspect it.

## Next Recommended Patch

Patch 20 should be a release hygiene and demo packaging patch:

1. Remove AppleDouble and generated artifacts in a dedicated cleanup.
2. Fix broad backend collection by moving `backend/scripts/test_audit_logger.py` out of pytest discovery or guarding its executable code.
3. Resolve or quarantine with explicit owner the non-RWDR broad backend failures.
4. Update `CaseScreen.test.tsx` broad frontend expectations or restore expected dashboard tab labels intentionally.
5. Add a lightweight PDF visual/readability fixture test or snapshot extraction check.
6. Produce a clean demo branch with only RWDR MVP changes and reports.
