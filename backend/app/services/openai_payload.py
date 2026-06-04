# backend/app/services/openai_payload.py
from __future__ import annotations
from typing import Dict, List, Tuple, Any


def use_responses_api(model: str) -> bool:
    m = (model or "").lower().strip()
    # GPT-5 / o4 / o3 nutzen die Responses API
    return m.startswith("gpt-5") or m.startswith("o4") or m.startswith("o3")


def _to_input_parts(
    content: Any, part_type: str = "input_text"
) -> List[Dict[str, Any]]:
    """
    Responses-API erwartet strukturierte Parts.
    Strings -> [{"type": part_type, "text": "..."}]
    Bereits strukturierte Parts werden durchgereicht.

    ``part_type`` muss rollenabhaengig gesetzt werden: Assistant-Content
    "output_text", User/System "input_text". Ein Assistant-Turn mit
    "input_text" loest OpenAI 400 invalid_value aus.
    """
    parts: List[Dict[str, Any]] = []
    if content is None:
        return parts
    if isinstance(content, str):
        return [{"type": part_type, "text": content}]
    if isinstance(content, list):
        for c in content:
            if isinstance(c, str):
                parts.append({"type": part_type, "text": c})
            elif isinstance(c, dict):
                if "type" in c:
                    parts.append(c)
                elif "text" in c:
                    parts.append({"type": part_type, "text": str(c["text"])})
                else:
                    parts.append({"type": part_type, "text": str(c)})
        return parts or [{"type": part_type, "text": str(content)}]
    if isinstance(content, dict):
        if "type" in content:
            return [content]
        if "text" in content:
            return [{"type": part_type, "text": str(content["text"])}]
        return [{"type": part_type, "text": str(content)}]
    return [{"type": part_type, "text": str(content)}]


def messages_to_responses_input(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Chat-Message-Format -> Responses-API 'input'
    [{"role":"system","content":[{"type":"input_text","text":"..."}]}, ...]
    """
    out: List[Dict[str, Any]] = []
    for m in messages or []:
        role = (m.get("role") or m.get("type") or "user").strip()
        content = m.get("content")
        part_type = "output_text" if role == "assistant" else "input_text"
        parts = _to_input_parts(content, part_type)
        if parts:
            out.append({"role": role, "content": parts})
    return out


def _responses_sampling_supported(model: str) -> bool:
    """
    Einige Responses-Modelle (z. B. gpt-5-mini) akzeptieren KEIN 'temperature'/'top_p'.
    Um 400er zu vermeiden, standardmäßig False.
    Stelle hier ggf. eine Whitelist her, falls du Modelle hast, die Sampling erlauben.
    """
    return False  # konservativ: keine Sampling-Parameter senden


def build_openai_payload(
    model: str,
    messages: List[Dict[str, Any]],
    max_new_tokens: int,
    temperature: float = 0.2,
    top_p: float = 1.0,
    stream: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """
    Liefert (endpoint, payload_json) passend zum Modell.
      - Responses API (gpt-5*/o4*/o3*):   /v1/responses + max_output_tokens
        -> ohne 'temperature'/'top_p' (verhindert 400 bei gpt-5-mini)
      - Chat Completions (rest):          /v1/chat/completions + max_tokens
    """
    if use_responses_api(model):
        endpoint = "/v1/responses"
        payload: Dict[str, Any] = {
            "model": model,
            "input": messages_to_responses_input(messages),
            "stream": stream,
            "max_output_tokens": max_new_tokens,
        }
        # Nur senden, wenn explizit erlaubt (derzeit bewusst aus)
        if _responses_sampling_supported(model):
            payload["temperature"] = temperature
            payload["top_p"] = top_p
    else:
        endpoint = "/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
            "max_tokens": max_new_tokens,
        }
    return endpoint, payload
