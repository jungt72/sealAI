from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id


def test_thread_key_includes_tenant():
    # New SoT: explicit tenant_id passing
    t_id = "tenant-1"
    u_id = "user-1"
    c_id = "chat-1"

    key = resolve_checkpoint_thread_id(
        tenant_id=t_id, 
        user_id=u_id, 
        chat_id=c_id
    )
    
    # Requirements:
    # - key contains tenant_id and user_id
    # - chat_id is normalized (so raw "chat-1" might not be visible, which is expected)
    assert t_id in key
    assert u_id in key
    assert isinstance(key, str)
    assert len(key) > 0
