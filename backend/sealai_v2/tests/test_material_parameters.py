"""Material-parameter store + grounded table rendering. The numbers live in the kernel seed; L1 only
renders them. Flag OFF -> byte-identical; ON -> the table instruction + the kernel values are injected."""

from sealai_v2.core.contracts import Flags
from sealai_v2.knowledge.material_parameters import (
    _validated_blocks,
    lookup,
    material_parameters_for,
)
from sealai_v2.prompts.assembler import PromptAssembler


def test_lookup_ptfe_is_reviewed_with_source_conditioned_params():
    p = lookup("ptfe")
    assert p and p["material"] == "PTFE" and p["review_state"] == "reviewed"
    assert any("temperatur" in x["label"].lower() for x in p["params"])
    assert all(x.get("basis") for x in p["params"])
    assert p.get("sources")


def test_lookup_unknown_is_none():
    assert lookup("Kryptonit") is None
    assert lookup("") is None


def test_reviewed_parameter_block_requires_sources_and_per_value_basis():
    block = {
        "PTFE": {
            "review_state": "reviewed",
            "params": [{"label": "Temperatur", "value": "260 C"}],
        }
    }
    try:
        _validated_blocks(block)
    except ValueError as exc:
        assert "sources" in str(exc)
    else:
        raise AssertionError("reviewed parameter block without sources was accepted")


def test_materials_for_question():
    mp = material_parameters_for("bitte gib mir informationen über ptfe")
    assert len(mp) == 1 and mp[0]["material"] == "PTFE"
    assert material_parameters_for("eine Frage ganz ohne Werkstoff") == []


def test_assembler_off_is_byte_identical():
    asm = PromptAssembler()
    assert asm.system_prompt(flags=Flags()) == asm.system_prompt(
        flags=Flags(), material_params=None
    )


def test_assembler_on_injects_table_instruction_and_kernel_values():
    asm = PromptAssembler()
    on = asm.system_prompt(flags=Flags(), material_params=[lookup("PTFE")])
    assert "Werkstoff-Kennwerte" in on and "Tabelle" in on and "PTFE" in on
    # the value comes from the seed (kernel), not invented by L1 — present verbatim in the prompt
    assert "260 °C" in on
    assert "Bezugsbasis" in on and "kein Familienlimit" in on
    assert "—" in on  # the missing-parameter marker instruction
