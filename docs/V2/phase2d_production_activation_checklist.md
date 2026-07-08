# Phase 2D — Production Activation Checklist

Controlled activation of the `smalltalk_navigation` compact-prompt routing (Phase 2D, PR #185 /
`440d61ac`). The implementation is **merged to `main` and deployed to production inert**; this checklist
governs the eventual runtime flip. Production activation is currently **NO-GO** — see gates below. Companion
record: `docs/ops/GOVERNANCE_LOG.md` entry `2026-07-08T12:49:42Z`.

## Current flags

| Environment | `route_optimization_enabled` | `route_prompt_families_enabled` | Source |
| --- | --- | --- | --- |
| **Production** (`backend-v2`) | `False` | `False` | code defaults (`backend/sealai_v2/config/settings.py` L168 / L179); both keys **absent from `.env.prod`** and unset in the container env |
| **Staging** (`backend-v2-staging`) | `True` | `True` | env `SEALAI_V2_ROUTE_OPTIMIZATION_ENABLED=true` / `SEALAI_V2_ROUTE_PROMPT_FAMILIES_ENABLED=true`, from unmerged branch `origin/feat/v2-staging-deploy-script-and-activation` (tip `1d20112d`) |

Env key names: `SEALAI_V2_ROUTE_OPTIMIZATION_ENABLED`, `SEALAI_V2_ROUTE_PROMPT_FAMILIES_ENABLED`.

When both are OFF, `Pipeline.run()` is byte-identical to pre-Phase-2D behavior (the compact smalltalk
generator is never constructed). When both are ON, the compact `smalltalk_navigation.jinja` prompt + cheap
helper-tier model answer a turn **only** when: route == `smalltalk_navigation`, `forced_full_pipeline` is
False, and `deterministic_signal_count` is 0. Every other route is unaffected.

## Required owner approvals (all must clear or be explicitly owner-deferred)

- [ ] LangSmith API-key rotation, or explicit owner deferral.
- [ ] Old LangSmith trace review / deletion / retention decision, or explicit owner deferral.
- [ ] LangSmith project-split decision, or explicit owner deferral.
- [ ] Named owner approval for production activation — must **name the action** (flip both flags True in
      `.env.prod` + recreate `backend-v2`), per `.claude/rules/workflow.md` HALT-gate convention.

## Required smoke / eval checks

- [ ] Owner-run authenticated smoke test (health internal + public; a real authed smalltalk turn).
- [ ] Targeted smalltalk eval / replay (adjudicated) covering the `smalltalk_navigation` compact path.
- [ ] Staging result review (`backend-v2-staging`, both flags already ON) signed off before the prod flip.

## Doctrine invariants (must remain true after activation)

No LangGraph · no knowledge-route L3 bypass · no material-route L3 bypass · no unverified engineering
streaming · `general_sealing_knowledge` L3=True · `material_knowledge` L3=True · `material_comparison`
L3=True · only `smalltalk_navigation` is eligible for the compact prompt path.

## Rollback plan

Rollback uses the existing mechanism in `ops/release-backend-v2.sh` — no new mechanism is introduced:

1. Before each recreate, the script reads the **currently running** `backend-v2` image from the Docker
   daemon (`docker inspect … --format '{{.Image}}'`) and tags it as a rollback rung
   `sealai-backend-v2:rollback-pre-<label>-<UTC-timestamp>`.
2. On smoke RED it **HALTs, writes no ledger line**, and prints the rollback path:
   `docker tag <rollback-rung> sealai-backend-v2:latest && docker compose … up -d --no-deps
   --force-recreate backend-v2`.
3. Because activation is a **flag-only** change (no image rebuild is required — the code already ships),
   the fastest rollback is to remove/`=false` the two env keys in `.env.prod` and recreate `backend-v2`
   (see Deactivation below); the tagged rollback rung remains available if an image-level revert is needed.

## Metrics to observe post-activation

Grounded in the telemetry fields that actually exist:
`backend/sealai_v2/pipeline/route_telemetry.py` (`RouteTelemetry`) and
`backend/sealai_v2/llm/telemetry.py` (`LlmCallTelemetry`).

- **Route telemetry distribution** — counts of `RouteTelemetry.route_name` (watch the
  `smalltalk_navigation` share vs the full-pipeline routes); the log-only sink is active only when
  `route_optimization_enabled=True`.
- **L3-bypass rate for smalltalk** — `RouteTelemetry.l3_bypassed=True` for
  `route_name=smalltalk_navigation` / `prompt_family=smalltalk_navigation`. Must stay confined to
  smalltalk; any L3 bypass on a knowledge/material route is a doctrine violation → halt + rollback.
- **cache_ratio** — `LlmCallTelemetry.cache_ratio` (with `cached_tokens`) for the helper-tier smalltalk
  call; confirms prompt-cache effectiveness of the static compact prompt.
- **Error rate** — `LlmCallTelemetry.status` / `error_type` and `route_latency_ms` /
  `LlmCallTelemetry.latency_ms`; watch for regressions vs the inert baseline.

## Activation command (placeholder — no real secrets)

```sh
# On the VPS, repo root /home/thorsten/sealai, after ALL gates above clear.
# Add/flip both keys in the gitignored .env.prod:
SEALAI_V2_ROUTE_OPTIMIZATION_ENABLED=<true>
SEALAI_V2_ROUTE_PROMPT_FAMILIES_ENABLED=<true>
# Then recreate ONLY backend-v2 via the sanctioned script (rollback rung auto-tagged, smoke-gated):
./ops/release-backend-v2.sh
# (no image rebuild needed for a flag-only flip; the script recreates backend-v2 with the new env)
```

## Deactivation command (placeholder)

```sh
# Flip both keys back OFF (or remove them → code defaults are False):
SEALAI_V2_ROUTE_OPTIMIZATION_ENABLED=<false>
SEALAI_V2_ROUTE_PROMPT_FAMILIES_ENABLED=<false>
# Recreate backend-v2 to return to the inert (byte-identical) baseline:
./ops/release-backend-v2.sh
```
