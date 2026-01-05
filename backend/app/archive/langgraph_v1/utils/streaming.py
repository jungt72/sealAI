from __future__ import annotations

import asyncio
from typing import Any

from langgraph.types import RunnableConfig


async def ainvoke_with_config(llm: Any, payload: Any, config: RunnableConfig | None = None) -> Any:
    """
    Invoke an LLM asynchronously while propagating the LangGraph config when supported.

    Falls back to running the synchronous .invoke implementation in a thread so that
    nodes can stay async without blocking the event loop if the LLM lacks ainvoke().
    """
    if llm is None:
        raise ValueError("No LLM instance provided.")

    ainvoke = getattr(llm, "ainvoke", None)
    if callable(ainvoke):
        if config is not None:
            try:
                return await ainvoke(payload, config=config)
            except TypeError:
                # Some fake/test models do not accept config kwargs.
                return await ainvoke(payload)
        return await ainvoke(payload)

    invoke = getattr(llm, "invoke", None)
    if callable(invoke):
        return await asyncio.to_thread(invoke, payload)

    raise AttributeError("LLM does not provide invoke or ainvoke.")


__all__ = ["ainvoke_with_config"]
