"""Case.seal_spec / Case.medium population from the turn question (Modus-E Inc).

The typed Case slots (§5.1) fill from the pure extractors at the pipeline
generalisation point. CRITICAL invariant (owner decision 2): ``to_prompt_context``
stays BYTE-IDENTICAL — only ``facts`` reach the prompt, so populating the typed
slots never perturbs L1/L3 or the eval.

Deterministic, offline, no LLM.
"""

from __future__ import annotations

from sealai_v2.core.contracts import Case, RememberedFact


def test_question_populates_seal_spec_and_medium():
    cs = (RememberedFact(feld="Anwendung", wert="Getriebe"),)
    case = Case.from_case_state(
        cs, question="Wir verwenden FKM in Heißdampf, passt das?"
    )
    assert case.seal_spec == {"material": "FKM"}
    assert case.medium == {"name": "Heißdampf"}


def test_no_question_leaves_slots_none():
    cs = (RememberedFact(feld="Anwendung", wert="Getriebe"),)
    case = Case.from_case_state(cs)
    assert case.seal_spec is None
    assert case.medium is None


def test_question_without_material_leaves_seal_spec_none():
    case = Case.from_case_state((), question="Welches Medium verträgt Heißdampf?")
    assert case.seal_spec is None
    assert case.medium == {"name": "Heißdampf"}


def test_to_prompt_context_byte_identical_regardless_of_slots():
    cs = (RememberedFact(feld="Medium", wert="Heißdampf"),)
    without_q = Case.from_case_state(cs)
    with_q = Case.from_case_state(cs, question="FKM in Heißdampf passt das?")
    assert without_q.to_prompt_context() == with_q.to_prompt_context()
    assert with_q.to_prompt_context() == [{"feld": "Medium", "wert": "Heißdampf"}]
