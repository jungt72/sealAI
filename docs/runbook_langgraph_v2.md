# Runbook: LangGraph v2 (Diagnose + Node Contract)

## Diagnose in 60 Sekunden

### 1) Stack & Health

```bash
docker compose ps
docker exec nginx curl -sS -i https://localhost/api/v1/langgraph/health -k
```

### 2) Fehlerbild `/parameters/patch`

**Unauth (soll 401):**

```bash
docker exec nginx curl -sS -i http://backend:8000/api/v1/langgraph/parameters/patch \
  -X POST -H "Content-Type: application/json" \
  -d '{"chat_id":"default","parameters":{"medium":"oil"}}'
```

**Auth (soll 200; Token lokal einfügen, nicht loggen):**

```bash
docker exec nginx sh -lc 'curl -sS -i http://backend:8000/api/v1/langgraph/parameters/patch \
  -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "X-Request-Id: debug-parameters-patch" \
  -d "{\"chat_id\":\"default\",\"parameters\":{\"medium\":\"oil\"}}\"'
```

**Expected Error Codes (nie als generisches 500):**
- `400` `missing_chat_id|missing_parameters|invalid_parameters|invalid_as_node`
- `401` `Authorization header fehlt oder ungültig`
- `503` `dependency_unavailable` (Redis/Qdrant/etc. down)
- `500` `internal_error` (nur als fallback, ohne raw exception message)

### 3) Backend Logs (Trace + Request-Id)

```bash
docker compose logs --tail=400 backend | rg -n "langgraph_v2_parameters_patch|internal_error|invalid_as_node|dependency_unavailable|Traceback" -S
```

## Node Contract (stable vs optional)

### Stable (API-/Contract-relevant)

Diese Node-Namen werden außerhalb des Graphs referenziert (Endpoints / State Updates) und gelten als **stable contract**:
- `supervisor_logic_node` (u.a. `parameters/patch` und Default für State Updates)
- `confirm_recommendation_node` (u.a. `confirm/go`)

Quelle: `backend/app/langgraph_v2/contracts.py`

### Optional / intern

Alle anderen Nodes sind intern/implementierungsabhängig und können sich ändern, solange der stable contract eingehalten wird.

## Node-Liste schnell ausgeben

### Dev Script (Repo)

```bash
cd backend
python scripts/print_langgraph_v2_nodes.py
```

### Direkt im Container (wenn nötig)

```bash
docker exec backend sh -lc "python - <<'PY'
import asyncio
import os
os.environ.setdefault('CHECKPOINTER_BACKEND','memory')
from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2
async def main():
  g = await get_sealai_graph_v2()
  nodes = g.get_graph().nodes
  print('nodes_count', len(nodes))
  for n in sorted(nodes.keys()):
    print(n)
asyncio.run(main())
PY"
```

## Wenn neue Nodes eingeführt werden

- Wenn ein Endpoint `as_node` nutzt: **immer** über `assert_node_exists(...)` absichern.
- Stable contract Nodes nur ändern, wenn:
  - Tests (`backend/tests/test_langgraph_parameters_patch.py`) angepasst sind
  - Docs/Runbook aktualisiert sind

## Tests (schnell vs. Compose)

### Schnell / deterministisch (pure app)

```bash
cd backend
pytest -q
pytest -q tests/integration/test_langgraph_v2_http.py
pytest -q tests/integration/test_langgraph_v2_sse.py
```

### Compose Wiring (optional)

Läuft nur, wenn der Stack erreichbar ist (Default: skip).

```bash
cd backend
RUN_INTEGRATION=1 pytest -q tests/integration/test_compose_wiring.py
```

Alternativ über Script:

```bash
./ops/test-backend.sh
RUN_INTEGRATION=1 ./ops/test-backend.sh
```
