# V2 OPTIMIZE backlog (post-cutover — none of these gate the cutover or the pilot)

## 1. Live token streaming for /api/v2/chat (owner-filed 2026-06-10)

Today `/api/v2/chat` returns the finished, verified, framed answer in one response. Streaming is
wanted for UX, but:

**HARD design constraint.** The trust spine verifies and frames AFTER L1
(answer → verify → render → cite). Naive raw-L1 token streaming would put UNVERIFIED text on
screen before the L3 critic pass and the claim-boundary framing apply — hallucination exposure,
the exact failure the four-layer architecture exists to prevent. Streaming must be DESIGNED to
coexist with post-hoc verification. Candidate shapes (none decided):

- stream L1 tokens but WITHHOLD the verdict/badges (vorläufig/candidate/corrections) until the
  L3 verify completes — the UI marks the stream as unverified-in-progress until then;
- two-phase render: stream a draft phase, replace with the verified/framed final;
- stream only post-verify (verify on the full answer, then stream the verified text out).

**Acceptance bar:** its own design pass (owner-gated), its own eval/REPLAY (the Schranken must
hold — no entered trap, no confident-false, no invented precision — including mid-stream states),
and an e2e pass. The SSE/streaming lessons from V1 (final-guard-before-stream, no draft-token
leak: AGENTS.md § runtime rules) are prior art to consult, not code to carry over (green-field
boundary stays).

**Explicitly NOT a cutover task** — the cutover ships the non-streaming chat.

## 2. Grounding/citation precision — a cited Fachkarte must match the claim's subject (owner-filed 2026-06-11)

