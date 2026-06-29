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
_REQUIRED_CLAUSE_THRESH = (
    0.6  # share of a clause's DISTINCTIVE (content-noun) stems that must appear
)
_COVER_THRESH = 0.34  # share of a technical sentence's significant words drawn from the contract vocab
#                       (low + material-anchored: prefilters are the primary leak defense, so the
#                       sentence-coverage check only needs to catch genuinely foreign-SUBJECT sentences)

# Physical-unit tokens — the invented-number prefilter is scoped to NUMBER+UNIT (the leak class:
# invented temperatures/pressures/limits); bare counts ("2 Lippen") are intentionally not policed.
_UNIT = r"°\s*C|bar|MPa|kPa|N/mm²|N/mm2|N/mm|MPa·m/s|m/s|mm/s|µm|mm|cm|%|Shore\s*[AD]|°"
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
        r"\bkann ich (?:dir |dann )?(?:nur|nicht|keine|erst|noch nicht)\b",
        r"\bsolange .{0,50}\bnicht\b",
        r"\blässt sich .{0,40}\b(?:nicht|kaum|erst)\b",
        r"\bohne .{0,60}\b(?:keine|nicht|lässt|kann|erst|bräuchte|brauche)\b",
        r"\bbeim hersteller\b",
        r"\bvom hersteller\b",
        r"\bhersteller.{0,30}(?:frei|bestätig|absicher|prüf|entscheid|treff|wähl|ausw)",
        r"\bherstellerfreigabe\b",
        r"\bquelle\s*:",  # a provenance/citation note, not an asserted claim
        r"\bdatenblatt\b",
        r"\bnicht berechenbar\b",
        r"\bkeine (?:werkstoff)?freigabe\b",
        r"\bvorläufig\b",
        r"\b(?:nicht|nicht abschließend|noch nicht) (?:abschließend|belastbar|gesichert|möglich|seriös)\b",
        r"\babsichern\b",
        r"\bprüf(?:en|pfad|stand|ung)\b",
        r"\bliegt mir .{0,30}\bnicht vor\b",
        r"\b(?:nicht|nicht pauschal|kein) belegt(?:er|es)?\b|\bbelegt ist\b",
        r"\bbenötige ich\b|\bbräuchte ich\b|\bbrauche ich\b|\bbitte .{0,30}\b(?:ergänz|nenn|angab|sag|schreib)",
        r"\bwenn du (?:magst|willst|möchtest)\b|\bschreib(?:e)? (?:mir|kurz|gern)\b|\bsag mir\b",
        r"\bnur (?:auf )?risiken? (?:hinweisen|nennen)\b|\bkann ich (?:dir )?nur\b",
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
    "nein",
    "ja",
    "hält",
    "halten",
    "bleibt",
    "bleiben",
    "liegt",
    "liegen",
    "zeigt",
    "zeigen",
    "gilt",
    "kommt",
    "kommen",
    "so",
    "es",
    "da",
    "zur",
    "genannten",
    "deinen",
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


def _stem(w: str) -> str:
    """Crude German stem — a 6-char prefix folds morphological variation (hydrolyse/hydrolysiert,
    beständig/beständiger) so a legitimate restatement is not falsely flagged as foreign content."""
    return w[:6] if len(w) >= 6 else w


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
    # A sentence carries claim-bearing technical content if it names a material or a suitability term.
    # NUMBERS are intentionally NOT a technical-trigger here: invented numbers are caught decisively by
    # the number+unit prefilter, and a sentence whose only "technical" token is a covered number (an
    # echoed user value / a computed value) must not be flagged as an unmapped claim.
    low = sent.lower()
    if any(re.search(rf"\b{re.escape(m.lower())}\b", low) for m in vocab_materials):
        return True
    return any(k in low for k in _SUITABILITY)


def _matches_uncertainty(sent: str) -> bool:
    return any(p.search(sent) for p in _UNCERTAINTY)


def _clause_satisfied(clause: str, answer_words: set[str]) -> bool:
    """A required clause counts as present if MOST of its DISTINCTIVE content nouns (len>=7) appear —
    paraphrase-tolerant: a clause noun matches by stem OR by bidirectional substring, so "Freigabe" in
    the answer covers the clause's "Werkstofffreigabe" and "...trifft der Hersteller" ==
    "...muss der Werkstoffhersteller treffen". A faithful restatement is not flagged as a dropped clause."""
    distinct = {w for w in _sig_words(clause) if len(w) >= 7} or _sig_words(clause)
    if not distinct:
        return True
    hits = 0
    for cw in distinct:
        cs = _stem(cw)
        if any(
            cs == _stem(aw) or (len(aw) >= 6 and (aw in cw or cw in aw))
            for aw in answer_words
        ):
            hits += 1
    return hits / len(distinct) >= _REQUIRED_CLAUSE_THRESH


