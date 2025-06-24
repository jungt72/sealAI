# backend/app/services/prompt/prompt_orchestrator.py

"""
Prompt-Orchestrator für zentrale, versionierbare Prompt-Verwaltung.
Alle Prompts liegen als Datei im Verzeichnis 'services/prompts/'.
Einheitlicher Zugriff für alle Chains, Retrieval-Flows und später LangGraph-Nodes.
"""

from langchain_core.prompts import ChatPromptTemplate

def build_dynamic_prompt(inputs: dict = None) -> ChatPromptTemplate:
    """
    Gibt ein ChatPromptTemplate für den Haupt-Chat zurück.
    Erwartet ein Dict mit den Prompt-Parametern (kann leer sein).
    System- und User-Message werden explizit definiert (Best Practice!).
    """
    template = [
        # System-Anweisung
        ("system",
         "Du bist ein freundlicher, präziser KI-Assistent für technische Beratung im Bereich Dichtungstechnik. "
         "Antworte **immer** zuerst anhand der vorhandenen Kontextinformationen ([RAG-Kontext], [Kontext/Summary], "
         "[Ergebnisse/Parameter]), bevor du Rückfragen stellst. "
         "Wenn du Informationen nicht findest, stelle gezielte Rückfragen."),
        # User-Kontext
        ("user",
         "[Kontext/Summary]\n{summary}\n\n"
         "[Ergebnisse/Parameter]\n{computed}\n\n"
         "[RAG-Kontext]\n{context}\n\n"
         "[Verlauf/Mitteilungen]\n{chat_history}\n\n"
         "[Nutzerfrage]\n{input}")
    ]
    return ChatPromptTemplate.from_messages(template)
