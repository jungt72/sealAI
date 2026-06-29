"""OWNER-CURATED contract policy (INC-NARRATOR-CONTRACT Phase 1, step 2).

This is the ONLY CONTENT in the contract path — it is NEVER model-generated. The phrasings below are a
VORLÄUFIG draft (the doctrine: build the machinery + a draft, the owner RATIFIES before the flag flips).
Everything else in ``response_contract`` is deterministic ASSEMBLY over existing kernel outputs.

- ``forbidden_always``: authority/provenance markers a grounded narrator must NEVER use — the exact leak
  class the n=3 probe surfaced (Mistral Large 3: "Belegter Befund" / "Richtwerte aus Fachliteratur" /
  "typisch"). ALWAYS forbidden, every status.
- ``forbidden_by_status``: suitability/clearance formulas forbidden only where the status does not warrant
  them (no "geeignet" / "freigegeben" in OUT_OF_SCOPE or NEEDS_CLARIFICATION; "freigegeben"/"garantiert"
  never — the final release is always the manufacturer's).
- ``required_clauses``: the verbatim safety/honesty clauses that MUST appear per status.
- ``material_vocab``: the reviewed material families — used to police "named a material the grounding
  never mentioned" (the guard, Phase 3). Mirrors the seed Fachkarten families.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Always forbidden — fabricated authority / provenance (the probe leak class). Lowercased; matched
# case-insensitively by the guard (Phase 3).
FORBIDDEN_ALWAYS: tuple[str, ...] = (
    "belegt",
    "belegter befund",
    "richtwert",
    "richtwerte",
    "fachliteratur",
    "typisch",
    "typischerweise",
    "bewährt",
    "erfahrungsgemäß",
    "faustregel",
    "allgemein bekannt",
    "in der praxis üblich",
)

# Status-conditional bans. The final Compound/Werkstoff release is ALWAYS the manufacturer's, so
# "freigegeben"/"garantiert" are forbidden in every status; "geeignet"/"empfohlen"/"passt" are only
# allowed where the grounded status warrants a recommendation.
FORBIDDEN_BY_STATUS: dict[str, tuple[str, ...]] = {
    "OUT_OF_SCOPE": (
        "geeignet",
        "empfohlen",
        "empfehle",
        "passt",
        "freigegeben",
        "unbedenklich",
        "kein problem",
    ),
    "NEEDS_CLARIFICATION": (
        "geeignet",
        "empfohlen",
        "empfehle",
        "passt",
        "freigegeben",
        "unbedenklich",
    ),
    "COVERED_CAUTION": ("freigegeben", "garantiert", "in jedem fall", "unbedenklich"),
    "COVERED_RECOMMENDATION": ("freigegeben", "garantiert", "in jedem fall"),
}

# Verbatim clauses that MUST appear, per status.
REQUIRED_CLAUSES: dict[str, tuple[str, ...]] = {
    "OUT_OF_SCOPE": (
        "Hierzu liegt mir keine geprüfte Werkstofffreigabe vor.",
        "Bitte den Werkstoff für diesen Anwendungsfall beim Hersteller absichern.",
    ),
    "NEEDS_CLARIFICATION": (),  # the templated clarification clause is prepended from missing_fields
    "COVERED_CAUTION": (
        "Dies ist eine bedingte Einschätzung, keine Freigabe — die finale "
        "Compound-Freigabe trifft der Hersteller.",
    ),
    "COVERED_RECOMMENDATION": (
        "Die finale Compound-/Werkstofffreigabe trifft der Hersteller.",
    ),
}

CLARIFICATION_TEMPLATE = "Ohne {fields} ist keine belastbare Auslegung möglich — bitte ergänzen."
MISSING_INPUT_TEMPLATE = "Für die belastbare Auslegung fehlt noch: {fields}."

# Reviewed material families (seed Fachkarten). Owner-curated; extend as the knowledge grows.
MATERIAL_VOCAB: tuple[str, ...] = (
    "FFKM",
    "FKM",
    "EPDM",
    "HNBR",
    "NBR",
    "PTFE",
    "TPU",
    "PUR",
    "PU",
    "POM",
    "PEEK",
    "VMQ",
    "Silikon",
    "ACM",
    "AEM",
    "CR",
    "SBR",
    "SiC",
    "Glasfaser-PTFE",
)


@dataclass
class ContractPolicy:
    """The owner-curated policy bundle handed to ``build_contract``. Passed as a parameter (not a hidden
    global) so the assembler stays pure + fixture-testable."""

    forbidden_always: tuple[str, ...] = FORBIDDEN_ALWAYS
    forbidden_by_status: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(FORBIDDEN_BY_STATUS)
    )
    required_clauses: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(REQUIRED_CLAUSES)
    )
    clarification_template: str = CLARIFICATION_TEMPLATE
    missing_input_template: str = MISSING_INPUT_TEMPLATE
    material_vocab: tuple[str, ...] = MATERIAL_VOCAB


DEFAULT_POLICY = ContractPolicy()
