import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.api.auth import verify_token
from app.services.ai_service import get_response, stream_response
from app.models.chat import ChatRequest

# Router mit Prefix "/ai"
router = APIRouter(prefix="/ai")

@router.post("/chat-test", tags=["AI"], summary="Test-Chat ohne Authentifizierung")
async def chat_without_auth(request: ChatRequest):
    """
    Test-Chat-Endpoint ohne Keycloak-Authentifizierung.
    Nützlich für Entwicklung und Debugging.
    """
    try:
        response = await get_response(request.message)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Verarbeiten der Anfrage: {str(e)}")

@router.post("/chat", tags=["AI"], summary="Geschützter Chat mit Authentifizierung")
async def chat_with_ai(request: ChatRequest, token: str = Depends(verify_token)):
    """
    Geschützter Endpunkt, der eine Anfrage an OpenAI sendet.
    Erfordert ein gültiges Keycloak-Token.
    """
    try:
        response = await get_response(request.message)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Verarbeiten der Anfrage: {str(e)}")

@router.post("/stream", tags=["AI"], summary="Streaming-Chat mit Authentifizierung")
async def stream_chat(request: ChatRequest, token: str = Depends(verify_token)):
    """
    Geschützter Endpunkt, der die OpenAI-Antwort als Server-Sent Events (SSE) streamt.
    Erfordert ein gültiges Keycloak-Token.
    """
    try:
        async def event_generator():
            # Verwende request.message, falls das beabsichtigt ist
            yield f"data: {request.message}\n\n"
            await asyncio.sleep(1)
            yield "data: [DONE]\n\n"
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Streaming: {str(e)}")

@router.get("/stream-test", tags=["AI"], summary="Test-Streaming ohne Authentifizierung")
async def stream_chat_test(message: str = Query(..., description="Die Chat-Nachricht")):
    """
    Ungeschützter Test-Endpunkt für Streaming ohne Authentifizierung.
    Nutzt GET, sodass EventSource problemlos funktioniert.
    """
    try:
        async def event_generator():
            yield f"data: {message}\n\n"
            await asyncio.sleep(1)
            yield "data: [DONE]\n\n"
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Streaming: {str(e)}")