def evaluate_render(
    *,
    answer_text: str,
    contract: dict,
    policy: ContractPolicy = DEFAULT_POLICY,
    known_values: tuple = (),
    known_materials: tuple = (),
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

    # ── prefilter 3: invented material (vocab material not in allowed_materials / user-stated) ──
    # known_materials = the materials the USER named (the case-state) — referencing them (to disqualify,
    # defer, or discuss) is not inventing a material, exactly as known_values are for numbers.
    allowed_low = {a.lower() for a in allowed_materials} | {
        m.lower() for m in known_materials
    }
    for mat in sorted(policy.material_vocab, key=len, reverse=True):
        if (
            re.search(rf"\b{re.escape(mat.lower())}\b", low)
            and mat.lower() not in allowed_low
        ):
            violations.append(Violation("invented_material", mat))

    # ── prefilter 4: a required clause is missing (paraphrase-tolerant distinctive-noun match) ──
    answer_words = _sig_words(text)
    for clause in required_clauses:
        if not _clause_satisfied(clause, answer_words):
            violations.append(Violation("missing_required_clause", clause))

    # ── coverage: every TECHNICAL sentence must map to claim / clause / question / uncertainty ──
    contract_vocab = (
        _sig_words(claim_blob_low)
        | {a.lower() for a in allowed_materials}
        | _BASE_WHITELIST
    )
    vocab_stems = {_stem(w) for w in contract_vocab}
    anchor_low = {a.lower() for a in allowed_materials} | {
        m.lower() for m in known_materials
    }
    for sent in _sentences(text):
        if not _is_technical(sent, policy.material_vocab):
            continue  # (5) purely linguistic / non-technical transition
        low_s = sent.lower()
        if any(re.search(rf"\b{re.escape(m)}\b", low_s) for m in anchor_low):
            continue  # (1) anchored to a contract/known material — elaboration is allowed; invented
            #             numbers/materials/authority inside it are caught by the prefilters above
        if sent.rstrip().endswith("?") or _matches_uncertainty(sent):
            continue  # (3) clarification question / (4) uncertainty-deferral
        ssig = _sig_words(sent)
        if not ssig:
            continue
        drawn = sum(1 for w in ssig if _stem(w) in vocab_stems) / len(ssig)
        if (
            drawn < _COVER_THRESH
        ):  # foreign-SUBJECT technical sentence (no anchor, low overlap) -> fail-closed
            violations.append(
                Violation("unmapped_sentence", f"drawn={drawn:.2f}", sent)
            )

    ok = not violations
    return GuardResult(
        ok=ok, action="PASS" if ok else "BLOCK", violations=tuple(violations)
    )


def known_inputs(
    text: str, policy: ContractPolicy = DEFAULT_POLICY
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The values + materials the USER stated in the case text — referencing them in the answer is not
    invention (the guard's known_values / known_materials exceptions). Pure; for the pipeline wiring."""
    low = (text or "").lower()
    materials = tuple(
        m
        for m in policy.material_vocab
        if re.search(rf"\b{re.escape(m.lower())}\b", low)
    )
    values = tuple(dict.fromkeys(_norm_num(n) for n in _ANY_NUM_RE.findall(text or "")))
    return values, materials


def correction_note(result: GuardResult) -> str:
    """A terse, DETERMINISTIC German instruction for the single regeneration — names what to fix from
    the violations, never invents content. Empty when the render already passed."""
    if result.ok:
        return ""
    by = {
        k: []
        for k in (
            "invented_number",
            "invented_material",
            "forbidden_phrase",
            "missing_required_clause",
        )
    }
    has_unmapped = False
    for v in result.violations:
        if v.kind in by:
            by[v.kind].append(v.detail)
        elif v.kind == "unmapped_sentence":
            has_unmapped = True
    bits: list[str] = []
    if by["invented_number"]:
        bits.append(
            f"Nenne KEINE nicht-gelieferten Zahlen (entferne: {', '.join(sorted(set(by['invented_number'])))})."
        )
    if by["invented_material"]:
        bits.append(
            f"Nenne KEINE nicht-freigegebenen Werkstoffe ({', '.join(sorted(set(by['invented_material'])))})."
        )
    if by["forbidden_phrase"]:
        bits.append(
            f"Vermeide die Autoritäts-/Freigabeformeln: {', '.join(sorted(set(by['forbidden_phrase'])))}."
        )
    if by["missing_required_clause"]:
        bits.append(
            "Übernimm die Pflichtklauseln des Vertrags sinngemäß: "
            + " | ".join(by["missing_required_clause"])
        )
    if has_unmapped:
        bits.append(
            "Bleibe strikt beim Vertragsinhalt — keine fachliche Aussage ohne deckenden Claim."
        )
    return "OUTPUT-GUARD-KORREKTUR (Antwort-Vertrag verletzt): " + " ".join(bits)
