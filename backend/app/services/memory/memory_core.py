# backend/app/services/memory/memory_core.py

"""
Memory Core: Multi-Layer-Architektur für Kurzzeit-, Mittel- und Langzeitgedächtnis.
Short-Term: Sliding Window in Redis. 
Mid-Term: LLM-basierte Zusammenfassung als Anchor.
Long-Term: Persistente Speicherung in Vektorstore (Qdrant).
"""

from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain.memory import ConversationSummaryMemory
from langchain_community.vectorstores import Qdrant
from langchain_community.embeddings import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from app.core.config import settings
from app.services.llm.llm_factory import get_llm  # Dein LLM-Lader; ggf. anpassen

def get_redis_history_key(username: str, chat_id: str) -> str:
    return f"chat_history:{username}:{chat_id}"

def get_memory_for_thread(session_id: str, window_size: int = 10) -> RedisChatMessageHistory:
    try:
        username, chat_id = session_id.split(":", 1)
    except ValueError:
        username = session_id
        chat_id = "default"
    return RedisChatMessageHistory(
        session_id=get_redis_history_key(username, chat_id),
        url=settings.redis_url,
        ttl=None,
        # window_size (falls von deiner LangChain-Version unterstützt; sonst aufrufen: memory.messages[-window_size:])
    )

def build_summary_memory(session_id: str) -> ConversationSummaryMemory:
    try:
        username, chat_id = session_id.split(":", 1)
    except ValueError:
        username = session_id
        chat_id = "default"
    chat_memory = RedisChatMessageHistory(
        session_id=f"chat_history:{username}:{chat_id}",
        url=settings.redis_url,
    )
    return ConversationSummaryMemory(
        llm=get_llm(),
        chat_memory=chat_memory,
        return_messages=True,
        memory_key="chat_history",
        summary_message_key="summary",
        moving_summary_buffer="",
    )

def get_longterm_vectorstore():
    embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)
    qdrant_client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    return Qdrant(
        client=qdrant_client,
        collection_name=settings.qdrant_collection,
        embeddings=embeddings,
    )
