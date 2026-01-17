from app.langgraph_v2.utils.threading import (
    reset_current_tenant_id,
    set_current_tenant_id,
    stable_thread_key,
)


def test_thread_key_includes_tenant():
    token = set_current_tenant_id("tenant-1")
    try:
        key = stable_thread_key("user-1", "chat-1")
    finally:
        reset_current_tenant_id(token)
    assert key == "tenant-1:user-1:chat-1"
