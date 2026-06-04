# RWDR Golden Cases & Demo Hardening Report

Date: 2026-05-27

## Scope

This patch adds a golden-case validation layer and demo documentation for the RWDR MVP.

The validated workflow remains:

1. analyze
2. user confirmation decisions
3. evaluate
4. generate `Technical RWDR RFQ Brief`
5. Markdown export
6. PDF export
7. snapshots
8. revision diff

No manufacturer marketplace, routing, paid listings, material recommendation, product recommendation, manufacturer recommendation, or final suitability language was added.

## Files changed

- `backend/tests/fixtures/rwdr_golden_cases.json`
  - Adds 12 realistic RWDR golden cases.

- `backend/app/api/tests/test_rwdr_golden_cases.py`
  - Adds end-to-end golden runner through the backend RWDR API functions.
  - Asserts status, missing fields, review flags, computed values, manufacturer questions, sections, exports, snapshots, deterministic repeatability, and revision diff.

- `backend/app/services/rwdr_mvp_brief.py`
  - Improves Markdown export metadata and section titles.
  - Keeps German customer-facing section labels in Markdown/PDF RWDR sections.

- `docs/product/sealing-intelligence/rwdr_demo_script.md`
  - Adds the MVP demo script and talk track.

- `docs/product/sealing-intelligence/rwdr_golden_cases.md`
  - Documents all golden cases and expected behavior.

- `docs/audits/sealingai-engine/18_rwdr_golden_cases_demo_hardening_report.md`
  - This report.

## Golden cases added

1. `simple_gearbox_replacement`
2. `complete_gearbox_case`
3. `missing_housing_bore_and_width`
4. `chocolate_mixer_food_paste`
5. `pump_ambiguity`
6. `mechanical_face_seal_oos`
7. `atex_oos`
8. `hydrogen_oos`
9. `shaft_groove_review`
10. `no_shaft_disassembly_split_review`
11. `material_mention_safety`
12. `pressure_boundary_case`

Each fixture includes:

- raw inquiry text
- expected extracted candidate fields
- confirmation decisions
- expected status
- expected missing critical fields
- expected review flags
- expected computed values
- expected manufacturer-question signals
- expected brief sections
- forbidden phrases

## Demo flow

The documented demo case is:

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

Demo steps:

1. Paste inquiry.
2. Review extracted fields with source spans.
3. Confirm dimensions, speed, application, medium, and sealing function.
4. Leave pressure, temperature, and shaft condition open or explicitly unknown.
5. Generate `Technical RWDR RFQ Brief`.
6. Show missing critical fields.
7. Show circumferential speed around `3.53 m/s`.
8. Export Markdown/PDF.
9. Show snapshot history.
10. Show revision diff.

Talk track:

```text
sealing | Intelligence gibt keine Dichtung frei. Es macht die Anfrage für Hersteller bewertbar.
```

## PDF/Markdown improvements

Markdown export now includes:

- `Technical RWDR RFQ Brief`
- Case-ID
- revision metadata where available
- export format
- status
- German section labels:
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

PDF export receives the same German RWDR section labels through the existing PDF renderer payload.

## Tests added

`backend/app/api/tests/test_rwdr_golden_cases.py` adds:

- 12 golden end-to-end cases.
- analyze → confirm → evaluate → brief → Markdown export → PDF export.
- snapshot creation assertions.
- expected status/missing/review/computed/question assertions.
- required section assertions.
- forbidden phrase assertions.
- deterministic repeat generation assertions.
- demo-case revision diff assertion for confirmation and computed-value changes.

Frontend focused tests were re-run to ensure no regression in:

- source-span confirmation UX
- PDF link visibility
- snapshot history
- revision diff rendering
- hidden manufacturer matching in RWDR flow

## Commands run

```bash
pwd
git status --short
git branch --show-current
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rwdr_golden_cases.py
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py backend/app/api/tests/test_rwdr_golden_cases.py
npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/services/rwdr_mvp_brief.py backend/app/api/v1/endpoints/rfq.py backend/app/api/v1/renderers/rfq_pdf.py backend/app/api/tests/test_rwdr_golden_cases.py
git diff --check
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer|empfohlenes Material|empfohlenes Produkt|geeignete Lösung|passende Lösung" backend frontend docs
```

## Test results

Green:

- RWDR golden cases: 13 passed
- Focused backend RWDR/RFQ/API/golden suite: 86 passed
- Focused frontend suite: 16 passed
- Python compile check: passed
- `git diff --check`: passed

Known warning:

- Existing `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning in the RWDR confirmation validation test. It is unrelated to golden-case behavior.

## Known limitations

- Golden tests use a fake async session and existing DB repository behavior, not a real database container.
- PDF content is validated through generated bytes and renderer path, not visual pixel comparison.
- The complete gearbox case requires explicit confirmation/editing for `seal_family` and `motion` because the MVP confirmation gate treats them as required/open fields.
- Broad forbidden-language search remains noisy due to legacy docs, tests, guards, prompt examples, and knowledge data.
- Forbidden-language search returned 455 hits. The new hits are fixture/documentation forbidden-phrase assertions or this report; remaining hits classify as existing tests/guards/prompts, legacy docs, knowledge data, or non-RWDR legacy surfaces.

## Next recommended patch

Add a compact demo seed endpoint or dev-only fixture loader if the project has a safe environment gate. Without safe env gating, keep the demo as documented manual flow plus golden tests.
