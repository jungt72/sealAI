"""Phase 2b — the deterministic parameter-submit confirmation (the 'übernommen' message).

Pure, LLM-free assembly. Echoes the POST-BIND settled value (the bound kernel value, or a settled
context fact), NOT the raw submitted string — so a residual mis-parse (e.g. a 0-bar settle) is visible
in the 'übernommen' line and never hidden. A clarify-triggering value is surfaced as a Rückfrage (the
binder's structured clarification), never claimed as taken. The kern results come from the same
deterministic recompute that drives /compute.
"""

from __future__ import annotations

from sealai_v2.api.serializers import compute_response
from sealai_v2.core.calc.binding import bind_params, bound_display
from sealai_v2.core.calc.derived import DerivedComputation
from sealai_v2.core.contracts import RememberedFact


def build_param_confirmation(
    items: list[dict],
    settled: tuple[RememberedFact, ...],
    comp: DerivedComputation,
) -> dict:
    """Assemble the confirmation from the binder (post-bind truth) + the kern result. ``items`` is the
    submitted order (carries the display ``label`` from the form schema); ``settled`` is the current
    case-state after the writes; ``comp`` is the recompute (derived + not_computed + clarifications)."""
    binding = bind_params(settled)
    bound = bound_display(
        binding
    )  # feld → post-bind "value unit" (bound kernel inputs only)
    clar_by_feld = {c.feld: c for c in binding.clarifications}
    settled_by_feld = {f.feld: f for f in settled}

    panel = compute_response(comp)  # {computed, not_computed, notes, clarifications}
    clar_dicts = {c["feld"]: c for c in panel["clarifications"]}

    uebernommen: list[dict] = []
    rueckfragen: list[dict] = []
    seen: set[str] = set()
    for it in items:
        feld = str(it.get("feld", "")).strip()
        if not feld or feld in seen:
            continue
        seen.add(feld)
        label = str(it.get("label") or feld)
        if feld in clar_by_feld:
            # clarify-pending → a Rückfrage; the value was NOT taken
            rueckfragen.append(
                {"feld": feld, "label": label, "clarification": clar_dicts[feld]}
            )
        elif feld in bound:
            # bound kernel input (d1/rpm, the user typed it) → echo the POST-BIND value (confirmed).
            uebernommen.append({"feld": feld, "label": label, "wert": bound[feld]})
        elif feld in settled_by_feld:
            # context fact (medium, seal-TYPE pack-assumption, …) — system-EXTRACTED or a forced calc-pack
            # default, NOT a value the user typed. Surface it TENTATIVELY so an auto-detected medium or an
            # assumed seal type is never shown as a settled fact (honesty / "Kandidat nicht final"): the
            # user confirms or corrects it. Kernel inputs above stay confirmed.
            uebernommen.append(
                {
                    "feld": feld,
                    "label": f"{label} (erkannt — bitte bestätigen)",
                    "wert": settled_by_feld[feld].wert,
                    "tentativ": True,
                }
            )

    return {
        "uebernommen": uebernommen,
        "rueckfragen": rueckfragen,
        "computed": panel["computed"],
        "not_computed": panel["not_computed"],
        "notes": panel["notes"],
        "clarifications": panel["clarifications"],
    }
