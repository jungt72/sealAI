from __future__ import annotations

import asyncio
import re
import threading
from typing import Any, Dict, Iterable, List, Optional

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.ai import AIMessageChunk

from app.services.chat.ws_commons import send_json_safe, ws_log
from app.services.chat.ws_config import WebSocketConfig
from app.services.langgraph.graph.consult.memory_utils import (
    read_history as stm_read_history,
    write_message as stm_write_message,
    read_history_raw as stm_read_history_raw,
)
from app.services.langgraph.llm_factory import get_llm as make_llm
from app.services.langgraph.prompt_registry import get_agent_prompt
from app.services.langgraph.instrumentation import with_tracing
from app.services.langgraph.redis_lifespan import get_redis_checkpointer


_BOUNDARY_RX = re.compile(r"[ \n\t.,;:!?…\)\]}]")
_GRAPH_BUILD_LOCK = threading.RLock()


def _piece_from_llm_chunk(chunk: Any) -> Optional[str]:
    if isinstance(chunk, AIMessageChunk):
        return chunk.content or ""
    text = getattr(chunk, "content", None)
    if isinstance(text, str) and text:
        return text
    additional = getattr(chunk, "additional_kwargs", None)
    if isinstance(additional, dict):
        for key in ("delta", "content", "text", "token"):
            value = additional.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(chunk, dict):
        for key in ("delta", "content", "text", "token"):
            value = chunk.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _iter_text_from_chunk(chunk: Any) -> Iterable[str]:
    if isinstance(chunk, dict):
        content = chunk.get("content")
        if isinstance(content, str) and content:
            yield content
            return
        delta = chunk.get("delta")
        if isinstance(delta, str) and delta:
            yield delta
            return
    content = getattr(chunk, "content", None)
    if isinstance(content, str) and content:
        yield content
        return
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                yield part
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                yield part["text"]
    additional = getattr(chunk, "additional_kwargs", None)
    if isinstance(additional, dict):
        for key in ("delta", "content", "text", "token"):
            value = additional.get(key)
            if isinstance(value, str) and value:
                yield value


def _micro_chunks(text: str, *, max_chars: int) -> Iterable[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        yield text
        return
    i = 0
    length = len(text)
    while i < length:
        j = min(i + max_chars, length)
        k = j
        if j < length:
            match = _BOUNDARY_RX.search(text, j, min(length, j + 40))
            if match:
                k = match.end()
        yield text[i:k]
        i = k


def _is_relevant_node(event_data: Dict[str, Any], *, config: WebSocketConfig) -> bool:
    if "*" in config.stream_nodes or "all" in config.stream_nodes:
        return True
    metadata = event_data.get("metadata") or {}
    run = event_data.get("run") or {}
    node = str(metadata.get("langgraph_node") or "").lower()
    run_name = str(run.get("name") or metadata.get("run_name") or "").lower()
    return node in config.stream_nodes or run_name in config.stream_nodes


def _extract_texts(obj: Any) -> List[str]:
    collected: List[str] = []
    if isinstance(obj, str) and obj.strip():
        collected.append(obj.strip())
        return collected
    if isinstance(obj, dict):
        for key in ("response", "final_text", "text", "answer"):
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                collected.append(value.strip())
        messages = obj.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, AIMessage):
                    content = getattr(message, "content", "")
                    if isinstance(content, str) and content.strip():
                        collected.append(content.strip())
                elif isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        collected.append(content.strip())
        for key in ("output", "state", "final_state", "result"):
            collected.extend(_extract_texts(obj.get(key)))
    elif isinstance(obj, list):
        for item in obj:
            collected.extend(_extract_texts(item))
    return collected


def _last_ai_text_from_result_like(obj: Dict[str, Any]) -> str:
    texts = _extract_texts(obj)
    return texts[-1].strip() if texts else ""


def _truncate_history_for_prompt(system_text: str, history_msgs: List[Any], max_chars: int) -> List[Any]:
    """Truncate oldest history messages until system+history <= max_chars (char-based)."""
    if max_chars <= 0:
        return history_msgs
    total = len(system_text or "")
    sizes = [len((getattr(m, "content", str(m)) or "")) for m in history_msgs]
    kept: List[Any] = []
    for m, s in zip(reversed(history_msgs), reversed(sizes)):
        if total + s > max_chars:
            break
        kept.insert(0, m)
        total += s
    if kept:
        return kept
    return history_msgs[-1:] if history_msgs else []


