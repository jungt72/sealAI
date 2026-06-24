"""L3 Verifier — the independent critic pass (build-spec §4/§5, Prinzipien §2-L3).

An L1 draft is checked against the OWNER-AUTHORED trap catalog (M2: the catalog only; the matrix
arrives at M3). Hard-gate violations grounded in a ``reviewed`` entry BLOCK — preferring a
regenerate-once against the entry's ``correct`` fact, else a fail-closed hedge. Soft / draft-only
matches FLAG. The integrity rule is structural: a correction's replacement fact comes ONLY from a
``reviewed`` catalog entry — L3 never free-generates a correction (build-spec §4 "darf nicht: eine
eigene Wahrheitsquelle erfinden"). That guarantees PROVENANCE, not topical fit: a reviewed trap's
``correct`` is split into ``correct_general`` (always injected) + a topic-scoped
``correct_recommendation`` (injected only when the question matches the trap's ``applies_to``), so an
off-topic trap firing never mis-directs with a wrong-topic material recommendation (OPTIMIZE_BACKLOG
#5). The regenerate-once also re-answers with the FULL draft context (grounding + matrix + calc +
memory + untrusted), not a degraded one.

Provider-agnostic: this module talks to the injected ``LlmClient`` Protocol only — no OpenAI, no
network of its own (``core`` stays I/O-free, build-spec §3). The verifier model is config; a
cross-vendor swap is a different adapter + a config flip, no change here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sealai_v2.core.calc.leak_detector import LeakFinding, detect_parametric_leaks
from sealai_v2.core.contracts import (
    Answer,
    CalcResult,
    ComputedValue,
    Flags,
    GroundingFact,
    LlmClient,
    ModelConfig,
    NotComputed,
    VerifierAction,
    VerifierFinding,
    VerifierPromptAssembler,
    VerifierVerdict,
)
from sealai_v2.core.text_match import query_tokens, tag_matches
from sealai_v2.knowledge.traps import TrapCatalog, TrapEntry

_HEDGE_MODEL = "l3-hedge"  # sentinel: the hedge is deterministic, not model-generated

# M8-C — the deterministic L1-parametric-computation guard (kind="calc_leak"). The detector
# (core/calc/leak_detector.py) fires server-side on draft AND regeneration; the same-named
# catalog entry lets the LLM critic catch paraphrases the regex core cannot (defense-in-depth).
PARAMETRIC_TRAP_ID = "TRAP-L1-PARAMETRIC-CALC"
PARAMETRIC_GATE = "parametric_computation"
_CALC_DISPLAY = {
    "umfangsgeschwindigkeit": "Umfangsgeschwindigkeit",
    "pv_wert": "PV-Wert",
    "verpressung_prozent": "Verpressung",
}

# --- precision over-application guard (firing condition only — NOT the reviewed `correct` facts) ---
# A compound-dependent LIMIT (temperature/pressure/Verpressung) given as a RANGE *with* a verify/
# Datenblatt caveat is the correct form, not a violation (PREC-EINZELZAHL) — yet the verifier model
# sometimes flags it anyway (m2-l3: TRAP-01 "ca. 120–130 °C … gegen Datenblatt verifizieren"); this
# is the deterministic backstop to the prompt's "Bereich ist kein Verstoß" rule. It scopes ONLY the
# firing condition; it never edits the catalog.
# PREC-LEBENSDAUER is deliberately NOT here (OPTIMIZE_BACKLOG #6): a future-PERFORMANCE prediction
# (lifetime/wear/leakage) gets NO number — not even a hedged range — so a lifetime range is a real
# violation, never the "correct form"; it must NOT be exempted.
_PRECISION_RANGE_TRAPS = frozenset({"PREC-EINZELZAHL"})
# a numeric range: two numbers joined by a dash, ellipsis, or "bis" (German thousands "." + spaces
# tolerated; optional "+" sign on the upper bound, e.g. "+135 bis +150").
_RANGE_RE = re.compile(
    r"\d[\d.\s'’]*\s*(?:[–—-]|…|\.{2,3}|\bbis\b)\s*\+?\s*\d",
    re.IGNORECASE,
)
_VERIFY_CAVEAT_TOKENS = (
    "verifizier",
    "datenblatt",
    "herstellerangabe",
    "typisch",
    "richtwert",
    "orientierung",
)


def is_precision_overapplication(trap_id: str, evidence: str, draft: str = "") -> bool:
    """True iff a RANGE-precision trap (PREC-EINZELZAHL — a compound-dependent LIMIT, NOT a lifetime
    prediction) was raised on a quantity that is ALREADY presented as a range AND carries a verify/
    Datenblatt caveat — i.e. L3 over-applied the "Einzelzahl OHNE Bereich" scope. Checks the evidence
    AND the draft answer (the
    verifier sometimes quotes a sub-snippet that drops the caveat) and recognises dash, ellipsis and
    "X bis Y" ranges. Requires BOTH range and caveat → a bare single value, or a range without a
    caveat, still fires (the catch is preserved). Pure/deterministic — the executable gate for the fix."""
    if trap_id not in _PRECISION_RANGE_TRAPS:
        return False
    text = f"{evidence or ''}\n{draft or ''}"
    return bool(_RANGE_RE.search(text)) and any(
        tok in text.lower() for tok in _VERIFY_CAVEAT_TOKENS
    )


def _extract_json(raw: str) -> str:
    """Pull the first {...} block, tolerating code fences (local copy — ``core`` does not import
    the pipeline layer)."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if "\n" in s:
            s = s.split("\n", 1)[1]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


