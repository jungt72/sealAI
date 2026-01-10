from unittest.mock import MagicMock

from app.services.chat import conversations

def test_upsert_trims_conversation_zset(monkeypatch) -> None:
    conversations.settings.chat_max_conversations_per_user = 2

    redis_client = MagicMock()
    pipeline = MagicMock()
    redis_client.pipeline.return_value = pipeline
    redis_client.hgetall.return_value = {}
    redis_client.zcard.return_value = 3
    monkeypatch.setattr(conversations, "_redis_client", lambda: redis_client)

    conversations.upsert_conversation(
        owner_id="user-1",
        conversation_id="chat-1",
        first_user_message="hi",
    )

    key_set = "chat:conversations:user-1"
    redis_client.zcard.assert_called_once()
    redis_client.zremrangebyrank.assert_called_once_with(key_set, 0, 0)
