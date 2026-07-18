"""Trap catalog (Fallen-Katalog) — L3's grounded failure-mode list (build-spec §4).

Derived from the OWNER-AUTHORED ground truth (eval ``must_catch``/``must_avoid`` + principles §2
+ the documented M1 divergences). Two review states with a hard discipline (build-spec §8 — no
"LLM erdet LLM"):

- ``reviewed`` — owner-grounded; MAY drive a block/correction (its ``correct`` fact is asserted).
- ``draft``   — model-proposed, UNREVIEWED; may only FLAG, NEVER correct.

The JSON keeps the two sets in separate blocks (``reviewed`` / ``draft_for_review``); the loader
stamps ``review_state`` from the block it came from, so a draft entry can never claim ``reviewed``.
This module is pure data + a typed loader — no LLM, no network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.core.contracts import HARD_GATES, GroundingFact
from sealai_v2.core.text_match import query_tokens, tag_matches

_CATALOG_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _CATALOG_DIR / "trap_catalog.json"

_REVIEW_STATES = ("reviewed", "draft")


@dataclass(frozen=True)
class TrapEntry:
    id: str
    trigger: str  # human-readable activation condition (selection is server-side, not Jinja logic)
    wrong: tuple[str, ...]  # the wrong claim(s)/mechanism(s) to catch
    correct: str  # the correct fact (owner-grounded for reviewed entries)
    gates: tuple[
        str, ...
    ]  # which hard gate(s) this trap can trip (subset of HARD_GATES)
    provenance: tuple[
        str, ...
    ]  # authored origin (eval:… / principles:§2 / divergence:…)
    review_state: str  # "reviewed" | "draft" — stamped from the JSON block
    tags: tuple[str, ...] = ()
    xrefs: tuple[str, ...] = ()
    # Topic-scoped correction split (OPTIMIZE_BACKLOG #5): for a material/seal-recommending reviewed
    # trap, `correct` is partitioned into a topic-AGNOSTIC general fact (always injected by L3) and a
    # topic-SCOPED recommendation (injected only when the question matches `applies_to`). union(general,
    # recommendation) == correct (faithful slices). Unsplit traps leave these empty and use `correct`.
    correct_general: str = ""
    correct_recommendation: str = ""
    applies_to: tuple[
        str, ...
    ] = ()  # medium/topic tags gating `correct_recommendation`
    # Optional owner-curated high-precision retrieval surface for facts that must reach L1 before
    # drafting. This is deliberately explicit rather than inferred from prose or selected by an LLM.
    retrieval_terms: tuple[str, ...] = ()
    retrieval_min_hits: int = 0
    sources: tuple[str, ...] = ()

    @property
    def reviewed(self) -> bool:
        return self.review_state == "reviewed"

    @property
    def has_split(self) -> bool:
        """True iff this trap carries a topic-scoped recommendation (→ L3 gates it on `applies_to`)."""
        return bool(self.correct_recommendation.strip())

    @property
    def corrective(self) -> bool:
        """Only source-evidenced policy entries may supply a replacement fact."""
        return self.reviewed and bool(self.sources) and bool(self.correct.strip())


@dataclass(frozen=True)
class TrapCatalog:
    entries: tuple[TrapEntry, ...]
    version: str = ""
    source: str = ""

    def reviewed(self) -> tuple[TrapEntry, ...]:
        return tuple(e for e in self.entries if e.review_state == "reviewed")

    def drafts(self) -> tuple[TrapEntry, ...]:
        return tuple(e for e in self.entries if e.review_state == "draft")

    def by_id(self, trap_id: str) -> TrapEntry | None:
        for e in self.entries:
            if e.id == trap_id:
                return e
        return None


def _entry(raw: dict, review_state: str) -> TrapEntry:
    return TrapEntry(
        id=str(raw["id"]),
        trigger=str(raw["trigger"]),
        wrong=tuple(str(w) for w in raw["wrong"]),
        correct=str(raw.get("correct", "")),
        gates=tuple(str(g) for g in raw["gates"]),
        provenance=tuple(str(p) for p in raw["provenance"]),
        review_state=review_state,
        tags=tuple(str(t) for t in raw.get("tags", [])),
        xrefs=tuple(str(x) for x in raw.get("xrefs", [])),
        correct_general=str(raw.get("correct_general", "")),
        correct_recommendation=str(raw.get("correct_recommendation", "")),
        applies_to=tuple(str(a) for a in raw.get("applies_to", [])),
        retrieval_terms=tuple(str(t) for t in raw.get("retrieval_terms", [])),
        retrieval_min_hits=int(raw.get("retrieval_min_hits", 0)),
        sources=tuple(str(source) for source in raw.get("sources", [])),
    )


def load_traps(path: Path | None = None) -> TrapCatalog:
    """Load + validate the catalog. ``review_state`` is taken from the BLOCK (``reviewed`` vs
    ``draft_for_review``) — never from inside an entry — so the discipline cannot be bypassed."""
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    entries: list[TrapEntry] = []
    seen: set[str] = set()
    for block, state in (("reviewed", "reviewed"), ("draft_for_review", "draft")):
        for raw in data.get(block, []):
            e = _entry(raw, state)
            if e.id in seen:
                raise ValueError(f"duplicate trap id: {e.id}")
            seen.add(e.id)
            if not all(g in HARD_GATES for g in e.gates):
                raise ValueError(f"{e.id}: gates {e.gates} not all in {HARD_GATES}")
            if not e.gates:
                raise ValueError(f"{e.id}: at least one gate required")
            if not e.wrong:
                raise ValueError(f"{e.id}: at least one 'wrong' pattern required")
            if not e.provenance:
                raise ValueError(
                    f"{e.id}: provenance is mandatory (owner-grounding audit)"
                )
            # Integrity: a reviewed entry MUST carry a correct fact (it may assert/correct);
            # a draft entry must NOT be relied on to correct, so its correct fact is optional.
            if e.review_state == "reviewed" and not e.correct.strip():
                raise ValueError(
                    f"{e.id}: reviewed entry must have a non-empty 'correct' fact"
                )
            # Split discipline (OPTIMIZE_BACKLOG #5): a topic-scoped recommendation is only usable with
            # its topic-agnostic general fact AND its applies_to topic — a split is complete or absent.
            if e.correct_recommendation.strip():
                if not e.correct_general.strip():
                    raise ValueError(
                        f"{e.id}: correct_recommendation requires a non-empty correct_general"
                    )
                if not e.applies_to:
                    raise ValueError(
                        f"{e.id}: correct_recommendation requires a non-empty applies_to"
                    )
            if e.retrieval_terms:
                if e.review_state != "reviewed":
                    raise ValueError(
                        f"{e.id}: only reviewed traps may define retrieval_terms"
                    )
                if not 1 <= e.retrieval_min_hits <= len(e.retrieval_terms):
                    raise ValueError(
                        f"{e.id}: retrieval_min_hits must be within retrieval_terms"
                    )
            elif e.retrieval_min_hits:
                raise ValueError(f"{e.id}: retrieval_min_hits requires retrieval_terms")
            entries.append(e)
    if not entries:
        raise ValueError("trap catalog is empty")
    return TrapCatalog(
        entries=tuple(entries),
        version=str(data.get("version", "")),
        source=str(data.get("source", "")),
    )


def retrieve_reviewed_trap_facts(
    catalog: TrapCatalog | None, question: str, *, k: int = 3
) -> tuple[GroundingFact, ...]:
    """Return high-precision reviewed policy facts relevant before generation.

    Only entries with an explicit owner-curated retrieval surface participate. Draft traps and
    prose-derived similarity are excluded, preserving the "no LLM grounds LLM" boundary.
    """
    if catalog is None or k <= 0:
        return ()
    q_norm = (question or "").lower()
    q_tokens = query_tokens(q_norm)
    matches: list[tuple[int, TrapEntry]] = []
    for entry in catalog.reviewed():
        if not entry.corrective:
            continue
        if not entry.retrieval_terms:
            continue
        hits = reviewed_trap_retrieval_hits(entry, q_norm, q_tokens=q_tokens)
        if hits >= entry.retrieval_min_hits:
            matches.append((hits, entry))
    matches.sort(key=lambda item: (-item[0], item[1].id))
    return tuple(
        GroundingFact(
            text=entry.correct,
            quelle=(
                f"Geprüfter Fallen-Katalog · {entry.id} "
                f"({', '.join(entry.provenance)})"
            ),
            card_id=entry.id,
            sources=entry.sources,
            kind="trap",
        )
        for _hits, entry in matches[:k]
    )


def reviewed_trap_retrieval_hits(
    entry: TrapEntry, question: str, *, q_tokens: set[str] | None = None
) -> int:
    """Count owner-curated activation terms for one high-precision trap.

    L1 prefetch and L3 catalog scoping share this exact matcher so a policy fact cannot be
    considered relevant before generation but off-topic during verification, or vice versa.
    Entries without an explicit retrieval surface return zero and remain governed by the broad
    verifier catalog behavior.
    """
    q_norm = (question or "").lower()
    tokens = q_tokens if q_tokens is not None else query_tokens(q_norm)
    return sum(1 for term in entry.retrieval_terms if tag_matches(term, tokens, q_norm))


def reviewed_trap_retrieval_matches(entry: TrapEntry, question: str) -> bool:
    """Whether an explicitly scoped reviewed trap is active for this question."""
    return bool(entry.retrieval_terms) and (
        reviewed_trap_retrieval_hits(entry, question) >= entry.retrieval_min_hits
    )
