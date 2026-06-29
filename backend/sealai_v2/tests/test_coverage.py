"""Coverage-Gate kernel tests (V2.2 SS4). The classifier is the I-COV-1 deterministic core, so the
truth table is exhaustive and the I-COV-3 dominant-axis safety property is fuzzed over all inputs."""

import pytest

from sealai_v2.core.coverage import (
    AxisCoverage as AX,
    CoverageStatus as CS,
    chemical_axis,
    classify_coverage,
)

# ── gegencheck verdict -> chemical-axis mapping ──────────────────────────────────────────────────


def test_chemical_none_is_not_applicable():
    assert chemical_axis(None) is AX.NOT_APPLICABLE


def test_chemical_disqualified_is_grounded():
    # a grounded NO is assertive evidence (SS6.2 "passt nicht (IN)")
    assert (
        chemical_axis({"disqualified": True, "reason": "x", "source": "MX-FKM-DAMPF"})
        is AX.GROUNDED
    )


def test_chemical_compatible_is_grounded():
    assert (
        chemical_axis({"disqualified": False, "basis": "matrix_compatible"})
        is AX.GROUNDED
    )


def test_chemical_conditional_is_border():
    assert (
        chemical_axis(
            {"disqualified": False, "basis": "matrix_conditional", "condition": "c"}
        )
        is AX.BORDER
    )


def test_chemical_no_data_is_missing():
    assert (
        chemical_axis({"disqualified": False, "basis": "no_matrix_data"}) is AX.MISSING
    )


def test_chemical_no_medium_is_missing():
    assert chemical_axis({"disqualified": False, "basis": "no_medium"}) is AX.MISSING


def test_chemical_unknown_basis_is_missing_conservative():
    assert chemical_axis({"disqualified": False, "basis": "wat"}) is AX.MISSING


# ── the deterministic combinator — truth table ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "chem,op,arch,expect",
    [
        (AX.GROUNDED, AX.GROUNDED, AX.NOT_APPLICABLE, CS.IN_ENVELOPE),
        (
            AX.GROUNDED,
            AX.NOT_APPLICABLE,
            AX.NOT_APPLICABLE,
            CS.IN_ENVELOPE,
        ),  # grounded compatibility q
        (
            AX.GROUNDED,
            AX.BORDER,
            AX.NOT_APPLICABLE,
            CS.PARTIAL_ENVELOPE,
        ),  # operating at the edge
        (
            AX.GROUNDED,
            AX.MISSING,
            AX.NOT_APPLICABLE,
            CS.PARTIAL_ENVELOPE,
        ),  # operating unknown
        (AX.GROUNDED, AX.GROUNDED, AX.GROUNDED, CS.IN_ENVELOPE),
        (AX.GROUNDED, AX.GROUNDED, AX.BORDER, CS.PARTIAL_ENVELOPE),
        (
            AX.BORDER,
            AX.GROUNDED,
            AX.NOT_APPLICABLE,
            CS.PARTIAL_ENVELOPE,
        ),  # bedingt dominates
        (AX.BORDER, AX.MISSING, AX.NOT_APPLICABLE, CS.PARTIAL_ENVELOPE),
        (
            AX.MISSING,
            AX.GROUNDED,
            AX.GROUNDED,
            CS.OUT_OF_ENVELOPE,
        ),  # no chemistry -> OUT even if op grounded
        (AX.ANALOG, AX.GROUNDED, AX.NOT_APPLICABLE, CS.ANALOG_ONLY),
        (
            AX.NOT_APPLICABLE,
            AX.GROUNDED,
            AX.NOT_APPLICABLE,
            CS.IN_ENVELOPE,
        ),  # pure geometry, op grounded
        (AX.NOT_APPLICABLE, AX.BORDER, AX.NOT_APPLICABLE, CS.PARTIAL_ENVELOPE),
        (
            AX.NOT_APPLICABLE,
            AX.NOT_APPLICABLE,
            AX.NOT_APPLICABLE,
            CS.OUT_OF_ENVELOPE,
        ),  # degenerate, no evidence
    ],
)
def test_status_truth_table(chem, op, arch, expect):
    assert (
        classify_coverage(chemical=chem, operating=op, archetype=arch).status is expect
    )


