# GATE-10 evidence manifest

This is the canonical evidence checklist hashed by `evidence_manifest_sha256` in the
GATE-10 release manifest (`ops/production-release-manifest.json`). The gate
independently recomputes the SHA-256 of this file's committed content — see
`ops/production_release_gate.py::_evidence_manifest_sha256` — and rejects a manifest
whose claimed value does not match.

## Why this file exists

The release manifest's `readiness` block currently requires four claims to be the
literal boolean `true`:

- `P0_SECRETS_CONTAINED`
- `P0_STORAGE_STABLE`
- `P0_REDIS_STABLE`
- `RELEASE_GATE_FAIL_CLOSED`

Today the gate only checks that these four keys are present and `true` — it does not
verify *why* they are true. A manifest author could type `true` four times with nothing
behind it. GATE-11's `test_evidence_sha256` field already established the right
principle for this repo: bind a hash to the **literal, verbatim output of a real check**,
not a self-reported pass/fail. This document extends that principle to all four P0
claims, so a future gate revision can require real evidence instead of a bare boolean.

## What counts as evidence for each claim

| Claim | Evidence command (run from repo root) | What "green" looks like |
|---|---|---|
| `P0_SECRETS_CONTAINED` | `python3 ops/check-secret-hygiene.py --tree HEAD` | Output starts with `OK: no secret artifacts detected` |
| `P0_STORAGE_STABLE` | `/bin/bash ops/check_guard_health.sh` (section 1: docker disk guard) | `OK:` lines only for the disk-guard timer checks, exit code `0` |
| `P0_REDIS_STABLE` | `docker inspect redis --format '{{.State.Health.Status}}' && docker exec redis redis-cli ping` | `healthy` then `PONG` |
| `RELEASE_GATE_FAIL_CLOSED` | `/bin/bash -p ops/gate.sh` | Ends with `GATE: grün` |

An evidence-bound release manifest should capture each command's **exact, unedited**
stdout (not a paraphrase, not just the exit code) and reference it — e.g. by
SHA-256, the same way `test_evidence_sha256` already works in GATE-11 — rather than
letting the `readiness` block assert `true` on its own authority.

## Known gap this does not close

`ops/check_guard_health.sh` today covers the disk guard and general systemd-unit health,
but has no dedicated Redis check yet — the `P0_REDIS_STABLE` evidence command above is
the minimal direct check, not a wrapper script. Adding one to
`ops/check_guard_health.sh` would make this table's second column shorter and more
consistent; left as a follow-up, not bundled into this document.

## What this does not cover

`P0_REDIS_STABLE`'s command above only proves Redis is reachable and healthy *right
now* — it does not prove data durability across a restart, and no such check exists yet
in this repo. Do not read a green `PONG` as a durability guarantee.
