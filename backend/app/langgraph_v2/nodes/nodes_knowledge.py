"""Wissens-Nodes für LangGraph v2."""

from __future__ import annotations
import logging
import os
from typing import Dict, Any, List, Tuple

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, WorkingMemory, Source
from app.langgraph_v2.utils.llm_factory import run_llm, get_model_tier
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.jinja_renderer import render_template
from app.langgraph_v2.utils.rag import unpack_rag_payload, apply_rag_quality_gate
from app.langgraph_v2.utils.rag_safety import wrap_rag_context
from app.langgraph_v2.utils.rag_tool import search_knowledge_base

logger = logging.getLogger(__name__)


def _process_knowledge_sources(retrieval_meta: Dict[str, Any] | None, existing_sources: List[Source] = None) -> Tuple[bool, str, List[Source]]:
    """
    Extrahiert Quellen aus retrieval_meta und bestimmt needs_sources/sources_status.
    F??hrt Deduplizierung basierend auf der 'source' ID durch.
    """
    sources = list(existing_sources or [])
    if not retrieval_meta or retrieval_meta.get("skipped"):
        return bool(sources), "ok" if sources else "missing", sources
    
    # RAG Orchestrator might return sources directly or under metrics
    raw_sources = retrieval_meta.get("sources") or retrieval_meta.get("metrics", {}).get("sources", [])
    
    if not raw_sources and not sources:
        return False, "missing", []
    
    known_ids = {s.source for s in sources if s.source}
    
    added_new = False
    for s in raw_sources:
        src_id = s.get("source") or s.get("url")
        if src_id and src_id not in known_ids:
            sources.append(Source(
                source=src_id,
                snippet=s.get("snippet") or s.get("text"),
                metadata=s.get("metadata") or s
            ))
            known_ids.add(src_id)
            added_new = True
    
    status = "ok" if sources else "missing"
    return bool(sources), status, sources


def knowledge_router_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Entscheidet, welche Wissens-Kategorie relevant ist:
    - knowledge_material (Werkstoffe)
    - knowledge_lifetime (Lebensdauer)
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
    can_read_private = bool(getattr(state, "can_read_private", False) or getattr(state, "is_privileged", False))
    rag_context = search_knowledge_base.invoke({
        "query": user_text,
        "category": "materials",
        "k": 3,
        "tenant": state.tenant_id,
        "can_read_private": can_read_private,
    })
    rag_text, retrieval_meta = unpack_rag_payload(rag_context)
    rag_text, retrieval_meta = apply_rag_quality_gate(
        rag_text,
        retrieval_meta,
        min_top_score=float(os.getenv("MIN_TOP_SCORE", "0.20")),
    )
    rag_text = wrap_rag_context(rag_text)
    
    # Quellen-Extraktion für UI
    needs_src, src_status, sources = _process_knowledge_sources(retrieval_meta, existing_sources=state.sources)
    
    # Template Rendering via Helper
    try:
        prompt = render_template(
            "knowledge_generic_qa.j2",
            context=rag_text,
            question=user_text or 'Beantworte eine allgemeine Frage zur Dichtungstechnik.'
        )
        sys_msg = "Du bist SealAI, ein Assistent für Dichtungstechnik."
    except Exception as e:
        print(f"Template rendering failed: {e}")
        prompt = f"""Kontext: {rag_text}\n\nFrage: {user_text}\n"""
        sys_msg = "Du bist ein Fachberater für Dichtungswerkstoffe."

    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=sys_msg,
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
            "knowledge_material": reply_text,
            "rag_context": rag_text,  # Speichere RAG-Kontext
            "response_text": reply_text,
            "response_kind": "knowledge_material",
        }
    )

    return {
        "working_memory": wm,
        "messages": list(state.get("messages") or []),
        "retrieval_meta": retrieval_meta,
        "phase": PHASE.FINAL,
        "last_node": "knowledge_material_node",
        "needs_sources": needs_src,
        "sources_status": src_status,
        "sources": sources,
    }


