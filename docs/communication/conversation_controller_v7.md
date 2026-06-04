# Conversation Controller V7

Status: active implementation contract for SealAI Communication Architecture V7.1.

The Conversation Controller is the central decision layer between router signals and user-visible answers. It does not create engineering truth and it does not compose the final answer. It turns one user message into a typed TurnDecision that can be validated by backend policy.

## Responsibilities

- Detect whether the user answered the pending question.
- Detect new technical facts, corrections, side questions, process questions, no-case knowledge, and smalltalk.
- Preserve the primary technical task while allowing one bounded side task.
- Decide the MutationPolicy before any domain service may change case state.
- Produce answer obligations for the FinalAnswerLayer.
- Produce or update a TaskStack and ResumeStrategy.

## Decision Priority

1. safety / blocked
2. explicit correction
3. pending-slot answer
4. new technical facts
5. active-case side question
6. meta / process question
7. no-case knowledge
8. smalltalk
9. unclear / clarification

The priority is for state action. A single user turn can still carry more than one answer obligation.

## Router Role

The nano-class router is only a signal provider. It may propose intent, answer mode, side-question status, case relevance, mutation suggestion, and confidence. It must not answer the user and must not mutate case truth.

## Backend Validation

Backend policy validates every TurnDecision before domain work runs. If the router and backend disagree, backend safety wins.

## Confidence Bands

- confidence >= 0.80: strong signal, still validated by backend.
- 0.55 <= confidence < 0.80: uncertain signal; pending slots and deterministic extraction have priority.
- confidence < 0.55: no automatic mutation; clarify or fallback.

## Disagreement Rules

| Conflict | Decision |
|---|---|
| Pending slot recognizes a valid answer, router says knowledge | Slot wins for state; answer may also address knowledge aspect. |
| Router suggests mutation, backend validates no value | No mutation. |
| Router says side question, user supplies concrete value | Side question plus candidate_fact. |
| Router uncertain, backend recognizes nothing | Clarification. |
| Safety triggers | Safety wins. |
| User correction appears | Correction wins. |
| Router says smalltalk, pending slot is answered | Pending slot wins. |
| Router says knowledge with no active case | no_case_knowledge. |
| Router says knowledge with active case | active_case_side_question; mutation defaults to forbidden or proposed. |

## Examples

User: `und FKM mit NBR?` during active case.

Expected: active_case_side_question, mutation_policy=forbidden, answer material comparison, then resume primary task.

User: `chlor` after pending medium question.

Expected: pending_slot_answer, candidate medium, needs clarification, no material suitability claim.
