import pytest
from pydantic import ValidationError

from app._legacy_v2.utils.confirm_go import ConfirmGoRequest


def test_confirm_go_request_requires_strict_bool() -> None:
    with pytest.raises(ValidationError):
        ConfirmGoRequest(chat_id="t1", go="true")  # type: ignore[arg-type]


def test_confirm_go_request_normalizes_legacy_go() -> None:
    request = ConfirmGoRequest(chat_id="t1", go=True)
    assert request.decision == "approve"
