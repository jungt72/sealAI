# Semantic Router v1

## Decision

Signal-free natural-language turns that the deterministic production router cannot classify may be
sent to a bounded semantic classifier. Deterministic engineering, risk, injection and case-state
guards remain authoritative. The classifier never answers a user question, retrieves knowledge,
executes tools, changes case state or approves technical content.

LangGraph is not part of this path. This is one typed classification call inside the existing
synchronous pipeline and deterministic execution policy.

## Runtime contract

- Feature flag: `SEALAI_V2_SEMANTIC_ROUTER_ENABLED` (default `false`).
- Provider/model: `mistral/ministral-8b-2512`.
- Temperature: `0.0`; maximum output: `96` tokens; timeout: `4.0` seconds.
- Provider output: strict JSON Schema plus local Pydantic validation.
- Minimum confidence: `0.9`.
- Input: current user message and one boolean (`ACTIVE_CASE`); no transcript, retrieved document,
  user identity or tenant data.
- Failure behavior: timeout, provider failure, invalid schema, low confidence or an inconsistent
  smalltalk classification preserves the existing deterministic fallback decision.
- Smalltalk is accepted only when the speech act is social, the turn is not case-bound and the
  classifier states that no technical request is present.
- Engineering, leakage, material-comparison, RFQ and unsupported routes remain full-pipeline routes.
- `SEALAI_V2_EXECUTION_POLICY_ENABLED=true` deaktiviert derzeit die understand()-Stufe (Guard:
  pipeline.py:1006) — die dort produzierte Intent-Klassifikation (wissensfrage/fallarbeit/
  faktfrage/gespraech/unklar) fließt in diesem Fall nicht in die Routing-Entscheidung ein; der
  Semantic Router (dieses Dokument) ist der einzige LLM-Beteiligte an der Turn-Routing-Entscheidung.

The model role and all behavior-affecting controls are included in the canonical runtime-profile
hash used by the release gate.

## Model selection evidence

On 2026-07-15, both candidate IDs were verified against the configured production Mistral account.
`ministral-3b-2512` accepted the schema but incorrectly classified the regional greeting `Moin` as
`unsupported_or_ambiguous` with confidence `0.0`. `ministral-8b-2512` classified the same bounded
probe as `smalltalk_navigation` with confidence `0.95`. The failed 3B candidate is therefore not
eligible for activation.

This probe establishes API/schema compatibility and the motivating regression only. It is not a
general factual or engineering eval and does not authorize weakening any technical guard.

## Rollback

Set `SEALAI_V2_SEMANTIC_ROUTER_ENABLED=false` and recreate `backend-v2`. No schema migration or
stored-state rollback is required; the previous deterministic behavior is preserved in code.
