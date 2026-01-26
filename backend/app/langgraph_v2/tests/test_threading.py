import pytest
import uuid
from app.langgraph_v2.sealai_graph_v2 import build_v2_config
from app.langgraph_v2.utils.threading import (
    _CHAT_ID_NAMESPACE,
    resolve_checkpoint_thread_id,
    stable_thread_key,
)

def test_stable_thread_key_requires_tenant():
    with pytest.raises(ValueError, match="missing tenant_id"):
        stable_thread_key(user_sub="user-123", conversation_id="chat-abc", tenant_id=None)

def test_stable_thread_key_scoped():
    # Tenant provided -> scoped format
    key = stable_thread_key(user_sub="user-123", conversation_id="chat-abc", tenant_id="tenant-1")
    assert key == "tenant-1:user-123:chat-abc"

def test_resolve_checkpoint_thread_id_normalizes_chat_id():
    # Spaces should be stripped/normalized - BUT must be valid UUID
    # mocking valid uuid
    valid_id = str(uuid.uuid4())
    chat_id = f"  {valid_id}  "
    key = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-123",
        chat_id=chat_id
    )
    assert key == f"tenant-1:user-123:{valid_id}"

def test_resolve_checkpoint_thread_id_requires_tenant_if_present():
    # Pass tenant explicitly
    valid_id = str(uuid.uuid4())
    key = resolve_checkpoint_thread_id(
        tenant_id="t-1",
        user_id="u-1",
        chat_id=valid_id
    )
    assert key == f"t-1:u-1:{valid_id}"

def test_resolve_checkpoint_thread_id_requires_tenant():
    valid_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="missing tenant_id"):
        resolve_checkpoint_thread_id(
            tenant_id=None,
            user_id="u-1",
            chat_id=valid_id
        )

def test_resolve_checkpoint_thread_id_handles_thread_prefix():
    # Frontend sends "thread-" prefix sometimes
    valid_id = str(uuid.uuid4())
    chat_id = f"thread-{valid_id}"
    key = resolve_checkpoint_thread_id(
        tenant_id="t-1",
        user_id="u-1",
        chat_id=chat_id
    )
    assert key == f"t-1:u-1:{valid_id}"

def test_resolve_checkpoint_thread_id_non_uuid_is_deterministic():
    chat_id = "chat-123"
    expected = str(uuid.uuid5(_CHAT_ID_NAMESPACE, "tenant-1:user-123:chat-123"))
    first = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-123",
        chat_id=chat_id
    )
    second = resolve_checkpoint_thread_id(
        tenant_id="tenant-1",
        user_id="user-123",
        chat_id=chat_id
    )
    assert first == f"tenant-1:user-123:{expected}"
    assert second == first


def test_build_v2_config_normalizes_non_uuid_chat_id():
    config = build_v2_config(thread_id="test2", user_id="u1", tenant_id="t1")
    configurable = config.get("configurable", {})
    checkpoint_thread_id = configurable.get("thread_id")
    assert isinstance(checkpoint_thread_id, str)
    parts = checkpoint_thread_id.split(":")
    assert parts[0] == "t1"
    assert parts[1] == "u1"
    assert str(uuid.UUID(parts[2])) == parts[2]
