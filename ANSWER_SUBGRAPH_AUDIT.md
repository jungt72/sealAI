# ANSWER_SUBGRAPH_AUDIT

## Scope
Audit target: `backend/app/langgraph_v2/nodes/answer_subgraph/*` with focus on `draft_answer` prompting and `safe_fallback` behavior under low-quality/empty retrieval.

## Step 1: Located Prompts and Subgraph Logic

### Subgraph files
- `backend/app/langgraph_v2/nodes/answer_subgraph/node_prepare_contract.py`
- `backend/app/langgraph_v2/nodes/answer_subgraph/node_draft_answer.py`
- `backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py`
- `backend/app/langgraph_v2/nodes/answer_subgraph/node_targeted_patch.py`
- `backend/app/langgraph_v2/nodes/answer_subgraph/node_finalize.py`
- `backend/app/langgraph_v2/nodes/answer_subgraph/subgraph_builder.py`

### Prompt sources (no Jinja2 templates here)
- `node_draft_answer.py:117-126`
  - System prompt includes: `Use only the provided contract facts.`
  - Human prefix is: `ANSWER CONTRACT:\n...`
- `subgraph_builder.py:70-111`
  - `safe_fallback` does not call an LLM; it reuses `state.draft_text` as final output.

### Search results requested in mission
- `Alpha GmbH`: no match in `backend/app/`
- `contract` in answer subgraph: multiple matches in prompt text/comments/field names
- No Jinja2 template found for `draft_answer` or `safe_fallback`; both are inline Python logic.

## Step 2: Root Cause Analysis

### A) Translation bug (`contract` -> legal "Vertrag")
Primary causes:
- The model is primed with legal-like wording in user-visible generation context:
  - `Use only the provided contract facts.`
  - `ANSWER CONTRACT:`
- In German output mode, "contract" commonly maps to "Vertrag", so the model may render a legal framing.

Amplifiers:
- The rendered payload is a rigid checklist, which can be reinterpreted as a formal/legal doc when semantic grounding is weak.
- Repo tests currently normalize this framing (`ANSWER CONTRACT`, `Laut Vertrag`), reinforcing the pattern.

### B) Fallback leak (why garbage reaches user)
Primary causes:
- `safe_fallback` currently does:
  - `fallback_text = state.draft_text` (subgraph_builder.py:81)
  - then returns that as `final_text/final_answer`
- So when the draft is hallucinated/legalistic, fallback republishes it unchanged.

Amplifiers:
- `rag_low_quality_results` exists only as a log event in `rag_orchestrator.py:987-995`; it is not persisted to `SealAIState.flags`.
- Verification currently extracts expected numbers from full `answer_contract.model_dump_json()` (verify node), which includes numbers from non-user-facing structures (e.g., fact IDs/chunk IDs). This can create persistent `render_mismatch` loops.

## Step 3: Proposed Fix Plan (No Code Applied Yet)

### 1) Prompt/Tone refactor in draft node
File: `backend/app/langgraph_v2/nodes/answer_subgraph/node_draft_answer.py`

Planned changes:
- Rename rendering vocabulary from "contract" to neutral internal naming in prompt payload labels (not data model yet):
  - `ANSWER CONTRACT:` -> `VERIFIED FACT SHEET:`
  - helper naming/comments from "contract draft" to "fact sheet" wording.
- Replace system prompt with sidekick tone and explicit legal ban, e.g.:
  - "Du bist ein hilfreicher technischer Sidekick."
  - "Nutze nur die verifizierten Fakten aus dem Fact Sheet."
  - "Nenne Unsicherheit klar, wenn Evidenz schwach ist."
  - "Schreibe niemals einen rechtlichen Vertrag und verwende keine Vertragsparteien/Vertragsgegenstand-Formulierungen."
- Keep strict numeric/disclaimer constraints, but phrased without "contract".

### 2) Introduce low-quality RAG signal into state
Files:
- `backend/app/mcp/knowledge_tool.py`
- `backend/app/langgraph_v2/nodes/nodes_flows.py`
- optional: `backend/app/services/rag/rag_orchestrator.py`

Planned changes:
- Compute/persist boolean quality marker from retrieval metrics:
  - `k_returned == 0`, or
  - `top_scores[0] < threshold` / configured minimum.
- Write into state flags from material flow:
  - `flags["rag_low_quality_results"] = True|False`
- Keep logging event but also expose machine-readable signal downstream.

### 3) Safe fallback must never echo failed draft in low-confidence mode
File: `backend/app/langgraph_v2/nodes/answer_subgraph/subgraph_builder.py`

Planned changes:
- In `_safe_fallback_node`, compute trigger:
  - `patch_attempts >= MAX_PATCH_ATTEMPTS` OR
  - `flags.rag_low_quality_results is True` OR
  - `retrieval_meta` indicates no hits/low score.
- If trigger true: return fixed sidekick-style message, not `state.draft_text`.
  - Example:
    - "Dazu habe ich in meinen technischen Datenblättern gerade keinen belastbaren Treffer gefunden. Wenn du mir Medium, Temperatur und Druck nennst, suche ich gezielter weiter."
- Only reuse `draft_text` as fallback when it passed a minimal safety check (no legal-contract lexicon + non-empty + non-garbage).

### 4) Optional hardening to reduce false verify loops
File: `backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py`

Planned changes:
- Build `expected_numbers` from user-facing quantitative fields only:
  - `resolved_parameters`, `calc_results`, required disclaimers (if numeric),
  - exclude IDs such as `selected_fact_ids`.
- This avoids `missing_numbers` from chunk/document identifiers and reduces pointless 3x patch loops.

## Test impact (must be updated with implementation)

Files likely requiring updates:
- `backend/app/langgraph_v2/tests/test_audit_traceability.py` (`ANSWER CONTRACT` prefix)
- `backend/app/langgraph_v2/tests/test_concurrency_integrity.py` (`ANSWER CONTRACT` prefix)
- `backend/app/langgraph_v2/tests/test_v3_adversarial_robustness.py` (phrases like `Laut Vertrag`)

New tests to add:
- `safe_fallback` returns sidekick fallback when `patch_attempts==3`.
- `safe_fallback` returns sidekick fallback when `rag_low_quality_results=True`.
- Draft prompt regression test: output must not include legal contract framing tokens in fallback path.

## Implementation order
1. Prompt rename/rewrite in `node_draft_answer.py`.
2. Propagate low-quality retrieval flag into state flags.
3. Replace `_safe_fallback_node` behavior with deterministic sidekick fallback.
4. Adjust verifier number-source scope (optional but recommended).
5. Update/add tests.

## Expected outcome
- No user-visible legal-contract hallucinations under low-quality RAG.
- Fallback tone matches SealAI sidekick behavior.
- Fewer dead-end verify/patch loops on structurally valid but low-evidence responses.
