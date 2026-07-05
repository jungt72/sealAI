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
