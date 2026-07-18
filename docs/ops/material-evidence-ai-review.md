# MAT-EVID-AI-REVIEW.v1 automation runbook

Status: non-production only. This runbook creates no human review, approval,
active pointer, sampling, public output or deployment authority.

## Preconditions

1. Work only in `development`, `test` or an explicitly authorized isolated
   `dark_staging` environment.
2. Verify the exact MAT-GOV-03A ruleset, MAT-EVID-01A.v2 `material_relation`
   snapshot, and one exact MAT-EVID-01A.v2 `media_identity` snapshot for every
   referenced canonical media ID, including all IDs, hashes and assertion refs.
3. Verify each atomic rule is disqualify-only: `unvertraeglich` or opaque
   `bedingt`, one material, one canonical media ID and one condition.
4. Verify every claim is derived from actual source content, not model memory,
   and is byte-identical to its primary rule statement.
5. Verify document/revision/edition/content digest, exact locator, rights state,
   bounded permitted excerpt, application/seal/temperature scope, conditions,
   exclusions and conflict references.
6. Verify every media identity is derived from its explicit canonical name and
   identity kind, carries only source-derived claims, and is not serialized as
   a verified MED-NORM catalog entry or human Evidence review.
7. Stop on missing or unclear locator, absent permitted excerpt,
   unknown/restricted rights, scope drift,
   unresolved conflict, hash drift, foreign reference or production target.
8. For safety-critical, hard-gate, temperature or family-wide scope, prefer two
   independent primary sources. A family-wide single-source claim is always
   blocked. Other high-risk single-source claims must be narrowly scoped,
   opaque `bedingt`, or quarantined.

## Creator step

- Codex creates new immutable ruleset and Evidence v2 snapshots from the
  verified source record; it does not import existing matrix prose.
- Record creator provider/model/version/prompt/run/input/output hashes.
- Build `AIReviewPayloadV1`, validate it against the exact ruleset, material
  Evidence and all media-identity Evidence snapshots,
  and persist the immutable `ai_draft` snapshot.
- Never populate a verified-human subject field and never use a human lifecycle
  state.

## Frozen challenge corpus

Build the corpus only with the contract helper. Confirm it contains exact
claims, rules, scopes, allowed source metadata/excerpts, source and artifact
digests, conflict references, rights, expected disqualifying effect, and the
ratified invariants. Confirm it contains no tenant/customer identity, Codex
reasoning, preapproval, secret, `.env` value, application prompt or protected
full text.

Hash the canonical corpus before execution. A changed byte creates a different
input hash and invalidates any previous challenge receipt.

## One-shot Claude challenge

Use only the authenticated local Claude CLI through
`run_claude_challenge`. The runner enforces exact model `claude-sonnet-5`, no
tools, MCP, hooks, Chrome, web or session persistence; it removes secret-bearing
environment variables and writes only to a newly created private directory
outside the repository. It does not retry.

Accept the transport only when the process returns zero, the envelope is a
complete result, model usage includes `claude-sonnet-5`, permission denials are
empty, and the closed report binds the exact review snapshot/hash and every
claim. The persisted result has its session ID redacted; only a one-way run hash
enters provenance.

A timeout, transport error, invalid JSON, wrong model, permission denial,
incomplete report or hash mismatch is `REVIEW_INCOMPLETE`, not PASS. Do not
silently repair or retry; create a new owner-visible execution decision.

## Codex adjudication

- Cover every Claude finding object-exactly.
- CRITICAL/HIGH/MEDIUM: quarantine or create a new immutable ruleset/evidence
  pair and/or exact media-identity Evidence snapshot. A factual change requires
  a new AI review snapshot and a new Claude corpus/run; never reuse the old
  PASS.
- LOW: accept as nonblocking only if it has no factual, scope, source, rights,
  hash or governance effect.
- `QUARANTINE` is fail-closed. `REVOKED` is terminal.
- Mark `ai_cross_reviewed_non_authoritative` only after Claude PASS, complete
  claim coverage, no open CRITICAL/HIGH/MEDIUM finding, unchanged facts and
  valid rights/scope/hash/source bindings.

## Postconditions and evidence

Record batch, review snapshot, challenge, adjudication, validation, lifecycle
and audit hashes. Reload all referenced snapshots and replay the hash-chained
lifecycle. Confirm tenant/environment isolation, no mutable table, no human
subject or human-review state, and `positive_statement_allowed=false` at every
layer.

Confirm separately that all material flags remain false, shadow sampling is
zero, no active pointer exists, no public API/frontend payload changed, no
production migration ran and no deployment occurred.

## RP-001 boundary

Candidate selection must start from the gap inventory, but a gap is not a
claim. Research each source independently and preserve its rights and content
digest. The first pack may contain only successfully cross-reviewed
`unvertraeglich` or opaque `bedingt` snapshots. Candidates that cannot satisfy
the contract remain explicit gaps or quarantined. MAT-GOV-03C and dark staging
remain separate owner-gated work.
