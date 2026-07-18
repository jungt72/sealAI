"""Pipeline-layer adapter for the Kandidaten-Spezifikation (Produktspec v3.1).

Maps the turn's case-state → a produktspec ``Fall``, runs the DETERMINISTIC spec, and serializes it to a
render dict. It lives in the PIPELINE layer on purpose: the ``produktspec`` package must stay a pure,
firewall-clean function of ``Fall`` (it imports neither ``core`` nor the case-state), so the case→Fall
glue belongs here, not there.

Doctrine:
  * FLAG-gated (``settings.produktspec_enabled``, default OFF) — wired but inert until the owner enables
    it (the expert Fachfreigabe + DIN-Lizenz NO-GO is an owner governance gate, not a technical one).
  * RWDR-scoped — the kernel's rules are DIN-3760 / RWDR ``reviewed_internal``; a non-RWDR seal type
    yields the structured ``not_available_for_seal_type`` marker below (OD-3), not a silent None —
    the caller/frontend can distinguish "this seal type is out of scope" from "nothing to specify yet".
  * ``medium_source = FREE_TEXT`` by construction — the conservative G2 gate: a chat/form medium is never
    an exact TDS/SDS reference, so the spec stays candidate-set-only and ≤ L1 (NEVER a single material).
  * A RENDER/serializer surface only — like gegencheck/decode/alternativen, it is NEVER injected into
    L1/L3, so the prompt + the eval stay byte-identical. This applies equally to the
    ``not_available_for_seal_type`` marker: it is visible only in ``PipelineResult.kandidaten_spec``,
    never in the L1 prompt — the narrator does not (and must not) comment on it.
  * Fail-OPEN on an actual compute error — any mapping/kernel EXCEPTION still degrades to plain None,
    unchanged from before OD-3. This is deliberately distinct from the non-RWDR case: an exception is
    an unexpected failure (fail-open, no marker), whereas a non-RWDR seal type is an expected, named
    structural scope boundary (fail-closed in the sense that it says so explicitly, never silent).
"""

from __future__ import annotations

import re
from enum import Enum

from sealai_v2.knowledge.produktspec.contracts import Fall, KandidatenSpec, MediumSource
from sealai_v2.knowledge.produktspec.spec_service import kandidaten_spezifikation

_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _num(wert: str | None) -> float | None:
    """Leading signed number from a case-state value ('40 mm'→40.0, '0,5 bar'→0.5, '-10 °C'→-10.0).
    German decimal comma → dot. None when no number is present (absence is meaningful for the Fall)."""
    if not wert:
        return None
    m = _NUM_RE.match(wert.strip().replace(",", "."))
    return float(m.group()) if m else None


def _flag(
    wert: str | None, *, true: tuple[str, ...], false: tuple[str, ...]
) -> bool | None:
    """A tri-state form value → bool | None (None = unknown; absence is meaningful)."""
    if not wert:
        return None
    w = wert.strip().lower()
    if any(t in w for t in true):
        return True
    if any(f in w for f in false):
        return False
    return None


def case_state_to_fall(facts, question: str) -> Fall:
    """Deterministic case-state → Fall. Only the clean, unit-bearing fields are mapped; everything else
    keeps the Fall default so that absence drives Defer/Kandidatenraum (the honest behaviour). The medium
    is carried as FREE_TEXT (G2) — the spec can never promote a single material from it."""
    g: dict[str, str] = {f.feld: f.wert for f in facts}
    return Fall(
        medium=g.get("medium", ""),
        medium_source=MediumSource.FREE_TEXT,
        temperatur_c=_num(g.get("betriebstemperatur")),
        druck_bar=_num(g.get("druck")),
        drehzahl_rpm=_num(g.get("drehzahl")),
        welle_d_mm=_num(g.get("wellendurchmesser")),
        welle_haerte_hrc=_num(g.get("haerte")),
        welle_drall=_flag(
            g.get("drall"), true=("drallbehaftet",), false=("drallfrei",)
        ),
        verschmutzung=_flag(
            g.get("verschmutzung"), true=("stark", "leicht"), false=("sauber",)
        ),
        rohtext=question,  # lets the kernel detect criticality (ATEX/Lebensmittel/Pharma → L0 escalation)
    )


