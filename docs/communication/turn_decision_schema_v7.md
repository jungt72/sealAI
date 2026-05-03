# TurnDecision Schema V7

TurnDecision replaces single-intent routing. It is the typed handoff from conversation interpretation to backend domain work.

## Required Fields

```json
{
  "turn_kind": "mixed",
  "primary_interpretation": "pending_slot_answer_with_embedded_knowledge_question",
  "router_signals": {},
  "state_actions": [],
  "answer_obligations": [],
  "answer_mode": "pending_slot_answer",
  "mutation_policy": "proposed",
  "resume_strategy": "reevaluate_after_answer",
  "resume_target_candidate": null,
  "confidence": 0.81
}
```

## Router Signals

Router signals are diagnostic and policy inputs only:

- nano_intent
- nano_confidence
- deterministic_pending_slot_match
- deterministic_value_extraction
- active_case_exists
- safety_blocked
- language

## State Actions

State actions may be:

- none
- candidate_fact
- confirm_fact
- correct_fact
- clear_pending_question
- open_side_task
- close_side_task
- block

Every state action carries a MutationPolicy.

## Answer Obligations

Answer obligations tell the FinalAnswerLayer what must be addressed. Examples:

- acknowledge_candidate_fact
- answer_side_question_directly
- correct_false_assumption
- ask_one_main_follow_up
- return_to_primary_task
- explain_limitation

## Mixed Turn Example

User: `EPDM waere fuer Wasser besser, oder? Wir haetten Wasser mit Reinigerzusatz.`

Expected:

- pending_slot_answer wins for state
- material assumption is answered carefully
- medium becomes candidate/proposed, not confirmed suitability
- resume_strategy=reevaluate_after_answer

## Forbidden In TurnDecision

TurnDecision must not contain final answer text, final material suitability, RFQ readiness, or manufacturer release. It is a control object, not the visible answer.
