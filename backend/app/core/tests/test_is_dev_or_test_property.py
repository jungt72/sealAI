"""Pins the security-relevant derivation `app_env → Settings.is_dev_or_test`.

The auth bypass in `app/services/auth/dependencies.py` gates on
`settings.is_dev_or_test`. This property must be False for any non dev/test
environment so the bypass stays disabled in production.

These are pure property tests on the REAL `Settings` class. They load
`app/core/config.py` directly by file path rather than `import app.core.config`,
because a suite-level fixture (`app/agent/tests/conftest.py`) replaces
`sys.modules["app.core.config"]` with a stub that exposes only the `settings`
instance and not the `Settings` class. Loading by path keeps this test robust
and independent of that stubbing. We use `model_construct` so no DB/env fields
are required and no global singleton is touched.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.py"


def _load_real_settings_cls():
    spec = importlib.util.spec_from_file_location(
        "_real_app_core_config_for_property_test", _CONFIG_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.Settings


_Settings = _load_real_settings_cls()


def _settings_with_app_env(app_env: str):
    # model_construct skips validation/required-field loading; the property only
    # reads `app_env`, so this is isolated from env and suite fixtures.
    return _Settings.model_construct(app_env=app_env)


@pytest.mark.parametrize("app_env", ["dev", "development", "local", "test"])
def test_is_dev_or_test_true_for_dev_and_test_envs(app_env: str) -> None:
    assert _settings_with_app_env(app_env).is_dev_or_test is True


@pytest.mark.parametrize(
    "app_env",
    ["production", "prod", "staging", "preprod", "", "PRODUCTION"],
)
def test_is_dev_or_test_false_outside_dev_or_test(app_env: str) -> None:
    assert _settings_with_app_env(app_env).is_dev_or_test is False


@pytest.mark.parametrize(
    ("app_env", "expected"),
    [("  TEST  ", True), ("Development", True), ("  Production ", False)],
)
def test_is_dev_or_test_normalizes_case_and_whitespace(app_env: str, expected: bool) -> None:
    assert _settings_with_app_env(app_env).is_dev_or_test is expected
