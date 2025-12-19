import faulthandler
import os
import sys

import pytest


@pytest.fixture(autouse=True, scope="session")
def _faulthandler_watchdog():
    timeout = os.getenv("PYTEST_FAULTHANDLER_TIMEOUT", "")
    try:
        seconds = int(timeout) if timeout else 0
    except ValueError:
        seconds = 0
    if seconds > 0:
        faulthandler.dump_traceback_later(seconds, file=sys.stderr, repeat=False)
    try:
        yield
    finally:
        if seconds > 0:
            faulthandler.cancel_dump_traceback_later()
