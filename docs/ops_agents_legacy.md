# Legacy External Agents (normen-agent/material-agent)

## Status
- These services are legacy and are not referenced by the LangGraph v2 or MAI-DxO supervisor.
- The canonical implementation is the MAI-DxO panel nodes inside the LangGraph v2 graph.

## How to run only when needed
- Default stack (no legacy agents):
  - `docker compose up -d`
- Enable legacy agents via profile:
  - `docker compose --profile agents-legacy up -d normen-agent material-agent`
  - Or include them with the full stack: `docker compose --profile agents-legacy up -d`

## Migration direction
- Use LangGraph MAI-DxO panels (calculator/material/norms RAG) instead of external containers.
- External agents are retained only for backwards compatibility and manual comparisons.
