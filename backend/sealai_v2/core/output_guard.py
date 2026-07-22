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
    "gegen",
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
    kind: str  # forbidden_phrase | invented_number | invented_material | missing_required_clause | semantic_inversion | unmapped_sentence
    detail: str
    sentence: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "detail": self.detail, "sentence": self.sentence}


@dataclass(frozen=True)
class ClaimMapping:
    """One rendered sentence deterministically mapped to one grounded contract claim."""

    sentence_index: int
    claim_id: str

    def to_dict(self) -> dict:
        return {"sentence_index": self.sentence_index, "claim_id": self.claim_id}


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    action: str  # "PASS" | "BLOCK"
    violations: tuple[Violation, ...]
    claim_mappings: tuple[ClaimMapping, ...] = ()

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "action": self.action,
            "violations": [v.to_dict() for v in self.violations],
            "claim_mappings": [m.to_dict() for m in self.claim_mappings],
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


_POSITIVE_SUITABILITY_RE = re.compile(
    r"\b(?:geeignet\w*|passt|beständig\w*|verträglich\w*|empfohlen\w*|empfehle|einsetzbar\w*|"
    r"tauglich\w*|resistent\w*|freigegeben\w*|standard(?:werkstoff)?|"
    r"\w*(?:eignung|beständigkeit|empfehlung|freigabe))\b",
    re.IGNORECASE,
)
_NEGATIVE_SUITABILITY_RE = re.compile(
    r"\b(?:ungeeignet\w*|unbeständig\w*|unverträglich\w*|qu(?:ill|ell)(?:t|en|ung\w*)|hydrolyse|"
    r"hydrolysiert|versprödet|versprödung|angegriffen\w*|untauglich\w*|wirkungslos\w*|"
    r"unwirksam\w*|scheitert)\b",
    re.IGNORECASE,
)
_NEGATED_POSITIVE_RE = re.compile(
    r"\b(?:"
    r"(?:nicht|keinesfalls|niemals|nie|auf\s+keinen\s+fall|in\s+keinem\s+fall|"
    r"unter\s+keinen\s+umständen)(?:\s+[\w'’/-]+){0,5}\s+"
    r"(?:geeignet|beständig|verträglich|empfohlen|freigegeben|"
    r"einsetzbar|tauglich|resistent)"
    r"|kein(?:e|en|er|es)?\s+\w*(?:eignung|empfehlung|freigabe)"
    r"|ohne\s+\w*(?:eignung|empfehlung|freigabe)"
    r")\b",
    re.IGNORECASE,
)
_NEGATED_NEGATIVE_RE = re.compile(
    r"\b(?:"
    r"(?:nicht|keineswegs|keinesfalls|niemals|nie|auf\s+keinen\s+fall|"
    r"in\s+keinem\s+fall|unter\s+keinen\s+umständen)\s+"
    r"(?:ungeeignet\w*|unbeständig\w*|unverträglich\w*|untauglich\w*|"
    r"wirkungslos\w*|unwirksam\w*|angegriffen\w*|hydrolysiert|versprödet|quillt|scheitert)"
    r"|(?:hydrolysiert|versprödet|quillt|scheitert)\s+(?:\w+[ -]?){0,3}"
    r"(?:nicht|keineswegs|keinesfalls|niemals|nie)"
    r")\b",
    re.IGNORECASE,
)
_NEGATED_STANDARD_RE = re.compile(
    r"\b(?:kein(?:e|en|er|es)?\s+[^.!?]{0,60}\bstandard(?:werkstoff)?|"
    r"nicht\s+(?:der|die|das|ein(?:e|en|er|es)?)?\s*[^.!?]{0,40}\bstandard(?:werkstoff)?)\b",
    re.IGNORECASE,
)
_CONDITIONAL_SUITABILITY_RE = re.compile(
    r"\b(?:"
    r"bedingt(?:e|en|er|es)?"
    r"|(?:geeignet\w*|beständig\w*|verträglich\w*|einsetzbar\w*|tauglich\w*)"
    r"\s+(?:nur\s+)?bedingt(?:e|en|er|es)?"
    r")\b",
    re.IGNORECASE,
)
_EXCLUSIVITY_RE = re.compile(
    r"\b(?:einzig(?:e|en|er|es)?|alleinig(?:e|en|er|es)?|ausschließlich|alternativlos)\b",
    re.IGNORECASE,
)