def _ensure_graph(app, builder_name: Optional[str], config: WebSocketConfig) -> None:
    desired = (builder_name or config.graph_builder).lower().strip() or "supervisor"
    if (
        getattr(app.state, "graph_name", None) == desired
        and (
            getattr(app.state, "graph_async", None) is not None
            or getattr(app.state, "graph_sync", None) is not None
        )
    ):
        return

    with _GRAPH_BUILD_LOCK:
        if (
            getattr(app.state, "graph_name", None) == desired
            and (
                getattr(app.state, "graph_async", None) is not None
                or getattr(app.state, "graph_sync", None) is not None
            )
        ):
            return

        if desired == "supervisor":
            from app.services.langgraph.graph.supervisor_graph import build_supervisor_graph as build_graph
        elif desired == "mvp":
            try:
                from app.services.langgraph.graph.mvp_graph import build_mvp_graph as build_graph  # type: ignore
            except Exception:
                from app.services.langgraph.graph.consult.build import build_consult_graph as build_graph
        else:
            from app.services.langgraph.graph.consult.build import build_consult_graph as build_graph

        saver = None
        try:
            saver = get_redis_checkpointer(app)
        except RuntimeError as exc:
            raise RuntimeError("Redis checkpointer required for LangGraph websocket") from exc
        except Exception as exc:
            ws_log("redis_checkpointer_fallback", error=str(exc))
            saver = None

        graph = build_graph()
        try:
            compiled = graph.compile(checkpointer=saver) if saver else graph.compile()
        except Exception:
            compiled = graph.compile()

        app.state.graph_async = compiled
        app.state.graph_sync = compiled
        app.state.graph_name = desired


async def _send_typing_stub(ws: WebSocket, thread_id: str) -> None:
    await send_json_safe(ws, {"event": "typing", "thread_id": thread_id})


async def stream_llm_direct(
    ws: WebSocket,
    llm,
    *,
    user_input: str,
    thread_id: str,
    config: WebSocketConfig,
) -> None:
    def cancelled() -> bool:
        flags = getattr(ws.app.state, "ws_cancel_flags", {})
        return bool(flags.get(thread_id))

    raw2 = stm_read_history_raw(thread_id, limit=80)
    summary_text2 = ""
    if raw2 and isinstance(raw2, list) and isinstance(raw2[0], dict) and raw2[0].get("role") == "system":
        summary_text2 = (raw2[0].get("content") or "").strip()

    history = stm_read_history(thread_id, limit=80)
    if cancelled():
        return
    history = [m for m in history if not isinstance(m, SystemMessage)]

    loop = asyncio.get_event_loop()
    buffered: List[str] = []
    accum: List[str] = []
    last_flush = [loop.time()]

    async def flush() -> None:
        if not buffered or cancelled():
            return
        chunk = "".join(buffered)
        buffered.clear()
        last_flush[0] = loop.time()
        accum.append(chunk)
        await send_json_safe(ws, {"event": "token", "delta": chunk, "thread_id": thread_id})

    try:
        sys_text = get_agent_prompt("supervisor", context={"rag_context": str(summary_text2 or "")})
    except Exception:
        sys_text = get_agent_prompt("supervisor")
    system_message = SystemMessage(content=sys_text)
    await _send_typing_stub(ws, thread_id)

    max_prompt_chars = int(getattr(config, "prompt_max_chars", 15000))
    truncated_history = _truncate_history_for_prompt(system_message.content or "", history, max_prompt_chars)
    agen = llm.astream([system_message] + truncated_history + [HumanMessage(content=user_input)])
    try:
        first = await asyncio.wait_for(
            agen.__anext__(), timeout=config.first_token_timeout_ms / 1000.0
        )
    except asyncio.TimeoutError:
        try:
            if not cancelled():
                response = await llm.ainvoke(
                    [system_message] + history + [HumanMessage(content=user_input)]
                )
                text = getattr(response, "content", "") or ""
            else:
                text = ""
        except Exception:
            text = ""
        try:
            await agen.aclose()
        except Exception:
            pass
        if text and not cancelled():
            await send_json_safe(ws, {"event": "token", "delta": text, "thread_id": thread_id})
            try:
                stm_write_message(thread_id=thread_id, role="assistant", content=text)
            except Exception:
                pass
        if config.emit_final_text and not cancelled():
            await send_json_safe(ws, {"event": "final", "text": text, "thread_id": thread_id})
        await send_json_safe(ws, {"event": "done", "thread_id": thread_id})
        return
    except Exception:
        try:
            await agen.aclose()
        except Exception:
            pass
        return

    if cancelled():
        try:
            await agen.aclose()
        except Exception:
            pass
        return

    first_text = _piece_from_llm_chunk(first) or ""
    if first_text and not cancelled():
        for segment in _micro_chunks(first_text, max_chars=config.micro_chunk_chars):
            buffered.append(segment)
            await flush()

    try:
        async for chunk in agen:
            if cancelled():
                break
            for piece in _iter_text_from_chunk(chunk):
                if not piece or cancelled():
                    continue
                for segment in _micro_chunks(piece, max_chars=config.micro_chunk_chars):
                    buffered.append(segment)
                    enough = sum(len(x) for x in buffered) >= config.coalesce_min_chars
                    natural = any("".join(buffered).endswith(e) for e in config.flush_endings)
                    too_old = (loop.time() - last_flush[0]) * 1000.0 >= config.coalesce_max_latency_ms
                    if enough or natural or too_old:
                        await flush()
        await flush()
    finally:
        try:
            await agen.aclose()
        except Exception:
            pass

    if cancelled():
        return

    final_text = ("".join(accum)).strip()
    if final_text:
        try:
            stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
        except Exception:
            pass
    if config.emit_final_text:
        await send_json_safe(ws, {"event": "final", "text": final_text, "thread_id": thread_id})
    await send_json_safe(ws, {"event": "done", "thread_id": thread_id})


