from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import RunnableConfig

from app.langgraph.state import SealAIState, WarmupState
from app.langgraph.types import interrupt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Starte das Gespräch freundlich und locker. Wenn fachlicher Kontext offensichtlich ist, "
    "leite sanft über zur Bedarfsanalyse. Andernfalls bleib allgemein und frage ggf. freundlich "
    "nach dem Ziel des Gesprächs."
)


def _use_offline_mode() -> bool:
    forced = os.getenv("LANGGRAPH_USE_FAKE_LLM", "")
    if forced.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return not api_key or api_key.lower() in {"dummy", "test"}


def _flatten_history(messages: List[BaseMessage]) -> str:
    lines: List[str] = []
    for msg in messages:
        role = getattr(msg, "type", getattr(msg, "role", "unknown"))
        content = getattr(msg, "content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def _find_last_user_message(messages: List[BaseMessage]) -> Optional[HumanMessage]:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg
    return None


def _first_non_empty(*candidates: Optional[str]) -> str:
    for candidate in candidates:
        if candidate:
            stripped = candidate.strip()
            if stripped:
                return stripped
    return ""


def _extract_user_name(slots: Dict[str, Any], fallback: str) -> str:
    profile = slots.get("user_profile")
    if isinstance(profile, dict):
        for key in ("name", "full_name", "first_name", "display_name"):
            value = profile.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("contact_name", "user_name"):
        value = slots.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _extract_company(slots: Dict[str, Any]) -> str:
    org = slots.get("company") or slots.get("account")
    if isinstance(org, dict):
        for key in ("name", "company", "organization"):
            value = org.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(org, str) and org.strip():
        return org.strip()
    candidate = slots.get("customer_industry") or slots.get("segment")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return ""


def _normalize_summary(data: Dict[str, Any]) -> WarmupState:
    rapport = _first_non_empty(str(data.get("warmup") or ""), "Kurz notiert.")
    context_hint = str(data.get("context_hint") or "").strip()
    summary = cast(
        WarmupState,
        {
            "rapport": rapport,
            "user_mood": "aufgeschlossen",
            "ready_for_analysis": not context_hint,
        },
    )
    return summary


def _offline_payload(user_name: str) -> Dict[str, Any]:
    message = (
        f"Hallo {user_name or 'da'}! Schön, dass du da bist. "
        "Womit beschäftigst du dich gerade, und wo können wir dich unterstützen?"
    )
    return {
        "message": message,
        "slots": {"warmup": "Willkommen geheißen, Gespräch eröffnet."},
        "meta": {"warmup": True},
    }


def _get_llm(_config: RunnableConfig):
    model_name = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    return ChatOpenAI(
        model=model_name,
        temperature=0.2,
        streaming=False,
    )


def _coerce_content(result: Any) -> str:
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content
    return str(result)


def _parse_payload(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        logger.debug("warmup_agent: JSON parsing failed for %s", raw, exc_info=True)
    return {}


def _build_human_prompt(user_name: str, company: str, history: str, latest_text: str) -> str:
    lines = [
        f"Name: {user_name}",
    ]
    if company:
        lines.append(f"Unternehmen/Branche: {company}")
    if latest_text:
        lines.append(f"Letzte Nachricht: {latest_text}")
    if history:
        lines.append("Gesamter Verlauf:")
        lines.append(history)
    return "\n".join(lines)


def warmup_agent_node(
    state: SealAIState,
    *,
    config: RunnableConfig,
) -> Dict[str, Any]:
    messages: List[BaseMessage] = list(state.get("messages") or [])
    if not messages:
        logger.info("warmup_agent: keine Nachrichten im State, breche ab.")
        return {}

    slots = dict(state.get("slots") or {})
    meta = dict(state.get("meta") or {})
    user_id = str(meta.get("user_id") or slots.get("user_id") or "Partner")

    user_name = _extract_user_name(slots, fallback=user_id)
    company = _extract_company(slots)
    history = _flatten_history(messages)
    last_user_msg = _find_last_user_message(messages)
    latest_text = last_user_msg.content if last_user_msg else ""

    configurable = (config.get("configurable") or {}) if isinstance(config, dict) else {}
    override_llm = configurable.get("warmup_llm")
    use_offline = False
    selected_llm = None
    if override_llm and hasattr(override_llm, "invoke"):
        selected_llm = override_llm
    else:
        use_offline = _use_offline_mode()
        if not use_offline:
            selected_llm = _get_llm(config)

    if use_offline and selected_llm is None:
        payload = _offline_payload(user_name)
    else:
        prompt = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_human_prompt(user_name, company, history, latest_text)),
        ]
        llm = selected_llm or _get_llm(config)
        try:
            llm_out = llm.invoke(prompt)
            raw_text = _coerce_content(llm_out)
            payload = _parse_payload(raw_text)
        except Exception:  # noqa: BLE001
            logger.exception("warmup_agent: LLM inference failed, fallback payload.", exc_info=True)
            payload = _offline_payload(user_name)

    message_text = str(payload.get("message") or "").strip()
    if not message_text:
        payload = _offline_payload(user_name)
        message_text = payload["message"]

    slots_payload = payload.get("slots")
    if not isinstance(slots_payload, dict):
        slots_payload = {}
    meta_payload = payload.get("meta")
    if not isinstance(meta_payload, dict):
        meta_payload = {}
    summary = _normalize_summary(slots_payload)

    ai_message = AIMessage(content=message_text, additional_kwargs={"phase": "warmup", "label": "Einstiegsgespräch"})
    messages.append(ai_message)

    slots["warmup"] = slots_payload.get("warmup", summary.get("rapport"))
    slots["context_hint"] = slots_payload.get("context_hint")

    warmup_meta = meta.get("warmup") or {}
    warmup_meta.update(meta_payload)
    meta["warmup"] = warmup_meta

    updates: Dict[str, Any] = {
        "messages": messages,
        "slots": slots,
        "warmup": summary,
        "phase": "warmup",
        "meta": meta,
        "message_out": message_text,
        "msg_type": "msg-warmup",
    }

    fallback_reason = str(meta_payload.get("fallback_reason") or "").strip()
    if fallback_reason:
        state["message_out"] = message_text
        state["msg_type"] = "msg-warmup"
        interrupt({"prompt": message_text, "reason": fallback_reason})

    return updates
