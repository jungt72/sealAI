from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/ping", summary="📡 Ping", response_class=JSONResponse)
async def ping():
    return {"message": "pong"}
