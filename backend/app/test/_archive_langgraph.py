# 📁 app/test/test_langchain_graph.py

import asyncio
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_community.chat_message_histories import RedisChatMessageHistory
from app.config.settings import settings


async def test_langchain_memory():
    session_id = "test-session"
    memory = RedisChatMessageHistory(
        session_id=session_id,
        url="redis://redis:6379",
        ttl=60 * 60 * 24,
    )

    print("🧹 Lösche alten Verlauf …")
    await memory.clear()

    print("➕ Schreibe neue Verlaufseinträge …")
    await memory.add_user_message("Wie heißen Sie?")
    await memory.add_ai_message("Ich bin Jasper, Ihre technische KI.")

    print("📜 Aktueller Verlauf:")
    messages = await memory.get_messages()
    for msg in messages:
        print(f"- {msg.type.upper()}: {msg.content}")

    print("🤖 GPT wird jetzt mit Verlauf + neuer Frage abgefragt …")
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.1,
        openai_api_key=settings.openai_api_key,
    )

    full_prompt = messages + [HumanMessage(content="Wie haben Sie sich vorgestellt?")]
    response = await llm.ainvoke(full_prompt)

    print("\n🧠 GPT-Antwort:")
    print(response.content)


if __name__ == "__main__":
    asyncio.run(test_langchain_memory())