@dataclass(frozen=True)
class _RawVerdict:
    findings: tuple[VerifierFinding, ...]
    parse_ok: bool
    raw: str


def _trap_payload(catalog: TrapCatalog) -> list[dict]:
    """All catalog entries as delimited DATA for the prompt (reviewed first). ``review_state`` is
    NOT sent — the model judges the claim; the review state is applied server-side on parse."""
    out: list[dict] = []
    for e in (*catalog.reviewed(), *catalog.drafts()):
        out.append(
            {
                "id": e.id,
                "trigger": e.trigger,
                "wrong": list(e.wrong),
                "correct": e.correct,
                "gates": list(e.gates),
            }
        )
    return out


class L3Verifier:
    """Runs ONE critic pass over a draft and returns the raw (violated) findings.

    The block/correct/hedge POLICY lives in ``run_verify`` so this stays a thin, testable judge."""

    def __init__(
        self,
        client: LlmClient,
        assembler: VerifierPromptAssembler,
        model_config: ModelConfig,
        catalog: TrapCatalog,
    ) -> None:
        self._client = client
        self._assembler = assembler
        self._model_config = model_config
        self._catalog = catalog

    async def verify(
        self,
        question: str,
        answer_text: str,
        grounding_facts: tuple[GroundingFact, ...] = (),
        computed_values: tuple[ComputedValue, ...] = (),
        matrix_facts: tuple[GroundingFact, ...] = (),
    ) -> _RawVerdict:
        gf_payload = [
            {"text": f.text, "card_id": f.card_id, "quelle": f.quelle}
            for f in grounding_facts
        ]
        cv_payload = [
            {"name": c.name, "value": c.value, "unit": c.unit, "calc_id": c.calc_id}
            for c in computed_values
        ]
        mx_payload = [
            {"cell_id": f.card_id, "text": f.text, "quelle": f.quelle}
            for f in matrix_facts
        ]
        system = self._assembler.verifier_system_prompt(
            traps=_trap_payload(self._catalog),
            grounding_facts=gf_payload,
            computed_values=cv_payload,
            matrix_facts=mx_payload,
        )
        user = (
            f"FRAGE:\n{question}\n\n"
            f'ENTWURFSANTWORT (zu prüfen):\n"""\n{answer_text}\n"""\n\n'
            "Prüfe die Entwurfsantwort gegen den Fallen-Katalog, die geerdeten Fakten, die "
            "Verträglichkeits-Matrix und die berechneten Werte und gib NUR das JSON zurück."
        )
        res = await self._client.generate(
            system=system, user=user, model_config=self._model_config
        )
        card_ids = frozenset(f.card_id for f in grounding_facts if f.card_id)
        calc_refs = frozenset(
            [c.name for c in computed_values] + [c.calc_id for c in computed_values]
        )
        matrix_ids = frozenset(f.card_id for f in matrix_facts if f.card_id)
        return self._parse(
            res.text,
            draft=answer_text,
            card_ids=card_ids,
            calc_refs=calc_refs,
            matrix_ids=matrix_ids,
        )

    def _parse(
        self,
        raw: str,
        draft: str = "",
        card_ids: frozenset[str] = frozenset(),
        calc_refs: frozenset[str] = frozenset(),
        matrix_ids: frozenset[str] = frozenset(),
    ) -> _RawVerdict:
        raw = (raw or "").strip()
        try:
            data = json.loads(_extract_json(raw))
        except (ValueError, TypeError):
            return _RawVerdict(findings=(), parse_ok=False, raw=raw[:6000])

        findings: list[VerifierFinding] = []
        for item in data.get("findings", []) or []:
            if not isinstance(item, dict) or item.get("violated") is not True:
                continue
            evidence = str(item.get("evidence", ""))[:400]
            # M3 — a contradiction of a reviewed Fachkarte that was actually injected. FLAG-only:
            # cards never drive a correction (integrity: corrections come only from reviewed traps).
            if item.get("card_contradiction") is True:
                cid = str(item.get("card_id", ""))
                if cid not in card_ids:
                    continue  # only a card shown to L3 can be contradicted (no invented ids)
                findings.append(
                    VerifierFinding(
                        trap_id=cid,
                        gate="confident_wrong",
                        review_state="reviewed",  # cards injected are reviewed
                        evidence=evidence,
                        kind="card",
                    )
                )
                continue
            # Gap #2 (Step B) — a contradiction of a reviewed §4 matrix verdict that was injected.
            # CORRECTIVE (kind="matrix"): unlike cards, a matrix contradiction drives a regenerate/
            # hedge — the replacement fact is the reviewed cell's verdict text (integrity preserved:
            # the correction comes only from the reviewed matrix, never free-generated).
            if item.get("matrix_contradiction") is True:
                cid = str(item.get("cell_id", ""))
                if cid not in matrix_ids:
                    continue  # only a matrix cell shown to L3 can be contradicted (no invented ids)
                findings.append(
                    VerifierFinding(
                        trap_id=cid,
                        gate="confident_wrong",
                        review_state="reviewed",  # matrix cells injected are reviewed
                        evidence=evidence,
                        kind="matrix",
                    )
                )
                continue
            # M4 — the draft contradicts a deterministically computed value that was injected.
            # FLAG-only (kind="calc"): computed truth is surfaced; corrections stay reviewed-trap-only.
            if item.get("calc_violation") is True:
                ref = str(item.get("calc", ""))
                if ref not in calc_refs:
                    continue  # only a computed value shown to L3 can be contradicted
                findings.append(
                    VerifierFinding(
                        trap_id=ref,
                        gate="confident_wrong",
                        review_state="reviewed",  # computed values are deterministic + reviewed-def
                        evidence=evidence,
                        kind="calc",
                    )
                )
                continue
            entry = self._catalog.by_id(str(item.get("trap_id", "")))
            if entry is None:
                continue  # never trust an id the catalog doesn't know
            if is_precision_overapplication(entry.id, evidence, draft):
                continue  # range + verify-caveat respects 'Einzelzahl OHNE Bereich' → L3 over-applied
            gate = str(item.get("gate", ""))
            if gate not in entry.gates:
                # keep the finding, but pin the gate to the entry's declared gate(s)
                gate = entry.gates[0]
            findings.append(
                VerifierFinding(
                    trap_id=entry.id,
                    gate=gate,
                    review_state=entry.review_state,  # server-side, not LLM-claimed
                    evidence=evidence,
                    kind="trap",
                )
            )
        return _RawVerdict(findings=tuple(findings), parse_ok=True, raw=raw[:6000])


