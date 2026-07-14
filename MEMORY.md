# sealingAI Working Memory

## VPS / Deploy

- Production deploy work happens on the VPS repo at `/home/thorsten/sealai`.
- For V2 backend changes, use the sanctioned wrapper `ops/release-backend-v2.sh`; do not deploy `backend-v2` with raw docker compose commands.
- Before staging on the VPS, inspect `git status --short`; pre-existing operator/deploy artifacts such as `frontend-cockpit-deploy/` are not source changes.

## Prompt SSoT

- Active V2 prompt templates live in `backend/sealai_v2/prompts/*.jinja` and render templates in `backend/sealai_v2/render/templates/*.jinja`.
- Structured helper prompts (`distill`, `understand`, `fachkarte_extract`, `medium_research`, `verifier_l3`) are optimized for Mistral-style structured output: valid JSON object only, no prose, no Markdown/code fences, no trailing commas, explicit empty/null behavior.
- `understand.jinja` remains annotate-only. Optional `archetype`, `suggested_seal_type`, and `medium_hint` are server-side validated/sanitized after the LLM call and must not become routing authority.
- `verifier_l3.jinja` must not contain pseudo-JSON literals like `true|false` or `clean|violation`; clean output is exactly `{"findings":[],"verdict":"clean"}`.

## Jinja Safety

- Keep the top block of `system_l1.jinja` as a real Jinja comment starting with `{#` and ending with `#}`. If the opener is changed to plain `#`, the explanatory text containing `{% if not contract %}` is parsed as a live Jinja block and crashes at runtime.

## Last V2 Prompt Deploy

- 2026-07-05T16:18:58Z: commit `38426f31` deployed on VPS via `ops/release-backend-v2.sh` as `backend-v2` image `sha256:b979d48b5d91104c8b9233c29530f6f81cd9f3b7543b4209d2304a6217a9cbbe`; tree hash `00d0e9d30f3cd57ca7bd7a41e9b4cb5af396a719`; L1 `mistral/mistral-small-2603`; rollback image `sha256:629ab93c8ede8c0f979c18e2d2e1ef4d8a0068d95bf896cb71818c57d6d054cd`.
- This deploy fixed the `system_l1.jinja` top-comment Jinja crash and shipped the structured helper/verifier prompt hardening. Eval gate was temporarily disabled by owner policy; wrapper smoke and live prompt checks passed.


## Dashboard Cockpit / Right Rail

- 2026-07-14: The active dashboard SSoT is `frontend-v2/`; production Nginx serves only the verified immutable `frontend-v2/dashboard-releases/current` target. Normal builds remain inert under `.build/dashboard-candidate`, and only GATE-08 may change `current`. The cockpit is built in `frontend-v2/src/components/ChatPane.tsx`; do not patch old scratch templates or `frontend-cockpit-deploy/`.
- The cockpit Right Rail is an orientation surface, not a raw compute/debug panel: show solution direction, next step, missing human-readable inputs, computed values, one critical point, medium, and RFQ readiness. Do not expose internal keys such as `d1_mm`, `rpm`, `p_bar`, or `v_m_s` in the UI.
- `/api/v2/compute` is case-aware via optional `case_id`; frontend `ApiClient.compute(caseId)` must pass the active case so the Right Rail uses the same case-state as chat, facts, and memory.
- Live verification case `b6734cb0-c470-4222-ba1a-0d7e157617b2`: Hydrauliköl, 45 mm, 1500 U/min, 0,5 bar computes `3,53 m/s` and `1,77 bar·m/s` in the Right Rail; console had no CSP/font warnings after deploy.

## Worktree Hygiene / Frontend Sources

- 2026-07-05: `frontend-cockpit-deploy/` was audited on the VPS and is an old untracked Next.js scratch/copy workspace, not a production source of truth. It is not referenced by `ops/release-frontend.sh`, Docker Compose, nginx dashboard mounts, or the running `sealai-frontend-1` container.
- Canonical frontend sources remain `frontend/` for the public Next frontend and `frontend-v2/` for the dashboard SPA. The scratch copy was moved out of `/home/thorsten/sealai` and archived at `/home/thorsten/sealai-archives/frontend-cockpit-deploy-20260705-164144.tar.gz` with sha256 `b98036ff67dfe0d960bca0ee0a9be42b6b6ea402c883221d3b7ade221f00253b`.
