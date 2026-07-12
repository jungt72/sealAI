"""Memory context assembler — sealingAI Memory Architecture V1.0, Patch 8.

``build_context_bundle()`` combines Patch 6's ``retrieve_memory()`` + Patch 7's ``usage_for()``
into a bounded ``MemoryContextBundle``. That function is PURE (no I/O) — it operates on an
already-fetched list of ``MemoryItem``s. ``MemoryContextService`` (bottom of this file) is the
I/O-touching wrapper the pipeline actually holds: one injected dependency object with a single
async method, mirroring ``MediumResearcher``'s shape exactly (see ``pipeline/pipeline.py``).

SCOPING NOTE (deliberate, not an oversight): this patch computes and exposes the bundle via
``PipelineResult``/the chat response's ``context_sources`` — structurally L1-NEUTRAL, exactly like
Medium Intelligence, when the flag is off (the service is never constructed, the field stays None).
It does NOT yet render the bundle into the L1 prompt text (``prompts/system_l1.jinja``/
``PromptAssembler``) — actually injecting memory content into what the LLM sees is a materially
higher-risk change than exposing it via the API and deserves its own dedicated eval-verification
pass before it ships, not bundled into this patch. "Memory unter Kernel/RAG priorisieren" (the
source prompt's own ordering requirement) is therefore NOT yet fulfilled by this patch — it's the
next, separately-gated step once this exposure surface has been reviewed.

Doctrine (source prompt, Patch 8 + the product-doctrine preamble):
- Max 8 items, max 750 tokens, max 10% of the total prompt budget (when a total budget is known —
  see ``build_context_bundle``'s ``prompt_token_budget`` param; the 10% cap only applies when the
  caller actually knows the total, otherwise only the flat 750-token cap holds).
- Memory is priced BELOW Kernel/RAG in the caller's prompt assembly order — this module does not
  enforce that ordering itself (it has no visibility into the rest of the prompt), it only produces
  the bounded memory slice; the CALLER (the actual prompt assembler, a later wiring step) is
  responsible for placing it after Kernel/RAG content, never before.
- Items whose policy usage is NEVER are dropped before the budget is even computed — a NEVER item
  must never consume any part of the token budget, not even to be immediately discarded.
- ``context_sources`` (the per-item provenance the API response surfaces, source prompt's PATCH 9
  Right Rail input) is built from the SAME bundle, so what's rendered into the prompt and what's
  shown to the user as "used context" can never silently diverge.

Token counting is a plain character-based heuristic (len(content) // 4, ~4 chars/token — a standard
rule-of-thumb for GPT-style tokenizers on English/German text), NOT an exact tokenizer count. This
is a deliberate choice: adding a real tokenizer dependency (e.g. tiktoken) for a budget APPROXIMATION
(not a billing-exact count) isn't justified, and this codebase's own convention (AGENTS.md) is not to
add new dependencies without the owner explicitly asking. Flagged here, not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

from sealai_v2.memory.curated import MemoryItem
from sealai_v2.memory.policy import MemoryUsage, usage_for

MAX_ITEMS = 8
MAX_TOKENS = 750
MAX_PROMPT_FRACTION = 0.10

_CHARS_PER_TOKEN_ESTIMATE = 4


def _estimate_tokens(text: str) -> int:
    """Character-based heuristic — see module docstring for why this isn't an exact tokenizer."""
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)


@dataclass(frozen=True)
class MemoryContextEntry:
    item_id: str
    content: str
    usage: MemoryUsage
    scope: (
        str  # .value already resolved — a rendering-facing shape, not the domain enum
    )
    type: str
    estimated_tokens: int


@dataclass(frozen=True)
class MemoryContextBundle:
    """The bounded, budget-respecting slice a prompt template may render. ``entries`` is already in
    the final render order (Qdrant relevance order, survivors of both policy + budget filtering).
    ``context_sources`` mirrors ``entries`` 1:1 — built from the SAME data, so the Right Rail (a
    later patch's UI) can never show something different from what actually reached the prompt."""

    entries: tuple[MemoryContextEntry, ...]
    total_estimated_tokens: int

    @property
    def is_empty(self) -> bool:
        return not self.entries

    @property
    def context_sources(self) -> tuple[dict, ...]:
        return tuple(
            {
                "item_id": e.item_id,
                "usage": e.usage.value,
                "scope": e.scope,
                "type": e.type,
            }
            for e in self.entries
        )


def build_context_bundle(
    items: list[MemoryItem],
    *,
    max_items: int = MAX_ITEMS,
    max_tokens: int = MAX_TOKENS,
    prompt_token_budget: int | None = None,
) -> MemoryContextBundle:
    """``items`` should already be in relevance order (Qdrant rank, post Patch-6-revalidation) — this
    function does not re-rank, it only filters (policy) and truncates (item count + token budget).

    The effective token cap is ``min(max_tokens, prompt_token_budget * MAX_PROMPT_FRACTION)`` when
    ``prompt_token_budget`` is given (the 10% rule), else just ``max_tokens``.
    """
    effective_token_cap = max_tokens
    if prompt_token_budget is not None:
        effective_token_cap = min(
            max_tokens, int(prompt_token_budget * MAX_PROMPT_FRACTION)
        )

    entries: list[MemoryContextEntry] = []
    running_tokens = 0
    for item in items:
        if len(entries) >= max_items:
            break
        usage = usage_for(item)
        if usage == MemoryUsage.NEVER:
            continue  # dropped before consuming any budget, see module docstring
        tokens = _estimate_tokens(item.content)
        if running_tokens + tokens > effective_token_cap:
            continue  # this one doesn't fit — try the next (lower-relevance) item, don't just stop
        entries.append(
            MemoryContextEntry(
                item_id=item.id,
                content=item.content,
                usage=usage,
                scope=item.scope.value,
                type=item.type.value,
                estimated_tokens=tokens,
            )
        )
        running_tokens += tokens

    return MemoryContextBundle(
        entries=tuple(entries), total_estimated_tokens=running_tokens
    )


class MemoryContextService:
    """The single injected dependency ``Pipeline`` holds for this feature — mirrors
    ``MediumResearcher``'s shape (one object, one async method) so the pipeline-wiring diff stays
    small and structurally identical to an already-shipped, reviewed pattern. Fails safe: any
    retrieval error yields an empty bundle rather than raising into the turn (never breaks a turn
    over a memory-lookup failure — memory is context, not a hard dependency)."""

    def __init__(
        self,
        *,
        store,
        qdrant_client,
        embedder,
        collection: str = "sealai_v2_memory",
    ) -> None:
        self._store = store
        self._qdrant_client = qdrant_client
        self._embedder = embedder
        self._collection = collection

    async def assemble(
        self, query: str, *, tenant_id: str, now: str
    ) -> MemoryContextBundle:
        import asyncio
        import logging

        from sealai_v2.memory.retrieval import retrieve_memory

        try:
            items = await asyncio.to_thread(
                retrieve_memory,
                query,
                tenant_id=tenant_id,
                qdrant_client=self._qdrant_client,
                embedder=self._embedder,
                store=self._store,
                now=now,
                k=MAX_ITEMS,
                collection=self._collection,
            )
        except Exception as exc:  # noqa: BLE001 — fail safe to empty; never break a turn
            logging.getLogger("sealai_v2.memory").warning(
                "memory context retrieval failed (%s) — empty bundle", exc
            )
            return MemoryContextBundle(entries=(), total_estimated_tokens=0)
        return build_context_bundle(list(items))