def _recommendation_applies(
    entry: TrapEntry, question: str, case_context: list[dict] | None = None
) -> bool:
    """True iff the trap's ``applies_to`` topic appears in the question (+ case-state werte). The match
    surface mirrors the §4 matrix (question + structured case facts) and reuses the same matcher
    (``core.text_match``). Conservative: an empty ``applies_to`` OR no match → False → the topic-scoped
    recommendation is suppressed (general only) — so a broad-trigger trap firing OFF-topic can never
    inject an off-topic material recommendation (OPTIMIZE_BACKLOG #5)."""
    if not entry.applies_to:
        return False
    q_norm = " ".join(
        [question] + [str(c.get("wert", "") or "") for c in (case_context or [])]
    ).lower()
    q_tokens = query_tokens(q_norm)
    return any(tag_matches(t, q_tokens, q_norm) for t in entry.applies_to)


def _scoped_fact(
    entry: TrapEntry, question: str, case_context: list[dict] | None
) -> str:
    """The topic-scoped correct fact for one entry: ``correct_general`` ALWAYS (the topic-agnostic
    assertion — keeps the polarity/property/trade-off correction), plus ``correct_recommendation`` ONLY
    when the question matches ``applies_to``. An unsplit entry uses its whole ``correct`` (unchanged)."""
    if not entry.has_split:
        return entry.correct.strip()
    parts = [entry.correct_general.strip()]
    if _recommendation_applies(entry, question, case_context):
        parts.append(entry.correct_recommendation.strip())
    return " ".join(p for p in parts if p)


def build_correction_note(
    catalog: TrapCatalog,
    findings: tuple[VerifierFinding, ...],
    *,
    question: str = "",
    case_context: list[dict] | None = None,
) -> str | None:
    """The catalog-grounded correction for a regeneration — built ONLY from ``reviewed`` entries
    (integrity rule). The injected fact is TOPIC-SCOPED (OPTIMIZE_BACKLOG #5): the topic-agnostic
    ``correct_general`` is always used; a trap's ``correct_recommendation`` is added ONLY when the
    question matches its ``applies_to`` (else a material rec wrong for THIS topic would mis-direct).
    Returns None when no reviewed correct-fact is available (→ caller hedges)."""
    seen: set[str] = set()
    facts: list[str] = []
    for f in findings:
        if f.trap_id in seen:
            continue
        entry = catalog.by_id(f.trap_id)
        if entry is None or not entry.reviewed or not entry.correct.strip():
            continue
        seen.add(f.trap_id)
        facts.append(_scoped_fact(entry, question, case_context))
    if not facts:
        return None
    bullets = "\n".join(f"- {c}" for c in facts)
    return (
        "Die Verifikation (L3) hat in deinem Entwurf eine bekannte Falle / einen "
        "selbstbewusst-falschen Mechanismus markiert. Korrigiere die Antwort und stütze dich "
        "dabei AUSSCHLIESSLICH auf diese geprüften Fakten (keine eigene Gegenbehauptung "
        "erfinden):\n" + bullets
    )


