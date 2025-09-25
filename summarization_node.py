from typing import AsyncIterator, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.services.langgraph.memory import get_summary_store, get_redis_memory
from app.services.memory.memory_core import save_memory_for_thread

summ_llm = ChatOpenAI(streaming=False, temperature=0, model="gpt-4o")
prompt   = ChatPromptTemplate.from_messages([
    ("system", "Fasse Dokumente + Gespräch kurz zusammen:"),
    MessagesPlaceholder("messages"),
    MessagesPlaceholder("retrieved_docs"),
])

async def summarization_node_stream(state: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
    # 1️⃣ saubere Dict-Nachrichten aufbauen
    def _clean(m: Dict[str, Any]):
        txt = m.get("content") or m.get("delta", {}).get("content")
        return {"role": m.get("role"), "content": txt} if txt else None
    clean_msgs = [_clean(m) for m in state.get("messages", []) if _clean(m)]

    # 2️⃣ Zusammenfassung erzeugen
    try:
        summary = await (prompt | summ_llm).ainvoke(
            {"messages": clean_msgs,
             "retrieved_docs": state.get("retrieved_docs", [])}
        )
        txt = summary.content
    except Exception as e:
        txt = f"[Summarize-Fehler] {e}"

    # 3️⃣ Persistieren (RAM + Redis)
    thread_id = state.get("thread_id")
    if thread_id and txt:
        save_memory_for_thread(thread_id, txt)           # RAM-Store
        await get_summary_store(thread_id).set(txt)      # Redis-Key
        get_redis_memory(thread_id).add_ai_message(txt)  # Chat-History

    # 4️⃣ Weiterreichen
    yield {**state, "summary": {"delta": {"content": txt}}}
