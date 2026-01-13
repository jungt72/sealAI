import uuid
from fastapi import HTTPException, status
from app.langgraph_v2.contracts import error_detail

def normalize_chat_id(chat_id: str | None, request_id: str | None = None) -> str:
    """
    Validates and normalizes chat_id.
    - If empty/None -> generates new UUIDv4.
    - If provided -> MUST be valid UUIDv4 string.
    
    Raises:
        HTTPException(400) if invalid format.
    """
    raw = (chat_id or "").strip()
    if not raw:
        return str(uuid.uuid4())
    
    try:
        # Strict UUID verification
        val = uuid.UUID(raw, version=4)
        # Verify strict string equality to avoid "safe" parsing like '{uuid}' or 'uuid...' 
        if str(val) != raw:
             raise ValueError("Format mismatch")
        return str(val)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_chat_id", request_id=request_id or "unknown", message="Chat ID must be a valid UUIDv4."),
        )