# ── safety invariants (fuzzed over all axis combinations) ────────────────────────────────────────


@pytest.mark.parametrize("op", list(AX))
@pytest.mark.parametrize("arch", list(AX))
def test_missing_chemical_never_in_envelope(op, arch):
    # I-COV-3: ungrounded chemistry can NEVER reach IN_ENVELOPE, whatever the other axes say.
    assert (
        classify_coverage(chemical=AX.MISSING, operating=op, archetype=arch).status
        is not CS.IN_ENVELOPE
    )


@pytest.mark.parametrize("op", list(AX))
@pytest.mark.parametrize("arch", list(AX))
def test_analog_chemical_is_always_analog_only(op, arch):
    assert (
        classify_coverage(chemical=AX.ANALOG, operating=op, archetype=arch).status
        is CS.ANALOG_ONLY
    )


@pytest.mark.parametrize("op", list(AX))
@pytest.mark.parametrize("arch", list(AX))
def test_conditional_chemical_is_never_in_envelope(op, arch):
    # `bedingt` chemistry is at best PARTIAL — never a clean IN.
    assert (
        classify_coverage(chemical=AX.BORDER, operating=op, archetype=arch).status
        is not CS.IN_ENVELOPE
    )


def test_result_carries_axes_and_summary():
    r = classify_coverage(chemical=AX.GROUNDED, operating=AX.BORDER)
    assert r.chemical is AX.GROUNDED and r.operating is AX.BORDER
    assert r.archetype is AX.NOT_APPLICABLE
    assert "chemical=grounded" in r.axis_summary()
    assert "operating=border" in r.axis_summary()


# ── adapters: archetype axis + the coverage_for / to_dict serialization surface ──────────────────


def test_archetype_axis_matched_profile_is_grounded():
    from sealai_v2.core.coverage import archetype_axis

    assert (
        archetype_axis({"archetyp": "getriebe", "interview_fragen": ["x"]})
        is AX.GROUNDED
    )


def test_archetype_axis_none_is_not_applicable():
    from sealai_v2.core.coverage import archetype_axis

    assert archetype_axis(None) is AX.NOT_APPLICABLE
    assert archetype_axis({}) is AX.NOT_APPLICABLE


def test_to_dict_is_a_render_surface():
    d = classify_coverage(chemical=AX.BORDER).to_dict()
    assert d["status"] == CS.PARTIAL_ENVELOPE.value
    assert d["chemical"] == AX.BORDER.value
    assert set(d) == {"status", "chemical", "operating", "archetype", "axes"}


def test_coverage_for_grounded_compatible_no_archetype_is_in():
    from sealai_v2.core.coverage import coverage_for

    d = coverage_for({"disqualified": False, "basis": "matrix_compatible"}, None)
    assert d["status"] == CS.IN_ENVELOPE.value


def test_coverage_for_disqualified_is_in_envelope():
    # a grounded NO is assertive (§6.2 "passt nicht (IN)")
    from sealai_v2.core.coverage import coverage_for

    d = coverage_for({"disqualified": True, "reason": "r", "source": "MX-X"}, None)
    assert d["status"] == CS.IN_ENVELOPE.value


def test_coverage_for_conditional_is_partial():
    from sealai_v2.core.coverage import coverage_for

    d = coverage_for(
        {"disqualified": False, "basis": "matrix_conditional", "condition": "c"}, None
    )
    assert d["status"] == CS.PARTIAL_ENVELOPE.value


def test_coverage_for_no_data_is_out():
    from sealai_v2.core.coverage import coverage_for

    d = coverage_for({"disqualified": False, "basis": "no_matrix_data"}, None)
    assert d["status"] == CS.OUT_OF_ENVELOPE.value


def test_coverage_for_no_pairing_but_archetype_is_in():
    # no material×medium (chemical N/A) but a recognised archetype → grounded on the archetype
    from sealai_v2.core.coverage import coverage_for

    d = coverage_for(None, {"archetyp": "getriebe"})
    assert d["status"] == CS.IN_ENVELOPE.value
