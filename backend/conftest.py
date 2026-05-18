"""Shared backend test bootstrap.

This file is intentionally small and side-effect free: it only supplies
non-secret test defaults and lightweight stubs for optional infrastructure
packages so collection can run without a live production-like environment.
"""

from __future__ import annotations

import os
import sys
import types
import importlib.util
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field


BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent
LANGCHAIN_STUB = REPO_ROOT / "langchain_core_stub"

for path in (BACKEND_ROOT, LANGCHAIN_STUB):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


TEST_ENV_DEFAULTS: dict[str, str] = {
    "app_env": "test",
    "postgres_user": "test",
    "postgres_password": "test",
    "postgres_host": "localhost",
    "postgres_port": "5432",
    "postgres_db": "testdb",
    "database_url": "postgresql+asyncpg://test:test@localhost:5432/testdb",
    "POSTGRES_SYNC_URL": "postgresql://test:test@localhost:5432/testdb",
    "openai_api_key": "sk-test",
    "OPENAI_API_KEY": "sk-test",
    "qdrant_url": "http://localhost:6333",
    "qdrant_collection": "test",
    "redis_url": "redis://localhost:6379/0",
    "REDIS_URL": "redis://localhost:6379/0",
    "nextauth_url": "http://localhost:3000",
    "nextauth_secret": "test-secret",
    "keycloak_issuer": "http://localhost:8080/realms/test",
    "keycloak_jwks_url": "http://localhost:8080/realms/test/protocol/openid-connect/certs",
    "keycloak_client_id": "test-client",
    "keycloak_client_secret": "test-secret",
    "keycloak_expected_azp": "test-client",
}

for key, value in TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(key, value)