def knowledge_lifetime_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Wissens-Node für Lebensdauer/Standzeit von Dichtungen.
    
    **Best Practice Nov 2025**: RAG-Augmentation.
    """
    user_text = latest_user_text(state.get("messages"))
    model_name = get_model_tier("mini")
    
    # RAG-Retrieval
    can_read_private = bool(getattr(state, "can_read_private", False) or getattr(state, "is_privileged", False))
    rag_context = search_knowledge_base.invoke({
        "query": user_text or "Lebensdauer Dichtungen Einflussfaktoren",
        "category": "lifetime",
        "k": 3,
        "tenant": state.tenant_id,
        "can_read_private": can_read_private,
    })
    rag_text, retrieval_meta = unpack_rag_payload(rag_context)
    rag_text, retrieval_meta = apply_rag_quality_gate(
        rag_text,
        retrieval_meta,
        min_top_score=float(os.getenv("MIN_TOP_SCORE", "0.20")),
    )
    rag_text = wrap_rag_context(rag_text)
    
    # Quellen-Extraktion für UI
    needs_src, src_status, sources = _process_knowledge_sources(retrieval_meta, existing_sources=state.sources)
    
    # Augmentierter Prompt
    prompt = f"""Kontext aus Wissensdatenbank:
{rag_text}

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
            "rag_context": rag_text,
            "response_text": reply_text,
            "response_kind": "knowledge_lifetime",
        }
    )

    return {
        "working_memory": wm,
        "messages": list(state.get("messages") or []),
        "retrieval_meta": retrieval_meta,
        "phase": PHASE.FINAL,
        "last_node": "knowledge_lifetime_node",
        "needs_sources": needs_src,
        "sources_status": src_status,
        "sources": sources,
    }


def generic_sealing_qa_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Allgemeine FAQ / Q&A zur Dichtungstechnik.
    
    **Best Practice Nov 2025**: RAG-Augmentation.
    """
    user_text = latest_user_text(state.get("messages"))
    model_name = get_model_tier("mini")
    
    # RAG-Retrieval (ohne category-Filter für breitere Suche)
    can_read_private = bool(getattr(state, "can_read_private", False) or getattr(state, "is_privileged", False))
    rag_context = search_knowledge_base.invoke({
        "query": user_text or "Allgemeine Frage Dichtungstechnik",
        "k": 3,
        "tenant": state.tenant_id,
        "can_read_private": can_read_private,
    })
    rag_text, retrieval_meta = unpack_rag_payload(rag_context)
    rag_text, retrieval_meta = apply_rag_quality_gate(
        rag_text,
        retrieval_meta,
        min_top_score=float(os.getenv("MIN_TOP_SCORE", "0.20")),
    )
    rag_text = wrap_rag_context(rag_text)
    
    # Quellen-Extraktion für UI
    needs_src, src_status, sources = _process_knowledge_sources(retrieval_meta, existing_sources=state.sources)
    
    # Augmentierter Prompt
    prompt = f"""Kontext aus Wissensdatenbank:
{rag_text}

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
            "rag_context": rag_text,  # Speichere RAG-Kontext
            "response_text": reply_text,
            "response_kind": "knowledge_generic",
        }
    )

    msg_content = f"Knowledge retrieved. Summary: {reply_text[:200]}..."
    logger.info("generic_sealing_qa_node: %s", msg_content)

    return {
        "working_memory": wm,
        "retrieval_meta": retrieval_meta,
        "phase": PHASE.FINAL,
        "last_node": "generic_sealing_qa_node",
        "needs_sources": needs_src,
        "sources_status": src_status,
        "sources": sources,
    }


__all__ = [
    "knowledge_router_node",
    "knowledge_material_node",
    "knowledge_lifetime_node",
    "generic_sealing_qa_node",
]
