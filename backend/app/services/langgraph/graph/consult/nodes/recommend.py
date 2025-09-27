# backend/app/services/langgraph/graph/consult/nodes/recommend.py
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

import structlog
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig

from app.services.langgraph.prompting import (
    render_template,
    messages_for_template,
    strip_json_fence,
)
from app.services.langgraph.prompt_registry import get_agent_prompt
from ..utils import normalize_messages, last_user_text
from ..config import create_llm

log = structlog.get_logger(__name__)

_STREAM_CHUNK_CHARS = 160

def _extract_text_from_chunk(chunk) -> List[str]:
    out: List[str] = []
    if not chunk:
        return out
    c = getattr(chunk, "content", None)
    if isinstance(c, str) and c:
        out.append(c)
    elif isinstance(c, list):
        for part in c:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                out.append(part["text"])
    ak = getattr(chunk, "additional_kwargs", None)
    if isinstance(ak, dict):
        for k in ("delta", "content", "text", "token"):
            v = ak.get(k)
            if isinstance(v, str) and v:
                out.append(v)
    if isinstance(chunk, dict):
        for k in ("delta", "content", "text", "token"):
            v = chunk.get(k)
            if isinstance(v, str) and v:
                out.append(v)
    return out

def _extract_json_any(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if (s[:1] in "{[") and (s[-1:] in "}]"):
        return s
    s2 = strip_json_fence(s)
    if (s2[:1] in "{[") and (s2[-1:] in "}]"):
        return s2
    m = re.search(r"\{(?:[^{}]|(?R))*\}", s, re.S)
    if m:
        return m.group(0)
    m = re.search(r"\[(?:[^\[\]]|(?R))*\]", s, re.S)
    return m.group(0) if m else ""

def _parse_empfehlungen(raw: str) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    try:
        data = json.loads(strip_json_fence(raw))
        if isinstance(data, dict) and isinstance(data.get("empfehlungen"), list):
            return data["empfehlungen"]
    except Exception as e:
        log.warning("[recommend_node] json_parse_error", err=str(e))
    return None

_RX = {
    "typ": re.compile(r"(?im)^\s*Typ:\s*(.+?)\s*$"),
    "werkstoff": re.compile(r"(?im)^\s*Werkstoff:\s*(.+?)\s*$"),
    "vorteile": re.compile(
        r"(?is)\bVorteile:\s*(.+?)(?:\n\s*(?:Einschr[aä]nkungen|Begr[üu]ndung|Abgeleiteter|Alternativen)\b|$)"
    ),
    "einschraenkungen": re.compile(
        r"(?is)\bEinschr[aä]nkungen:\s*(.+?)(?:\n\s*(?:Begr[üu]ndung|Abgeleiteter|Alternativen)\b|$)"
    ),
    "begruendung": re.compile(
        r"(?is)\bBegr[üu]ndung:\s*(.+?)(?:\n\s*(?:Abgeleiteter|Alternativen)\b|$)"
    ),
}

def _split_items(s: str) -> List[str]:
    if not s:
        return []
    s = re.sub(r"[•\-\u2013\u2014]\s*", ", ", s)
    parts = re.split(r"[;,]\s*|\s{2,}", s.strip())
    return [p.strip(" .") for p in parts if p and not p.isspace()]

def _coerce_from_markdown(text: str) -> Optional[List[Dict[str, Any]]]:
    if not text:
        return None
    def _m(rx):
        m = rx.search(text)
        return (m.group(1).strip() if m else "")
    typ = _m(_RX["typ"])
    werkstoff = _m(_RX["werkstoff"])
    vorteile = _split_items(_m(_RX["vorteile"]))

    einschr = _split_items(_m(_RX["einschraenkungen"]))
    begr = _m(_RX["begruendung"])
    if not (typ or werkstoff or begr or vorteile or einschr):
        return None
    return [{
        "typ": typ or "",
        "werkstoff": werkstoff or "",
        "begruendung": begr or "",
        "vorteile": vorteile or [],
        "einschraenkungen": einschr or [],
        "geeignet_fuer": [],
    }]

def _context_from_docs(docs: List[Dict[str, Any]], max_chars: int = 1200) -> str:
    if not docs:
        return ""
    parts: List[str] = []
    for d in docs[:6]:
        t = (d.get("text") or "").strip()
        if not t:
            continue
        src = d.get("source") or (d.get("metadata") or {}).get("source")
        if src:
            t = f"{t}\n[source: {src}]"
        parts.append(t)
    ctx = "\n\n".join(parts)
    return ctx[:max_chars]

def _emit_stream_chunks(events: Optional[Callable[[Dict[str, Any]], None]], *, node: str, text: str) -> None:
    if not events or not text:
        return
    try:
        for i in range(0, len(text), _STREAM_CHUNK_CHARS):
            chunk = text[i : i + _STREAM_CHUNK_CHARS]
            if chunk:
                events({"type": "stream_text", "node": node, "text": chunk})
    except Exception as exc:
        log.debug("[recommend_node] stream_emit_failed", err=str(exc))


def recommend_node(
    state: Dict[str, Any],
    config: Optional[RunnableConfig] = None,
    *,
    events: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    # Falls noch Pflichtfelder fehlen, NICHT ins teure RAG/LLM gehen – stattdessen UI-Form öffnen
    missing = state.get("fehlend") or state.get("missing") or []
    if isinstance(missing, (list, tuple)) and len(missing) > 0:
        ui = {
            "ui_event": {
                "ui_action": "open_form",
                "form_id": "rwdr_params_v1",
                "schema_ref": "domains/rwdr/params@1.0.0",
                "missing": list(missing),
                "prefill": (state.get("params") or {})
            }
        }
        return {**state, **ui, "phase": "ask_missing"}

    msgs = normalize_messages(state.get("messages", []))
    params: Dict[str, Any] = state.get("params") or {}
    domain = (state.get("domain") or "").strip().lower()
    derived = state.get("derived") or {}
    retrieved_docs: List[Dict[str, Any]] = state.get("retrieved_docs") or []
    context = state.get("context") or _context_from_docs(retrieved_docs)
    if context:
        log.info("[recommend_node] using_context", n_docs=len(retrieved_docs), ctx_len=len(context))

    base_llm = create_llm(streaming=True)
    try:
        llm = base_llm.bind(response_format={"type": "json_object"})
    except Exception:
        llm = base_llm

    recent_user = (last_user_text(msgs) or "").strip()
    prompt = render_template(
        "recommend.jinja2",
        messages=messages_for_template(msgs),
        params=params,
        domain=domain,
        derived=derived,
        recent_user=recent_user,
        context=context,
    )

    effective_cfg: RunnableConfig = (config or {}).copy()  # type: ignore[assignment]
    if "run_name" not in (effective_cfg or {}):
        effective_cfg = {**effective_cfg, "run_name": "recommend"}  # type: ignore[dict-item]

    content_parts: List[str] = []
    try:
        for chunk in llm.with_config(effective_cfg).stream([
            SystemMessage(content=get_agent_prompt(domain or "rwdr")),
            SystemMessage(content=prompt),
        ]):
            texts = _extract_text_from_chunk(chunk)
            for piece in texts:
                _emit_stream_chunks(events, node="recommend", text=piece)
            content_parts.extend(texts)
    except Exception as e:
        log.warning("[recommend_node] stream_failed", err=str(e))
        try:
            resp = llm.invoke([
                SystemMessage(content=get_agent_prompt(domain or "rwdr")),
                SystemMessage(content=prompt),
            ], config=effective_cfg)
            final_text = getattr(resp, "content", "") or ""
            if final_text:
                _emit_stream_chunks(events, node="recommend", text=final_text)
            content_parts = [final_text]
        except Exception as e2:
            log.error("[recommend_node] invoke_failed", err=str(e2))
            payload = json.dumps({"empfehlungen": []}, ensure_ascii=False, separators=(",", ":"))
            _emit_stream_chunks(events, node="recommend", text=payload)
            ai_msg = AIMessage(content=payload)
            return {
                **state,
                "messages": msgs + [ai_msg],
                "answer": payload,
                "phase": "recommend",
                "empfehlungen": [],
                "retrieved_docs": retrieved_docs,
                "docs": retrieved_docs,
                "context": context,
            }

    raw = ("".join(content_parts) or "").strip()
    log.info("[recommend_node] stream_len", chars=len(raw))

    json_snippet = _extract_json_any(raw)
    recs = _parse_empfehlungen(json_snippet) or _parse_empfehlungen(raw)
    if not recs:
        recs = _coerce_from_markdown(raw)
    if not recs:
        recs = [{
            "typ": "",
            "werkstoff": "",
            "begruendung": (raw[:600] if raw else "Keine strukturierte Empfehlung erhalten."),
            "vorteile": [],
            "einschraenkungen": [],
            "geeignet_fuer": [],
        }]

    content_out = json.dumps({"empfehlungen": recs}, ensure_ascii=False, separators=(",", ":")).replace("\n", " ").strip()

    ai_msg = AIMessage(content=content_out)
    return {
        **state,
        "messages": msgs + [ai_msg],
        "answer": content_out,
        "phase": "recommend",
        "empfehlungen": recs,
        "retrieved_docs": retrieved_docs,
        "docs": retrieved_docs,
        "context": context,
    }
