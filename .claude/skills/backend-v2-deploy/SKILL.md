---
name: backend-v2-deploy
description: >-
  Deploy the sealingAI backend-v2 service to production safely. Use when a task
  asks to deploy, release, ship, or roll back backend-v2, add a new SEALAI_V2_*
  setting or bind mount, or touch docker-compose.deploy.yml. Encodes the
  sanctioned release script, the compose-passthrough allow-list invariant (the
  #1 recurring incident class in this repo), rollback anchors, and the
  post-incident HALT rule.
---

# Deploy backend-v2 (production)

Read `.claude/rules/ops.md` and `AGENTS.md § Git / branch workflow` alongside this.
The only sanctioned mechanism is the release script — never `docker compose up`
by hand for a prod change.

## The sanctioned path

```bash
# Backend-v2 to prod — health-gated, smoke-tested, tags an automatic rollback anchor
./ops/release-backend-v2.sh --final
```

- Do **not** deploy by editing containers directly.
- The pytest exit code is authoritative for the pre-deploy gate. Never hide a
  failing test to get past it.
- The eval hard-gate in the release script is currently **temporarily
  owner-disabled** (between the `###EVAL-GATE-DISABLED-TEMP###` /
  `###EVAL-GATE-ORIGINAL-BEGIN###`…`###EVAL-GATE-ORIGINAL-END###` markers). That is
  an owner authorization, not a license to skip targeted eval — run the targeted
  REPLAY yourself (see the `eval-replay-adjudication` skill).

## THE compose-passthrough invariant (read this every time)

A `docker-compose.deploy.yml` field/env-var is an **explicit allow-list**. A new
`SEALAI_V2_*` setting in `config/settings.py` or a new bind mount **does nothing**
until:

1. it also has a line in `docker-compose.deploy.yml`'s `environment:` /
   `volumes:` block, **and**
2. the running container is **recreated** (not just restarted) to pick it up.

This exact bug class has caused **multiple real production incidents** in this
repo. Rule: **add the compose passthrough in the SAME patch as the settings
field.** When you add a flag, grep `docker-compose.deploy.yml` for it before
claiming it is wired.

Related footgun (2026-07-04): a flag that flips runtime behavior can hide a
runtime-only cost — e.g. the hybrid-retrieval reranker downloads a ~1.1GB model
at **runtime**, not build time, which crash-looped the service. Pre-bake heavy
assets; do not assume a flag is free to flip.

## Feature-flag discipline

Feature work lands **flag-gated, default OFF, byte-identical when unset** unless
the owner explicitly says otherwise. Prove byte-identity with a targeted eval or
an explicit before/after diff against live data **before** activating — do not
assume it.

## Schema/migration parity (confirmed-twice incident class)

`backend/sealai_v2/db/migrate.py` is **`create_all`-only** ("Alembic is the future
path"), run manually in-container:

```bash
python -m sealai_v2.db.migrate up --url postgresql+psycopg2://…@postgres:5432/sealai_v2
```

`create_all` **creates missing tables but never ALTERs an existing one**. History:
4 tables were missing entirely in prod — a **confirmed-twice** recurring risk. So:
if a patch adds or changes a model/column in `db/`, you must run `migrate up`
in-container **and verify schema parity post-deploy** — a new `SEALAI_V2_*` flag
that reads a not-yet-created table silently fails. Do not assume the schema
followed the code.

## Rollback

- The release script tags a rollback anchor automatically. If you need the anchor
  for a running daemon, derive it from the **running container**, not from a
  guess.
- `frontend-v2`/dashboard deploys via a **different** mechanism (its live `dist/`
  bind-mount — `npm run build` IS the deploy). Be explicit about which service
  you mean; do not conflate them.

## HALT gates (never auto past a gate)

- Plan → owner gate → build → review. A `docker-compose.deploy.yml` change or a
  new bind mount to the shared stack needs **explicit, per-action owner
  go-ahead** — a confirmation must NAME the action, not just affirm.
- A **self-caused production incident is itself a HALT point**: report and stop.
  Do **not** self-commit a fix to `main`, even a tested and correct one, without
  checking back with the owner first.
- Shared edge nginx changes are especially dangerous (a rate-limit rollout once
  broke Keycloak login) — treat them as owner-gated per action.

## Secret hygiene

Governed by `.claude/rules/ops.md § Secrets & untouchables` — `.env*` never
read/printed/committed; a live REPLAY sources `OPENAI_API_KEY` transiently for that
run only, never into logs.
