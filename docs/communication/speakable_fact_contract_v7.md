# SpeakableFact Contract V7

SpeakableFacts bridge cockpit truth and chat language. The composer may speak only from AnswerPlan, EvidenceItems, and SpeakableFacts.

## Schema

```json
{
  "fact_id": "medium_chlor_candidate",
  "field": "medium",
  "status": "candidate",
  "claim_level_max": "L2",
  "structured_value": {"value": "chlor", "needs_clarification": true},
  "safe_phrases": [
    "Ich habe Chlor als Medium verstanden, aber die genaue Form ist noch offen."
  ],
  "forbidden_phrases": [
    "Chlor ist fuer den Werkstoff geeignet."
  ],
  "source": "slot_binding",
  "visible_in_cockpit": true
}
```

## Claim Levels

- L1: general technical knowledge
- L2: application-oriented orientation with caution
- L3: backend-supported preliminary assessment
- L4: final release, forbidden for the chat

## Selection Rules

1. Use the contextually best safe phrase.
2. Paraphrase only within claim_level_max.
3. Do not repeat the same phrase in consecutive turns if an alternative exists.
4. Candidate must never sound confirmed.
5. Chat must never contradict cockpit state.

## Forbidden

- final material suitability
- manufacturer release
- RFQ-ready without deterministic backend basis
- invented values
- legal/current regulatory claims without current evidence