Found at the M8 HALT #2 owner adjudication (run `m8-calc`, CALC-FAILCLOSED-01 Turn 0): the answer
cites `FK-EPDM-MINERALOEL` as the source for an **NBR**-suitability sentence ("NBR typisch passend
für Mineralöle … (Quelle: Fachkarte FK-EPDM-MINERALOEL)"). The card is on-topic for the *adjacent*
EPDM warning (which cites it correctly), but the NBR claim is not what that card asserts — the
citation over-reaches the card's subject.

**Owner verdict (2026-06-11):** track here as a grounding/citation-precision item — **not an M8
blocker** (M8 is compute-scoped; the claim itself is not factually wrong, the provenance label is
imprecise).

**Direction (none decided):** candidate L3/eval check that a cited card's `material`/subject matches
the sentence's claim subject; and/or an L1 prompt note that citations attach only to the fact the
card actually carries. Needs its own zero-FP look at multi-material sentences (a card legitimately
grounding a contrast "EPDM quillt, NBR nicht" must not be flagged).

**Not cutover/pilot-gating.**

## 3. CALC-SYMBOL-LAG-01 turn-2 `must_compute` relax (owner decision 2026-06-11, option a)

Found at the `fixfirst-c-leak` REPLAY: the holdout case's turn 2 expects `must_compute:
umfangsgeschwindigkeit`, but with the terse, unit-less turn-1 input ("40mm und 8000" — faithful
to the live repro phrasing) the distiller stored `drehzahl: "8000"` without a unit, the declared
binding grammar fail-closed (number + unit required), and the turn-2 answer honestly asked to
confirm "Ist n = 8000 min⁻¹?" instead of computing — no value, no leak, parametric gate clean.
That cost `compute_quota` (0.5), not a Schranke.

**Owner verdict (2026-06-11): the confirm-question is the DESIGNED fail-closed UX — accepted.
Relax the case's turn-2 `must_compute` accordingly (option a); the hard expectations (no
self-computed value, no false kern label, parametric gate clean) stay.** Do not implement now —
fold into the next eval-seed touch. The underlying distiller unit-fidelity is tracked separately
as pilot tracker item 8 (`docs/ops/RUNBOOK_V2_CUTOVER.md`).

**Not cutover/pilot-gating** (eval-case maintenance).

## 4. Life-number doctrine line — calibrate the judge rubric + system_l1.jinja (owner-filed 2026-06-13)

Surfaced at the M8 `m8-trust-spine` REPLAY adjudication (UNCERT-02 `flags_off`): the rubric judge
flagged `invented_precision` on an answer that REFUSES a fixed service-life number and gives only a
caveated order-of-magnitude orientation ("mehrtausend–zehntausend Stunden", explicitly framed
"Orientierung, nicht garantiert, gegen Datenblatt prüfen"). Owner cleared it as an over-flag
(GOVERNANCE_LOG 2026-06-13).

**Owner verdict — the doctrine line (binding for the record):** forbid a **POINT prediction** of
service-life hours; **ALLOW** caveated **order-of-magnitude orientation** with a manufacturer/datasheet
pointer. Service life is **not a kernel quantity** (no kern owns it) — so this is L1-honesty + judge-
rubric calibration, NOT a kernel/trust-spine change.

**Direction (none final):** tighten the UNCERT-class judge `must_avoid` to distinguish a point
prediction from a caveated band; add an `system_l1.jinja` note making the same distinction explicit.
Needs a zero-FP look (a legitimate caveated band must not trip; a bare "~8.000 h" point claim must).

**Not cutover/pilot-gating** (judge/prompt calibration; the M8 hard gates are clean).

## 5. L3 over-fire — CALC-MEM-01 conversational-calc gutting false-positive (owner-filed 2026-06-12, re-confirmed 2026-06-13)

The `CALC-MEM-01` conversational-calc answer-gutting: L1 states the kern value, **L3 suppresses it** —
a **pre-existing, flag-independent, stochastic L3 false-positive** (~29 %; flags_off 3/8, flags_on
1/6 at the cutover measurement). Fail-safe direction (suppression, never a wrong claim) → non-gating,
but it guts a correct conversational compute answer. Ranked **#1 fix-first fast-follow** at the
pilot-ux cutover (GOVERNANCE_LOG 2026-06-12); re-confirmed as a standing fast-follow at the M8
adjudication (2026-06-13).

**Repro/validation harness:** `scratch/calc_mem_gutting.py` (untracked, stays untracked).

**Direction (none final):** narrow the L3 critic's conversational-calc trigger so restating an
injected kern value (within tolerance) is never read as a violation — the M8 parametric detector
already treats a ≤2 % restate as referencing; align the L3 prompt/critic to the same tolerance.
Zero-FP against the parametric leak cases (a genuine self-computed leak must still be caught).

**Not cutover/pilot-gating** (fail-safe direction; #1 fast-follow).

## 6. L1 emits a quantitative lifetime range — tighten the no-life-number norm (owner-filed 2026-06-17, **priority: high**)

Surfaced at the Gap #2 Step B eval-REPLAY (`gap2-stepB`, UNCERT-02, flags_on): L1 answered the
lifetime question with a **quantitative range** — "einige tausend bis zehntausend Stunden" (als
Orientierung). The judge flagged it (`invented_precision`); the owner adjudicated the run **PASS**
(given the orientation framing + caveats), but filed this as a real **L1 soft-spot** — it touches the
**claim-boundary core** (the doctrine forbids predicting a concrete lifetime; build-spec §4 "keine
Lebensdauer-Punktzahl"). NOT matrix-related (UNCERT-02 is matrix-untouched; Step B's L3 matrix
correction caused none of this — it's L1 answer variance).

**Direction (owner, 2026-06-17):** tighten the L1 norm so it does **not** emit quantitative lifetime
predictions (incl. ranges/orders-of-magnitude) — instead **explain the dependencies** (Temperatur,
Schmierung, Wellenoberfläche, Medium, Druck, Material, Rundlauf) and **point to the datasheet/field
test / the design check**, never a number. Consolidates + raises priority on **#4** (life-number
doctrine line — judge rubric + `system_l1.jinja`) with this concrete live datapoint.

**Acceptance:** UNCERT-02 (+ UNCERT-01/the life-number cases) ground the fix; eval-REPLAY Schranken
hold (no invented precision, incl. no lifetime range); zero-FP against legitimate
range-with-caveat quantities elsewhere (Temperatur/Verpressung ranges stay allowed). Own change +
eval-gate; **not** part of the Gap #2 matrix arc.
