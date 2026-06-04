# RWDR MVP Implementation Report

Date: 2026-05-26

## Scope

Implemented the first strict RWDR MVP boundary on top of the existing RFQ
preview service. The change does not replace the governed runtime and does not
add external dispatch, manufacturer routing, or recommendation logic.

## Implemented

- Added `backend/app/services/rwdr_mvp_brief.py`.
- Added canonical code-level objects:
  - `CanonicalRWDRCase`
  - `EvidenceField`
  - `RWDREvaluation`
  - `TechnicalRWDRRFQBrief`
  - `EvidenceConfirmationIntelligence`
  - `RWDRCaseOrchestrator`
- Embedded `technical_rwdr_rfq_brief` into the existing RFQ preview payload.
- Included the exact RWDR MVP brief in the allowlisted RFQ export contract and
  deterministic PDF renderer.
- Extended the frontend RFQ panel so the exact `Technical RWDR RFQ Brief`
  artifact is displayed as the primary RWDR MVP output.
- Added exact MVP statuses:
  - `COMPLETE`
  - `NEEDS_CLARIFICATION`
  - `OUT_OF_SCOPE`
- Added a deterministic evidence gate:
  - candidate, inferred, conflicting, missing, stale, unknown,
    unvalidated, and confirmation-required liability fields are blocked from
    confirmed brief facts.
  - deterministic calculations are separated from case facts.
  - manufacturer matching is explicitly disabled in the RWDR MVP brief.
- Updated `AGENTS.md` with the active RWDR MVP boundary.
- Added focused tests in
  `backend/tests/unit/services/test_rwdr_mvp_brief.py`.

## Product Boundary

The artifact title is exactly `Technical RWDR RFQ Brief`.

The artifact is a manufacturer-evaluation basis only. It is not:

- a final engineering release,
- a material or product recommendation,
- a manufacturer marketplace,
- a routing or shortlist mechanism,
- an automatic dispatch system,
- a compliance statement.

## Remaining Hardening

- Persist a richer source-span model for structured UI confirmations and
  extracted chat spans.
- Add end-to-end browser coverage from conversation intake to generated PDF.
- Remove untracked AppleDouble files from the worktree after explicit cleanup
  approval.
