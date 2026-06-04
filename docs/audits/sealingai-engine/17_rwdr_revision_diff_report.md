# RWDR Revision Diff Report

Date: 2026-05-27

## Scope

This patch adds a read-only RWDR revision diff for persisted `case_state_snapshots`.

The feature compares two RWDR revisions and does not mutate cases, snapshots, EvidenceFields, confirmations, briefs, or exports.

Product boundaries remain unchanged:

- No manufacturer marketplace.
- No manufacturer routing.
- No paid listings.
- No material/product/manufacturer recommendation.
- No final technical release language.
- No weakening of the backend Evidence Gate.

## Files changed

- `backend/app/services/rwdr_mvp_brief.py`
  - Adds DB-backed snapshot diff retrieval.
  - Adds deterministic diff helpers for EvidenceFields, missing fields, computed values, review flags, questions, measurements, brief sections, and export metadata.
  - Excludes audit metadata from deterministic comparison.

- `backend/app/api/v1/endpoints/rfq.py`
  - Adds `GET /api/v1/rfq/rwdr/cases/{case_id}/diff/{from_revision}/{to_revision}`.

- `backend/app/api/tests/test_rfq_endpoint.py`
  - Adds endpoint-level tests for same revision, confirmation changes, edits, explicitly unknown fields, rejected fields, computed values, export diffs, and missing revision/case handling.

- `frontend/src/lib/bff/workspace.ts`
  - Adds BFF and backend path builders for RWDR revision diff.

- `frontend/src/app/api/bff/rfq/rwdr/cases/[caseId]/diff/[fromRevision]/[toRevision]/route.ts`
  - Adds BFF proxy for the backend diff endpoint.

- `frontend/src/components/dashboard/RfqPane.tsx`
  - Extends the compact revision list with revision selectors and a read-only comparison panel.

- `frontend/src/components/dashboard/RfqPane.test.tsx`
  - Adds assertions for diff endpoint calls and rendered diff categories.

## Diff algorithm

The backend diff compares `case_state_snapshots.state_json.deterministic_payload_json` where available, falling back to `snapshot_payload`.

Audit-only fields are stripped before deterministic comparison:

- `created_at`
- `updated_at`
- `trace_id`
- `request_id`
- `user_action_timestamp`

EvidenceFields are keyed by `field` and compared on:

- `value`
- `unit`
- `origin`
- `source_type`
- `source_span`
- `confirmation_status`
- `liability_bearing`
- `allowed_in_brief`
- `previous_value`

List-like sections are compared with stable JSON keys and deterministic sorting.

If `from_revision == to_revision`, the endpoint returns an empty deterministic diff while still exposing audit metadata.

The implementation preserves requested direction. `from_revision > to_revision` is supported as a reverse comparison instead of being normalized.

## Supported diff categories

- `added`
- `removed`
- `changed`
- `confirmation_status_changed`
- `value_changed`
- `source_span_changed`
- `allowed_in_brief_changed`
- `liability_bearing_changed`
- `section_added`
- `section_removed`
- `section_changed`

Compared areas:

- EvidenceFields
- evaluation status
- missing critical fields
- missing helpful fields
- computed values
- review flags
- manufacturer questions
- measurement recommendations
- source evidence summary
- Technical RWDR RFQ Brief section presence/metadata
- Markdown/PDF export metadata

## API contract

Added:

```http
GET /api/v1/rfq/rwdr/cases/{case_id}/diff/{from_revision}/{to_revision}
```

Returns:

- `case_id`
- `from_revision`
- `to_revision`
- `from_event_type`
- `to_event_type`
- `summary`
- `status_diff`
- `evidence_field_diffs`
- `missing_critical_fields_diff`
- `missing_helpful_fields_diff`
- `computed_values_diff`
- `review_flags_diff`
- `manufacturer_questions_diff`
- `measurement_recommendations_diff`
- `source_evidence_summary_diff`
- `brief_diff`
- `export_diff`
- `audit_metadata`

Safe 404s are returned for missing case IDs or missing revisions.

## Frontend behavior

The RWDR pane now shows:

- `Versionsvergleich`
- two revision selectors
- `Revisionen vergleichen`
- read-only label
- changed EvidenceFields
- critical missing-field additions/removals
- computed-value additions/changes/removals
- review-topic additions/removals
- manufacturer-question additions/removals
- export metadata changes

The UI calls the BFF endpoint:

```text
/api/bff/rfq/rwdr/cases/{case_id}/diff/{from_revision}/{to_revision}
```

The panel is explicitly read-only and does not change persisted state.

## Tests added or updated

Backend:

- Same revision returns empty deterministic diff.
- Missing case and missing revision return safe 404.
- Confirmation changes are reported.
- Edited values include changed value and `previous_value`.
- Explicit unknown fields are reported.
- Rejected fields are reported.
- Removed missing critical fields are reported.
- Added `circumferential_speed_mps` is reported.
- Export revision reports PDF export metadata change.
- Audit timestamp drift is excluded from deterministic diff.

Frontend:

- Revision list renders after restore.
- Compare button calls the diff endpoint.
- Confirmation-status change renders.
- Missing critical diff renders.
- Computed values diff renders.
- Export metadata diff renders.
- RWDR flow still does not render partner/matching UI.

## Commands run

```bash
pwd
git status --short
git branch --show-current
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/app/api/tests/test_rfq_endpoint.py
npm --prefix frontend run test:run -- src/components/dashboard/RfqPane.test.tsx src/components/dashboard/ManufacturerFitPanel.test.tsx src/lib/unsafeProductCopy.spec.ts
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/unit/services/test_rwdr_mvp_brief.py backend/tests/unit/services/test_rfq_preview_service.py backend/app/api/tests/test_rfq_endpoint.py
PYTHONPATH=backend .venv/bin/python -m py_compile backend/app/services/rwdr_mvp_brief.py backend/app/api/v1/endpoints/rfq.py backend/app/api/v1/renderers/rfq_pdf.py
git diff --check
rg -n "freigegeben|geeignete Dichtung|passende Partnerprofile|Warum passend|recommended material|recommended product|suitable|approved|certified|final solution|best manufacturer" backend frontend docs
```

## Test results

Green:

- `backend/app/api/tests/test_rfq_endpoint.py`: 14 passed
- Focused backend RWDR/RFQ suite: 73 passed
- Focused frontend suite: 16 passed
- Python compile check: passed
- `git diff --check`: passed

Known warning:

- Existing deprecation warning for `HTTP_422_UNPROCESSABLE_ENTITY` in the RWDR confirmation validation test. It is unrelated to revision diff behavior.

Forbidden-language search:

- 408 hits.
- Classified as tests/guards/prompts, legacy architecture docs, knowledge data, historical reports, legacy non-RWDR surfaces, and negating/disclaimer contexts.
- No new RWDR revision-diff customer-facing surface introduces manufacturer matching, material/product recommendation, or final-release wording.

## Known limitations

- Brief comparison is section-level metadata only, not a line-level Markdown diff.
- Export diff tracks export-reference/metadata changes, not binary PDF byte-level differences.
- EvidenceField history remains JSON-snapshot-based rather than relational.
- Reverse comparisons are directional but not visually labeled as reverse beyond revision numbers.

## Next recommended patch

Add a focused line-level Markdown diff for persisted `markdown_export_content`, still read-only and still excluding audit metadata from deterministic comparisons.