def build_hedge(
    findings: tuple[VerifierFinding, ...],
    catalog: TrapCatalog | None = None,
    *,
    question: str = "",
    case_context: list[dict] | None = None,
) -> str:
    """Deterministic fail-closed fallback. Output integrity: it NEVER echoes the flagged WRONG claim.
    When a reviewed correct fact is available (L3 already holds it), the hedge STATES that correct
    fact + the verify/no-release caveat; otherwise it flags the concern generically without asserting
    any replacement. The stated fact is TOPIC-SCOPED (OPTIMIZE_BACKLOG #5): ``correct_general`` always,
    a trap's topic-scoped ``correct_recommendation`` only when the question matches ``applies_to`` — so
    a deterministic hedge can never recommend a material wrong for THIS question's topic. Scoped per the
    safety language (orientation, verify, keine Freigabe)."""
    correct_facts: list[str] = []
    if catalog is not None:
        seen: set[str] = set()
        for f in findings:
            if f.trap_id in seen:
                continue
            entry = catalog.by_id(f.trap_id)
            if entry is not None and entry.reviewed and entry.correct.strip():
                seen.add(f.trap_id)
                correct_facts.append(_scoped_fact(entry, question, case_context))
    if correct_facts:
        bullets = "\n".join(f"- {c}" for c in correct_facts)
        return (
            "⚠️ Hier ist Vorsicht geboten. Nach geprüftem Stand gilt:\n"
            + bullets
            + "\nDas ist nur eine ingenieurtechnische Orientierung — "
            "bitte gegen das Datenblatt des konkreten Werkstoffs bzw. mit dem Hersteller "
            "verifizieren; keine Freigabe."
        )
    return (
        "⚠️ Hier ist Vorsicht geboten. Zu diesem Punkt kann ich ohne eine geprüfte Quelle "
        "keine belastbare Aussage treffen — bitte gegen das Datenblatt des konkreten Werkstoffs "
        "bzw. mit dem Hersteller verifizieren. Das ist nur eine Orientierung, keine Freigabe."
    )


def _leak_findings(leaks: tuple[LeakFinding, ...]) -> tuple[VerifierFinding, ...]:
    """Deterministic detector hits as findings (kind="calc_leak"). ``review_state`` is "reviewed"
    by construction: the detector compares against the kern's CalcResult, never a model claim."""
    return tuple(
        VerifierFinding(
            trap_id=PARAMETRIC_TRAP_ID,
            gate=PARAMETRIC_GATE,
            review_state="reviewed",
            evidence=f"{leak.calc_id}: »{leak.value_text}« — {leak.excerpt}"[:400],
            kind="calc_leak",
        )
        for leak in leaks
    )


def _kern_truth_lines(
    leaks: tuple[LeakFinding, ...],
    computed_values: tuple[ComputedValue, ...],
    not_computed: tuple[NotComputed, ...],
) -> list[str]:
    """One deterministic truth line per leaked quantity, built ONLY from the CalcResult — the
    kern is a legitimate non-model truth source (integrity rule holds: never a free-generated
    counter-claim). Computed → reference exactly; not-computed → reason names the missing inputs."""
    computed_by_id = {c.calc_id: c for c in computed_values}
    reasons_by_id = {n.calc_id: n.reason for n in not_computed}
    lines: list[str] = []
    for calc_id in dict.fromkeys(leak.calc_id for leak in leaks):  # dedup, keep order
        display = _CALC_DISPLAY.get(calc_id, calc_id)
        c = computed_by_id.get(calc_id)
        if c is not None:
            lines.append(
                f"- {display}: deterministisch berechnet — {c.name} = {c.value} {c.unit}. "
                "Referenziere exakt diesen Wert; rechne nichts selbst."
            )
        else:
            reason = reasons_by_id.get(
                calc_id,
                "kein deterministisch berechneter Wert (Eingaben nicht bestätigt)",
            )
            lines.append(
                f"- {display}: {reason}. Nenne dafür KEINEN Zahlenwert; benenne die "
                "fehlenden Eingaben. Die Formel darf nur symbolisch erscheinen — "
                "keine Zahlen einsetzen."
            )
    return lines


def build_calc_leak_note(
    leaks: tuple[LeakFinding, ...],
    *,
    computed_values: tuple[ComputedValue, ...] = (),
    not_computed: tuple[NotComputed, ...] = (),
) -> str:
    """The correction note for a regeneration after a parametric-computation leak. Deterministic
    from the CalcResult — unlike trap corrections it needs no catalog ``correct`` fact, because the
    replacement truth IS the kern output (or its honest absence)."""
    return (
        "Die Verifikation (L3) hat in deinem Entwurf einen selbst berechneten Zahlenwert für "
        "eine kern-eigene Größe markiert. Kern-eigene Größen berechnet ausschließlich der "
        "deterministische Rechenkern — niemals das Sprachmodell. Korrigiere die Antwort gemäß "
        "diesem Kern-Stand:\n"
        + "\n".join(_kern_truth_lines(leaks, computed_values, not_computed))
    )


def build_calc_leak_hedge(
    leaks: tuple[LeakFinding, ...],
    *,
    computed_values: tuple[ComputedValue, ...] = (),
    not_computed: tuple[NotComputed, ...] = (),
) -> str:
    """Deterministic fail-closed fallback when a parametric leak persists after regeneration.
    USER-facing. Output integrity: NEVER echoes the leaked number; states a value only when the
    kern computed it; otherwise names the quantity + the missing inputs honestly (the Schranke:
    no number in the fail-closed case)."""
    computed_by_id = {c.calc_id: c for c in computed_values}
    reasons_by_id = {n.calc_id: n.reason for n in not_computed}
    lines: list[str] = []
    for calc_id in dict.fromkeys(leak.calc_id for leak in leaks):
        display = _CALC_DISPLAY.get(calc_id, calc_id)
        c = computed_by_id.get(calc_id)
        if c is not None:
            lines.append(
                f"- {display}: deterministisch berechnet — {c.name} = {c.value} {c.unit}."
            )
        else:
            reason = reasons_by_id.get(
                calc_id,
                "kein deterministisch berechneter Wert (Eingaben nicht bestätigt)",
            )
            lines.append(
                f"- {display}: {reason} — ich nenne daher bewusst keinen Zahlenwert."
            )
    return (
        "⚠️ Hier ist Vorsicht geboten. Der Antwortentwurf enthielt einen selbst berechneten "
        "Zahlenwert für eine kern-eigene Größe — solche Werte stammen hier ausschließlich aus "
        "der deterministischen Berechnung. Aktueller Kern-Stand:\n"
        + "\n".join(lines)
        + "\nSobald die fehlenden Eingaben bestätigt sind, berechnet der Rechenkern den Wert "
        "deterministisch mit zitierter Formel. Das ist nur eine Orientierung, keine Freigabe."
    )


