from __future__ import annotations

import asyncio
import inspect
import sys
import types
from types import SimpleNamespace

import pytest


# Keep imports stable in isolated unit tests without requiring full runtime env.
if "app.core.config" not in sys.modules:
    config_stub = types.ModuleType("app.core.config")
    config_stub.settings = SimpleNamespace(
        qdrant_collection="test_collection",
        openai_temperature=0.0,
    )
    sys.modules["app.core.config"] = config_stub


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: run test in local asyncio event loop")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if "asyncio" not in pyfuncitem.keywords:
        return None
    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None
    kwargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
    asyncio.run(test_func(**kwargs))
    return True
