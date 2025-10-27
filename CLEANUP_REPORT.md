# Cleanup Report (Draft)

| Path | Action | Reason | Evidence |
| --- | --- | --- | --- |
| backend/agents/material_agent/main.py | move to .trash | Legacy FastAPI micro-service unused by backend since LangGraph migration; vulture marks `health` unused. | vulture report (`analysis/vulture_backend.txt`), file `backend/agents/material_agent/main.py:17` |
| backend/agents/normen_agent/main.py | move to .trash | Legacy stub agent not imported anywhere; duplicate functionality removed. | vulture report (`analysis/vulture_backend.txt`), file `backend/agents/normen_agent/main.py:17` |
| backend/app/api/routes/chat.py | move to .trash | Deprecated SSE fallback conflicting with current LangGraph streaming; missing dependency pins. | deptry report (`analysis/deptry_backend.json`), file `backend/app/api/routes/chat.py:7` |
| backend/app/__pycache__ | move to .trash | Bytecode artefact. | inventory (`analysis/artifact_dirs.json`) |
| backend/app/langgraph/__pycache__ | move to .trash | Bytecode artefact. | inventory (`analysis/artifact_dirs.json`) |
| backend/.pytest_cache | move to .trash | Test artefact. | inventory (`analysis/artifact_dirs.json`) |
| frontend/.next | move to .trash | Stale Next.js build output, not tracked. | inventory (`analysis/artifact_dirs.json`) |
| .pytest_cache | move to .trash | Root pytest cache. | inventory (`analysis/artifact_dirs.json`) |
| .env.bak.1754931261 | move to .trash | Duplicate env backup; no unique content. | duplicate scan (`analysis/duplicates_filtered.json`) |
| .env.bak.1754931391 | move to .trash | Duplicate env backup; no unique content. | duplicate scan (`analysis/duplicates_filtered.json`) |
| .env.bak.1754931465 | move to .trash | Duplicate env backup; no unique content. | duplicate scan (`analysis/duplicates_filtered.json`) |
| frontend/src/components/Fog.tsx | move to .trash | Unused component (ts-prune). | `analysis/ts_prune_frontend.txt` |
| frontend/src/components/HeroBackground.tsx | move to .trash | Unused component (ts-prune). | `analysis/ts_prune_frontend.txt` |
| frontend/src/components/organisms/Header.tsx | move to .trash | Legacy layout unused. | `analysis/ts_prune_frontend.txt` |
| frontend/src/components/organisms/Sidebar.tsx | move to .trash | Replaced by new dashboard; ts-prune unused. | `analysis/ts_prune_frontend.txt` |
| frontend/src/components/ui/card.tsx | move to .trash | Duplicate card component; unused (knip). | `analysis/knip_frontend.json` |
| frontend/src/app/dashboard/Dashboard.tsx | move to .trash | Obsolete dashboard wrapper (ts-prune). | `analysis/ts_prune_frontend.txt` |
| frontend/src/app/dashboard/ChatScreen.tsx | move to .trash | Legacy chat entry (ts-prune). | `analysis/ts_prune_frontend.txt` |
| frontend/src/app/dashboard/components/Sidebar/Sidebar.tsx | move to .trash | Unused wrapper (ts-prune). | `analysis/ts_prune_frontend.txt` |
| frontend/src/app/dashboard/components/Sidebar/SidebarRight.tsx | move to .trash | Unused panel (ts-prune). | `analysis/ts_prune_frontend.txt` |
| frontend/src/lib/logout.ts | move to .trash | Duplicate logout helper; unused exports. | `analysis/knip_frontend.json`, `analysis/ts_prune_frontend.txt` |
| frontend/src/lib/useAccessToken.ts | move to .trash | Unused helper; replaced by session tokens. | `analysis/knip_frontend.json`, `analysis/ts_prune_frontend.txt` |

> Note: All removals routed through `scripts/cleanup.sh` and executed only after sign-off.
