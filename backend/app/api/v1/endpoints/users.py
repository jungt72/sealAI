from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/ping", summary="👥 User Ping", response_class=JSONResponse)
async def users_ping():
    return {"pong": True, "module": "users"}