def build_matrix_correction_note(
    matrix_facts: tuple[GroundingFact, ...], findings: tuple[VerifierFinding, ...]
) -> str | None:
    """The §4-matrix-grounded correction for a regeneration (Gap #2, Step B) — built ONLY from the
    reviewed matrix cells that were flagged (integrity rule: the replacement fact is the reviewed
    cell's verdict text, never free-generated). Returns None when no flagged cell is available."""
    by_id = {f.card_id: f for f in matrix_facts if f.card_id}
    seen: set[str] = set()
    facts: list[str] = []
    for f in findings:
        if f.kind != "matrix" or f.trap_id in seen:
            continue
        cell = by_id.get(f.trap_id)
        if cell is None or not cell.text.strip():
            continue
        seen.add(f.trap_id)
        facts.append(f"{cell.text.strip()} [Quelle: {cell.quelle}]")
    if not facts:
        return None
    bullets = "\n".join(f"- {c}" for c in facts)
    return (
        "Die Verifikation (L3) hat in deinem Entwurf eine Verträglichkeits-Aussage markiert, die "
        "einem GEPRÜFTEN Matrix-Verdikt widerspricht. Korrigiere die Antwort und stütze dich dabei "
        "AUSSCHLIESSLICH auf diese geprüften Verträglichkeits-Fakten (keine eigene Gegenbehauptung "
        "erfinden):\n" + bullets
    )


def build_matrix_hedge(
    matrix_facts: tuple[GroundingFact, ...], findings: tuple[VerifierFinding, ...]
) -> str:
    """Deterministic fail-closed fallback for a persisting matrix contradiction. States the reviewed
    verdict (L3 holds it) + the verify/no-release caveat; never echoes the draft's wrong claim."""
    by_id = {f.card_id: f for f in matrix_facts if f.card_id}
    seen: set[str] = set()
    facts: list[str] = []
    for f in findings:
        if f.kind != "matrix" or f.trap_id in seen:
            continue
        cell = by_id.get(f.trap_id)
        if cell is None or not cell.text.strip():
            continue
        seen.add(f.trap_id)
        facts.append(f"{cell.text.strip()} [Quelle: {cell.quelle}]")
    bullets = "\n".join(f"- {c}" for c in facts)
    return (
        "⚠️ Hier ist Vorsicht geboten. Nach geprüftem Verträglichkeits-Stand gilt:\n"
        + bullets
        + "\nDas ist nur eine ingenieurtechnische Orientierung — bitte gegen das Datenblatt des "
        "konkreten Werkstoffs bzw. mit dem Hersteller verifizieren; keine Freigabe."
    )


def _reviewed_traps(
    findings: tuple[VerifierFinding, ...],
) -> tuple[VerifierFinding, ...]:
    """Only reviewed TRAP findings drive a block/correction. Card-contradiction findings (kind=
    'card') and draft matches are FLAG-only — corrections come ONLY from reviewed traps (integrity)."""
    return tuple(
        f for f in findings if f.review_state == "reviewed" and f.kind == "trap"
    )


def _reviewed_matrix(
    findings: tuple[VerifierFinding, ...],
) -> tuple[VerifierFinding, ...]:
    """Reviewed MATRIX findings (Gap #2, Step B) — also drive a block/correction (the §4 matrix is a
    reviewed correction source beside the trap catalog), with the reviewed cell's verdict as the fact."""
    return tuple(
        f for f in findings if f.review_state == "reviewed" and f.kind == "matrix"
    )


# ── C2 (V2.1 Inc 2) — deterministic velocity-over-limit verification ──────────────────────────────
# DD-1 HYBRID: C1 (the kernel, sourced from calc_seed.json) already compares v against its material
# limit and emits a FACT-ONLY over-limit warning into ``ComputedValue.warnings``. L3 READS that verdict
# (so the limit NUMBER is never duplicated here, and ``core`` stays I/O-free — build-spec §3) and
# verifies the DRAFT: an over-limit v whose draft does NOT name the consequence (non-prescriptive) is a
# DD-2a deterministic block-trigger → regen-once. The replacement note/hedge is FACT-ONLY + QUALITATIVE
# — NO threshold number (a non-kern m/s number would trip the parametric Schranke, kern-fix-01) and NO
# material direction (DD-5: a specific material comes only from the §4 matrix, never this v-signal).
_OVER_LIMIT_WARNING_MARKER = (
    "belastungsgrenze"  # C1's evaluator over-limit marker (core/calc/evaluator.py)
)
_OVER_LIMIT_PRESCRIPTIVE_MARKERS = (
    "unzureichend",
    "über der",
    "überschrit",
    "höher belastbar",
    "reicht nicht",
    "nicht aus",
    "grenze",
)


