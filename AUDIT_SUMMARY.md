# Audit Summary — prepare-apply

## Status
- Backend + frontend inventory generated (`reports/inventory.json`, `analysis/*`).
- Scripts + pytest harness scaffolded; cleanup plan captured for dry-run.

## Quick Wins
- Unused FastAPI agent stubs + legacy material nodes flagged for safe trash move.
- Frontend duplicates (`Sidebar` variants, `useAccessToken`) confirmed unused by knip/ts-prune.
- Dependency pins realigned to platform matrix (FastAPI 0.120, LangGraph 1.0.1, ts-prune 0.10.3).

## Risks / Watchpoints
- LangGraph websocket endpoint still contains redundant decorators + duplicated exception handling; review during cleanup.
- Deptry surfaced large number of global `requirements.txt` packages (legacy server list) — out of scope for current cleanup but note for later pruning.
- Vulture run failed on directory alias (`backend/main.py`) — ensure future re-org resolves path ambiguity.

## Next Steps
1. `bash scripts/cleanup.sh --apply`
2. `pytest -q` in `backend/`
3. `npm -C frontend ci && npm -C frontend run -s build`
4. Stage commits + craft PR text
