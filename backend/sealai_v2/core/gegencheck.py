"""Pure Gegencheck verdict kernel: (material × medium) -> disqualified-or-not dict.

No I/O, no LLM, no mutation, no float literals, no narration prose.
Consumes the §4 Verträglichkeitsmatrix via its existing public APIs
(``query()`` for matching + the tenant gate, ``by_id()`` for the verdict) — it
never changes the matrix and never rebuilds the matcher. The catalog is INJECTED
so ``core`` stays I/O-free (the caller owns ``load_matrix()``).

Owner doctrine E4-1: this kernel may DISQUALIFY, never QUALIFY. The headline is
always the binary ``disqualified``; the only non-disqualifying outcome is the
*absence* of a documented incompatibility (``basis`` is an opaque state marker,
never an affirmative "passt/geeignet"). ``reason``/``condition``/``source`` are
surfaced verbatim from the reviewed matrix cell — grounded data, never
kernel-formulated. For a *bedingt* verdict the condition text travels INLINE
(``condition``), because that condition ("works under condition X — verify") is
the single most valuable Gegencheck output and must not be lost behind a bare
citation; it is its OWN field (not ``reason``), so the conditional category is
never confused with a disqualification reason. IS wired (ungated, every turn):
called from ``pipeline/stages.py::gegencheck`` -> ``pipeline.py`` (Modus E), the
verdict reaches ``PipelineResult.gegencheck`` and the ``/api/v2/chat`` response.
"""

from __future__ import annotations

from sealai_v2.knowledge.matrix import (
    CompatibilityMatrixCatalog,
    InProcessCompatibilityMatrix,
)


def evaluate_gegencheck(
    material: str,
    medium: str | None,
    *,
    tenant: str,
    catalog: CompatibilityMatrixCatalog,
) -> dict:
    """Check an existing seal's ``material`` against ``medium`` via the matrix.

    Returns a small structured verdict (never prose):
    - ``unvertraeglich`` (any matched cell) ->
      ``{"disqualified": True, "reason": <cell text>, "source": <cell ref>}``
    - ``bedingt`` (no incompatible cell, ≥1 conditional) ->
      ``{"disqualified": False, "basis": "matrix_conditional",
         "condition": <cell text>, "source": <cell ref>}`` — the grounded
      condition travels inline (verbatim cell begründung), never lost behind the
      bare citation, never kernel-formulated.
    - ``vertraeglich`` (all matched cells compatible) ->
      ``{"disqualified": False, "basis": "matrix_compatible"}``
    - no matched cell -> ``{"disqualified": False, "basis": "no_matrix_data"}``
    - no/blank ``medium`` -> ``{"disqualified": False, "basis": "no_medium"}``

    E4-1 disqualify-lean fold: with several cells returned (``query`` yields up to
    k, strongest first), ANY ``unvertraeglich`` wins the verdict, else ANY
    ``bedingt`` marks conditional, else compatible. ``reason``/``condition``/
    ``source`` come from the strongest cell of the winning category.
    """
    if medium is None or not str(medium).strip():
        return {"disqualified": False, "basis": "no_medium"}

    # query() reuses the deterministic scope-tag matcher AND enforces the P0 tenant
    # gate; building over the injected catalog does no I/O.
    facts = InProcessCompatibilityMatrix(catalog).query(
        tenant_id=tenant,
        query_text=f"{material} {medium}",
    )
    if not facts:
        return {"disqualified": False, "basis": "no_matrix_data"}

    # Recover the verdict enum that query() drops, via the existing by_id() accessor.
    # Facts stay in query's strongest-first order, so the first match of a category
    # is the strongest one.
    incompatible = None
    conditional = None
    for fact in facts:
        cell = catalog.by_id(fact.card_id)
        if cell is None:
            continue
        if cell.bewertung == "unvertraeglich" and incompatible is None:
            incompatible = fact
        elif cell.bewertung == "bedingt" and conditional is None:
            conditional = fact

    if incompatible is not None:
        return {
            "disqualified": True,
            "reason": incompatible.text,
            "source": incompatible.quelle,
        }
    if conditional is not None:
        return {
            "disqualified": False,
            "basis": "matrix_conditional",
            "condition": conditional.text,
            "source": conditional.quelle,
        }
    return {"disqualified": False, "basis": "matrix_compatible"}
