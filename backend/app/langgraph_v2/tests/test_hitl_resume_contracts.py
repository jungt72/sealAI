import pytest
from pydantic import ValidationError

from app.langgraph_v2.contracts import HITLResumeRequest


def test_hitl_resume_request_valid() -> None:
    payload = HITLResumeRequest(
        checkpoint_id="chk-1",
        command={"action": "approve", "feedback": "looks good", "override_params": {"pressure_bar": 12}},
    )
    assert payload.command.action == "approve"


def test_hitl_resume_request_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        HITLResumeRequest(
            checkpoint_id="chk-1",
            command={"action": "reject", "unexpected": True},
            unexpected_top=True,
        )
