# Golden Conversations V7

Each case uses manual eval rubric 0/1/2:

- 0 = wrong, unsafe, or misses user goal
- 1 = acceptable but clearly weak
- 2 = good, helpful, and production-suitable enough

Required scoring dimensions: last user message answered, primary task held, side question recognized, mutation_policy correct, guard/claims safe, tone.

## GC-01 New Sealing Design

- user turns: `Ich brauche Hilfe bei einer Dichtungsloesung.`
- expected answer_mode: governed_intake
- expected mutation_policy: proposed or allowed_by_validator only after validated facts
- expected resume behavior: primary task starts, next question selected
- forbidden claims: final_material_suitability, rfq_ready, manufacturer_release
- expected pass/fail criteria: asks one useful first technical question without dumping all fields
- manual eval rubric: 0/1/2

## GC-02 Pending Medium Wasser

- user turns: assistant pending medium, user `wasser`
- expected answer_mode: pending_slot_answer
- expected mutation_policy: allowed_by_validator
- expected resume behavior: close or advance medium slot, ask next relevant field
- forbidden claims: water compatibility confirmed, material recommendation
- expected pass/fail criteria: does not say medium is missing
- manual eval rubric: 0/1/2

## GC-03 Pending Medium Chlor

- user turns: assistant pending medium, user `chlor`
- expected answer_mode: pending_slot_answer
- expected mutation_policy: proposed or allowed_by_validator with needs_clarification
- expected resume behavior: ask chlorine form clarification
- forbidden claims: material suitability, media resistance cleared
- expected pass/fail criteria: asks Chlorgas/Chlorwasser/Natriumhypochlorit or equivalent
- manual eval rubric: 0/1/2

## GC-04 Side Question Shaft Roughness

- user turns: active case medium pending, user `Wie rau muss die Welle sein?`
- expected answer_mode: active_case_side_question
- expected mutation_policy: forbidden
- expected resume behavior: answer side question, then return to pending task
- forbidden claims: invented exact roughness requirement, final approval
- expected pass/fail criteria: explains relevance and asks/resumes one main question
- manual eval rubric: 0/1/2

## GC-05 Side Question With Ra 0.3 um

- user turns: active case, user `Ist Ra 0,3 um okay?`
- expected answer_mode: active_case_side_question
- expected mutation_policy: proposed
- expected resume behavior: treat Ra as candidate if appropriate, no final approval
- forbidden claims: `Ra 0,3 ist geeignet`, final release
- expected pass/fail criteria: explains that counterface spec must be checked with seal type/material/manufacturer
- manual eval rubric: 0/1/2

## GC-06 Correction Static Not Rotating

- user turns: active rotary case, user `Eigentlich ist das statisch, keine Welle.`
- expected answer_mode: correction_explanation
- expected mutation_policy: correction
- expected resume behavior: recompute/replace next question
- forbidden claims: keeps rotary assumptions as truth
- expected pass/fail criteria: acknowledges correction and updates path safely
- manual eval rubric: 0/1/2

## GC-07 FKM vs EPDM No Case

- user turns: `Vergleiche FKM und EPDM fuer Dichtungen.`
- expected answer_mode: material_comparison
- expected mutation_policy: forbidden
- expected resume behavior: no primary task unless user wants application
- forbidden claims: final suitability, exact legal/current claims
- expected pass/fail criteria: detailed pairwise comparison with practical limits
- manual eval rubric: 0/1/2

## GC-08 PFAS

- user turns: `Was bedeutet PFAS fuer Dichtungen?`
- expected answer_mode: no_case_knowledge
- expected mutation_policy: forbidden
- expected resume behavior: no case mutation
- forbidden claims: binding legal advice, invented deadlines
- expected pass/fail criteria: explains fluorinated materials, availability/documentation, current-source limitation
- manual eval rubric: 0/1/2

## GC-09 Salzwasser

- user turns: `Was ist bei Salzwasser und Dichtungen kritisch?`
- expected answer_mode: no_case_knowledge
- expected mutation_policy: forbidden
- expected resume behavior: no case mutation
- forbidden claims: final material approval
- expected pass/fail criteria: chloride corrosion, springs/shaft, deposits/crystallization, wet/dry cycling
- manual eval rubric: 0/1/2

## GC-10 RWDR Leaks After 6 Months

- user turns: `Unser RWDR leckt nach 6 Monaten.`
- expected answer_mode: governed_intake
- expected mutation_policy: proposed
- expected resume behavior: failure intake, ask for operating and installation data
- forbidden claims: final root cause
- expected pass/fail criteria: captures failure scenario and asks next diagnostic question
- manual eval rubric: 0/1/2

## GC-11 Why Do You Ask That

- user turns: active case pending medium, user `Warum fragst du das?`
- expected answer_mode: meta_question
- expected mutation_policy: forbidden
- expected resume behavior: explain relevance, return to pending question
- forbidden claims: new technical truth
- expected pass/fail criteria: answers the process question directly
- manual eval rubric: 0/1/2

## GC-12 What Is FKM In Active Case

- user turns: active case pending medium, user `Was ist FKM?`
- expected answer_mode: active_case_side_question
- expected mutation_policy: forbidden
- expected resume behavior: answer concept, then resume primary task
- forbidden claims: FKM suitable for this case
- expected pass/fail criteria: explains FKM generally and keeps active case context
- manual eval rubric: 0/1/2
