# HITL Design (LangGraph v2)

## Event Contract
- `checkpoint_required` (SSE): emitted when a confirm gate is reached.
- `state_update` (SSE): stable updates for phase + parameters + pending action.
- `done` (SSE): always emitted at stream completion; includes `awaiting_confirmation` and `checkpoint_id`.

### Example: checkpoint_required
```json
{
  "checkpoint_id": "chk-123",
  "required_user_sub": "kc-sub-123",
  "conversation_id": "conv-456",
  "action": "RUN_PANEL_NORMS_RAG",
  "risk": "high",
  "preview": {
    "text": "...human readable preview...",
    "summary": "discovery summary",
    "parameters": {"pressure_bar": 8, "temperature_C": 70},
    "coverage_score": 0.72,
    "coverage_gaps": ["medium"]
  },
  "diff": null,
  "created_at": "2025-01-01T12:00:00Z"
}
```

## Payload Schema
- `checkpoint_id`: unique identifier for the gate.
- `required_user_sub`: Keycloak `sub` that must confirm.
- `conversation_id`: scoped chat/conversation id.
- `action`: canonical graph action being gated (e.g. `RUN_PANEL_NORMS_RAG`).
- `risk`: `low|med|high` risk hint for UI.
- `preview`: safe-for-UI context; includes a human-readable `text` plus structured details.
- `diff`: optional structured diff for edits.
- `created_at`: ISO timestamp.

## Resume Semantics
- `approve`: continue the pending action.
- `reject`: terminate with a safe cancellation response.
- `edit`: apply parameter patch (provenance=`user`) and optional instructions, then continue.

Confirm resume is handled by:
- `backend/app/langgraph_v2/nodes/nodes_resume.py` (`confirm_resume_node`, `confirm_reject_node`).
- `backend/app/api/v1/endpoints/langgraph_v2.py` (`POST /confirm/go`) runs a resume cycle.

## Adding Additional Gates
1) Choose a high-impact action in `backend/app/langgraph_v2/nodes/nodes_supervisor.py`.
2) Add it to the confirmation policy (set `action = REQUIRE_CONFIRM` and `pending_action = <action>`).
3) Optionally extend `_ACTION_RISK` in `backend/app/langgraph_v2/nodes/nodes_confirm.py`.
4) Ensure frontend renders the new action label or risk copy if needed.
