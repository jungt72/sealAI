"""L3 Verifier — the independent critic pass (build-spec §4/§5, Prinzipien §2-L3).

An L1 draft is checked against the OWNER-AUTHORED trap catalog (M2: the catalog only; the matrix
arrives at M3). Hard-gate violations grounded in a ``reviewed`` entry BLOCK — preferring a
regenerate-once against the entry's ``correct`` fact, else a fail-closed hedge. Soft / draft-only
matches FLAG. The integrity rule is structural: a correction's replacement fact comes ONLY from a
``reviewed`` catalog entry — L3 never free-generates a correction (build-spec §4 "darf nicht: eine
eigene Wahrheitsquelle erfinden").

Provider-agnostic: this module talks to the injected ``LlmClient`` Protocol only — no OpenAI, no
network of its own (``core`` stays I/O-free, build-spec §3). The verifier model is config; a
cross-vendor swap is a different adapter + a config flip, no change here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sealai_v2.core.contracts import (
    Answer,
    ComputedValue,
    Flags,
    GroundingFact,
    LlmClient,
    ModelConfig,
    VerifierAction,
    VerifierFinding,
    VerifierPromptAssembler,
    VerifierVerdict,
)
from sealai_v2.knowledge.traps import TrapCatalog

_HEDGE_MODEL = "l3-hedge"  # sentinel: the hedge is deterministic, not model-generated

# --- precision over-application guard (firing condition only — NOT the reviewed `correct` facts) ---
# The range-precision traps fire on a "falsch-präzise Einzelzahl OHNE Bereich". A value already
# given as a RANGE *with* a verify/Datenblatt caveat is the correct form, not a violation — yet the
# verifier model sometimes flags it anyway (m2-l3: TRAP-01 "ca. 120–130 °C … gegen Datenblatt
# verifizieren"). This is the deterministic backstop to the verifier prompt's existing
# "Bereich ist kein Verstoß" rule. It scopes ONLY the firing condition; it never edits the catalog.
_PRECISION_RANGE_TRAPS = frozenset({"PREC-EINZELZAHL", "PREC-LEBENSDAUER"})
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
    """True iff a RANGE-precision trap (PREC-EINZELZAHL / PREC-LEBENSDAUER) was raised on a quantity
    that is ALREADY presented as a range AND carries a verify/Datenblatt caveat — i.e. L3
    over-applied the "Einzelzahl OHNE Bereich" scope. Checks the evidence AND the draft answer (the
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
    ) -> _RawVerdict:
        gf_payload = [
            {"text": f.text, "card_id": f.card_id, "quelle": f.quelle}
            for f in grounding_facts
        ]
        cv_payload = [
            {"name": c.name, "value": c.value, "unit": c.unit, "calc_id": c.calc_id}
            for c in computed_values
        ]
        system = self._assembler.verifier_system_prompt(
            traps=_trap_payload(self._catalog),
            grounding_facts=gf_payload,
            computed_values=cv_payload,
        )
        user = (
            f"FRAGE:\n{question}\n\n"
            f'ENTWURFSANTWORT (zu prüfen):\n"""\n{answer_text}\n"""\n\n'
            "Prüfe die Entwurfsantwort gegen den Fallen-Katalog, die geerdeten Fakten und die "
            "berechneten Werte und gib NUR das JSON zurück."
        )
        res = await self._client.generate(
            system=system, user=user, model_config=self._model_config
        )
        card_ids = frozenset(f.card_id for f in grounding_facts if f.card_id)
        calc_refs = frozenset(
            [c.name for c in computed_values] + [c.calc_id for c in computed_values]
        )
        return self._parse(
            res.text, draft=answer_text, card_ids=card_ids, calc_refs=calc_refs
        )

    def _parse(
        self,
        raw: str,
        draft: str = "",
        card_ids: frozenset[str] = frozenset(),
        calc_refs: frozenset[str] = frozenset(),
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


def build_correction_note(
    catalog: TrapCatalog, findings: tuple[VerifierFinding, ...]
) -> str | None:
    """The catalog-grounded correction for a regeneration — built ONLY from ``reviewed`` entries
    (integrity rule). Returns None when no reviewed correct-fact is available (→ caller hedges)."""
    seen: set[str] = set()
    facts: list[str] = []
    for f in findings:
        if f.trap_id in seen:
            continue
        entry = catalog.by_id(f.trap_id)
        if entry is None or not entry.reviewed or not entry.correct.strip():
            continue
        seen.add(f.trap_id)
        facts.append(entry.correct.strip())
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
    findings: tuple[VerifierFinding, ...], catalog: TrapCatalog | None = None
) -> str:
    """Deterministic fail-closed fallback. Output integrity: it NEVER echoes the flagged WRONG claim.
    When a reviewed correct fact is available (L3 already holds it), the hedge STATES that correct
    fact + the verify/no-release caveat; otherwise it flags the concern generically without asserting
    any replacement. Scoped per the safety language (orientation, verify, keine Freigabe)."""
    correct_facts: list[str] = []
    if catalog is not None:
        seen: set[str] = set()
        for f in findings:
            if f.trap_id in seen:
                continue
            entry = catalog.by_id(f.trap_id)
            if entry is not None and entry.reviewed and entry.correct.strip():
                seen.add(f.trap_id)
                correct_facts.append(entry.correct.strip())
    if correct_facts:
        bullets = "\n".join(f"- {c}" for c in correct_facts)
        return (
            "⚠️ Hier ist Vorsicht geboten. Die interne Verifikation (L3) hat im Entwurf eine "
            "bekannte Falle / einen selbstbewusst-falschen Mechanismus markiert. Nach geprüftem "
            "Stand gilt:\n"
            + bullets
            + "\nDas ist nur eine ingenieurtechnische Orientierung — "
            "bitte gegen das Datenblatt des konkreten Werkstoffs bzw. mit dem Hersteller "
            "verifizieren; keine Freigabe."
        )
    return (
        "⚠️ Hier ist Vorsicht geboten. Die interne Verifikation (L3) hat in diesem Entwurf einen "
        "möglichen Fehler / eine bekannte Falle markiert. Ohne eine geprüfte Quelle kann ich dazu "
        "keine belastbare Aussage treffen — bitte gegen das Datenblatt des konkreten Werkstoffs "
        "bzw. mit dem Hersteller verifizieren. Das ist nur eine Orientierung, keine Freigabe."
    )