def _suitability_polarity(text: str) -> int:
    """Return proposition direction, including conditionals and double negation."""
    if _NEGATED_NEGATIVE_RE.search(text):
        return 1
    if _NEGATED_STANDARD_RE.search(text):
        return -1
    if _NEGATED_POSITIVE_RE.search(text) or _NEGATIVE_SUITABILITY_RE.search(text):
        return -1
    if _CONDITIONAL_SUITABILITY_RE.search(text):
        return 2
    if _POSITIVE_SUITABILITY_RE.search(text):
        return 1
    return 0


def _claim_fragments(text: str) -> tuple[str, ...]:
    """Split legacy multi-proposition facts before semantic comparison."""
    parts = re.split(r";|(?<=[.!?])\s+", text or "")
    return tuple(part.strip() for part in parts if part.strip())


def _semantically_compatible(sentence: str, claim_fragment: str) -> bool:
    sentence_polarity = _suitability_polarity(sentence)
    claim_polarity = _suitability_polarity(claim_fragment)
    if sentence_polarity != claim_polarity and (sentence_polarity or claim_polarity):
        return False
    if _EXCLUSIVITY_RE.search(sentence) and not _EXCLUSIVITY_RE.search(claim_fragment):
        return False
    return True


def _word_matches(left: str, right: str) -> bool:
    ls, rs = _stem(left), _stem(right)
    return ls == rs or (
        min(len(left), len(right)) >= 5 and (left in right or right in left)
    )


def _map_allowed_claim(
    sentence: str,
    allowed_claims: tuple[dict, ...] | list[dict],
    *,
    anchor_materials: set[str],
) -> str | None:
    """Map a sentence to one claim; a material name alone is never sufficient."""
    sentence_words = _sig_words(sentence)
    if not sentence_words:
        return None
    anchor_words = {_stem(m.lower()) for m in anchor_materials}
    neutral_words = {_stem(w) for w in _BASE_WHITELIST}
    best: tuple[float, int, str] | None = None
    for claim in allowed_claims:
        claim_id = str(claim.get("id") or "")
        claim_text = str(claim.get("text") or "")
        if not claim_id or not claim_text:
            continue
        for fragment in _claim_fragments(claim_text):
            if not _semantically_compatible(sentence, fragment):
                continue
            claim_words = _sig_words(fragment)
            matched = {
                word
                for word in sentence_words
                if any(_word_matches(word, claim_word) for claim_word in claim_words)
            }
            substantive = {
                word
                for word in matched
                if _stem(word) not in anchor_words and _stem(word) not in neutral_words
            }
            score = len(matched) / len(sentence_words)
            if not substantive or score < _COVER_THRESH:
                continue
            candidate = (score, len(substantive), claim_id)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    return best[2] if best is not None else None