def _over_limit_computed(
    computed_values: tuple[ComputedValue, ...],
) -> ComputedValue | None:
    """The computed value the kernel flagged as over its material limit (C1), or None. Reads C1's
    verdict from ``warnings`` — never re-loads the limit (no duplication; ``core`` stays I/O-free)."""
    for c in computed_values:
        if any(_OVER_LIMIT_WARNING_MARKER in (w or "").lower() for w in c.warnings):
            return c
    return None


def _draft_addresses_limit(draft: str) -> bool:
    """Heuristic, deterministic: does the draft name the over-limit consequence? The C4 ``must_avoid``
    cases are the backstop against brittleness here (DD-2: deterministic trigger, no LLM critic)."""
    low = (draft or "").lower()
    return any(m in low for m in _OVER_LIMIT_PRESCRIPTIVE_MARKERS)


def detect_velocity_over_limit(
    draft: str, *, computed_values: tuple[ComputedValue, ...] = ()
) -> tuple[VerifierFinding, ...]:
    """DD-2a deterministic block-trigger: the kernel flagged v over its material limit (C1) AND the
    draft does NOT name the consequence → ONE ``calc_overlimit`` finding (drives the regen-once path).
    Over-limit + already prescriptive → (); under-limit (no C1 over-limit warning) → ()."""
    cv = _over_limit_computed(computed_values)
    if cv is None or _draft_addresses_limit(draft):
        return ()
    return (
        VerifierFinding(
            trap_id=f"calc_overlimit:{cv.calc_id}",
            gate="confident_wrong",
            review_state="reviewed",  # the limit is a reviewed calc-def datum (calc_seed)
            evidence=f"{cv.name}={cv.value} {cv.unit} über der Werkstoffgrenze (C1-Verdikt)",
            kind="calc_overlimit",
        ),
    )


def build_overlimit_note(
    findings: tuple[VerifierFinding, ...],
    computed_values: tuple[ComputedValue, ...] = (),
) -> str | None:
    """Fact-only correction note for an over-limit velocity (C2 → regen). QUALITATIVE: names the
    grounded fact (the computed v is over a Standard-NBR lip's limit → that lip is insufficient → a
    higher-rated lip is needed) WITHOUT a threshold number (parametric-leak-safe) and WITHOUT a material
    direction (DD-5: a specific material may come only from the §4 matrix, never this signal)."""
    if not any(f.kind == "calc_overlimit" for f in findings):
        return None
    cv = _over_limit_computed(computed_values)
    vtxt = (
        f"Die berechnete Umfangsgeschwindigkeit ({cv.value} {cv.unit}) "
        if cv is not None
        else "Die berechnete Umfangsgeschwindigkeit "
    )
    return (
        f"{vtxt}liegt über der Belastungsgrenze einer Standard-NBR-Lippe. Benenne das prescriptive: "
        "eine Standard-NBR-Lippe ist bei diesem v unzureichend → eine höher belastbare Lippe ist nötig. "
        "Nenne KEINE eigene Geschwindigkeits-Grenzzahl und KEIN konkretes Material allein aus dem v — "
        "ein konkretes Material nur, wenn die Verträglichkeits-Matrix es trägt."
    )


def build_overlimit_hedge(
    findings: tuple[VerifierFinding, ...],
    computed_values: tuple[ComputedValue, ...] = (),
) -> str:
    """User-facing fail-closed hedge for a PERSISTING over-limit (the regen stayed non-prescriptive).
    Fact-only + qualitative: the grounded over-limit consequence, no threshold number, no material
    direction. The computed v IS kern-backed (parametric-leak-safe)."""
    cv = _over_limit_computed(computed_values)
    vtxt = (
        f"Die berechnete Umfangsgeschwindigkeit ({cv.value} {cv.unit}) "
        if cv is not None
        else "Die berechnete Umfangsgeschwindigkeit "
    )
    return (
        f"{vtxt}liegt über der Belastungsgrenze einer Standard-NBR-Lippe: eine Standard-NBR-Lippe ist "
        "dafür unzureichend — eine höher belastbare Lippe ist nötig. Das ist eine ingenieurtechnische "
        "Orientierung — die konkrete Werkstoffwahl bitte mit dem Hersteller bestätigen; keine Freigabe."
    )


# ── Eingriff 2 (V2.1 Inc-2 close) — CALC-velocity-trap scope ──────────────────────────────────────
_CALC_VELOCITY_TRAP_ID = "CALC-UMFANGSGESCHWINDIGKEIT"


def scope_calc_velocity_trap(
    findings: tuple[VerifierFinding, ...],
    computed_values: tuple[ComputedValue, ...] = (),
) -> tuple[VerifierFinding, ...]:
    """The CALC-UMFANGSGESCHWINDIGKEIT trap is legitimate ONLY when the kern actually computed a velocity
    verdict this turn (a ComputedValue ``umfangsgeschwindigkeit`` in ``computed_values``). A pure
    materials-orientation turn (no d+rpm → no v computed) must NOT be flagged for 'not computing v' —
    that OVER-FIRES on the kern-fix-01/C3 restraint (the draft mentioning 'Hochdrehzahl' only
    qualitatively, the documented (iv) bug). Gates the trigger on KERN-VERDICT presence, not draft-text
    presence. I/O-free (reads ``computed_values`` — the same source as C2). Catch preserved: v computed →
    findings unchanged; only the velocity trap is gated, every other finding passes through."""
    if any(c.calc_id == "umfangsgeschwindigkeit" for c in computed_values):
        return findings
    return tuple(f for f in findings if f.trap_id != _CALC_VELOCITY_TRAP_ID)


