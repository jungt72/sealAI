"""Offline regression tests for explicit sealing-type case entry."""

from sealai_v2.core.seal_type_extract import (
    extract_seal_type,
    extract_seal_type_facts,
)


def test_real_rwdr_entry_phrase_binds_canonical_case_fact() -> None:
    (fact,) = extract_seal_type_facts("ich benötige einen rwdr")

    assert (fact.feld, fact.wert, fact.provenance) == (
        "dichtungstyp",
        "RWDR",
        "chat-inline",
    )


def test_rwdr_pack_aliases_share_one_canonical_value() -> None:
    for phrase in (
        "Radialwellendichtring",
        "Radial-Wellendichtring",
        "Simmerring",
        "Wellendichtung",
    ):
        assert extract_seal_type(phrase) == "RWDR"


def test_synonyms_for_same_type_are_not_ambiguous() -> None:
    assert extract_seal_type("RWDR / Radialwellendichtring") == "RWDR"


def test_multiple_distinct_types_fail_closed() -> None:
    assert extract_seal_type("RWDR oder O-Ring") is None
    assert extract_seal_type_facts("RWDR oder O-Ring") == ()


def test_generic_request_does_not_guess_a_type() -> None:
    assert extract_seal_type_facts("Ich benötige eine Dichtung") == ()
