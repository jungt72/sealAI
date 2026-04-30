# SeaLAI Human Communication Layer

## Purpose

The Human Communication Layer makes SeaLAI's chat feel more like a careful sealing-technology engineer without moving technical authority into the LLM.

The principle is:

```text
Human communication in the frontend.
Deterministic engineering truth in the backend.
The LLM explains; the backend decides.
```

## Modes

The layer separates broad explanation from case-bound engineering:

- `GENERAL_KNOWLEDGE`: educational explanations such as what a radial shaft seal is.
- `CASE_QUALIFICATION`: a concrete sealing application or suitability question.
- `RFQ_PREPARATION`: RFQ or inquiry-preparation language.
- `FAILURE_ANALYSIS`: leakage, damage, or failure intake.
- `FIELD_EXTRACTION`: values from chat become proposals only.
- `OUT_OF_SCOPE_OR_UNSAFE`: injection or unsafe requests.

## Allowed Claims

Concrete case-bound statements must come from `allowed_claims`.

Allowed claims are built from backend state:

- confirmed fields
- proposed fields
- missing fields
- stale fields
- deterministic calculations
- backend risks
- readiness status
- evidence references
- allowed next actions
- system limitation that final approval remains external

The LLM may only use claim IDs it received. Fabricated claim IDs or evidence references are blocked.

## Response Contract

The LLM returns structured JSON:

```text
mode
assistant_message
used_claim_ids
asks_for_fields
proposed_field_updates
contains_solution_recommendation
contains_final_approval
requires_human_review
safety_flags
next_action
```

`proposed_field_updates` never confirms state. They remain candidates for the existing governed validation/reducer path.

## Guard

`CommunicationGuard` checks the structured response before it reaches the user.

It blocks or falls back on:

- final approval or release wording
- guarantee wording
- suitability or final recommendation language
- unsupported risk claims
- readiness claims without readiness grounding
- fabricated allowed claim IDs
- fabricated evidence references
- prompt-injection outcomes

If validation fails, the user receives a deterministic fallback based only on backend missing fields and allowed next actions.

## Integration

The layer is wired into governed visible replies through `collect_governed_visible_reply`.

For the governed path:

```text
deterministic backend result
→ CaseConversationState
→ allowed_claims
→ structured LLM response
→ CommunicationGuard
→ visible reply or deterministic fallback
```

The legacy governed renderer remains as a fail-open-to-safe fallback if the new layer itself errors.

## Configuration

Feature flag:

```text
HUMAN_COMMUNICATION_LAYER_ENABLED=true|false
```

Model selection reuses:

```text
SEALAI_CONVERSATION_MODEL
```

Tests use fakes and do not call a real LLM.

## Tests

Run:

```bash
.venv/bin/python -m pytest backend/app/agent/tests/test_human_communication_layer.py -q
```

Useful regression set:

```bash
.venv/bin/python -m pytest \
  backend/app/agent/tests/test_human_communication_layer.py \
  backend/app/agent/tests/test_governed_stream_payload.py \
  backend/app/agent/tests/test_output_guard.py \
  backend/app/agent/tests/test_turn_context.py -q
```

## Known Limits

- The layer does not persist new engineering truth.
- It does not build RAG, matching, RFQ export, or manufacturer dispatch.
- It does not make final sealing recommendations.
- It only exposes proposal objects; state mutation remains the job of existing governed services.