def run_parametric_guard(
    draft: Answer,
    *,
    computed_values: tuple[ComputedValue, ...] = (),
    not_computed: tuple[NotComputed, ...] = (),
) -> tuple[Answer, VerifierVerdict | None]:
    """P0.3: the DETERMINISTIC parametric Schranke as a standalone, LLM-free guard.

    ``detect_parametric_leaks`` normally lives INSIDE ``run_verify``, so a disabled/unconfigured L3
    verifier (the incident kill-switch) would silently drop this trust-spine guard together with the
    LLM critic. The pipeline calls this on the no-verifier path so the parametric Schranke holds
    unconditionally. Pure: no LLM, no IO. Returns ``(answer, verdict)`` — ``verdict`` is None when clean."""
    leaks = detect_parametric_leaks(draft.text, computed_values=computed_values)
    if not leaks:
        return draft, None
    hedge_text = build_calc_leak_hedge(
        leaks, computed_values=computed_values, not_computed=not_computed
    )
    # Same backstop as run_verify: never let the hedge itself re-introduce a kern-quantity number.
    if detect_parametric_leaks(hedge_text, computed_values=computed_values):
        hedge_text = build_hedge((), None)
    hedge = Answer(
        text=hedge_text, model=_HEDGE_MODEL, grounding_facts=draft.grounding_facts
    )
    return hedge, VerifierVerdict(
        action=VerifierAction.BLOCKED_HEDGE,
        findings=_leak_findings(leaks),
        parse_ok=True,
        raw=None,
    )