def _reviewed_traps(
    findings: tuple[VerifierFinding, ...],
) -> tuple[VerifierFinding, ...]:
    """Only reviewed TRAP findings drive a block/correction. Card-contradiction findings (kind=
    'card') and draft matches are FLAG-only — corrections come ONLY from reviewed traps (integrity)."""
    return tuple(
        f for f in findings if f.review_state == "reviewed" and f.kind == "trap"
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
) -> tuple[Answer, VerifierVerdict]:
    """The L3 policy: PASS / FLAG / CORRECTED (regenerate-once) / BLOCKED_HEDGE.

    M3/M4: L3 also sees the reviewed grounding facts + computed values and may FLAG a card or calc
    contradiction — but card/calc findings never block/correct (only reviewed TRAP findings do).
    ``generator`` is the injected L1 generator (duck-typed: ``await generator.generate(...)``)."""
    raw = await verifier.verify(question, draft.text, grounding_facts, computed_values)
    if not raw.findings:
        return draft, VerifierVerdict(
            action=VerifierAction.PASS, parse_ok=raw.parse_ok, raw=raw.raw
        )

    reviewed = _reviewed_traps(raw.findings)
    if not reviewed:
        # draft-trap and/or card-contradiction matches → advisory FLAG, never block/correct
        return draft, VerifierVerdict(
            action=VerifierAction.FLAG,
            findings=raw.findings,
            parse_ok=raw.parse_ok,
            raw=raw.raw,
        )

    correction = build_correction_note(catalog, reviewed)
    if correction is not None:
        regen = await generator.generate(
            question, flags=flags, correction_note=correction
        )
        raw2 = await verifier.verify(
            question, regen.text, grounding_facts, computed_values
        )
        if not _reviewed_traps(raw2.findings):
            return regen, VerifierVerdict(
                action=VerifierAction.CORRECTED,
                findings=raw.findings,
                regenerated=True,
                parse_ok=raw.parse_ok,
                raw=raw.raw,
            )

    # No usable reviewed correction, or regeneration still tripped L3 → fail closed to a hedge.
    hedge = Answer(
        text=build_hedge(reviewed, catalog),
        model=_HEDGE_MODEL,
        grounding_facts=draft.grounding_facts,
    )
    return hedge, VerifierVerdict(
        action=VerifierAction.BLOCKED_HEDGE,
        findings=raw.findings,
        regenerated=correction is not None,
        parse_ok=raw.parse_ok,
        raw=raw.raw,
    )
