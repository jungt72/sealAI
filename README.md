# SealAI - LangGraph Migration V0.6.10

## Prerequisites
- Redis with RedisJSON and RediSearch modules.
- Python dependencies: langgraph, pydantic, jinja2, etc.

## Feature Flag
Set `ENABLE_LANGGRAPH_V06=1` to enable new LangGraph workflow.

## Configuration Keys
See `backend/app/langgraph/config/agents.yaml` for model, prompt, rag, tools, limits, budget settings.

## Test Commands
- `pytest backend/app/langgraph/tests/`
- Specific: `pytest backend/app/langgraph/tests/test_state.py`
- In-container: `python -m pytest -q /app/backend/app/api/v1/tests/test_rag_tenant_scoping.py`

## Tests
- `./scripts/test.sh unit`
- `./scripts/test.sh api`
- `./scripts/test.sh all`

## Migration Notes
- Phase-1: State slimmed, ToolNode introduced, Redis checkpointer.
- Phase-2: Discovery loop, subgraphs, resolver, debate.

## Changelog
- MIGRATION: Phase-1 - Initial structure.
- MIGRATION: Phase-2 - Full architecture.