def _semantic_conflict_claim(
    sentence: str,
    allowed_claims: tuple[dict, ...] | list[dict],
    *,
    anchor_materials: set[str],
) -> str | None:
    """Return a closely restated claim whose direction the sentence contradicts."""
    sentence_words = _sig_words(sentence)
    if not sentence_words:
        return None
    anchor_words = {_stem(m.lower()) for m in anchor_materials}
    neutral_words = {_stem(w) for w in _BASE_WHITELIST}
    for claim in allowed_claims:
        claim_id = str(claim.get("id") or "")
        claim_text = str(claim.get("text") or "")
        if not claim_id or not claim_text:
            continue
        for fragment in _claim_fragments(claim_text):
            sentence_polarity = _suitability_polarity(sentence)
            claim_polarity = _suitability_polarity(fragment)
            direction_conflict = bool(
                sentence_polarity
                and claim_polarity
                and sentence_polarity != claim_polarity
            )
            unlicensed_exclusivity = bool(
                _EXCLUSIVITY_RE.search(sentence)
                and not _EXCLUSIVITY_RE.search(fragment)
            )
            if not (direction_conflict or unlicensed_exclusivity):
                continue
            claim_words = _sig_words(fragment)
            matched = {
                word
                for word in sentence_words
                if any(_word_matches(word, claim_word) for claim_word in claim_words)
            }
            substantive = {
                word
                for word in matched
                if _stem(word) not in anchor_words and _stem(word) not in neutral_words
            }
            if substantive and len(matched) / len(sentence_words) >= _COVER_THRESH:
                return claim_id
    return None


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
    check_sentence_coverage: bool = True,
) -> GuardResult:
    """Enforce the answer-contract against the rendered text. Fail-closed: any violation -> BLOCK. PURE.

    ``check_sentence_coverage`` (P0-B, default True — unchanged behaviour for every existing caller):
    the sentence-coverage check (5, below) assumes L1 was INSTRUCTED to render only the contract's
    content (the Renderer-Modus prompt block) — false for a guard-only contract
    (``response_contract.build_guard_contract``), where L1 was never told to stay inside the contract
    at all. Pass False there: the 4 prefilters (forbidden_phrase / invented_number / invented_material
    / missing_required_clause — the last a no-op on an empty required_clauses) plus the narrow
    semantic-inversion check stay active as turn-agnostic safety nets; only the strict "every technical
    sentence must map to a claim" check is skipped."""
    violations: list[Violation] = []
    mappings: list[ClaimMapping] = []
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

    # A close lexical restatement may never invert the grounded proposition. This remains active in
    # light mode, but does not require every technical sentence to map.
    anchor_low = {a.lower() for a in allowed_materials} | {
        m.lower() for m in known_materials
    }
    sentences = _sentences(text)
    for sent in sentences:
        if not _is_technical(sent, policy.material_vocab):
            continue
        if sent.rstrip().endswith("?") or _matches_uncertainty(sent):
            continue
        conflict = _semantic_conflict_claim(
            sent, allowed_claims, anchor_materials=anchor_low
        )
        if conflict is not None:
            violations.append(Violation("semantic_inversion", conflict, sent))

    # ── coverage: every TECHNICAL sentence must map to claim / clause / question / uncertainty ──
    if check_sentence_coverage:
        for sentence_index, sent in enumerate(sentences):
            if not _is_technical(sent, policy.material_vocab):
                continue  # (5) purely linguistic / non-technical transition
            if sent.rstrip().endswith("?") or _matches_uncertainty(sent):
                continue  # (3) clarification question / (4) uncertainty-deferral
            if any(
                _clause_satisfied(clause, _sig_words(sent))
                for clause in required_clauses
            ):
                continue  # policy-owned safety/deference clause; no source citation
            claim_id = _map_allowed_claim(
                sent, allowed_claims, anchor_materials=anchor_low
            )
            if claim_id is not None:
                mappings.append(ClaimMapping(sentence_index, claim_id))
                continue
            violations.append(Violation("unmapped_sentence", "no_single_claim", sent))

    ok = not violations
    return GuardResult(
        ok=ok,
        action="PASS" if ok else "BLOCK",
        violations=tuple(violations),
        claim_mappings=tuple(mappings),
    )


def _case_open_inputs(question: str) -> tuple[str, ...]:
    """Return discriminating, non-numeric design inputs for a blocked case answer."""
    low = (question or "").casefold()
    if any(
        alias in low
        for alias in (
            "rwdr",
            "radialwellendichtring",
            "radial-wellendichtring",
            "simmerring",
            "wellendichtring",
        )
    ):
        return (
            "Druckdifferenz mit Druckspitzen und Druckrichtung sowie exakte Mediumbezeichnung einschließlich Additiven.",
            "Wellenhärte, Rauheit und Drallfreiheit sowie Rundlauf und Exzentrizität am Dichtsitz.",
            "Einbauraum und Montageweg, geforderte Lebensdauer und Leckage sowie Art und Menge des Schmutzeintrags.",
        )
    if "o-ring" in low or "oring" in low:
        return (
            "Exakter Compound, Medium einschließlich Additiven sowie Temperatur- und Druckkollektiv.",
            "Nutgeometrie, Verpressung, Nutfüllung und Extrusionsspalt einschließlich Toleranzen.",
            "Bewegungsart, Lastwechsel, Oberflächen, Montageweg, Lebensdauer- und Leckageanforderung.",
        )
    if any(alias in low for alias in ("gleitringdichtung", "gleitdichtung", "glrd")):
        return (
            "Mediumzusammensetzung, Feststoff- und Gasanteil sowie Temperatur-, Druck- und Drehzahlkollektiv.",
            "Wellen- und Gehäuseschnittstellen, Betriebsweise einschließlich Anfahren, Stillstand und Trockenlaufgefahr.",
            "Dichtungsanordnung, Werkstoffpaarung, Hilfssystem und zulässige Leckage beziehungsweise Lebensdauer.",
        )
    return ()


