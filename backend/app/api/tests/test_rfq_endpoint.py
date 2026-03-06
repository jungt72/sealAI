from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.rfq import rfq_download


def test_rfq_download_is_disabled_even_with_server_path() -> None:
    with pytest.raises(HTTPException) as exc_info:
        rfq_download("/etc/passwd")

    assert exc_info.value.status_code == 410
    assert "temporarily disabled" in str(exc_info.value.detail)
