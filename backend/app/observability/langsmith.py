"""LangSmith helpers for SeaLAI runtime observability.

This module is intentionally defensive: local tests and developer machines can
run without langsmith installed or configured, while production gets OpenAI SDK
and custom span tracing once the LangSmith environment is enabled.
"""

from __future__ import annotations

import logging
import os
import inspect
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any, Iterator, ParamSpec, TypeVar

from app.observability.sealai_quality import (
    identity_trace_metadata,
    redact_trace_value,
    sanitize_trace_inputs,
    sanitize_trace_outputs,
)

log = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_WRAP_UNAVAILABLE_LOGGED = False


def _truthy(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUE_VALUES


def langsmith_api_key() -> str | None:
    """Return the configured LangSmith key without exposing it."""

    return (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY") or "").strip() or None


def langsmith_project(default: str = "sealai-production") -> str:
    """Return the active LangSmith project name."""

    return (
        os.getenv("LANGSMITH_PROJECT")
        or os.getenv("LANGCHAIN_PROJECT")
        or default
    ).strip()


def langsmith_tracing_requested(default: bool = False) -> bool:
    """Return whether tracing was requested via modern or legacy env names."""

    if "LANGSMITH_TRACING" in os.environ:
        return _truthy(os.getenv("LANGSMITH_TRACING"))
    if "LANGCHAIN_TRACING_V2" in os.environ:
        return _truthy(os.getenv("LANGCHAIN_TRACING_V2"))
    return default


def langsmith_enabled(default: bool = False) -> bool:
    """Return whether LangSmith can actually emit traces."""

    return bool(langsmith_api_key()) and langsmith_tracing_requested(default=default)


def langsmith_capture_llm_content(default: bool = False) -> bool:
    """Return whether raw LLM SDK inputs/outputs may be captured.

    Production defaults to false because SDK wrappers can include prompts, user
    messages, retrieved evidence, and completions. Enable only behind a
    redaction gateway or in controlled non-customer runs.
    """

    if "LANGSMITH_CAPTURE_LLM_CONTENT" in os.environ:
        return _truthy(os.getenv("LANGSMITH_CAPTURE_LLM_CONTENT"))
    return default


def langsmith_trace_langgraph_children(default: bool = False) -> bool:
    """Return whether raw LangGraph child spans may be emitted.

    LangGraph's automatic tracing is invaluable during development, but its
    state snapshots can include user wording, extracted fields, evidence, and
    interrupt payloads. Production keeps SealAI's own redacted wrapper spans and
    disables these deep child spans unless explicitly enabled.
    """

    if "LANGSMITH_TRACE_LANGGRAPH_CHILDREN" in os.environ:
        return _truthy(os.getenv("LANGSMITH_TRACE_LANGGRAPH_CHILDREN"))
    return default


@contextmanager
def langsmith_tracing_disabled(*, disabled: bool = True) -> Iterator[None]:
    """Temporarily disable automatic LangSmith tracing for a sensitive block."""

    if not disabled:
        yield
        return
    try:
        import langsmith as ls  # type: ignore
    except Exception:  # noqa: BLE001
        yield
        return
    tracing_context = getattr(ls, "tracing_context", None)
    if not callable(tracing_context):
        yield
        return
    try:
        context = tracing_context(enabled=False)
        context.__enter__()
    except Exception as exc:  # noqa: BLE001
        log.warning("LangSmith tracing_context unavailable; continuing without suppression: %s", exc)
        yield
        return
    try:
        yield
    except BaseException as exc:
        try:
            suppress = bool(context.__exit__(type(exc), exc, exc.__traceback__))
        except Exception as cleanup_exc:  # noqa: BLE001
            log.warning(
                "LangSmith tracing_context cleanup failed after runtime exception; preserving original error: %s",
                cleanup_exc,
            )
            suppress = False
        if not suppress:
            raise
    else:
        try:
            context.__exit__(None, None, None)
        except Exception as exc:  # noqa: BLE001
            log.warning("LangSmith tracing_context cleanup failed; continuing: %s", exc)


def configure_langsmith_environment(
    *,
    tracing_enabled: bool,
    api_key: str | None,
    project: str | None,
    endpoint: str | None = None,
) -> bool:
    """Normalize LangSmith/LangChain tracing env vars for all SDKs.

    LangSmith's current docs use LANGSMITH_* names; older LangChain integrations
    still honor LANGCHAIN_* names. We set both so LangGraph, LangChain and direct
    OpenAI wrappers behave consistently.
    """

    if not tracing_enabled:
        return False
    clean_key = (api_key or langsmith_api_key() or "").strip()
    if not clean_key:
        log.info("LangSmith tracing requested but no API key provided; tracing remains disabled.")
        return False

    clean_project = (project or langsmith_project()).strip() or "sealai-production"
    clean_endpoint = (endpoint or os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT") or "").strip()

    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_API_KEY", clean_key)
    os.environ.setdefault("LANGCHAIN_API_KEY", clean_key)
    os.environ.setdefault("LANGSMITH_PROJECT", clean_project)
    os.environ.setdefault("LANGCHAIN_PROJECT", clean_project)
    if clean_endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", clean_endpoint)
        os.environ.setdefault("LANGCHAIN_ENDPOINT", clean_endpoint)
    return True


def wrap_openai_client(client: Any) -> Any:
    """Wrap OpenAI SDK clients for LangSmith tracing when enabled.

    The function is a no-op unless LangSmith is fully configured. If the
    langsmith package or wrapper API is unavailable, we keep the original client
    so runtime behavior never depends on observability.
    """

    if not langsmith_enabled() or not langsmith_capture_llm_content():
        return client
    try:
        from langsmith.wrappers import wrap_openai  # type: ignore

        return wrap_openai(client)
    except Exception as exc:  # noqa: BLE001
        global _WRAP_UNAVAILABLE_LOGGED
        if not _WRAP_UNAVAILABLE_LOGGED:
            log.warning("LangSmith OpenAI wrapping unavailable; continuing without SDK spans: %s", exc)
            _WRAP_UNAVAILABLE_LOGGED = True
        return client


def traceable(
    *,
    name: str | None = None,
    run_type: str | None = None,
    project_name: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    process_inputs: Callable[[dict[str, Any]], Any] | None = None,
    process_outputs: Callable[[Any], Any] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Return a lazy LangSmith traceable decorator with a safe no-op fallback.

    The LangSmith decorator inspects the runtime at call time. Some pinned
    LangChain/LangSmith combinations can raise while building that metadata.
    SeaLAI must never let observability break the user path, so this wrapper
    only activates when tracing is configured and falls back to the original
    function on any LangSmith-side failure.
    """

    def _extract_call_metadata(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
        request = kwargs.get("request")
        current_user = kwargs.get("current_user")
        for value in args:
            if request is None and hasattr(value, "session_id"):
                request = value
            if current_user is None and hasattr(value, "user_id"):
                current_user = value
        return identity_trace_metadata(request=request, current_user=current_user)

    def _kwargs_with_call_metadata(
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        call_metadata = _extract_call_metadata(args, kwargs)
        if not call_metadata:
            return kwargs
        traced_kwargs = dict(kwargs)
        existing_extra = traced_kwargs.get("langsmith_extra")
        if not isinstance(existing_extra, dict):
            existing_extra = {}
        existing_metadata = existing_extra.get("metadata")
        if not isinstance(existing_metadata, dict):
            existing_metadata = {}
        traced_kwargs["langsmith_extra"] = {
            **existing_extra,
            "metadata": {
                **existing_metadata,
                **call_metadata,
            },
        }
        return traced_kwargs

    def _decorator(func: Callable[P, R]) -> Callable[P, R]:
        traced_func: Callable[P, R] | None = None

        def _build_traced() -> Callable[P, R] | None:
            nonlocal traced_func
            if traced_func is not None:
                return traced_func
            if not langsmith_enabled():
                return None
            try:
                from langsmith import traceable as _traceable  # type: ignore

                options: dict[str, Any] = {}
                if name:
                    options["name"] = name
                if run_type:
                    options["run_type"] = run_type
                if project_name:
                    options["project_name"] = project_name
                if tags:
                    options["tags"] = list(tags)
                if metadata:
                    options["metadata"] = redact_trace_value(dict(metadata))
                options["process_inputs"] = process_inputs or sanitize_trace_inputs
                options["process_outputs"] = process_outputs or sanitize_trace_outputs
                try:
                    traced_func = _traceable(**options)(func)
                except TypeError:
                    options.pop("process_inputs", None)
                    options.pop("process_outputs", None)
                    traced_func = _traceable(**options)(func)
                return traced_func
            except Exception as exc:  # noqa: BLE001
                log.warning("LangSmith traceable wrapper unavailable; continuing without span: %s", exc)
                return None

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def _async_wrapped(*args: P.args, **kwargs: P.kwargs) -> Any:
                traced = _build_traced()
                if traced is None:
                    return await func(*args, **kwargs)
                try:
                    return await traced(*args, **_kwargs_with_call_metadata(args, dict(kwargs)))  # type: ignore[misc]
                except Exception as exc:  # noqa: BLE001
                    log.warning("LangSmith traced async call failed; continuing without span: %s", exc)
                    return await func(*args, **kwargs)

            return _async_wrapped  # type: ignore[return-value]

        @wraps(func)
        def _wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            traced = _build_traced()
            if traced is None:
                return func(*args, **kwargs)
            try:
                return traced(*args, **_kwargs_with_call_metadata(args, dict(kwargs)))
            except Exception as exc:  # noqa: BLE001
                log.warning("LangSmith traced call failed; continuing without span: %s", exc)
                return func(*args, **kwargs)

        return _wrapped
    return _decorator
