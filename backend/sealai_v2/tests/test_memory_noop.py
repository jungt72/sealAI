"""The airtight memory no-op proof (build-spec §7; owner gate): with EMPTY/absent memory the
assembled system prompt is BYTE-IDENTICAL to the captured baseline.

This is the deterministic, zero-token guarantee that the wired memory seam has no systematic effect
on the answer path when memory is empty: if the prompt is byte-for-byte unchanged, the LLM draws
from the same distribution as before. The golden is an 8-config matrix (flags × grounding × calc),
all with empty memory and no ``conversation_window`` param.

The baseline is **re-captured whenever the prompt LEGITIMATELY changes** — re-captured at **M6a-B**
after the owner-approved additive ``# Gesprächsführung`` edge bullets, at **M8-A** after the
owner-approved additive calc-provenance line (diff = exactly the ``Eingaben:`` origin line in the 4
calc configs; recapture asserted additive-only), and at **M8-B** after the owner-approved
``# Berechnungen`` compute-constraint tightening (recapture asserted every changed line sits inside
that section, all 8 configs). This re-baselines the snapshot; it does NOT loosen the invariant —
``test_none_and_empty_memory_are_equivalent`` independently guards the relative no-op (None ≡
empty), which holds regardless of the prompt's content.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from sealai_v2.core.contracts import Flags
from sealai_v2.prompts.assembler import PromptAssembler

_GOLDEN = Path(__file__).resolve().parent / "golden_prompt_no_memory.json"

_GF = [
    type(
        "G",
        (),
        {
            "text": "EPDM ist unpolar; quillt in unpolaren Medien.",
            "quelle": "Fachkarte FK-EPDM (reviewed)",
        },
    )()
]
_CV = [
    {
        "name": "v_m_s",
        "value": 12.57,
        "unit": "m/s",
        "formula": "v=pi*d*n/60000",
        "stage": 1,
        "estimate": False,
        "assumptions": [],
        "inputs_used": ["d1_mm", "rpm"],
        "input_origins": ["Parameter", "Parameter"],  # M8-A payload shape
        "warnings": [],
    }
]


def test_empty_memory_prompt_is_byte_identical_to_baseline():
    matrix = json.loads(_GOLDEN.read_text(encoding="utf-8"))["matrix"]
    a = PromptAssembler()
    for cfg in matrix:
        fc, sc = cfg["flags"]
        # re-render WITH the new memory params, both empty — the no-memory path post-M5
        out = a.system_prompt(
            flags=Flags(compliance_hint=fc, safety_critical=sc),
            grounding_facts=(_GF if cfg["grounding"] else None),
            computed_values=(_CV if cfg["calc"] else None),
            case_context=[],
            conversation_window=[],
        )
        if out != cfg["out"]:
            diff = "\n".join(
                difflib.unified_diff(
                    cfg["out"].splitlines(),
                    out.splitlines(),
                    fromfile="baseline golden",
                    tofile="empty-memory render",
                    lineterm="",
                )
            )
            raise AssertionError(
                f"empty-memory prompt diverged from baseline (flags={cfg['flags']}, "
                f"grounding={cfg['grounding']}, calc={cfg['calc']}):\n{diff}"
            )


def test_none_and_empty_memory_are_equivalent():
    a = PromptAssembler()
    base = a.system_prompt(flags=Flags(False, False))
    explicit = a.system_prompt(
        flags=Flags(False, False), case_context=[], conversation_window=[]
    )
    assert base == explicit