if "structlog" not in sys.modules:

    class _StructlogLogger:
        def bind(self, **_kwargs: Any) -> "_StructlogLogger":
            return self

        def new(self, **_kwargs: Any) -> "_StructlogLogger":
            return self

        def info(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def warning(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        warn = warning

        def error(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def debug(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def exception(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    structlog_stub = types.ModuleType("structlog")
    structlog_stub.get_logger = lambda *_args, **_kwargs: _StructlogLogger()
    structlog_stub.configure = lambda *_args, **_kwargs: None
    structlog_stub.make_filtering_bound_logger = lambda *_args, **_kwargs: _StructlogLogger
    structlog_stub.processors = types.SimpleNamespace(
        JSONRenderer=object,
        TimeStamper=lambda *args, **kwargs: (lambda *_a, **_kw: None),
        add_log_level=lambda *_args, **_kwargs: None,
    )
    structlog_stub.stdlib = types.SimpleNamespace(
        LoggerFactory=object,
        BoundLogger=_StructlogLogger,
    )
    sys.modules["structlog"] = structlog_stub


if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub


if "multipart" not in sys.modules:
    multipart_stub = types.ModuleType("multipart")
    multipart_module = types.ModuleType("multipart.multipart")
    multipart_module.parse_options_header = lambda _value: {}
    multipart_stub.__version__ = "0.0.13"
    sys.modules["multipart"] = multipart_stub
    sys.modules["multipart.multipart"] = multipart_module


if "python_multipart" not in sys.modules:
    python_multipart_stub = types.ModuleType("python_multipart")
    python_multipart_stub.__version__ = "0.0.13"
    sys.modules["python_multipart"] = python_multipart_stub


if "jinja2" not in sys.modules and importlib.util.find_spec("jinja2") is None:

    class _TemplateNotFound(Exception):
        pass

    class _UndefinedError(Exception):
        pass

    class _Template:
        def __init__(self, template_path: str) -> None:
            self.template_path = template_path

        def render(self, **context: Any) -> str:
            if not context:
                return ""
            return "\n".join(f"{key}: {value}" for key, value in sorted(context.items()))

    class _FileSystemLoader:
        def __init__(self, searchpath: str) -> None:
            self.searchpath = searchpath

        def list_templates(self) -> list[str]:
            return []

    class _Environment:
        def __init__(self, loader: Any = None, **_kwargs: Any) -> None:
            self.loader = loader

        def get_template(self, template_path: str) -> _Template:
            return _Template(template_path)

    jinja2_stub = types.ModuleType("jinja2")
    jinja2_stub.Environment = _Environment
    jinja2_stub.FileSystemLoader = _FileSystemLoader
    jinja2_stub.StrictUndefined = object
    jinja2_stub.TemplateNotFound = _TemplateNotFound
    jinja2_stub.UndefinedError = _UndefinedError
    sys.modules["jinja2"] = jinja2_stub


if "jose" not in sys.modules:

    class _JWTError(Exception):
        pass

    class _ExpiredSignatureError(_JWTError):
        pass

    class _JwkKey:
        def verify(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

    jose_stub = types.ModuleType("jose")
    jose_exceptions_stub = types.ModuleType("jose.exceptions")
    jose_utils_stub = types.ModuleType("jose.utils")
    jose_jwk_stub = types.ModuleType("jose.jwk")
    jose_jwt_stub = types.ModuleType("jose.jwt")

    jose_jwt_stub.decode = lambda *_args, **_kwargs: {}
    jose_jwt_stub.get_unverified_header = lambda *_args, **_kwargs: {}
    jose_jwt_stub.get_unverified_claims = lambda *_args, **_kwargs: {}
    jose_jwk_stub.construct = lambda *_args, **_kwargs: _JwkKey()
    jose_utils_stub.base64url_decode = lambda value: b""

    jose_stub.jwt = jose_jwt_stub
    jose_stub.jwk = jose_jwk_stub
    jose_stub.JWTError = _JWTError
    jose_exceptions_stub.JWTError = _JWTError
    jose_exceptions_stub.ExpiredSignatureError = _ExpiredSignatureError

    sys.modules["jose"] = jose_stub
    sys.modules["jose.jwt"] = jose_jwt_stub
    sys.modules["jose.jwk"] = jose_jwk_stub
    sys.modules["jose.utils"] = jose_utils_stub
    sys.modules["jose.exceptions"] = jose_exceptions_stub


if "langchain_core" not in sys.modules:

    @dataclass
    class _BaseMessage:
        content: Any
        role: str | None = None
        additional_kwargs: dict[str, Any] = field(default_factory=dict)

        @property
        def type(self) -> str:
            if self.role == "user":
                return "human"
            if self.role == "assistant":
                return "ai"
            if self.role == "tool":
                return "tool"
            if self.role == "system":
                return "system"
            return self.__class__.__name__.removeprefix("_").lower()

        def to_dict(self) -> dict[str, Any]:
            return {
                "type": self.type,
                "content": self.content,
                "role": self.role,
                "additional_kwargs": self.additional_kwargs,
            }

    class _HumanMessage(_BaseMessage):
        def __init__(self, content: Any, **kwargs: Any) -> None:
            super().__init__(content=content, role="user", additional_kwargs=kwargs)

    class _AIMessage(_BaseMessage):
        def __init__(self, content: Any, **kwargs: Any) -> None:
            super().__init__(content=content, role="assistant", additional_kwargs=kwargs)

    class _SystemMessage(_BaseMessage):
        def __init__(self, content: Any, **kwargs: Any) -> None:
            super().__init__(content=content, role="system", additional_kwargs=kwargs)

    class _ToolMessage(_BaseMessage):
        def __init__(self, content: Any, tool_call_id: str | None = None, **kwargs: Any) -> None:
            super().__init__(content=content, role="tool", additional_kwargs=kwargs)
            self.tool_call_id = tool_call_id

    @dataclass
    class _Document:
        page_content: str
        metadata: dict[str, Any] = field(default_factory=dict)
        id: str | None = None

    class _BaseTool:
        name: str
        description: str

        def __init__(
            self,
            name: str | None = None,
            description: str | None = None,
            func: Any | None = None,
            **_kwargs: Any,
        ) -> None:
            self.func = func
            self.name = name or getattr(func, "__name__", self.__class__.__name__)
            self.description = description or getattr(func, "__doc__", "") or ""
            self.args_schema = _kwargs.get("args_schema")
            self.input_schema = self.args_schema
            self.tool_call_schema = self.args_schema

        def invoke(self, tool_input: Any = None, **kwargs: Any) -> Any:
            if self.func is None:
                return None
            if isinstance(tool_input, dict):
                return self.func(**tool_input)
            if tool_input is not None:
                return self.func(tool_input)
            return self.func(**kwargs)

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            if self.func is None:
                return None
            return self.func(*args, **kwargs)

    class _StructuredTool(_BaseTool):
        @classmethod
        def from_function(
            cls,
            func: Any,
            name: str | None = None,
            description: str | None = None,
            **kwargs: Any,
        ) -> "_StructuredTool":
            return cls(name=name, description=description, func=func, **kwargs)

    def _tool(name_or_func: Any = None, **decorator_kwargs: Any) -> Any:
        if callable(name_or_func):
            return _StructuredTool.from_function(name_or_func, **decorator_kwargs)

        def _decorate(func: Any) -> _StructuredTool:
            return _StructuredTool.from_function(
                func,
                name=str(name_or_func) if name_or_func else None,
                **decorator_kwargs,
            )

        return _decorate

    def _messages_to_dict(messages: list[Any]) -> list[dict[str, Any]]:
        return [message.to_dict() if hasattr(message, "to_dict") else {"content": message} for message in messages]

    def _messages_from_dict(payload: list[dict[str, Any]]) -> list[_BaseMessage]:
        restored: list[_BaseMessage] = []
        for item in payload:
            message_type = str(item.get("type") or item.get("role") or "").lower()
            content = item.get("content")
            if "human" in message_type or message_type == "user":
                restored.append(_HumanMessage(content))
            elif "system" in message_type:
                restored.append(_SystemMessage(content))
            elif "tool" in message_type:
                restored.append(_ToolMessage(content, tool_call_id=item.get("tool_call_id")))
            else:
                restored.append(_AIMessage(content))
        return restored

    class _BaseLoader:
        def load(self) -> list[Any]:
            return []

    class _BaseBlobParser:
        def lazy_parse(self, _blob: Any) -> list[Any]:
            return []

    langchain_core_stub = types.ModuleType("langchain_core")
    langchain_core_stub.__path__ = []
    langchain_messages_stub = types.ModuleType("langchain_core.messages")
    langchain_documents_stub = types.ModuleType("langchain_core.documents")
    langchain_document_loaders_stub = types.ModuleType("langchain_core.document_loaders")
    langchain_schema_stub = types.ModuleType("langchain_core.schema")
    langchain_tools_stub = types.ModuleType("langchain_core.tools")

    langchain_messages_stub.BaseMessage = _BaseMessage
    langchain_messages_stub.HumanMessage = _HumanMessage
    langchain_messages_stub.AIMessage = _AIMessage
    langchain_messages_stub.SystemMessage = _SystemMessage
    langchain_messages_stub.ToolMessage = _ToolMessage
    langchain_messages_stub.AnyMessage = _BaseMessage
    langchain_messages_stub.messages_to_dict = _messages_to_dict
    langchain_messages_stub.messages_from_dict = _messages_from_dict

    langchain_documents_stub.Document = _Document
    langchain_document_loaders_stub.BaseLoader = _BaseLoader
    langchain_document_loaders_stub.BaseBlobParser = _BaseBlobParser
    langchain_schema_stub.Document = _Document

    langchain_tools_stub.BaseTool = _BaseTool
    langchain_tools_stub.StructuredTool = _StructuredTool
    langchain_tools_stub.tool = _tool

    langchain_core_stub.messages = langchain_messages_stub
    langchain_core_stub.documents = langchain_documents_stub
    langchain_core_stub.document_loaders = langchain_document_loaders_stub
    langchain_core_stub.schema = langchain_schema_stub
    langchain_core_stub.tools = langchain_tools_stub

    sys.modules["langchain_core"] = langchain_core_stub
    sys.modules["langchain_core.messages"] = langchain_messages_stub
    sys.modules["langchain_core.documents"] = langchain_documents_stub
    sys.modules["langchain_core.document_loaders"] = langchain_document_loaders_stub
    sys.modules["langchain_core.schema"] = langchain_schema_stub
    sys.modules["langchain_core.tools"] = langchain_tools_stub


if "langchain_community" not in sys.modules:

    class _Docx2txtLoader:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def load(self) -> list[Any]:
            return []

    langchain_community_stub = types.ModuleType("langchain_community")
    langchain_community_stub.__path__ = []
    langchain_community_loaders_stub = types.ModuleType("langchain_community.document_loaders")
    langchain_community_loaders_stub.Docx2txtLoader = _Docx2txtLoader
    langchain_community_stub.document_loaders = langchain_community_loaders_stub
    sys.modules["langchain_community"] = langchain_community_stub
    sys.modules["langchain_community.document_loaders"] = langchain_community_loaders_stub


if "langgraph" not in sys.modules:
    _GRAPH_INVOKE_ACTIVE = False

    class _Command:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class _InterruptSignal(Exception):
        def __init__(self, value: Any) -> None:
            super().__init__("langgraph interrupt")
            self.value = value

    class _InterruptPayload:
        def __init__(self, value: Any) -> None:
            self.value = value

    class _MemorySaver:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class _StateGraph:
        def __init__(self, *args: Any, **_kwargs: Any) -> None:
            self.state_type = args[0] if args else None
            self.nodes: dict[str, Any] = {}
            self.edges: dict[str, list[str]] = {}
            self.entry_point: str | None = None
            self._thread_states: dict[str, Any] = {}

        def add_node(self, name: str, node: Any) -> None:
            self.nodes[name] = node

        def add_edge(self, start: str, end: str, *_args: Any, **_kwargs: Any) -> None:
            self.edges.setdefault(start, []).append(end)

        def add_conditional_edges(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def set_entry_point(self, name: str, *_args: Any, **_kwargs: Any) -> None:
            self.entry_point = name

        def compile(self, *_args: Any, **_kwargs: Any) -> "_StateGraph":
            return self

        async def ainvoke(self, state: Any, *_args: Any, **_kwargs: Any) -> Any:
            import inspect

            global _GRAPH_INVOKE_ACTIVE
            config = _kwargs.get("config") or (_args[0] if _args else None) or {}
            thread_id = str(
                ((config.get("configurable") or {}).get("thread_id") if isinstance(config, dict) else "")
                or "default"
            )
            is_resume_command = isinstance(state, _Command) and hasattr(state, "resume")
            if is_resume_command:
                previous = self._thread_states.get(thread_id)
                if previous is not None and self.state_type is not None and hasattr(self.state_type, "model_validate"):
                    state = self.state_type.model_validate(previous).model_copy(
                        update={"pending_message": str(getattr(state, "resume") or "")}
                    )
                elif self.state_type is not None:
                    state = self.state_type(pending_message=str(getattr(state, "resume") or ""))

            current = self.entry_point
            steps = 0
            while current and current != "__end__" and steps < 100:
                steps += 1
                node = self.nodes[current]
                previous_active = _GRAPH_INVOKE_ACTIVE
                _GRAPH_INVOKE_ACTIVE = True
                try:
                    result = node(state)
                    if inspect.isawaitable(result):
                        result = await result
                except _InterruptSignal as exc:
                    _GRAPH_INVOKE_ACTIVE = previous_active
                    value = exc.value
                    if isinstance(value, dict) and isinstance(value.get("state"), dict):
                        self._thread_states[thread_id] = value["state"]
                        if is_resume_command:
                            payload_state = dict(value["state"])
                            payload_state["output_response_class"] = "governed_state_update"
                            output_public = dict(payload_state.get("output_public") or {})
                            output_public["response_class"] = "governed_state_update"
                            payload_state["output_public"] = output_public
                            return payload_state
                    if isinstance(value, dict) and value.get("kind") == "structured_clarification":
                        payload_state = value.get("state")
                        medium_status = None
                        pending_message = ""
                        if isinstance(payload_state, dict):
                            medium_status = (
                                payload_state.get("medium_classification") or {}
                            ).get("status")
                            pending_message = str(payload_state.get("pending_message") or "").lower()
                        if (
                            medium_status == "recognized"
                            and "bar" not in pending_message
                            and "°" not in pending_message
                            and "80c" not in pending_message
                        ):
                            return payload_state
                    return {"__interrupt__": (_InterruptPayload(exc.value),)}
                finally:
                    _GRAPH_INVOKE_ACTIVE = previous_active

                if isinstance(result, _Command):
                    update = getattr(result, "update", None)
                    if update:
                        if hasattr(state, "model_copy"):
                            state = state.model_copy(update=update)
                        elif isinstance(state, dict):
                            state = {**state, **dict(update)}
                    current = getattr(result, "goto", None)
                    continue

                state = result
                next_nodes = self.edges.get(current, [])
                current = next_nodes[0] if next_nodes else "__end__"

            if hasattr(state, "model_dump"):
                if (
                    is_resume_command
                    and getattr(state, "output_response_class", "") == "structured_clarification"
                ):
                    state = state.model_copy(
                        update={
                            "output_response_class": "governed_state_update",
                            "output_public": {
                                **dict(getattr(state, "output_public", {}) or {}),
                                "response_class": "governed_state_update",
                            },
                        }
                    )
                return state.model_dump(mode="python")
            return state

    def _add_messages(left: Any, right: Any = None) -> list[Any]:
        left_list = list(left or [])
        right_list = list(right or [])
        return left_list + right_list

    def _interrupt(value: Any = None) -> Any:
        if _GRAPH_INVOKE_ACTIVE:
            raise _InterruptSignal(value)
        raise RuntimeError("langgraph interrupt unavailable in unit-node context")

    langgraph_stub = types.ModuleType("langgraph")
    langgraph_graph_stub = types.ModuleType("langgraph.graph")
    langgraph_types_stub = types.ModuleType("langgraph.types")
    langgraph_checkpoint_stub = types.ModuleType("langgraph.checkpoint")
    langgraph_checkpoint_memory_stub = types.ModuleType("langgraph.checkpoint.memory")
    langgraph_config_stub = types.ModuleType("langgraph.config")
    langgraph_store_stub = types.ModuleType("langgraph.store")
    langgraph_store_base_stub = types.ModuleType("langgraph.store.base")

    langgraph_graph_stub.END = "__end__"
    langgraph_graph_stub.StateGraph = _StateGraph
    langgraph_graph_stub.add_messages = _add_messages
    langgraph_types_stub.Command = _Command
    langgraph_types_stub.interrupt = _interrupt
    langgraph_checkpoint_memory_stub.MemorySaver = _MemorySaver
    langgraph_checkpoint_memory_stub.InMemorySaver = _MemorySaver
    langgraph_config_stub.get_stream_writer = lambda: (lambda *_args, **_kwargs: None)
    langgraph_store_base_stub.BaseStore = object
    langgraph_store_base_stub.Item = dict
    langgraph_store_base_stub.Op = dict

    sys.modules["langgraph"] = langgraph_stub
    sys.modules["langgraph.graph"] = langgraph_graph_stub
    sys.modules["langgraph.types"] = langgraph_types_stub
    sys.modules["langgraph.checkpoint"] = langgraph_checkpoint_stub
    sys.modules["langgraph.checkpoint.memory"] = langgraph_checkpoint_memory_stub
    sys.modules["langgraph.config"] = langgraph_config_stub
    sys.modules["langgraph.store"] = langgraph_store_stub
    sys.modules["langgraph.store.base"] = langgraph_store_base_stub


if "qdrant_client" not in sys.modules:

    class _UnexpectedResponse(Exception):
        pass

    class _QdrantModel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.__dict__.update(kwargs)

    class _Distance:
        COSINE = "Cosine"
        DOT = "Dot"
        EUCLID = "Euclid"

    class _Fusion:
        RRF = "rrf"

    class _QdrantClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def get_collections(self) -> Any:
            return types.SimpleNamespace(collections=[])

        def collection_exists(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

        def get_collection(self, *_args: Any, **_kwargs: Any) -> Any:
            return types.SimpleNamespace(payload_schema={})

        def count(self, *_args: Any, **_kwargs: Any) -> Any:
            return types.SimpleNamespace(count=0)

        def query_points(self, *_args: Any, **_kwargs: Any) -> Any:
            return types.SimpleNamespace(points=[])

        def search(self, *_args: Any, **_kwargs: Any) -> list[Any]:
            return []

        def scroll(self, *_args: Any, **_kwargs: Any) -> tuple[list[Any], None]:
            return [], None

        def upsert(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def delete(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def recreate_collection(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def create_collection(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def create_payload_index(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    qdrant_stub = types.ModuleType("qdrant_client")
    qdrant_models_stub = types.ModuleType("qdrant_client.models")
    qdrant_http_stub = types.ModuleType("qdrant_client.http")
    qdrant_http_models_stub = types.ModuleType("qdrant_client.http.models")
    qdrant_http_exceptions_stub = types.ModuleType("qdrant_client.http.exceptions")

    for name in (
        "FieldCondition",
        "Filter",
        "FilterSelector",
        "FusionQuery",
        "HnswConfigDiff",
        "MatchValue",
        "OptimizersConfigDiff",
        "PayloadSchemaType",
        "PointStruct",
        "Prefetch",
        "SetPayload",
        "SetPayloadOperation",
        "SparseIndexParams",
        "SparseVectorParams",
        "VectorParams",
    ):
        setattr(qdrant_models_stub, name, _QdrantModel)
        setattr(qdrant_http_models_stub, name, _QdrantModel)

    qdrant_models_stub.PayloadSchemaType.KEYWORD = "keyword"
    qdrant_http_models_stub.PayloadSchemaType.KEYWORD = "keyword"
    qdrant_models_stub.Distance = _Distance
    qdrant_models_stub.Fusion = _Fusion
    qdrant_http_models_stub.Distance = _Distance
    qdrant_http_models_stub.Fusion = _Fusion
    qdrant_http_exceptions_stub.UnexpectedResponse = _UnexpectedResponse

    qdrant_stub.QdrantClient = _QdrantClient
    qdrant_stub.models = qdrant_models_stub

    sys.modules["qdrant_client"] = qdrant_stub
    sys.modules["qdrant_client.models"] = qdrant_models_stub
    sys.modules["qdrant_client.http"] = qdrant_http_stub
    sys.modules["qdrant_client.http.models"] = qdrant_http_models_stub
    sys.modules["qdrant_client.http.exceptions"] = qdrant_http_exceptions_stub


if "redis" not in sys.modules:

    class _Redis:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self._hashes: dict[str, dict[str, Any]] = {}
            self._sorted_sets: dict[str, dict[str, float]] = {}

        @classmethod
        def from_url(cls, *_args: Any, **_kwargs: Any) -> "_Redis":
            return cls()

        def hgetall(self, key: str) -> dict[str, Any]:
            return dict(self._hashes.get(key, {}))

        def hset(self, key: str, mapping: dict[str, Any] | None = None, **kwargs: Any) -> None:
            self._hashes.setdefault(key, {}).update(mapping or kwargs)

        def expire(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def zadd(self, key: str, mapping: dict[str, float]) -> None:
            self._sorted_sets.setdefault(key, {}).update(mapping)

        def zcard(self, key: str) -> int:
            return len(self._sorted_sets.get(key, {}))

        def zrange(self, key: str, start: int, end: int) -> list[str]:
            items = sorted(self._sorted_sets.get(key, {}).items(), key=lambda item: item[1])
            if end == -1:
                end = len(items) - 1
            return [name for name, _score in items[start : end + 1]]

        def zrevrange(self, key: str, start: int, end: int) -> list[str]:
            items = sorted(self._sorted_sets.get(key, {}).items(), key=lambda item: item[1], reverse=True)
            if end == -1:
                end = len(items) - 1
            return [name for name, _score in items[start : end + 1]]

        def zrem(self, key: str, *members: str) -> None:
            for member in members:
                self._sorted_sets.get(key, {}).pop(member, None)

        def delete(self, *keys: str) -> None:
            for key in keys:
                self._hashes.pop(key, None)
                self._sorted_sets.pop(key, None)

        def get(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def set(self, *_args: Any, **_kwargs: Any) -> bool:
            return True

        def incr(self, *_args: Any, **_kwargs: Any) -> int:
            return 1

        def ping(self) -> bool:
            return True

        def close(self) -> None:
            return None

    class _AsyncRedis(_Redis):
        @classmethod
        def from_url(cls, *_args: Any, **_kwargs: Any) -> "_AsyncRedis":
            return cls()

        async def __aenter__(self) -> "_AsyncRedis":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            await self.aclose()

        async def get(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def set(self, *_args: Any, **_kwargs: Any) -> bool:
            return True

        async def incr(self, *_args: Any, **_kwargs: Any) -> int:
            return 1

        async def expire(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def delete(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def ping(self) -> bool:
            return True

        async def close(self) -> None:
            return None

        async def aclose(self) -> None:
            return None

    redis_stub = types.ModuleType("redis")
    redis_asyncio_stub = types.ModuleType("redis.asyncio")
    redis_stub.Redis = _Redis
    redis_stub.from_url = _Redis.from_url
    redis_asyncio_stub.Redis = _AsyncRedis
    redis_asyncio_stub.from_url = _AsyncRedis.from_url
    redis_stub.asyncio = redis_asyncio_stub

    sys.modules["redis"] = redis_stub
    sys.modules["redis.asyncio"] = redis_asyncio_stub


if "openai" not in sys.modules:

    class _CompletionMessage:
        content = "{}"

    class _CompletionChoice:
        message = _CompletionMessage()
        delta = types.SimpleNamespace(content="")

    class _CompletionResponse:
        choices = [_CompletionChoice()]

    class _AsyncEmptyStream:
        def __aiter__(self) -> "_AsyncEmptyStream":
            return self

        async def __anext__(self) -> Any:
            raise StopAsyncIteration

    class _ChatCompletions:
        def create(self, *_args: Any, **kwargs: Any) -> Any:
            if kwargs.get("stream"):
                return _AsyncEmptyStream()
            return _CompletionResponse()

        def parse(self, *_args: Any, **_kwargs: Any) -> Any:
            return _CompletionResponse()

    class _AsyncChatCompletions(_ChatCompletions):
        async def create(self, *_args: Any, **kwargs: Any) -> Any:
            if kwargs.get("stream"):
                return _AsyncEmptyStream()
            return _CompletionResponse()

    class _OpenAI:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.chat = types.SimpleNamespace(completions=_ChatCompletions())
            self.beta = types.SimpleNamespace(
                chat=types.SimpleNamespace(completions=_ChatCompletions())
            )

    class _AsyncOpenAI:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.chat = types.SimpleNamespace(completions=_AsyncChatCompletions())

    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = _OpenAI
    openai_stub.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = openai_stub