def _enum(v):
    return v.value if isinstance(v, Enum) else v


def _serialize(spec: KandidatenSpec) -> dict:
    """KandidatenSpec → a JSON-able render dict (enums → their value). The structural invariants
    (``freigegeben`` False, ``final_design_code`` None) ride along so the UI can assert them; the
    Geltungsrahmen is always present."""
    return {
        "response_level": _enum(spec.response_level),
        "envelope_band": _enum(spec.envelope_band),
        "kritikalitaet": _enum(spec.kritikalitaet),
        "axes": [
            {
                "name": a.name,
                "value": a.value,
                "status": _enum(a.status),
                "begruendung": list(a.begruendung),
            }
            for a in spec.axes
        ],
        "material": {
            "kind": _enum(spec.material.kind),
            "primary": list(spec.material.primary),
            "alternatives": list(spec.material.alternatives),
            "escalation": list(spec.material.escalation),
            "excluded": list(spec.material.excluded),
            "reason_codes": list(spec.material.reason_codes),
            "next_question": list(spec.material.next_question),
            "validation_required": spec.material.validation_required,
        },
        "material_candidate_set": list(spec.material_candidate_set),
        "din_candidate_label": spec.din_candidate_label,
        "final_design_code": spec.final_design_code,  # always None (G3)
        "defer_gruende": list(spec.defer_gruende),
        "open_verifications": list(spec.open_verifications),
        "offene_punkte": list(spec.offene_punkte),
        "failure_mode_checklist": list(spec.failure_mode_checklist),
        "freigegeben": spec.freigegeben,  # always False (G1)
        "geltungsrahmen": spec.geltungsrahmen,
        "quellen": list(spec.quellen),
    }


def not_available_for_seal_type_marker(seal_type: str) -> dict:
    """The structured OD-3 marker for a seal type the Kandidaten-Spezifikation rule engine does not
    cover. Deliberately a DISTINCT shape from ``_serialize``'s render dict (discriminated by the
    ``status`` key, which the RWDR shape never has) so a caller can tell the two apart without
    guessing. A render/serializer value only -- never injected into L1/L3 (see module docstring)."""
    return {
        "status": "not_available_for_seal_type",
        "seal_type": seal_type,
        "geltungsrahmen": (
            f'Kandidaten-Spezifikation ist für den Dichtungstyp "{seal_type}" nicht '
            "verfügbar — die Regel-Engine deckt ausschließlich RWDR/DIN-3760 ab."
        ),
    }


def compute_kandidaten_spec(
    facts, question: str, *, enabled: bool, seal_type: str
) -> dict | None:
    """Flag-gated, RWDR-scoped entry. Returns the render dict; the structured
    ``not_available_for_seal_type`` marker (OD-3) for a non-RWDR seal type (the rules are
    RWDR/DIN-3760 only); or None when: disabled; or there is no substantive input yet (no medium
    AND no shaft diameter → nothing to specify, don't surface an empty spec). Fail-open on an
    actual compute error: any exception → plain None, unchanged from before OD-3 -- distinct from
    the deliberate non-RWDR marker, which is a structural scope boundary, not a failure."""
    if not enabled:
        return None
    normalized_seal_type = seal_type.strip().lower() if seal_type else ""
    if normalized_seal_type not in ("rwdr", ""):
        return not_available_for_seal_type_marker(seal_type)
    g: dict[str, str] = {f.feld: f.wert for f in facts}
    if not (g.get("medium") or g.get("wellendurchmesser")):
        return None
    try:
        return _serialize(kandidaten_spezifikation(case_state_to_fall(facts, question)))
    except Exception:
        return None
