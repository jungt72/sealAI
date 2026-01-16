import uuid
import pytest
from fastapi.exceptions import HTTPException

from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id



def _is_uuid4(s: str) -> bool:
    try:
        val = uuid.UUID(s, version=4)
        return str(val) == s
    except Exception:
        return False


def test_resolve_checkpoint_thread_id_accepts_uuid_chat_id():
    """A provided chat_id must be a strict UUIDv4 and must be preserved in the key."""
    chat_id = str(uuid.uuid4())

    key = resolve_checkpoint_thread_id(
        tenant_id="acme",
        user_id="u1",
        chat_id=chat_id,
    )

    assert key == f"acme:u1:{chat_id}"


def test_resolve_checkpoint_thread_id_generates_uuid_when_missing():
    """If chat_id is missing/empty, a UUIDv4 is generated and used."""
    key = resolve_checkpoint_thread_id(
        tenant_id="acme",
        user_id="u1",
        chat_id=None,
    )

    parts = key.split(":")
    assert parts[0] == "acme"
    assert parts[1] == "u1"
    assert len(parts) == 3
    assert _is_uuid4(parts[2])


@pytest.mark.parametrize("bad_chat_id", [" Default ", "session-1", "not-a-uuid", "{123}"])
def test_resolve_checkpoint_thread_id_rejects_non_uuid_chat_id(bad_chat_id):
    """Non-UUID chat_id must be rejected to prevent collisions and ensure determinism."""
    with pytest.raises(HTTPException) as e:
        resolve_checkpoint_thread_id(
            tenant_id="corp-a",
            user_id="alice",
            chat_id=bad_chat_id,
        )

    assert e.value.status_code == 400
