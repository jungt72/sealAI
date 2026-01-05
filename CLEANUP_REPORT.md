# Cleanup Report (dry-run ready)
## Backend — Functions/Files
DELETE backend/agents/material_agent/main.py | Grund: ungenutztes health() | Nachweis: vulture material_agent/main.py:17
DELETE backend/agents/normen_agent/main.py   | Grund: ungenutztes health() | Nachweis: vulture normen_agent/main.py:17
DELETE backend/agents/supervisor_stack.py    | Grund: arithmetischer Dummy/Stub | Nachweis: vulture supervisor_stack.py:234
DELETE backend/app/langgraph/subgraphs/material/nodes/*_legacy.py | Grund: veraltete LCEL/Wrapper | Nachweis: ruff F401/F841 + Review
## Backend — Ruff Fixes
FIX backend/app/api/v1/endpoints/ai.py:12 | Grund: ungenutzter Import | Nachweis: ruff F401
FIX backend/app/langgraph/subgraphs/material/nodes/** | Grund: ungenutzte Variablen/Imports | Nachweis: ruff F401/F841
## Backend — Tests/Harness
MOVE backend/app/langgraph/tests/test_hybrid_flow.py -> backend/tests/test_hybrid_flow.py | Grund: Imports reparieren | Nachweis: pytest collect log
## Frontend — Components/Helpers
DELETE frontend/src/components/organisms/Sidebar.tsx | Grund: keine Konsumenten | Nachweis: knip, ts-prune
DELETE frontend/src/app/dashboard/components/Sidebar/Sidebar.tsx | Grund: Legacy-Duplikat | Nachweis: knip, ts-prune
## Frontend — Dependencies
REMOVE @react-three/drei | Grund: ungenutzt | Nachweis: depcheck
REMOVE react-icons | Grund: ungenutzt | Nachweis: depcheck
REMOVE react-textarea-autosize | Grund: ungenutzt | Nachweis: depcheck
## Artefakte
DELETE .pytest_cache/ 
DELETE __pycache__/
DELETE frontend/.next/
DELETE dist/
DELETE build/
DELETE coverage/
