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
- `SMALLTALK`: light non-technical conversation before a case starts.
- `MANUAL_REVIEW`: reserved for cases that need human engineering review.

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

The LLM may only use claim IDs it received. Claims carry the state snapshot hash and a lifecycle marker so stale or revoked claims can be blocked before user-visible output.

Fabricated claim IDs or evidence references are blocked. Evidence must be cited through explicit `cited_evidence_ref_ids`; text-only citation claims are not enough.

## Response Contract

The LLM returns structured JSON:

```text
mode
assistant_message
used_claim_ids
cited_evidence_ref_ids
asks_for_fields
proposed_field_updates
recommendation_level
contains_solution_recommendation
contains_final_approval
requires_human_review
safety_flags
next_action
```

`proposed_field_updates` never confirms state. They remain candidates for the existing governed validation/reducer path.

The communication LLM must not introduce new field proposals. It may only echo proposals produced by the deterministic extraction path and every proposal must require user confirmation.

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
- inactive/stale/revoked allowed claim IDs
- unsupported field proposal keys or units
- LLM-introduced proposals that did not come from the extraction path
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

The successful HCL output is not routed back through the legacy renderer. This prevents natural answers from being collapsed into internal labels such as "Arbeitsstand" or "Naechste sinnvolle Frage".

If the new layer itself errors, SeaLAI returns the deterministic backend fallback unless `SEALAI_ENABLE_LEGACY_VISIBLE_RENDERER=true` is explicitly configured.

## Failure Diagnostic Intake

Failure and complaint conversations use a stricter diagnostic order than normal RFQ clarification.
The assistant must not jump to root-cause language. It should first preserve the field evidence and
collect the facts that a sealing technician would need before forming hypotheses.

Priority order:

```text
1. safety_context
2. leak_location
3. damage_evidence
4. seal_type
5. failure_timing
6. damage_pattern
7. operating_conditions
8. medium_at_failure
9. pressure_profile
10. temperature_at_seal
11. motion_profile
12. geometry_surface_context
13. installation_context
14. material_or_compound
15. previous_service_life
```

The complaint/failure intake service may extract candidates such as seal type, leak location,
damage pattern, pressure, temperature, speed, shaft diameter, material and surface hints. These
remain candidates until governed validation or user/manufacturer confirmation. Visible answers
should use "Hypothese", "Hinweis", "offen" or "zu prüfen", never "Ursache bestätigt".

## New Design Intake

Neuauslegung is handled as a stricter design-intake problem, not as a product
catalog question. The read-only `SealDesignIntakeService` compares the available
case data against a minimum engineering dataset and may compute screening
checks only where the required inputs are present.

Minimum design-intake priorities:

```text
1. sealing_function
2. leakage_target
3. safety_context
4. medium
5. motion_type
6. pressure_profile
7. temperature_profile
8. lifetime_target
9. lubrication
10. contamination
11. geometry_space
12. tolerance_gap
13. surface_roughness
14. mounting_path
15. verification_criteria
16. seal_type
```

The service may surface O-ring/groove screening values such as squeeze, groove
fill and stretch when inputs are present. It may also mark escalation triggers
such as high pressure with unknown or large gap, gas decompression review, high
temperature with high groove fill, or flange-gasket norm-calculation need. These
are screening facts only. They are never a final material release, design freeze
or manufacturer approval.

The next-best-question layer follows this design-intake order for `new_rfq`.
That prevents SeaLAI from starting a new design with a catalog-style "which seal
type?" question before function, leakage target, medium, motion and load profile
are understood.

## Configuration

Feature flag:

```text
HUMAN_COMMUNICATION_LAYER_ENABLED=true|false
```

Optional append-only trace metadata sink:

```text
SEALAI_COMMUNICATION_AUDIT_LOG=/path/to/hcl-audit.jsonl
```

This writes trace metadata only: turn ID, mode, prompt version, state hash, used claim IDs, evidence IDs, guard result, validation errors, model name and timestamp. It does not write raw prompts, secrets or full user text.

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
- It writes durable HCL trace metadata only when `SEALAI_COMMUNICATION_AUDIT_LOG` is configured.
