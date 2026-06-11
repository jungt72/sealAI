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
