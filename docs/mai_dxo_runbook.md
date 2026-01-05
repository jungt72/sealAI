# MAI-DxO Supervisor Runbook (LangGraph v2)

## Enable MAI-DxO mode
- Set environment variable `LANGGRAPH_V2_SUPERVISOR_MODE=mai_dxo`.
- Default behavior is `legacy` when the variable is unset or any other value.
- Restart the backend service to rebuild the cached graph.

## Expected behavior
- Entry remains: START -> frontdoor_discovery_node.
- When enabled, routing goes to supervisor_policy_node with a loop:
  supervisor_policy_node -> panel_* -> aggregator_node -> supervisor_policy_node.
- Final responses still use the existing Jinja2 pipeline and SSE behavior.

## Rollback
- Set `LANGGRAPH_V2_SUPERVISOR_MODE=legacy` (or unset).
- No schema or endpoint contract changes are required to revert.

## Quick checks
- Verify logs show `supervisor_policy_node` when enabled.
- Confirm legacy routing uses `supervisor_logic_node` when disabled.
