"""Response-contract kernel (V2.2 / INC-NARRATOR-CONTRACT Phase 1). Deterministic, no LLM, no I/O.

The contract is the DETERMINISTIC bound on what L1 may say. The kernel owns the facts; the contract
turns one turn's grounded evidence into a CLOSED answer-space:

  - ``status``          — the SS-coupled answer mode, from the coverage gate (+ a clarification layer);
  - ``allowed_claims``  — the ONLY technical statements L1 may render, each with its provenance id +
                          sources (so the Phase-3 guard maps a rendered sentence -> exactly one claim);
  - ``required_clauses``— clauses that MUST appear (safety / "keine Freigabe" / "keine Auslegung ohne X");
  - ``missing_fields``  — the clarifiable input gaps (missing medium / missing calc inputs);
  - ``allowed_materials``/``allowed_values`` — the only materials / numbers that may be named;
  - ``forbidden_phrases``— fabricated-authority markers (always) + status-forbidden suitability formulas.

L1 becomes a RENDERER of this contract (Phase 2); a claim-level code guard enforces sentence->claim
coverage against it (Phase 3). This module is PURE and, in Phase 1, UNWIRED+INERT: building the contract
changes no prod behaviour (the L1 prompt is untouched; the contract is attached to the result, not
consumed). The two pieces of CONTENT (forbidden phrases + required clauses) are OWNER-CURATED in
``response_contract_policy`` — everything here is deterministic ASSEMBLY over outputs that already exist
(the coverage dict, the GroundingFacts, the gegencheck verdict, the CalcResult).

v1 SCOPE: the contract is built for material x medium SUITABILITY turns (a gegencheck verdict is present)
— the surface where the probe showed L1 leaks. Other turn types (open recommendation, decode) return
None here and are an owner-gated later extension.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sealai_v2.core.contracts import CalcResult, GroundingFact
from sealai_v2.core.response_contract_policy import DEFAULT_POLICY, ContractPolicy

# ── contract status (the SS-coupled answer mode) ────────────────────────────────────────────────
STATUS_OUT_OF_SCOPE = "OUT_OF_SCOPE"
STATUS_NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
STATUS_COVERED_CAUTION = "COVERED_CAUTION"
STATUS_COVERED_RECOMMENDATION = "COVERED_RECOMMENDATION"

# coverage_status (core/coverage.py) -> contract status. A grounded NO (disqualified -> coverage IN)
# maps to COVERED_RECOMMENDATION: the MODE is assertive-because-grounded; the CONTENT is a negative
# recommendation. Clarification + the OUT/NEEDS split are derived in ``_contract_status`` from the
# gegencheck basis (no_medium = a clarifiable gap, not a knowledge gap).
_COVERAGE_TO_STATUS = {
    "in_envelope": STATUS_COVERED_RECOMMENDATION,
    "partial_envelope": STATUS_COVERED_CAUTION,
    "analog_only": STATUS_COVERED_CAUTION,
    "out_of_envelope": STATUS_OUT_OF_SCOPE,
}

# The calc engine emits NotComputed(calc_id, reason) with reasons like
# "nicht berechenbar: Eingaben fehlen (p_bar)" (core/calc/evaluator.py). A missing INPUT is a
# clarifiable gap; "outside validity" / "N/A" reasons are NOT clarification triggers.
_MISSING_INPUT_RE = re.compile(r"(?:Eingaben?\s+fehlen|fehlt|fehlen)\b", re.IGNORECASE)
_FIELD_RE = re.compile(r"\(([^)]+)\)")


@dataclass(frozen=True)
class AllowedClaim:
    """One technical statement L1 is ALLOWED to render — carries its provenance id + sources so the
    guard can map a rendered sentence back to exactly one grounded claim (Phase 3)."""

    id: str  # card_id — source Fachkarte id / matrix cell id (the provenance ref)
    text: str  # the grounded claim text (the content L1 may rephrase, never exceed)
    severity: str  # "disqualify" | "caution" | "info"
    sources: tuple[
        str, ...
    ] = ()  # owner-verified primary sources (Parker handbook, ISO ...)
    kind: str = "card"  # provenance lane: "card" (Fachkarte) | "matrix" (Verträglichkeitsmatrix)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "severity": self.severity,
            "sources": list(self.sources),
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ResponseContract:
    status: str
    allowed_claims: tuple[AllowedClaim, ...]
    required_clauses: tuple[str, ...]
    missing_fields: tuple[str, ...]
    allowed_materials: tuple[str, ...]
    allowed_values: tuple[dict, ...]
    forbidden_phrases: tuple[str, ...]
    coverage_status: str  # the raw coverage_status, kept for the trace / SS9 flywheel

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "coverage_status": self.coverage_status,
            "allowed_claims": [c.to_dict() for c in self.allowed_claims],
            "required_clauses": list(self.required_clauses),
            "missing_fields": list(self.missing_fields),
            "allowed_materials": list(self.allowed_materials),
            "allowed_values": list(self.allowed_values),
            "forbidden_phrases": list(self.forbidden_phrases),
        }


def _missing_fields(calc: CalcResult | None) -> list[str]:
    if calc is None:
        return []
    fields: list[str] = []
    for nc in calc.not_computed:
        reason = nc.reason or ""
        if not _MISSING_INPUT_RE.search(reason):
            continue
        for grp in _FIELD_RE.findall(reason):
            for tok in re.split(r"[,;]\s*", grp):
                tok = tok.strip()
                if tok and tok not in fields:
                    fields.append(tok)
    return fields


def _contract_status(coverage_status: str, basis: str | None) -> str:
    # A missing medium is the irreducible clarification: chemistry can't even be checked -> ask first.
    if basis == "no_medium":
        return STATUS_NEEDS_CLARIFICATION
    return _COVERAGE_TO_STATUS.get(coverage_status, STATUS_OUT_OF_SCOPE)


def _severity(gf: GroundingFact, disqualified: bool, basis: str | None) -> str:
    # Coarse v1: the case-level gegencheck verdict tags the MATRIX facts; card facts are supporting
    # info. (The per-claim 8-value epistemics live on the Fachkarte Claim, not propagated to the
    # GroundingFact — a later refinement, owner-tracked.)
    if gf.kind == "matrix":
        if disqualified:
            return "disqualify"
        if basis == "matrix_conditional":
            return "caution"
    return "info"


def _allowed_claims(
    grounding_facts: tuple[GroundingFact, ...], disqualified: bool, basis: str | None
) -> tuple[AllowedClaim, ...]:
    return tuple(
        AllowedClaim(
            id=gf.card_id,
            text=gf.text,
            severity=_severity(gf, disqualified, basis),
            sources=gf.sources,
            kind=gf.kind,
        )
        for gf in grounding_facts
    )


def _allowed_materials(
    claims: tuple[AllowedClaim, ...], material_vocab: tuple[str, ...]
) -> tuple[str, ...]:
    # Only materials the GROUNDED claims actually name may be named in the render (the guard's
    # "invented material" prefilter, Phase 3). Vocab is owner-curated; longest-first so "Glasfaser-PTFE"
    # wins over "PTFE" and "FFKM" over "FKM".
    blob = " ".join(c.text for c in claims)
    found: list[str] = []
    for m in sorted(material_vocab, key=len, reverse=True):
        if re.search(rf"\b{re.escape(m)}\b", blob, re.IGNORECASE) and m not in found:
            found.append(m)
    return tuple(found)


def _allowed_values(calc: CalcResult | None) -> tuple[dict, ...]:
    if calc is None:
        return ()
    return tuple(
        {"name": cv.name, "value": cv.value, "unit": cv.unit, "calc_id": cv.calc_id}
        for cv in calc.computed
    )


def _required_clauses(
    status: str, missing_fields: list[str], policy: ContractPolicy
) -> tuple[str, ...]:
    clauses = list(policy.required_clauses.get(status, ()))
    fields = ", ".join(missing_fields)
    if status == STATUS_NEEDS_CLARIFICATION and missing_fields:
        clauses.insert(0, policy.clarification_template.format(fields=fields))
    elif missing_fields and status in (
        STATUS_COVERED_CAUTION,
        STATUS_COVERED_RECOMMENDATION,
    ):
        # A grounded verdict stands, but the design needs the missing inputs — say so, don't suppress.
        clauses.append(policy.missing_input_template.format(fields=fields))
    return tuple(clauses)


def _forbidden_phrases(status: str, policy: ContractPolicy) -> tuple[str, ...]:
    out = list(policy.forbidden_always)
    for p in policy.forbidden_by_status.get(status, ()):
        if p not in out:
            out.append(p)
    return tuple(out)


def build_contract(
    *,
    coverage: dict | None,
    grounding_facts: tuple[GroundingFact, ...],
    gegencheck_verdict: dict | None,
    calc: CalcResult | None,
    policy: ContractPolicy = DEFAULT_POLICY,
) -> ResponseContract | None:
    """Assemble the deterministic answer-contract from a turn's grounded evidence. Returns None for
    non-suitability turns (no gegencheck verdict) — the v1 scope is material x medium. PURE."""
    if not gegencheck_verdict:
        return None
    coverage_status = (coverage or {}).get("status", "out_of_envelope")
    basis = gegencheck_verdict.get(
        "basis"
    )  # None when disqualified ({"disqualified", "reason", ...})
    disqualified = bool(gegencheck_verdict.get("disqualified"))

    missing = _missing_fields(calc)
    if basis == "no_medium" and "Medium" not in missing:
        missing.insert(0, "Medium")

    status = _contract_status(coverage_status, basis)
    claims = _allowed_claims(grounding_facts, disqualified, basis)
    return ResponseContract(
        status=status,
        allowed_claims=claims,
        required_clauses=_required_clauses(status, missing, policy),
        missing_fields=tuple(missing),
        allowed_materials=_allowed_materials(claims, policy.material_vocab),
        allowed_values=_allowed_values(calc),
        forbidden_phrases=_forbidden_phrases(status, policy),
        coverage_status=coverage_status,
    )
