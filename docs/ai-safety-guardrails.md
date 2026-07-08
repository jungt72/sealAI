# AI Safety Guardrails: Regulated/Safety-Critical Application Detection

## Doctrine

A question that touches a regulated or safety-critical domain (ATEX, food/pharma contact, pressure
equipment, hydrogen, ...) does **not** get hard-blocked — sealingAI still answers, but the turn is
marked for restriction/review across every surface, and the response stays strictly informational
(no suitability/approval language). See `core/legal_doctrine.py`'s `RISK_TRIGGER_TERMS` for the full
term list (owner-specified).

## Why detection is deterministic, not LLM-based

`safety/risk_flags.py::detect_risk_flags()` is a plain word-boundary regex match over the user's
question text — no LLM call, no randomness, cannot be "talked out of" by a model. This is the
**primary** guarantee: it is always on (`PipelineResult.risk_flags` is populated on every turn,
never flag-gated) and its correctness doesn't depend on an LLM reliably self-policing.

An **optional, secondary** layer reinforces this at the L1-prompt level
(`SEALAI_V2_RISK_FLAG_PROMPT_ENABLED`, default OFF): when a turn's `risk_flags` is non-empty AND
this flag is on, `system_l1.jinja`'s `{% if risk_flags %}` block adds an explicit instruction to
stay informational-only. Off by default because it's unverified against the eval suite; the primary
(deterministic) guarantee holds regardless of this flag's state.

## What was deliberately NOT built

An earlier design considered adding a `risk_flag_violation` finding type to the L3 verifier's JSON
trap-schema (checking whether L1's draft used approval language despite a risk flag). This was
**rejected**: the L3 trap-catalog is the most heavily-audited, most regression-sensitive part of
this codebase (see the 2026-07-07 LangGraph-audit session's L3 over-flagging incident), and adding a
new finding type risks the exact kind of eval regression that incident already caused once. The
deterministic detection + always-visible badge is a stronger guarantee than trying to get an LLM
(L1 or L3) to reliably self-police, without touching that fragile machinery at all.

## Where the signal surfaces

- `PipelineResult.risk_flags` → `chat_response()`'s `"risk_flags"` field (always present, `[]` when
  no match).
- `RenderSnapshot.risk_flags` → `Artifact.risk_flags` → the `/briefing` and `/anfrage` responses'
  `"risk_flags"` field (same signal, briefing/RFQ-preview surface).
- Frontend: `Answer.tsx`'s `RiskFlagsNote` — an unmissable badge rendered OUTSIDE the collapsed
  answer-meta `<details>` (same placement discipline as the existing Gegencheck note — must not
  require a click to see).
- PDF export: `lib/pdf.ts` shows the identical warning text (`RISK_WARNING_TEXT`, kept in sync
  between backend `safety/risk_flags.py` and frontend `lib/safety/riskFlags.ts` by convention, not a
  runtime fetch — it's static doctrine text, not request-dependent).

## Tests

`backend/sealai_v2/tests/test_risk_flags.py` (pure detection), `test_pipeline_risk_flags.py`
(always-on result field vs. flag-gated prompt injection), `test_api_risk_flags.py` (chat/briefing/
anfrage responses). Frontend: `Answer.test.tsx`'s risk-flags-note block, `lib/pdf.test.ts`'s
Legal-by-Design block, `lib/safety/riskFlags.test.ts`.