async def run_verify(
    verifier: L3Verifier,
    generator,
    catalog: TrapCatalog,
    question: str,
    draft: Answer,
    *,
    flags: Flags,
    grounding_facts: tuple[GroundingFact, ...] = (),
    computed_values: tuple[ComputedValue, ...] = (),
    not_computed: tuple[NotComputed, ...] = (),
    matrix_facts: tuple[GroundingFact, ...] = (),
    calc: CalcResult | None = None,
    case_context: list[dict] | None = None,
    durable_context: list[dict] | None = None,
    conversation_window: list[dict] | None = None,
    untrusted: list[dict] | None = None,
) -> tuple[Answer, VerifierVerdict]:
    """The L3 policy: PASS / FLAG / CORRECTED (regenerate-once) / BLOCKED_HEDGE.

    M3/M4: L3 also sees the reviewed grounding facts + computed values and may FLAG a card or calc
    contradiction — but card/calc findings never block/correct (only reviewed TRAP findings do).
    Gap #2 (Step B): L3 also sees the reviewed §4 matrix verdicts; a reviewed MATRIX contradiction
    BLOCKS like a reviewed trap — regenerate-once against the cell's verdict, hedge if it re-fires
    (the matrix is a reviewed correction source beside the catalog; the replacement fact comes only
    from the reviewed cell). M8-C: the deterministic parametric-leak detector runs server-side on the
    draft AND on the regeneration (kind="calc_leak"); a leak BLOCKS. ``not_computed`` carries the
    kern's fail-closed reasons so note/hedge can NAME the missing inputs.
    OPTIMIZE_BACKLOG #5: the trap correction is TOPIC-SCOPED — ``question``/``case_context`` are threaded
    into the note/hedge builders so a material recommendation is injected only when the question matches
    the trap's topic; and the regeneration re-answers with the FULL draft context (grounding + matrix +
    ``calc`` + memory + untrusted), not a degraded one, so it can fix the flaw without losing grounding.
    ``generator`` is the injected L1 generator (duck-typed: ``await generator.generate(...)``)."""
    # §9.2 (affirmative "Teil X = Teil Y" interchangeability) is the single most dangerous claim, but it
    # is intentionally NOT guarded by a deterministic text matcher here: a regex over-fires on benign
    # echoes and alternatives questions (eval v21-qdrant-gate*: APP-01 and ALT-NEUTRAL-EMPTY-01 were
    # good answers wrongly hedged). §9.2 is held by the L1 prompt (gpt-5.1 — DEC-AEQUIVALENZ passes)
    # plus the deploy-blocking DEC-AEQUIVALENZ hard gate. The planned runtime backstop is a reviewed
    # equivalence-trap (L3 semantic, owner-reviewed — no regex false-positives), not a free-text guard.
    leaks = detect_parametric_leaks(draft.text, computed_values=computed_values)
    overlimit = detect_velocity_over_limit(draft.text, computed_values=computed_values)
    raw = await verifier.verify(
        question, draft.text, grounding_facts, computed_values, matrix_facts
    )
    # P0.1 fail-closed: the LLM verdict IS the catalog/matrix trap net. If it did not parse, that net
    # did NOT run — a no-findings PASS here would ship an UNVERIFIED draft as if clean (the §2/§9
    # "never confidently wrong" hole). Re-run the gate once (a transient bad sample); if it still will
    # not parse, treat verification as UNAVAILABLE and fail closed to a hedge below — never PASS.
    if not raw.parse_ok:
        raw = await verifier.verify(
            question, draft.text, grounding_facts, computed_values, matrix_facts
        )
    verify_unavailable = not raw.parse_ok
    # Eingriff 2: the CALC-velocity trap only counts when the kern computed a v verdict this turn.
    scoped = scope_calc_velocity_trap(raw.findings, computed_values)
    findings = scoped + _leak_findings(leaks) + overlimit
    if not findings and not verify_unavailable:
        return draft, VerifierVerdict(
            action=VerifierAction.PASS, parse_ok=raw.parse_ok, raw=raw.raw
        )

    reviewed = _reviewed_traps(scoped)
    reviewed_mx = _reviewed_matrix(scoped)
    if (
        not reviewed
        and not reviewed_mx
        and not leaks
        and not overlimit
        and not verify_unavailable
    ):
        # draft-trap and/or card-contradiction matches → advisory FLAG, never block/correct
        return draft, VerifierVerdict(
            action=VerifierAction.FLAG,
            findings=findings,
            parse_ok=raw.parse_ok,
            raw=raw.raw,
        )

    # Blocking cause: a reviewed trap, a reviewed matrix contradiction, and/or a calc leak → regen once.
    notes: list[str] = []
    if leaks:
        notes.append(
            build_calc_leak_note(
                leaks, computed_values=computed_values, not_computed=not_computed
            )
        )
    if overlimit:
        ol_note = build_overlimit_note(overlimit, computed_values=computed_values)
        if ol_note is not None:
            notes.append(ol_note)
    if reviewed:
        trap_note = build_correction_note(
            catalog, reviewed, question=question, case_context=case_context
        )
        if trap_note is not None:
            notes.append(trap_note)
    if reviewed_mx:
        mx_note = build_matrix_correction_note(matrix_facts, reviewed_mx)
        if mx_note is not None:
            notes.append(mx_note)

    persisting_leaks = leaks
    persisting_overlimit = overlimit
    persisting_traps = reviewed
    persisting_mx = reviewed_mx
    if notes:
        regen = await generator.generate(
            question,
            flags=flags,
            grounding_facts=grounding_facts
            + matrix_facts,  # = l1_grounding the draft used
            calc=calc,
            case_context=case_context,
            durable_context=durable_context,
            conversation_window=conversation_window,
            untrusted=untrusted,
            correction_note="\n\n".join(notes),
        )
        persisting_leaks = detect_parametric_leaks(
            regen.text, computed_values=computed_values
        )
        persisting_overlimit = detect_velocity_over_limit(
            regen.text, computed_values=computed_values
        )
        raw2 = await verifier.verify(
            question, regen.text, grounding_facts, computed_values, matrix_facts
        )
        scoped2 = scope_calc_velocity_trap(raw2.findings, computed_values)
        persisting_traps = _reviewed_traps(scoped2)
        persisting_mx = _reviewed_matrix(scoped2)
        if (
            not persisting_traps
            and not persisting_mx
            and not persisting_leaks
            and not persisting_overlimit
        ):
            return regen, VerifierVerdict(
                action=VerifierAction.CORRECTED,
                findings=findings,
                regenerated=True,
                parse_ok=raw.parse_ok,
                raw=raw.raw,
            )

    # No usable correction, or the regeneration still tripped L3 → fail closed to a hedge.
    # Hedge precedence: a persisting leak first (its hedge must not carry a number), then matrix, then trap.
    if persisting_leaks:
        hedge_text = build_calc_leak_hedge(
            persisting_leaks, computed_values=computed_values, not_computed=not_computed
        )
    elif persisting_overlimit:
        hedge_text = build_overlimit_hedge(
            persisting_overlimit, computed_values=computed_values
        )
    elif persisting_mx or reviewed_mx:
        hedge_text = build_matrix_hedge(matrix_facts, reviewed_mx or persisting_mx)
    elif reviewed or persisting_traps:
        hedge_text = build_hedge(
            reviewed or persisting_traps,
            catalog,
            question=question,
            case_context=case_context,
        )
    else:
        # P0.1: verify_unavailable — the catalog/matrix trap net could not run for this turn → a
        # number-free generic hedge (Orientierung, keine Freigabe), never a confident unverified answer.
        hedge_text = build_hedge((), None)
    # Backstop (kern-fix-01): build_hedge / build_matrix_hedge echo a reviewed entry's text VERBATIM.
    # If that text ever carries a plugged kern-quantity number, the emitted hedge would re-introduce
    # the very parametric leak the Schranke forbids (the canonical CALC-MEM-01 Turn-0 failure). The
    # draft/regen are already scanned above, but the hedge itself was not — re-scan it and fall back
    # to the number-free generic hedge. Catalog-content-independent; build_calc_leak_hedge is already
    # number-free by construction, so this only ever rewrites a leaking trap/matrix hedge.
    if detect_parametric_leaks(hedge_text, computed_values=computed_values):
        hedge_text = build_hedge((), None)
    hedge = Answer(
        text=hedge_text,
        model=_HEDGE_MODEL,
        grounding_facts=draft.grounding_facts,
    )
    return hedge, VerifierVerdict(
        action=VerifierAction.BLOCKED_HEDGE,
        findings=findings,
        regenerated=bool(notes),
        parse_ok=raw.parse_ok,
        raw=raw.raw,
    )
