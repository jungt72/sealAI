# Side Question Taxonomy V7

Side questions are allowed during an active case. They must not destroy the primary task.

## Types

| Type | Example | MutationPolicy |
|---|---|---|
| pure_side_question | `Wie rau muss die Welle sein?` | forbidden |
| side_question_with_value | `Ist Ra 0,3 um okay?` | proposed |
| hidden_correction | `Eigentlich ist das statisch, keine Welle.` | correction |
| process_question | `Warum fragst du das?` | forbidden |
| concept_question | `Was ist FKM?` | forbidden |
| side_task_continuation | `Und wie misst man die Rauheit?` | forbidden/proposed by content |

## Depth Rule

Maximum side-task depth is 1. A second related question is a side_task_continuation, not a nested task.

## Resume Rule

The original resume target remains attached to the primary task. Patch 1 may use restore_to_pending_question_v1. Patch 2 must reevaluate after answering.

## Safety

Side questions may use general knowledge and evidence. They may not set technical truth, material suitability, RFQ readiness, or manufacturer approval.