async def stream_supervised(
    ws: WebSocket,
    *,
    app,
    user_input: str,
    thread_id: str,
    params_patch: Optional[Dict[str, Any]] = None,
    builder_name: Optional[str] = None,
    config: WebSocketConfig,
    routing_payload: Optional[Dict[str, Any]] = None,
) -> None:
    def cancelled() -> bool:
        flags = getattr(ws.app.state, "ws_cancel_flags", {})
        return bool(flags.get(thread_id))

    if cancelled():
        return

    await _send_typing_stub(ws, thread_id)

    try:
        _ensure_graph(app, builder_name=builder_name, config=config)
    except Exception as exc:
        if config.emit_final_text and not cancelled():
            await send_json_safe(
                ws,
                {
                    "event": "final",
                    "text": "",
                    "thread_id": thread_id,
                    "error": f"graph_build_failed: {exc!r}",
                },
            )
        await send_json_safe(ws, {"event": "done", "thread_id": thread_id})
        return

    graph_async = getattr(app.state, "graph_async", None)
    graph_sync = getattr(app.state, "graph_sync", None)

    ws_log(
        "graph_ready",
        builder=config.graph_builder,
        has_async=bool(graph_async),
        has_sync=bool(graph_sync),
    )

    raw = stm_read_history_raw(thread_id, limit=80)
    summary_text = ""
    if raw and isinstance(raw, list) and isinstance(raw[0], dict) and raw[0].get("role") == "system":
        summary_text = (raw[0].get("content") or "").strip()

    history = stm_read_history(thread_id, limit=80)
    history = [m for m in history if not isinstance(m, SystemMessage)]

    prompt_key = "consult" if ((builder_name or config.graph_builder).strip().lower() == "consult") else "supervisor"
    try:
        system_text = get_agent_prompt(prompt_key, context={"rag_context": str(summary_text or "")})
    except Exception:
        system_text = get_agent_prompt("supervisor", context={"rag_context": str(summary_text or "")})
    system_message = SystemMessage(content=system_text)

    max_prompt_chars = int(getattr(config, "prompt_max_chars", 15000))
    truncated_history = _truncate_history_for_prompt(system_message.content or "", history, max_prompt_chars)

    base_messages: List[Any] = [system_message] + truncated_history
    if user_input:
        base_messages.append(HumanMessage(content=user_input))

    initial: Dict[str, Any] = {
        "messages": base_messages,
        "chat_id": thread_id,
        "input": user_input,
    }

    try:
        payload = ws.scope.get("user") or {}
        user_id = str(payload.get("sub") or payload.get("email") or thread_id)
        initial["user_id"] = user_id
    except Exception:
        user_id = thread_id

    if isinstance(params_patch, dict) and params_patch:
        initial["params"] = params_patch

    if isinstance(routing_payload, dict):
        for key in ("intent_seed", "source", "confidence"):
            value = routing_payload.get(key)
            if value is not None and value != "":
                initial[key] = value

    cfg = with_tracing(
        {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": getattr(app.state, "checkpoint_ns", None),
            }
        },
        run_name=(builder_name or config.graph_builder or "supervisor").lower(),
    )
    try:
        cfg["configurable"]["user_id"] = user_id  # type: ignore[index]
    except Exception:
        pass

    loop = asyncio.get_event_loop()
    buffered: List[str] = []
    last_flush = [loop.time()]
    streamed_any = False
    final_tail: str = ""
    accum: List[str] = []

    async def flush() -> None:
        nonlocal streamed_any
        if not buffered or cancelled():
            return
        chunk = "".join(buffered)
        buffered.clear()
        last_flush[0] = loop.time()
        streamed_any = True
        accum.append(chunk)
        if not await send_json_safe(ws, {"event": "token", "delta": chunk, "thread_id": thread_id}):
            raise WebSocketDisconnect()

    def emit_ui_event_if_any(ev_data: Any) -> bool:
        if not isinstance(ev_data, dict):
            return False
        ui_event = ev_data.get("ui_event")
        if isinstance(ui_event, dict):
            payload = {**ui_event, "event": "ui_action", "thread_id": thread_id}
            ws_log("emit_ui_event", payload=payload)
            return asyncio.create_task(send_json_safe(ws, payload)) is not None
        for key in ("output", "state", "final_state", "result"):
            sub = ev_data.get(key)
            if isinstance(sub, dict) and isinstance(sub.get("ui_event"), dict):
                nested = {**sub["ui_event"], "event": "ui_action", "thread_id": thread_id}
                ws_log("emit_ui_event_nested", payload=nested)
                return asyncio.create_task(send_json_safe(ws, nested)) is not None
        return False

    def maybe_emit_ask_missing_fallback(ev_data: Any) -> bool:
        try:
            metadata = (ev_data or {}).get("metadata") or {}
            node = str(metadata.get("langgraph_node") or metadata.get("node") or "").lower()
        except Exception:
            node = ""
        output = (ev_data or {}).get("output") or ev_data or {}
        phase = str(output.get("phase") or "").lower()
        if node == "ask_missing" or phase == "ask_missing":
            payload = {
                "event": "ui_action",
                "ui_action": "open_form",
                "thread_id": thread_id,
                "source": "ws_fallback",
            }
            ws_log("emit_ui_event_fallback", node=node, phase=phase, payload=payload)
            asyncio.create_task(send_json_safe(ws, payload))
            return True
        return False

    def try_stream_text_from_node(data: Any) -> None:
        texts = _extract_texts(data)
        if not texts:
            return
        joined = "\n".join([t for t in texts if isinstance(t, str)])
        if not joined:
            return
        for segment in _micro_chunks(joined, max_chars=config.micro_chunk_chars):
            buffered.append(segment)

    async def run_stream(version: str) -> None:
        nonlocal final_tail
        if graph_async is None:
            return
        async for event in graph_async.astream_events(initial, config=cfg, version=version):  # type: ignore[attr-defined]
            if cancelled():
                break
            event_name = event.get("event")
            data = event.get("data")

            if isinstance(data, dict) and str(data.get("type") or "").lower() == "stream_text":
                text_piece = data.get("text")
                if isinstance(text_piece, str) and text_piece:
                    for segment in _micro_chunks(text_piece, max_chars=config.micro_chunk_chars):
                        buffered.append(segment)
                        enough = sum(len(x) for x in buffered) >= config.coalesce_min_chars
                        natural = any("".join(buffered).endswith(e) for e in config.flush_endings)
                        too_old = (loop.time() - last_flush[0]) * 1000.0 >= config.coalesce_max_latency_ms
                        if enough or natural or too_old:
                            await flush()
                    await flush()
                continue

            if event_name in ("on_chat_model_stream", "on_llm_stream") and _is_relevant_node(event, config=config):
                chunk = data.get("chunk") if isinstance(data, dict) else None
                if chunk:
                    for piece in _iter_text_from_chunk(chunk):
                        if not piece or cancelled():
                            continue
                        for segment in _micro_chunks(piece, max_chars=config.micro_chunk_chars):
                            buffered.append(segment)
                            enough = sum(len(x) for x in buffered) >= config.coalesce_min_chars
                            natural = any("".join(buffered).endswith(e) for e in config.flush_endings)
                            too_old = (loop.time() - last_flush[0]) * 1000.0 >= config.coalesce_max_latency_ms
                            if enough or natural or too_old:
                                await flush()

            if event_name in ("on_node_end",):
                if isinstance(data, dict):
                    try_stream_text_from_node(data.get("output") or data)
                await flush()
                emitted = emit_ui_event_if_any(data)
                if not emitted:
                    maybe_emit_ask_missing_fallback(data)

            if event_name in ("on_chain_end", "on_graph_end"):
                if isinstance(data, dict):
                    emit_ui_event_if_any(data)
                    final_tail = _last_ai_text_from_result_like(data) or final_tail

        await flush()

    timed_out = False
    if config.force_sync_fallback:
        timed_out = True
    elif graph_async is not None and not cancelled():
        try:
            await asyncio.wait_for(run_stream("v2"), timeout=config.event_timeout_sec)
        except asyncio.TimeoutError:
            timed_out = True
        except Exception:
            try:
                await asyncio.wait_for(run_stream("v1"), timeout=config.event_timeout_sec)
            except asyncio.TimeoutError:
                timed_out = True
            except Exception:
                pass

    if cancelled():
        return

    assistant_text = ""
    if final_tail:
        if not streamed_any:
            accum.append(final_tail)
        assistant_text = final_tail
    elif (not streamed_any) or timed_out:
        try:
            result: Any = None
            if graph_sync is not None:
                def run_sync() -> Any:
                    return graph_sync.invoke(initial, config=cfg)

                result = await asyncio.get_event_loop().run_in_executor(None, run_sync)
            elif graph_async is not None:
                result = await graph_async.ainvoke(initial, config=cfg)  # type: ignore[attr-defined]

            if isinstance(result, dict):
                emitted = emit_ui_event_if_any(result)
                if not emitted:
                    maybe_emit_ask_missing_fallback(result)

            final_text = _last_ai_text_from_result_like(result or {}) or ""
            assistant_text = final_text
            if final_text:
                accum.append(final_text)
        except Exception:
            assistant_text = ""
        if not assistant_text:
            try:
                llm = getattr(app.state, "llm", make_llm(streaming=False))
                response = await llm.ainvoke(
                    [system_message] + history + [HumanMessage(content=user_input)]
                )
                assistant_text = (getattr(response, "content", "") or "").strip()
            except Exception:
                assistant_text = ""
    else:
        assistant_text = "".join(accum)

    if cancelled():
        return

    final_text = (assistant_text or "".join(accum)).strip()
    already = "".join(accum).strip()
    should_emit_final_token = bool(final_text) and (
        not streamed_any or not already or already != final_text
    )
    if should_emit_final_token:
        # Ensure the fallback path (sync invoke or timeout recovery) still yields
        # at least one text chunk even when no streaming tokens were flushed.
        streamed_any = True
        if not await send_json_safe(ws, {"event": "token", "delta": final_text, "thread_id": thread_id}):
            return

    try:
        if final_text:
            stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
    except Exception:
        pass

    if config.emit_final_text:
        await send_json_safe(ws, {"event": "final", "text": final_text, "thread_id": thread_id})
    await send_json_safe(ws, {"event": "done", "thread_id": thread_id})


__all__ = ["stream_llm_direct", "stream_supervised"]
