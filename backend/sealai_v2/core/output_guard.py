"""Claim-level output guard (V2.2 / INC-NARRATOR-CONTRACT Phase 3). Deterministic, no LLM, no I/O.

The guard ENFORCES the answer-contract against the rendered text — it does not match forbidden strings,
it enforces COVERAGE positively: every TECHNICAL sentence of the render must map to exactly one of
(1) an allowed_claim, (2) a required_clause, (3) a clarification question about a missing_field,
(4) an uncertainty / non-design statement, (5) a purely linguistic transition (no technical content).
A non-mappable technical sentence is FAIL-CLOSED (BLOCK -> regenerate). On top sit fast deterministic
prefilters: an invented physical quantity (number+unit not covered by allowed_values / a claim / a
user-stated value), an invented material (a vocab material not in allowed_materials), a missing
required_clause, a forbidden_phrase without a covering claim.

This is what catches a leaking DISPOSITION (the probe class) rather than only artefacts, and it does so
independent of the model. It STARTS deterministic-conservative: where mapping is not certain it
fail-closes (overblock-before-leak; the renderer's regeneration recovers legitimate cases). Whether a
cheap LLM *mapping* classifier is ever needed is downstream + MEASURED (Phase 4) — never a fact verifier.

PURE + INERT: importing/calling changes no prod behaviour. Wiring it into the pipeline (run after generate;
BLOCK -> regenerate; GOVERNANCE_LOG) and arming it are later, measured, owner-gated steps. Builds on the
existing L3 parametric-leak detector (it does not duplicate it — the contract gives it the allow-set L3
lacks). v1 SCOPE mirrors the contract: material x medium suitability turns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sealai_v2.core.response_contract_policy import DEFAULT_POLICY, ContractPolicy

# ── tunables (Phase-4 measures overblock/miss-rate and the owner sets these) ─────────────────────
_REQUIRED_CLAUSE_THRESH = 0.6  # share of a clause's significant words that must appear
_COVER_THRESH = 0.5  # share of a technical sentence's significant words drawn from the contract vocab

# Physical-unit tokens — the invented-number prefilter is scoped to NUMBER+UNIT (the leak class:
# invented temperatures/pressures/limits); bare counts ("2 Lippen") are intentionally not policed.
_UNIT = (
    r"°\s*C|bar|MPa|kPa|N/mm²|N/mm2|N/mm|MPa·m/s|m/s|mm/s|µm|mm|cm|%|Shore\s*[AD]|°"
)
_NUM = r"\d+(?:[.,]\d+)?"
_NUM_UNIT_RE = re.compile(
    rf"({_NUM})(?:\s*(?:bis|–|-|\.\.\.|…|‑)\s*({_NUM}))?\s*(?:{_UNIT})", re.IGNORECASE
)
_ANY_NUM_RE = re.compile(_NUM)

# Suitability vocabulary — a sentence carrying any of these is a TECHNICAL (claim-bearing) sentence.
_SUITABILITY = (
    "geeignet",
    "ungeeignet",
    "passt",
    "beständig",
    "unbeständig",
    "verträglich",
    "unverträglich",
    "beständigkeit",
    "eignung",
    "empfohlen",
    "empfehle",
    "empfehlung",
    "freigabe",
    "freigegeben",
    "einsetzbar",
    "tauglich",
    "quillt",
    "quellung",
    "hydrolyse",
    "verspröd",
    "angegriffen",
    "resistent",
)

# Uncertainty / non-design / honest-deferral patterns — a sentence matching these is COVERED (4).
_UNCERTAINTY = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bkann ich (?:dir )?nicht\b",
        r"\bohne .{0,40}\b(?:keine|nicht)\b",
        r"\bbeim hersteller\b",
        r"\bvom hersteller\b",
        r"\bhersteller\b.{0,30}\b(?:frei|bestätig|absicher|prüf)",
        r"\bdatenblatt\b",
        r"\bnicht berechenbar\b",
        r"\bkeine (?:werkstoff)?freigabe\b",
        r"\bvorläufig\b",
        r"\bnicht (?:abschließend|belastbar|gesichert)\b",
        r"\babsichern\b",
        r"\bprüf(?:en|pfad|stand)\b",
        r"\bliegt mir .{0,30}\bnicht vor\b",
        r"\bbenötige ich\b|\bbräuchte ich\b|\bbitte .{0,30}\b(?:ergänz|nenn|angab)",
    )
)

# Base linguistic / domain-neutral whitelist — words that are not "foreign technical content" on their
# own (so a sentence built from these + the contract vocab is covered).
_BASE_WHITELIST = {
    "dichtung",
    "dichtungen",
    "werkstoff",
    "werkstoffe",
    "material",
    "medium",
    "anwendung",
    "anwendungsfall",
    "fall",
    "hersteller",
    "datenblatt",
    "freigabe",
    "temperatur",
    "druck",
    "einsatz",
    "lösung",
    "empfehlung",
    "bedingung",
    "prüfung",
    "kandidat",
    "kandidaten",
    "auslegung",
    "frage",
    "angabe",
    "angaben",
}

_STOP = {
    "und",
    "oder",
    "der",
    "die",
    "das",
    "ein",
    "eine",
    "einen",
    "einem",
    "einer",
    "ist",
    "sind",
    "war",
    "wird",
    "werden",
    "kann",
    "können",
    "muss",
    "müssen",
    "soll",
    "für",
    "mit",
    "ohne",
    "bei",
    "auf",
    "aus",
    "von",
    "vom",
    "zum",
    "zur",
    "den",
    "dem",
    "des",
    "auch",
    "noch",
    "nur",
    "nicht",
    "kein",
    "keine",
    "als",
    "wie",
    "sich",
    "dich",
    "dir",
    "ich",
    "wir",
    "sie",
    "hier",
    "dann",
    "also",
    "aber",
    "sehr",
    "schon",
    "diese",
    "dieser",
    "dieses",
    "ihre",
    "ihrer",
    "über",
    "unter",
    "vor",
    "nach",
    "gerne",
    "bitte",
    "danke",
}


@dataclass(frozen=True)
class Violation:
    kind: str  # forbidden_phrase | invented_number | invented_material | missing_required_clause | unmapped_sentence
    detail: str
    sentence: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "detail": self.detail, "sentence": self.sentence}


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    action: str  # "PASS" | "BLOCK"
    violations: tuple[Violation, ...]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "action": self.action,
            "violations": [v.to_dict() for v in self.violations],
        }


def _sig_words(text: str) -> set[str]:
    toks = re.findall(r"[a-zäöüß][a-zäöüß\-]{2,}", (text or "").lower())
    return {t for t in toks if t not in _STOP}


def _norm_num(s: str) -> str:
    s = s.replace(",", ".").strip()
    try:
        f = float(s)
        return str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        return s


def _covered_numbers(contract: dict, known_values: tuple) -> set[str]:
    nums: set[str] = set()
    for v in contract.get("allowed_values", ()):
        try:
            nums.add(_norm_num(str(v.get("value"))))
        except Exception:  # noqa: BLE001 — defensive; a malformed value just isn't a covered number
            pass
    for blob in list(contract.get("required_clauses", ())) + [
        c.get("text", "") for c in contract.get("allowed_claims", ())
    ]:
        for m in _ANY_NUM_RE.findall(blob):
            nums.add(_norm_num(m))
    for kv in known_values:
        nums.add(_norm_num(str(kv)))
    return nums


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _is_technical(sent: str, vocab_materials: tuple) -> bool:
    low = sent.lower()
    if any(re.search(rf"\b{re.escape(m.lower())}\b", low) for m in vocab_materials):
        return True
    if _NUM_UNIT_RE.search(sent):
        return True
    return any(k in low for k in _SUITABILITY)


def _matches_uncertainty(sent: str) -> bool:
    return any(p.search(sent) for p in _UNCERTAINTY)


def evaluate_render(
    *,
    answer_text: str,
    contract: dict,
    policy: ContractPolicy = DEFAULT_POLICY,
    known_values: tuple = (),
) -> GuardResult:
    """Enforce the answer-contract against the rendered text. Fail-closed: any violation -> BLOCK. PURE."""
    violations: list[Violation] = []
    text = answer_text or ""
    low = text.lower()

    allowed_claims = contract.get("allowed_claims", ())
    required_clauses = tuple(contract.get("required_clauses", ()))
    allowed_materials = tuple(contract.get("allowed_materials", ()))
    forbidden = tuple(contract.get("forbidden_phrases", ()))

    claim_blob_low = " ".join(
        [c.get("text", "") for c in allowed_claims] + list(required_clauses)
    ).lower()

    # ── prefilter 1: forbidden phrase (unless it occurs inside an allowed claim / clause text) ──
    for ph in forbidden:
        p = ph.lower()
        if p in low and p not in claim_blob_low:
            violations.append(Violation("forbidden_phrase", ph))

    # ── prefilter 2: invented physical quantity (number+unit not covered) ──
    covered = _covered_numbers(contract, known_values)
    for m in _NUM_UNIT_RE.finditer(text):
        for g in (m.group(1), m.group(2)):
            if g and _norm_num(g) not in covered:
                violations.append(
                    Violation("invented_number", _norm_num(g), m.group(0).strip())
                )

    # ── prefilter 3: invented material (vocab material not in allowed_materials) ──
    allowed_low = {a.lower() for a in allowed_materials}
    for mat in sorted(policy.material_vocab, key=len, reverse=True):
        if re.search(rf"\b{re.escape(mat.lower())}\b", low) and mat.lower() not in allowed_low:
            violations.append(Violation("invented_material", mat))

    # ── prefilter 4: a required clause is missing (significant-word coverage) ──
    for clause in required_clauses:
        csig = _sig_words(clause)
        if not csig:
            continue
        present = len(csig & _sig_words(text)) / len(csig)
        if present < _REQUIRED_CLAUSE_THRESH:
            violations.append(Violation("missing_required_clause", clause))

    # ── coverage: every TECHNICAL sentence must map to claim / clause / question / uncertainty ──
    contract_vocab = (
        _sig_words(claim_blob_low)
        | {a.lower() for a in allowed_materials}
        | _BASE_WHITELIST
    )
    for sent in _sentences(text):
        if not _is_technical(sent, policy.material_vocab):
            continue  # (5) purely linguistic / non-technical transition
        if sent.rstrip().endswith("?") or _matches_uncertainty(sent):
            continue  # (3) clarification question / (4) uncertainty-deferral
        ssig = _sig_words(sent)
        if not ssig:
            continue
        drawn = len(ssig & contract_vocab) / len(ssig)
        if drawn < _COVER_THRESH:  # technical content not drawn from the contract -> foreign -> fail-closed
            violations.append(Violation("unmapped_sentence", f"drawn={drawn:.2f}", sent))

    ok = not violations
    return GuardResult(ok=ok, action="PASS" if ok else "BLOCK", violations=tuple(violations))
