"""Legal-by-Design Phase E (Goal 10): a terminology lint over production code, using
``core.legal_doctrine.FORBIDDEN_STATUS_TERMS`` — the SAME list used for the L1-prompt-hardening
doctrine (Phase D) and the UI-vocabulary guidance (Goal 8), so this test, the prompt, and the docs
can never silently drift apart into three different "forbidden word" lists.

Scope deliberately narrower than the full FORBIDDEN_STATUS_TERMS map: "sicher" is excluded from the
SCANNED subset below — it is common German for both "safe" (the risky sense) and "certain/make sure"
(completely benign, e.g. "stelle sicher, dass…"), so a bare word-boundary scan for it would be pure
noise, not a real check. The other seven terms are specific enough to scan directly.

``eval/`` is excluded (fixtures legitimately contain WRONG example phrasing to score against — that
is the whole point of an eval question, not a violation) and ``tests/`` is excluded (this module's
own test, plus any fixture/assertion string, would otherwise trip on itself).

The remaining ALLOWLIST entries are every current hit in ``backend/sealai_v2`` outside those two
excluded trees, individually reviewed (Legal-by-Design Phase E audit, 2026-07-08) and confirmed
safe — each either negates the term ("keine Empfehlung"), IS the existing forbidden-phrase
enforcement list this lint mirrors (core/output_guard.py, core/response_contract_policy.py), is a
structural field hardcoded to False (produktspec's G1 ``freigegeben`` invariant), or matches
unrelated meaning ("owner-approved" describing a unit-spelling convention). A NEW hit outside this
allowlist fails the test — that is the point.
"""

from __future__ import annotations

from pathlib import Path

from sealai_v2.core.legal_doctrine import FORBIDDEN_STATUS_TERMS

_ROOT = Path(__file__).resolve().parent.parent  # backend/sealai_v2/
_EXCLUDED_DIRS = {"tests", "eval", "__pycache__"}
_SCANNED_TERMS = tuple(
    t for t in FORBIDDEN_STATUS_TERMS if t != "sicher"
)  # see module docstring

# file path (relative to backend/sealai_v2/) -> every already-reviewed hit is safe in this file.
_ALLOWLIST_FILES = {
    "api/routes/contribute.py",  # negated: "fließt nie automatisch in eine Empfehlung ein"
    "api/routes/case_records.py",  # SSoT review-state enum; never component release language
    "api/routes/knowledge_review.py",  # internal claim-review enum; never suitability advice
    "core/calc/binding.py",  # "owner-approved" = an approved UNIT SPELLING, unrelated meaning
    "core/contracts.py",  # negated doctrine comment: "keine Empfehlung ist auf den Wissensstand..."
    "core/decision_records.py",  # internal SSoT case-review status, not suitability approval
    "core/gegencheck.py",  # describes what it does NOT do: "never an affirmative passt/geeignet"
    "core/interview/contracts.py",  # internal expert verification state; never suitability approval
    "core/interview/policy.py",  # reads that internal verification state; no user-facing wording
    "core/legal_doctrine.py",  # defines the terms themselves (this module's own source list)
    "core/material_evidence_review.py",  # internal factual-review/approval states; never suitability language
    "core/output_guard.py",  # IS the existing forbidden-phrase enforcement list this lint mirrors
    "core/response_contract_policy.py",  # same doctrine — banned-phrase list + negated comments
    "knowledge/produktspec/contracts.py",  # `freigegeben: bool = False` G1 structural invariant
    "knowledge/produktspec/kernel.py",  # constructs with `freigegeben=False` (always)
    "knowledge/ledger.py",  # `approved` is an internal review-state enum; never user-facing advice
    "db/material_evidence_review.py",  # persists the same internal factual-review lifecycle only
    "db/models.py",  # schema constraints for internal review states; never public suitability wording
    "db/migrations/versions/20260718_0016_mat_evid_01c_review.py",  # immutable internal review schema
    "pipeline/produktspec_step.py",  # surfaces the same always-False `freigegeben` field
    "pipeline/routing.py",  # regex DETECTING "geeignet für" in USER input, not an output claim
    "pipeline/stages.py",  # "Herstellerempfehlung" = WHICH manufacturer partner to route an RFQ
    # to (Modus F capability-matching directory), not a technical suitability/approval claim
    "safety/risk_flags.py",  # negated warning text: "keine Empfehlung, keine Eignungs-, ..."
}


def _iter_scanned_files():
    for path in _ROOT.rglob("*.py"):
        rel = path.relative_to(_ROOT)
        if rel.parts and rel.parts[0] in _EXCLUDED_DIRS:
            continue
        yield rel, path


def test_no_new_risky_status_terms_outside_the_reviewed_allowlist():
    violations: list[str] = []
    for rel, path in _iter_scanned_files():
        rel_str = str(rel)
        if rel_str in _ALLOWLIST_FILES:
            continue
        text_lower = path.read_text(encoding="utf-8").lower()
        for term in _SCANNED_TERMS:
            if term.lower() in text_lower:
                violations.append(f"{rel_str}: contains forbidden term {term!r}")
    assert not violations, (
        "New risky status term(s) found outside the reviewed allowlist — either use the safe "
        "replacement from FORBIDDEN_STATUS_TERMS (core/legal_doctrine.py), or, if this is a "
        "genuinely reviewed-safe negated/structural usage, add the file to _ALLOWLIST_FILES above "
        "with a one-line justification:\n" + "\n".join(violations)
    )


def test_allowlist_has_no_stale_entries():
    # The inverse guard: an allowlisted file that no longer contains ANY scanned term should be
    # removed from the list — an empty allowlist entry is a silent signal the audit went stale.
    stale = []
    for rel_str in sorted(_ALLOWLIST_FILES):
        path = _ROOT / rel_str
        if not path.exists():
            stale.append(f"{rel_str}: file no longer exists")
            continue
        text_lower = path.read_text(encoding="utf-8").lower()
        if not any(term.lower() in text_lower for term in _SCANNED_TERMS):
            stale.append(f"{rel_str}: no longer contains any scanned term")
    assert not stale, "Stale _ALLOWLIST_FILES entries (remove them):\n" + "\n".join(
        stale
    )