def fail_closed_answer(contract: dict, *, question: str = "") -> str:
    """Build a useful terminal fallback solely from contract-approved content.

    This runs only after one failed regeneration. Every technical line is copied from an allowed
    claim or required clause assembled by the kernel, so the fallback cannot invent a material,
    number, source, or recommendation.
    """
    claims = list(contract.get("allowed_claims", ()))
    is_general = contract.get("status") == "GENERAL"
    if is_general:
        # An overview is pedagogical, not an incident report: definition and balanced family
        # tendencies precede cautions. Stable sorting preserves retrieval's diversified order for
        # repeated kinds. Suitability contracts retain their safety-first severity ordering below.
        kind_priority = {
            "definition": 0,
            "family_tendency": 1,
            "system_dependent": 2,
            "safety_caution": 3,
            "qualification_required": 4,
            "regulatory_status": 5,
            "safety_nogo": 6,
            "example_value": 7,
        }
        claims.sort(key=lambda claim: kind_priority.get(claim.get("claim_kind"), 8))
    else:
        priority = {"disqualify": 0, "caution": 1, "info": 2}
        claims.sort(
            key=lambda claim: (
                priority.get(claim.get("severity"), 3),
                claim.get("id", ""),
            )
        )
    open_inputs = _case_open_inputs(question)
    if is_general and open_inputs:
        sections = [
            "Technische Vorprüfung auf Basis der geprüften Quellen. Eine Bauform- oder "
            "Werkstofffreigabe ist mit den vorliegenden Angaben noch nicht belastbar."
        ]
    elif is_general:
        sections = [
            "Zu dieser Wissensfrage kann ich aus den aktuell geprüften Quellen "
            "Folgendes belastbar festhalten:"
        ]
    else:
        sections = [
            "Die technische Antwort konnte auf Basis der geprüften Informationen nicht "
            "widerspruchsfrei ausgegeben werden. Belastbar festhalten kann ich:"
        ]
    approved = list(
        dict.fromkeys(
            claim.get("text", "").strip()
            for claim in claims
            if claim.get("text", "").strip()
        )
    )
    if approved:
        sections.append("\n".join(f"- {text}" for text in approved[:5]))
    else:
        sections.append(
            "Für eine belastbare technische Einordnung fehlen derzeit geprüfte Grundlagen."
        )
    labels = {
        "umfangsgeschwindigkeit": "Umfangsgeschwindigkeit",
        "pv_wert": "PV-Wert",
        "verpressung_prozent": "Verpressung",
    }
    values = []
    for value in contract.get("allowed_values", ()):
        name = labels.get(value.get("calc_id"), value.get("name", "Berechneter Wert"))
        values.append(
            f"- {name}: {value.get('value')} {value.get('unit', '')}".rstrip()
        )
        values.extend(
            f"  - {warning}"
            for warning in value.get("warnings", ())
            if str(warning).strip()
        )
    if values:
        sections.append("**Deterministisch berechnet**\n" + "\n".join(values))
    if open_inputs:
        sections.append(
            "**Für die belastbare Auswahl noch erforderlich**\n"
            + "\n".join(f"- {item}" for item in open_inputs)
        )
    required = [
        str(clause).strip()
        for clause in contract.get("required_clauses", ())
        if str(clause).strip()
    ]
    sections.append(
        "\n".join(required)
        if required
        else "Bitte die konkrete Auswahl gegen Datenblatt und Herstellerangaben prüfen."
    )
    return "\n\n".join(sections)


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
            "semantic_inversion",
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
    if by["semantic_inversion"]:
        bits.append(
            "Kehre die Aussage des belegenden Claims nicht um; formuliere nur in seiner "
            "belegten Richtung."
        )
    if has_unmapped:
        bits.append(
            "Bleibe strikt beim Vertragsinhalt — keine fachliche Aussage ohne deckenden Claim."
        )
    return "OUTPUT-GUARD-KORREKTUR (Antwort-Vertrag verletzt): " + " ".join(bits)
