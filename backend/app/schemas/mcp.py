from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field

class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field("2.0", pattern=r"^2\.0$")
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Union[str, int, None] = None

class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Union[str, int, None] = None
