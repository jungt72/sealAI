from __future__ import annotations

import pytest

from app.domain.engineering_path import (
    AUTHORITY_ENGINEERING_PATHS,
    derive_engineering_path,
)


@pytest.mark.parametrize("engineering_path", sorted(AUTHORITY_ENGINEERING_PATHS))
def test_authority_engineering_path_is_preserved(engineering_path: str) -> None:
    assert derive_engineering_path(engineering_path=engineering_path) == engineering_path


def test_duplicate_identical_authority_signals_are_preserved() -> None:
    assert (
        derive_engineering_path(
            engineering_path="rwdr",
            authority_values=["rwdr", None, ""],
        )
        == "rwdr"
    )


@pytest.mark.parametrize("engineering_path", [None, "", "   "])
def test_empty_engineering_path_returns_none(engineering_path: object) -> None:
    assert derive_engineering_path(engineering_path=engineering_path) is None


@pytest.mark.parametrize("engineering_path", ["rotary", "RWDR", "rwdr ", "radial_shaft_seal"])
def test_unknown_explicit_engineering_path_returns_none(engineering_path: str) -> None:
    assert derive_engineering_path(engineering_path=engineering_path) is None


def test_mixed_authority_values_return_none() -> None:
    assert derive_engineering_path(authority_values=["rwdr", "static"]) is None


def test_unknown_mixed_with_authority_value_returns_none() -> None:
    assert derive_engineering_path(authority_values=["rwdr", "radial_shaft_seal"]) is None


@pytest.mark.parametrize(
    "signals",
    [
        {"motion_type": "rotary"},
        {"sealing_type": "rwdr"},
        {"seal_type": "radial_shaft_seal"},
        {"seal_family": "radial_shaft_seal"},
    ],
)
def test_neighbouring_signals_do_not_derive_engineering_path(signals: dict[str, str]) -> None:
    assert derive_engineering_path(**signals) is None
