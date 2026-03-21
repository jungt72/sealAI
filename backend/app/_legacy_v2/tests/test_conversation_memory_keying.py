from app.services.memory import conversation_memory


def test_stm_key_includes_user_id_and_chat_id() -> None:
    key = conversation_memory._stm_key("user-1", "chat-1")
    assert key.endswith("user-1:chat-1")


def test_last_agent_key_includes_user_id_and_chat_id() -> None:
    key = conversation_memory._last_agent_key("user-1", "chat-1")
    assert key.endswith("user-1:chat-1:last_agent")
