"""JSON serialization utilities with fallbacks for complex objects."""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Union

from fastapi.encoders import jsonable_encoder
import dataclasses


def to_jsonable(obj: Any) -> Any:
    """
    Convert an object to a JSON-serializable form using multiple fallbacks.

    Order:
    1. fastapi.encoders.jsonable_encoder with custom encoder for bytes
    2. .model_dump() (Pydantic v2) -> .dict() (Pydantic v1) -> dataclasses.asdict()
    3. Fallback: json.dumps(..., default=str) or str(obj)
    """
    if obj is None:
        return None

    # Try fastapi jsonable_encoder first, with bytes to base64
    try:
        return jsonable_encoder(obj, custom_encoder={bytes: lambda b: base64.b64encode(b).decode('ascii')})
    except (AttributeError, TypeError) as e:
        # If it fails, try other methods
        pass

    # Try Pydantic v2 model_dump
    if hasattr(obj, 'model_dump') and callable(getattr(obj, 'model_dump')):
        try:
            return obj.model_dump()
        except Exception:
            pass

    # Try Pydantic v1 dict
    if hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
        try:
            return obj.dict()
        except Exception:
            pass

    # Try dataclasses.asdict
    if dataclasses.is_dataclass(obj):
        try:
            return dataclasses.asdict(obj)
        except Exception:
            pass

    # Special cases for LangChain/BaseMessage
    if hasattr(obj, '__class__') and 'BaseMessage' in obj.__class__.__name__:
        try:
            result = {
                'type': getattr(obj, 'type', 'unknown'),
                'content': getattr(obj, 'content', ''),
                'tool_calls': getattr(obj, 'tool_calls', None) if hasattr(obj, 'tool_calls') else None,
            }
            # Remove None values
            return {k: v for k, v in result.items() if v is not None}
        except Exception:
            pass

    # Special case for RAG Document
    if hasattr(obj, '__class__') and 'Document' in obj.__class__.__name__:
        try:
            result = {
                'id': getattr(obj, 'id', None) or getattr(obj, 'page_content', '')[:50] + '...',
                'page_content': getattr(obj, 'page_content', ''),
                'metadata': getattr(obj, 'metadata', {}),
                'score': getattr(obj, 'score', None),
            }
            # Remove None values except score if present
            return {k: v for k, v in result.items() if v is not None or k == 'score'}
        except Exception:
            pass

    # For bytes/audio, encode as base64 with MIME hint
    if isinstance(obj, bytes):
        try:
            mime = 'application/octet-stream'  # Default, could be detected
            return {'data': base64.b64encode(obj).decode('ascii'), 'mime': mime, 'type': 'bytes'}
        except Exception:
            pass

    # Fallback: try json.dumps with default=str
    try:
        json_str = json.dumps(obj, default=str)
        return json.loads(json_str)  # To ensure it's parseable
    except Exception:
        # Last resort: str(obj)
        return str(obj)


def to_jsonable_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert all values in a dict to jsonable."""
    return {k: to_jsonable(v) for k, v in data.items()}


def to_jsonable_list(data: List[Any]) -> List[Any]:
    """Convert all items in a list to jsonable."""
    return [to_jsonable(item) for item in data]