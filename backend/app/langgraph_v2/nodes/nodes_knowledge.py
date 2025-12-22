"""
Knowledge Nodes mit RAG-Augmentation (Best Practice Nov 2025).

Jeder Node nutzt search_knowledge_base Tool für faktische Informationen.
"""
from typing import Dict

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state.sealai_state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.rag_tool import search_knowledge_base
from app.core.llm_client import run_llm, get_model_tier
from app.utils.message_helpers import latest_user_text


def knowledge_router_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Router für Knowledge-Anfragen.
    
    Entscheidet zwischen:
    - knowledge_material (Werkstoffe, Elastomere)
    - knowledge_lifetime (Lebensdauer, Standzeit)
    - generic_sealing_qa (allgemeine Fragen)
    """
    user_text = latest_user_text(state.get("messages")) or ""
    model_name = get_model_tier("mini")
    
    # LLM klassifiziert die Anfrage
    classification = run_llm(
        model=model_name,
        prompt=f"Klassifiziere diese Frage: '{user_text}'\n\nAntworte nur mit: material, lifetime oder generic",
        system="Du bist ein Klassifizierer für Dichtungstechnik-Fragen.",
        temperature=0.0,
        max_tokens=10,
        metadata={"node": "knowledge_router_node"}
    ).strip().lower()
    
    # Routing-Logik
    if "material" in classification:
        route = "knowledge_material"
    elif "lifetime" in classification or "lebensdauer" in classification:
        route = "knowledge_lifetime"
    else:
        route = "generic_sealing_qa"
    
    return {
        "messages": list(state.get("messages") or []),
        "phase": PHASE.KNOWLEDGE,
        "last_node": "knowledge_router_node",
        "route": route
    }


def knowledge_material_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Wissens-Node für Dichtungswerkstoffe (NBR, FKM, EPDM etc.).
    
    **Best Practice Nov 2025**: RAG-Augmentation vor LLM-Call.
    """
    user_text = latest_user_text(state.get("messages"))
    model_name = get_model_tier("mini")
    
    # RAG-Retrieval VOR LLM-Call
    rag_context = search_knowledge_base.invoke({
        "query": user_text,
        "category": "materials",
        "k": 3,
        "tenant": state.user_id,
    })
    
    # Augmentierter Prompt mit RAG-Kontext
    prompt = f"""Kontext aus Wissensdatenbank:
{rag_context}

Frage des Nutzers: {user_text}

Beantworte die Frage basierend auf dem Kontext. Zitiere Quellen wenn möglich."""
    
    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=(
            "Du bist ein Fachberater für Dichtungswerkstoffe. "
            "Nutze die bereitgestellten Informationen aus der Wissensdatenbank. "
            "Erkläre Eigenschaften (Temperatur, Chemikalien, Verschleiß) kompakt und praxisnah."
        ),
        temperature=0.4,
        max_tokens=400,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "knowledge_material_node",
        },
    )

    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(
        update={
            "knowledge_material": reply_text,
            "rag_context": rag_context,  # Speichere RAG-Kontext
            "response_text": reply_text,
            "response_kind": "knowledge_material",
        }
    )

    return {
        "working_memory": wm,
        "messages": list(state.get("messages") or []),
        "phase": PHASE.FINAL,
        "last_node": "knowledge_material_node",
    }


def knowledge_lifetime_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Wissens-Node für Lebensdauer/Standzeit von Dichtungen.
    
    **Best Practice Nov 2025**: RAG-Augmentation.
    """
    user_text = latest_user_text(state.get("messages"))
    model_name = get_model_tier("mini")
    
    # RAG-Retrieval
    rag_context = search_knowledge_base.invoke({
        "query": user_text or "Lebensdauer Dichtungen Einflussfaktoren",
        "category": "lifetime",
        "k": 3,
        "tenant": state.user_id,
    })
    
    # Augmentierter Prompt
    prompt = f"""Kontext aus Wissensdatenbank:
{rag_context}

Frage: {user_text or 'Erkläre Einflussfaktoren auf Lebensdauer und Standzeit von Dichtungen.'}

Beantworte basierend auf dem Kontext."""
    
    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=(
            "Du bist ein Fachberater für Lebensdauer/Standzeit von Dichtungen. "
            "Nutze die Wissensdatenbank. "
            "Erkläre typische Ausfallmechanismen (z.B. Extrusion, Verschleiß, chemischer Angriff) "
            "und die wichtigsten Einflussgrößen (Medium, Temperatur, Druck, Bewegung, Montage, Oberflächen). "
            "Bleib konkret und praxisnah."
        ),
        temperature=0.4,
        max_tokens=400,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "knowledge_lifetime_node",
        },
    )

    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(
        update={
            "knowledge_lifetime": reply_text,
            "rag_context": rag_context,
            "response_text": reply_text,
            "response_kind": "knowledge_lifetime",
        }
    )

    return {
        "working_memory": wm,
        "messages": list(state.get("messages") or []),
        "phase": PHASE.FINAL,
        "last_node": "knowledge_lifetime_node",
    }


def generic_sealing_qa_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Allgemeine FAQ / Q&A zur Dichtungstechnik.
    
    **Best Practice Nov 2025**: RAG-Augmentation.
    """
    user_text = latest_user_text(state.get("messages"))
    model_name = get_model_tier("mini")
    
    # RAG-Retrieval (ohne category-Filter für breitere Suche)
    rag_context = search_knowledge_base.invoke({
        "query": user_text or "Allgemeine Frage Dichtungstechnik",
        "k": 3,
        "tenant": state.user_id,
    })
    
    # Augmentierter Prompt
    prompt = f"""Kontext aus Wissensdatenbank:
{rag_context}

Frage: {user_text or 'Beantworte eine allgemeine Frage zur Dichtungstechnik klar und praxisnah.'}

Beantworte basierend auf dem Kontext."""
    
    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=(
            "Du bist ein allgemeiner Berater für Dichtungstechnik. "
            "Nutze die Wissensdatenbank. "
            "Antworte klar, strukturiert und möglichst praxisnah (Beispiele aus Pumpen, Zylindern, Getrieben etc.). "
            "Bleib kompakt und vermeide unnötige Wiederholungen."
        ),
        temperature=0.4,
        max_tokens=400,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "generic_sealing_qa_node",
        },
    )

    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(
        update={
            "knowledge_generic": reply_text,
            "rag_context": rag_context,
            "response_text": reply_text,
            "response_kind": "knowledge_generic",
        }
    )

    return {
        "working_memory": wm,
        "messages": list(state.get("messages") or []),
        "phase": PHASE.FINAL,
        "last_node": "generic_sealing_qa_node",
    }


__all__ = [
    "knowledge_router_node",
    "knowledge_material_node",
    "knowledge_lifetime_node",
    "generic_sealing_qa_node",
]
