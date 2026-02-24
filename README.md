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

## Migration Notes
- Phase-1: State slimmed, ToolNode introduced, Redis checkpointer.
- Phase-2: Discovery loop, subgraphs, resolver, debate.

## Changelog
- MIGRATION: Phase-1 - Initial structure.
- MIGRATION: Phase-2 - Full architecture.

## Monitoring Runbook (Phase 6)
- Start stack: `docker-compose up -d`
- API: `http://localhost:8000`
- Health: `http://localhost:8000/health`
- Metrics: `http://localhost:8000/metrics`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (`admin` / `admin`)
- Smoke test: `python test_monitoring.py`
