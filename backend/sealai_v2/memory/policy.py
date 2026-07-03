"""Memory policy — sealingAI Memory Architecture V1.0, Patch 7.

Given an already-revalidated (Patch 6) ``MemoryItem``, what usage is it allowed for? This is a
SECOND, finer-grained gate on top of Patch 6's coarse "is this even safe to surface" check —
``revalidate()`` answers WHETHER an item may be considered at all; ``usage_for()`` answers HOW.

Doctrine (source prompt, Patch 7 + the product-doctrine preamble):
- preference               -> style_only (never a technical input)
- implicit_context STATUS  -> ask_clarifying_question_only (regardless of the item's type — an
  unconfirmed hint stays a question, never a recommendation, until the user reacts)
- technical_note           -> context_only, never a recommendation
- case_parameter           -> ONLY when CONFIRMED and CASE-scoped; anything else (unconfirmed, or
  confirmed but a different scope) is NEVER usable as this type
- rejected/deprecated/deleted/purged -> never allowed (fail-closed defense in depth; Patch 6's
  revalidate() should already have excluded these before policy is ever consulted)

Structural note, deliberate: ``MemoryUsage`` has NO "recommendation" or "full-trust" value. That
omission IS the enforcement of "Memory darf technische Eignung niemals allein begründen" — there is
no code path through this policy that can hand a caller a green light to recommend from memory
alone; the strongest grant is CONTEXT_ONLY.

Open flag carried from Patch 1: ``MemoryType``'s three values (preference/technical_note/
case_parameter) were INFERRED from this same source text, not a literal enumerated spec — this
patch is where that inference actually starts driving real behavior. Still awaiting explicit owner
confirmation (flagged again here, not just in Patch 1's PR, since this is the point it stops being
free-standing and starts gating what the assistant may say).
"""

from __future__ import annotations

from enum import Enum

from sealai_v2.memory.curated import MemoryItem, MemoryScope, MemoryStatus, MemoryType


class MemoryUsage(str, Enum):
    STYLE_ONLY = "style_only"
    ASK_CLARIFYING_QUESTION_ONLY = "ask_clarifying_question_only"
    CONTEXT_ONLY = "context_only"
    NEVER = "never"


def usage_for(item: MemoryItem) -> MemoryUsage:
    if not item.is_injectable:
        return MemoryUsage.NEVER  # fail-closed defense in depth (see module docstring)

    if item.status == MemoryStatus.IMPLICIT_CONTEXT:
        return (
            MemoryUsage.ASK_CLARIFYING_QUESTION_ONLY
        )  # status overrides type, see docstring

    if item.type == MemoryType.CASE_PARAMETER:
        if item.status == MemoryStatus.CONFIRMED and item.scope == MemoryScope.CASE:
            return MemoryUsage.CONTEXT_ONLY
        return MemoryUsage.NEVER  # fails the "nur confirmed und nur case scope" gate

    if item.type == MemoryType.PREFERENCE:
        return MemoryUsage.STYLE_ONLY

    if item.type == MemoryType.TECHNICAL_NOTE:
        return MemoryUsage.CONTEXT_ONLY

    return (
        MemoryUsage.NEVER
    )  # unrecognized type — fail-closed default, never a silent allow
