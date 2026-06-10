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
