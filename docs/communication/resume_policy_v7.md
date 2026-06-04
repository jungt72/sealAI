# Resume Policy V7

Resume decides what happens after a side question, correction, or mixed turn.

## Strategies

- none
- restore_to_pending_question_v1
- reevaluate_after_answer
- pause_primary_task
- continue_side_task

## Patch 1 Transition

Patch 1 may use restore_to_pending_question_v1 for a narrow active-case side-question spike. The trace must mark this as transitional.

## Patch 2 Target

Patch 2 replaces blind restore with reevaluate_after_answer.

## Decision Table

| Condition after answer | Resume |
|---|---|
| No new facts and pending question still valid | restore/return to pending question |
| Candidate fact detected, pending question still valid | acknowledge candidate, then return |
| Candidate fact answered pending question | close pending question, compute next question |
| Correction | recompute and determine new next question |
| Pending question became invalid | replace pending question |
| Side continuation | continue side task, keep original resume target |
| User explicitly changes topic | pause primary task or route by policy |
| High uncertainty | ask clarification, no mutation |
