# SealAI Code Dump (Fri Sep 26 11:52:46 AM UTC 2025)


## backend/.env

```bash
# =========================================
# SealAI Backend – Production Defaults (backend/.env)
# =========================================

# -------- App ----------
ENV=production
OFFLINE_MODE=0
LOG_LEVEL=DEBUG

# -------- Networking / CORS / WS ----------
ALLOWED_ORIGIN="https://sealai.net,https://www.sealai.net"
ALLOW_WS_ORIGIN_ANY=0
ALLOW_WS_ORIGIN_EMPTY=0
WS_REQUIRE_ORIGIN=0
WS_ENFORCE_TOKEN_ORIGIN=0
WS_AUTH_OPTIONAL=1

# -------- Auth / Keycloak (prod) ----------
KEYCLOAK_BASE_URL="https://auth.sealai.net"
KEYCLOAK_REALM="sealAI"
KEYCLOAK_CLIENT_ID="nextauth"
KEYCLOAK_CLIENT_SECRET=""   # via Secret/CI setzen
KEYCLOAK_ISSUER="https://auth.sealai.net/realms/sealAI"
KEYCLOAK_JWKS_URL="https://auth.sealai.net/realms/sealAI/protocol/openid-connect/certs"
KEYCLOAK_OPENID_DISCOVERY="${KEYCLOAK_BASE_URL}/realms/${KEYCLOAK_REALM}/.well-known/openid-configuration"

# -------- JWT / NextAuth ----------
NEXTAUTH_URL="https://sealai.net"
NEXTAUTH_SECRET=""          # via Secret/CI setzen

# -------- OpenAI / LLM ----------
OPENAI_API_BASE="https://api.openai.com/v1"
OPENAI_API_KEY=sk-...dein_schlüssel...
LLM_MODEL_DEFAULT="gpt-5-mini"
LLM_STREAMING=1
GRAPH_BUILDER=consult

# Einheitlich auf GPT-5-mini stellen
OPENAI_MODEL=gpt-5-mini
OPENAI_INTENT_MODEL=gpt-5-mini
OPENAI_INTENT_FALLBACK_MODEL=gpt-5-mini
OPENAI_ROUTER_MODEL=gpt-5-mini

# -------- Streaming Tunables (WS + SSE) ----------
WS_STREAM_NODES="*"
WS_EMIT_FINAL_TEXT=0
WS_COALESCE_MIN_CHARS=1
WS_COALESCE_MAX_LAT_MS=1
WS_EVENT_TIMEOUT_SEC=60
WS_INPUT_MAX_CHARS=4000

SSE_COALESCE_MIN_CHARS=24
SSE_COALESCE_MAX_LAT_MS=60
SSE_EVENT_TIMEOUT_SEC=60
SSE_INPUT_MAX_CHARS=4000

# -------- Redis ----------
REDIS_URL="redis://redis:6379/0"
REDIS_CHECKPOINTER_URL="${REDIS_URL}"

# -------- PostgreSQL ----------
POSTGRES_HOST="postgres"
POSTGRES_PORT="5432"
POSTGRES_DB="sealai"
POSTGRES_USER="sealai"
POSTGRES_PASSWORD=""        # via Secret/CI setzen
SQLALCHEMY_ECHO=0

# -------- Qdrant ----------
QDRANT_URL="http://qdrant:6333"
QDRANT_COLLECTION="sealai-docs"
QDRANT_API_KEY=""

# -------- RAG / Embeddings ----------
EMBEDDINGS_MODEL="intfloat/multilingual-e5-base"
RAG_TOP_K=6
RAG_BM25_ENABLED=false      # BM25-Logs abschalten; auf true + Index schalten, wenn genutzt
# RAG_BM25_INDEX="sealai-bm25"

# -------- LangSmith ----------
LANGSMITH_TRACING=0
LANGSMITH_API_KEY=""
LANGSMITH_PROJECT="sealai"

# -------- Server ----------
HOST="0.0.0.0"
PORT="8000"
WORKERS=1

# -------- Feature Flags ----------
ENABLE_RAG=1
ENABLE_CONSULT_FLOW=1
ENABLE_SUPERVISOR=0

# -------- Dateien ----------
RFQ_PDF_DIR="/app/data/rfq"
MICRO_CHUNK_CHARS=1

```


## backend/.env.example

```example
ENV=production
LOG_LEVEL=INFO
LLM_MODEL_DEFAULT=gpt-5-mini
REDIS_URL=redis://redis:6379/0
REDIS_CHECKPOINTER_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION_PREFIX=sealai-docs
LTM_COLLECTION=sealai_ltm
LTM_EMB_MODEL=intfloat/multilingual-e5-base

```


## backend/Dockerfile

```backend/Dockerfile
# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS builder
WORKDIR /opt/build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc curl libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements*.txt ./
RUN set -eux; mkdir -p /opt/wheels; \
    if [ -f requirements.txt ]; then pip wheel -r requirements.txt -w /opt/wheels; \
    elif [ -f requirements.prod.txt ]; then pip wheel -r requirements.prod.txt -w /opt/wheels; \
    fi

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 10001 -s /usr/sbin/nologin appuser

# Python deps
COPY --from=builder /opt/wheels /opt/wheels
COPY requirements*.txt ./
RUN set -eux; \
    if ls /opt/wheels/*.whl >/dev/null 2>&1; then pip install /opt/wheels/*; fi; \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; \
    elif [ -f requirements.prod.txt ]; then pip install -r requirements.prod.txt; fi

# App code
COPY app ./app

# Alembic config + scripts (fixes: "No 'script_location' key found")
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

USER appuser
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]

```


## backend/alembic/env.py

```py
from __future__ import annotations
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic Config
config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# DB-URL aus ENV übernehmen
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL not set")
config.set_main_option("sqlalchemy.url", db_url)

# Models-Metadata laden
from app.database import Base  # noqa: E402

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Offline: ohne DB-Connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Online: mit echter Connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",            # WICHTIG: erwartet 'sqlalchemy.url'
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

```


## backend/alembic/versions/70968fe4c62e_add_form_results_table.py

```py
"""add form_results table

Revision ID: 70968fe4c62e
Revises: 963dc293d186
Create Date: 2025-04-24 11:27:46.686028
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '70968fe4c62e'
down_revision = '963dc293d186'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'form_results',
        sa.Column('id', sa.String(), primary_key=True, index=True),
        sa.Column('username', sa.String(), nullable=False, index=True),
        sa.Column('radial_clearance', sa.Float(), nullable=False),
        sa.Column('tolerance_fit', sa.String(), nullable=False),
        sa.Column('result_text', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_form_results_created_at', 'form_results', ['created_at'])

def downgrade():
    op.drop_index('ix_form_results_created_at', table_name='form_results')
    op.drop_table('form_results')

```


## backend/alembic/versions/963dc293d186_initial_schema.py

```py
"""Initial schema

Revision ID: 963dc293d186
Revises: None
Create Date: 2025-04-16 11:57:31.285553
"""

# revision identifiers, used by Alembic.
revision = '963dc293d186'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_username'), 'chat_messages', ['username'], unique=False)
    # ### end Alembic commands ###

def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_chat_messages_username'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
    # ### end Alembic commands ###

```


## backend/app/__init__.py

```py

```


## backend/app/api/__init__.py

```py

```


## backend/app/api/v1/__init__.py

```py

```


## backend/app/api/v1/api.py

```py
from __future__ import annotations
from app.api.v1.endpoints import rfq as rfq_endpoint
from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai,
    auth,
    chat_ws,
    consult_invoke,
    memory,
    system,
    users,
)
from app.api.v1.endpoints import langgraph_sse  # <-- NEU

api_router = APIRouter()

# SSE
api_router.include_router(langgraph_sse.router, prefix="/langgraph", tags=["sse"])  # <-- NEU

# WebSocket (ohne extra Prefix → /api/v1/ai/ws)
api_router.include_router(chat_ws.router, tags=["ws"])

# Sync-Invoke (Debug)
api_router.include_router(consult_invoke.router, tags=["test"])

# REST
api_router.include_router(ai.router, prefix="/ai")   # → /api/v1/ai/beratung
api_router.include_router(auth.router)
api_router.include_router(memory.router)
api_router.include_router(system.router)
api_router.include_router(users.router)

api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])

```


## backend/app/api/v1/dependencies/__init__.py

```py

```


## backend/app/api/v1/dependencies/auth.py

```py
import os
import time
import logging
from typing import Optional, Tuple, Iterable
import urllib.parse as urlparse

import httpx
from jose import jwt, jwk
from jose.utils import base64url_decode
from fastapi import WebSocket

logger = logging.getLogger("auth")

# ---- Config / ENV ------------------------------------------------------------

def _csv(env: str) -> Iterable[str]:
    raw = (os.getenv(env) or "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]

def _norm_url(u: str) -> str:
    """Normalize for strict compare: lowercase scheme/host, strip trailing slash."""
    if not u:
        return ""
    try:
        p = urlparse.urlparse(u.strip())
        scheme = (p.scheme or "https").lower()
        host   = (p.hostname or "").lower()
        port   = f":{p.port}" if p.port else ""
        path   = (p.path or "").rstrip("/")
        return f"{scheme}://{host}{port}{path}"
    except Exception:
        return u.strip().rstrip("/").lower()

REALM_URL  = os.getenv("KEYCLOAK_REALM_URL", "https://auth.sealai.net/realms/sealAI")
ISSUER_ENV = os.getenv("KEYCLOAK_ISSUER", REALM_URL)
ALLOWED_ISSUERS = {ISSUER_ENV, REALM_URL, *_csv("KEYCLOAK_ALLOWED_ISSUERS")}
ALLOWED_ISSUERS_NORM = {_norm_url(x) for x in ALLOWED_ISSUERS if x}

JWKS_URL = (
    os.getenv("KEYCLOAK_JWKS_URL")
    or f"{_norm_url(ISSUER_ENV)}/protocol/openid-connect/certs"
)

ALLOWED_AUDIENCES = set(_csv("ALLOWED_AUDIENCES") or ["account", "nextauth", "sealai-backend-api"])

JWKS_TTL_SEC = int(os.getenv("JWKS_TTL_SEC", "600"))
CLOCK_SKEW   = int(os.getenv("WS_CLOCK_SKEW_LEEWAY", "120"))

# ---- JWKS cache with TTL -----------------------------------------------------

_JWKS_CACHE = {"data": None, "ts": 0.0}

def _get_jwks_cached() -> dict:
    now = time.time()
    if _JWKS_CACHE["data"] and (now - _JWKS_CACHE["ts"] < JWKS_TTL_SEC):
        return _JWKS_CACHE["data"]  # type: ignore[return-value]
    logger.info("Fetching JWKS from %s", JWKS_URL)
    with httpx.Client(timeout=10.0) as client:
        r = client.get(JWKS_URL)
        r.raise_for_status()
        _JWKS_CACHE["data"] = r.json()
        _JWKS_CACHE["ts"] = now
        return _JWKS_CACHE["data"]  # type: ignore[return-value]

def _jwks_clear():
    _JWKS_CACHE["data"] = None
    _JWKS_CACHE["ts"] = 0.0

def _find_key(kid: str) -> Optional[dict]:
    jwks = _get_jwks_cached()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    # miss? refresh once
    _jwks_clear()
    jwks = _get_jwks_cached()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None

# ---- Token verification ------------------------------------------------------

def _verify_rs256(token: str) -> dict:
    try:
        headers = jwt.get_unverified_header(token)
        payload = jwt.get_unverified_claims(token)
    except Exception as e:
        raise ValueError(f"invalid token format: {e}")

    kid = headers.get("kid")
    if not kid:
        raise ValueError("token header missing 'kid'")

    key_dict = _find_key(kid)
    if not key_dict:
        raise ValueError("jwks key not found for kid")

    # signature
    signing_input, signature = token.rsplit(".", 1)
    signature_bytes = base64url_decode(signature.encode())
    public_key = jwk.construct(key_dict)
    if not public_key.verify(signing_input.encode(), signature_bytes):
        raise ValueError("signature verification failed")

    # temporal claims (with skew)
    now = int(time.time())
    exp = int(payload.get("exp", 0) or 0)
    nbf = int(payload.get("nbf", 0) or 0)
    if nbf and now + CLOCK_SKEW < nbf:
        raise ValueError("token not yet valid (nbf)")
    if exp and now - CLOCK_SKEW >= exp:
        raise ValueError("token expired")

    # issuer (case/host normalized)
    iss = payload.get("iss")
    if _norm_url(iss or "") not in ALLOWED_ISSUERS_NORM:
        raise ValueError(f"invalid issuer: {iss}")

    # audience / azp fallback
    aud = payload.get("aud")
    aud_ok = False
    if isinstance(aud, str):
        aud_ok = aud in ALLOWED_AUDIENCES
    elif isinstance(aud, (list, tuple, set)):
        aud_ok = any(a in ALLOWED_AUDIENCES for a in aud)
    if not aud_ok:
        azp = payload.get("azp") or payload.get("client_id")
        if not azp or azp not in ALLOWED_AUDIENCES:
            raise ValueError(f"aud not allowed: {aud}")

    return payload

# ---- WS helpers --------------------------------------------------------------

from fastapi import WebSocket

def extract_bearer_or_query_token(websocket: WebSocket) -> Optional[str]:
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    token = websocket.query_params.get("token")
    if token:
        return token.strip()
    return None

def _truthy(v: Optional[str]) -> bool:
    if v is None:
        return False
    v = str(v).strip().strip('\'"').lower()
    return v in ("1", "true", "yes", "on")

def _allowed_origins_set() -> set[str]:
    raw = (os.getenv("ALLOWED_ORIGIN", "") or "").strip().strip('\'"')
    return {o.strip() for o in raw.split(",") if o.strip()}

def check_origin_allowed(origin: Optional[str]) -> Tuple[bool, str]:
    if _truthy(os.getenv("ALLOW_WS_ORIGIN_ANY", "0")):
        return True, "ALLOW_WS_ORIGIN_ANY=1"
    if not origin and not _truthy(os.getenv("WS_REQUIRE_ORIGIN", "0")):
        return True, "no Origin header (allowed)"
    if not origin:
        return False, "missing Origin header"
    allowed = _allowed_origins_set()
    if not allowed:
        return False, "ALLOWED_ORIGIN not configured"
    if "*" in allowed or "any" in allowed:
        return True, "ALLOWED_ORIGIN=*"
    if origin in allowed:
        return True, "origin ok"
    return False, f"origin '{origin}' not in {sorted(allowed)}"

def token_allows_origin(payload: dict, origin: Optional[str]) -> Tuple[bool, str]:
    if not _truthy(os.getenv("WS_ENFORCE_TOKEN_ORIGIN", "0")):
        return True, "token-origin check disabled"
    if not origin:
        return True, "skip claim check (no origin)"
    claim = payload.get("allowed-origins")
    if not claim:
        return True, "no allowed-origins claim; skipping"
    if isinstance(claim, list) and origin in claim:
        return True, "allowed-origins claim ok"
    return False, f"origin '{origin}' not in token allowed-origins"

def verify_token_or_raise(token: str) -> dict:
    try:
        return _verify_rs256(token)
    except Exception as e:
        logger.warning("JWT verify failed: %s", e)
        raise

async def guard_websocket(websocket: WebSocket) -> dict:
    origin = websocket.headers.get("origin")

    ok, _ = check_origin_allowed(origin)
    if not ok:
        await websocket.close(code=1008)
        raise RuntimeError("forbidden origin")

    token = extract_bearer_or_query_token(websocket)
    if not token:
        await websocket.close(code=1008)
        raise RuntimeError("missing bearer token")

    try:
        payload = verify_token_or_raise(token)
    except Exception:
        await websocket.close(code=1008)
        raise

    ok2, _ = token_allows_origin(payload, origin)
    if not ok2:
        await websocket.close(code=1008)
        raise RuntimeError("token origin mismatch")

    websocket.scope["user"] = payload
    return payload

```


## backend/app/api/v1/endpoints/__init__.py

```py

```


## backend/app/api/v1/endpoints/ai.py

```py
# backend/app/api/v1/endpoints/ai.py
from __future__ import annotations

import os
import re
import json
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState
from pydantic import BaseModel, Field
from redis import Redis

# Nur die Consult-Funktion nutzen; Checkpointer wird im Consult-Modul intern gehandhabt.
from app.services.langgraph.graph.consult.io import invoke_consult as _invoke_consult

log = logging.getLogger("uvicorn.error")

# ─────────────────────────────────────────────────────────────
# ENV / Redis STM (Short-Term Memory)
# ─────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STM_PREFIX = os.getenv("STM_PREFIX", "chat:stm")
STM_TTL_SEC = int(os.getenv("STM_TTL_SEC", "604800"))  # 7 Tage
WS_AUTH_OPTIONAL = os.getenv("WS_AUTH_OPTIONAL", "1") == "1"

def _stm_key(thread_id: str) -> str:
    return f"{STM_PREFIX}:{thread_id}"

def _get_redis() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)

def _set_stm(thread_id: str, key: str, value: str) -> None:
    r = _get_redis()
    skey = _stm_key(thread_id)
    r.hset(skey, key, value)
    r.expire(skey, STM_TTL_SEC)

def _get_stm(thread_id: str, key: str) -> Optional[str]:
    r = _get_redis()
    skey = _stm_key(thread_id)
    v = r.hget(skey, key)
    return v if (isinstance(v, str) and v.strip()) else None

# ─────────────────────────────────────────────────────────────
# Intent: “merke dir … / remember …” (optional)
# ─────────────────────────────────────────────────────────────
RE_REMEMBER_NUM  = re.compile(r"\b(merke\s*dir|merk\s*dir|remember)\b[^0-9\-+]*?(-?\d+(?:[.,]\d+)?)", re.I)
RE_REMEMBER_FREE = re.compile(r"\b(merke\s*dir|merk\s*dir|remember)\b[:\s]+(.+)$", re.I)
RE_ASK_NUMBER    = re.compile(r"\b(welche\s+zahl\s+meinte\s+ich|what\s+number\s+did\s+i\s+mean)\b", re.I)
RE_ASK_FREE      = re.compile(r"\b(woran\s+erinn?erst\s+du\s+dich|what\s+did\s+you\s+remember)\b", re.I)

def _normalize_num_str(s: str) -> str:
    return (s or "").replace(",", ".")

def _maybe_handle_memory_intent(text: str, thread_id: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None

    m = RE_REMEMBER_NUM.search(t)
    if m:
        raw = m.group(2)
        norm = _normalize_num_str(raw)
        _set_stm(thread_id, "last_number", norm)
        return f"Alles klar – ich habe mir **{raw}** gemerkt."

    m2 = RE_REMEMBER_FREE.search(t)
    if m2 and not m:
        val = (m2.group(2) or "").strip()
        if val:
            _set_stm(thread_id, "last_note", val)
            return "Notiert. 👍"

    if RE_ASK_NUMBER.search(t):
        v = _get_stm(thread_id, "last_number")
        return f"Du meintest **{v}**." if v else "Ich habe dazu noch keine Zahl gespeichert."

    if RE_ASK_FREE.search(t):
        v = _get_stm(thread_id, "last_note")
        return f"Ich habe mir gemerkt: “{v}”." if v else "Ich habe dazu noch nichts gespeichert."

    return None

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _extract_text_from_consult_out(out: Dict[str, Any]) -> str:
    # 1) letzte Assistant-Message
    msgs = out.get("messages") or []
    if msgs:
        last = msgs[-1]
        # LangChain-Objekt oder dict
        content = getattr(last, "content", None)
        if isinstance(last, dict):
            content = last.get("content", content)
        if isinstance(content, str) and content.strip():
            return content.strip()
    # 2) strukturierte Felder (JSON/Explain)
    for k in ("answer", "explanation", "text", "response"):
        v = out.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "OK."

# ─────────────────────────────────────────────────────────────
# API (HTTP)
# ─────────────────────────────────────────────────────────────
router = APIRouter()  # KEIN prefix hier – der übergeordnete Router hängt '/ai' an.

class ChatRequest(BaseModel):
    chat_id: str = Field(default="default", description="Konversations-ID")
    input_text: str = Field(..., description="Nutzertext")

class ChatResponse(BaseModel):
    text: str

@router.post("/beratung", response_model=ChatResponse)
async def beratung(request: Request, payload: ChatRequest) -> ChatResponse:
    """
    Einstieg in den Consult-Flow.
    """
    user_text = (payload.input_text or "").strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="input_text empty")

    thread_id = f"api:{payload.chat_id}"

    # 1) Memory-Intents kurz-circuited beantworten
    mem = _maybe_handle_memory_intent(user_text, thread_id)
    if mem:
        return ChatResponse(text=mem)

    # 2) Consult-Flow korrekt mit State aufrufen
    state = {
        "messages": [{"role": "user", "content": user_text}],
        "input": user_text,
        "chat_id": thread_id,
    }
    try:
        out = _invoke_consult(state)  # returns dict-like ConsultState
    except Exception as e:
        log.exception("consult invoke failed: %r", e)
        raise HTTPException(status_code=500, detail="consult_failed")

    return ChatResponse(text=_extract_text_from_consult_out(out))

# ─────────────────────────────────────────────────────────────
# API (WebSocket) – zuerst accept(), dann prüfen/antworten
# ─────────────────────────────────────────────────────────────
@router.websocket("/ws")
@router.websocket("/chat/ws")
@router.websocket("/v1/ws")
@router.websocket("/ws_chat")   # Backwards-compat
@router.websocket("/api/v1/ai/ws")  # aktueller Pfad im Frontend
async def chat_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    Robuster WS-Handler:
      - Erst 'accept()', dann (optionale) Token/Origin-Prüfung
      - Erwartet Textframes mit JSON wie: {"chat_id":"default","input":"hallo","mode":"graph"}
    """
    await websocket.accept()

    try:
        if not WS_AUTH_OPTIONAL and not token:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_text('{"error":"unauthorized"}')
            await websocket.close(code=1008)
            return

        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
            except Exception:
                data = {"input": msg}

            if isinstance(data, dict) and data.get("type") == "ping":
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text('{"type":"pong"}')
                continue

            chat_id = (data.get("chat_id") or "default") if isinstance(data, dict) else "default"
            user_input = (data.get("input") or "").strip() if isinstance(data, dict) else str(data)
            thread_id = f"api:{chat_id}"

            if not user_input:
                continue

            mem = _maybe_handle_memory_intent(user_input, thread_id)
            if mem:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text(json.dumps({"event": "final", "text": mem}))
                continue

            # Consult-Flow korrekt mit State aufrufen
            state = {
                "messages": [{"role": "user", "content": user_input}],
                "input": user_input,
                "chat_id": thread_id,
            }
            try:
                out = _invoke_consult(state)
                out_text = _extract_text_from_consult_out(out)
            except Exception as e:
                log.exception("consult error: %r", e)
                out_text = "Entschuldige, da ist gerade ein Fehler passiert."

            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_text(json.dumps({"event": "final", "text": out_text}))

    except WebSocketDisconnect:
        log.info("ws: client disconnected")
    except Exception as e:
        log.exception("ws_chat error: %r", e)
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.send_text('{"error":"internal"}')
                await websocket.close(code=1011)
        except Exception:
            pass

```


## backend/app/api/v1/endpoints/auth.py

```py
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

router = APIRouter()

@router.get("/login", tags=["Auth"])
def login_redirect():
    """
    Leitet den Benutzer zum Keycloak-Login weiter.
    Die Parameter müssen mit der Konfiguration deines Keycloak-Clients übereinstimmen.
    """
    keycloak_base_url = "https://auth.sealai.net/realms/sealAI/protocol/openid-connect/auth"
    # Ersetze diese Werte mit deinen konfigurierten Angaben:
    client_id = "nextauth"  # oder "sealai-backend", je nachdem, was du in Keycloak als Client definiert hast
    redirect_uri = "https://sealai.net/api/auth/callback/keycloak"  # muss zu deinen Keycloak-Redirect-URIs passen
    response_type = "code"
    scope = "openid"

    params = {
        "client_id": client_id,
        "response_type": response_type,
        "redirect_uri": redirect_uri,
        "scope": scope
    }

    # Erzeuge die vollständige URL
    url = f"{keycloak_base_url}?{urlencode(params)}"
    return RedirectResponse(url)

```


## backend/app/api/v1/endpoints/chat_ws.py

```py
# backend/app/api/v1/endpoints/chat_ws.py
from __future__ import annotations

import os
import re
import json
import asyncio
from typing import Any, Dict, Iterable, List, Optional, Tuple
import redis

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages.ai import AIMessageChunk

# # from app.api.v1.dependencies.auth import guard_websocket  # disabled for WS  # WS auth disabled here
from app.services.langgraph.llm_factory import get_llm as make_llm
from app.services.langgraph.redis_lifespan import get_redis_checkpointer
from app.services.langgraph.prompt_registry import get_agent_prompt
from app.services.langgraph.graph.consult.memory_utils import (
    read_history as stm_read_history,
    write_message as stm_write_message,
)
from app.services.langgraph.tools import long_term_memory as ltm

router = APIRouter()

# --- Tunables / Env (engere Defaults für mehr Tempo) ---
COALESCE_MIN_CHARS      = int(os.getenv("WS_COALESCE_MIN_CHARS", "24"))
COALESCE_MAX_LAT_MS     = float(os.getenv("WS_COALESCE_MAX_LAT_MS", "40"))
IDLE_TIMEOUT_SEC        = int(os.getenv("WS_IDLE_TIMEOUT_SEC", "45"))  # 45s, Client heartbeat < 45s
FIRST_TOKEN_TIMEOUT_MS  = int(os.getenv("WS_FIRST_TOKEN_TIMEOUT_MS", "2000"))
WS_INPUT_MAX_CHARS      = int(os.getenv("WS_INPUT_MAX_CHARS", "4000"))
WS_RATE_LIMIT_PER_MIN   = int(os.getenv("WS_RATE_LIMIT_PER_MIN", "30"))
MICRO_CHUNK_CHARS       = int(os.getenv("WS_MICRO_CHUNK_CHARS", "0"))
EMIT_FINAL_TEXT         = os.getenv("WS_EMIT_FINAL_TEXT", "0") == "1"
DEBUG_EVENTS            = os.getenv("WS_DEBUG_EVENTS", "1") == "1"
WS_EVENT_TIMEOUT_SEC    = int(os.getenv("WS_EVENT_TIMEOUT_SEC", "25"))
FORCE_SYNC_FALLBACK     = os.getenv("WS_FORCE_SYNC", "0") == "1"

FLUSH_ENDINGS: Tuple[str, ...] = (". ", "? ", "! ", "\n\n", ":", ";", "…", ", ", ") ", "] ", " }")

def _env_stream_nodes() -> set[str]:
    raw = os.getenv("WS_STREAM_NODES", "*").strip()
    if not raw or raw in {"*", "all"}:
        return {"*"}
    return {x.strip().lower() for x in raw.split(",") if x.strip()}

STREAM_NODES = _env_stream_nodes()
GRAPH_BUILDER = os.getenv("GRAPH_BUILDER", "supervisor").lower()

def _log(msg: str, **extra):
    try:
        if extra:
            print(f"[ws] {msg} " + json.dumps(extra, ensure_ascii=False, default=str))
        else:
            print(f"[ws] {msg}")
    except Exception:
        try: print(f"[ws] {msg} {extra}")
        except Exception: pass

def _get_rl_redis(app) -> Optional[redis.Redis]:
    client = getattr(app.state, "redis_rl", None)
    if client is not None:
        return client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        app.state.redis_rl = client
        return client
    except Exception:
        return None

def _piece_from_llm_chunk(chunk: Any) -> Optional[str]:
    if isinstance(chunk, AIMessageChunk):
        return chunk.content or ""
    txt = getattr(chunk, "content", None)
    if isinstance(txt, str) and txt:
        return txt
    ak = getattr(chunk, "additional_kwargs", None)
    if isinstance(ak, dict):
        for k in ("delta", "content", "text", "token"):
            v = ak.get(k)
            if isinstance(v, str) and v:
                return v
    if isinstance(chunk, dict):
        for k in ("delta", "content", "text", "token"):
            v = chunk.get(k)
            if isinstance(v, str) and v:
                return v
    return None

def _iter_text_from_chunk(chunk) -> Iterable[str]:
    if isinstance(chunk, dict):
        c = chunk.get("content")
        if isinstance(c, str) and c:
            yield c; return
        d = chunk.get("delta")
        if isinstance(d, str) and d:
            yield d; return
    content = getattr(chunk, "content", None)
    if isinstance(content, str) and content:
        yield content; return
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                yield part
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                yield part["text"]
    ak = getattr(chunk, "additional_kwargs", None)
    if isinstance(ak, dict):
        for k in ("delta", "content", "text", "token"):
            v = ak.get(k)
            if isinstance(v, str) and v:
                yield v

_BOUNDARY_RX = re.compile(r"[ \n\t.,;:!?…)\]}]")

def _micro_chunks(s: str) -> Iterable[str]:
    n = MICRO_CHUNK_CHARS
    if n <= 0 or len(s) <= n:
        yield s; return
    i = 0; L = len(s)
    while i < L:
        j = min(i + n, L); k = j
        if j < L:
            m = _BOUNDARY_RX.search(s, j, min(L, j + 40))
            if m: k = m.end()
        yield s[i:k]; i = k

def _is_relevant_node(ev: Dict) -> bool:
    if "*" in STREAM_NODES or "all" in STREAM_NODES:
        return True
    meta = ev.get("metadata") or {}; run  = ev.get("run") or {}
    node = str(meta.get("langgraph_node") or "").lower()
    run_name = str(run.get("name") or meta.get("run_name") or "").lower()
    return (node in STREAM_NODES) or (run_name in STREAM_NODES)

def _extract_texts(obj: Any) -> List[str]:
    out: List[str] = []
    if isinstance(obj, str) and obj.strip():
        out.append(obj.strip()); return out
    if isinstance(obj, dict):
        for k in ("response", "final_text", "text", "answer"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        msgs = obj.get("messages")
        if isinstance(msgs, list):
            for m in msgs:
                if isinstance(m, AIMessage):
                    c = getattr(m, "content", "")
                    if isinstance(c, str) and c.strip():
                        out.append(c.strip())
                elif isinstance(m, dict):
                    c = m.get("content")
                    if isinstance(c, str) and c.strip():
                        out.append(c.strip())
        for k in ("output", "state", "final_state", "result"):
            sub = obj.get(k)
            out.extend(_extract_texts(sub))
    elif isinstance(obj, list):
        for it in obj:
            out.extend(_extract_texts(it))
    return out

def _last_ai_text_from_result_like(obj: Dict[str, Any]) -> str:
    texts = _extract_texts(obj)
    return texts[-1].strip() if texts else ""

REMEMBER_RX = re.compile(r"^\s*(?:!remember|remember|merke(?:\s*dir)?|speicher(?:e)?)\s*[:\-]?\s*(.+)$", re.I)
GREETING_RX = re.compile(r"^(hi|hallo|hello|hey|moin)\b", re.I)

def _ensure_graph(app, builder_name: str | None = None) -> None:
    # Cache pro Graph-Name
    want = (builder_name or GRAPH_BUILDER).lower().strip() or "supervisor"
    if getattr(app.state, "graph_name", None) == want and (
        getattr(app.state, "graph_async", None) is not None or getattr(app.state, "graph_sync", None) is not None
    ):
        return

    if want == "supervisor":
        from app.services.langgraph.supervisor_graph import build_supervisor_graph as build_graph
    else:
        from app.services.langgraph.graph.consult.build import build_consult_graph as build_graph

    saver = None
    try:
        saver = get_redis_checkpointer(app)
    except Exception:
        saver = None

    g = build_graph()
    try:
        compiled = g.compile(checkpointer=saver) if saver else g.compile()
    except Exception:
        compiled = g.compile()

    app.state.graph_async = compiled
    app.state.graph_sync  = compiled
    app.state.graph_name  = want


def _choose_subprotocol(ws: WebSocket) -> Optional[str]:
    raw = ws.headers.get("sec-websocket-protocol")
    if not raw:
        return None
    return raw.split(",")[0].strip() or None

async def _send_json_safe(ws: WebSocket, payload: Dict) -> bool:
    try:
        await ws.send_json(payload); return True
    except WebSocketDisconnect:
        return False
    except Exception:
        return False

def _get_token(ws: WebSocket) -> Optional[str]:
    auth = ws.headers.get("authorization") or ws.headers.get("Authorization")
    if auth:
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    try:
        q = ws.query_params.get("token")
        if q:
            return q
    except Exception:
        pass
    return None

# ------------------- Streaming helpers -------------------

async def _send_typing_stub(ws: WebSocket, thread_id: str):
    await _send_json_safe(ws, {"event": "typing", "thread_id": thread_id})

async def _stream_llm_direct(ws: WebSocket, llm, *, user_input: str, thread_id: str):
    def cancelled() -> bool:
        flags = getattr(ws.app.state, "ws_cancel_flags", {})
        return bool(flags.get(thread_id))

    history = stm_read_history(thread_id, limit=80)
    if cancelled():
        return

    loop = asyncio.get_event_loop()
    buf: List[str] = []; accum: List[str] = []; last_flush = [loop.time()]

    async def flush():
        if not buf or cancelled():
            return
        chunk = "".join(buf); buf.clear(); last_flush[0] = loop.time()
        accum.append(chunk)
        await _send_json_safe(ws, {"event": "token", "delta": chunk, "thread_id": thread_id})

    sys_msg = SystemMessage(content=get_agent_prompt("supervisor"))
    await _send_typing_stub(ws, thread_id)

    agen = llm.astream([sys_msg] + history + [HumanMessage(content=user_input)])
    try:
        first = await asyncio.wait_for(agen.__anext__(), timeout=FIRST_TOKEN_TIMEOUT_MS / 1000.0)
    except asyncio.TimeoutError:
        try:
            if not cancelled():
                resp = await llm.ainvoke([sys_msg] + history + [HumanMessage(content=user_input)])
                text = getattr(resp, "content", "") or ""
            else:
                text = ""
        except Exception:
            text = ""
        try: await agen.aclose()
        except Exception: pass
        if text and not cancelled():
            await _send_json_safe(ws, {"event": "token", "delta": text, "thread_id": thread_id})
            try: stm_write_message(thread_id=thread_id, role="assistant", content=text)
            except Exception: pass
        if EMIT_FINAL_TEXT and not cancelled():
            await _send_json_safe(ws, {"event": "final", "text": text, "thread_id": thread_id})
        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
        return
    except Exception:
        try: await agen.aclose()
        except Exception: pass
        return

    if cancelled():
        try: await agen.aclose()
        except Exception: pass
        return

    txt = (_piece_from_llm_chunk(first) or "")
    if txt and not cancelled():
        for seg in _micro_chunks(txt):
            buf.append(seg); await flush()

    try:
        async for chunk in agen:
            if cancelled(): break
            for piece in _iter_text_from_chunk(chunk):
                if not piece or cancelled(): continue
                for seg in _micro_chunks(piece):
                    buf.append(seg)
                    enough  = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                    natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                    too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                    if enough or natural or too_old:
                        await flush()
        await flush()
    finally:
        try: await agen.aclose()
        except Exception: pass

    if cancelled():
        return

    final_text = ("".join(accum)).strip()
    if final_text:
        try: stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
        except Exception: pass
    if EMIT_FINAL_TEXT:
        await _send_json_safe(ws, {"event": "final", "text": final_text, "thread_id": thread_id})
    await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})

async def _stream_supervised(ws: WebSocket, *, app, user_input: str, thread_id: str, params_patch: Optional[Dict]=None, builder_name: str | None = None):
    def cancelled() -> bool:
        flags = getattr(ws.app.state, "ws_cancel_flags", {})
        return bool(flags.get(thread_id))

    if cancelled():
        return

    try:
        _ensure_graph(app, builder_name=builder_name)
    except Exception as e:
        if EMIT_FINAL_TEXT and not cancelled():
            await _send_json_safe(ws, {"event": "final", "text": "", "thread_id": thread_id, "error": f"graph_build_failed: {e!r}"})
        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
        return

    g_async = getattr(app.state, "graph_async", None)
    g_sync  = getattr(app.state, "graph_sync", None)

    _log("graph_ready", builder=GRAPH_BUILDER, has_async=bool(g_async), has_sync=bool(g_sync))

    history = stm_read_history(thread_id, limit=80)
    sys_msg = SystemMessage(content=get_agent_prompt("supervisor"))

    base_msgs: List[Any] = [sys_msg] + history
    if user_input:
        base_msgs.append(HumanMessage(content=user_input))

    initial: Dict[str, Any] = {
        "messages": base_msgs,
        "chat_id": thread_id,
        "input": user_input,
    }
    if isinstance(params_patch, dict) and params_patch:
        initial["params"] = params_patch

    cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": getattr(app.state, "checkpoint_ns", None)}}

    loop = asyncio.get_event_loop()
    buf: List[str] = []; last_flush = [loop.time()]; streamed_any = False
    final_tail: str = ""; accum: List[str] = []

    async def flush():
        nonlocal streamed_any
        if not buf or cancelled(): return
        chunk = "".join(buf); buf.clear(); last_flush[0] = loop.time()
        streamed_any = True; accum.append(chunk)
        if not await _send_json_safe(ws, {"event": "token", "delta": chunk, "thread_id": thread_id}):
            raise WebSocketDisconnect()

    def _emit_ui_event_if_any(ev_data: Any) -> bool:
        if not isinstance(ev_data, dict):
            return False
        ui_ev = ev_data.get("ui_event")
        if isinstance(ui_ev, dict):
            payload = {**ui_ev, "event": "ui_action", "thread_id": thread_id}
            _log("emit_ui_event", payload=payload)
            return asyncio.create_task(_send_json_safe(ws, payload)) is not None
        for key in ("output", "state", "final_state", "result"):
            sub = ev_data.get(key)
            if isinstance(sub, dict) and isinstance(sub.get("ui_event"), dict):
                u = {**sub["ui_event"], "event": "ui_action", "thread_id": thread_id}
                _log("emit_ui_event_nested", payload=u)
                return asyncio.create_task(_send_json_safe(ws, u)) is not None
        return False

    def _maybe_emit_ask_missing_fallback(ev_data: Any) -> bool:
        try:
            meta = (ev_data or {}).get("metadata") or {}
            node = str(meta.get("langgraph_node") or meta.get("node") or "").lower()
        except Exception:
            node = ""
        out = (ev_data or {}).get("output") or ev_data or {}
        phase = str(out.get("phase") or "").lower()
        if node == "ask_missing" or phase == "ask_missing":
            payload = {
                "event": "ui_action",
                "ui_action": "open_form",
                "thread_id": thread_id,
                "source": "ws_fallback"
            }
            _log("emit_ui_event_fallback", node=node, phase=phase, payload=payload)
            asyncio.create_task(_send_json_safe(ws, payload))
            return True
        return False

    def _try_stream_text_from_node(data: Any) -> None:
        texts = _extract_texts(data)
        if not texts: return
        joined = "\n".join([t for t in texts if isinstance(t, str)])
        for seg in _micro_chunks(joined):
            buf.append(seg)

    await _send_typing_stub(ws, thread_id)

    async def _run_stream(version: str):
        nonlocal final_tail
        async for ev in g_async.astream_events(initial, config=cfg, version=version):  # type: ignore
            if cancelled(): return
            ev_name = ev.get("event") if isinstance(ev, dict) else None
            data = ev.get("data") if isinstance(ev, dict) else None
            meta = ev.get("metadata") if isinstance(ev, dict) else None
            node_name = ""
            try:
                if isinstance(meta, dict):
                    node_name = str(meta.get("langgraph_node") or meta.get("node") or "")
            except Exception:
                node_name = ""

            if DEBUG_EVENTS and ev_name in ("on_node_start", "on_node_end"):
                _log("node_event", event=ev_name, node=node_name)

            if isinstance(data, dict) and str(data.get("type") or "").lower() == "stream_text":
                text_piece = data.get("text")
                if isinstance(text_piece, str) and text_piece:
                    for seg in _micro_chunks(text_piece):
                        buf.append(seg)
                        enough  = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                        natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                        too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                        if enough or natural or too_old:
                            await flush()
                    await flush()
                continue

            if ev_name in ("on_chat_model_stream", "on_llm_stream") and _is_relevant_node(ev):
                chunk = (data or {}).get("chunk") if isinstance(data, dict) else None
                if chunk:
                    for piece in _iter_text_from_chunk(chunk):
                        if not piece or cancelled(): continue
                        for seg in _micro_chunks(piece):
                            buf.append(seg)
                            enough  = sum(len(x) for x in buf) >= COALESCE_MIN_CHARS
                            natural = any("".join(buf).endswith(e) for e in FLUSH_ENDINGS)
                            too_old = (loop.time() - last_flush[0]) * 1000.0 >= COALESCE_MAX_LAT_MS
                            if enough or natural or too_old:
                                await flush()

            if ev_name in ("on_node_end",):
                if isinstance(data, dict):
                    _try_stream_text_from_node(data.get("output") or data)
                await flush()
                emitted = _emit_ui_event_if_any(data)
                if not emitted:
                    _maybe_emit_ask_missing_fallback(data)

            if ev_name in ("on_chain_end", "on_graph_end"):
                if isinstance(data, dict):
                    _emit_ui_event_if_any(data)
                    final_tail = _last_ai_text_from_result_like(data) or final_tail

        await flush()

    timed_out = False
    if FORCE_SYNC_FALLBACK:
        timed_out = True
    elif g_async is not None and not cancelled():
        try:
            await asyncio.wait_for(_run_stream("v2"), timeout=WS_EVENT_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            timed_out = True
        except Exception:
            try:
                await asyncio.wait_for(_run_stream("v1"), timeout=WS_EVENT_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                timed_out = True
            except Exception:
                pass

    if cancelled():
        return

    assistant_text: str = ""
    if final_tail:
        if not streamed_any:
            accum.append(final_tail)
        assistant_text = final_tail
    elif (not streamed_any) or timed_out:
        try:
            result = None
            if g_sync is not None:
                def _run_sync(): return g_sync.invoke(initial, config=cfg)
                result = await asyncio.get_event_loop().run_in_executor(None, _run_sync)
            elif g_async is not None:
                result = await g_async.ainvoke(initial, config=cfg)  # type: ignore

            if isinstance(result, dict):
                emitted = _emit_ui_event_if_any(result)
                if not emitted:
                    _maybe_emit_ask_missing_fallback(result)

            final_text = _last_ai_text_from_result_like(result or {}) or ""
            assistant_text = final_text
            if final_text:
                accum.append(final_text)
        except Exception:
            assistant_text = ""
        if not assistant_text:
            try:
                llm = getattr(app.state, "llm", make_llm(streaming=False))
                resp = await llm.ainvoke([SystemMessage(content=get_agent_prompt("supervisor"))] + history + [HumanMessage(content=user_input)])
                assistant_text = (getattr(resp, "content", "") or "").strip()
            except Exception:
                assistant_text = ""
    else:
        assistant_text = "".join(accum)

    if cancelled():
        return

    final_text = (assistant_text or "".join(accum)).strip()

    already = "".join(accum).strip()
    if final_text and (not already or already != final_text):
        if not await _send_json_safe(ws, {"event": "token", "delta": final_text, "thread_id": thread_id}):
            return

    try:
        if final_text:
            stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
    except Exception:
        pass

    if EMIT_FINAL_TEXT:
        await _send_json_safe(ws, {"event": "final", "text": final_text, "thread_id": thread_id})
    await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})

# ------------------- WebSocket endpoint -------------------
@router.websocket("/ai/ws")
async def ws_chat(ws: WebSocket):
    # Einmaliger, toleranter Handshake inkl. Subprotocol
    await ws.accept(subprotocol=_choose_subprotocol(ws))
    """
    Robuster Handshake & tolerante Auth:
    """

    # Soft-Auth (Keycloak optional); bei Fehler anonym/bearer setzen
    user_payload: Dict[str, Any] = {}
    try:
        # guard_websocket ist ggf. nicht importiert → NameError wird unten abgefangen
        user_payload = await guard_websocket(ws)  # type: ignore[name-defined]
    except Exception:
        token = _get_token(ws)
        user_payload = {"sub": "anonymous"} if not token else {"sub": "bearer"}

    try:
        ws.scope["user"] = user_payload
    except Exception:
        pass

    # Lazy-Init shared state
    app = ws.app
    if not getattr(app.state, "llm", None):
        app.state.llm = make_llm(streaming=True)
    try:
        ltm.prewarm_ltm()
    except Exception:
        pass
    if not hasattr(app.state, "ws_cancel_flags"):
        app.state.ws_cancel_flags = {}

    try:
        while True:
            # Heartbeat/Idle
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=IDLE_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                await _send_json_safe(ws, {"event": "idle", "ts": int(asyncio.get_event_loop().time())})
                continue

            # Parsen
            try:
                short = raw if len(raw) < 256 else raw[:252] + "...}"
                _log("RX_raw", raw=short)
            except Exception:
                pass

            if isinstance(raw, str) and WS_INPUT_MAX_CHARS > 0 and len(raw) > (WS_INPUT_MAX_CHARS * 2):
                await _send_json_safe(ws, {
                    "event": "error",
                    "code": "input_oversize",
                    "message": f"payload too large (>{WS_INPUT_MAX_CHARS*2} chars)",
                })
                await _send_json_safe(ws, {"event": "done", "thread_id": "ws"})
                continue

            try:
                data = json.loads(raw)
            except Exception:
                await _send_json_safe(ws, {"event": "error", "message": "invalid_json"})
                continue

            # Control-Messages
            typ = (data.get("type") or "").strip().lower()
            if typ == "ping":
                await _send_json_safe(ws, {"event": "pong", "ts": data.get("ts")})
                continue
            if typ == "cancel":
                tid = (data.get("thread_id") or f"api:{(data.get('chat_id') or 'default').strip()}").strip()
                ws.app.state.ws_cancel_flags[tid] = True
                await _send_json_safe(ws, {"event": "done", "thread_id": tid})
                continue

            # Kontext / Limits
            chat_id   = (data.get("chat_id") or "").strip() or "default"
            thread_id = f"api:{chat_id}"
            payload   = ws.scope.get("user") or {}
            user_id   = str(payload.get("sub") or payload.get("email") or chat_id)

            rl = _get_rl_redis(app)
            if rl and WS_RATE_LIMIT_PER_MIN > 0:
                key = f"ws:ratelimit:{user_id}:{chat_id}"
                try:
                    cur = rl.incr(key)
                    if cur == 1:
                        rl.expire(key, 60)
                    if cur > WS_RATE_LIMIT_PER_MIN:
                        await _send_json_safe(ws, {
                            "event": "error",
                            "code": "rate_limited",
                            "message": "Too many requests, slow down.",
                            "retry_after_sec": int(rl.ttl(key) or 60)
                        })
                        await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                        continue
                except Exception:
                    pass

            params_patch = data.get("params") or data.get("params_patch")
            if not isinstance(params_patch, dict):
                params_patch = None

            user_input = (data.get("input") or data.get("text") or data.get("query") or "").strip()
            if user_input and WS_INPUT_MAX_CHARS > 0 and len(user_input) > WS_INPUT_MAX_CHARS:
                await _send_json_safe(ws, {
                    "event": "error",
                    "code": "input_too_long",
                    "message": f"input exceeds {WS_INPUT_MAX_CHARS} chars"
                })
                await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                continue

            if not user_input and not params_patch:
                await _send_json_safe(ws, {"event": "error", "message": "missing_input", "thread_id": thread_id})
                continue

            try:
                app.state.ws_cancel_flags.pop(thread_id, None)
            except Exception:
                pass

            if user_input:
                try:
                    stm_write_message(thread_id=thread_id, role="user", content=user_input)
                except Exception:
                    pass

            # Kurzbefehl "remember ..."
            m = REMEMBER_RX.match(user_input or "")
            if m:
                note = m.group(1).strip()
                ok = False
                try:
                    _ = ltm.upsert_memory(user=thread_id, chat_id=thread_id, text=note, kind="note")
                    ok = True
                except Exception:
                    ok = False
                msg = "✅ Gespeichert." if ok else "⚠️ Konnte nicht speichern."
                await _send_json_safe(ws, {"event": "token", "delta": msg, "thread_id": thread_id})
                await _send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                try:
                    stm_write_message(thread_id=thread_id, role="assistant", content=msg)
                except Exception:
                    pass
                continue

            # Triviale Grüße → direkter LLM-Stream
            if user_input and not params_patch and GREETING_RX.match(user_input):
                llm = getattr(app.state, "llm", make_llm(streaming=True))
                await _stream_llm_direct(ws, llm, user_input=user_input, thread_id=thread_id)
                try:
                    app.state.ws_cancel_flags.pop(thread_id, None)
                except Exception:
                    pass
                continue

            # Start-Event + Routing
            mode = (data.get("mode") or os.getenv("WS_MODE", "graph")).strip().lower()
            graph_name = (data.get("graph") or os.getenv("GRAPH_BUILDER", "supervisor")).strip().lower()
            await _send_json_safe(ws, {"event": "start", "thread_id": thread_id, "route": mode, "graph": graph_name})

            # Stream ausführen
            if mode == "llm":
                llm = getattr(app.state, "llm", make_llm(streaming=True))
                await _stream_llm_direct(ws, llm, user_input=(user_input or ""), thread_id=thread_id)
            else:
                effective_input = user_input if user_input else ""
                _log("route", mode=mode, graph=graph_name, thread_id=thread_id, params_present=bool(params_patch), input_len=len(user_input))
                await _stream_supervised(
                    ws,
                    app=app,
                    user_input=effective_input,
                    thread_id=thread_id,
                    params_patch=params_patch,
                    builder_name=graph_name,
                )

            try:
                app.state.ws_cancel_flags.pop(thread_id, None)
            except Exception:
                pass

    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            print(f"[ws_chat] error: {e!r}")
        except Exception:
            pass
        await _send_json_safe(ws, {"event": "done", "thread_id": "ws"})

```


## backend/app/api/v1/endpoints/consult_invoke.py

```py
from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from app.services.langgraph.graph.consult.io import invoke_consult
from app.services.langgraph.redis_lifespan import get_redis_checkpointer

router = APIRouter(prefix="/test", tags=["test"])  # wird unter /api/v1 gemountet

class ConsultInvokeIn(BaseModel):
    text: str = Field(..., description="Nutzereingabe")
    chat_id: str = Field(..., description="Thread/Chat ID")

class ConsultInvokeOut(BaseModel):
    text: str

@router.post("/consult/invoke", response_model=ConsultInvokeOut)
async def consult_invoke_endpoint(payload: ConsultInvokeIn, request: Request):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text empty")

    chat_id = f"api:{payload.chat_id.strip() or 'test'}"
    try:
        saver = None
        try:
            saver = get_redis_checkpointer(request.app)
        except Exception:
            saver = None
        out = invoke_consult(text, thread_id=chat_id, checkpointer=saver)
        return {"text": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"invoke_failed: {e}")

```


## backend/app/api/v1/endpoints/langgraph_sse.py

```py
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncGenerator, Dict, Iterable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.langgraph.llm_factory import get_llm as make_llm
from app.services.langgraph.redis_lifespan import get_redis_checkpointer
from app.services.langgraph.prompt_registry import get_agent_prompt
from app.services.langgraph.graph.consult.memory_utils import (
    read_history as stm_read_history,
    write_message as stm_write_message,
)

router = APIRouter()

# Tunables
SSE_MIN_CHARS      = int(os.getenv("SSE_COALESCE_MIN_CHARS", "24"))
SSE_MAX_LAT_MS     = float(os.getenv("SSE_COALESCE_MAX_LAT_MS", "60"))
SSE_EVENT_TIMEOUT  = int(os.getenv("SSE_EVENT_TIMEOUT_SEC", "60"))
SSE_INPUT_MAX      = int(os.getenv("SSE_INPUT_MAX_CHARS", "4000"))
GRAPH_BUILDER      = os.getenv("GRAPH_BUILDER", "supervisor").lower()

# Helpers
def _iter_text_from_chunk(chunk: Any) -> Iterable[str]:
    if isinstance(chunk, dict):
        for k in ("content", "delta", "text", "token"):
            v = chunk.get(k)
            if isinstance(v, str) and v:
                yield v
    c = getattr(chunk, "content", None)
    if isinstance(c, str) and c:
        yield c
    if isinstance(c, list):
        for part in c:
            if isinstance(part, str) and part:
                yield part

def _last_ai_text_from_result_like(obj: Dict[str, Any]) -> str:
    def _collect(x: Any, out: list[str]):
        if isinstance(x, str) and x.strip():
            out.append(x.strip()); return
        if isinstance(x, dict):
            for k in ("response", "final_text", "text", "answer"):
                v = x.get(k)
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
            msgs = x.get("messages")
            if isinstance(msgs, list):
                for m in msgs:
                    if isinstance(m, dict):
                        c = m.get("content")
                        if isinstance(c, str) and c.strip():
                            out.append(c.strip())
            for k in ("output", "state", "final_state", "result"):
                _collect(x.get(k), out)
        elif isinstance(x, list):
            for it in x:
                _collect(it, out)
    tmp: list[str] = []
    _collect(obj, tmp)
    return tmp[-1].strip() if tmp else ""

def _build_graph(app):
    # Gleiche Logik wie WS: Supervisor bevorzugen, sonst Consult
    if GRAPH_BUILDER == "supervisor":
        from app.services.langgraph.supervisor_graph import build_supervisor_graph as build_graph
    else:
        from app.services.langgraph.graph.consult.build import build_consult_graph as build_graph
    saver = None
    try:
        saver = get_redis_checkpointer(app)
    except Exception:
        saver = None
    g = build_graph()
    try:
        return g.compile(checkpointer=saver) if saver else g.compile()
    except Exception:
        return g.compile()

def _sse(event: str, data: Any) -> bytes:
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")

@router.post("/chat/stream")
async def chat_stream(request: Request) -> StreamingResponse:
    """
    Input (JSON):
      { "chat_id": "default", "input_text": "..." }
    Output: text/event-stream mit Events: token, final, done
    """
    body = await request.json()
    chat_id   = (body.get("chat_id") or body.get("chatId") or "default").strip() or "default"
    user_text = (body.get("input_text") or body.get("input") or body.get("message") or "").strip()
    if not user_text:
        async def bad() -> AsyncGenerator[bytes, None]:
            yield _sse("error", {"error": "input_empty"}); yield _sse("done", {"done": True})
        return StreamingResponse(bad(), media_type="text/event-stream")
    if SSE_INPUT_MAX > 0 and len(user_text) > SSE_INPUT_MAX:
        async def too_long() -> AsyncGenerator[bytes, None]:
            yield _sse("error", {"error": f"input exceeds {SSE_INPUT_MAX} chars"}); yield _sse("done", {"done": True})
        return StreamingResponse(too_long(), media_type="text/event-stream")

    async def gen() -> AsyncGenerator[bytes, None]:
        app = request.app
        # LLM fallback für Notfälle bereitstellen
        if not getattr(app.state, "llm", None):
            app.state.llm = make_llm(streaming=True)

        # History
        thread_id = f"api:{chat_id}"
        history = stm_read_history(thread_id, limit=80)
        sys_msg = SystemMessage(content=get_agent_prompt("supervisor"))

        # Graph vorbereiten (wie WS)
        if not getattr(app.state, "graph_async", None):
            app.state.graph_async = _build_graph(app)
            app.state.graph_sync  = app.state.graph_async

        g_async = app.state.graph_async
        initial = {
            "messages": [sys_msg] + history + [HumanMessage(content=user_text)],
            "chat_id": thread_id,
            "input": user_text,
        }
        cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": getattr(app.state, "checkpoint_ns", None)}}

        loop = asyncio.get_event_loop()
        buf: list[str] = []
        last_flush = [loop.time()]
        accum: list[str] = []
        final_tail = ""

        async def flush():
            if not buf:
                return
            chunk = "".join(buf); buf.clear(); last_flush[0] = loop.time()
            accum.append(chunk)
            yield_bytes = _sse("token", {"delta": chunk})
            # yield innerhalb Hilfsfunktion geht nicht; zurückgeben
            return yield_bytes

        # Sofortiges Lebenszeichen
        yield _sse("token", {"delta": "…"})
        # Stream
        async def run_stream(version: str):
            nonlocal final_tail
            async for ev in g_async.astream_events(initial, config=cfg, version=version):  # type: ignore
                ev_name = ev.get("event"); data = ev.get("data")
                if ev_name in ("on_chat_model_stream", "on_llm_stream"):
                    chunk = (data or {}).get("chunk") if isinstance(data, dict) else None
                    if chunk:
                        for piece in _iter_text_from_chunk(chunk):
                            if not piece:
                                continue
                            buf.append(piece)
                            enough  = sum(len(x) for x in buf) >= SSE_MIN_CHARS
                            too_old = (loop.time() - last_flush[0]) * 1000.0 >= SSE_MAX_LAT_MS
                            if enough or too_old:
                                y = await flush()
                                if y: yield y
                if ev_name in ("on_node_end",):
                    y = await flush()
                    if y: yield y
                if ev_name in ("on_chain_end", "on_graph_end"):
                    if isinstance(data, dict):
                        final_tail = _last_ai_text_from_result_like(data) or final_tail
            y = await flush()
            if y: yield y

        timed_out = False
        try:
            async for y in asyncio.wait_for(run_stream("v2").__aiter__(), timeout=SSE_EVENT_TIMEOUT):  # type: ignore
                if y:
                    yield y
        except asyncio.TimeoutError:
            timed_out = True
        except Exception:
            # v1 Fallback
            try:
                async for y in asyncio.wait_for(run_stream("v1").__aiter__(), timeout=SSE_EVENT_TIMEOUT):  # type: ignore
                    if y:
                        yield y
            except Exception:
                pass

        final_text = final_tail or "".join(accum).strip()
        if not final_text:
            # Notfall: einmalig synchron antworten
            try:
                resp = await app.state.llm.ainvoke([sys_msg] + history + [HumanMessage(content=user_text)])
                final_text = (getattr(resp, "content", "") or "").strip()
            except Exception:
                final_text = ""
        if final_text:
            try: stm_write_message(thread_id=thread_id, role="assistant", content=final_text)
            except Exception: pass
        if final_text:
            yield _sse("final", {"final": {"text": final_text}})
        else:
            yield _sse("final", {"final": {"text": ""}})
        yield _sse("done", {"done": True})

    return StreamingResponse(gen(), media_type="text/event-stream")

```


## backend/app/api/v1/endpoints/memory.py

```py
# backend/app/api/v1/endpoints/memory.py
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient, models as qmodels

from app.core.config import settings
from app.services.auth.dependencies import get_current_request_user
from app.services.memory.memory_core import (
    ltm_export_all,
    ltm_delete_all,
    ensure_ltm_collection,
    _get_qdrant_client,
)

router = APIRouter(prefix="/memory", tags=["memory"])
logger = logging.getLogger(__name__)


def _ltm_collection() -> str:
    """Resolve the Qdrant collection name for LTM (Long-Term-Memory)."""
    return (settings.qdrant_collection_ltm or f"{settings.qdrant_collection}-ltm").strip()


# ----------------------------------------------------------------------
# Create Memory Item
# ----------------------------------------------------------------------
@router.post("", summary="Lege einen LTM-Eintrag in Qdrant an")
async def create_memory_item(
    payload: Dict[str, Any],
    username: str = Depends(get_current_request_user),
) -> JSONResponse:
    """
    Erwartet JSON:
    {
      "text": "…Pflicht…",
      "kind": "note|preference|fact|…",
      "chat_id": "optional"
    }
    """
    if not settings.ltm_enable:
        return JSONResponse({"ltm_enabled": False}, status_code=200)

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Field 'text' is required and must be non-empty")

    kind = (payload.get("kind") or "note").strip()
    chat_id = (payload.get("chat_id") or None) or None

    point_id = uuid.uuid4().hex
    q_payload: Dict[str, Any] = {
        "user": username,  # WICHTIG: Schlüssel = 'user' (wird für Filter verwendet!)
        "chat_id": chat_id,
        "kind": kind,
        "text": text,
        "created_at": time.time(),
    }
    # Zusatzfelder übernehmen (ohne Pflichtfelder zu überschreiben)
    for k, v in payload.items():
        if k not in q_payload:
            q_payload[k] = v

    try:
        client: QdrantClient = _get_qdrant_client()
        ensure_ltm_collection(client)

        # Dummy-Vektor, da nur Payload benötigt wird
        client.upsert(
            collection_name=_ltm_collection(),
            points=[
                qmodels.PointStruct(
                    id=point_id,
                    vector=[0.0],
                    payload=q_payload,
                )
            ],
            wait=True,
        )

        logger.info(f"[LTM] create_memory_item user={username} chat_id={chat_id} id={point_id}")
        return JSONResponse(
            {"id": point_id, "ltm_enabled": True, "success": True},
            status_code=200,
        )

    except Exception as exc:
        logger.exception(f"[LTM] Fehler beim Speichern für user={username}, chat_id={chat_id}: {exc}")
        raise HTTPException(status_code=500, detail="Speichern fehlgeschlagen") from exc


# ----------------------------------------------------------------------
# Export Memory Items
# ----------------------------------------------------------------------
@router.get("/export", summary="Exportiere Long-Term-Memory (Qdrant) des aktuellen Nutzers")
async def export_memory(
    chat_id: Optional[str] = Query(default=None, description="Optional: nur Einträge dieses Chats exportieren"),
    limit: int = Query(default=10000, ge=1, le=20000),
    username: str = Depends(get_current_request_user),
) -> JSONResponse:
    if not settings.ltm_enable:
        return JSONResponse({"items": [], "count": 0, "ltm_enabled": False}, status_code=200)

    try:
        items: List[Dict[str, Any]] = ltm_export_all(user=username, chat_id=chat_id, limit=limit)
        logger.info(f"[LTM] export_memory user={username} chat_id={chat_id} count={len(items)}")
        return JSONResponse(
            {"items": items, "count": len(items), "ltm_enabled": True, "success": True},
            status_code=200,
        )
    except Exception as exc:
        logger.exception(f"[LTM] Fehler beim Export für user={username}, chat_id={chat_id}: {exc}")
        raise HTTPException(status_code=500, detail="Export fehlgeschlagen") from exc


# ----------------------------------------------------------------------
# Delete Memory Items
# ----------------------------------------------------------------------
@router.delete("", summary="Lösche Long-Term-Memory des aktuellen Nutzers (optional pro Chat)")
async def delete_memory(
    chat_id: Optional[str] = Query(default=None, description="Optional: nur Einträge dieses Chats löschen"),
    username: str = Depends(get_current_request_user),
) -> JSONResponse:
    if not settings.ltm_enable:
        return JSONResponse({"deleted": 0, "ltm_enabled": False}, status_code=200)

    try:
        deleted = ltm_delete_all(user=username, chat_id=chat_id)
        logger.info(f"[LTM] delete_memory user={username} chat_id={chat_id} deleted={deleted}")
        return JSONResponse(
            {"deleted": deleted, "ltm_enabled": True, "success": True},
            status_code=200,
        )
    except Exception as exc:
        logger.exception(f"[LTM] Fehler beim Löschen für user={username}, chat_id={chat_id}: {exc}")
        raise HTTPException(status_code=500, detail="Löschen fehlgeschlagen") from exc

```


## backend/app/api/v1/endpoints/rfq.py

```py
from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter()

@router.get("/download")
def rfq_download(path: str = Query(..., description="Server-Pfad zur PDF")):
    if not os.path.isfile(path):
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(path, filename=os.path.basename(path), media_type="application/pdf")

```


## backend/app/api/v1/endpoints/system.py

```py
from __future__ import annotations

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request
import json

from app.services.langgraph.graph.consult.io import invoke_consult
from app.services.langgraph.redis_lifespan import get_redis_checkpointer

router = APIRouter()  # Prefix und Tags werden im übergeordneten Router gesetzt

class _ConsultInvokeIn(BaseModel):
    text: str = Field(..., min_length=1)
    chat_id: Optional[str] = None

@router.post("/test/consult/invoke", tags=["test"])
async def test_consult_invoke(body: _ConsultInvokeIn, request: Request) -> Dict[str, Any]:
    thread_id = f"api:{body.chat_id or 'test'}"
    try:
        saver = get_redis_checkpointer(request.app)
    except Exception:
        saver = None

    out = invoke_consult(body.text, thread_id=thread_id, checkpointer=saver)

    try:
        parsed = json.loads(out)
        payload = {"json": parsed} if isinstance(parsed, (dict, list)) else {"text": out}
    except Exception:
        payload = {"text": out}

    return {"final": payload}

```


## backend/app/api/v1/endpoints/users.py

```py
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/ping", summary="👥 User Ping", response_class=JSONResponse)
async def users_ping():
    return {"pong": True, "module": "users"}

```


## backend/app/api/v1/schemas/chat.py

```py
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime

class ChatRequest(BaseModel):
    chat_id: str
    input_text: str

class ChatResponse(BaseModel):
    response: str

# ───────────────────────────────────────────────────────
# Für den Beratungs-Workflow via /beratung
# ───────────────────────────────────────────────────────
class BeratungsRequest(BaseModel):
    frage: str
    chat_id: str

class BeratungsResponse(BaseModel):
    antworten: Dict[str, str]

class BeratungsverlaufResponse(BaseModel):
    id: int
    session_id: str
    frage: Optional[str]
    parameter: Optional[dict]
    antworten: Optional[List[str]]
    timestamp: datetime

```


## backend/app/api/v1/schemas/form.py

```py
from pydantic import BaseModel, Field
from datetime import datetime

class FormData(BaseModel):
    shaft_diameter: float = Field(..., description="Wellen-Ø in mm")
    housing_diameter: float = Field(..., description="Gehäuse-Ø in mm")

class FormResult(BaseModel):
    id: str
    username: str
    radial_clearance: float
    tolerance_fit: str
    result_text: str
    created_at: datetime

    class Config:
        from_attributes = True

```


## backend/app/core/config.py

```py
# backend/app/core/config.py
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import structlog

# Strukturiertes Logging (JSON)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

class Settings(BaseSettings):
    # Datenbank / SQLAlchemy
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    database_url: str
    debug_sql: bool = False

    # Neu: Postgres-Sync-URL (basierend auf database_url oder explizit)
    POSTGRES_SYNC_URL: str

    # OpenAI / LLM / LangChain
    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"

    # Embeddings
    embedding_model: str = "BAAI/bge-base-en-v1.5"

    # Qdrant (RAG & LTM)
    qdrant_url: str
    qdrant_collection: str
    qdrant_collection_ltm: Optional[str] = None
    qdrant_api_key: Optional[str] = None
    rag_k: int = 4
    qdrant_filter_metadata: Optional[dict] = None
    debug_qdrant: bool = False

    # Redis Memory & Sessions
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_url: str
    redis_db: int = 0
    redis_ttl: int = 60 * 60 * 24  # 24h

    # Explizite REDIS_URL (Fallback für andere Komponenten)
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth / Keycloak / NextAuth
    nextauth_url: str
    nextauth_secret: str
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_client_id: str
    keycloak_client_secret: str
    keycloak_expected_azp: str

    # LangChain Tracing etc.
    langchain_tracing_v2: bool = True
    langchain_endpoint: Optional[str] = "https://api.smith.langchain.com"
    langchain_api_key: Optional[str] = None
    langchain_project: Optional[str] = "sealai"

    # Feature-Flags
    ltm_enable: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Wichtig: nicht mehr aus ENV lesen.
    # Der Backend-Issuer entspricht immer dem Keycloak-Issuer.
    @property
    def backend_keycloak_issuer(self) -> str:
        return self.keycloak_issuer


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

```


## backend/app/database.py

```py
# 📁 backend/app/database.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
# Best Practice: Einzige Quelle für Einstellungen ist app.core.config
from app.core.config import settings

# SQLAlchemy Base
Base = declarative_base()

# Datenbank-URL aus Core-Config ziehen
DATABASE_URL = settings.database_url

# Engine mit optionalem SQL-Debug aus den Settings
engine = create_async_engine(
    DATABASE_URL,
    future=True,
    echo=settings.debug_sql,   # gibt SQL-Statements bei Bedarf aus
)

# Session-Factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# FastAPI-Dependency für DB-Sessions
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

```


## backend/app/main.py

```py
from __future__ import annotations

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.v1.api import api_router
from app.services.langgraph.graph.consult.build import build_consult_graph

# Bevorzugte LLM-Factory (nutzt das zentrale LLM für WS/SSE)
try:
    from app.services.langgraph.llm_factory import get_llm as _make_llm  # hat meist streaming=True
except Exception:  # Fallback nur, falls Modul nicht vorhanden
    _make_llm = None  # type: ignore

# Zweite Option: LLM-Factory aus der Consult-Config
try:
    from app.services.langgraph.graph.consult.config import create_llm as _create_llm_cfg
except Exception:
    _create_llm_cfg = None  # type: ignore

# RAG-Orchestrator für Warmup
try:
    from app.services.rag import rag_orchestrator as ro  # enthält prewarm(), hybrid_retrieve, …
except Exception:
    ro = None  # type: ignore

# ---- Access-Log-Filter: /health stummschalten ----
class _HealthSilencer(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return "/health" not in msg

logging.getLogger("uvicorn.access").addFilter(_HealthSilencer())
# ---------------------------------------------------

log = logging.getLogger("uvicorn.error")


def _init_llm():
    """
    Initialisiert ein Chat LLM für Streaming-Endpoints.
    Robust gegen unterschiedliche Factory-Signaturen/Module.
    """
    # 1) Primär: zentrale LLM-Factory
    if _make_llm:
        try:
            return _make_llm(streaming=True)  # neue Signatur
        except TypeError:
            # ältere Signatur ohne streaming-Param
            return _make_llm()

    # 2) Fallback: Consult-Config Factory
    if _create_llm_cfg:
        try:
            return _create_llm_cfg(streaming=True)
        except TypeError:
            return _create_llm_cfg()

    return None


def create_app() -> FastAPI:
    app = FastAPI(title="SealAI Backend", version=os.getenv("APP_VERSION", "dev"))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health für LB/Compose
    @app.get("/health")
    async def _health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    # API v1
    app.include_router(api_router, prefix="/api/v1")

    @app.on_event("startup")
    async def _startup():
        # 1) LLM für Streaming-Endpoints initialisieren
        try:
            app.state.llm = _init_llm()
            if app.state.llm is None:
                raise RuntimeError("No LLM factory available")
            log.info("LLM initialized for streaming endpoints.")
        except Exception as e:
            app.state.llm = None
            log.warning("LLM init failed: %s", e)

        # 2) RAG Warmup (Embedding, Reranker, Redis, Qdrant) – verhindert langen ersten Request
        try:
            if ro and hasattr(ro, "prewarm"):
                ro.prewarm()
                log.info("RAG prewarm completed.")
            else:
                log.info("RAG prewarm skipped (no ro.prewarm available).")
        except Exception as e:
            log.warning("RAG prewarm failed: %s", e)

        # 3) Sync-Fallback-Graph (ohne Checkpointer) vorbereiten
        try:
            app.state.graph_sync = build_consult_graph().compile()
            log.info("Consult graph compiled for sync fallback.")
        except Exception as e:
            app.state.graph_sync = None
            log.warning("Graph compile failed: %s", e)

        log.info("Startup: no prebuilt async graph (lazy build in chat_ws).")

    return app


app = create_app()

```


## backend/app/models/beratungsergebnis.py

```py
from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime

# ✅ Gemeinsame Base aus app.database verwenden (keine eigene deklarieren)
from app.database import Base

class Beratungsergebnis(Base):
    __tablename__ = "beratungsergebnisse"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    session_id = Column(String, index=True)
    frage = Column(String)
    parameter = Column(JSON)
    antworten = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)

```


## backend/app/models/chat_message.py

```py
# 📁 backend/app/models/chat_message.py

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database import Base

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    session_id = Column(String, index=True)
    role = Column(String)  # "user" oder "assistant"
    content = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

```


## backend/app/models/form_result.py

```py
# 📁 backend/app/models/form_result.py
from __future__ import annotations
from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base

class FormResult(Base):
    __tablename__ = "form_results"

    id = Column(String, primary_key=True, index=True)
    username = Column(String, index=True)
    radial_clearance = Column(Float, nullable=False)
    tolerance_fit = Column(String, nullable=False)
    result_text = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

```


## backend/app/models/long_term_memory.py

```py
# backend/app/models/long_term_memory.py

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database import Base

class LongTermMemory(Base):
    __tablename__ = "long_term_memory"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    key = Column(String, index=True, nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

```


## backend/app/models/postgres_logger.py

```py
# 📁 backend/app/services/memory/postgres_logger.py

from app.models.chat_message import ChatMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Literal

async def log_message_to_db(
    db: AsyncSession,
    username: str,
    session_id: str,
    role: Literal["user", "assistant"],
    content: str,
):
    message = ChatMessage(
        username=username,
        session_id=session_id,
        role=role,
        content=content
    )
    db.add(message)
    await db.commit()

async def get_messages_for_session(
    db: AsyncSession,
    username: str,
    session_id: str
):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.username == username)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp)
    )
    return result.scalars().all()

```


## backend/app/redis_init.py

```py
import asyncio
import os
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

async def main():
    saver = AsyncRedisSaver(redis_url=os.environ["REDIS_URL"])
    await saver.asetup()      # idempotent
    print("✅  RediSearch-Index angelegt/aktualisiert")

asyncio.run(main())

```


## backend/app/services/__init__.py

```py

```


## backend/app/services/auth/__init__.py

```py

```


## backend/app/services/auth/dependencies.py

```py
# 📁 backend/app/services/auth/dependencies.py
"""
Auth-Dependencies für FastAPI-/WebSocket-Endpoints.

* prüft Bearer-Token (Keycloak / OIDC)
* liefert den User-Namen für Endpoints (HTTP & WS)
* WS: akzeptiert neben "Authorization: Bearer <token>" auch ?token= / ?access_token=
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, WebSocket, status, Header

from app.core.config import settings              # <-- korrekter Pfad!
from app.services.auth.token import verify_access_token


# --------------------------------------------------------------------------- #
# 1) HTTP-Dependency – für normale FastAPI-Routes
# --------------------------------------------------------------------------- #
async def get_current_request_user(  # noqa: D401 (FastAPI-Namenskonvention)
    authorization: str | None = Header(default=None),
) -> str:
    """
    Liefert den `preferred_username` aus dem gültigen JWT,
    sonst → 401 UNAUTHORIZED.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header fehlt oder ungültig",
        )

    token = authorization.removeprefix("Bearer ").strip()
    payload = verify_access_token(token)
    return payload.get("preferred_username", "anonymous")


# --------------------------------------------------------------------------- #
# 2) WebSocket-Dependency – für Chat-Streaming
#    (unterstützt Header *oder* Query-Parameter ?token=/ ?access_token=)
# --------------------------------------------------------------------------- #
async def get_current_ws_user(websocket: WebSocket) -> str:
    """
    Prüft beim WS-Handshake das Access Token.
    Bevorzugt `Authorization: Bearer <token>`, fällt aber auf Query-Parameter
    `?token=` oder `?access_token=` zurück (praktisch, da Browser-WS keine
    Custom-Header setzen kann).
    """
    # 1) Versuche Authorization-Header
    auth_header = websocket.headers.get("Authorization", "")
    token: str | None = None
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

    # 2) Fallback: Query-Parameter (z. B. ws://.../ws?token=xxx)
    if not token:
        qp = websocket.query_params
        token = qp.get("token") or qp.get("access_token")

    if not token:
        await websocket.close(code=1008)  # Policy violation
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kein Token gefunden (weder Authorization-Header noch Query-Param).",
        )

    payload = verify_access_token(token)
    return payload.get("preferred_username", "anonymous")

```


## backend/app/services/auth/jwt_utils.py

```py
# 📁 backend/app/services/auth/jwt_utils.py
from fastapi import HTTPException, status

def extract_username_from_payload(payload: dict) -> str:
    """
    Extrahiert den Nutzernamen aus dem bereits verifizierten JWT-Payload.
    """
    try:
        return (
            payload.get("preferred_username")
            or payload.get("email")
            or payload["sub"]
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username claim missing in token"
        )

```


## backend/app/services/auth/token.py

```py
"""
Token-Utilities
===============
Verifiziert Keycloak-JWTs für das Backend (REST & WebSocket).
Logging reduziert (keine sensiblen Daten), Algorithmen strikt auf RS256.
"""

from __future__ import annotations
from app.core.config import settings
import functools
from typing import Any, Final
import httpx
from jose import jwt, JWTError
import logging
import base64
import re
import json

log = logging.getLogger("uvicorn.error")

REALM_ISSUER: Final[str] = settings.backend_keycloak_issuer
JWKS_URL: Final[str] = settings.keycloak_jwks_url
ALLOWED_AUDS: Final[set[str]] = {"nextauth", "sealai-backend-api"}
ALLOWED_ALGS: Final[tuple[str, ...]] = ("RS256",)  # ✅ fixiert

@functools.lru_cache(maxsize=1)
def _get_jwks() -> dict[str, Any]:
    resp = httpx.get(JWKS_URL, timeout=5.0, verify=True)
    resp.raise_for_status()
    return resp.json()

def _get_key(kid: str) -> dict[str, Any]:
    for key in _get_jwks()["keys"]:
        if key["kid"] == kid:
            return key
    raise JWTError(f"kid {kid!r} not found in JWKS")

def _jwk_to_pem(jwk: dict[str, Any]) -> str:
    x5c = jwk.get("x5c")
    if not x5c:
        raise JWTError("x5c field missing in JWKS")
    cert = x5c[0]
    cert_str = "-----BEGIN CERTIFICATE-----\n"
    cert_str += "\n".join(cert[i:i+64] for i in range(0, len(cert), 64))
    cert_str += "\n-----END CERTIFICATE-----\n"
    return cert_str

def _safe_get_unverified_header(token: str) -> dict:
    try:
        header_b64 = token.split(".")[0]
        header_b64 = re.sub(r'[^A-Za-z0-9_\-]', '', header_b64)
        padded = header_b64 + "=" * (-len(header_b64) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        return json.loads(decoded)
    except Exception as exc:
        log.debug("JWT header decode failed: %r", exc)
        raise JWTError("Header decode fail") from exc

def verify_access_token(token: str) -> dict[str, Any]:
    """
    * Gibt den vollständigen Claim-Dict zurück, wenn alles passt
    * Löst ValueError aus, wenn der Token ungültig ist
    """
    try:
        header = _safe_get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")

        if alg not in ALLOWED_ALGS:
            raise JWTError(f"unsupported alg {alg!r}; allowed={ALLOWED_ALGS}")

        jwk = _get_key(kid)
        public_key_pem = _jwk_to_pem(jwk)

        claims: dict[str, Any] = jwt.decode(
            token,
            public_key_pem,
            algorithms=list(ALLOWED_ALGS),  # ✅ strikt
            issuer=REALM_ISSUER,
            options={"verify_aud": False},  # aud separat prüfen
        )

        # Audience/Client-Checks
        aud = claims.get("aud")
        aud_ok = (
            (isinstance(aud, str)  and aud in ALLOWED_AUDS)
            or (isinstance(aud, list) and any(a in ALLOWED_AUDS for a in aud))
            or (claims.get("azp") in ALLOWED_AUDS)
            or (claims.get("client_id") in ALLOWED_AUDS)
        )
        if not aud_ok:
            raise JWTError(
                f"audience not allowed (aud={aud!r}, azp={claims.get('azp')!r}, client_id={claims.get('client_id')!r})"
            )

        # Minimal-log (kein PEM/keine Claims)
        log.debug("JWT verified (kid=%s, alg=%s, iss ok, aud ok)", kid, alg)
        return claims

    except Exception as exc:
        log.warning("JWT verify failed: %s", exc)
        raise ValueError(str(exc)) from exc

```


## backend/app/services/langgraph/__init__.py

```py

```


## backend/app/services/langgraph/agents/__init__.py

```py

```


## backend/app/services/langgraph/agents/material_agent.py

```py
import os
from jinja2 import Environment, FileSystemLoader
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

PROMPT_FILE = os.path.join(os.path.dirname(__file__), "..", "prompts", "material_agent.jinja2")

def get_prompt(context=None):
    env = Environment(loader=FileSystemLoader(os.path.dirname(PROMPT_FILE)))
    template = env.get_template("material_agent.jinja2")
    return template.render(context=context)

class MaterialAgent:
    name = "material_agent"

    def __init__(self, context=None):
        self.system_prompt = get_prompt(context)
        self.llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0")),
            streaming=True,
        )

    def invoke(self, state):
        messages = [SystemMessage(content=self.system_prompt)] + state["messages"]
        return {"messages": self.llm.invoke(messages)}

def get_material_agent(context=None):
    return MaterialAgent(context)

```


## backend/app/services/langgraph/agents/profile_agent.py

```py
# backend/app/services/langgraph/agents/profile_agent.py
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from app.services.langgraph.llm_factory import get_llm
from app.services.langgraph.prompting import render_template

def _last_user_text(messages: List[Any]) -> str:
    for m in reversed(messages or []):
        c = getattr(m, "content", None)
        if isinstance(c, str) and c.strip():
            return c.strip()
    return ""

class ProfileAgent:
    name = "profile_agent"

    def __init__(self) -> None:
        self.llm = get_llm()

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        msgs = state.get("messages") or []
        query = _last_user_text(msgs)
        system_prompt = render_template("profile_agent.jinja2", query=query)
        response = self.llm.invoke([SystemMessage(content=system_prompt)] + msgs)
        ai = response if isinstance(response, AIMessage) else AIMessage(content=getattr(response, "content", "") or "")
        return {"messages": [ai]}

def get_profile_agent() -> ProfileAgent:
    return ProfileAgent()

```


## backend/app/services/langgraph/domains/__init__.py

```py
# -*- coding: utf-8 -*-
# Stellt sicher, dass Domains beim Import registriert werden.
from .rwdr import register as register_rwdr
from .hydraulics_rod import register as register_hydraulics_rod

def register_all_domains() -> None:
    register_rwdr()
    register_hydraulics_rod()

```


## backend/app/services/langgraph/domains/base.py

```py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import yaml
from dataclasses import dataclass
from typing import Dict, Any, Tuple, List, Optional, Callable


@dataclass
class DomainSpec:
    id: str
    name: str
    base_dir: str            # Ordner der Domain (für Prompts/Schema)
    schema_file: str         # relativer Pfad
    calculator: Callable[[dict], Dict[str, Any]]  # compute(params) -> {'calculated': ..., 'flags': ...}
    ask_order: List[str]     # Reihenfolge der Nachfragen (falls fehlt)

    def template_dir(self) -> str:
        return os.path.join(self.base_dir, "prompts")

    def schema_path(self) -> str:
        return os.path.join(self.base_dir, self.schema_file)

_REGISTRY: Dict[str, DomainSpec] = {}

def register_domain(spec: DomainSpec) -> None:
    _REGISTRY[spec.id] = spec
    # Domain-Prompts dem Jinja-Loader bekannt machen

def get_domain(domain_id: str) -> Optional[DomainSpec]:
    return _REGISTRY.get(domain_id)

def list_domains() -> List[str]:
    return list(_REGISTRY.keys())

# -------- YAML Schema Laden & Validieren (leichtgewichtig) ----------
def load_schema(spec: DomainSpec) -> Dict[str, Any]:
    with open(spec.schema_path(), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def validate_params(spec: DomainSpec, params: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Gibt (errors, warnings) zurück.
    YAML-Schema Felder:
      fields:
        <name>:
          required: bool
          type: str ('int'|'float'|'str'|'enum')
          min: float
          max: float
          enum: [..]
          ask_if: optional (Dependency-Hinweis, nur Info)
    """
    schema = load_schema(spec)
    fields = schema.get("fields", {})
    errors: List[str] = []
    warnings: List[str] = []

    def _typename(x):
        if isinstance(x, bool):   # bool ist auch int in Python
            return "bool"
        if isinstance(x, int):
            return "int"
        if isinstance(x, float):
            return "float"
        if isinstance(x, str):
            return "str"
        return type(x).__name__

    for key, rule in fields.items():
        req = bool(rule.get("required", False))
        if req and (key not in params or params.get(key) in (None, "")):
            errors.append(f"Pflichtfeld fehlt: {key}")
            continue
        if key not in params or params.get(key) in (None, ""):
            continue

        val = params.get(key)
        typ = rule.get("type")
        if typ == "enum":
            allowed = rule.get("enum", [])
            if val not in allowed:
                errors.append(f"{key}: ungültiger Wert '{val}', erlaubt: {allowed}")
        elif typ == "int":
            if not isinstance(val, int):
                # ints können als float ankommen (LLM) – tolerant casten
                try:
                    params[key] = int(float(val))
                except Exception:
                    errors.append(f"{key}: erwartet int, erhalten {_typename(val)}")
            else:
                # ok
                pass
        elif typ == "float":
            if isinstance(val, (int, float)):
                params[key] = float(val)
            else:
                try:
                    params[key] = float(str(val).replace(",", "."))
                except Exception:
                    errors.append(f"{key}: erwartet float, erhalten {_typename(val)}")
        elif typ == "str":
            if not isinstance(val, str):
                params[key] = str(val)

        # Ranges
        if isinstance(params.get(key), (int, float)):
            v = float(params[key])
            if "min" in rule and v < float(rule["min"]):
                errors.append(f"{key}: {v} < min {rule['min']}")
            if "max" in rule and v > float(rule["max"]):
                warnings.append(f"{key}: {v} > empfohlene Obergrenze {rule['max']}")

    return errors, warnings

```


## backend/app/services/langgraph/domains/hydraulics_rod/__init__.py

```py
# -*- coding: utf-8 -*-
import os
from typing import Dict, Any
from app.services.langgraph.domains.base import DomainSpec, register_domain
from .calculator import compute as hyd_rod_compute

def register() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    spec = DomainSpec(
        id="hydraulics_rod",
        name="Hydraulik – Stangendichtung",
        base_dir=base_dir,
        schema_file="schema.yaml",
        calculator=hyd_rod_compute,
        ask_order=[
            "falltyp", "stange_mm", "nut_d_mm", "nut_b_mm", "druck_bar",
            "geschwindigkeit_m_s", "medium", "temp_max_c"
        ],
    )
    register_domain(spec)

```


## backend/app/services/langgraph/domains/hydraulics_rod/calculator.py

```py
# Hydraulik – Stangendichtung: deterministische Checks
from typing import Dict, Any

def _to_float(v, default=None):
    try:
        if v is None or v == "" or v == "unknown":
            return default
        return float(v)
    except Exception:
        return default

def compute(params: Dict[str, Any]) -> Dict[str, Any]:
    # Pflicht-/Kernparameter
    p_bar   = _to_float(params.get("druck_bar"))
    t_max   = _to_float(params.get("temp_max_c"))
    speed   = _to_float(params.get("geschwindigkeit_m_s"))  # optional
    bore    = _to_float(params.get("nut_d_mm"))              # ✅ Nut-Ø D (mm)
    rod     = _to_float(params.get("stange_mm"))             # ✅ Stangen-Ø (mm)

    flags = {}
    warnings = []
    reqs = []

    # Extrusionsrisiko grob ab ~160–200 bar (ohne Stützring / je nach Spalt)
    if p_bar is not None and p_bar >= 160:
        flags["extrusion_risk"] = True
        reqs.append("Stütz-/Back-up-Ring prüfen (≥160 bar).")

    if t_max is not None and t_max > 100:
        warnings.append(f"Hohe Temperatur ({t_max:.0f} °C) – Werkstoffwahl prüfen.")

    if speed is not None and speed > 0.6:
        warnings.append(f"Hohe Stangengeschwindigkeit ({speed:.2f} m/s) – Reibung/Stick-Slip beachten.")

    # Plausibilitäts-Hinweis (Spaltmaß sehr klein)
    if bore and rod and bore - rod < 2.0:
        warnings.append("Sehr kleiner Spalt zwischen Bohrung und Stange (< 2 mm).")

    return {
        "calculated": {
            "druck_bar": p_bar,
            "temp_max_c": t_max,
            "geschwindigkeit_m_s": speed,
            "bohrung_mm": bore,
            "stange_mm": rod,
        },
        "flags": flags,
        "warnings": warnings,
        "requirements": reqs,
    }

```


## backend/app/services/langgraph/domains/hydraulics_rod/prompts/__init__.py

```py

```


## backend/app/services/langgraph/domains/hydraulics_rod/schema.yaml

```yaml
fields:
  falltyp:
    required: true
    type: enum
    enum: ["ersatz", "neu", "optimierung"]

  stange_mm:
    required: true
    type: float
    min: 4
    max: 400
  nut_d_mm:
    required: true
    type: float
    min: 6
    max: 500
  nut_b_mm:
    required: true
    type: float
    min: 2
    max: 50

  druck_bar:
    required: true
    type: float
    min: 0
    max: 500

  geschwindigkeit_m_s:
    required: false
    type: float
    min: 0
    max: 15

  medium:
    required: true
    type: str

  temp_max_c:
    required: true
    type: float
    min: -60
    max: 200

  # Umgebung/Präferenzen
  umgebung:
    required: false
    type: str
  prioritaet:
    required: false
    type: str
  besondere_anforderungen:
    required: false
    type: str
  bekannte_probleme:
    required: false
    type: str

  # NEW – Qualitätssichernde Zusatzinfos
  profil:
    required: false
    type: str
  werkstoff_pref:
    required: false
    type: str
  stange_iso:
    required: false
    type: str
  nut_toleranz:
    required: false
    type: str
  ra_stange_um:
    required: false
    type: float
    min: 0
    max: 5
  rz_stange_um:
    required: false
    type: float
    min: 0
    max: 50
  stangenwerkstoff:
    required: false
    type: str
  normen:
    required: false
    type: str

```


## backend/app/services/langgraph/domains/rwdr/__init__.py

```py
# -*- coding: utf-8 -*-
import os
from typing import Dict, Any
from app.services.langgraph.domains.base import DomainSpec, register_domain
from .calculator import compute as rwdr_compute

def register() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    spec = DomainSpec(
        id="rwdr",
        name="Radialwellendichtring",
        base_dir=base_dir,
        schema_file="schema.yaml",
        calculator=rwdr_compute,
        ask_order=[
            "falltyp", "bauform", "wellen_mm", "gehause_mm", "breite_mm",
            "medium", "temp_max_c", "druck_bar", "drehzahl_u_min"
        ],
    )
    register_domain(spec)

```


## backend/app/services/langgraph/domains/rwdr/calculator.py

```py
# backend/app/services/langgraph/domains/rwdr/calculator.py
from __future__ import annotations
from typing import Dict, Any
import math


def _to_float(x, default=0.0):
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(" ", "").replace(".", "").replace(",", ".")
        return float(s)
    except Exception:
        return default


def compute(params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    out = {"calculated": {}, "flags": {}, "warnings": [], "requirements": []}

    d_mm = _to_float(p.get("wellen_mm"))
    rpm = _to_float(p.get("drehzahl_u_min"))
    t_max = _to_float(p.get("temp_max_c"))
    press_bar = _to_float(p.get("druck_bar"))
    medium = (p.get("medium") or "").lower()
    bauform = (p.get("bauform") or "").upper()

    # Umfangsgeschwindigkeit [m/s]
    v = 0.0
    if d_mm > 0 and rpm > 0:
        v = math.pi * (d_mm / 1000.0) * (rpm / 60.0)
    v = round(v, 3)

    # Beide Keys setzen (Deutsch+Englisch), damit Templates/Alt-Code beides finden
    out["calculated"]["umfangsgeschwindigkeit_m_s"] = v
    out["calculated"]["surface_speed_m_s"] = v

    # Flags
    if press_bar > 2.0:
        out["flags"]["requires_pressure_stage"] = True
    if v >= 20.0:
        out["flags"]["speed_high"] = True
    if t_max >= 120.0:
        out["flags"]["temp_very_high"] = True

    # Material-Guidance (Whitelist/Blacklist)
    whitelist, blacklist = set(), set()

    # RWDR Bauform BA: Standard ist Elastomer-Lippe (NBR/FKM). PTFE nur Spezialprofile.
    if bauform.startswith("BA"):
        blacklist.add("PTFE")
        if any(k in medium for k in ("hydraulik", "öl", "oel", "oil")):
            if t_max <= 100:
                whitelist.update(["NBR", "FKM"])   # NBR präferiert, FKM ok
            else:
                whitelist.add("FKM")
                blacklist.add("NBR")
        else:
            whitelist.update(["FKM", "NBR"])

    # Druckrestriktion für PTFE (Standard-RWDR): ab ~0.5 bar vermeiden
    if press_bar > 0.5:
        blacklist.add("PTFE")

    # Chemie / sehr hohe Temp → PTFE als mögliche Alternative zulassen
    if any(k in medium for k in ("chem", "lösemittel", "loesemittel", "solvent")) or t_max > 180:
        whitelist.add("PTFE")

    out["calculated"]["material_whitelist"] = sorted(whitelist) if whitelist else []
    out["calculated"]["material_blacklist"] = sorted(blacklist) if blacklist else []

    # Anforderungen (menschlich lesbar)
    if whitelist:
        out["requirements"].append("Bevorzuge Materialien: " + ", ".join(sorted(whitelist)))
    if blacklist:
        out["requirements"].append("Vermeide Materialien: " + ", ".join(sorted(blacklist)))
    if out["flags"].get("requires_pressure_stage"):
        out["requirements"].append("Druckstufe oder Drucktaugliches Profil erforderlich (>2 bar).")
    if out["flags"].get("speed_high"):
        out["requirements"].append("Hohe Umfangsgeschwindigkeit (>= 20 m/s) berücksichtigen.")

    return out

```


## backend/app/services/langgraph/domains/rwdr/prompts/__init__.py

```py

```


## backend/app/services/langgraph/domains/rwdr/schema.yaml

```yaml
# RWDR Param-Schema (leichtgewichtig)
fields:
  falltyp:
    required: true
    type: enum
    enum: ["ersatz", "neu", "optimierung"]

  # Optional/Profil
  bauform:
    required: false
    type: str

  wellen_mm:
    required: true
    type: float
    min: 1
    max: 500
  gehause_mm:
    required: true
    type: float
    min: 1
    max: 800
  breite_mm:
    required: true
    type: float
    min: 1
    max: 50

  medium:
    required: true
    type: str

  temp_max_c:
    required: true
    type: float
    min: -60
    max: 250

  druck_bar:
    required: true
    type: float
    min: 0
    max: 25

  drehzahl_u_min:
    required: true
    type: int
    min: 1
    max: 30000

  # Umgebung/Präferenzen
  umgebung:
    required: false
    type: str
  prioritaet:
    required: false
    type: str
  besondere_anforderungen:
    required: false
    type: str
  bekannte_probleme:
    required: false
    type: str

  # NEW – Qualitätssichernde Zusatzinfos
  werkstoff_pref:
    required: false
    type: str
  welle_iso:
    required: false
    type: str
  gehause_iso:
    required: false
    type: str
  ra_welle_um:
    required: false
    type: float
    min: 0
    max: 5
  rz_welle_um:
    required: false
    type: float
    min: 0
    max: 50
  wellenwerkstoff:
    required: false
    type: str
  gehausewerkstoff:
    required: false
    type: str
  normen:
    required: false
    type: str

```


## backend/app/services/langgraph/examples/__init__.py

```py

```


## backend/app/services/langgraph/graph/__init__.py

```py

```


## backend/app/services/langgraph/graph/consult/__init__.py

```py

```


## backend/app/services/langgraph/graph/consult/build.py

```py
# backend/app/services/langgraph/graph/consult/build.py
from __future__ import annotations

import logging
from typing import Any, Dict, List
from langgraph.graph import StateGraph, END  # END aktuell ungenutzt, bleibt für spätere Flows

from .state import ConsultState
from .utils import normalize_messages
from .domain_router import detect_domain
from .domain_runtime import compute_domain

from .nodes.intake import intake_node
from .nodes.ask_missing import ask_missing_node
from .nodes.validate import validate_node
from .nodes.recommend import recommend_node
from .nodes.explain import explain_node
from .nodes.calc_agent import calc_agent_node
from .nodes.rag import run_rag_node
from .nodes.validate_answer import validate_answer

# NEU
from .nodes.smalltalk import smalltalk_node
from .nodes.lite_router import lite_router_node
from .nodes.deterministic_calc import deterministic_calc_node  # NEW

from .heuristic_extract import pre_extract_params
from .extract import extract_params_with_llm
from .config import create_llm  # ggf. später genutzt

log = logging.getLogger("uvicorn.error")


def _join_user_text(msgs: List) -> str:
    out: List[str] = []
    for m in msgs:
        role = (getattr(m, "type", "") or getattr(m, "role", "")).lower()
        content = getattr(m, "content", "")
        if isinstance(m, dict):
            role = (m.get("type") or m.get("role") or "").lower()
            content = m.get("content")
        if role in ("human", "user") and isinstance(content, str) and content.strip():
            out.append(content.strip())
    return "\n".join(out)


def _merge_seed_first(seed: Dict[str, Any], llm_out: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(llm_out or {})
    for k, v in (seed or {}).items():
        if v not in (None, "", []):
            out[k] = v
    return out


def _compact_param_summary(domain: str, params: Dict[str, Any]) -> str:
    p = params or {}
    parts: List[str] = []

    if domain == "rwdr":
        parts.append("RWDR")
        if p.get("abmessung"):
            parts.append(str(p["abmessung"]))
        elif p.get("wellen_mm") and p.get("gehause_mm") and p.get("breite_mm"):
            parts.append(f'{p["wellen_mm"]}x{p["gehause_mm"]}x{p["breite_mm"]}')
    elif domain == "hydraulics_rod":
        parts.append("Hydraulik Stangendichtung")

    if p.get("medium"):
        parts.append(str(p["medium"]))
    if p.get("temp_max_c") or p.get("tmax_c"):
        parts.append(f'Tmax {int(p.get("temp_max_c") or p.get("tmax_c"))} °C')
    if p.get("druck_bar"):
        parts.append(f'Druck {p["druck_bar"]} bar')
    if p.get("drehzahl_u_min"):
        parts.append(f'{int(p["drehzahl_u_min"])} U/min')
    if p.get("relativgeschwindigkeit_ms") or p.get("geschwindigkeit_m_s"):
        v = p.get("relativgeschwindigkeit_ms") or p.get("geschwindigkeit_m_s")
        parts.append(f'v≈{float(v):.2f} m/s')

    bl = p.get("material_blacklist") or p.get("vermeide_materialien")
    wl = p.get("material_whitelist") or p.get("bevorzugte_materialien")
    if bl:
        parts.append(f'Vermeide: {bl}')
    if wl:
        parts.append(f'Bevorzugt: {wl}')

    return ", ".join(parts)


def _extract_node(state: Dict[str, Any]) -> Dict[str, Any]:
    msgs = normalize_messages(state.get("messages", []))
    params = dict(state.get("params") or {})
    user_text = _join_user_text(msgs)

    heur = pre_extract_params(user_text)
    seed = {**params, **{k: v for k, v in heur.items() if v not in (None, "", [])}}

    llm_params = extract_params_with_llm(user_text)
    final_params = _merge_seed_first(seed, llm_params)
    return {**state, "params": final_params, "phase": "extract"}


def _domain_router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    msgs = normalize_messages(state.get("messages", []))
    params = dict(state.get("params") or {})
    try:
        domain = detect_domain(None, msgs, params) or "rwdr"
        domain = domain.strip().lower()
    except Exception:
        domain = "rwdr"
    return {**state, "domain": domain, "phase": "domain_router"}


def _compute_node(state: Dict[str, Any]) -> Dict[str, Any]:
    domain = (state.get("domain") or "rwdr").strip().lower()
    params = dict(state.get("params") or {})
    derived = compute_domain(domain, params) or {}

    alias_map = {
        "tmax_c": params.get("temp_max_c"),
        "temp_c": params.get("temp_max_c"),
        "druck": params.get("druck_bar"),
        "pressure_bar": params.get("druck_bar"),
        "n_u_min": params.get("drehzahl_u_min"),
        "rpm": params.get("drehzahl_u_min"),
        "v_ms": params.get("relativgeschwindigkeit_ms") or params.get("geschwindigkeit_m_s"),
    }
    for k, v in alias_map.items():
        if k not in params and v not in (None, "", []):
            params[k] = v

    return {**state, "params": params, "derived": derived, "phase": "compute"}


def _prepare_query_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if (state.get("query") or "").strip():
        return {**state, "phase": "prepare_query"}

    params = dict(state.get("params") or {})
    domain = (state.get("domain") or "rwdr").strip().lower()

    user_text = ""  # Query ist rein technisch – daher kompakter Param-String
    param_str = _compact_param_summary(domain, params)
    prefix = "RWDR" if domain == "rwdr" else "Hydraulik"
    query = ", ".join([s for s in [prefix, user_text, param_str] if s])

    new_state = dict(state)
    new_state["query"] = query
    return {**new_state, "phase": "prepare_query"}


def _respond_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return {**state, "phase": "respond"}


# ---- Conditional helpers ----
def _route_key(state: Dict[str, Any]) -> str:
    return (state.get("route") or "default").strip().lower() or "default"


def _ask_or_ok(state: Dict[str, Any]) -> str:
    p = state.get("params") or {}

    def has(v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, (list, dict)) and not v:
            return False
        if isinstance(v, str) and not v.strip():
            return False
        return True

    base_ok = has(p.get("temp_max_c")) and has(p.get("druck_bar"))
    rel_ok = has(p.get("relativgeschwindigkeit_ms") or p.get("geschwindigkeit_m_s")) or (
        has(p.get("wellen_mm")) and has(p.get("drehzahl_u_min"))
    )

    if not (base_ok and rel_ok):
        return "ask"

    return "ok"


def _after_rag(state: Dict[str, Any]) -> str:
    p = state.get("params") or {}

    def has(v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, (list, dict)) and not v:
            return False
        if isinstance(v, str) and not v.strip():
            return False
        return True

    base_ok = has(p.get("temp_max_c")) and has(p.get("druck_bar"))
    rel_ok = has(p.get("relativgeschwindigkeit_ms") or p.get("geschwindigkeit_m_s")) or (
        has(p.get("wellen_mm")) and has(p.get("drehzahl_u_min"))
    )
    docs = state.get("retrieved_docs") or state.get("docs") or []
    ctx_ok = bool(docs) or bool(state.get("context"))

    return "recommend" if (base_ok and rel_ok and ctx_ok) else "explain"


def build_graph() -> StateGraph:
    log.info("[ConsultGraph] Initialisierung…")
    g = StateGraph(ConsultState)

    # --- Nodes ---
    g.add_node("lite_router", lite_router_node)   # NEU
    g.add_node("smalltalk", smalltalk_node)       # NEU

    g.add_node("intake", intake_node)
    g.add_node("extract", _extract_node)
    g.add_node("domain_router", _domain_router_node)
    g.add_node("compute", _compute_node)

    # NEW: deterministische Physik vor dem LLM-Calc-Agent
    g.add_node("deterministic_calc", deterministic_calc_node)

    g.add_node("calc_agent", calc_agent_node)
    g.add_node("ask_missing", ask_missing_node)
    g.add_node("validate", validate_node)
    g.add_node("prepare_query", _prepare_query_node)
    g.add_node("rag", run_rag_node)
    g.add_node("recommend", recommend_node)
    g.add_node("validate_answer", validate_answer)
    g.add_node("explain", explain_node)
    g.add_node("respond", _respond_node)

    # --- Entry & Routing ---
    g.set_entry_point("lite_router")
    g.add_conditional_edges("lite_router", _route_key, {
        "smalltalk": "smalltalk",
        "default": "intake",
    })

    # Smalltalk direkt abschließen
    g.add_edge("smalltalk", "respond")

    # --- Main flow ---
    g.add_edge("intake", "extract")
    g.add_edge("extract", "domain_router")
    g.add_edge("domain_router", "compute")
    g.add_edge("compute", "deterministic_calc")
    g.add_edge("deterministic_calc", "calc_agent")
    g.add_edge("calc_agent", "ask_missing")

    g.add_conditional_edges("ask_missing", _ask_or_ok, {
        "ask": "respond",
        "ok": "validate",
    })

    g.add_edge("validate", "prepare_query")
    g.add_edge("prepare_query", "rag")

    g.add_conditional_edges("rag", _after_rag, {
        "recommend": "recommend",
        "explain": "explain",
    })

    g.add_edge("recommend", "validate_answer")
    g.add_edge("validate_answer", "respond")
    g.add_edge("explain", "respond")

    return g


# ---- Alias für io.py (erwartet build_consult_graph) ----
def build_consult_graph() -> StateGraph:
    """Kompatibilitäts-Alias – liefert denselben StateGraph wie build_graph()."""
    return build_graph()


__all__ = ["build_graph", "build_consult_graph"]

```


## backend/app/services/langgraph/graph/consult/config.py

```py
# backend/app/services/langgraph/graph/consult/config.py
from __future__ import annotations

import os
from typing import List, Optional
from langchain_openai import ChatOpenAI


# --- Domänen-Schalter ---------------------------------------------------------
# Kommagetrennte Liste via ENV z. B.: "rwdr,hydraulics_rod"
def _env_domains() -> List[str]:
    raw = (os.getenv("CONSULT_ENABLED_DOMAINS") or "").strip()
    if not raw:
        return ["rwdr", "hydraulics_rod"]
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


ENABLED_DOMAINS: List[str] = _env_domains()


# --- LLM-Fabrik ---------------------------------------------------------------
def _model_name() -> str:
    # Fällt auf GPT-5 mini zurück, wie gewünscht
    return (os.getenv("LLM_MODEL_DEFAULT") or "gpt-5-mini").strip()


def _base_url() -> Optional[str]:
    # kompatibel zu llm_factory: neues Feld heißt base_url (nicht api_base)
    base = (os.getenv("OPENAI_API_BASE") or "").strip()
    return base or None


def create_llm(*, streaming: bool = True) -> ChatOpenAI:
    """
    Einheitliche LLM-Erzeugung für den Consult-Graph.
    Nutzt GPT-5-mini (Default) und übernimmt OPENAI_API_BASE, falls gesetzt,
    via base_url (kein api_base!).
    """
    kwargs = {
        "model": _model_name(),
        "streaming": streaming,
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.3")),
        "max_retries": int(os.getenv("LLM_MAX_RETRIES", "2")),
    }
    base = _base_url()
    if base:
        kwargs["base_url"] = base
    return ChatOpenAI(**kwargs)

```


## backend/app/services/langgraph/graph/consult/domain_router.py

```py
# backend/app/services/langgraph/graph/consult/domain_router.py
from __future__ import annotations
import json
from typing import List
from langchain_openai import ChatOpenAI
from app.services.langgraph.llm_router import get_router_llm, get_router_fallback_llm
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from app.services.langgraph.prompting import render_template, messages_for_template, strip_json_fence
from .config import ENABLED_DOMAINS

def detect_domain(llm: ChatOpenAI, msgs: List[AnyMessage], params: dict) -> str:
    router = llm or get_router_llm()
    prompt = render_template(
        "domain_router.jinja2",
        messages=messages_for_template(msgs),
        params_json=json.dumps(params, ensure_ascii=False),
        enabled_domains=ENABLED_DOMAINS,
    )
    # 1st pass
    resp = router.invoke([HumanMessage(content=prompt)])
    domain, conf = None, 0.0
    try:
        data = json.loads(strip_json_fence(resp.content or ""))
        domain = str((data.get("domain") or "")).strip().lower()
        conf = float(data.get("confidence") or 0.0)
    except Exception:
        domain, conf = None, 0.0

    # Fallback, wenn unsicher
    if (domain not in ENABLED_DOMAINS) or (conf < 0.70):
        fb = get_router_fallback_llm()
        try:
            resp2 = fb.invoke([HumanMessage(content=prompt)])
            data2 = json.loads(strip_json_fence(resp2.content or ""))
            d2 = str((data2.get("domain") or "")).strip().lower()
            c2 = float(data2.get("confidence") or 0.0)
            if (d2 in ENABLED_DOMAINS) and (c2 >= conf):
                domain, conf = d2, c2
        except Exception:
            pass

    # Heuristische Fallbacks – nur Nutzertext
    if (domain not in ENABLED_DOMAINS) or (conf < 0.40):
        utter = ""
        for m in reversed(msgs or []):
            if hasattr(m, "content") and getattr(m, "content"):
                if isinstance(m, HumanMessage):
                    utter = (m.content or "").lower().strip()
                    break
        if "wellendichtring" in utter or "rwdr" in utter:
            domain = "rwdr"
        elif "stangendichtung" in utter or "kolbenstange" in utter or "hydraulik" in utter:
            domain = "hydraulics_rod"
        elif (params.get("bauform") or "").upper().startswith("BA"):
            domain = "rwdr"
        elif ENABLED_DOMAINS:
            domain = ENABLED_DOMAINS[0]
        else:
            domain = "rwdr"
    return domain

```


## backend/app/services/langgraph/graph/consult/domain_runtime.py

```py
# backend/app/services/langgraph/graph/consult/domain_runtime.py
from __future__ import annotations
import importlib
import logging
from typing import Any, Dict, List
from .state import Parameters, Derived

log = logging.getLogger(__name__)

def compute_domain(domain: str, params: Parameters) -> Derived:
    try:
        mod = importlib.import_module(f"app.services.langgraph.domains.{domain}.calculator")
        compute = getattr(mod, "compute")
        out = compute(params)  # type: ignore
        return {
            "calculated": dict(out.get("calculated", {})),
            "flags": dict(out.get("flags", {})),
            "warnings": list(out.get("warnings", [])),
            "requirements": list(out.get("requirements", [])),
        }
    except Exception as e:
        log.warning("Domain compute failed (%s): %s", domain, e)
        return {"calculated": {}, "flags": {}, "warnings": [], "requirements": []}

def missing_by_domain(domain: str, p: Parameters) -> List[str]:
    # ✅ Hydraulik-Stange nutzt stange_mm / nut_d_mm / nut_b_mm
    if domain == "hydraulics_rod":
        req = [
            "falltyp",
            "stange_mm",
            "nut_d_mm",
            "nut_b_mm",
            "medium",
            "temp_max_c",
            "druck_bar",
            "geschwindigkeit_m_s",
        ]
    else:
        req = [
            "falltyp",
            "wellen_mm",
            "gehause_mm",
            "breite_mm",
            "medium",
            "temp_max_c",
            "druck_bar",
            "drehzahl_u_min",
        ]

    def _is_missing(key: str, val: Any) -> bool:
        if val is None or val == "" or val == "unknown":
            return True
        if key == "druck_bar":
            try: float(val); return False
            except Exception: return True
        if key in ("wellen_mm", "gehause_mm", "breite_mm", "drehzahl_u_min", "geschwindigkeit_m_s",
                   "stange_mm", "nut_d_mm", "nut_b_mm"):
            try: return float(val) <= 0
            except Exception: return True
        if key == "temp_max_c":
            try: float(val); return False
            except Exception: return True
        return False

    return [k for k in req if _is_missing(k, p.get(k))]

def anomaly_messages(domain: str, params: Parameters, derived: Derived) -> List[str]:
    msgs: List[str] = []
    flags = (derived.get("flags") or {})
    if flags.get("requires_pressure_stage") and not flags.get("pressure_stage_ack"):
        msgs.append("Ein Überdruck >2 bar ist für Standard-Radialdichtringe kritisch. Dürfen Druckstufenlösungen geprüft werden?")
    if flags.get("speed_high"):
        msgs.append("Die Drehzahl/Umfangsgeschwindigkeit ist hoch – ist sie dauerhaft oder nur kurzzeitig (Spitzen)?")
    if flags.get("temp_very_high"):
        msgs.append("Die Temperatur ist sehr hoch. Handelt es sich um Dauer- oder Spitzentemperaturen?")
    if domain == "hydraulics_rod" and flags.get("extrusion_risk") and not flags.get("extrusion_risk_ack"):
        msgs.append("Bei dem Druck besteht Extrusionsrisiko. Darf eine Stütz-/Back-up-Ring-Lösung geprüft werden?")
    return msgs

```


## backend/app/services/langgraph/graph/consult/extract.py

```py
# backend/app/services/langgraph/graph/consult/extract.py
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from app.services.langgraph.llm_factory import get_llm
from app.services.langgraph.prompting import render_template

log = logging.getLogger(__name__)

# ============================================================
# einfache Heuristik als Fallback
# ============================================================

_NUMBER = r"[-+]?\d+(?:[.,]\d+)?"

def _to_float(x: Any) -> Optional[float]:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().replace(",", ".")
        return float(s)
    except Exception:
        return None

def heuristic_extract(user_input: str) -> Dict[str, Any]:
    txt = (user_input or "").lower()
    out: Dict[str, Any] = {"source": "heuristic"}

    if any(w in txt for w in ["rwdr", "wellendichtring", "radialwellendichtring"]):
        out["domain"] = "rwdr"; out["falltyp"] = "rwdr"
    elif any(w in txt for w in ["stangendichtung", "kolbenstange", "hydraulik"]):
        out["domain"] = "hydraulics_rod"; out["falltyp"] = "hydraulics_rod"

    m = re.search(rf"(?P<d>{_NUMBER})\s*[x×]\s*(?P<D>{_NUMBER})\s*[x×]\s*(?P<b>{_NUMBER})\s*mm", txt)
    if m:
        out["wellen_mm"]  = _to_float(m.group("d"))
        out["gehause_mm"] = _to_float(m.group("D"))
        out["breite_mm"]  = _to_float(m.group("b"))
    else:
        md = re.search(rf"(?:welle|d)\s*[:=]?\s*({_NUMBER})\s*mm", txt)
        mD = re.search(rf"(?:gehäuse|gehause|D)\s*[:=]?\s*({_NUMBER})\s*mm", txt)
        mb = re.search(rf"(?:breite|b)\s*[:=]?\s*({_NUMBER})\s*mm", txt)
        if md: out["wellen_mm"]  = _to_float(md.group(1))
        if mD: out["gehause_mm"] = _to_float(mD.group(1))
        if mb: out["breite_mm"]  = _to_float(mb.group(1))

    tmax = re.search(rf"(?:tmax|temp(?:eratur)?(?:\s*max)?)\s*[:=]?\s*({_NUMBER})\s*°?\s*c", txt)
    if not tmax:
        tmax = re.search(rf"({_NUMBER})\s*°?\s*c", txt)
    if tmax:
        out["temp_max_c"] = _to_float(tmax.group(1))

    p = re.search(rf"(?:p(?:_?max)?|druck)\s*[:=]?\s*({_NUMBER})\s*bar", txt)
    if p:
        out["druck_bar"] = _to_float(p.group(1))

    rpm = re.search(rf"(?:n|drehzahl|rpm)\s*[:=]?\s*({_NUMBER})\s*(?:u/?min|rpm)", txt)
    if rpm:
        out["drehzahl_u_min"] = _to_float(rpm.group(1))

    v = re.search(rf"(?:v|geschwindigkeit)\s*[:=]?\s*({_NUMBER})\s*m/?s", txt)
    if v:
        out["geschwindigkeit_m_s"] = _to_float(v.group(1))

    med = re.search(r"(?:medium|medien|stoff)\s*[:=]\s*([a-z0-9\-_/.,\s]+)", txt)
    if med:
        out["medium"] = med.group(1).strip()
    else:
        for k in ["öl", "oel", "diesel", "benzin", "kraftstoff", "wasser", "dampf", "säure", "saeure", "lauge"]:
            if k in txt:
                out["medium"] = k; break

    return out

# ============================================================
# robustes JSON aus LLM
# ============================================================

_JSON_RX = re.compile(r"\{[\s\S]*\}")

def _safe_json(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _JSON_RX.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

# ============================================================
# Öffentliche API (SIGNATUR passt zu build.py)
# ============================================================

def extract_params_with_llm(user_input: str, *, rag_context: str | None = None) -> Dict[str, Any]:
    """
    Extrahiert Pflicht-/Kernparameter aus der Nutzeranfrage.
    - FIX: korrektes Rendering von Jinja (keine zusätzlichen Positional-Args)
    - Normales Chat-Completion + robustes JSON-Parsing
    - Fallback: lokale Heuristik
    """
    try:
        sys_prompt = render_template(
            "consult_extract_params.jinja2",
            messages=[{"type": "user", "content": (user_input or "").strip()}],
            params_json="{}",
        )
    except Exception as e:
        log.warning("[extract_params_with_llm] template_render_failed: %r", e)
        return heuristic_extract(user_input)

    messages: List[Any] = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=user_input or ""),
    ]

    llm = get_llm(streaming=False)

    try:
        resp = llm.invoke(messages)
        text = getattr(resp, "content", "") or ""
    except Exception as e:
        log.warning("[extract_params_with_llm] llm_invoke_failed_plain: %r", e)
        return heuristic_extract(user_input)

    data = _safe_json(text)
    if not isinstance(data, dict):
        log.info("[extract_params_with_llm] no_json_in_response – using heuristic")
        return heuristic_extract(user_input)

    normalized: Dict[str, Any] = {}

    def _pick(name: str, *aliases: str, cast=None):
        for k in (name, *aliases):
            if k in data and data[k] is not None:
                v = data[k]
                if cast:
                    try:
                        v = cast(v)
                    except Exception:
                        pass
                normalized[name] = v
                return

    _pick("falltyp")
    _pick("domain")
    _pick("wellen_mm", "stange_mm", cast=_to_float)
    _pick("gehause_mm", "nut_d_mm", cast=_to_float)
    _pick("breite_mm", "nut_b_mm", cast=_to_float)
    _pick("temp_max_c", cast=_to_float)
    _pick("drehzahl_u_min", cast=_to_float)
    _pick("druck_bar", cast=_to_float)
    _pick("geschwindigkeit_m_s", cast=_to_float)
    _pick("medium")

    for k, v in data.items():
        if k not in normalized:
            normalized[k] = v

    normalized.setdefault("source", "llm_json")
    return normalized

def extract_params(user_input: str, *, rag_context: str | None = None) -> Dict[str, Any]:
    return extract_params_with_llm(user_input, rag_context=rag_context)

```


## backend/app/services/langgraph/graph/consult/heuristic_extract.py

```py
from __future__ import annotations
import re
from typing import Dict, Optional

_NUM = r"-?\d+(?:[.,]\d+)?"

def _to_float(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None

def pre_extract_params(text: str) -> Dict[str, object]:
    t = text or ""
    out: Dict[str, object] = {}

    m = re.search(r"(?:\b(?:rwdr|ba|bauform)\b\s*)?(\d{1,3})\s*[x×]\s*(\d{1,3})\s*[x×]\s*(\d{1,3})", t, re.I)
    if m:
        out["wellen_mm"]  = int(m.group(1))
        out["gehause_mm"] = int(m.group(2))
        out["breite_mm"]  = int(m.group(3))

    if re.search(r"\bhydraulik ?öl\b", t, re.I):
        out["medium"] = "Hydrauliköl"
    elif re.search(r"\böl\b", t, re.I):
        out["medium"] = "Öl"
    elif re.search(r"\bwasser\b", t, re.I):
        out["medium"] = "Wasser"

    m = re.search(r"(?:t\s*max|temp(?:eratur)?(?:\s*max)?|t)\s*[:=]?\s*(" + _NUM + r")\s*°?\s*c\b", t, re.I)
    if not m:
        m = re.search(r"\b(" + _NUM + r")\s*°?\s*c\b", t, re.I)
    if m:
        out["temp_max_c"] = _to_float(m.group(1))

    m = re.search(r"(?:\bdruck\b|[^a-z]p)\s*[:=]?\s*(" + _NUM + r")\s*bar\b", t, re.I)
    if not m:
        m = re.search(r"\b(" + _NUM + r")\s*bar\b", t, re.I)
    if m:
        out["druck_bar"] = _to_float(m.group(1))

    m = re.search(r"(?:\bn\b|drehzahl)\s*[:=]?\s*(\d{1,7})\s*(?:u/?min|rpm)\b", t, re.I)
    if not m:
        m = re.search(r"\b(\d{1,7})\s*(?:u/?min|rpm)\b", t, re.I)
    if m:
        out["drehzahl_u_min"] = int(m.group(1))

    m = re.search(r"\bbauform\s*[:=]?\s*([A-Z0-9]{1,4})\b|\b(BA|B1|B2|TC|SC)\b", t, re.I)
    if m:
        out["bauform"] = (m.group(1) or m.group(2) or "").upper()

    return out

```


## backend/app/services/langgraph/graph/consult/intent_llm.py

```py
from __future__ import annotations

"""
LLM-basierter Intent-Router (verpflichtend).
- Nutzt ChatOpenAI (Model per ENV, Default: gpt-5-mini).
- Gibt eines der erlaubten Labels zurück, sonst 'chitchat'.
- Fallback: robuste Heuristik, falls LLM fehlschlägt.
"""

import os
import re
import logging
from typing import Any, Dict, List, Optional, TypedDict

log = logging.getLogger("uvicorn.error")

# Erlaubte Ziele (müssen mit build.py übereinstimmen)
ALLOWED_ROUTES: List[str] = [
    "rag_qa",
    "material_agent",
    "profile_agent",
    "calc_agent",
    "report_agent",
    "memory_export",
    "memory_delete",
    "chitchat",
]

# Prompt für den reinen Label-Output
_INTENT_PROMPT = """Du bist ein Intent-Router. Antworte NUR mit einem Label (genau wie angegeben):
{allowed}

Eingabe: {query}
Label:"""

# Heuristiken als Fallback
_HEURISTICS: List[tuple[str, re.Pattern]] = [
    ("memory_export", re.compile(r"\b(export|download|herunterladen|daten\s*export)\b", re.I)),
    ("memory_delete", re.compile(r"\b(löschen|delete|entfernen)\b", re.I)),
    ("calc_agent",    re.compile(r"\b(rechnen|berechne|calculate|calc|formel|formulas?)\b", re.I)),
    ("report_agent",  re.compile(r"\b(report|bericht|pdf|zusammenfassung|protokoll)\b", re.I)),
    ("material_agent",re.compile(r"\b(material|werkstoff|elastomer|ptfe|fkm|nbr|epdm)\b", re.I)),
    ("profile_agent", re.compile(r"\b(profil|o-ring|x-ring|u-profil|lippe|dichtung\s*profil)\b", re.I)),
    ("rag_qa",        re.compile(r"\b(warum|wie|quelle|dokument|datenblatt|docs?)\b", re.I)),
]

# State-Shape (nur für Typing; zur Laufzeit wird ein dict genutzt)
class ConsultState(TypedDict, total=False):
    user: str
    chat_id: Optional[str]
    input: str
    route: str
    response: str
    citations: List[Dict[str, Any]]

# LLM-Konfiguration
try:
    from langchain_openai import ChatOpenAI
    _LLM_OK = bool(os.getenv("OPENAI_API_KEY"))
except Exception:
    ChatOpenAI = None  # type: ignore
    _LLM_OK = False

def _classify_heuristic(query: str) -> str:
    q = (query or "").lower()
    for label, pattern in _HEURISTICS:
        if pattern.search(q):
            return label
    if re.search(r"[?]|(wie|warum|wieso|quelle|beleg)", q):
        return "rag_qa"
    return "chitchat"

def _classify_llm(query: str) -> str:
    if not (_LLM_OK and ChatOpenAI):
        raise RuntimeError("LLM not available")
    model_name = os.getenv("OPENAI_INTENT_MODEL", "gpt-5-mini")
    llm = ChatOpenAI(model=model_name, temperature=0, max_tokens=6)  # type: ignore
    prompt = _INTENT_PROMPT.format(allowed=", ".join(ALLOWED_ROUTES), query=query.strip())
    try:
        resp = llm.invoke(prompt)  # type: ignore
        label = str(getattr(resp, "content", "")).strip().lower()
        if label in ALLOWED_ROUTES:
            return label
    except Exception as exc:
        log.warning("LLM Intent error: %r", exc)
    # Fallback falls Ausgabe nicht sauber ist
    return _classify_heuristic(query)

def intent_router_node(state: ConsultState) -> ConsultState:
    """Graph-Node: setzt state['route'] über LLM (mit Heuristik-Fallback)."""
    query = state.get("input", "") or ""
    try:
        route = _classify_llm(query)
    except Exception:
        route = _classify_heuristic(query)

    if route not in ALLOWED_ROUTES:
        route = "chitchat"

    state["route"] = route
    return state

```


## backend/app/services/langgraph/graph/consult/io.py

```py
# backend/app/services/langgraph/graph/consult/io.py
from __future__ import annotations

from typing import Any, Dict

# MemorySaver je nach LangGraph-Version importieren
try:
    from langgraph.checkpoint import MemorySaver  # neuere Versionen
except Exception:
    try:
        from langgraph.checkpoint.memory import MemorySaver  # ältere Versionen
    except Exception:
        MemorySaver = None  # Fallback: ohne Checkpointer

# Build-Funktion robust importieren
try:
    from .build import build_consult_graph as _build_graph
except ImportError:
    from .build import build_graph as _build_graph  # Fallback

from .state import ConsultState


def _make_graph():
    g = _build_graph()
    if MemorySaver is not None:
        g.checkpointer = MemorySaver()
    return g.compile()


_GRAPH = None


def invoke_consult(state: Dict[str, Any]) -> Dict[str, Any]:
    """Synchroner Invoke des Consult-Graphs mit einfachem Singleton-Caching."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _make_graph()
    result = _GRAPH.invoke(state or {})
    if isinstance(result, ConsultState):
        return dict(result)
    return dict(result or {})

```


## backend/app/services/langgraph/graph/consult/memory_utils.py

```py
from __future__ import annotations

import os
import json
from typing import List, Dict, Literal, TypedDict

from redis import Redis
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AnyMessage


def _redis() -> Redis:
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return Redis.from_url(url, decode_responses=True)

def _conv_key(thread_id: str) -> str:
    # Gleicher Key wie im SSE: chat:stm:{thread_id}:messages
    return f"chat:stm:{thread_id}:messages"


def write_message(*, thread_id: str, role: Literal["user", "assistant", "system"], content: str) -> None:
    if not content:
        return
    r = _redis()
    key = _conv_key(thread_id)
    item = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.lpush(key, item)
    pipe.ltrim(key, 0, int(os.getenv("STM_MAX_ITEMS", "200")) - 1)
    pipe.expire(key, int(os.getenv("STM_TTL_SEC", "604800")))  # 7 Tage
    pipe.execute()


def read_history_raw(thread_id: str, limit: int = 80) -> List[Dict[str, str]]:
    """Rohdaten (älteste -> neueste)."""
    r = _redis()
    key = _conv_key(thread_id)
    items = r.lrange(key, 0, limit - 1) or []
    out: List[Dict[str, str]] = []
    for s in reversed(items):  # Redis speichert neueste zuerst
        try:
            obj = json.loads(s)
            role = (obj.get("role") or "").lower()
            content = obj.get("content") or ""
            if role and content:
                out.append({"role": role, "content": content})
        except Exception:
            continue
    return out


def read_history(thread_id: str, limit: int = 80) -> List[AnyMessage]:
    """LangChain-Messages (älteste -> neueste)."""
    msgs: List[AnyMessage] = []
    for item in read_history_raw(thread_id, limit=limit):
        role = item["role"]
        content = item["content"]
        if role in ("user", "human"):
            msgs.append(HumanMessage(content=content))
        elif role in ("assistant", "ai"):
            msgs.append(AIMessage(content=content))
        elif role == "system":
            msgs.append(SystemMessage(content=content))
    return msgs

```


## backend/app/services/langgraph/graph/consult/nodes/__init__.py

```py
# backend/app/services/langgraph/graph/consult/nodes/__init__.py
# (nur für Paketinitialisierung)

```


## backend/app/services/langgraph/graph/consult/nodes/ask_missing.py

```py
# backend/app/services/langgraph/graph/consult/nodes/ask_missing.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from app.services.langgraph.prompting import render_template

try:
    from ..utils import missing_by_domain, anomaly_messages, normalize_messages
except ImportError:
    from ..utils import missing_by_domain, normalize_messages
    from ..domain_runtime import anomaly_messages

log = logging.getLogger(__name__)

FIELD_LABELS_RWDR = {
    "falltyp": "Anwendungsfall (Ersatz/Neu/Optimierung)",
    "wellen_mm": "Welle (mm)",
    "gehause_mm": "Gehäuse (mm)",
    "breite_mm": "Breite (mm)",
    "bauform": "Bauform/Profil",
    "medium": "Medium",
    "temp_min_c": "Temperatur min (°C)",
    "temp_max_c": "Temperatur max (°C)",
    "druck_bar": "Druck (bar)",
    "drehzahl_u_min": "Drehzahl (U/min)",
    "geschwindigkeit_m_s": "Relativgeschwindigkeit (m/s)",
    "umgebung": "Umgebung",
    "prioritaet": "Priorität (z. B. Preis, Lebensdauer)",
    "besondere_anforderungen": "Besondere Anforderungen",
    "bekannte_probleme": "Bekannte Probleme",
}
DISPLAY_ORDER_RWDR = [
    "falltyp","wellen_mm","gehause_mm","breite_mm","bauform","medium",
    "temp_min_c","temp_max_c","druck_bar","drehzahl_u_min","geschwindigkeit_m_s",
    "umgebung","prioritaet","besondere_anforderungen","bekannte_probleme",
]

FIELD_LABELS_HYD = {
    "falltyp": "Anwendungsfall (Ersatz/Neu/Optimierung)",
    "stange_mm": "Stange (mm)",
    "nut_d_mm": "Nut-Ø D (mm)",
    "nut_b_mm": "Nutbreite B (mm)",
    "medium": "Medium",
    "temp_max_c": "Temperatur max (°C)",
    "druck_bar": "Druck (bar)",
    "geschwindigkeit_m_s": "Relativgeschwindigkeit (m/s)",
}
DISPLAY_ORDER_HYD = [
    "falltyp","stange_mm","nut_d_mm","nut_b_mm","medium","temp_max_c","druck_bar","geschwindigkeit_m_s",
]

def _friendly_list(keys: List[str], domain: str) -> str:
    if domain == "hydraulics_rod":
        labels, order = FIELD_LABELS_HYD, DISPLAY_ORDER_HYD
    else:
        labels, order = FIELD_LABELS_RWDR, DISPLAY_ORDER_RWDR
    ordered = [k for k in order if k in keys]
    return ", ".join(f"**{labels.get(k, k)}**" for k in ordered)

def ask_missing_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Rückfragen & UI-Event (Formular öffnen) bei fehlenden Angaben."""
    consult_required = bool(state.get("consult_required", True))
    if not consult_required:
        return {**state, "messages": [], "phase": "ask_missing"}

    _ = normalize_messages(state.get("messages", []))
    params: Dict[str, Any] = state.get("params") or {}
    domain: str = (state.get("domain") or "rwdr").strip().lower()
    derived: Dict[str, Any] = state.get("derived") or {}

    lang = (params.get("lang") or state.get("lang") or "de").lower()

    missing = missing_by_domain(domain, params)
    log.info("[ask_missing_node] fehlend=%s domain=%s consult_required=%s", missing, domain, consult_required)

    if missing:
        friendly = _friendly_list(missing, domain)
        example = (
            "Welle 25, Gehäuse 47, Breite 7, Medium Öl, Tmax 80, Druck 2 bar, n 1500"
            if domain != "hydraulics_rod"
            else "Stange 25, Nut D 32, Nut B 6, Medium Öl, Tmax 80, Druck 160 bar, v 0,3 m/s"
        )

        content = render_template("ask_missing.jinja2", domain=domain, friendly=friendly, example=example, lang=lang)

        ui_event = {
            "ui_action": "open_form",
            "form_id": f"{domain}_params_v1",
            "schema_ref": f"domains/{domain}/params@1.0.0",
            "missing": missing,
            "prefill": {k: v for k, v in params.items() if v not in (None, "", [])},
        }
        log.info("[ask_missing_node] ui_event=%s", ui_event)
        return {**state, "messages": [AIMessage(content=content)], "phase": "ask_missing", "ui_event": ui_event, "missing_fields": missing}

    followups = anomaly_messages(domain, params, derived)
    if followups:
        content = render_template("ask_missing_followups.jinja2", followups=followups[:2], lang=lang)
        ui_event = {
            "ui_action": "open_form",
            "form_id": f"{domain}_params_v1",
            "schema_ref": f"domains/{domain}/params@1.0.0",
            "missing": [],
            "prefill": {k: v for k, v in params.items() if v not in (None, "", [])},
        }
        log.info("[ask_missing_node] ui_event_followups=%s", ui_event)
        return {**state, "messages": [AIMessage(content=content)], "phase": "ask_missing", "ui_event": ui_event, "missing_fields": []}

    return {**state, "messages": [], "phase": "ask_missing"}

```


## backend/app/services/langgraph/graph/consult/nodes/calc_agent.py

```py
# backend/app/services/langgraph/graph/consult/nodes/calc_agent.py
from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

def _num(x: Any) -> float | None:
    try:
        if x in (None, "", []):
            return None
        if isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None

def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def _calc_rwdr(params: Dict[str, Any]) -> Dict[str, Any]:
    d_mm = _num(params.get("wellen_mm"))
    n_rpm = _num(params.get("drehzahl_u_min"))
    p_bar = _num(params.get("druck_bar"))
    tmax = _num(params.get("temp_max_c"))

    calc: Dict[str, Any] = {}
    if d_mm is not None and n_rpm is not None and d_mm > 0 and n_rpm >= 0:
        d_m = d_mm / 1000.0
        v_ms = 3.141592653589793 * d_m * (n_rpm / 60.0)
        calc["umfangsgeschwindigkeit_m_s"] = v_ms
        calc["surface_speed_m_s"] = round(v_ms, 3)

    if p_bar is not None and calc.get("umfangsgeschwindigkeit_m_s") is not None:
        calc["pv_indicator_bar_ms"] = p_bar * calc["umfangsgeschwindigkeit_m_s"]

    mat_whitelist: list[str] = []
    mat_blacklist: list[str] = []
    medium = (params.get("medium") or "").strip().lower()
    # KEINE harte PTFE-Blacklist bei Wasser
    if "wasser" in medium:
        mat_whitelist.extend(["EPDM", "FKM", "PTFE"])

    if tmax is not None:
        if tmax > 120:
            mat_whitelist.append("FKM")
        if tmax > 200:
            mat_whitelist.append("PTFE")

    reqs: list[str] = []
    flags: Dict[str, Any] = {}
    if p_bar is not None and p_bar > 1.0:
        flags["druckbelastet"] = True

    return {
        "calculated": calc,
        "material_whitelist": mat_whitelist,
        "material_blacklist": mat_blacklist,
        "requirements": reqs,
        "flags": flags,
    }

def _calc_hydraulics_rod(params: Dict[str, Any]) -> Dict[str, Any]:
    p_bar = _num(params.get("druck_bar"))
    v_lin = _num(params.get("geschwindigkeit_m_s"))
    tmax = _num(params.get("temp_max_c"))

    calc: Dict[str, Any] = {}
    if p_bar is not None and v_lin is not None:
        calc["pv_indicator_bar_ms"] = p_bar * v_lin

    flags: Dict[str, Any] = {}
    reqs: list[str] = []
    if p_bar is not None and p_bar >= 160:
        flags["extrusion_risk"] = True
        reqs.append("Stütz-/Back-up-Ring prüfen (≥160 bar).")

    mat_whitelist: list[str] = []
    if tmax is not None and tmax > 100:
        mat_whitelist.append("FKM")

    return {
        "calculated": calc,
        "flags": flags,
        "requirements": reqs,
        "material_whitelist": mat_whitelist,
        "material_blacklist": [],
    }

def calc_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Domänenspezifische Heuristiken ergänzen und mit derived mergen.
    Sendet ebenfalls einen calc_snapshot fürs UI.
    """
    domain = (state.get("domain") or "rwdr").strip().lower()
    params = dict(state.get("params") or {})
    derived_existing = dict(state.get("derived") or {})

    try:
        if domain == "hydraulics_rod":
            derived_new = _calc_hydraulics_rod(params)
        else:
            derived_new = _calc_rwdr(params)
    except Exception as e:
        log.warning("[calc_agent] calc_failed", exc=str(e))
        return {**state, "phase": "calc_agent"}

    derived_merged = _deep_merge(derived_existing, derived_new)

    v = (
        derived_merged.get("calculated", {}).get("umfangsgeschwindigkeit_m_s")
        or params.get("relativgeschwindigkeit_ms")
    )
    if v is not None:
        derived_merged["relativgeschwindigkeit_ms"] = v

    new_state = {**state, "derived": derived_merged, "phase": "calc_agent"}
    new_state["ui_event"] = {"ui_action": "calc_snapshot", "derived": derived_merged}
    return new_state

```


## backend/app/services/langgraph/graph/consult/nodes/deterministic_calc.py

```py
# backend/app/services/langgraph/graph/consult/nodes/deterministic_calc.py
from __future__ import annotations

import math
from typing import Any, Dict

def _to_float(x, default=None):
    try:
        if x is None or x == "" or x == "unknown":
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).replace(" ", "").replace(",", ".")
        return float(s)
    except Exception:
        return default

def _max_defined(*vals):
    for v in vals:
        if v is not None:
            return v
    return None

def deterministic_calc_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministische Kernberechnungen (kein LLM):
      - v, ω, p (bar/Pa/MPa), PV (bar·m/s / MPa·m/s)
      - optional Reibkraft & Reibleistung (falls Parameter vorhanden)
    Ergänzt state['derived'] nicht-destruktiv und sendet ein UI-Snapshot-Event.
    """
    params: Dict[str, Any] = dict(state.get("params") or {})
    derived: Dict[str, Any] = dict(state.get("derived") or {})

    d_mm   = _max_defined(_to_float(params.get("wellen_mm")), _to_float(params.get("stange_mm")))
    rpm    = _max_defined(_to_float(params.get("drehzahl_u_min")), _to_float(params.get("n_u_min")), _to_float(params.get("rpm")))
    v_ms   = _max_defined(_to_float(params.get("relativgeschwindigkeit_ms")), _to_float(params.get("geschwindigkeit_m_s")), _to_float(params.get("v_ms")))
    p_bar  = _max_defined(_to_float(params.get("druck_bar")), _to_float(params.get("pressure_bar")))
    width_mm = _to_float(params.get("width_mm"))
    mu     = _to_float(params.get("mu"))
    p_contact_mpa = _to_float(params.get("contact_pressure_mpa"))
    axial_force_n = _to_float(params.get("axial_force_n"))

    # v
    if v_ms is None and d_mm is not None and rpm is not None and d_mm > 0 and rpm > 0:
        v_ms = math.pi * (d_mm / 1000.0) * (rpm / 60.0)

    # ω
    omega = 2.0 * math.pi * (rpm / 60.0) if rpm is not None else None

    # p
    p_pa = p_mpa = None
    if p_bar is not None:
        p_pa = p_bar * 1e5
        p_mpa = p_bar / 10.0

    # PV
    pv_bar_ms = pv_mpa_ms = None
    if p_bar is not None and v_ms is not None:
        pv_bar_ms = p_bar * v_ms
        pv_mpa_ms = (p_bar / 10.0) * v_ms

    # Reibung/Leistung (Variante A: über Axialkraft)
    friction_force_n = friction_power_w = None
    if axial_force_n is not None and mu is not None and v_ms is not None:
        friction_force_n = mu * axial_force_n
        friction_power_w = friction_force_n * v_ms
    # Variante B: Kontaktpressung * Fläche
    elif (p_contact_mpa is not None) and (d_mm is not None) and (width_mm is not None) and (mu is not None) and (v_ms is not None):
        d_m = d_mm / 1000.0
        b_m = width_mm / 1000.0
        area_m2 = math.pi * d_m * b_m
        normal_force_n = (p_contact_mpa * 1e6) * area_m2
        friction_force_n = mu * normal_force_n
        friction_power_w = friction_force_n * v_ms

    # write back
    calc = dict(derived.get("calculated") or {})
    if v_ms is not None:
        calc["umfangsgeschwindigkeit_m_s"] = round(v_ms, 6)
        calc["surface_speed_m_s"] = round(v_ms, 6)
    if omega is not None:
        calc["omega_rad_s"] = round(omega, 6)
    if p_bar is not None:
        calc["p_bar"] = round(p_bar, 6)
    if p_pa is not None:
        calc["p_pa"] = round(p_pa, 3)
    if p_mpa is not None:
        calc["p_mpa"] = round(p_mpa, 6)
    if pv_bar_ms is not None:
        calc["pv_bar_ms"] = round(pv_bar_ms, 6)
    if pv_mpa_ms is not None:
        calc["pv_mpa_ms"] = round(pv_mpa_ms, 6)
    if friction_force_n is not None:
        calc["friction_force_n"] = round(friction_force_n, 6)
    if friction_power_w is not None:
        calc["friction_power_w"] = round(friction_power_w, 6)

    flags = dict(derived.get("flags") or {})
    warnings = list(derived.get("warnings") or [])
    if pv_mpa_ms is not None and pv_mpa_ms > 0.5:
        warnings.append(f"PV-Kennzahl hoch ({pv_mpa_ms:.3f} MPa·m/s) – Material/Profil prüfen.")

    new_derived = dict(derived)
    new_derived["calculated"] = calc
    new_derived["flags"] = flags
    new_derived["warnings"] = warnings

    # UI-Snapshot für Sidebar
    ui_event = {"ui_action": "calc_snapshot", "derived": new_derived}

    # Kompatibilitätsalias
    if v_ms is not None:
        new_derived["relativgeschwindigkeit_ms"] = v_ms

    return {**state, "derived": new_derived, "phase": "deterministic_calc", "ui_event": ui_event}

```


## backend/app/services/langgraph/graph/consult/nodes/explain.py

```py
# backend/app/services/langgraph/graph/consult/nodes/explain.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
import json
import structlog
from langchain_core.messages import AIMessage
from app.services.langgraph.prompting import render_template

log = structlog.get_logger(__name__)

def _top_sources(docs: List[Dict[str, Any]], k: int = 3) -> List[str]:
    if not docs:
        return []
    def _score(d: Dict[str, Any]) -> float:
        try:
            if d.get("fused_score") is not None:
                return float(d["fused_score"])
            return max(float(d.get("vector_score") or 0.0),
                       float(d.get("keyword_score") or 0.0) / 100.0)
        except Exception:
            return 0.0
    tops = sorted(docs, key=_score, reverse=True)[:k]
    out: List[str] = []
    for d in tops:
        src = d.get("source") or (d.get("metadata") or {}).get("source") or ""
        if src:
            out.append(str(src))
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq

def _emit_text(events: Optional[Callable[[Dict[str, Any]], None]],
               node: str, text: str, chunk_size: int = 180) -> None:
    if not events or not text:
        return
    for i in range(0, len(text), chunk_size):
        events({"type": "stream_text", "node": node, "text": text[i:i+chunk_size]})

def _last_ai_text(state: Dict[str, Any]) -> str:
    """Zieht den Text der letzten AIMessage (string oder tool-structured)."""
    msgs = state.get("messages") or []
    last_ai = None
    for m in reversed(msgs):
        t = (getattr(m, "type", "") or getattr(m, "role", "") or "").lower()
        if t in ("ai", "assistant"):
            last_ai = m
            break
    if not last_ai:
        return ""
    content = getattr(last_ai, "content", None)
    if isinstance(content, str):
        return content.strip()
    # LangChain kann Liste aus {"type":"text","text":"..."} liefern
    out_parts: List[str] = []
    if isinstance(content, list):
        for p in content:
            if isinstance(p, str):
                out_parts.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                out_parts.append(p["text"])
    return "\n".join(out_parts).strip()

def _parse_recommendation(text: str) -> Dict[str, Any]:
    """
    Akzeptiert:
      1) {"empfehlungen":[{typ, werkstoff, begruendung, vorteile, einschraenkungen, ...}, ...]}
      2) {"main": {...}, "alternativen": [...], "hinweise":[...]}
      3) {"text": "<JSON string>"}  -> wird rekursiv geparst
    """
    if not text:
        return {}

    def _loads_maybe(s: str):
        try:
            return json.loads(s)
        except Exception:
            return None

    obj = _loads_maybe(text)
    if isinstance(obj, dict) and "text" in obj and isinstance(obj["text"], str):
        obj2 = _loads_maybe(obj["text"])
        if isinstance(obj2, dict):
            obj = obj2

    if not isinstance(obj, dict):
        return {}

    # Form 2
    if "main" in obj or "alternativen" in obj:
        main = obj.get("main") or {}
        alternativen = obj.get("alternativen") or []
        hinweise = obj.get("hinweise") or []
        return {"main": main, "alternativen": alternativen, "hinweise": hinweise}

    # Form 1
    if isinstance(obj.get("empfehlungen"), list) and obj["empfehlungen"]:
        recs = obj["empfehlungen"]
        main = recs[0] if isinstance(recs[0], dict) else {}
        alternativen = [r for r in recs[1:] if isinstance(r, dict)]
        return {"main": main, "alternativen": alternativen, "hinweise": obj.get("hinweise") or []}

    return {}

def explain_node(state: Dict[str, Any], *, events: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    """
    Rendert die Empfehlung als freundliches Markdown (explain.jinja2),
    streamt Chunks (falls WS-Events übergeben werden) und hängt eine AIMessage an.
    Holt sich – falls nötig – main/alternativen automatisch aus der letzten AI-JSON.
    """
    params: Dict[str, Any] = state.get("params") or {}
    docs: List[Dict[str, Any]] = state.get("retrieved_docs") or state.get("docs") or []
    sources = _top_sources(docs, k=3)

    # Falls main/alternativen/hinweise fehlen, aus der letzten AI-Message extrahieren
    main = state.get("main") or {}
    alternativen = state.get("alternativen") or []
    hinweise = state.get("hinweise") or []
    if not main and not alternativen:
        parsed = _parse_recommendation(_last_ai_text(state))
        if parsed:
            main = parsed.get("main") or main
            alternativen = parsed.get("alternativen") or alternativen
            if not hinweise:
                hinweise = parsed.get("hinweise") or []

    md = render_template(
        "explain.jinja2",
        main=main or {},
        alternativen=alternativen or [],
        derived=state.get("derived") or {},
        hinweise=hinweise or [],
        params=params,
        sources=sources,
    ).strip()

    _emit_text(events, node="explain", text=md)

    msgs = (state.get("messages") or []) + [AIMessage(content=md)]
    return {
        **state,
        "main": main,
        "alternativen": alternativen,
        "hinweise": hinweise,
        "phase": "explain",
        "messages": msgs,
        "explanation": md,
        "retrieved_docs": docs,
    }

```


## backend/app/services/langgraph/graph/consult/nodes/intake.py

```py
# backend/app/services/langgraph/graph/consult/nodes/intake.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, AIMessage
from app.services.langgraph.prompting import (
    render_template,
    messages_for_template,
    strip_json_fence,
)
from ..utils import normalize_messages
# Vereinheitlichte LLM-Factory für Consult
from ..config import create_llm
# NEU: Frühe Pflichtfeldprüfung für sofortiges Sidebar-Open
from ..domain_runtime import missing_by_domain

log = logging.getLogger(__name__)

def intake_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analysiert die Eingabe, klassifiziert den Intent und extrahiert Parameter.
    Deterministischer Output: state['triage'], state['params'].
    Öffnet (falls Pflichtfelder fehlen) direkt die Sidebar-Form via ui_event.
    """
    msgs = normalize_messages(state.get("messages", []))
    params = dict(state.get("params") or {})

    prompt = render_template(
        "intake_triage.jinja2",
        messages=messages_for_template(msgs),
        params=params,
        params_json=json.dumps(params, ensure_ascii=False),
    )

    try:
        llm = create_llm(streaming=False)
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = strip_json_fence(getattr(resp, "content", "") or "")
        data = json.loads(raw)
    except Exception as e:
        log.warning("intake_node: parse_or_llm_error: %s", e, exc_info=True)
        data = {}

    intent = str((data.get("intent") or "unknown")).strip().lower()
    new_params = dict(params)
    if isinstance(data.get("params"), dict):
        for k, v in data["params"].items():
            if v not in (None, "", "unknown"):
                new_params[k] = v

    triage = {
        "intent": intent if intent in ("greeting", "smalltalk", "consult", "unknown") else "unknown",
        "confidence": 1.0 if intent in ("greeting", "smalltalk", "consult") else 0.0,
        "reply": "",
        "flags": {"source": "intake_triage"},
    }

    # ----- NEU: Sidebar sofort öffnen, wenn Kern-Pflichtfelder fehlen -----
    # einfache Domänenschätzung
    domain_guess = "hydraulics_rod" if any(k in new_params for k in ("stange_mm", "nut_d_mm", "nut_b_mm")) else "rwdr"
    missing = missing_by_domain(domain_guess, new_params)

    ui_event = None
    assistant_msg = None
    if missing:
        # Beispielzeile je Domain
        example = (
            "Stange 25, Nut D 32, Nut B 6, Medium Öl, Tmax 80, Druck 160 bar, v 0,3 m/s"
            if domain_guess == "hydraulics_rod"
            else "Welle 25, Gehäuse 47, Breite 7, Medium Öl, Tmax 80, Druck 2 bar, n 1500"
        )
        # Hinweistext (Template nutzt intern 'friendly_required', der bestehende ask_missing-Node
        # übergibt historisch 'friendly' – wir bleiben kompatibel)
        assistant_msg = AIMessage(
            content=render_template(
                "ask_missing.jinja2",
                domain=domain_guess,
                friendly=", ".join(missing),  # kompatibel zu bestehendem Template-Gebrauch
                example=example,
                lang="de",
            )
        )
        # UI-Event für das Frontend (Frontend lauscht auf sealai:ui_action/ui_event)
        ui_event = {
            "ui_action": "open_form",
            "form_id": f"{domain_guess}_params_v1",
            "schema_ref": f"domains/{domain_guess}/params@1.0.0",
            "missing": missing,
            "prefill": {k: v for k, v in new_params.items() if v not in (None, "", [])},
        }
        log.info("[intake_node] early_open_form domain=%s missing=%s", domain_guess, missing)

    return {
        "messages": ([assistant_msg] if assistant_msg else []),
        "params": new_params,
        "triage": triage,
        "phase": "intake",
        **({"ui_event": ui_event} if ui_event else {}),
    }

```


## backend/app/services/langgraph/graph/consult/nodes/lite_router.py

```py
# backend/app/services/langgraph/graph/consult/nodes/lite_router.py
from __future__ import annotations

import re
from typing import Any, Dict, List

from ..utils import normalize_messages

# (unverändert) Regexe …
RE_GREET = re.compile(
    r"\b(hi|hallo|hello|hey|servus|moin|grüß(?:e)?\s*dich|guten\s*(?:morgen|tag|abend))\b",
    re.I,
)
RE_SMALLTALK = re.compile(
    r"\b(wie\s+geht'?s|alles\s+gut|was\s+geht|na\s+du|danke|bitte|tschüss|ciao|bye)\b",
    re.I,
)
RE_TECH_HINT = re.compile(
    r"\b(rwdr|hydraulik|dichtung|welle|gehäuse|rpm|u\/min|bar|°c|tmax|werkstoff|profil|rag|query|bm25)\b",
    re.I,
)

def _join_user_text(msgs: List) -> str:
    out: List[str] = []
    for m in msgs:
        role = (getattr(m, "type", "") or getattr(m, "role", "")).lower()
        content = getattr(m, "content", "")
        if isinstance(m, dict):
            role = (m.get("type") or m.get("role") or "").lower()
            content = m.get("content")
        if role in ("human", "user") and isinstance(content, str) and content.strip():
            out.append(content.strip())
    return " ".join(out)

def _fallback_text_from_state(state: Dict[str, Any]) -> str:
    # NEU: WS/HTTP-Fallbacks wie im RAG-Node
    for k in ("input", "user_input", "question", "query"):
        v = state.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def lite_router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entscheidet, ob wir in Smalltalk verzweigen oder in den technischen Flow.
      - Gruß-/Smalltalk-Phrasen bei kurzen Texten → smalltalk
      - technische Stichwörter → default
      - sonst: sehr kurze Eingaben → smalltalk
    """
    msgs = normalize_messages(state.get("messages", []))
    text = _join_user_text(msgs)

    # NEU: wenn keine messages vorhanden, auf input/question/query zurückfallen
    if not text:
        text = _fallback_text_from_state(state)

    tlen = len(text)

    if not text:
        return {**state, "route": "default"}

    if RE_TECH_HINT.search(text):
        return {**state, "route": "default"}

    if RE_GREET.search(text) or RE_SMALLTALK.search(text):
        if tlen <= 64:
            return {**state, "route": "smalltalk"}

    if tlen <= 20:
        return {**state, "route": "smalltalk"}

    return {**state, "route": "default"}

```


## backend/app/services/langgraph/graph/consult/nodes/rag.py

```py
# backend/app/services/langgraph/graph/consult/nodes/rag.py
"""
RAG-Node: holt Hybrid-Treffer (Qdrant + Redis BM25), baut kompakten
Kontext-String und legt beides in den State (retrieved_docs/docs, context) ab.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import structlog

from .....rag import rag_orchestrator as ro  # relativer Import

log = structlog.get_logger(__name__)


def _extract_query(state: Dict[str, Any]) -> str:
    return (
        state.get("query")
        or state.get("question")
        or state.get("user_input")
        or state.get("input")
        or ""
    )


def _extract_tenant(state: Dict[str, Any]) -> Optional[str]:
    ctx = state.get("context") or {}
    return state.get("tenant") or (ctx.get("tenant") if isinstance(ctx, dict) else None)


def _context_from_docs(docs: List[Dict[str, Any]], max_chars: int = 1200) -> str:
    """Kompakter Textkontext für Prompting (inkl. Quelle)."""
    if not docs:
        return ""
    parts: List[str] = []
    for d in docs[:6]:
        t = (d.get("text") or "").strip()
        if not t:
            continue
        src = d.get("source") or (d.get("metadata") or {}).get("source")
        if src:
            t = f"{t}\n[source: {src}]"
        parts.append(t)
    ctx = "\n\n".join(parts)
    return ctx[:max_chars]


def run_rag_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Eingänge (optional):
      - query/question/user_input/input
      - tenant bzw. context.tenant
      - rag_filters, rag_k, rag_rerank
    Ausgänge:
      - retrieved_docs/docs: List[Dict[str, Any]]
      - context: str
    """
    query = _extract_query(state)
    tenant = _extract_tenant(state)
    filters = state.get("rag_filters") or None
    k = int(state.get("rag_k") or ro.FINAL_K)
    use_rerank = bool(state.get("rag_rerank", True))

    if not query.strip():
        return {**state, "retrieved_docs": [], "docs": [], "context": "", "phase": "rag"}

    docs = ro.hybrid_retrieve(
        query=query,
        tenant=tenant,
        k=k,
        metadata_filters=filters,
        use_rerank=use_rerank,
    )

    context = state.get("context")
    if not isinstance(context, str) or not context.strip():
        context = _context_from_docs(docs)

    out = {
        **state,
        "retrieved_docs": docs,
        "docs": docs,              # Alias für nachfolgende Nodes
        "context": context,
        "phase": "rag",
    }
    try:
        log.info("[rag_node] retrieved", n=len(docs), tenant=tenant or "-", ctx_len=len(context or ""))
    except Exception:
        pass
    return out


__all__ = ["run_rag_node"]

```


## backend/app/services/langgraph/graph/consult/nodes/recommend.py

```py
# backend/app/services/langgraph/graph/consult/nodes/recommend.py
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

import structlog
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig

from app.services.langgraph.prompting import (
    render_template,
    messages_for_template,
    strip_json_fence,
)
from app.services.langgraph.prompt_registry import get_agent_prompt
from ..utils import normalize_messages, last_user_text
from ..config import create_llm

log = structlog.get_logger(__name__)

_STREAM_CHUNK_CHARS = 160

def _extract_text_from_chunk(chunk) -> List[str]:
    out: List[str] = []
    if not chunk:
        return out
    c = getattr(chunk, "content", None)
    if isinstance(c, str) and c:
        out.append(c)
    elif isinstance(c, list):
        for part in c:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                out.append(part["text"])
    ak = getattr(chunk, "additional_kwargs", None)
    if isinstance(ak, dict):
        for k in ("delta", "content", "text", "token"):
            v = ak.get(k)
            if isinstance(v, str) and v:
                out.append(v)
    if isinstance(chunk, dict):
        for k in ("delta", "content", "text", "token"):
            v = chunk.get(k)
            if isinstance(v, str) and v:
                out.append(v)
    return out

def _extract_json_any(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if (s[:1] in "{[") and (s[-1:] in "}]"):
        return s
    s2 = strip_json_fence(s)
    if (s2[:1] in "{[") and (s2[-1:] in "}]"):
        return s2
    m = re.search(r"\{(?:[^{}]|(?R))*\}", s, re.S)
    if m:
        return m.group(0)
    m = re.search(r"\[(?:[^\[\]]|(?R))*\]", s, re.S)
    return m.group(0) if m else ""

def _parse_empfehlungen(raw: str) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    try:
        data = json.loads(strip_json_fence(raw))
        if isinstance(data, dict) and isinstance(data.get("empfehlungen"), list):
            return data["empfehlungen"]
    except Exception as e:
        log.warning("[recommend_node] json_parse_error", err=str(e))
    return None

_RX = {
    "typ": re.compile(r"(?im)^\s*Typ:\s*(.+?)\s*$"),
    "werkstoff": re.compile(r"(?im)^\s*Werkstoff:\s*(.+?)\s*$"),
    "vorteile": re.compile(
        r"(?is)\bVorteile:\s*(.+?)(?:\n\s*(?:Einschr[aä]nkungen|Begr[üu]ndung|Abgeleiteter|Alternativen)\b|$)"
    ),
    "einschraenkungen": re.compile(
        r"(?is)\bEinschr[aä]nkungen:\s*(.+?)(?:\n\s*(?:Begr[üu]ndung|Abgeleiteter|Alternativen)\b|$)"
    ),
    "begruendung": re.compile(
        r"(?is)\bBegr[üu]ndung:\s*(.+?)(?:\n\s*(?:Abgeleiteter|Alternativen)\b|$)"
    ),
}

def _split_items(s: str) -> List[str]:
    if not s:
        return []
    s = re.sub(r"[•\-\u2013\u2014]\s*", ", ", s)
    parts = re.split(r"[;,]\s*|\s{2,}", s.strip())
    return [p.strip(" .") for p in parts if p and not p.isspace()]

def _coerce_from_markdown(text: str) -> Optional[List[Dict[str, Any]]]:
    if not text:
        return None
    def _m(rx):
        m = rx.search(text)
        return (m.group(1).strip() if m else "")
    typ = _m(_RX["typ"])
    werkstoff = _m(_RX["werkstoff"])
    vorteile = _split_items(_m(_RX["vorteile"]))

    einschr = _split_items(_m(_RX["einschraenkungen"]))
    begr = _m(_RX["begruendung"])
    if not (typ or werkstoff or begr or vorteile or einschr):
        return None
    return [{
        "typ": typ or "",
        "werkstoff": werkstoff or "",
        "begruendung": begr or "",
        "vorteile": vorteile or [],
        "einschraenkungen": einschr or [],
        "geeignet_fuer": [],
    }]

def _context_from_docs(docs: List[Dict[str, Any]], max_chars: int = 1200) -> str:
    if not docs:
        return ""
    parts: List[str] = []
    for d in docs[:6]:
        t = (d.get("text") or "").strip()
        if not t:
            continue
        src = d.get("source") or (d.get("metadata") or {}).get("source")
        if src:
            t = f"{t}\n[source: {src}]"
        parts.append(t)
    ctx = "\n\n".join(parts)
    return ctx[:max_chars]

def _emit_stream_chunks(events: Optional[Callable[[Dict[str, Any]], None]], *, node: str, text: str) -> None:
    if not events or not text:
        return
    try:
        for i in range(0, len(text), _STREAM_CHUNK_CHARS):
            chunk = text[i : i + _STREAM_CHUNK_CHARS]
            if chunk:
                events({"type": "stream_text", "node": node, "text": chunk})
    except Exception as exc:
        log.debug("[recommend_node] stream_emit_failed", err=str(exc))


def recommend_node(
    state: Dict[str, Any],
    config: Optional[RunnableConfig] = None,
    *,
    events: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    # Falls noch Pflichtfelder fehlen, NICHT ins teure RAG/LLM gehen – stattdessen UI-Form öffnen
    missing = state.get("fehlend") or state.get("missing") or []
    if isinstance(missing, (list, tuple)) and len(missing) > 0:
        ui = {
            "ui_event": {
                "ui_action": "open_form",
                "form_id": "rwdr_params_v1",
                "schema_ref": "domains/rwdr/params@1.0.0",
                "missing": list(missing),
                "prefill": (state.get("params") or {})
            }
        }
        return {**state, **ui, "phase": "ask_missing"}

    msgs = normalize_messages(state.get("messages", []))
    params: Dict[str, Any] = state.get("params") or {}
    domain = (state.get("domain") or "").strip().lower()
    derived = state.get("derived") or {}
    retrieved_docs: List[Dict[str, Any]] = state.get("retrieved_docs") or []
    context = state.get("context") or _context_from_docs(retrieved_docs)
    if context:
        log.info("[recommend_node] using_context", n_docs=len(retrieved_docs), ctx_len=len(context))

    base_llm = create_llm(streaming=True)
    try:
        llm = base_llm.bind(response_format={"type": "json_object"})
    except Exception:
        llm = base_llm

    recent_user = (last_user_text(msgs) or "").strip()
    prompt = render_template(
        "recommend.jinja2",
        messages=messages_for_template(msgs),
        params=params,
        domain=domain,
        derived=derived,
        recent_user=recent_user,
        context=context,
    )

    effective_cfg: RunnableConfig = (config or {}).copy()  # type: ignore[assignment]
    if "run_name" not in (effective_cfg or {}):
        effective_cfg = {**effective_cfg, "run_name": "recommend"}  # type: ignore[dict-item]

    content_parts: List[str] = []
    try:
        for chunk in llm.with_config(effective_cfg).stream([
            SystemMessage(content=get_agent_prompt(domain or "rwdr")),
            SystemMessage(content=prompt),
        ]):
            texts = _extract_text_from_chunk(chunk)
            for piece in texts:
                _emit_stream_chunks(events, node="recommend", text=piece)
            content_parts.extend(texts)
    except Exception as e:
        log.warning("[recommend_node] stream_failed", err=str(e))
        try:
            resp = llm.invoke([
                SystemMessage(content=get_agent_prompt(domain or "rwdr")),
                SystemMessage(content=prompt),
            ], config=effective_cfg)
            final_text = getattr(resp, "content", "") or ""
            if final_text:
                _emit_stream_chunks(events, node="recommend", text=final_text)
            content_parts = [final_text]
        except Exception as e2:
            log.error("[recommend_node] invoke_failed", err=str(e2))
            payload = json.dumps({"empfehlungen": []}, ensure_ascii=False, separators=(",", ":"))
            _emit_stream_chunks(events, node="recommend", text=payload)
            ai_msg = AIMessage(content=payload)
            return {
                **state,
                "messages": msgs + [ai_msg],
                "answer": payload,
                "phase": "recommend",
                "empfehlungen": [],
                "retrieved_docs": retrieved_docs,
                "docs": retrieved_docs,
                "context": context,
            }

    raw = ("".join(content_parts) or "").strip()
    log.info("[recommend_node] stream_len", chars=len(raw))

    json_snippet = _extract_json_any(raw)
    recs = _parse_empfehlungen(json_snippet) or _parse_empfehlungen(raw)
    if not recs:
        recs = _coerce_from_markdown(raw)
    if not recs:
        recs = [{
            "typ": "",
            "werkstoff": "",
            "begruendung": (raw[:600] if raw else "Keine strukturierte Empfehlung erhalten."),
            "vorteile": [],
            "einschraenkungen": [],
            "geeignet_fuer": [],
        }]

    content_out = json.dumps({"empfehlungen": recs}, ensure_ascii=False, separators=(",", ":")).replace("\n", " ").strip()

    ai_msg = AIMessage(content=content_out)
    return {
        **state,
        "messages": msgs + [ai_msg],
        "answer": content_out,
        "phase": "recommend",
        "empfehlungen": recs,
        "retrieved_docs": retrieved_docs,
        "docs": retrieved_docs,
        "context": context,
    }

```


## backend/app/services/langgraph/graph/consult/nodes/smalltalk.py

```py
# backend/app/services/langgraph/graph/consult/nodes/smalltalk.py
from __future__ import annotations

import random
import re
from typing import Any, Dict, List

from ..utils import normalize_messages

RE_HELLO = re.compile(r"\b(hi|hallo|hello|hey|servus|moin)\b", re.I)
RE_HOWAREYOU = re.compile(r"wie\s+geht'?s|how\s+are\s+you", re.I)
RE_BYE = re.compile(r"\b(tsch(ü|u)ss|ciao|bye)\b", re.I)

GREETINGS = [
    "Hi! 👋 Wie kann ich dir helfen?",
    "Hallo! 😊 Was steht an?",
    "Servus! Was kann ich für dich tun?",
    "Moin! Womit kann ich dich unterstützen?",
]
HOW_ARE_YOU = [
    "Danke der Nachfrage – mir geht's gut! Wie kann ich dir helfen?",
    "Alles gut hier 🙌 Was brauchst du?",
    "Läuft! Sag gern, worum es geht.",
]
GOODBYES = [
    "Tschüss! 👋 Melde dich jederzeit wieder.",
    "Ciao! Bis zum nächsten Mal.",
    "Bis bald! 😊",
]


def _last_user_text(msgs: List) -> str:
    for m in reversed(msgs):
        role = (getattr(m, "type", "") or getattr(m, "role", "")).lower()
        content = getattr(m, "content", "")
        if isinstance(m, dict):
            role = (m.get("type") or m.get("role") or "").lower()
            content = m.get("content")
        if role in ("human", "user") and isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def smalltalk_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Leichte, determ. Smalltalk-Antwort ohne LLM.
    Antwort wird als Assistant-Message in `messages` gelegt; der Flow führt
    anschließend (per Edge) nach `respond`.
    """
    msgs = normalize_messages(state.get("messages", []))
    text = _last_user_text(msgs)

    if RE_BYE.search(text):
        reply = random.choice(GOODBYES)
    elif RE_HOWAREYOU.search(text):
        reply = random.choice(HOW_ARE_YOU)
    elif RE_HELLO.search(text):
        reply = random.choice(GREETINGS)
    else:
        reply = "Alles klar! 🙂 Womit kann ich dir helfen?"

    new_msgs = list(msgs) + [{"role": "assistant", "content": reply}]
    return {**state, "messages": new_msgs, "phase": "smalltalk_done"}

```


## backend/app/services/langgraph/graph/consult/nodes/validate.py

```py
# backend/app/services/langgraph/graph/consult/nodes/validate.py
from __future__ import annotations
from typing import Any, Dict


def _to_float(x: Any) -> Any:
    try:
        if isinstance(x, bool):
            return x
        return float(x)
    except Exception:
        return x


def validate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Leichter Parameter-Check/Normalisierung vor RAG.
    WICHTIG: Keine Berechnungen, kein Calculator-Aufruf – das macht calc_agent.
    """
    params = dict(state.get("params") or {})

    # numerische Felder best-effort in float wandeln
    for k in (
        "temp_max_c", "temp_min_c", "druck_bar", "drehzahl_u_min",
        "wellen_mm", "gehause_mm", "breite_mm",
        "relativgeschwindigkeit_ms",
        "tmax_c", "pressure_bar", "n_u_min", "rpm", "v_ms",
    ):
        if k in params and params[k] not in (None, "", []):
            params[k] = _to_float(params[k])

    # einfache Alias-Harmonisierung (falls Ziel noch leer)
    alias = {
        "tmax_c": "temp_max_c",
        "pressure_bar": "druck_bar",
        "n_u_min": "drehzahl_u_min",
        "rpm": "drehzahl_u_min",
        "v_ms": "relativgeschwindigkeit_ms",
    }
    for src, dst in alias.items():
        if (params.get(dst) in (None, "", [])) and (params.get(src) not in (None, "", [])):
            params[dst] = params[src]

    return {**state, "params": params, "phase": "validate"}

```


## backend/app/services/langgraph/graph/consult/nodes/validate_answer.py

```py
# backend/app/services/langgraph/graph/consult/nodes/validate_answer.py
from __future__ import annotations

import math
from typing import Any, Dict, List
import structlog

from ..state import ConsultState

log = structlog.get_logger(__name__)

def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except Exception:
        return 0.5

def _confidence_from_docs(docs: List[Dict[str, Any]]) -> float:
    """
    Grobe Konfidenzabschätzung aus RAG-Scores.
    Nutzt fused_score, sonst max(vector_score, keyword_score/100).
    Falls Score bereits [0..1], direkt verwenden – sonst sigmoid.
    """
    if not docs:
        return 0.15

    vals: List[float] = []
    for d in docs[:6]:
        vs = d.get("vector_score")
        ks = d.get("keyword_score")
        fs = d.get("fused_score")
        try:
            base = float(fs if fs is not None else max(float(vs or 0.0), float(ks or 0.0) / 100.0))
        except Exception:
            base = 0.0

        if 0.0 <= base <= 1.0:
            vals.append(base)
        else:
            vals.append(_sigmoid(base))

    conf = sum(vals) / max(1, len(vals))
    return max(0.05, min(0.98, conf))

def _top_source(d: Dict[str, Any]) -> str:
    return (d.get("source")
            or (d.get("metadata") or {}).get("source")
            or "")

def validate_answer(state: ConsultState) -> ConsultState:
    """
    Bewertet die Antwortqualität (Konfidenz/Quellen) und MERGT den State,
    ohne RAG-Felder zu verlieren.
    """
    retrieved_docs: List[Dict[str, Any]] = state.get("retrieved_docs") or state.get("docs") or []
    context: str = state.get("context") or ""

    conf = _confidence_from_docs(retrieved_docs)
    needs_more = bool(state.get("needs_more_params")) or conf < 0.35

    validation: Dict[str, Any] = {
        "n_docs": len(retrieved_docs),
        "confidence": round(conf, 3),
        "top_source": _top_source(retrieved_docs[0]) if retrieved_docs else "",
    }

    log.info(
        "validate_answer",
        confidence=validation["confidence"],
        needs_more_params=needs_more,
        n_docs=validation["n_docs"],
        top_source=validation["top_source"],
    )

    return {
        **state,
        "phase": "validate_answer",
        "validation": validation,
        "confidence": conf,
        "needs_more_params": needs_more,
        # explizit erhalten
        "retrieved_docs": retrieved_docs,
        "docs": retrieved_docs,
        "context": context,
    }

```


## backend/app/services/langgraph/graph/consult/state.py

```py
# backend/app/services/langgraph/graph/consult/state.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import Annotated
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


# ---- Parameter- & Derived-Typen -------------------------------------------------
class Parameters(TypedDict, total=False):
    # Kernparameter
    temp_max_c: float
    druck_bar: float
    drehzahl_u_min: float
    wellen_mm: float
    relativgeschwindigkeit_ms: float  # alias für geschwindigkeit_m_s
    geschwindigkeit_m_s: float
    # Hydraulik
    stange_mm: float
    nut_d_mm: float
    nut_b_mm: float
    # Aliasse / Harmonisierung
    tmax_c: float
    pressure_bar: float
    n_u_min: float
    rpm: float
    v_ms: float
    # optionale Filter/Routing
    material: str
    profile: str
    domain: str
    norm: str
    lang: str
    # optionale physikalische Parameter (falls bekannt; sonst werden optionale Berechnungen übersprungen)
    mu: float                     # Reibkoeffizient
    contact_pressure_mpa: float   # Kontaktpressung an der Dichtkante
    axial_force_n: float          # Axialkraft (Hydraulik)
    width_mm: float               # wirksame Dichtbreite (für Reib-/Leistungsabschätzung)


class Derived(TypedDict, total=False):
    # Allgemeine berechnete Größen
    surface_speed_m_s: float              # v
    umfangsgeschwindigkeit_m_s: float     # v (de)
    omega_rad_s: float                    # ω
    p_bar: float                          # Druck [bar]
    p_pa: float                           # Druck [Pa]
    p_mpa: float                          # Druck [MPa]
    pv_bar_ms: float                      # PV in bar·m/s
    pv_mpa_ms: float                      # PV in MPa·m/s
    # Optional – nur wenn genug Parameter vorliegen
    friction_force_n: float               # F_f = μ * N (wenn N/Kontaktpressung bekannt)
    friction_power_w: float               # P = F_f * v
    # Vorhandene Felder bleiben erhalten
    relativgeschwindigkeit_ms: float
    calculated: Dict[str, Any]
    flags: Dict[str, Any]
    warnings: List[str]
    requirements: List[str]


# ---- Graph-State ----------------------------------------------------------------
class ConsultState(TypedDict, total=False):
    # Dialog
    messages: Annotated[List[AnyMessage], add_messages]
    query: str

    # Parameter
    params: Parameters
    derived: Derived

    # Routing / Kontext
    user_id: Optional[str]
    tenant: Optional[str]
    domain: Optional[str]
    phase: Optional[str]
    consult_required: Optional[bool]

    # ---- UI/Frontend-Integration ----
    ui_event: Dict[str, Any]
    missing_fields: List[str]

    # --- RAG-Ergebnis ---
    retrieved_docs: List[Dict[str, Any]]
    context: str

    # Empfehlungen / Ergebnis
    empfehlungen: List[Dict[str, Any]]

    # Qualitäts-/Validierungsinfos
    validation: Dict[str, Any]
    confidence: float
    needs_more_params: bool

    # --- Legacy-Felder ---
    docs: List[Dict[str, Any]]
    citations: List[str]
    answer: Optional[str]

```


## backend/app/services/langgraph/graph/consult/utils.py

```py
# backend/app/services/langgraph/graph/consult/utils.py
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional

from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage, SystemMessage

log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Message utilities
# -------------------------------------------------------------------

def deserialize_message(x: Any) -> AnyMessage:
    """Robuste Konvertierung nach LangChain-Message-Objekten."""
    if isinstance(x, (HumanMessage, AIMessage, SystemMessage)):
        return x
    if isinstance(x, dict) and "role" in x:
        role = (x.get("role") or "").lower()
        content = x.get("content") or ""
        if role in ("user", "human"):
            return HumanMessage(content=content)
        if role in ("assistant", "ai"):
            return AIMessage(content=content)
        if role == "system":
            return SystemMessage(content=content)
    if isinstance(x, str):
        return HumanMessage(content=x)
    return HumanMessage(content=str(x))


def normalize_messages(seq: Iterable[Any]) -> List[AnyMessage]:
    return [deserialize_message(m) for m in (seq or [])]


def merge_messages(left: Iterable[Any], right: Iterable[Any]) -> List[AnyMessage]:
    return add_messages(normalize_messages(left), normalize_messages(right))


def last_user_text(msgs: List[AnyMessage]) -> str:
    for m in reversed(msgs or []):
        if isinstance(m, HumanMessage):
            return (m.content or "").strip()
    return ""


def messages_text(msgs: List[AnyMessage], *, only_user: bool = False) -> str:
    """
    Verkettet Text aller Messages.
    - only_user=True -> nur HumanMessage.
    """
    parts: List[str] = []
    for m in msgs or []:
        if only_user and not isinstance(m, HumanMessage):
            continue
        c = getattr(m, "content", None)
        if isinstance(c, str) and c:
            parts.append(c)
    return "\n".join(parts)

# Kompatibilitäts-Alias (einige Module importieren 'msgs_text')
msgs_text = messages_text

def only_user_text(msgs: List[AnyMessage]) -> str:
    """Nur die User-Texte zusammengefasst (ohne Lowercasing)."""
    return messages_text(msgs, only_user=True)

def only_user_text_lower(msgs: List[AnyMessage]) -> str:
    """Nur die User-Texte, zu Kleinbuchstaben normalisiert."""
    return only_user_text(msgs).lower()

# -------------------------------------------------------------------
# Numeric parsing & heuristics
# -------------------------------------------------------------------

def _num_from_str(raw: str) -> Optional[float]:
    """Float aus Strings wie '1 200,5' oder '1.200,5' oder '1200.5' extrahieren."""
    try:
        s = (raw or "").replace(" ", "").replace(".", "").replace(",", ".")
        return float(s)
    except Exception:
        return None


def apply_heuristics_from_text(params: Dict[str, Any], text: str) -> Dict[str, Any]:
    """
    Deterministische Fallbacks, falls das LLM Werte nicht gesetzt hat:
      - 'kein/ohne Überdruck/Druck' -> druck_bar = 0
      - '... Druck: 5 bar'          -> druck_bar = 5
      - 'Drehzahl 1.200 U/min'      -> drehzahl_u_min = 1200
      - 'dauerhaft X U/min'         -> drehzahl_u_min = X
      - 'Geschwindigkeit 0.5 m/s'   -> geschwindigkeit_m_s = 0.5
    """
    t = (text or "").lower()
    merged: Dict[str, Any] = dict(params or {})

    # Druck
    if merged.get("druck_bar") in (None, "", "unknown"):
        if re.search(r"\b(kein|ohne)\s+(überdruck|ueberdruck|druck)\b", t, re.I):
            merged["druck_bar"] = 0.0
        else:
            m = re.search(r"(?:überdruck|ueberdruck|druck)\s*[:=]?\s*([0-9][\d\.\s,]*)\s*bar\b", t, re.I)
            if m:
                val = _num_from_str(m.group(1))
                if val is not None:
                    merged["druck_bar"] = val

    # Drehzahl (generisch)
    if merged.get("drehzahl_u_min") in (None, "", "unknown"):
        m = re.search(r"drehzahl[^0-9]{0,12}([0-9][\d\.\s,]*)\s*(?:u\s*/?\s*min|rpm)\b", t, re.I)
        if m:
            val = _num_from_str(m.group(1))
            if val is not None:
                merged["drehzahl_u_min"] = int(round(val))

    # Spezifisch „dauerhaft“
    m_dauer = re.search(
        r"(dauerhaft|kontinuierlich)[^0-9]{0,12}([0-9][\d\.\s,]*)\s*(?:u\s*/?\s*min|rpm)\b",
        t,
        re.I,
    )
    if m_dauer:
        val = _num_from_str(m_dauer.group(2))
        if val is not None:
            merged["drehzahl_u_min"] = int(round(val))

    # Relativgeschwindigkeit in m/s
    if merged.get("geschwindigkeit_m_s") in (None, "", "unknown"):
        m_speed = re.search(r"(geschwindigkeit|v)[^0-9]{0,12}([0-9][\d\.\s,]*)\s*m\s*/\s*s", t, re.I)
        if m_speed:
            val = _num_from_str(m_speed.group(2))
            if val is not None:
                merged["geschwindigkeit_m_s"] = float(val)

    return merged

# -------------------------------------------------------------------
# Validation & anomaly messages
# -------------------------------------------------------------------

def _is_missing_value(key: str, val: Any) -> bool:
    if val is None or val == "" or val == "unknown":
        return True
    # 0 bar ist gültig
    if key == "druck_bar":
        try:
            float(val)
            return False
        except Exception:
            return True
    # Positive Größen brauchen > 0
    if key in (
        "wellen_mm", "gehause_mm", "breite_mm", "drehzahl_u_min", "geschwindigkeit_m_s",
        "stange_mm", "nut_d_mm", "nut_b_mm"
    ):
        try:
            return float(val) <= 0
        except Exception:
            return True
    # temp_max_c: nur presence check
    if key == "temp_max_c":
        try:
            float(val)
            return False
        except Exception:
            return True
    return False


def _required_fields_by_domain(domain: str) -> List[str]:
    # Hydraulik-Stange nutzt stange_mm / nut_d_mm / nut_b_mm
    if (domain or "rwdr") == "hydraulics_rod":
        return [
            "falltyp",
            "stange_mm",
            "nut_d_mm",
            "nut_b_mm",
            "medium",
            "temp_max_c",
            "druck_bar",
            "geschwindigkeit_m_s",
        ]
    # default: rwdr
    return [
        "falltyp",
        "wellen_mm",
        "gehause_mm",
        "breite_mm",
        "medium",
        "temp_max_c",
        "druck_bar",
        "drehzahl_u_min",
    ]


def _missing_by_domain(domain: str, params: Dict[str, Any]) -> List[str]:
    req = _required_fields_by_domain(domain or "rwdr")
    return [k for k in req if _is_missing_value(k, (params or {}).get(k))]

# Öffentlicher Alias (Pflicht)
missing_by_domain = _missing_by_domain

# ---------- Optional/empfohlen ----------
# Domänenspezifische Empfehl-Felder, die Qualität/Tragfähigkeit deutlich erhöhen
_RWDR_OPTIONAL = [
    "bauform", "werkstoff_pref",
    "welle_iso", "gehause_iso",
    "ra_welle_um", "rz_welle_um",
    "wellenwerkstoff", "gehausewerkstoff",
    "normen", "umgebung", "prioritaet", "besondere_anforderungen", "bekannte_probleme",
]
_HYD_OPTIONAL = [
    "profil", "werkstoff_pref",
    "stange_iso", "nut_toleranz",
    "ra_stange_um", "rz_stange_um",
    "stangenwerkstoff",
    "normen", "umgebung", "prioritaet", "besondere_anforderungen", "bekannte_probleme",
]

def _is_unset(x: Any) -> bool:
    return x in (None, "", [], "unknown")

def optional_missing_by_domain(domain: str, params: Dict[str, Any]) -> List[str]:
    p = params or {}
    fields = _HYD_OPTIONAL if (domain or "") == "hydraulics_rod" else _RWDR_OPTIONAL
    missing: List[str] = []
    for k in fields:
        if _is_unset(p.get(k)):
            missing.append(k)
    return missing

# ---- Anomalie-/Follow-up-Meldungen (FEHLTE zuvor!) --------------------------

def _anomaly_messages(domain: str, params: Dict[str, Any], derived: Dict[str, Any]) -> List[str]:
    """
    Erzeugt Rückfragen basierend auf abgeleiteten Flags (domainabhängig).
    Erwartet 'derived' z. B.: {"flags": {...}, "warnings": [...], "requirements": [...]}
    """
    msgs: List[str] = []
    flags = (derived.get("flags") or {})

    # RWDR – Druckstufenfreigabe
    if flags.get("requires_pressure_stage") and not flags.get("pressure_stage_ack"):
        msgs.append(
            "Ein Überdruck >2 bar ist für Standard-Radialdichtringe kritisch. "
            "Dürfen Druckstufenlösungen geprüft werden?"
        )

    # Hohe Drehzahl/Geschwindigkeit
    if flags.get("speed_high"):
        msgs.append("Die Drehzahl/Umfangsgeschwindigkeit ist hoch – ist sie dauerhaft oder nur kurzzeitig (Spitzen)?")

    # Sehr hohe Temperatur
    if flags.get("temp_very_high"):
        msgs.append("Die Temperatur ist sehr hoch. Handelt es sich um Dauer- oder Spitzentemperaturen?")

    # Hydraulik Stange – Extrusions-/Back-up-Ring-Freigabe
    if (domain or "") == "hydraulics_rod" and flags.get("extrusion_risk") and not flags.get("extrusion_risk_ack"):
        msgs.append("Bei dem Druck besteht Extrusionsrisiko. Darf eine Stütz-/Back-up-Ring-Lösung geprüft werden?")

    return msgs

# --- Output-Cleaner etc. (unverändert) --------------------------------------

def _strip(s: str) -> str:
    return (s or "").strip()

def _normalize_newlines(text: str) -> str:
    """Normalisiert Zeilenenden und trimmt überflüssige Leerzeichen am Zeilenende."""
    if not isinstance(text, str):
        return text
    t = re.sub(r"\r\n?|\r", "\n", text)
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    return t

def strip_leading_meta_blocks(text: str) -> str:
    """
    Entfernt am *Anfang* der Antwort Meta-Blöcke wie:
      - führende JSON-/YAML-Objekte
      - ```…``` fenced code blocks
      - '# QA-Notiz …' bis zur nächsten Leerzeile
    Wir iterieren, bis kein solcher Block mehr vorne steht.
    """
    if not isinstance(text, str) or not text.strip():
        return text
    t = text.lstrip()

    changed = True
    # max. 5 Durchläufe als Sicherung
    for _ in range(5):
        if not changed:
            break
        changed = False

        # Fenced code block (beliebiges fence, inkl. json/yaml)
        m = re.match(r"^\s*```[\s\S]*?```\s*", t)
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue

        # Führendes JSON-/YAML-Objekt (heuristisch, nicht perfekt balanciert)
        m = re.match(r"^\s*\{[\s\S]*?\}\s*(?=\n|$)", t)
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue
        m = re.match(r"^\s*---[\s\S]*?---\s*(?=\n|$)", t)  # YAML frontmatter
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue

        # QA-Notiz-Block bis zur nächsten Leerzeile
        m = re.match(r"^\s*#\s*QA-Notiz[^\n]*\n[\s\S]*?(?:\n\s*\n|$)", t, flags=re.IGNORECASE)
        if m:
            t = t[m.end():].lstrip()
            changed = True
            continue

    return t

def clean_ai_output(ai_text: str, recent_user_texts: List[str]) -> str:
    """
    Entfernt angehängte Echos zuletzt gesagter User-Texte am Ende der AI-Ausgabe.
    - vergleicht trim-normalisiert (Suffix)
    - entfernt ganze trailing Blöcke, falls sie exakt einem der recent_user_texts entsprechen
    """
    if not isinstance(ai_text, str) or not ai_text:
        return ai_text

    out = ai_text.rstrip()

    # Prüfe Kandidaten in abnehmender Länge (stabil gegen Teilmengen)
    for u in sorted(set(recent_user_texts or []), key=len, reverse=True):
        u_s = _strip(u)
        if not u_s:
            continue

        # Work on a normalized working copy for suffix check
        norm_out = _strip(out)
        if norm_out.endswith(u_s):
            # schneide die letzte (nicht-normalisierte) Vorkommen-Stelle am Ende ab
            raw_idx = out.rstrip().rfind(u_s)
            if raw_idx != -1:
                out = out[:raw_idx].rstrip()

    return out

def _norm_key(block: str) -> str:
    """Normierungs-Schlüssel für Block-Vergleich (whitespace-/case-insensitiv)."""
    return re.sub(r"\s+", " ", (block or "").strip()).lower()

def dedupe_text_blocks(text: str) -> str:
    """
    Entfernt doppelte inhaltlich identische Absätze/Blöcke, robust gegen CRLF
    und gemischte Leerzeilen. Als Absatztrenner gilt: ≥1 (auch nur whitespace-) Leerzeile.
    Zusätzlich werden identische, aufeinanderfolgende Einzelzeilen entfernt.
    """
    if not isinstance(text, str) or not text.strip():
        return text

    t = _normalize_newlines(text)

    # Absätze anhand *mindestens* einer Leerzeile trennen (auch wenn nur Whitespace in der Leerzeile steht)
    parts = [p.strip() for p in re.split(r"\n\s*\n+", t.strip()) if p.strip()]

    seen = set()
    out_blocks = []
    for p in parts:
        k = _norm_key(p)
        if k in seen:
            continue
        seen.add(k)
        out_blocks.append(p)

    # Zusammensetzen mit Leerzeile zwischen Absätzen
    merged = "\n\n".join(out_blocks)

    # Zusätzlicher Schutz: identische direkt aufeinanderfolgende Zeilen entfernen
    final_lines = []
    prev_key = None
    for line in merged.split("\n"):
        key = _norm_key(line)
        if key and key == prev_key:
            continue
        final_lines.append(line)
        prev_key = key

    return "\n".join(final_lines)

def clean_and_dedupe(ai_text: str, recent_user_texts: List[str]) -> str:
    """
    Reihenfolge:
      1) Führende Meta-Blöcke entfernen
      2) Trailing User-Echos abschneiden
      3) Identische Absätze/Zeilen de-dupen
    """
    head_clean = strip_leading_meta_blocks(ai_text)
    tail_clean = clean_ai_output(head_clean, recent_user_texts)
    return dedupe_text_blocks(tail_clean)

# Öffentlicher Alias
anomaly_messages = _anomaly_messages

```


## backend/app/services/langgraph/graph/intent_router.py

```py
# backend/app/services/langgraph/graph/intent_router.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Literal, Sequence

from ..prompting import render_template
from app.services.langgraph.llm_router import get_router_llm, get_router_fallback_llm
from langchain_core.messages import HumanMessage

_TEMPLATE_FILE = "intent_router.jinja2"

# Fast-Path Regex für Selektionsfälle (Material/Typ/Bauform/RWDR/Hydraulik & Maße)
_FAST_SELECT_RX = re.compile(
    r"(?i)\b(rwdr|wellendichtring|bauform\s*[a-z0-9]{1,4}|hydraulik|stangendichtung|kolbenstange|nut\s*[db]|"
    r"\d{1,3}\s*[x×/]\s*\d{1,3}\s*[x×/\-]?\s*\d{1,3}|material\s*(wahl|auswahl|empfehlung)|"
    r"(ptfe|nbr|hnbr|fk[mh]|epdm)\b)"
)

def _last_user_text(messages: Sequence[Any]) -> str:
    if not messages:
        return ""
    for m in reversed(messages):
        content = getattr(m, "content", None)
        if content:
            return str(content)
        if isinstance(m, dict):
            c = m.get("content") or m.get("text") or m.get("message")
            if c:
                return str(c)
    return ""

def _strip_json_fence(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip().strip("`").strip()

def _conf_min() -> float:
    try:
        return float(os.getenv("INTENT_CONF_MIN", "0.60"))
    except Exception:
        return 0.60

def classify_intent(_: Any, messages: Sequence[Any]) -> Literal["material_select", "llm"]:
    """
    LLM-first Routing:
      - "material_select": Graph (Selektions-Workflow) verwenden
      - "llm": Direkter LLM-Stream (Erklärung/Smalltalk/Wissen)
    """
    user_text = _last_user_text(messages).strip()

    # 1) Fast-Path (regex)
    if _FAST_SELECT_RX.search(user_text):
        return "material_select"

    # 2) Router-LLMs
    router = get_router_llm()
    fallback = get_router_fallback_llm()
    prompt = render_template(_TEMPLATE_FILE, input_text=user_text)

    def _ask(llm) -> tuple[str, float]:
        resp = llm.invoke([HumanMessage(content=prompt)])
        content = getattr(resp, "content", None) or str(resp)
        raw = _strip_json_fence(content)
        data = json.loads(raw)
        intent = str(data.get("intent") or "").strip().lower()
        conf = float(data.get("confidence") or 0.0)
        return intent, conf

    try:
        intent, conf = _ask(router)
    except Exception:
        try:
            intent, conf = _ask(fallback)
        except Exception:
            # fail-open zu material_select, damit echte Selektionsfälle nie „untergehen“
            return "material_select"

    if conf < _conf_min():
        try:
            i2, c2 = _ask(fallback)
            if c2 >= conf:
                intent, conf = i2, c2
        except Exception:
            pass

    if intent == "llm" and conf >= _conf_min():
        return "llm"
    return "material_select"

```


## backend/app/services/langgraph/graph/nodes/__init__.py

```py

```


## backend/app/services/langgraph/graph/nodes/deterministic.py

```py
from __future__ import annotations
from typing import Dict, Any
from math import pi

def intake_validate(state: Dict[str, Any]) -> Dict[str, Any]:
    p = state.get("params", {}) or {}
    missing = []
    for k in ("medium", "pressure_bar", "temp_max_c"):
        if p.get(k) is None:
            missing.append(k)
    if state.get("mode") == "consult" and p.get("speed_rpm") is None:
        missing.append("speed_rpm")
    state.setdefault("derived", {}).setdefault("notes", [])
    if missing:
        state.setdefault("ui_events", []).append({
            "ui_action": "open_form",
            "payload": {"form_id": "rwdr_params_v1", "missing": missing, "prefill": p}
        })
    return state

def _v_m_s(d_mm: float, rpm: float) -> float:
    return pi * (d_mm/1000.0) * (rpm/60.0)

def _dn(d_mm: float, rpm: float) -> float:
    return d_mm * rpm

def calc_core(state: Dict[str, Any]) -> Dict[str, Any]:
    p = state.get("params", {}) or {}
    d = state.get("derived", {}) or {}
    shaft = p.get("shaft_d")
    rpm = p.get("speed_rpm")
    pressure = p.get("pressure_bar")
    if shaft and rpm:
        v = _v_m_s(shaft, rpm)
        d["v_m_s"] = round(v, 4)
        d["dn_value"] = round(_dn(shaft, rpm), 2)
    if pressure and "v_m_s" in d:
        d["pv_indicator_bar_ms"] = round(float(pressure) * float(d["v_m_s"]), 4)
    state["derived"] = d
    return state

def calc_advanced(state: Dict[str, Any]) -> Dict[str, Any]:
    p = state.get("params", {}) or {}
    notes = state.setdefault("derived", {}).setdefault("notes", [])
    if p.get("temp_max_c", 0) > 200:
        notes.append("Hohe Temperatur: Fluorpolymere prüfen.")
    if (p.get("pressure_bar") or 0) > 5:
        notes.append("Druck > 5 bar: Stützelement/Extrusionsschutz prüfen.")
    return state

```


## backend/app/services/langgraph/graph/nodes/explain_nodes.py

```py
from __future__ import annotations
from typing import Dict, Any
from app.services.langgraph.policies.model_routing import RoutingContext, llm_params_for, should_use_llm
from app.services.langgraph.llm_factory import get_llm

def explain(state: Dict[str, Any]) -> Dict[str, Any]:
    if not should_use_llm("explain"):
        return state
    ctx = RoutingContext(
        node="explain",
        confidence=state.get("confidence"),
        red_flags=bool(state.get("red_flags")),
        regulatory=bool(state.get("regulatory")),
    )
    llm_cfg = llm_params_for("explain", ctx)
    # sanitize unsupported kwargs
    llm_cfg.pop("top_p", None)
    llm = get_llm(**llm_cfg)

    params = state.get("params", {})
    derived = state.get("derived", {})
    sources = state.get("sources", [])
    prompt = (
        "Erkläre die Auswahlkriterien kurz und sachlich. Nutze nur PARAMS, abgeleitete Werte und Quellen. "
        "Keine Produkte, keine Entscheidungen. Quellen benennen.\n"
        f"PARAMS: {params}\nDERIVED: {derived}\nSOURCES: {sources}\n"
        "Gib 3–6 Sätze."
    )
    msg = llm.invoke([{"role": "user", "content": prompt}])
    state.setdefault("messages", []).append({"role": "assistant", "content": msg.content})
    return state

```


## backend/app/services/langgraph/graph/nodes/rag_nodes.py

```py
from __future__ import annotations
from typing import Dict, Any, List
from datetime import date
from app.services.langgraph.tools.telemetry import telemetry, PARTNER_COVERAGE, NO_MATCH_RATE

def rag_retrieve(state: Dict[str, Any]) -> Dict[str, Any]:
    cands = state.get("candidates") or []
    state["sources"] = state.get("sources") or []
    state.setdefault("telemetry", {})["candidates_total"] = len(cands)
    return state

def _is_partner(c: Dict[str, Any]) -> bool:
    tier = (c.get("paid_tier") or "none").lower()
    active = bool(c.get("active", False))
    valid_until = (c.get("contract_valid_until") or "")
    try:
        y, m, d = map(int, valid_until.split("-"))
        ok_date = date(y, m, d) >= date.today()
    except Exception:
        ok_date = False
    return tier != "none" and active and ok_date

def partner_only_filter(state: Dict[str, Any]) -> Dict[str, Any]:
    cands: List[Dict[str, Any]] = state.get("candidates") or []
    partners = [c for c in cands if _is_partner(c)]
    state["candidates"] = partners
    total = state.get("telemetry", {}).get("candidates_total", 0)
    coverage = (len(partners) / total) if total else 0.0
    telemetry.set_gauge(PARTNER_COVERAGE, coverage)
    if not partners:
        state.setdefault("ui_events", []).append({"ui_action": "no_partner_available", "payload": {}})
        telemetry.incr(NO_MATCH_RATE, 1)
    return state

def rules_filter(state: Dict[str, Any]) -> Dict[str, Any]:
    return state

```


## backend/app/services/langgraph/graph/nodes/rfq_nodes.py

```py
from __future__ import annotations
from typing import Dict, Any
from datetime import datetime
import os, uuid
from app.services.langgraph.pdf.rfq_renderer import generate_rfq_pdf
from app.services.langgraph.tools.telemetry import telemetry, RFQ_GENERATED
from app.services.langgraph.tools.ui_events import UI, make_event

def decision_ready(state: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("ui_events", []).append(make_event(UI["DECISION_READY"], summary={
        "params": state.get("params"),
        "derived": state.get("derived"),
        "candidate_count": len(state.get("candidates") or []),
    }))
    return state

def await_user_action(state: Dict[str, Any]) -> Dict[str, Any]:
    return state

def generate_rfq_pdf_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("user_action") != "export_pdf":
        return state
    out_dir = os.getenv("RFQ_PDF_DIR", "/app/data/rfq")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"rfq_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}.pdf"
    path = os.path.join(out_dir, fname)
    payload = {
        "params": state.get("params"),
        "derived": state.get("derived"),
        "candidates": state.get("candidates"),
        "sources": state.get("sources"),
        "legal_notice": "Verbindliche Eignungszusage obliegt dem Hersteller.",
    }
    generate_rfq_pdf(payload, path)
    state["rfq_pdf"] = {"path": path, "created_at": datetime.utcnow().isoformat() + "Z", "download_token": uuid.uuid4().hex}
    telemetry.incr(RFQ_GENERATED, 1)
    return state

def deliver_pdf(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("rfq_pdf"):
        state.setdefault("ui_events", []).append(make_event(UI["RFQ_READY"], pdf=state["rfq_pdf"]))
    return state

```


## backend/app/services/langgraph/graph/sealai_consult_flow.py

```py
# backend/app/services/langgraph/graph/sealai_consult_flow.py
from __future__ import annotations

import os
import logging

from .consult.io import invoke_consult as _invoke_consult_single

log = logging.getLogger(__name__)

_SUP_AVAILABLE = True
try:
    from .supervisor_graph import invoke_consult_supervisor as _invoke_consult_supervisor
except Exception as e:
    _SUP_AVAILABLE = False
    log.warning("Supervisor graph not available, falling back to single-agent: %s", e)

_MODE = os.getenv("CONSULT_MODE", "consult").strip().lower()

def invoke_consult(prompt: str, *, thread_id: str) -> str:
    use_supervisor = (_MODE == "supervisor" and _SUP_AVAILABLE)
    if use_supervisor:
        try:
            return _invoke_consult_supervisor(prompt, thread_id=thread_id)
        except Exception as e:
            log.exception("Supervisor failed, falling back to single-agent: %s", e)
    return _invoke_consult_single(prompt, thread_id=thread_id)

```


## backend/app/services/langgraph/graph/state.py

```py
from __future__ import annotations
from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import Annotated
from langgraph.graph import add_messages

class Params(TypedDict, total=False):
    shaft_d: float
    housing_d: float
    width: float
    medium: str
    pressure_bar: float
    temp_min_c: float
    temp_max_c: float
    speed_rpm: float

class Derived(TypedDict, total=False):
    v_m_s: float
    dn_value: float
    pv_indicator_bar_ms: float
    notes: List[str]

class Candidate(TypedDict, total=False):
    doc_id: str
    vendor_id: str
    title: str
    profile: str
    material: str
    paid_tier: str
    contract_valid_until: str
    active: bool
    score: float
    url: Optional[str]

class RFQPdfInfo(TypedDict, total=False):
    path: str
    created_at: str
    download_token: str

class UIEvent(TypedDict, total=False):
    ui_action: str
    payload: Dict[str, Any]

class SealAIState(TypedDict, total=False):
    messages: Annotated[List[Any], add_messages]
    mode: str
    params: Params
    derived: Derived
    candidates: List[Candidate]
    sources: List[Dict[str, Any]]
    user_action: Optional[str]
    rfq_pdf: Optional[RFQPdfInfo]
    ui_events: List[UIEvent]
    telemetry: Dict[str, Any]
    confidence: Optional[float]
    red_flags: bool
    regulatory: bool

```


## backend/app/services/langgraph/graph/supervisor_graph.py

```py
from __future__ import annotations

import logging
from typing import TypedDict, List, Literal, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph
from langgraph.constants import END
from langchain_core.runnables import RunnableLambda

from app.services.langgraph.tools import long_term_memory as ltm
from .intent_router import classify_intent
from .consult.build import build_consult_graph
from app.services.langgraph.llm_factory import get_llm

log = logging.getLogger(__name__)

@tool
def ltm_search(query: str) -> str:
    """Durchsucht das Long-Term-Memory (Qdrant) nach relevanten Erinnerungen (MMR, top-k=5) und gibt einen zusammenhängenden Kontext-Text zurück."""
    ctx, _hits = ltm.ltm_query(query, strategy="mmr", top_k=5)
    return ctx or "Keine relevanten Erinnerungen gefunden."

@tool
def ltm_store(user: str, chat_id: str, text: str, kind: str = "note") -> str:
    """Speichert einen Text-Schnipsel im Long-Term-Memory (Qdrant). Parameter: user, chat_id, text, kind."""
    try:
        pid = ltm.upsert_memory(user=user, chat_id=chat_id, text=text, kind=kind)
        return f"Memory gespeichert (ID={pid})"
    except Exception as e:
        return f"Fehler beim Speichern: {e}"

TOOLS = [ltm_search, ltm_store]

class ChatState(TypedDict, total=False):
    messages: List[BaseMessage]
    intent: Literal["consult", "chitchat"]

def create_llm() -> ChatOpenAI:
    # LLM aus Factory – mit streaming=True
    return get_llm(streaming=True)

def build_chat_builder(llm: Optional[ChatOpenAI] = None) -> StateGraph:
    """Supervisor-Graph mit echtem Streaming:
    - chitchat als Runnable-Chain (liefert on_chat_model_stream)
    - consult als eingebetteter Subgraph (Events werden durchgereicht)
    """
    log.info("[supervisor] Initialisiere…")
    builder = StateGraph(ChatState)

    base_llm = llm or create_llm()          # streaming=True
    llm_chitchat = base_llm.bind_tools(TOOLS)

    # Consult **als Subgraph** (NICHT kompilieren/aufrufen)
    consult_graph = build_consult_graph()

    # Router
    def router_node(state: ChatState) -> ChatState:
        intent = classify_intent(base_llm, state.get("messages", []))
        return {"intent": intent}

    # Chitchat als Runnable-Chain → erzeugt on_chat_model_stream Events
    def _pick_msgs(s: ChatState):
        return s.get("messages", [])

    def _wrap_msg(m):
        ai = m if isinstance(m, AIMessage) else AIMessage(content=getattr(m, "content", str(m)))
        return {"messages": [ai]}

    chitchat_chain = RunnableLambda(_pick_msgs) | llm_chitchat | RunnableLambda(_wrap_msg)

    builder.add_node("router", router_node)
    builder.add_node("chitchat", chitchat_chain)
    builder.add_node("consult", consult_graph)

    builder.set_entry_point("router")

    def decide(state: ChatState) -> str:
        intent = state.get("intent") or "chitchat"
        return "consult" if intent == "consult" else "chitchat"

    builder.add_conditional_edges("router", decide, {"consult": "consult", "chitchat": "chitchat"})
    builder.add_edge("consult", END)
    builder.add_edge("chitchat", END)

    log.info("[supervisor] Bereit (Streaming aktiviert).")
    return builder

def build_supervisor_graph(llm: Optional[ChatOpenAI] = None) -> StateGraph:
    """Wrapper für chat_ws._ensure_graph(): liefert einen *uncompilierten* StateGraph."""
    return build_chat_builder(llm)

```


## backend/app/services/langgraph/llm_factory.py

```py
# backend/app/services/langgraph/llm_factory.py
from __future__ import annotations
import os
from typing import Any
from langchain_openai import ChatOpenAI

# env:
# OPENAI_API_KEY, OPENAI_BASE_URL (optional), OPENAI_MODEL (default gpt-5-mini)
# OPENAI_TIMEOUT_S (default 60)

def get_llm(*, streaming: bool = True) -> Any:
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    timeout = float(os.getenv("OPENAI_TIMEOUT_S", "60"))
    llm = ChatOpenAI(
        model=model,
        streaming=streaming,
        temperature=0.2,
        timeout=timeout,
        max_retries=2,
    )
    return llm

```


## backend/app/services/langgraph/llm_router.py

```py
# backend/app/services/langgraph/llm_router.py
from __future__ import annotations

import os
from functools import lru_cache
from langchain_openai import ChatOpenAI

def _mk_router_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        streaming=False,
        max_retries=1,
        timeout=5,
    )

@lru_cache(maxsize=1)
def get_router_llm() -> ChatOpenAI:
    model = os.getenv("OPENAI_INTENT_MODEL", "gpt-5-mini")
    return _mk_router_llm(model)

@lru_cache(maxsize=1)
def get_router_fallback_llm() -> ChatOpenAI:
    model = os.getenv("OPENAI_INTENT_FALLBACK_MODEL", "gpt-5-mini")
    return _mk_router_llm(model)

```


## backend/app/services/langgraph/nodes/__init__.py

```py

```


## backend/app/services/langgraph/pdf/__init__.py

```py

```


## backend/app/services/langgraph/pdf/rfq_renderer.py

```py
from __future__ import annotations
from typing import Dict, Any

def _ensure_reportlab():
    # Lazy import to avoid startup crashes if reportlab not yet installed
    global canvas, A4, mm, simpleSplit
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.lib.utils import simpleSplit
    except Exception as e:
        raise RuntimeError("reportlab missing: pip install reportlab>=4.2.0") from e

def _draw_multiline(c, text: str, x: float, y: float, max_width: float, leading: float = 14):
    lines = simpleSplit(text, "Helvetica", 10, max_width)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y

def generate_rfq_pdf(data: Dict[str, Any], out_path: str) -> None:
    _ensure_reportlab()
    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4
    x0, y = 20*mm, height - 25*mm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0, y, "RFQ – Request for Quotation")
    c.setFont("Helvetica", 9)
    c.drawString(x0, y-14, "SealAI – Dichtungstechnik Beratung")
    y -= 30

    # Eingabedaten
    c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "Eingabedaten"); y -= 12
    c.setFont("Helvetica", 10)
    for k, v in (data.get("params") or {}).items():
        c.drawString(x0, y, f"- {k}: {v}"); y -= 12

    # Abgeleitete Kennwerte
    y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "Abgeleitete Kennwerte"); y -= 12
    c.setFont("Helvetica", 10)
    for k, v in (data.get("derived") or {}).items():
        c.drawString(x0, y, f"- {k}: {v}"); y -= 12

    # Kandidaten
    y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "Top-Partnerprodukte"); y -= 12
    c.setFont("Helvetica", 10); c.drawString(x0, y, "(Preise/LZ/MOQ durch Hersteller)"); y -= 14
    for cand in (data.get("candidates") or [])[:10]:
        line = f"- {cand.get('title')} | {cand.get('vendor_id')} | Material {cand.get('material')} | Profil {cand.get('profile')}"
        y = _draw_multiline(c, line, x0, y, width - 40*mm)
        if y < 40*mm:
            c.showPage(); y = height - 25*mm; c.setFont("Helvetica", 10)

    # Quellen
    y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "Quellen"); y -= 12
    c.setFont("Helvetica", 9)
    for src in (data.get("sources") or [])[:12]:
        y = _draw_multiline(c, f"- {src}", x0, y, width - 40*mm, leading=12)
        if y < 40*mm:
            c.showPage(); y = height - 25*mm; c.setFont("Helvetica", 9)

    # Rechtshinweis
    y -= 8; c.setFont("Helvetica", 9)
    leg = data.get("legal_notice") or "Verbindliche Eignungszusage obliegt dem Hersteller."
    _draw_multiline(c, f"Rechtshinweis: {leg}", x0, y, width - 40*mm, leading=12)

    c.showPage()
    c.save()

```


## backend/app/services/langgraph/policies/__init__.py

```py

```


## backend/app/services/langgraph/policies/model_routing.py

```py
# backend/app/services/langgraph/policies/model_routing.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Any
import os

ModelName = Literal["gpt-5-nano", "gpt-5-mini", "gpt-5"]

@dataclass
class RoutingContext:
    node: str
    confidence: Optional[float] = None
    red_flags: bool = False
    regulatory: bool = False
    ambiguous: bool = False
    hint: Optional[ModelName] = None

# Defaults stärker auf gpt-5-mini ausgerichtet
DEFAULTS: Dict[str, ModelName] = {
    "normalize_intent": "gpt-5-mini",
    "pre_extract": "gpt-5-mini",
    "domain_router": "gpt-5-mini",
    "ask_missing": "gpt-5-mini",
    "critic_light": "gpt-5-mini",
    "explain": "gpt-5-mini",
    "info_graph": "gpt-5-mini",
    "market_graph": "gpt-5-mini",
    "service_graph": "gpt-5-mini",
}

def select_model(ctx: RoutingContext) -> ModelName:
    if ctx.hint:
        return ctx.hint
    if ctx.red_flags or ctx.regulatory:
        return "gpt-5"
    if ctx.confidence is not None:
        if ctx.confidence < 0.70:
            return "gpt-5"
        if 0.70 <= ctx.confidence <= 0.84:
            return "gpt-5-mini"
        return "gpt-5-mini"  # statt nano
    if ctx.ambiguous and ctx.node in ("domain_router", "info_graph"):
        return "gpt-5-mini"
    return DEFAULTS.get(ctx.node, "gpt-5-mini")

def should_use_llm(node: str) -> bool:
    deterministic = {
        "intake_validate", "calc_core", "calc_advanced",
        "rag_retrieve", "rules_filter",
        "generate_rfq_pdf", "deliver_pdf"
    }
    return node not in deterministic

def llm_params_for(node: str, ctx: RoutingContext) -> Dict[str, Any]:
    model = select_model(ctx)
    temperature = float(os.getenv("SEALAI_LLM_TEMPERATURE", "0.2"))
    top_p = float(os.getenv("SEALAI_LLM_TOP_P", "0.9"))
    max_tokens = {"gpt-5-nano": 512, "gpt-5-mini": 2048, "gpt-5": 4096}[model]
    return {"model": model, "temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}

```


## backend/app/services/langgraph/postgres_lifespan.py

```py
# backend/app/services/langgraph/postgres_lifespan.py
"""
Kompatibler Postgres-Checkpointer (LangGraph).
– Neuer Namespace: langgraph_checkpoint.postgres
– Alter Namespace: langgraph.checkpoint.postgres
– Fallback: AsyncRedisSaver oder InMemorySaver
Zusatz: prewarm Long-Term-Memory (Qdrant) beim Start.
"""
from __future__ import annotations

import atexit
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from langgraph.checkpoint.memory import InMemorySaver

log = logging.getLogger(__name__)

from app.core.config import settings

POSTGRES_URL = settings.POSTGRES_SYNC_URL

# LTM prewarm
try:
    from app.services.langgraph.tools import long_term_memory as _ltm
except Exception:  # pragma: no cover
    _ltm = None

# ─────────────────────────────────────────────────────────────────────────────
# Kompatibler Import für PostgresSaver
# ─────────────────────────────────────────────────────────────────────────────
try:
    from langgraph_checkpoint.postgres.aio import AsyncPostgresSaver as _PgSaver
    log.info("AsyncPostgresSaver importiert aus langgraph_checkpoint.postgres.aio")
except ModuleNotFoundError:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as _PgSaver
        log.info("AsyncPostgresSaver importiert aus langgraph.checkpoint.postgres.aio")
    except ModuleNotFoundError:
        _PgSaver = None
        log.warning("❗ Postgres-Modul nicht gefunden – Priorisiere RedisSaver")


@asynccontextmanager
async def get_checkpointer(app) -> AsyncGenerator:
    """Universal-Initialisierung (async) + LTM-Prewarm."""
    # Prewarm LTM (nicht-blockierend)
    try:
        if _ltm:
            _ltm.prewarm_ltm()
            log.info("LTM prewarm gestartet.")
    except Exception as e:
        log.warning("LTM prewarm fehlgeschlagen (ignoriert): %s", e)

    checkpointer = None
    if _PgSaver:
        try:
            async with _PgSaver.from_conn_string(POSTGRES_URL) as saver:
                await saver.setup()
                checkpointer = saver
                log.info("✅ AsyncPostgresSaver initialisiert")
                yield saver
                return
        except Exception as e:
            log.warning("PostgresSaver-Init fehlgeschlagen: %s – Fallback auf RedisSaver", e)

    # Redis-Fallback (primär für Memory)
    try:
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver
        from redis.asyncio import Redis
        redis_url = settings.REDIS_URL or "redis://redis:6379/0"
        redis_client = Redis.from_url(redis_url)
        saver = AsyncRedisSaver(redis_client)
        await saver.setup()
        checkpointer = saver
        log.info("✅ AsyncRedisSaver als Fallback initialisiert")
        yield saver
        return
    except Exception as e:
        log.warning("RedisSaver-Init fehlgeschlagen: %s – Ultimativer Fallback: InMemorySaver", e)

    saver = InMemorySaver()
    yield saver
    log.info("InMemorySaver initialisiert – keine persistente LangGraph-History")


async def get_saver():
    async with get_checkpointer(None) as saver:
        return saver


@asynccontextmanager
async def lifespan(app) -> AsyncGenerator[None, None]:
    async with get_checkpointer(app):
        yield


def cleanup():
    pass


atexit.register(cleanup)

```


## backend/app/services/langgraph/prompt_registry.py

```py
from __future__ import annotations
import functools
from pathlib import Path
from typing import Dict, List
import yaml

_BASE = Path(__file__).resolve().parent / "prompts"

@functools.lru_cache(maxsize=64)
def _load_registry() -> Dict:
    p = _BASE / "registry.yaml"
    if not p.exists():
        return {"agents": {}}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"agents": {}}

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

@functools.lru_cache(maxsize=256)
def get_agent_prompt(agent_id: str, lang: str = "de") -> str:
    reg = _load_registry()
    agent = (reg.get("agents") or {}).get(agent_id) or (reg.get("agents") or {}).get("supervisor")
    if not agent:
        return ""
    files: List[str] = agent.get("files") or []
    parts: List[str] = []
    for rel in files:
        p = _BASE / rel
        if p.suffix.lower() in {".md", ".txt", ".jinja2"} and p.exists():
            parts.append(_read(p))
    return "\n\n".join(x for x in parts if x)

```


## backend/app/services/langgraph/prompting.py

```py
# backend/app/services/langgraph/prompting.py
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable, List, Dict

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Template-Verzeichnisse einsammeln (mit ENV-Override)
# -------------------------------------------------------------------
_BASE = Path(__file__).resolve().parent
_GLOBAL_PROMPTS = _BASE / "prompts"
_GLOBAL_PROMPT_TEMPLATES = _BASE / "prompt_templates"
_GRAPH_CONSULT_PROMPTS = _BASE / "graph" / "consult" / "prompts"
_DOMAINS_ROOT = _BASE / "domains"


def _collect_template_dirs() -> List[Path]:
    # Optional: zusätzliche Pfade per ENV (z. B. "/app/custom_prompts:/mnt/prompts")
    env_paths: List[Path] = []
    raw = os.getenv("SEALAI_TEMPLATE_DIRS", "").strip()
    if raw:
        for p in raw.split(":"):
            pp = Path(p).resolve()
            if pp.is_dir():
                env_paths.append(pp)

    fixed: List[Path] = [
        _GLOBAL_PROMPTS,
        _GLOBAL_PROMPT_TEMPLATES,
        _GRAPH_CONSULT_PROMPTS,
    ]

    domain_prompts: List[Path] = []
    if _DOMAINS_ROOT.is_dir():
        for p in _DOMAINS_ROOT.glob("**/prompts"):
            if p.is_dir():
                domain_prompts.append(p)

    all_candidates = env_paths + fixed + domain_prompts

    seen = set()
    result: List[Path] = []
    for p in all_candidates:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp.is_dir():
            key = str(rp)
            if key not in seen:
                seen.add(key)
                result.append(rp)

    if not result:
        result = [_BASE]
        log.warning("[prompting] Keine Template-Verzeichnisse gefunden; Fallback=%s", _BASE)

    try:
        log.info("[prompting] template search dirs: %s", ", ".join(str(p) for p in result))
    except Exception:
        pass

    return result


_ENV = Environment(
    loader=FileSystemLoader([str(p) for p in _collect_template_dirs()]),
    autoescape=False,
    undefined=StrictUndefined,  # Fail-fast
    trim_blocks=True,
    lstrip_blocks=True,
)

# -------------------------------------------------------------------
# Jinja2 Filter
# -------------------------------------------------------------------
def _regex_search(value: Any, pattern: str) -> bool:
    try:
        return re.search(pattern, str(value or ""), flags=re.I) is not None
    except Exception:
        return False


def _tojson_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _tojson_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


_ENV.filters["regex_search"] = _regex_search
_ENV.filters["tojson_compact"] = _tojson_compact
_ENV.filters["tojson_pretty"] = _tojson_pretty

# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def render_template(name: str, /, **kwargs: Any) -> str:
    """Rendert ein Jinja2-Template und loggt die Quelle; fügt params_json automatisch hinzu."""
    if "params" in kwargs and "params_json" not in kwargs:
        try:
            kwargs["params_json"] = safe_json(kwargs["params"])
        except Exception:
            kwargs["params_json"] = "{}"

    tpl = _ENV.get_template(name)
    src_file = getattr(tpl, "filename", None)
    log.info("[prompting] loaded template '%s' from '%s'", name, src_file or "?")
    return tpl.render(**kwargs)


def messages_for_template(seq: Iterable[Any]) -> List[Dict[str, str]]:
    """Normalisiert Nachrichten in [{type, content}]."""
    out: List[Dict[str, str]] = []

    def _norm_one(m: Any) -> Dict[str, str]:
        if isinstance(m, HumanMessage):
            return {"type": "user", "content": (m.content or "").strip()}
        if isinstance(m, AIMessage):
            return {"type": "ai", "content": (m.content or "").strip()}
        if isinstance(m, SystemMessage):
            return {"type": "system", "content": (m.content or "").strip()}

        if isinstance(m, dict):
            role = (m.get("role") or m.get("type") or "").lower()
            content = (m.get("content") or "").strip()
            if role in ("user", "human"):
                t = "user"
            elif role in ("assistant", "ai"):
                t = "ai"
            elif role == "system":
                t = "system"
            else:
                t = "user"
            return {"type": t, "content": content}

        return {"type": "user", "content": (str(m) if m is not None else "").strip()}

    for m in (seq or []):
        norm = _norm_one(m)
        if norm["content"]:
            out.append(norm)
    return out


# -------------------------------------------------------------------
# JSON-Utilities
# -------------------------------------------------------------------
_CODE_FENCE_RX = re.compile(r"^```(?:json|JSON)?\s*(.*?)\s*```$", re.DOTALL)


def _extract_balanced_json(s: str) -> str:
    """Extrahiert den ersten ausgewogenen JSON-Block ({...} oder [...]) aus s."""
    if not s:
        return ""
    start_idx = None
    opener = None
    closer = None
    for i, ch in enumerate(s):
        if ch in "{[":
            start_idx = i
            opener = ch
            closer = "}" if ch == "{" else "]"
            break
    if start_idx is None:
        return s.strip()

    depth = 0
    in_string = False
    escape = False
    for j in range(start_idx, len(s)):
        ch = s[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return s[start_idx : j + 1].strip()
    return s[start_idx:].strip()


def strip_json_fence(text: str) -> str:
    """Entfernt ```json fences``` ODER extrahiert den ersten ausgewogenen JSON-Block."""
    if not isinstance(text, str):
        return ""
    s = text.strip()

    m = _CODE_FENCE_RX.match(s)
    if m:
        inner = m.group(1).strip()
        if inner.startswith("{") or inner.startswith("["):
            return _extract_balanced_json(inner)
        return inner

    if s.startswith("{") or s.startswith("["):
        return _extract_balanced_json(s)

    return _extract_balanced_json(s)


def safe_json(obj: Any) -> str:
    """Kompaktes JSON (UTF-8) für Prompt-Übergaben."""
    return json.dumps(obj or {}, ensure_ascii=False, separators=(",", ":"))

```


## backend/app/services/langgraph/prompts/__init__.py

```py

```


## backend/app/services/langgraph/prompts/agents/__init__.py

```py

```


## backend/app/services/langgraph/prompts/agents/consult_supervisor.de.md

```md
# Rolle & Ziel
Du bist **SealAI**, ein wissenschaftlich fundierter Ingenieur für Dichtungstechnik (≥20 Jahre Praxis).
Deine Aufgabe: Nutzeranliegen schnell verstehen, fehlende Pflichtdaten strukturiert erfragen,
und eine **technisch belastbare** Empfehlung zu Dichtungstyp & Material geben – inkl. kurzer Begründung,
Risiken, Annahmen, Normhinweisen und nächsten Schritten.

# Domänenfokus
- Wellendichtringe (RWDR), O-Ringe, Hydraulik/Pneumatik (Stangen-/Kolbendichtungen), Flansch-/Flachdichtungen.
- Werkstoffe: PTFE, NBR, HNBR, FKM/FPM, EPDM, PU/TPU, PEEK, Grafit, Faser-/Weichstoff.
- Normen/Leitlinien (bei Bedarf ansprechen, nicht auswendig zitieren): ISO/DIN (z. B. ISO 3601, DIN 3760/3761, DIN EN 1514), FDA/EU 1935/2004, USP Class VI.

# Arbeitsweise (immer)
1) **Analyse:** Medium/Medien, Temperaturprofil (min/nom/max), Druck (stat./dyn.), Bewegung (rotierend/translatorisch, Geschwindigkeit), Abmessungen, Umgebung (Schmutz/Strahlung/UV), Einbau (Nut-/Gegenlaufflächen), Lebensdauer/Regelwerk.
2) **Plausibilität:** Werte & Einheiten prüfen (SI), fehlende Pflichtdaten **gezielt** nachfragen (max. 3 Punkte pro Runde).
3) **Bewertung:** Chem./therm./mechan. Eignung + Sicherheitsmargen; Reibung/Verschleiß; Montage- und Oberflächenanforderungen.
4) **Empfehlung:** Dichtungstyp + Werkstoff + Kernparameter (Härte/Shore, Füllstoffe, Toleranzen) mit **kurzer** Begründung.
5) **Qualität:** Annahmen offen legen; Risiken nennen; Alternativen skizzieren; nächste Schritte vorschlagen.

# Tiefe & Nachweis
- Antworte **substanziell**: i. d. R. **≥ 12–18 Zeilen** in den Sachabschnitten (kein Fülltext).
- Führe **Betriebsgrenzen** aus (**Tmax**, **p_max**, **v** bzw. **pv**-Hinweise) und erkläre **Reibungs-/Verschleißmechanismen**.
- Zeige **Material-Trade-offs** (z. B. PTFE vs. FKM: Reibung, Diffusion, Temperatur, Kosten/Lebensdauer) und **Grenzfälle**.
- Nenne **mindestens 3 Risiken/Annahmen** und **mindestens 2 sinnvolle Alternativen** mit Einsatzgrenzen.

# Informationsquellen
- Nutze bereitgestellten Kontext (RAG) **nur unterstützend**; erfinde keine Zitate.
- Wenn Kontext unklar/leer ist, arbeite aus Fachwissen + bitte um fehlende Kerndaten statt zu raten.
{% if rag_context %}
# RAG-Kontext (nur zur Begründung, nicht wörtlich abschreiben)
{{ rag_context }}
{% endif %}

# Kommunikationsstil
- Deutsch, **präzise, knapp, freundlich**. Keine Floskeln.
- Abschnitte mit klaren Überschriften. Bullet-Points statt langer Fließtexte, wo sinnvoll.
- Zahlen mit Einheit (SI), z. B. „150 °C“, „10 bar“, „0,5 m/s“, „25×47×7 mm“.

# Pflichtprüfpunkte vor einer Empfehlung
- Medium/Medien (Name, ggf. Konzentration, Reinheit, Lebensmittelkontakt?)
- Temperatur (min/nom/max), Druck (min/nom/max), Bewegung/Speed
- Abmessungen / Norm-Reihe (falls vorhanden), Oberflächenrauheit/Gegenlauf
- Anforderungen: Lebensdauer, Reibung, Freigaben (z. B. FDA), Dichtigkeit, Kostenrahmen

# Ausgabeformat (immer einhalten)
**Kurzfazit (1–2 Sätze)**
- Kernempfehlung (Dichtungstyp + Material) + primärer Grund.

**Empfehlung**
- Dichtungstyp: …
- Werkstoff/Qualität: … (z. B. FKM 75 ShA, PTFE+Bronze 40 %)
- Relevante Kennwerte: Tmax, p, v, ggf. pv-Hinweis, Shore, Füllstoffe
- Einbauhinweise: Nutmaß/Oberflächen (falls bekannt), Vor-/Nachteile, Pflege/Schutz (z. B. Schmutzlippe)

**Begründung (technisch)**
- Chemische/thermische Eignung; mechanische Aspekte; Norm-/Compliance-Hinweise.
{% if citations %}- (Quellenhinweis/RAG: {{ citations }}){% endif %}

**Betriebsgrenzen & Auslegung**
- Grenzwerte (T, p, v/pv) mit Kurzbegründung und Sicherheitsmargen.
- Reibung/Verschleiß, Schmierung/Mediumseinfluss, Oberflächenanforderungen.

**Versagensmodi & Gegenmaßnahmen**
- z. B. Kaltfluss, Extrusion, chemische Degradation, thermische Alterung; jeweilige Gegenmaßnahmen.

**Compliance & Normhinweise**
- Relevante Normreihen / „Compound-Freigabe des konkreten Lieferanten prüfen“.

**Annahmen & Risiken**
- Annahmen: …
- Risiken/Trade-offs: …

**Fehlende Angaben – bitte bestätigen**
- [max. 3 gezielte Items, nur was für Entscheidung nötig ist]

**Nächste Schritte**
- z. B. Detailauslegung (Nut/Passung), Oberflächenprüfung, Lieferantenauswahl, Musterprüfung.

# Sicherheits- & Qualitätsregeln
- **Keine Halluzinationen.** Wenn unsicher: nachfragen oder konservative Option nennen.
- **Keine internen Gedankenabläufe** preisgeben; nur Ergebnisse, Annahmen und kurze Begründungen.
- Klare Warnhinweise bei Randbereich/Extremen (Tmax/chemische Exposition/hohe v/pv).
- Bei Lebensmittel/Pharma: explizit „Freigabe/Compliance des konkreten Compounds prüfen“.

# Spezifische Heuristiken (nicht dogmatisch, fachlich abwägen)
- PTFE: exzellent chem./Temp., geringe Reibung; ggf. gefüllt (Bronze/Glas/Carbon) für Verschleiß/Verzug; Kaltfluss beachten.
- NBR/HNBR: gut für Öle/Fette; begrenzt bei Säuren/polaren Medien; Temp. moderat.
- FKM: hohe Temp. + Medienbreite (Öle, Kraftstoffe, viele Chemikalien); geringe Gasdurchlässigkeit; Preis höher.
- EPDM: Wasser/Dampf/Ozon gut; **nicht** für Mineralöle/Kraftstoffe geeignet.
- PU/TPU: sehr gute Abriebfestigkeit (Hydraulik), Temp. begrenzt; Medienverträglichkeit prüfen.
- RWDR: bei Schmutz → Doppellippe/Staublippe; bei hoher v/pv → PTFE-Lippe erwägen; Wellenhärte/Rauheit prüfen.
- Hydraulik Stange/Kolben: Spaltmaße, Führung, Oberflächen und Medienreinheit kritisch; Dichtungspaket betrachten.

# Parameter- und Einheitenpolitik
- Immer SI; Dezimaltrenner „,“ akzeptieren, ausgeben mit „.“ oder schmalem Leerzeichen (z. B. 0,5 m/s).
- Abmessungen RWDR standardisiert als „d×D×b“.
- Falls Werte nur qualitativ vorliegen („hohe Temp.“): konservativ quantifizieren oder Rückfrage stellen.

# Wenn Eingabe nur Gruß/Kleintalk
- Kurz freundlich antworten und **ein** Beispiel nennen, welche Angaben du brauchst (z. B. „Medium, Temp-max, Druck, Bewegung, Abmessungen“).

# Wenn Pflichtdaten widersprüchlich/unplausibel
- Höflich darauf hinweisen, die 1–2 wichtigsten Punkte konkretisieren lassen; bis dahin **keine** definitive Materialempfehlung.

# Tabellenpflicht bei Vergleichen
- Wenn die Eingabe **Vergleich** impliziert („vergleiche“, „vs“, „gegenüberstellen“, „PTFE vs NBR“), zusätzlich eine **kompakte Tabelle** mit Kriterien:
  Chemische Beständigkeit, Temperatur (dauer/kurz), Medien/Quellung, Reibung/Verschleiß, Gas-/Diffusionsrate, Compliance, Kosten/Lebensdauer;
  plus **Vergleichs-Fazit** in 1–2 Sätzen.

# JSON-Snippets (optional, wenn der Client es fordert)
- Auf Wunsch zusätzlich ein kompaktes JSON mit „type“, „material“, „key_params“, „assumptions“, „risks“.

```


## backend/app/services/langgraph/prompts/agents/hyd_rod_agent.de.md

```md
**Domäne:** Hydraulik-Stange (Rod)
**Pflichtfelder:** falltyp, stange_mm, nut_d_mm, nut_b_mm, medium, temp_max_c, druck_bar, geschwindigkeit_m_s
**Beispiel Eingabezeile:** `Stange 25, Nut D 32, Nut B 6, Medium Öl, Tmax 80, Druck 160 bar, v 0,3 m/s`

```


## backend/app/services/langgraph/prompts/agents/rwdr_agent.de.md

```md
**Domäne:** RWDR (Radial-Wellendichtringe)
**Pflichtfelder:** falltyp, wellen_mm, gehause_mm, breite_mm, medium, temp_max_c, druck_bar, drehzahl_u_min
**Hinweise:**
- Maße in mm, Druck in bar, Temperatur in °C, Drehzahl in U/min.
- Beispiel Eingabezeile: `Welle 25, Gehäuse 47, Breite 7, Medium Öl, Tmax 80, Druck 2 bar, n 1500`

```


## backend/app/services/langgraph/prompts/partials/__init__.py

```py

```


## backend/app/services/langgraph/prompts/partials/safety.de.md

```md
Sicherheit & Compliance:
- Keine vertraulichen Daten erfragen oder speichern, außer der Nutzer liefert sie aktiv.
- Bei Unsicherheiten: **Nachfragen** statt raten.
- Keine technischen Empfehlungen ohne erforderliche Randbedingungen; weise ggf. auf Annahmen hin.

```


## backend/app/services/langgraph/prompts/partials/tone.de.md

```md
Du sprichst **menschlich, respektvoll, charmant und leicht locker** – aber fachlich präzise.
- Kurzer, wertschätzender Opener („Prima, das hilft mir schon weiter.“ / „Danke dir!“).
- **Proaktiv** 1–3 Rückfragen stellen, die direkt zur Empfehlung führen.
- **Kurz & klar**, keine Floskeln; gern ein leichtes Emoji (😊/🙂) wo passend.
- **Immer** ein Einzeilen-Beispiel für die Eingabe anbieten („z. B.: Welle 25, Gehäuse 47, …“).

```


## backend/app/services/langgraph/prompts/registry.yaml

```yaml
agents:
  supervisor:
    lang: de
    files:
      - partials/tone.de.md
      - partials/safety.de.md
      - agents/consult_supervisor.de.md

  rwdr:
    lang: de
    files:
      - partials/tone.de.md
      - agents/rwdr_agent.de.md

  hydraulics_rod:
    lang: de
    files:
      - partials/tone.de.md
      - agents/hyd_rod_agent.de.md

```


## backend/app/services/langgraph/rag/__init__.py

```py

```


## backend/app/services/langgraph/rag/schemas.py

```py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class VendorMeta:
    vendor_id: str
    paid_tier: str
    contract_valid_until: date
    active: bool

    def is_partner(self, today: Optional[date] = None) -> bool:
        t = today or date.today()
        return self.paid_tier != "none" and self.active and self.contract_valid_until >= t

```


## backend/app/services/langgraph/redis_lifespan.py

```py
# backend/app/services/langgraph/redis_lifespan.py
from __future__ import annotations

import os
import logging
from typing import Optional, Any

log = logging.getLogger("app.redis_checkpointer")

# RedisSaver (sync). Unterschiedliche Versionen haben verschiedene __init__-Signaturen.
try:
    from langgraph.checkpoint.redis import RedisSaver  # type: ignore
except Exception as e:  # pragma: no cover
    RedisSaver = None  # type: ignore
    log.warning("LangGraph RedisSaver nicht importierbar: %s", e)


def _redis_url() -> str:
    """
    Liefert eine normierte REDIS_URL (inkl. DB-Index), Default: redis://redis:6379/0
    """
    url = (os.getenv("REDIS_URL") or "redis://redis:6379/0").strip()
    return url or "redis://redis:6379/0"


def _namespace() -> tuple[str, Optional[int]]:
    """
    Erzeugt einen einheitlichen Namespace/Key-Präfix (kompatibel zu namespace|key_prefix).
    TTL optional.
    """
    raw_ns = (os.getenv("LANGGRAPH_CHECKPOINT_NS") or os.getenv("CHECKPOINT_NS") or "chat.supervisor.v1").strip()
    prefix = (os.getenv("LANGGRAPH_CHECKPOINT_PREFIX") or "lg:cp").strip()
    ttl_env = (os.getenv("LANGGRAPH_CHECKPOINT_TTL") or "").strip()
    ttl = int(ttl_env) if ttl_env.isdigit() else None
    ns = f"{prefix}:{raw_ns}"
    return ns, ttl


def _try_construct_redis_saver(redis_url: str, ns: str, ttl: Optional[int]) -> Any:
    """
    Probiert mehrere Konstruktor-Varianten – kompatibel zu alten/neuen Paketen.
    Gibt den ersten erfolgreichen Saver zurück, sonst Exception.
    """
    errors: list[tuple[dict, Exception]] = []

    # 1) Neuere Pakete – URL-basiert
    for kwargs in (
        {"redis_url": redis_url, "namespace": ns, "ttl_seconds": ttl},
        {"redis_url": redis_url, "key_prefix": ns, "ttl_seconds": ttl},
        {"redis_url": redis_url, "ttl_seconds": ttl},
        {"redis_url": redis_url},
    ):
        try:
            return RedisSaver(**{k: v for k, v in kwargs.items() if v is not None})  # type: ignore[misc]
        except Exception as e:
            errors.append((kwargs, e))

    # 2) Ältere Pakete – Client-basiert
    try:
        from redis import Redis as _Redis
        client = _Redis.from_url(redis_url)
        for kwargs in (
            {"redis": client, "namespace": ns, "ttl_seconds": ttl},
            {"redis": client, "key_prefix": ns, "ttl_seconds": ttl},
            {"redis": client, "ttl_seconds": ttl},
            {"redis": client},
        ):
            try:
                return RedisSaver(**{k: v for k, v in kwargs.items() if v is not None})  # type: ignore[misc]
            except Exception as e:
                errors.append((kwargs, e))
    except Exception as e:
        errors.append(({"redis_client_build": True}, e))

    # Letzte Fehlermeldung ausgeben und erneut werfen
    if errors:
        kw, err = errors[-1]
        log.warning("RedisSaver-Konstruktion fehlgeschlagen. Letzter Versuch %s: %r", kw, err)
        raise err
    raise RuntimeError("Unbekannter Fehler bei RedisSaver-Konstruktion")


def get_redis_checkpointer(app=None) -> Optional["RedisSaver"]:
    """
    Erzeugt einen LangGraph-RedisSaver (Checkpointer).
    Gibt None zurück, wenn Paket fehlt oder Konstruktion scheitert.
    ENV:
      REDIS_URL, LANGGRAPH_CHECKPOINT_NS | CHECKPOINT_NS,
      LANGGRAPH_CHECKPOINT_PREFIX, LANGGRAPH_CHECKPOINT_TTL
    """
    if RedisSaver is None:
        log.warning("LangGraph RedisSaver nicht verfügbar. Installiere 'langgraph-checkpoint-redis'.")
        return None

    redis_url = _redis_url()
    ns, ttl = _namespace()

    try:
        saver = _try_construct_redis_saver(redis_url, ns, ttl)
        log.info("LangGraph Checkpointer aktiv: url=%s ns/prefix=%s ttl=%s", redis_url, ns, ttl)
        return saver
    except Exception as e:
        log.warning("RedisSaver nicht nutzbar (%r). Fallback: None (In-Memory-Graph).", e)
        return None

```


## backend/app/services/langgraph/rules/__init__.py

```py

```


## backend/app/services/langgraph/rules/common.yaml

```yaml
version: 1
materials:
  water:
    max_temp_c: 120
    notes: ["Korrosionsschutz beachten", "Trinkwasser: WRAS/KTW beachten"]
  oil:
    max_temp_c: 150
    notes: ["Additive beachten", "Viskosität beeinflusst Reibung"]
profiles:
  rwdr:
    dn_limit: 300000
    v_limit_m_s: 20
pressure:
  high_bar_threshold: 5
  notes_above: ["Stützelement/Extrusionsschutz prüfen"]

```


## backend/app/services/langgraph/rules/rwdr.yaml

```yaml
version: 1
medium_map:
  water: ["EPDM", "FKM", "PTFE"]
  oil: ["NBR", "FKM", "HNBR", "PTFE"]
pv_bands:
  - max_pv: 1.5
    recommend: ["NBR", "EPDM"]
  - max_pv: 3.0
    recommend: ["HNBR", "FKM"]
  - max_pv: 10.0
    recommend: ["PTFE"]
speed_bands_m_s:
  - max_v: 5.0
    recommend: ["NBR", "HNBR"]
  - max_v: 15.0
    recommend: ["FKM"]
  - max_v: 30.0
    recommend: ["PTFE"]

```


## backend/app/services/langgraph/tests/__init__.py

```py

```


## backend/app/services/langgraph/tests/test_ask_missing_prompt.py

```py
from __future__ import annotations
from app.services.langgraph.graph.consult.nodes.ask_missing import ask_missing_node
from app.services.langgraph.prompting import render_template

def test_rwdr_missing_prompt_contains_expected_labels():
    state = {"consult_required": True, "domain": "rwdr", "params": {}, "messages":[{"role":"user","content":"rwdr"}]}
    res = ask_missing_node(state)
    msg = res["messages"][0].content
    assert "Welle (mm)" in msg
    assert "Gehäuse (mm)" in msg
    assert "Breite (mm)" in msg
    assert "Druck (bar)" in msg
    assert res.get("ui_event", {}).get("form_id") == "rwdr_params_v1"
    assert res.get("phase") == "ask_missing"

def test_hyd_missing_prompt_contains_expected_labels():
    state = {"consult_required": True, "domain": "hydraulics_rod", "params": {}, "messages":[{"role":"user","content":"hyd"}]}
    res = ask_missing_node(state)
    msg = res["messages"][0].content
    assert "Stange (mm)" in msg
    assert "Nut-Ø D (mm)" in msg
    assert "Nutbreite B (mm)" in msg
    assert "Relativgeschwindigkeit (m/s)" in msg
    assert res.get("ui_event", {}).get("form_id") == "hydraulics_rod_params_v1"

def test_followups_template_renders_list():
    out = render_template("ask_missing_followups.jinja2",
                          followups=["Tmax plausibel bei v≈3 m/s?", "Druck > 200 bar bestätigt?"])
    assert "Bevor ich empfehle" in out
    assert "- Tmax plausibel bei v≈3 m/s?" in out
    assert "- Druck > 200 bar bestätigt?" in out
    assert "Passt das so?" in out

```


## backend/app/services/langgraph/tools/__init__.py

```py

```


## backend/app/services/langgraph/tools/hitl.py

```py
from __future__ import annotations
from typing import Dict, Any

def hitl_required(reason: str) -> Dict[str, Any]:
    return {"hitl_required": True, "reason": reason, "status": "pending_review"}

```


## backend/app/services/langgraph/tools/long_term_memory.py

```py
# backend/app/services/langgraph/tools/long_term_memory.py
from __future__ import annotations

import os
import time
import uuid
import logging
import threading
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# -------------------- ENV & Defaults --------------------

_QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333").strip() or "http://qdrant:6333"
_COLLECTION = os.getenv("LTM_COLLECTION", "sealai_ltm").strip() or "sealai_ltm"
_EMB_MODEL = os.getenv("LTM_EMBED_MODEL", "intfloat/multilingual-e5-base").strip() or "intfloat/multilingual-e5-base"
_DISABLE_PREWARM = os.getenv("LTM_DISABLE_PREWARM", "0").strip() in ("1", "true", "yes", "on")

# -------------------- Singletons --------------------

_client = None            # QdrantClient
_embeddings = None        # HuggingFaceEmbeddings
_ready = False
_init_err: Optional[str] = None
_lock = threading.RLock()

# -------------------- Init helpers --------------------

def _init_hf_embeddings():
    """Create CPU-safe HuggingFaceEmbeddings."""
    from langchain_huggingface import HuggingFaceEmbeddings
    log.info("LTM: using HuggingFaceEmbeddings model=%s", _EMB_MODEL)
    return HuggingFaceEmbeddings(
        model_name=_EMB_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

def _ensure_collection(client, dim: int):
    from qdrant_client.http.models import Distance, VectorParams
    try:
        info = client.get_collection(_COLLECTION)
        if info and getattr(info, "vectors_count", 0) > 0:
            return
    except Exception:
        pass
    client.recreate_collection(
        collection_name=_COLLECTION,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

def _do_init_once():
    global _client, _embeddings, _ready, _init_err
    from qdrant_client import QdrantClient

    log.info("LTM: Connecting Qdrant at %s", _QDRANT_URL)
    client = QdrantClient(url=_QDRANT_URL, prefer_grpc=False, timeout=5.0)

    embeddings = _init_hf_embeddings()
    # probe to get dimension
    probe_vec = embeddings.embed_query("ltm-probe")
    dim = len(probe_vec)
    _ensure_collection(client, dim)

    _client = client
    _embeddings = embeddings
    _ready = True
    _init_err = None

def _do_init(retries: int = 2, backoff_ms: int = 400):
    global _ready, _init_err
    if _ready:
        return
    with _lock:
        if _ready:
            return
        for i in range(retries + 1):
            try:
                _do_init_once()
                log.info("LTM init ok")
                return
            except Exception as e:
                _init_err = f"{e}"
                if i < retries:
                    log.warning("LTM init attempt %s failed: %s – retrying in %dms", i + 1, _init_err, backoff_ms)
                    time.sleep(backoff_ms / 1000.0)
                else:
                    log.error("LTM init failed: %s", _init_err)

# -------------------- Public API --------------------

def prewarm_ltm():
    """Optional prewarm – no-op if disabled by ENV."""
    if _DISABLE_PREWARM:
        return
    _do_init()

def upsert_memory(*, user: str, chat_id: str, text: str, kind: str = "note") -> bool:
    """
    Store a short memory snippet. Returns True if stored, False otherwise.
    Works even if init failed (returns False, no exception).
    """
    try:
        if not _ready:
            _do_init()
        if not (_ready and _client and _embeddings):
            return False

        vec = _embeddings.embed_query(text or "")
        if not isinstance(vec, list):
            vec = list(vec)

        payload: Dict[str, Any] = {
            "user": user,
            "chat_id": chat_id,
            "kind": kind,
            "text": text,
        }

        point_id = str(uuid.uuid4())
        from qdrant_client.http.models import PointStruct
        _client.upsert(
            collection_name=_COLLECTION,
            points=[PointStruct(id=point_id, vector=vec, payload=payload)],
            wait=True,
        )
        return True
    except Exception as e:
        log.warning("LTM upsert failed: %s", e)
        return False

```


## backend/app/services/langgraph/tools/rag_search_tool.py

```py
# backend/app/services/langgraph/tools/rag_search_tool.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
from langchain_core.tools import tool
from ...rag.rag_orchestrator import hybrid_retrieve

class RagSearchInput(TypedDict, total=False):
    query: str
    tenant: Optional[str]
    k: int
    filters: Dict[str, Any]

@tool("rag_search", return_direct=False)
def rag_search_tool(query: str, tenant: Optional[str] = None, k: int = 6, **filters: Any) -> List[Dict[str, Any]]:
    """Hybrid Retrieval (Qdrant + BM25 + Rerank). Returns top-k docs with metadata and fused scores."""
    docs = hybrid_retrieve(query=query, tenant=tenant, k=k, metadata_filters=filters or None, use_rerank=True)
    return docs

```


## backend/app/services/langgraph/tools/telemetry.py

```py
from __future__ import annotations
import os
try:
    import redis
except Exception:
    redis = None

class Telemetry:
    def __init__(self) -> None:
        self.client = None
        url = os.getenv("REDIS_URL") or os.getenv("REDIS_HOST")
        if redis and url:
            try:
                self.client = redis.Redis.from_url(url) if "://" in url else redis.Redis(host=url, port=int(os.getenv("REDIS_PORT", "6379")))
            except Exception:
                self.client = None

    def incr(self, key: str, amount: int = 1) -> None:
        if self.client:
            try:
                self.client.incr(key, amount)
            except Exception:
                pass

    def set_gauge(self, key: str, value: float) -> None:
        if self.client:
            try:
                self.client.set(key, value)
            except Exception:
                pass

telemetry = Telemetry()
RFQ_GENERATED = "rfq_generated_count"
PARTNER_COVERAGE = "partner_coverage_rate"
MODEL_USAGE = "model_usage_distribution"
NO_MATCH_RATE = "no_match_rate"

```


## backend/app/services/langgraph/tools/ui_events.py

```py
from __future__ import annotations
from typing import Dict, Any

UI = dict(
    DECISION_READY="decision_ready",
    RFQ_READY="rfq_ready",
    NO_PARTNER_AVAILABLE="no_partner_available",
    OPEN_FORM="open_form",
)

def make_event(action: str, **payload: Any) -> Dict[str, Any]:
    return {"ui_action": action, "payload": payload}

```


## backend/app/services/memory/__init__.py

```py

```


## backend/app/services/memory/conversation_memory.py

```py
# backend/app/services/memory/conversation_memory.py
"""
Conversation STM (Short-Term Memory) auf Redis
----------------------------------------------
- Speichert JEDE Chatnachricht (user|assistant|system) chronologisch.
- Ring-Buffer per LTRIM (STM_MAX_MSG).
- TTL wird bei jedem Push erneuert (STM_TTL_SEC).
"""

from __future__ import annotations
import os
import json
import time
from typing import Literal, List, Dict, Any
from redis import Redis

# ───────────────────────── Config ──────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TTL_SEC   = int(os.getenv("STM_TTL_SEC", "604800"))           # 7 Tage
MAX_MSG   = int(os.getenv("STM_MAX_MSG", "200"))              # max. Messages/Chat
PREFIX    = os.getenv("STM_PREFIX", "chat:stm")               # Key-Namespace
# ────────────────────────────────────────────────────────────

def _r() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)

def _key(chat_id: str) -> str:
    return f"{PREFIX}:{chat_id}:messages"

def _touch(chat_id: str) -> None:
    _r().expire(_key(chat_id), TTL_SEC)

Role = Literal["user", "assistant", "system"]

def add_message(chat_id: str, role: Role, content: str) -> None:
    """Hängt eine Nachricht an das Chat-Log (Ring-Buffer) an."""
    if not chat_id or not isinstance(content, str) or not content.strip():
        return
    doc: Dict[str, Any] = {
        "role": role,
        "content": content,
        "ts": time.time(),
    }
    r = _r()
    r.rpush(_key(chat_id), json.dumps(doc, ensure_ascii=False))
    r.ltrim(_key(chat_id), -MAX_MSG, -1)  # Ring-Buffer begrenzen
    _touch(chat_id)

def get_history(chat_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Liest die letzten N Nachrichten (chronologisch)."""
    if limit <= 0:
        return []
    r = _r()
    raw = r.lrange(_key(chat_id), -limit, -1)
    out: List[Dict[str, Any]] = []
    for row in raw:
        try:
            out.append(json.loads(row))
        except Exception:
            continue
    return out

```


## backend/app/services/memory/memory_core.py

```py
"""
Memory Core: Kapselt Long-Term-Memory (Qdrant) für Export/Löschen.
Kurz-/Mittelzeit (Redis/Summary) laufen separat über LangGraph-Checkpointer.

Payload-Felder pro Eintrag:
- user: str                  (Pflicht für Filterung pro Benutzer)
- chat_id: str               (optional; für Export/Löschen pro Chat)
- kind: str                  (z. B. "preference", "fact", "note", …)
- text: str                  (Inhalt)
- created_at: float|int|str  (optional: Unix-Zeit oder ISO)
Weitere Felder erlaubt – werden unverändert mit exportiert.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from qdrant_client import QdrantClient, models
from qdrant_client.http.models import FilterSelector

from app.core.config import settings


# ---------------------------------------------------------------------------
# Qdrant Client & Collection
# ---------------------------------------------------------------------------

def _get_qdrant_client() -> QdrantClient:
    kwargs = {"url": settings.qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return QdrantClient(**kwargs)


def _ltm_collection_name() -> str:
    """
    Eigene LTM-Collection verwenden, um keine Vektorgrößen-Konflikte mit der
    RAG-Collection zu riskieren. Fallback: "<qdrant_collection>-ltm".
    """
    return (settings.qdrant_collection_ltm or f"{settings.qdrant_collection}-ltm").strip()


def ensure_ltm_collection(client: QdrantClient) -> None:
    """
    Stellt sicher, dass die LTM-Collection existiert. Wir verwenden einen
    Dummy-Vektor (size=1), da wir nur Payload-basierte Scroll/Filter-Operationen
    benötigen. (Qdrant verlangt einen Vektorspace pro Collection.)
    """
    coll = _ltm_collection_name()
    try:
        client.get_collection(coll)
    except Exception:
        client.recreate_collection(
            collection_name=coll,
            vectors_config=models.VectorParams(size=1, distance=models.Distance.COSINE),
        )


# ---------------------------------------------------------------------------
# Export / Delete
# ---------------------------------------------------------------------------

def _build_user_filter(user: str, chat_id: Optional[str] = None) -> models.Filter:
    must: List[models.FieldCondition] = [
        models.FieldCondition(key="user", match=models.MatchValue(value=user))
    ]
    if chat_id:
        must.append(models.FieldCondition(key="chat_id", match=models.MatchValue(value=chat_id)))
    return models.Filter(must=must)


def ltm_export_all(
    user: str,
    chat_id: Optional[str] = None,
    limit: int = 10000,
) -> List[Dict[str, Any]]:
    """
    Exportiert bis zu `limit` LTM-Items für den User (optional gefiltert nach chat_id).
    Liefert Liste aus {id, payload}.
    """
    if not settings.ltm_enable:
        return []

    client = _get_qdrant_client()
    ensure_ltm_collection(client)

    flt = _build_user_filter(user, chat_id)
    out: List[Dict[str, Any]] = []

    next_page = None
    fetched = 0
    page_size = 512
    coll = _ltm_collection_name()

    while fetched < limit:
        points, next_page = client.scroll(
            collection_name=coll,
            scroll_filter=flt,
            with_payload=True,
            with_vectors=False,
            limit=min(page_size, limit - fetched),
            offset=next_page,
        )
        if not points:
            break
        for p in points:
            out.append({
                "id": str(p.id),
                "payload": dict(p.payload or {}),
            })
        fetched += len(points)
        if next_page is None:
            break

    return out


def ltm_delete_all(
    user: str,
    chat_id: Optional[str] = None,
) -> int:
    """
    Löscht alle LTM-Items für User (optional gefiltert nach chat_id).
    Gibt die Anzahl der gelöschten Punkte (approx.) zurück.
    """
    if not settings.ltm_enable:
        return 0

    client = _get_qdrant_client()
    ensure_ltm_collection(client)

    flt = _build_user_filter(user, chat_id)
    coll = _ltm_collection_name()

    # Vorab zählen (für Response)
    to_delete = 0
    next_page = None
    while True:
        points, next_page = client.scroll(
            collection_name=coll,
            scroll_filter=flt,
            with_payload=False,
            with_vectors=False,
            limit=1024,
            offset=next_page,
        )
        if not points:
            break
        to_delete += len(points)
        if next_page is None:
            break

    # Delete via Filter (serverseitig)
    client.delete(
        collection_name=coll,
        points_selector=FilterSelector(filter=flt),
        wait=True,
    )
    return to_delete

```


## backend/app/services/rag/__init__.py

```py
# backend/app/services/rag/__init__.py
from __future__ import annotations

# Public surface für Altaufrufer: ro.prewarm(), ro.hybrid_retrieve, ro.FINAL_K
from .rag_orchestrator import (
    startup_warmup as prewarm,   # erwartet von Startup
    hybrid_retrieve,
    FINAL_K,
)

__all__ = ["prewarm", "hybrid_retrieve", "FINAL_K"]

```


## backend/app/services/rag/rag_ingest.py

```py
import os, sys
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import (
    PDFPlumberLoader, Docx2txtLoader, TextLoader, UnstructuredFileLoader
)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sealai-docs-bge-m3")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
SUPPORTED_EXTENSIONS = [".pdf", ".txt", ".docx", ".md"]

def load_document(file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return PDFPlumberLoader(file_path).load()
    elif ext == ".docx":
        return Docx2txtLoader(file_path).load()
    elif ext in (".txt", ".md"):
        return TextLoader(file_path).load()
    else:
        return UnstructuredFileLoader(file_path).load()

def ingest_file(file_path: str, chunk_size: int = 700, chunk_overlap: int = 80):
    print(f"[INGEST] Lade: {file_path}")
    docs = load_document(file_path)
    print(f"[INGEST] Split: size={chunk_size}, overlap={chunk_overlap}")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\\n\\n", "\\n", ".", " ", ""],
    )
    split_docs = splitter.split_documents(docs)

    print(f"[INGEST] HF-Embeddings: {EMBEDDING_MODEL} (normalize=True)")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )

    print(f"[INGEST] Schreibe nach Qdrant: {QDRANT_COLLECTION}")
    _ = QdrantVectorStore.from_documents(
        split_docs, embeddings,
        url=QDRANT_URL, api_key=QDRANT_API_KEY,
        collection_name=QDRANT_COLLECTION,
    )
    print(f"[INGEST] OK: {file_path}")

def ingest_directory(directory: str):
    files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ]
    if not files:
        print(f"[INGEST] Keine unterstützten Dateien in {directory}")
    for fp in files:
        ingest_file(fp)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Nutzung: python rag_ingest.py <file_or_directory>")
        sys.exit(1)
    target = sys.argv[1]
    if os.path.isdir(target):
        ingest_directory(target)
    else:
        ingest_file(target)

```


## backend/app/services/rag/rag_orchestrator.py

```py
from __future__ import annotations

import os
import time
import math
import logging
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("app.services.rag.rag_orchestrator")

# ─────────────────────────────────────────────────────────────────────────────
# Env & Flags
# ─────────────────────────────────────────────────────────────────────────────
def _truthy(x: Optional[str]) -> bool:
    if x is None:
        return False
    v = str(x).strip().lower()
    return v in {"1", "true", "yes", "on"}

# RAG core
QDRANT_URL                 = os.getenv("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QDRANT_COLLECTION_PREFIX   = os.getenv("QDRANT_COLLECTION_PREFIX", "").strip()
QDRANT_COLLECTION_DEFAULT  = os.getenv("QDRANT_COLLECTION", "sealai-docs").strip()

# Embeddings / Rerank
EMB_MODEL_NAME             = os.getenv("EMB_MODEL_NAME", os.getenv("EMBEDDINGS_MODEL", "intfloat/multilingual-e5-base"))
RERANK_MODEL_NAME          = os.getenv("RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Retrieval knobs
HYBRID_K                   = int(os.getenv("RAG_HYBRID_K", os.getenv("RAG_TOP_K", "12")))
FINAL_K                    = int(os.getenv("RAG_FINAL_K", "6"))
RRF_K                      = int(os.getenv("RAG_RRF_K", "60"))
SCORE_THRESHOLD            = float(os.getenv("RAG_SCORE_THRESHOLD", "0.0"))

# Optional BM25 over Redis (gated)
USE_BM25                   = _truthy(os.getenv("RAG_BM25_ENABLED", "0"))
REDIS_URL                  = os.getenv("REDIS_URL")
REDIS_BM25_INDEX           = os.getenv("REDIS_BM25_INDEX") or os.getenv("RAG_BM25_INDEX")

# ─────────────────────────────────────────────────────────────────────────────
# Module globals (lazy)
# ─────────────────────────────────────────────────────────────────────────────
_embedder = None
_reranker = None

def _event(event: str, **data: Any) -> None:
    payload = {**data, "event": event, "timestamp": _iso_utc(), "level": "info"}
    log.info(f"{payload}")

def _iso_utc() -> str:
    import datetime as _dt
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()

# ─────────────────────────────────────────────────────────────────────────────
# Init / warmup
# ─────────────────────────────────────────────────────────────────────────────
def init_bm25(redis_url: Optional[str] = None, index_name: Optional[str] = None) -> Optional[Any]:
    """BM25 optional. Wenn deaktiviert, komplett still."""
    if not USE_BM25:
        return None
    url = redis_url or REDIS_URL
    idx = index_name or REDIS_BM25_INDEX
    if not url or not idx:
        _event("redis_bm25_unavailable", reason="missing_url_or_index")
        return None
    try:
        import redis
        r = redis.Redis.from_url(url)
        _ = r.ping()
        _event("redis_bm25_ready", index=idx)
        return {"client": r, "index": idx}
    except Exception as e:
        _event("redis_bm25_unavailable", reason=f"{type(e).__name__}: {e}")
        return None

def prewarm_embeddings() -> None:
    """Lädt Embeddings + Reranker und meldet Zeiten."""
    global _embedder, _reranker
    try:
        t0 = time.perf_counter()
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMB_MODEL_NAME)
        _event("embeddings_loaded", model=EMB_MODEL_NAME, ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        _event("embeddings_failed", model=EMB_MODEL_NAME, error=f"{type(e).__name__}: {e}")

    try:
        t0 = time.perf_counter()
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(RERANK_MODEL_NAME)
        _event("reranker_loaded", model=RERANK_MODEL_NAME, ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        _event("reranker_failed", model=RERANK_MODEL_NAME, error=f"{type(e).__name__}: {e}")

    log.info("RAG prewarm completed.")

def startup_warmup() -> None:
    _ = init_bm25()
    prewarm_embeddings()

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def _collection_for_tenant(tenant: Optional[str]) -> str:
    t = (tenant or "").strip()
    if QDRANT_COLLECTION_PREFIX and t:
        return f"{QDRANT_COLLECTION_PREFIX}:{t}"
    return QDRANT_COLLECTION_DEFAULT

def _embed(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMB_MODEL_NAME)
    return _embedder.encode(texts, normalize_embeddings=True).tolist()

def _rrf_merge(candidates: List[Tuple[Dict[str, Any], float]], k: int = RRF_K) -> List[Tuple[Dict[str, Any], float]]:
    """Reciprocal Rank Fusion on already ranked hits (doc, score)."""
    # candidates are already from a single source; RRF is trivial passthrough here.
    # Hook left in for future BM25+Vector fusion.
    return candidates

def _qdrant_search(query_vec: List[float], collection: str, top_k: int = HYBRID_K,
                   metadata_filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    import httpx
    url = f"{QDRANT_URL}/collections/{collection}/points/search"
    body: Dict[str, Any] = {
        "vector": query_vec,
        "limit": top_k,
        "with_payload": True,
        "with_vector": False,
    }
    if metadata_filters:
        body["filter"] = {"must": [{"key": k, "match": {"value": v}} for k, v in metadata_filters.items()]}
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            res = data.get("result") or []
            out: List[Dict[str, Any]] = []
            for item in res:
                payload = item.get("payload") or {}
                txt = payload.get("text") or payload.get("chunk") or payload.get("content") or ""
                src = payload.get("source") or (payload.get("metadata") or {}).get("source") or payload.get("file") or ""
                out.append({
                    "text": txt,
                    "source": src,
                    "vector_score": float(item.get("score") or 0.0),
                    "metadata": payload,
                })
            return out
    except Exception as e:
        _event("qdrant_search_failed", reason=f"{type(e).__name__}: {e}", collection=collection)
        return []

def _apply_threshold(hits: List[Dict[str, Any]], thr: float) -> List[Dict[str, Any]]:
    if thr <= 0:
        return hits
    out = []
    for h in hits:
        s = float(h.get("fused_score") or h.get("vector_score") or 0.0)
        if s >= thr:
            out.append(h)
    return out

def _rerank_if_enabled(query: str, hits: List[Dict[str, Any]], use_rerank: bool) -> List[Dict[str, Any]]:
    if not use_rerank or not hits:
        return hits
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(RERANK_MODEL_NAME)
        except Exception:
            return hits
    pairs = [(query, h.get("text") or "") for h in hits]
    try:
        scores = _reranker.predict(pairs)
    except Exception:
        return hits
    # attach and sort
    for h, s in zip(hits, scores):
        h["rerank_score"] = float(s)
        # normalize a bit into 0..1 via sigmoid
        try:
            h["fused_score"] = 1.0 / (1.0 + math.exp(-float(s)))
        except Exception:
            h["fused_score"] = float(h.get("vector_score") or 0.0)
    return sorted(hits, key=lambda d: float(d.get("fused_score") or 0.0), reverse=True)

# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def hybrid_retrieve(*, query: str, tenant: Optional[str], k: int = FINAL_K,
                    metadata_filters: Optional[Dict[str, Any]] = None,
                    use_rerank: bool = True) -> List[Dict[str, Any]]:
    """
    Vector-first retrieval from Qdrant (+ optional BM25 fusion in future).
    Returns list of {text, source, vector_score, fused_score?, metadata}.
    """
    q = (query or "").strip()
    if not q:
        return []

    # Embed query
    vec = _embed([q])[0]

    # Pick collection by tenant
    collection = _collection_for_tenant(tenant)

    # Vector search
    vec_hits = _qdrant_search(vec, collection, top_k=max(HYBRID_K, k), metadata_filters=metadata_filters)

    # Placeholder: BM25 could be merged here when enabled
    fused = _rrf_merge([(h, float(h.get("vector_score") or 0.0)) for h in vec_hits], k=RRF_K)
    merged = [h for (h, _s) in fused]

    # Optional rerank
    merged = _rerank_if_enabled(q, merged, use_rerank)

    # Threshold + top-k
    merged = _apply_threshold(merged, SCORE_THRESHOLD)[:k]

    try:
        _event("hybrid_retrieve", n=len(merged), tenant=tenant or "-", collection=collection, k=k)
    except Exception:
        pass

    return merged

__all__ = [
    "startup_warmup",
    "init_bm25",
    "prewarm_embeddings",
    "hybrid_retrieve",
    "FINAL_K",
    "prewarm",
]
# ---- Backward-compat shim for startup ----
def prewarm() -> None:
    """Backward-compat: Startup expects ro.prewarm()."""
    try:
        startup_warmup()
    except Exception:
        # Beim Boot nie eskalieren
        pass

```


## backend/app/ws_stream_test.py

```py
import os
import json
import asyncio
import inspect
import websockets

# --- Konfiguration über ENV ---
WS_BASE   = os.getenv("WS_BASE", "ws://127.0.0.1:8000")
WS_PATH   = os.getenv("WS_PATH", "/api/v1/ai/ws")
WS_ORIGIN = os.getenv("WS_ORIGIN", "http://localhost:3000")
WS_URL    = os.getenv("WS_URL")  # komplette URL (optional)
TOKEN     = os.getenv("TOKEN", "")
FORCE_STREAM = os.getenv("WS_FORCE_STREAM", "1") not in ("0", "false", "False")
RAW_DEBUG    = os.getenv("WS_RAW_DEBUG", "0") in ("1", "true", "True")

PROMPTS = [
    ("ws1", "Guten Morgen, kurze Frage zu RWDR."),
    ("ws1", "Ich brauche eine optimale Dichtungsempfehlung für RWDR 25x47x7, Öl, 2 bar, 1500 rpm."),
]

# --- Helpers ---
def _connect_kwargs(headers):
    """Kompatibel zu websockets-Versionen mit additional_headers/extra_headers."""
    params = {"subprotocols": ["json"], "ping_interval": 20, "ping_timeout": 20, "max_size": None}
    sig = inspect.signature(websockets.connect)
    if "additional_headers" in sig.parameters:
        params["additional_headers"] = headers
    elif "extra_headers" in sig.parameters:
        params["extra_headers"] = headers
    return params

def _empty(s: str) -> bool:
    if not s: return True
    t = s.strip()
    return t in ("", "{}", "null", "[]")

async def _drain(ws):
    """Alle Frames lesen; bei event=done beenden."""
    got_delta = False
    while True:
        raw = await ws.recv()
        if RAW_DEBUG:
            print(f"[raw] {raw!r}", flush=True)

        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")
        if _empty(raw):
            continue

        try:
            msg = json.loads(raw)
        except Exception:
            # Falls der Server reine Textframes schickt (nicht JSON)
            print(raw, end="", flush=True)
            continue

        if not isinstance(msg, dict):
            continue

        if msg.get("phase") == "starting":
            print(f"\n[{msg.get('thread_id','?')}] starting\n", flush=True)

        # Token-Streaming (delta)
        if "delta" in msg and msg["delta"]:
            got_delta = True
            print(str(msg["delta"]), end="", flush=True)

        # Fallback auf Ganztext, wenn kein delta-Feld benutzt wird
        if not got_delta and msg.get("content"):
            print(str(msg["content"]), end="", flush=True)

        if msg.get("error"):
            print(f"\n[error] {msg['error']}\n", flush=True)

        if msg.get("event") == "done":
            print("\n— done —\n", flush=True)
            break

async def _send(ws, chat_id: str, text: str):
    payload = {
        "chat_id": chat_id,
        "input": text,
    }
    # Wichtig: Server explizit um Token-Streaming bitten
    if FORCE_STREAM:
        payload["stream"] = True
        payload["emit_delta"] = True  # einige Backends nutzen diesen Schlüssel

    await ws.send(json.dumps(payload))
    await _drain(ws)

async def main():
    uri = WS_URL or (f"{WS_BASE}{WS_PATH}?token={TOKEN}" if TOKEN else f"{WS_BASE}{WS_PATH}")
    headers = [("Origin", WS_ORIGIN)]
    if TOKEN:
        headers.append(("Authorization", f"Bearer {TOKEN}"))

    async with websockets.connect(uri, **_connect_kwargs(headers)) as ws:
        for chat_id, text in PROMPTS:
            await _send(ws, chat_id, text)

if __name__ == "__main__":
    asyncio.run(main())

```


## backend/tests/test_explain_node.py

```py
# backend/tests/test_explain_node.py
from __future__ import annotations

from langchain_core.messages import HumanMessage, AIMessage

# Ziel: nur explain_node testen, ohne echte LLM-Aufrufe
from app.services.langgraph.graph.consult.nodes.explain import explain_node

def _fake_state_base():
    return {
        "params": {
            "falltyp": "ersatz",
            "wellen_mm": 25.0,
            "gehause_mm": 47.0,
            "breite_mm": 7.0,
            "medium": "Öl",
            "temp_max_c": 80.0,
            "druck_bar": 2.0,
            "drehzahl_u_min": 1500.0,
        },
        "derived": {"calculated": {"umfangsgeschwindigkeit_m_s": 1.96}, "flags": {}},
    }

def test_explain_node_always_outputs_message_when_recs_present():
    """
    Wenn recommendations im State vorhanden sind, muss explain_node immer eine AIMessage liefern
    (auch ohne Vergleichs-Intent). => Kein Echo, kein Leerlauf.
    """
    state = _fake_state_base()
    state["messages"] = [HumanMessage(content="Ich brauche Ersatz für BA 25x47x7")]
    state["recommendations"] = [
        {
            "typ": "BA 25x47x7",
            "werkstoff": "NBR",
            "begruendung": "Öl, 80°C, 2 bar, moderate Drehzahl → NBR geeignet.",
            "vorteile": ["gute Medienbeständigkeit", "kosteneffizient"],
            "einschraenkungen": ["nicht für >100°C"],
            "geeignet_fuer": ["Öl", "bis 80°C", "2 bar"],
        },
        {
            "typ": "BA 25x47x7",
            "werkstoff": "FKM",
            "begruendung": "Alternative für höhere Temperaturreserve.",
            "vorteile": ["hohe Temperaturbeständigkeit"],
            "einschraenkungen": ["teurer"],
            "geeignet_fuer": ["Öl", "höhere Temperaturen"],
        },
    ]

    out = explain_node(state)
    msgs = out.get("messages") or []
    assert msgs, "explain_node muss eine Nachricht erzeugen"
    assert isinstance(msgs[0], AIMessage), "Antwort muss AIMessage sein"
    content = (msgs[0].content or "").lower()
    # sollte kein Echo des Usertexts sein, sondern strukturierte Erklärung
    assert "meine empfehlung" in content or "typ:" in content, "Erwartete Empfehlung/Erklärung nicht gefunden"


def test_explain_node_comparison_table_when_user_asks_to_compare():
    """
    Wenn Nutzer:in 'vergleichen' wünscht, soll explain_node eine Tabelle liefern.
    Wir simulieren das, indem wir in den letzten HumanMessage-Text ein Vergleichs-Signal packen
    und eine vorherige AI-Antwort mit Empfehlung als Quelle bereitstellen.
    """
    state = _fake_state_base()
    state["messages"] = [
        AIMessage(content=(
            "🔎 **Meine Empfehlung – präzise und transparent:**\n\n"
            "**Typ:** BA 25x47x7\n"
            "**Werkstoff:** NBR\n"
            "**Vorteile:** gute Medienbeständigkeit, kosteneffizient\n"
            "**Einschränkungen:** nicht für >100 °C\n"
            "**Begründung:** Öl, 80°C, 2 bar, 1500 U/min → NBR passt.\n\n"
            "**Alternativen:**\n"
            "- BA 25x47x7 (FKM)\n"
        )),
        HumanMessage(content="Kannst du die Optionen bitte vergleichen?"),
    ]
    # recommendations optional für die Vergleichstabelle, wir nutzen hier die vorhandene AI-Passage
    state["recommendations"] = [
        {"typ": "BA 25x47x7", "werkstoff": "NBR"},
        {"typ": "BA 25x47x7", "werkstoff": "FKM"},
    ]

    out = explain_node(state)
    msgs = out.get("messages") or []
    assert msgs, "explain_node muss eine Nachricht erzeugen"
    assert isinstance(msgs[0], AIMessage)
    content = msgs[0].content or ""
    assert "| Option | Werkstoff |" in content, "Vergleichstabelle (Markdown) nicht gefunden"

```


## backend/ws_test.py

```py
# backend/ws_test.py

import asyncio
import websockets
import json
import os

WS_URL = os.environ.get(
    "WS_URL",
    "wss://sealai.net/api/v1/ai/ws?token=" + os.environ.get("TOKEN", "")
)
CHAT_ID = os.environ.get("CHAT_ID", "ws-debug")
PROMPT = os.environ.get("PROMPT", "Welche Eigenschaften hat PTFE?")

async def main():
    async with websockets.connect(WS_URL, subprotocols=["json"]) as ws:
        print("Verbunden!")
        # Anfrage senden
        msg = {"chat_id": CHAT_ID, "input": PROMPT}
        await ws.send(json.dumps(msg))
        print(f"Gesendet: {msg}")
        # Antworte empfangen (Streaming)
        try:
            while True:
                response = await asyncio.wait_for(ws.recv(), timeout=15)
                print("Empfangen:", response)
                data = json.loads(response)
                # Stream-Ende
                if data.get("finished") or data.get("choices", [{}])[0].get("delta", {}).get("content", "") == "":
                    break
        except asyncio.TimeoutError:
            print("Timeout – keine Antwort mehr erhalten.")
        except Exception as e:
            print("Fehler:", e)

if __name__ == "__main__":
    asyncio.run(main())

```


## frontend/.env

```bash
NEXTAUTH_URL=https://sealai.net
NEXT_PUBLIC_SITE_URL=https://sealai.net

```


## frontend/.env.local

```local
# Öffentliche URL deiner App (über Nginx)
NEXTAUTH_URL=https://sealai.net

# Interne URL (Container-zu-Container)
NEXTAUTH_URL_INTERNAL=http://frontend:3000

# Keycloak
KEYCLOAK_ISSUER=https://auth.sealai.net/realms/sealAI
KEYCLOAK_CLIENT_ID=nextauth

# (optional, falls noch nicht gesetzt)
NEXT_PUBLIC_BACKEND_URL=http://backend:8000
NEXT_PUBLIC_WS_URL=wss://sealai.net/api/v1/ai/ws

```


## frontend/.env.local.bak

```bak
# Öffentliche URL deiner App (über Nginx)
NEXTAUTH_URL=https://sealai.net

# Interne URL (Container-zu-Container)
NEXTAUTH_URL_INTERNAL=http://frontend:3000

# Keycloak
KEYCLOAK_ISSUER=https://auth.sealai.net/realms/sealAI
KEYCLOAK_CLIENT_ID=nextauth

# (optional, falls noch nicht gesetzt)
NEXT_PUBLIC_BACKEND_URL=http://backend:8000
NEXT_PUBLIC_WS_URL=ws://backend:8000/api/v1/ai/ws

```


## frontend/Dockerfile

```frontend/Dockerfile
# =========================================
# SealAI Frontend – Production Dockerfile
# Next.js 15, Standalone-Output
# =========================================

# ---- Builder ----
FROM node:20-alpine AS builder

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# 1) Dependencies
COPY package.json package-lock.json* ./
# robust gegen veraltete Locks
RUN if [ -f package-lock.json ]; then \
      npm ci --include=dev || (echo "Lockfile out of sync – regenerating" && rm -f package-lock.json && npm install --include=dev); \
    else \
      npm install --include=dev; \
    fi

# 2) App-Code
COPY . .

# 3) Build (erzeugt .next/standalone dank output:'standalone')
RUN npm run build

# ---- Runner ----
FROM node:20-alpine AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

# Minimaler Runtime-Footprint aus dem Standalone-Build
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# Nicht-root User
RUN addgroup -g 10001 -S app && adduser -S app -u 10001 -G app
USER app

EXPOSE 3000

# Der Standalone-Build bringt server.js mit
CMD ["node", "server.js"]

```


## frontend/README.md

```md
This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

```


## frontend/middleware.ts

```ts
// frontend/middleware.ts
import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

const PUBLIC_FILE = /\.(.*)$/;
const SESSION_COOKIES = [
  "__Secure-authjs.session-token","authjs.session-token",
  "__Secure-next-auth.session-token","next-auth.session-token"
];

const hasSessionCookie = (req: NextRequest) =>
  SESSION_COOKIES.some((n) => !!req.cookies.get(n)?.value);

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/static") ||
    pathname === "/favicon.ico" ||
    PUBLIC_FILE.test(pathname)
  ) return NextResponse.next();

  if (!pathname.startsWith("/dashboard")) return NextResponse.next();

  const hasCookie = hasSessionCookie(req);
  let hasJwt = false;
  try { hasJwt = !!(await getToken({ req })); } catch {}

  if (hasCookie || hasJwt) return NextResponse.next();

  const envBase = (process.env.NEXTAUTH_URL ?? "").replace(/\/+$/,"");
  const base = envBase || `https://${req.headers.get("host")}`;
  // *** v5-kompatibel: Query-Variante ***
  const redirect = new URL("/api/auth/signin", base);
  redirect.searchParams.set("provider", "keycloak");
  redirect.searchParams.set("callbackUrl", `${base}${req.nextUrl.pathname}${req.nextUrl.search}`);
  redirect.searchParams.set("prompt", "login");
  return NextResponse.redirect(redirect);
}

export const config = { matcher: ["/dashboard/:path*"] };

```


## frontend/next-env.d.ts

```ts
/// <reference types="next" />
/// <reference types="next/image-types/global" />
/// <reference types="next/navigation-types/compat/navigation" />

// NOTE: This file should not be edited
// see https://nextjs.org/docs/app/api-reference/config/typescript for more information.

```


## frontend/next.config.js

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // erzeugt .next/standalone für schlanke Docker-Runner-Images
  output: 'standalone',

  // Builds in CI/Container robuster machen
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },

  // optional – falls envs im Build fehlen, lieber nicht crashen:
  experimental: {
    // weitere Flags nur bei Bedarf
  },
};

module.exports = nextConfig;

```


## frontend/out.css

```css
/*! tailwindcss v4.1.5 | MIT License | https://tailwindcss.com */
@layer properties;
.absolute {
  position: absolute;
}
.relative {
  position: relative;
}
.block {
  display: block;
}
.flex {
  display: flex;
}
.hidden {
  display: none;
}
.h-\[80vh\] {
  height: 80vh;
}
.h-full {
  height: 100%;
}
.h-screen {
  height: 100vh;
}
.min-h-screen {
  min-height: 100vh;
}
.w-full {
  width: 100%;
}
.flex-1 {
  flex: 1;
}
.transform {
  transform: var(--tw-rotate-x,) var(--tw-rotate-y,) var(--tw-rotate-z,) var(--tw-skew-x,) var(--tw-skew-y,);
}
.resize-none {
  resize: none;
}
.flex-col {
  flex-direction: column;
}
.items-center {
  align-items: center;
}
.items-end {
  align-items: flex-end;
}
.justify-between {
  justify-content: space-between;
}
.justify-center {
  justify-content: center;
}
.justify-end {
  justify-content: flex-end;
}
.justify-start {
  justify-content: flex-start;
}
.self-end {
  align-self: flex-end;
}
.self-start {
  align-self: flex-start;
}
.overflow-hidden {
  overflow: hidden;
}
.overflow-y-auto {
  overflow-y: auto;
}
.rounded-br-none {
  border-bottom-right-radius: 0;
}
.rounded-bl-none {
  border-bottom-left-radius: 0;
}
.border {
  border-style: var(--tw-border-style);
  border-width: 1px;
}
.border-t {
  border-top-style: var(--tw-border-style);
  border-top-width: 1px;
}
.border-b {
  border-bottom-style: var(--tw-border-style);
  border-bottom-width: 1px;
}
.text-center {
  text-align: center;
}
.antialiased {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
.transition {
  transition-property: color, background-color, border-color, outline-color, text-decoration-color, fill, stroke, --tw-gradient-from, --tw-gradient-via, --tw-gradient-to, opacity, box-shadow, transform, translate, scale, rotate, filter, -webkit-backdrop-filter, backdrop-filter, display, visibility, content-visibility, overlay, pointer-events;
  transition-timing-function: var(--tw-ease, ease);
  transition-duration: var(--tw-duration, 0s);
}
.transition-all {
  transition-property: all;
  transition-timing-function: var(--tw-ease, ease);
  transition-duration: var(--tw-duration, 0s);
}
.duration-300 {
  --tw-duration: 300ms;
  transition-duration: 300ms;
}
.hover\:underline {
  &:hover {
    @media (hover: hover) {
      text-decoration-line: underline;
    }
  }
}
.focus\:ring-2 {
  &:focus {
    --tw-ring-shadow: var(--tw-ring-inset,) 0 0 0 calc(2px + var(--tw-ring-offset-width)) var(--tw-ring-color, currentcolor);
    box-shadow: var(--tw-inset-shadow), var(--tw-inset-ring-shadow), var(--tw-ring-offset-shadow), var(--tw-ring-shadow), var(--tw-shadow);
  }
}
.focus\:outline-none {
  &:focus {
    --tw-outline-style: none;
    outline-style: none;
  }
}
.disabled\:opacity-50 {
  &:disabled {
    opacity: 50%;
  }
}
@property --tw-rotate-x {
  syntax: "*";
  inherits: false;
}
@property --tw-rotate-y {
  syntax: "*";
  inherits: false;
}
@property --tw-rotate-z {
  syntax: "*";
  inherits: false;
}
@property --tw-skew-x {
  syntax: "*";
  inherits: false;
}
@property --tw-skew-y {
  syntax: "*";
  inherits: false;
}
@property --tw-border-style {
  syntax: "*";
  inherits: false;
  initial-value: solid;
}
@property --tw-duration {
  syntax: "*";
  inherits: false;
}
@property --tw-shadow {
  syntax: "*";
  inherits: false;
  initial-value: 0 0 #0000;
}
@property --tw-shadow-color {
  syntax: "*";
  inherits: false;
}
@property --tw-shadow-alpha {
  syntax: "<percentage>";
  inherits: false;
  initial-value: 100%;
}
@property --tw-inset-shadow {
  syntax: "*";
  inherits: false;
  initial-value: 0 0 #0000;
}
@property --tw-inset-shadow-color {
  syntax: "*";
  inherits: false;
}
@property --tw-inset-shadow-alpha {
  syntax: "<percentage>";
  inherits: false;
  initial-value: 100%;
}
@property --tw-ring-color {
  syntax: "*";
  inherits: false;
}
@property --tw-ring-shadow {
  syntax: "*";
  inherits: false;
  initial-value: 0 0 #0000;
}
@property --tw-inset-ring-color {
  syntax: "*";
  inherits: false;
}
@property --tw-inset-ring-shadow {
  syntax: "*";
  inherits: false;
  initial-value: 0 0 #0000;
}
@property --tw-ring-inset {
  syntax: "*";
  inherits: false;
}
@property --tw-ring-offset-width {
  syntax: "<length>";
  inherits: false;
  initial-value: 0px;
}
@property --tw-ring-offset-color {
  syntax: "*";
  inherits: false;
  initial-value: #fff;
}
@property --tw-ring-offset-shadow {
  syntax: "*";
  inherits: false;
  initial-value: 0 0 #0000;
}
@layer properties {
  @supports ((-webkit-hyphens: none) and (not (margin-trim: inline))) or ((-moz-orient: inline) and (not (color:rgb(from red r g b)))) {
    *, ::before, ::after, ::backdrop {
      --tw-rotate-x: initial;
      --tw-rotate-y: initial;
      --tw-rotate-z: initial;
      --tw-skew-x: initial;
      --tw-skew-y: initial;
      --tw-border-style: solid;
      --tw-duration: initial;
      --tw-shadow: 0 0 #0000;
      --tw-shadow-color: initial;
      --tw-shadow-alpha: 100%;
      --tw-inset-shadow: 0 0 #0000;
      --tw-inset-shadow-color: initial;
      --tw-inset-shadow-alpha: 100%;
      --tw-ring-color: initial;
      --tw-ring-shadow: 0 0 #0000;
      --tw-inset-ring-color: initial;
      --tw-inset-ring-shadow: 0 0 #0000;
      --tw-ring-inset: initial;
      --tw-ring-offset-width: 0px;
      --tw-ring-offset-color: #fff;
      --tw-ring-offset-shadow: 0 0 #0000;
    }
  }
}

```


## frontend/pages/api/langgraph/chat/stream.ts

```ts
// 📁 frontend/pages/api/langgraph/chat/stream.ts
import type { NextApiRequest, NextApiResponse } from 'next'
import type { Readable } from 'stream'

export const config = {
  api: {
    bodyParser: false,    // wir parsen den Body selbst
    externalResolver: true, // damit Next.js nicht mittendrin autoflush macht
  },
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'POST') {
    res.status(405).end('Method Not Allowed')
    return
  }

  const auth = req.headers.authorization
  if (!auth?.startsWith('Bearer ')) {
    res.setHeader('WWW-Authenticate', 'Bearer')
    res.status(401).json({ error: 'Unauthorized' })
    return
  }
  const token = auth.split(' ')[1]

  // Body einlesen
  const buffers: Buffer[] = []
  for await (const chunk of (req as any) as AsyncIterable<Buffer>) {
    buffers.push(chunk)
  }
  const { input_text, chat_id } = JSON.parse(Buffer.concat(buffers).toString('utf-8'))
  if (!input_text || !chat_id) {
    res.status(400).json({ error: 'input_text and chat_id required' })
    return
  }

  // eigentliche Backend-URL
  const BACKEND = process.env.BACKEND_URL || 'https://sealai.net'

  // SSE-Header
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    Connection: 'keep-alive',
    'Cache-Control': 'no-cache',
  })

  // Fetch zum echten Backend und Pipe chunkweise
  const upstream = await fetch(
    `${BACKEND}/api/v1/langgraph/chat/stream`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ input_text, chat_id }),
    }
  )
  if (!upstream.body) {
    res.end()
    return
  }

  const reader = (upstream.body as Readable).getReader()
  const decoder = new TextDecoder()
  let done = false
  while (!done) {
    const { value, done: streamDone } = await reader.read()
    done = streamDone
    if (value) {
      // wir schreiben jeden Chunk sofort raus
      const chunk = decoder.decode(value)
      res.write(chunk)
    }
  }

  res.write('\n')  // sicherheitshalber
  res.end()
}

```


## frontend/pnpm-lock.yaml

```yaml
lockfileVersion: '9.0'

settings:
  autoInstallPeers: true
  excludeLinksFromLockfile: false

importers:

  .:
    dependencies:
      '@ant-design/icons':
        specifier: ^5.6.1
        version: 5.6.1(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react':
        specifier: 2.8.1
        version: 2.8.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@emotion/react':
        specifier: 11.11.0
        version: 11.11.0(@types/react@18.3.21)(react@18.2.0)
      '@emotion/styled':
        specifier: 11.11.0
        version: 11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0)
      '@heroicons/react':
        specifier: ^2.2.0
        version: 2.2.0(react@18.2.0)
      '@next-auth/typeorm-legacy-adapter':
        specifier: ^2.0.2
        version: 2.0.2(next-auth@4.24.11(next@15.2.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(typeorm@0.3.7(ioredis@5.6.1))
      '@radix-ui/react-icons':
        specifier: ^1.3.2
        version: 1.3.2(react@18.2.0)
      '@radix-ui/react-slot':
        specifier: ^1.1.2
        version: 1.2.2(@types/react@18.3.21)(react@18.2.0)
      '@shadcn/ui':
        specifier: ^0.0.4
        version: 0.0.4
      axios:
        specifier: ^1.8.1
        version: 1.9.0
      class-variance-authority:
        specifier: ^0.7.1
        version: 0.7.1
      clsx:
        specifier: ^2.1.1
        version: 2.1.1
      dotenv:
        specifier: ^16.4.7
        version: 16.5.0
      framer-motion:
        specifier: 7.6.8
        version: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      highlight.js:
        specifier: ^11.11.1
        version: 11.11.1
      ioredis:
        specifier: ^5.6.0
        version: 5.6.1
      jwt-decode:
        specifier: ^4.0.0
        version: 4.0.0
      lucide-react:
        specifier: ^0.477.0
        version: 0.477.0(react@18.2.0)
      markdown-to-jsx:
        specifier: ^7.7.4
        version: 7.7.6(react@18.2.0)
      next:
        specifier: 15.2.0
        version: 15.2.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      next-auth:
        specifier: ^4.24.11
        version: 4.24.11(next@15.2.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react:
        specifier: 18.2.0
        version: 18.2.0
      react-dom:
        specifier: 18.2.0
        version: 18.2.0(react@18.2.0)
      react-icons:
        specifier: ^5.5.0
        version: 5.5.0(react@18.2.0)
      react-markdown:
        specifier: ^10.1.0
        version: 10.1.0(@types/react@18.3.21)(react@18.2.0)
      react-syntax-highlighter:
        specifier: ^15.6.1
        version: 15.6.1(react@18.2.0)
      rehype-highlight:
        specifier: ^7.0.2
        version: 7.0.2
      rehype-raw:
        specifier: ^7.0.0
        version: 7.0.0
      rehype-sanitize:
        specifier: ^6.0.0
        version: 6.0.0
      remark-breaks:
        specifier: ^4.0.0
        version: 4.0.0
      remark-gfm:
        specifier: ^4.0.1
        version: 4.0.1
      tailwind-merge:
        specifier: ^3.0.2
        version: 3.2.0
      tailwindcss-animate:
        specifier: ^1.0.7
        version: 1.0.7(tailwindcss@3.4.17)
      uuid:
        specifier: ^11.1.0
        version: 11.1.0
    devDependencies:
      '@tailwindcss/forms':
        specifier: ^0.5.10
        version: 0.5.10(tailwindcss@3.4.17)
      '@tailwindcss/typography':
        specifier: ^0.5.16
        version: 0.5.16(tailwindcss@3.4.17)
      '@types/jwt-decode':
        specifier: ^2.2.1
        version: 2.2.1
      '@types/node':
        specifier: ^20.17.28
        version: 20.17.41
      '@types/react':
        specifier: ^18.2.0
        version: 18.3.21
      '@types/react-dom':
        specifier: ^18.2.0
        version: 18.3.7(@types/react@18.3.21)
      autoprefixer:
        specifier: ^10.4.21
        version: 10.4.21(postcss@8.5.3)
      postcss:
        specifier: ^8.5.3
        version: 8.5.3
      tailwindcss:
        specifier: ^3.4.17
        version: 3.4.17
      typescript:
        specifier: ^5.3.3
        version: 5.8.3

packages:

  '@alloc/quick-lru@5.2.0':
    resolution: {integrity: sha512-UrcABB+4bUrFABwbluTIBErXwvbsU/V7TZWfmbgJfbkwiBuziS9gxdODUyuiecfdGQ85jglMW6juS3+z5TsKLw==}
    engines: {node: '>=10'}

  '@ant-design/colors@7.2.0':
    resolution: {integrity: sha512-bjTObSnZ9C/O8MB/B4OUtd/q9COomuJAR2SYfhxLyHvCKn4EKwCN3e+fWGMo7H5InAyV0wL17jdE9ALrdOW/6A==}

  '@ant-design/fast-color@2.0.6':
    resolution: {integrity: sha512-y2217gk4NqL35giHl72o6Zzqji9O7vHh9YmhUVkPtAOpoTCH4uWxo/pr4VE8t0+ChEPs0qo4eJRC5Q1eXWo3vA==}
    engines: {node: '>=8.x'}

  '@ant-design/icons-svg@4.4.2':
    resolution: {integrity: sha512-vHbT+zJEVzllwP+CM+ul7reTEfBR0vgxFe7+lREAsAA7YGsYpboiq2sQNeQeRvh09GfQgs/GyFEvZpJ9cLXpXA==}

  '@ant-design/icons@5.6.1':
    resolution: {integrity: sha512-0/xS39c91WjPAZOWsvi1//zjx6kAp4kxWwctR6kuU6p133w8RU0D2dSCvZC19uQyharg/sAvYxGYWl01BbZZfg==}
    engines: {node: '>=8'}
    peerDependencies:
      react: '>=16.0.0'
      react-dom: '>=16.0.0'

  '@babel/code-frame@7.27.1':
    resolution: {integrity: sha512-cjQ7ZlQ0Mv3b47hABuTevyTuYN4i+loJKGeV9flcCgIK37cCXRh+L1bd3iBHlynerhQ7BhCkn2BPbQUL+rGqFg==}
    engines: {node: '>=6.9.0'}

  '@babel/generator@7.27.1':
    resolution: {integrity: sha512-UnJfnIpc/+JO0/+KRVQNGU+y5taA5vCbwN8+azkX6beii/ZF+enZJSOKo11ZSzGJjlNfJHfQtmQT8H+9TXPG2w==}
    engines: {node: '>=6.9.0'}

  '@babel/helper-module-imports@7.27.1':
    resolution: {integrity: sha512-0gSFWUPNXNopqtIPQvlD5WgXYI5GY2kP2cCvoT8kczjbfcfuIljTbcWrulD1CIPIX2gt1wghbDy08yE1p+/r3w==}
    engines: {node: '>=6.9.0'}

  '@babel/helper-string-parser@7.27.1':
    resolution: {integrity: sha512-qMlSxKbpRlAridDExk92nSobyDdpPijUq2DW6oDnUqd0iOGxmQjyqhMIihI9+zv4LPyZdRje2cavWPbCbWm3eA==}
    engines: {node: '>=6.9.0'}

  '@babel/helper-validator-identifier@7.27.1':
    resolution: {integrity: sha512-D2hP9eA+Sqx1kBZgzxZh0y1trbuU+JoDkiEwqhQ36nodYqJwyEIhPSdMNd7lOm/4io72luTPWH20Yda0xOuUow==}
    engines: {node: '>=6.9.0'}

  '@babel/parser@7.27.1':
    resolution: {integrity: sha512-I0dZ3ZpCrJ1c04OqlNsQcKiZlsrXf/kkE4FXzID9rIOYICsAbA8mMDzhW/luRNAHdCNt7os/u8wenklZDlUVUQ==}
    engines: {node: '>=6.0.0'}
    hasBin: true

  '@babel/runtime@7.27.1':
    resolution: {integrity: sha512-1x3D2xEk2fRo3PAhwQwu5UubzgiVWSXTBfWpVd2Mx2AzRqJuDJCsgaDVZ7HB5iGzDW1Hl1sWN2mFyKjmR9uAog==}
    engines: {node: '>=6.9.0'}

  '@babel/template@7.27.1':
    resolution: {integrity: sha512-Fyo3ghWMqkHHpHQCoBs2VnYjR4iWFFjguTDEqA5WgZDOrFesVjMhMM2FSqTKSoUSDO1VQtavj8NFpdRBEvJTtg==}
    engines: {node: '>=6.9.0'}

  '@babel/traverse@7.27.1':
    resolution: {integrity: sha512-ZCYtZciz1IWJB4U61UPu4KEaqyfj+r5T1Q5mqPo+IBpcG9kHv30Z0aD8LXPgC1trYa6rK0orRyAhqUgk4MjmEg==}
    engines: {node: '>=6.9.0'}

  '@babel/types@7.27.1':
    resolution: {integrity: sha512-+EzkxvLNfiUeKMgy/3luqfsCWFRXLb7U6wNQTk60tovuckwB15B191tJWvpp4HjiQWdJkCxO3Wbvc6jlk3Xb2Q==}
    engines: {node: '>=6.9.0'}

  '@chakra-ui/accordion@2.3.1':
    resolution: {integrity: sha512-FSXRm8iClFyU+gVaXisOSEw0/4Q+qZbFRiuhIAkVU6Boj0FxAMrlo9a8AV5TuF77rgaHytCdHk0Ng+cyUijrag==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      framer-motion: '>=4.0.0'
      react: '>=18'

  '@chakra-ui/alert@2.2.1':
    resolution: {integrity: sha512-GduIqqWCkvID8hxRlKw29Jp3w93r/E9S30J2F8By3ODon9Bhk1o/KVolcPiSiQvRwKNBJCd/rBTpPpLkB+s7pw==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/anatomy@2.2.1':
    resolution: {integrity: sha512-bbmyWTGwQo+aHYDMtLIj7k7hcWvwE7GFVDViLFArrrPhfUTDdQTNqhiDp1N7eh2HLyjNhc2MKXV8s2KTQqkmTg==}

  '@chakra-ui/avatar@2.3.0':
    resolution: {integrity: sha512-8gKSyLfygnaotbJbDMHDiJoF38OHXUYVme4gGxZ1fLnQEdPVEaIWfH+NndIjOM0z8S+YEFnT9KyGMUtvPrBk3g==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/breadcrumb@2.2.0':
    resolution: {integrity: sha512-4cWCG24flYBxjruRi4RJREWTGF74L/KzI2CognAW/d/zWR0CjiScuJhf37Am3LFbCySP6WSoyBOtTIoTA4yLEA==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/breakpoint-utils@2.0.8':
    resolution: {integrity: sha512-Pq32MlEX9fwb5j5xx8s18zJMARNHlQZH2VH1RZgfgRDpp7DcEgtRW5AInfN5CfqdHLO1dGxA7I3MqEuL5JnIsA==}

  '@chakra-ui/button@2.1.0':
    resolution: {integrity: sha512-95CplwlRKmmUXkdEp/21VkEWgnwcx2TOBG6NfYlsuLBDHSLlo5FKIiE2oSi4zXc4TLcopGcWPNcm/NDaSC5pvA==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/card@2.2.0':
    resolution: {integrity: sha512-xUB/k5MURj4CtPAhdSoXZidUbm8j3hci9vnc+eZJVDqhDOShNlD6QeniQNRPRys4lWAQLCbFcrwL29C8naDi6g==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/checkbox@2.3.1':
    resolution: {integrity: sha512-e6qL9ntVI/Ui6g0+iljUV2chX86YMsXafldpTHBNYDEoNLjGo1lqLFzq3y6zs3iuB3DHI0X7eAG3REmMVs0A0w==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/clickable@2.1.0':
    resolution: {integrity: sha512-flRA/ClPUGPYabu+/GLREZVZr9j2uyyazCAUHAdrTUEdDYCr31SVGhgh7dgKdtq23bOvAQJpIJjw/0Bs0WvbXw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/close-button@2.1.1':
    resolution: {integrity: sha512-gnpENKOanKexswSVpVz7ojZEALl2x5qjLYNqSQGbxz+aP9sOXPfUS56ebyBrre7T7exuWGiFeRwnM0oVeGPaiw==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/color-mode@2.2.0':
    resolution: {integrity: sha512-niTEA8PALtMWRI9wJ4LL0CSBDo8NBfLNp4GD6/0hstcm3IlbBHTVKxN6HwSaoNYfphDQLxCjT4yG+0BJA5tFpg==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/control-box@2.1.0':
    resolution: {integrity: sha512-gVrRDyXFdMd8E7rulL0SKeoljkLQiPITFnsyMO8EFHNZ+AHt5wK4LIguYVEq88APqAGZGfHFWXr79RYrNiE3Mg==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/counter@2.1.0':
    resolution: {integrity: sha512-s6hZAEcWT5zzjNz2JIWUBzRubo9la/oof1W7EKZVVfPYHERnl5e16FmBC79Yfq8p09LQ+aqFKm/etYoJMMgghw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/css-reset@2.3.0':
    resolution: {integrity: sha512-cQwwBy5O0jzvl0K7PLTLgp8ijqLPKyuEMiDXwYzl95seD3AoeuoCLyzZcJtVqaUZ573PiBdAbY/IlZcwDOItWg==}
    peerDependencies:
      '@emotion/react': '>=10.0.35'
      react: '>=18'

  '@chakra-ui/descendant@3.1.0':
    resolution: {integrity: sha512-VxCIAir08g5w27klLyi7PVo8BxhW4tgU/lxQyujkmi4zx7hT9ZdrcQLAted/dAa+aSIZ14S1oV0Q9lGjsAdxUQ==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/dom-utils@2.1.0':
    resolution: {integrity: sha512-ZmF2qRa1QZ0CMLU8M1zCfmw29DmPNtfjR9iTo74U5FPr3i1aoAh7fbJ4qAlZ197Xw9eAW28tvzQuoVWeL5C7fQ==}

  '@chakra-ui/editable@3.1.0':
    resolution: {integrity: sha512-j2JLrUL9wgg4YA6jLlbU88370eCRyor7DZQD9lzpY95tSOXpTljeg3uF9eOmDnCs6fxp3zDWIfkgMm/ExhcGTg==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/event-utils@2.0.8':
    resolution: {integrity: sha512-IGM/yGUHS+8TOQrZGpAKOJl/xGBrmRYJrmbHfUE7zrG3PpQyXvbLDP1M+RggkCFVgHlJi2wpYIf0QtQlU0XZfw==}

  '@chakra-ui/focus-lock@2.1.0':
    resolution: {integrity: sha512-EmGx4PhWGjm4dpjRqM4Aa+rCWBxP+Rq8Uc/nAVnD4YVqkEhBkrPTpui2lnjsuxqNaZ24fIAZ10cF1hlpemte/w==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/form-control@2.1.1':
    resolution: {integrity: sha512-LJPDzA1ITc3lhd/iDiINqGeca5bJD09PZAjePGEmmZyLPZZi8nPh/iii0RMxvKyJArsTBwXymCh+dEqK9aDzGQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/hooks@2.2.1':
    resolution: {integrity: sha512-RQbTnzl6b1tBjbDPf9zGRo9rf/pQMholsOudTxjy4i9GfTfz6kgp5ValGjQm2z7ng6Z31N1cnjZ1AlSzQ//ZfQ==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/icon@3.2.0':
    resolution: {integrity: sha512-xxjGLvlX2Ys4H0iHrI16t74rG9EBcpFvJ3Y3B7KMQTrnW34Kf7Da/UC8J67Gtx85mTHW020ml85SVPKORWNNKQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/image@2.1.0':
    resolution: {integrity: sha512-bskumBYKLiLMySIWDGcz0+D9Th0jPvmX6xnRMs4o92tT3Od/bW26lahmV2a2Op2ItXeCmRMY+XxJH5Gy1i46VA==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/input@2.1.1':
    resolution: {integrity: sha512-RQYzQ/qcak3eCuCfvSqc1kEFx0sCcnIeiSi7i0r70CeBnAUK/CP1/4Uz849FpKz81K4z2SikC9MkHPQd8ZpOwg==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/layout@2.3.1':
    resolution: {integrity: sha512-nXuZ6WRbq0WdgnRgLw+QuxWAHuhDtVX8ElWqcTK+cSMFg/52eVP47czYBE5F35YhnoW2XBwfNoNgZ7+e8Z01Rg==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/lazy-utils@2.0.5':
    resolution: {integrity: sha512-UULqw7FBvcckQk2n3iPO56TMJvDsNv0FKZI6PlUNJVaGsPbsYxK/8IQ60vZgaTVPtVcjY6BE+y6zg8u9HOqpyg==}

  '@chakra-ui/live-region@2.1.0':
    resolution: {integrity: sha512-ZOxFXwtaLIsXjqnszYYrVuswBhnIHHP+XIgK1vC6DePKtyK590Wg+0J0slDwThUAd4MSSIUa/nNX84x1GMphWw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/media-query@3.3.0':
    resolution: {integrity: sha512-IsTGgFLoICVoPRp9ykOgqmdMotJG0CnPsKvGQeSFOB/dZfIujdVb14TYxDU4+MURXry1MhJ7LzZhv+Ml7cr8/g==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/menu@2.2.1':
    resolution: {integrity: sha512-lJS7XEObzJxsOwWQh7yfG4H8FzFPRP5hVPN/CL+JzytEINCSBvsCDHrYPQGp7jzpCi8vnTqQQGQe0f8dwnXd2g==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      framer-motion: '>=4.0.0'
      react: '>=18'

  '@chakra-ui/modal@2.3.1':
    resolution: {integrity: sha512-TQv1ZaiJMZN+rR9DK0snx/OPwmtaGH1HbZtlYt4W4s6CzyK541fxLRTjIXfEzIGpvNW+b6VFuFjbcR78p4DEoQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      framer-motion: '>=4.0.0'
      react: '>=18'
      react-dom: '>=18'

  '@chakra-ui/number-input@2.1.1':
    resolution: {integrity: sha512-B4xwUPyr0NmjGN/dBhOmCD2xjX6OY1pr9GmGH3GQRozMsLAClD3TibwiZetwlyCp02qQqiFwEcZmUxaX88794Q==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/number-utils@2.0.7':
    resolution: {integrity: sha512-yOGxBjXNvLTBvQyhMDqGU0Oj26s91mbAlqKHiuw737AXHt0aPllOthVUqQMeaYLwLCjGMg0jtI7JReRzyi94Dg==}

  '@chakra-ui/object-utils@2.1.0':
    resolution: {integrity: sha512-tgIZOgLHaoti5PYGPTwK3t/cqtcycW0owaiOXoZOcpwwX/vlVb+H1jFsQyWiiwQVPt9RkoSLtxzXamx+aHH+bQ==}

  '@chakra-ui/pin-input@2.1.0':
    resolution: {integrity: sha512-x4vBqLStDxJFMt+jdAHHS8jbh294O53CPQJoL4g228P513rHylV/uPscYUHrVJXRxsHfRztQO9k45jjTYaPRMw==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/popover@2.2.1':
    resolution: {integrity: sha512-K+2ai2dD0ljvJnlrzesCDT9mNzLifE3noGKZ3QwLqd/K34Ym1W/0aL1ERSynrcG78NKoXS54SdEzkhCZ4Gn/Zg==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      framer-motion: '>=4.0.0'
      react: '>=18'

  '@chakra-ui/popper@3.1.0':
    resolution: {integrity: sha512-ciDdpdYbeFG7og6/6J8lkTFxsSvwTdMLFkpVylAF6VNC22jssiWfquj2eyD4rJnzkRFPvIWJq8hvbfhsm+AjSg==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/portal@2.1.0':
    resolution: {integrity: sha512-9q9KWf6SArEcIq1gGofNcFPSWEyl+MfJjEUg/un1SMlQjaROOh3zYr+6JAwvcORiX7tyHosnmWC3d3wI2aPSQg==}
    peerDependencies:
      react: '>=18'
      react-dom: '>=18'

  '@chakra-ui/progress@2.2.0':
    resolution: {integrity: sha512-qUXuKbuhN60EzDD9mHR7B67D7p/ZqNS2Aze4Pbl1qGGZfulPW0PY8Rof32qDtttDQBkzQIzFGE8d9QpAemToIQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/provider@2.4.1':
    resolution: {integrity: sha512-u4g02V9tJ9vVYfkLz5jBn/bKlAyjLdg4Sh3f7uckmYVAZpOL/uUlrStyADrynu3tZhI+BE8XdmXC4zs/SYD7ow==}
    peerDependencies:
      '@emotion/react': ^11.0.0
      '@emotion/styled': ^11.0.0
      react: '>=18'
      react-dom: '>=18'

  '@chakra-ui/radio@2.1.1':
    resolution: {integrity: sha512-5JXDVvMWsF/Cprh6BKfcTLbLtRcgD6Wl2zwbNU30nmKIE8+WUfqD7JQETV08oWEzhi3Ea4e5EHvyll2sGx8H3w==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/react-children-utils@2.0.6':
    resolution: {integrity: sha512-QVR2RC7QsOsbWwEnq9YduhpqSFnZGvjjGREV8ygKi8ADhXh93C8azLECCUVgRJF2Wc+So1fgxmjLcbZfY2VmBA==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-context@2.1.0':
    resolution: {integrity: sha512-iahyStvzQ4AOwKwdPReLGfDesGG+vWJfEsn0X/NoGph/SkN+HXtv2sCfYFFR9k7bb+Kvc6YfpLlSuLvKMHi2+w==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-env@3.1.0':
    resolution: {integrity: sha512-Vr96GV2LNBth3+IKzr/rq1IcnkXv+MLmwjQH6C8BRtn3sNskgDFD5vLkVXcEhagzZMCh8FR3V/bzZPojBOyNhw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-types@2.0.7':
    resolution: {integrity: sha512-12zv2qIZ8EHwiytggtGvo4iLT0APris7T0qaAWqzpUGS0cdUtR8W+V1BJ5Ocq+7tA6dzQ/7+w5hmXih61TuhWQ==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-animation-state@2.1.0':
    resolution: {integrity: sha512-CFZkQU3gmDBwhqy0vC1ryf90BVHxVN8cTLpSyCpdmExUEtSEInSCGMydj2fvn7QXsz/za8JNdO2xxgJwxpLMtg==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-callback-ref@2.1.0':
    resolution: {integrity: sha512-efnJrBtGDa4YaxDzDE90EnKD3Vkh5a1t3w7PhnRQmsphLy3g2UieasoKTlT2Hn118TwDjIv5ZjHJW6HbzXA9wQ==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-controllable-state@2.1.0':
    resolution: {integrity: sha512-QR/8fKNokxZUs4PfxjXuwl0fj/d71WPrmLJvEpCTkHjnzu7LnYvzoe2wB867IdooQJL0G1zBxl0Dq+6W1P3jpg==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-disclosure@2.1.0':
    resolution: {integrity: sha512-Ax4pmxA9LBGMyEZJhhUZobg9C0t3qFE4jVF1tGBsrLDcdBeLR9fwOogIPY9Hf0/wqSlAryAimICbr5hkpa5GSw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-event-listener@2.1.0':
    resolution: {integrity: sha512-U5greryDLS8ISP69DKDsYcsXRtAdnTQT+jjIlRYZ49K/XhUR/AqVZCK5BkR1spTDmO9H8SPhgeNKI70ODuDU/Q==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-focus-effect@2.1.0':
    resolution: {integrity: sha512-xzVboNy7J64xveLcxTIJ3jv+lUJKDwRM7Szwn9tNzUIPD94O3qwjV7DDCUzN2490nSYDF4OBMt/wuDBtaR3kUQ==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-focus-on-pointer-down@2.1.0':
    resolution: {integrity: sha512-2jzrUZ+aiCG/cfanrolsnSMDykCAbv9EK/4iUyZno6BYb3vziucmvgKuoXbMPAzWNtwUwtuMhkby8rc61Ue+Lg==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-interval@2.1.0':
    resolution: {integrity: sha512-8iWj+I/+A0J08pgEXP1J1flcvhLBHkk0ln7ZvGIyXiEyM6XagOTJpwNhiu+Bmk59t3HoV/VyvyJTa+44sEApuw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-latest-ref@2.1.0':
    resolution: {integrity: sha512-m0kxuIYqoYB0va9Z2aW4xP/5b7BzlDeWwyXCH6QpT2PpW3/281L3hLCm1G0eOUcdVlayqrQqOeD6Mglq+5/xoQ==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-merge-refs@2.1.0':
    resolution: {integrity: sha512-lERa6AWF1cjEtWSGjxWTaSMvneccnAVH4V4ozh8SYiN9fSPZLlSG3kNxfNzdFvMEhM7dnP60vynF7WjGdTgQbQ==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-outside-click@2.2.0':
    resolution: {integrity: sha512-PNX+s/JEaMneijbgAM4iFL+f3m1ga9+6QK0E5Yh4s8KZJQ/bLwZzdhMz8J/+mL+XEXQ5J0N8ivZN28B82N1kNw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-pan-event@2.1.0':
    resolution: {integrity: sha512-xmL2qOHiXqfcj0q7ZK5s9UjTh4Gz0/gL9jcWPA6GVf+A0Od5imEDa/Vz+533yQKWiNSm1QGrIj0eJAokc7O4fg==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-previous@2.1.0':
    resolution: {integrity: sha512-pjxGwue1hX8AFcmjZ2XfrQtIJgqbTF3Qs1Dy3d1krC77dEsiCUbQ9GzOBfDc8pfd60DrB5N2tg5JyHbypqh0Sg==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-safe-layout-effect@2.1.0':
    resolution: {integrity: sha512-Knbrrx/bcPwVS1TorFdzrK/zWA8yuU/eaXDkNj24IrKoRlQrSBFarcgAEzlCHtzuhufP3OULPkELTzz91b0tCw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-size@2.1.0':
    resolution: {integrity: sha512-tbLqrQhbnqOjzTaMlYytp7wY8BW1JpL78iG7Ru1DlV4EWGiAmXFGvtnEt9HftU0NJ0aJyjgymkxfVGI55/1Z4A==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-timeout@2.1.0':
    resolution: {integrity: sha512-cFN0sobKMM9hXUhyCofx3/Mjlzah6ADaEl/AXl5Y+GawB5rgedgAcu2ErAgarEkwvsKdP6c68CKjQ9dmTQlJxQ==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-use-update-effect@2.1.0':
    resolution: {integrity: sha512-ND4Q23tETaR2Qd3zwCKYOOS1dfssojPLJMLvUtUbW5M9uW1ejYWgGUobeAiOVfSplownG8QYMmHTP86p/v0lbA==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react-utils@2.0.12':
    resolution: {integrity: sha512-GbSfVb283+YA3kA8w8xWmzbjNWk14uhNpntnipHCftBibl0lxtQ9YqMFQLwuFOO0U2gYVocszqqDWX+XNKq9hw==}
    peerDependencies:
      react: '>=18'

  '@chakra-ui/react@2.8.1':
    resolution: {integrity: sha512-UL9Rtj4DovP3+oVbI06gsdfyJJb+wmS2RYnGNXjW9tsjCyXxjlBw9TAUj0jyOfWe0+zd/4juL8+J+QCwmdhptg==}
    peerDependencies:
      '@emotion/react': ^11.0.0
      '@emotion/styled': ^11.0.0
      framer-motion: '>=4.0.0'
      react: '>=18'
      react-dom: '>=18'

  '@chakra-ui/select@2.1.1':
    resolution: {integrity: sha512-CERDATncv5w05Zo5/LrFtf1yKp1deyMUyDGv6eZvQG/etyukH4TstsuIHt/0GfNXrCF3CJLZ8lINzpv5wayVjQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/shared-utils@2.0.5':
    resolution: {integrity: sha512-4/Wur0FqDov7Y0nCXl7HbHzCg4aq86h+SXdoUeuCMD3dSj7dpsVnStLYhng1vxvlbUnLpdF4oz5Myt3i/a7N3Q==}

  '@chakra-ui/skeleton@2.1.0':
    resolution: {integrity: sha512-JNRuMPpdZGd6zFVKjVQ0iusu3tXAdI29n4ZENYwAJEMf/fN0l12sVeirOxkJ7oEL0yOx2AgEYFSKdbcAgfUsAQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/skip-nav@2.1.0':
    resolution: {integrity: sha512-Hk+FG+vadBSH0/7hwp9LJnLjkO0RPGnx7gBJWI4/SpoJf3e4tZlWYtwGj0toYY4aGKl93jVghuwGbDBEMoHDug==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/slider@2.1.0':
    resolution: {integrity: sha512-lUOBcLMCnFZiA/s2NONXhELJh6sY5WtbRykPtclGfynqqOo47lwWJx+VP7xaeuhDOPcWSSecWc9Y1BfPOCz9cQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/spinner@2.1.0':
    resolution: {integrity: sha512-hczbnoXt+MMv/d3gE+hjQhmkzLiKuoTo42YhUG7Bs9OSv2lg1fZHW1fGNRFP3wTi6OIbD044U1P9HK+AOgFH3g==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/stat@2.1.1':
    resolution: {integrity: sha512-LDn0d/LXQNbAn2KaR3F1zivsZCewY4Jsy1qShmfBMKwn6rI8yVlbvu6SiA3OpHS0FhxbsZxQI6HefEoIgtqY6Q==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/stepper@2.3.1':
    resolution: {integrity: sha512-ky77lZbW60zYkSXhYz7kbItUpAQfEdycT0Q4bkHLxfqbuiGMf8OmgZOQkOB9uM4v0zPwy2HXhe0vq4Dd0xa55Q==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/styled-system@2.9.1':
    resolution: {integrity: sha512-jhYKBLxwOPi9/bQt9kqV3ELa/4CjmNNruTyXlPp5M0v0+pDMUngPp48mVLoskm9RKZGE0h1qpvj/jZ3K7c7t8w==}

  '@chakra-ui/switch@2.1.1':
    resolution: {integrity: sha512-cOHIhW5AlLZSFENxFEBYTBniqiduOowa1WdzslP1Fd0usBFaD5iAgOY1Fvr7xKhE8nmzzeMCkPB3XBvUSWnawQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      framer-motion: '>=4.0.0'
      react: '>=18'

  '@chakra-ui/system@2.6.1':
    resolution: {integrity: sha512-P5Q/XRWy3f1pXJ7IxDkV+Z6AT7GJeR2JlBnQl109xewVQcBLWWMIp702fFMFw8KZ2ALB/aYKtWm5EmQMddC/tg==}
    peerDependencies:
      '@emotion/react': ^11.0.0
      '@emotion/styled': ^11.0.0
      react: '>=18'

  '@chakra-ui/table@2.1.0':
    resolution: {integrity: sha512-o5OrjoHCh5uCLdiUb0Oc0vq9rIAeHSIRScc2ExTC9Qg/uVZl2ygLrjToCaKfaaKl1oQexIeAcZDKvPG8tVkHyQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/tabs@3.0.0':
    resolution: {integrity: sha512-6Mlclp8L9lqXmsGWF5q5gmemZXOiOYuh0SGT/7PgJVNPz3LXREXlXg2an4MBUD8W5oTkduCX+3KTMCwRrVrDYw==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/tag@3.1.1':
    resolution: {integrity: sha512-Bdel79Dv86Hnge2PKOU+t8H28nm/7Y3cKd4Kfk9k3lOpUh4+nkSGe58dhRzht59lEqa4N9waCgQiBdkydjvBXQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/textarea@2.1.1':
    resolution: {integrity: sha512-28bpwgmXg3BzSpg8i1Ao9h7pHaE1j2mBBFJpWaqPgMhS0IHm0BQsqqyWU6PsxxJDvrC4HN6MTzrIL4C1RA1I0A==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@chakra-ui/theme-tools@2.1.1':
    resolution: {integrity: sha512-n14L5L3ej3Zy+Xm/kDKO1G6/DkmieT7Li1C7NzMRcUj5C9YybQpyo7IZZ0BBUh3u+OVnKVhNC3d4P2NYDGRXmA==}
    peerDependencies:
      '@chakra-ui/styled-system': '>=2.0.0'

  '@chakra-ui/theme-utils@2.0.20':
    resolution: {integrity: sha512-IkAzSmwBlRIZ3dN2InDz0tf9SldbckVkgwylCobSFmYP8lnMjykL8Lex1BBo9U8UQjZxEDVZ+Qw6SeayKRntOQ==}

  '@chakra-ui/theme@3.3.0':
    resolution: {integrity: sha512-VHY2ax5Wqgfm83U/zYBk0GS0TGD8m41s/rxQgnEq8tU+ug1YZjvOZmtOq/VjfKP/bQraFhCt05zchcxXmDpEYg==}
    peerDependencies:
      '@chakra-ui/styled-system': '>=2.8.0'

  '@chakra-ui/toast@7.0.1':
    resolution: {integrity: sha512-V5JUhw6RZxbGRTijvd5k4iEMLCfbzTLNWbZLZhRZk10YvFfAP5OYfRCm68zpE/t3orN/f+4ZLL3P+Wb4E7oSmw==}
    peerDependencies:
      '@chakra-ui/system': 2.6.1
      framer-motion: '>=4.0.0'
      react: '>=18'
      react-dom: '>=18'

  '@chakra-ui/tooltip@2.3.0':
    resolution: {integrity: sha512-2s23f93YIij1qEDwIK//KtEu4LLYOslhR1cUhDBk/WUzyFR3Ez0Ee+HlqlGEGfGe9x77E6/UXPnSAKKdF/cpsg==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      framer-motion: '>=4.0.0'
      react: '>=18'
      react-dom: '>=18'

  '@chakra-ui/transition@2.1.0':
    resolution: {integrity: sha512-orkT6T/Dt+/+kVwJNy7zwJ+U2xAZ3EU7M3XCs45RBvUnZDr/u9vdmaM/3D/rOpmQJWgQBwKPJleUXrYWUagEDQ==}
    peerDependencies:
      framer-motion: '>=4.0.0'
      react: '>=18'

  '@chakra-ui/utils@2.0.15':
    resolution: {integrity: sha512-El4+jL0WSaYYs+rJbuYFDbjmfCcfGDmRY95GO4xwzit6YAPZBLcR65rOEwLps+XWluZTy1xdMrusg/hW0c1aAA==}

  '@chakra-ui/visually-hidden@2.2.0':
    resolution: {integrity: sha512-KmKDg01SrQ7VbTD3+cPWf/UfpF5MSwm3v7MWi0n5t8HnnadT13MF0MJCDSXbBWnzLv1ZKJ6zlyAOeARWX+DpjQ==}
    peerDependencies:
      '@chakra-ui/system': '>=2.0.0'
      react: '>=18'

  '@emnapi/runtime@1.4.3':
    resolution: {integrity: sha512-pBPWdu6MLKROBX05wSNKcNb++m5Er+KQ9QkB+WVM+pW2Kx9hoSrVTnu3BdkI5eBLZoKu/J6mW/B6i6bJB2ytXQ==}

  '@emotion/babel-plugin@11.13.5':
    resolution: {integrity: sha512-pxHCpT2ex+0q+HH91/zsdHkw/lXd468DIN2zvfvLtPKLLMo6gQj7oLObq8PhkrxOZb/gGCq03S3Z7PDhS8pduQ==}

  '@emotion/cache@11.14.0':
    resolution: {integrity: sha512-L/B1lc/TViYk4DcpGxtAVbx0ZyiKM5ktoIyafGkH6zg/tj+mA+NE//aPYKG0k8kCHSHVJrpLpcAlOBEXQ3SavA==}

  '@emotion/hash@0.9.2':
    resolution: {integrity: sha512-MyqliTZGuOm3+5ZRSaaBGP3USLw6+EGykkwZns2EPC5g8jJ4z9OrdZY9apkl3+UP9+sdz76YYkwCKP5gh8iY3g==}

  '@emotion/is-prop-valid@0.8.8':
    resolution: {integrity: sha512-u5WtneEAr5IDG2Wv65yhunPSMLIpuKsbuOktRojfrEiEvRyC85LgPMZI63cr7NUqT8ZIGdSVg8ZKGxIug4lXcA==}

  '@emotion/is-prop-valid@1.3.1':
    resolution: {integrity: sha512-/ACwoqx7XQi9knQs/G0qKvv5teDMhD7bXYns9N/wM8ah8iNb8jZ2uNO0YOgiq2o2poIvVtJS2YALasQuMSQ7Kw==}

  '@emotion/memoize@0.7.4':
    resolution: {integrity: sha512-Ja/Vfqe3HpuzRsG1oBtWTHk2PGZ7GR+2Vz5iYGelAw8dx32K0y7PjVuxK6z1nMpZOqAFsRUPCkK1YjJ56qJlgw==}

  '@emotion/memoize@0.9.0':
    resolution: {integrity: sha512-30FAj7/EoJ5mwVPOWhAyCX+FPfMDrVecJAM+Iw9NRoSl4BBAQeqj4cApHHUXOVvIPgLVDsCFoz/hGD+5QQD1GQ==}

  '@emotion/react@11.11.0':
    resolution: {integrity: sha512-ZSK3ZJsNkwfjT3JpDAWJZlrGD81Z3ytNDsxw1LKq1o+xkmO5pnWfr6gmCC8gHEFf3nSSX/09YrG67jybNPxSUw==}
    peerDependencies:
      '@types/react': '*'
      react: '>=16.8.0'
    peerDependenciesMeta:
      '@types/react':
        optional: true

  '@emotion/serialize@1.3.3':
    resolution: {integrity: sha512-EISGqt7sSNWHGI76hC7x1CksiXPahbxEOrC5RjmFRJTqLyEK9/9hZvBbiYn70dw4wuwMKiEMCUlR6ZXTSWQqxA==}

  '@emotion/sheet@1.4.0':
    resolution: {integrity: sha512-fTBW9/8r2w3dXWYM4HCB1Rdp8NLibOw2+XELH5m5+AkWiL/KqYX6dc0kKYlaYyKjrQ6ds33MCdMPEwgs2z1rqg==}

  '@emotion/styled@11.11.0':
    resolution: {integrity: sha512-hM5Nnvu9P3midq5aaXj4I+lnSfNi7Pmd4EWk1fOZ3pxookaQTNew6bp4JaCBYM4HVFZF9g7UjJmsUmC2JlxOng==}
    peerDependencies:
      '@emotion/react': ^11.0.0-rc.0
      '@types/react': '*'
      react: '>=16.8.0'
    peerDependenciesMeta:
      '@types/react':
        optional: true

  '@emotion/unitless@0.10.0':
    resolution: {integrity: sha512-dFoMUuQA20zvtVTuxZww6OHoJYgrzfKM1t52mVySDJnMSEa08ruEvdYQbhvyu6soU+NeLVd3yKfTfT0NeV6qGg==}

  '@emotion/use-insertion-effect-with-fallbacks@1.2.0':
    resolution: {integrity: sha512-yJMtVdH59sxi/aVJBpk9FQq+OR8ll5GT8oWd57UpeaKEVGab41JWaCFA7FRLoMLloOZF/c/wsPoe+bfGmRKgDg==}
    peerDependencies:
      react: '>=16.8.0'

  '@emotion/utils@1.4.2':
    resolution: {integrity: sha512-3vLclRofFziIa3J2wDh9jjbkUz9qk5Vi3IZ/FSTKViB0k+ef0fPV7dYrUIugbgupYDx7v9ud/SjrtEP8Y4xLoA==}

  '@emotion/weak-memoize@0.3.1':
    resolution: {integrity: sha512-EsBwpc7hBUJWAsNPBmJy4hxWx12v6bshQsldrVmjxJoc3isbxhOrF2IcCpaXxfvq03NwkI7sbsOLXbYuqF/8Ww==}

  '@emotion/weak-memoize@0.4.0':
    resolution: {integrity: sha512-snKqtPW01tN0ui7yu9rGv69aJXr/a/Ywvl11sUjNtEcRc+ng/mQriFL0wLXMef74iHa/EkftbDzU9F8iFbH+zg==}

  '@heroicons/react@2.2.0':
    resolution: {integrity: sha512-LMcepvRaS9LYHJGsF0zzmgKCUim/X3N/DQKc4jepAXJ7l8QxJ1PmxJzqplF2Z3FE4PqBAIGyJAQ/w4B5dsqbtQ==}
    peerDependencies:
      react: '>= 16 || ^19.0.0-rc'

  '@img/sharp-darwin-arm64@0.33.5':
    resolution: {integrity: sha512-UT4p+iz/2H4twwAoLCqfA9UH5pI6DggwKEGuaPy7nCVQ8ZsiY5PIcrRvD1DzuY3qYL07NtIQcWnBSY/heikIFQ==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [arm64]
    os: [darwin]

  '@img/sharp-darwin-x64@0.33.5':
    resolution: {integrity: sha512-fyHac4jIc1ANYGRDxtiqelIbdWkIuQaI84Mv45KvGRRxSAa7o7d1ZKAOBaYbnepLC1WqxfpimdeWfvqqSGwR2Q==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [x64]
    os: [darwin]

  '@img/sharp-libvips-darwin-arm64@1.0.4':
    resolution: {integrity: sha512-XblONe153h0O2zuFfTAbQYAX2JhYmDHeWikp1LM9Hul9gVPjFY427k6dFEcOL72O01QxQsWi761svJ/ev9xEDg==}
    cpu: [arm64]
    os: [darwin]

  '@img/sharp-libvips-darwin-x64@1.0.4':
    resolution: {integrity: sha512-xnGR8YuZYfJGmWPvmlunFaWJsb9T/AO2ykoP3Fz/0X5XV2aoYBPkX6xqCQvUTKKiLddarLaxpzNe+b1hjeWHAQ==}
    cpu: [x64]
    os: [darwin]

  '@img/sharp-libvips-linux-arm64@1.0.4':
    resolution: {integrity: sha512-9B+taZ8DlyyqzZQnoeIvDVR/2F4EbMepXMc/NdVbkzsJbzkUjhXv/70GQJ7tdLA4YJgNP25zukcxpX2/SueNrA==}
    cpu: [arm64]
    os: [linux]

  '@img/sharp-libvips-linux-arm@1.0.5':
    resolution: {integrity: sha512-gvcC4ACAOPRNATg/ov8/MnbxFDJqf/pDePbBnuBDcjsI8PssmjoKMAz4LtLaVi+OnSb5FK/yIOamqDwGmXW32g==}
    cpu: [arm]
    os: [linux]

  '@img/sharp-libvips-linux-s390x@1.0.4':
    resolution: {integrity: sha512-u7Wz6ntiSSgGSGcjZ55im6uvTrOxSIS8/dgoVMoiGE9I6JAfU50yH5BoDlYA1tcuGS7g/QNtetJnxA6QEsCVTA==}
    cpu: [s390x]
    os: [linux]

  '@img/sharp-libvips-linux-x64@1.0.4':
    resolution: {integrity: sha512-MmWmQ3iPFZr0Iev+BAgVMb3ZyC4KeFc3jFxnNbEPas60e1cIfevbtuyf9nDGIzOaW9PdnDciJm+wFFaTlj5xYw==}
    cpu: [x64]
    os: [linux]

  '@img/sharp-libvips-linuxmusl-arm64@1.0.4':
    resolution: {integrity: sha512-9Ti+BbTYDcsbp4wfYib8Ctm1ilkugkA/uscUn6UXK1ldpC1JjiXbLfFZtRlBhjPZ5o1NCLiDbg8fhUPKStHoTA==}
    cpu: [arm64]
    os: [linux]

  '@img/sharp-libvips-linuxmusl-x64@1.0.4':
    resolution: {integrity: sha512-viYN1KX9m+/hGkJtvYYp+CCLgnJXwiQB39damAO7WMdKWlIhmYTfHjwSbQeUK/20vY154mwezd9HflVFM1wVSw==}
    cpu: [x64]
    os: [linux]

  '@img/sharp-linux-arm64@0.33.5':
    resolution: {integrity: sha512-JMVv+AMRyGOHtO1RFBiJy/MBsgz0x4AWrT6QoEVVTyh1E39TrCUpTRI7mx9VksGX4awWASxqCYLCV4wBZHAYxA==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [arm64]
    os: [linux]

  '@img/sharp-linux-arm@0.33.5':
    resolution: {integrity: sha512-JTS1eldqZbJxjvKaAkxhZmBqPRGmxgu+qFKSInv8moZ2AmT5Yib3EQ1c6gp493HvrvV8QgdOXdyaIBrhvFhBMQ==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [arm]
    os: [linux]

  '@img/sharp-linux-s390x@0.33.5':
    resolution: {integrity: sha512-y/5PCd+mP4CA/sPDKl2961b+C9d+vPAveS33s6Z3zfASk2j5upL6fXVPZi7ztePZ5CuH+1kW8JtvxgbuXHRa4Q==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [s390x]
    os: [linux]

  '@img/sharp-linux-x64@0.33.5':
    resolution: {integrity: sha512-opC+Ok5pRNAzuvq1AG0ar+1owsu842/Ab+4qvU879ippJBHvyY5n2mxF1izXqkPYlGuP/M556uh53jRLJmzTWA==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [x64]
    os: [linux]

  '@img/sharp-linuxmusl-arm64@0.33.5':
    resolution: {integrity: sha512-XrHMZwGQGvJg2V/oRSUfSAfjfPxO+4DkiRh6p2AFjLQztWUuY/o8Mq0eMQVIY7HJ1CDQUJlxGGZRw1a5bqmd1g==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [arm64]
    os: [linux]

  '@img/sharp-linuxmusl-x64@0.33.5':
    resolution: {integrity: sha512-WT+d/cgqKkkKySYmqoZ8y3pxx7lx9vVejxW/W4DOFMYVSkErR+w7mf2u8m/y4+xHe7yY9DAXQMWQhpnMuFfScw==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [x64]
    os: [linux]

  '@img/sharp-wasm32@0.33.5':
    resolution: {integrity: sha512-ykUW4LVGaMcU9lu9thv85CbRMAwfeadCJHRsg2GmeRa/cJxsVY9Rbd57JcMxBkKHag5U/x7TSBpScF4U8ElVzg==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [wasm32]

  '@img/sharp-win32-ia32@0.33.5':
    resolution: {integrity: sha512-T36PblLaTwuVJ/zw/LaH0PdZkRz5rd3SmMHX8GSmR7vtNSP5Z6bQkExdSK7xGWyxLw4sUknBuugTelgw2faBbQ==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [ia32]
    os: [win32]

  '@img/sharp-win32-x64@0.33.5':
    resolution: {integrity: sha512-MpY/o8/8kj+EcnxwvrP4aTJSWw/aZ7JIGR4aBeZkZw5B7/Jn+tY9/VNwtcoGmdT7GfggGIU4kygOMSbYnOrAbg==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}
    cpu: [x64]
    os: [win32]

  '@ioredis/commands@1.2.0':
    resolution: {integrity: sha512-Sx1pU8EM64o2BrqNpEO1CNLtKQwyhuXuqyfH7oGKCk+1a33d2r5saW8zNwm3j6BTExtjrv2BxTgzzkMwts6vGg==}

  '@isaacs/cliui@8.0.2':
    resolution: {integrity: sha512-O8jcjabXaleOG9DQ0+ARXWZBTfnP4WNAqzuiJK7ll44AmxGKv/J2M4TPjxjY3znBCfvBXFzucm1twdyFybFqEA==}
    engines: {node: '>=12'}

  '@jridgewell/gen-mapping@0.3.8':
    resolution: {integrity: sha512-imAbBGkb+ebQyxKgzv5Hu2nmROxoDOXHh80evxdoXNOrvAnVx7zimzc1Oo5h9RlfV4vPXaE2iM5pOFbvOCClWA==}
    engines: {node: '>=6.0.0'}

  '@jridgewell/resolve-uri@3.1.2':
    resolution: {integrity: sha512-bRISgCIjP20/tbWSPWMEi54QVPRZExkuD9lJL+UIxUKtwVJA8wW1Trb1jMs1RFXo1CBTNZ/5hpC9QvmKWdopKw==}
    engines: {node: '>=6.0.0'}

  '@jridgewell/set-array@1.2.1':
    resolution: {integrity: sha512-R8gLRTZeyp03ymzP/6Lil/28tGeGEzhx1q2k703KGWRAI1VdvPIXdG70VJc2pAMw3NA6JKL5hhFu1sJX0Mnn/A==}
    engines: {node: '>=6.0.0'}

  '@jridgewell/sourcemap-codec@1.5.0':
    resolution: {integrity: sha512-gv3ZRaISU3fjPAgNsriBRqGWQL6quFx04YMPW/zD8XMLsU32mhCCbfbO6KZFLjvYpCZ8zyDEgqsgf+PwPaM7GQ==}

  '@jridgewell/trace-mapping@0.3.25':
    resolution: {integrity: sha512-vNk6aEwybGtawWmy/PzwnGDOjCkLWSD2wqvjGGAgOAwCGWySYXfYoxt00IJkTF+8Lb57DwOb3Aa0o9CApepiYQ==}

  '@motionone/animation@10.18.0':
    resolution: {integrity: sha512-9z2p5GFGCm0gBsZbi8rVMOAJCtw1WqBTIPw3ozk06gDvZInBPIsQcHgYogEJ4yuHJ+akuW8g1SEIOpTOvYs8hw==}

  '@motionone/dom@10.13.1':
    resolution: {integrity: sha512-zjfX+AGMIt/fIqd/SL1Lj93S6AiJsEA3oc5M9VkUr+Gz+juRmYN1vfvZd6MvEkSqEjwPQgcjN7rGZHrDB9APfQ==}

  '@motionone/easing@10.18.0':
    resolution: {integrity: sha512-VcjByo7XpdLS4o9T8t99JtgxkdMcNWD3yHU/n6CLEz3bkmKDRZyYQ/wmSf6daum8ZXqfUAgFeCZSpJZIMxaCzg==}

  '@motionone/generators@10.18.0':
    resolution: {integrity: sha512-+qfkC2DtkDj4tHPu+AFKVfR/C30O1vYdvsGYaR13W/1cczPrrcjdvYCj0VLFuRMN+lP1xvpNZHCRNM4fBzn1jg==}

  '@motionone/types@10.17.1':
    resolution: {integrity: sha512-KaC4kgiODDz8hswCrS0btrVrzyU2CSQKO7Ps90ibBVSQmjkrt2teqta6/sOG59v7+dPnKMAg13jyqtMKV2yJ7A==}

  '@motionone/utils@10.18.0':
    resolution: {integrity: sha512-3XVF7sgyTSI2KWvTf6uLlBJ5iAgRgmvp3bpuOiQJvInd4nZ19ET8lX5unn30SlmRH7hXbBbH+Gxd0m0klJ3Xtw==}

  '@next-auth/typeorm-legacy-adapter@2.0.2':
    resolution: {integrity: sha512-S74GepULrPA8Dym1FPSP5CUqbTyxPPeSB0ffe42OCzUEsO7qkV87syrCXUEmGUzGF7uvdc+dsOsxF94Ob11yCw==}
    peerDependencies:
      mssql: ^6.2.1 || 7
      mysql: ^2.18.1
      next-auth: ^4
      pg: ^8.2.1
      sqlite3: ^5.0.2
      typeorm: 0.3.7
    peerDependenciesMeta:
      mssql:
        optional: true
      mysql:
        optional: true
      pg:
        optional: true
      sqlite3:
        optional: true

  '@next/env@15.2.0':
    resolution: {integrity: sha512-eMgJu1RBXxxqqnuRJQh5RozhskoNUDHBFybvi+Z+yK9qzKeG7dadhv/Vp1YooSZmCnegf7JxWuapV77necLZNA==}

  '@next/swc-darwin-arm64@15.2.0':
    resolution: {integrity: sha512-rlp22GZwNJjFCyL7h5wz9vtpBVuCt3ZYjFWpEPBGzG712/uL1bbSkS675rVAUCRZ4hjoTJ26Q7IKhr5DfJrHDA==}
    engines: {node: '>= 10'}
    cpu: [arm64]
    os: [darwin]

  '@next/swc-darwin-x64@15.2.0':
    resolution: {integrity: sha512-DiU85EqSHogCz80+sgsx90/ecygfCSGl5P3b4XDRVZpgujBm5lp4ts7YaHru7eVTyZMjHInzKr+w0/7+qDrvMA==}
    engines: {node: '>= 10'}
    cpu: [x64]
    os: [darwin]

  '@next/swc-linux-arm64-gnu@15.2.0':
    resolution: {integrity: sha512-VnpoMaGukiNWVxeqKHwi8MN47yKGyki5q+7ql/7p/3ifuU2341i/gDwGK1rivk0pVYbdv5D8z63uu9yMw0QhpQ==}
    engines: {node: '>= 10'}
    cpu: [arm64]
    os: [linux]

  '@next/swc-linux-arm64-musl@15.2.0':
    resolution: {integrity: sha512-ka97/ssYE5nPH4Qs+8bd8RlYeNeUVBhcnsNUmFM6VWEob4jfN9FTr0NBhXVi1XEJpj3cMfgSRW+LdE3SUZbPrw==}
    engines: {node: '>= 10'}
    cpu: [arm64]
    os: [linux]

  '@next/swc-linux-x64-gnu@15.2.0':
    resolution: {integrity: sha512-zY1JduE4B3q0k2ZCE+DAF/1efjTXUsKP+VXRtrt/rJCTgDlUyyryx7aOgYXNc1d8gobys/Lof9P9ze8IyRDn7Q==}
    engines: {node: '>= 10'}
    cpu: [x64]
    os: [linux]

  '@next/swc-linux-x64-musl@15.2.0':
    resolution: {integrity: sha512-QqvLZpurBD46RhaVaVBepkVQzh8xtlUN00RlG4Iq1sBheNugamUNPuZEH1r9X1YGQo1KqAe1iiShF0acva3jHQ==}
    engines: {node: '>= 10'}
    cpu: [x64]
    os: [linux]

  '@next/swc-win32-arm64-msvc@15.2.0':
    resolution: {integrity: sha512-ODZ0r9WMyylTHAN6pLtvUtQlGXBL9voljv6ujSlcsjOxhtXPI1Ag6AhZK0SE8hEpR1374WZZ5w33ChpJd5fsjw==}
    engines: {node: '>= 10'}
    cpu: [arm64]
    os: [win32]

  '@next/swc-win32-x64-msvc@15.2.0':
    resolution: {integrity: sha512-8+4Z3Z7xa13NdUuUAcpVNA6o76lNPniBd9Xbo02bwXQXnZgFvEopwY2at5+z7yHl47X9qbZpvwatZ2BRo3EdZw==}
    engines: {node: '>= 10'}
    cpu: [x64]
    os: [win32]

  '@nodelib/fs.scandir@2.1.5':
    resolution: {integrity: sha512-vq24Bq3ym5HEQm2NKCr3yXDwjc7vTsEThRDnkp2DK9p1uqLR+DHurm/NOTo0KG7HYHU7eppKZj3MyqYuMBf62g==}
    engines: {node: '>= 8'}

  '@nodelib/fs.stat@2.0.5':
    resolution: {integrity: sha512-RkhPPp2zrqDAQA/2jNhnztcPAlv64XdhIp7a7454A5ovI7Bukxgt7MX7udwAu3zg1DcpPU0rz3VV1SeaqvY4+A==}
    engines: {node: '>= 8'}

  '@nodelib/fs.walk@1.2.8':
    resolution: {integrity: sha512-oGB+UxlgWcgQkgwo8GcEGwemoTFt3FIO9ababBmaGwXIoBKZ+GTy0pP185beGg7Llih/NSHSV2XAs1lnznocSg==}
    engines: {node: '>= 8'}

  '@panva/hkdf@1.2.1':
    resolution: {integrity: sha512-6oclG6Y3PiDFcoyk8srjLfVKyMfVCKJ27JwNPViuXziFpmdz+MZnZN/aKY0JGXgYuO/VghU0jcOAZgWXZ1Dmrw==}

  '@pkgjs/parseargs@0.11.0':
    resolution: {integrity: sha512-+1VkjdD0QBLPodGrJUeqarH8VAIvQODIbwh9XpP5Syisf7YoQgsJKPNFoqqLQlu+VQ/tVSshMR6loPMn8U+dPg==}
    engines: {node: '>=14'}

  '@popperjs/core@2.11.8':
    resolution: {integrity: sha512-P1st0aksCrn9sGZhp8GMYwBnQsbvAWsZAX44oXNNvLHGqAOcoVxmjZiohstwQ7SqKnbR47akdNi+uleWD8+g6A==}

  '@radix-ui/react-compose-refs@1.1.2':
    resolution: {integrity: sha512-z4eqJvfiNnFMHIIvXP3CY57y2WJs5g2v3X0zm9mEJkrkNv4rDxu+sg9Jh8EkXyeqBkB7SOcboo9dMVqhyrACIg==}
    peerDependencies:
      '@types/react': '*'
      react: ^16.8 || ^17.0 || ^18.0 || ^19.0 || ^19.0.0-rc
    peerDependenciesMeta:
      '@types/react':
        optional: true

  '@radix-ui/react-icons@1.3.2':
    resolution: {integrity: sha512-fyQIhGDhzfc9pK2kH6Pl9c4BDJGfMkPqkyIgYDthyNYoNg3wVhoJMMh19WS4Up/1KMPFVpNsT2q3WmXn2N1m6g==}
    peerDependencies:
      react: ^16.x || ^17.x || ^18.x || ^19.0.0 || ^19.0.0-rc

  '@radix-ui/react-slot@1.2.2':
    resolution: {integrity: sha512-y7TBO4xN4Y94FvcWIOIh18fM4R1A8S4q1jhoz4PNzOoHsFcN8pogcFmZrTYAm4F9VRUrWP/Mw7xSKybIeRI+CQ==}
    peerDependencies:
      '@types/react': '*'
      react: ^16.8 || ^17.0 || ^18.0 || ^19.0 || ^19.0.0-rc
    peerDependenciesMeta:
      '@types/react':
        optional: true

  '@shadcn/ui@0.0.4':
    resolution: {integrity: sha512-0dtu/5ApsOZ24qgaZwtif8jVwqol7a4m1x5AxPuM1k5wxhqU7t/qEfBGtaSki1R8VlbTQfCj5PAlO45NKCa7Gg==}
    hasBin: true

  '@sqltools/formatter@1.2.5':
    resolution: {integrity: sha512-Uy0+khmZqUrUGm5dmMqVlnvufZRSK0FbYzVgp0UMstm+F5+W2/jnEEQyc9vo1ZR/E5ZI/B1WjjoTqBqwJL6Krw==}

  '@swc/counter@0.1.3':
    resolution: {integrity: sha512-e2BR4lsJkkRlKZ/qCHPw9ZaSxc0MVUd7gtbtaB7aMvHeJVYe8sOB8DBZkP2DtISHGSku9sCK6T6cnY0CtXrOCQ==}

  '@swc/helpers@0.5.15':
    resolution: {integrity: sha512-JQ5TuMi45Owi4/BIMAJBoSQoOJu12oOk/gADqlcUL9JEdHB8vyjUSsxqeNXnmXHjYKMi2WcYtezGEEhqUI/E2g==}

  '@tailwindcss/forms@0.5.10':
    resolution: {integrity: sha512-utI1ONF6uf/pPNO68kmN1b8rEwNXv3czukalo8VtJH8ksIkZXr3Q3VYudZLkCsDd4Wku120uF02hYK25XGPorw==}
    peerDependencies:
      tailwindcss: '>=3.0.0 || >= 3.0.0-alpha.1 || >= 4.0.0-alpha.20 || >= 4.0.0-beta.1'

  '@tailwindcss/typography@0.5.16':
    resolution: {integrity: sha512-0wDLwCVF5V3x3b1SGXPCDcdsbDHMBe+lkFzBRaHeLvNi+nrrnZ1lA18u+OTWO8iSWU2GxUOCvlXtDuqftc1oiA==}
    peerDependencies:
      tailwindcss: '>=3.0.0 || insiders || >=4.0.0-alpha.20 || >=4.0.0-beta.1'

  '@types/debug@4.1.12':
    resolution: {integrity: sha512-vIChWdVG3LG1SMxEvI/AK+FWJthlrqlTu7fbrlywTkkaONwk/UAGaULXRlf8vkzFBLVm0zkMdCquhL5aOjhXPQ==}

  '@types/estree-jsx@1.0.5':
    resolution: {integrity: sha512-52CcUVNFyfb1A2ALocQw/Dd1BQFNmSdkuC3BkZ6iqhdMfQz7JWOFRuJFloOzjk+6WijU56m9oKXFAXc7o3Towg==}

  '@types/estree@1.0.7':
    resolution: {integrity: sha512-w28IoSUCJpidD/TGviZwwMJckNESJZXFu7NBZ5YJ4mEUnNraUn9Pm8HSZm/jDF1pDWYKspWE7oVphigUPRakIQ==}

  '@types/hast@2.3.10':
    resolution: {integrity: sha512-McWspRw8xx8J9HurkVBfYj0xKoE25tOFlHGdx4MJ5xORQrMGZNqJhVQWaIbm6Oyla5kYOXtDiopzKRJzEOkwJw==}

  '@types/hast@3.0.4':
    resolution: {integrity: sha512-WPs+bbQw5aCj+x6laNGWLH3wviHtoCv/P3+otBhbOhJgG8qtpdAMlTCxLtsTWA7LH1Oh/bFCHsBn0TPS5m30EQ==}

  '@types/jwt-decode@2.2.1':
    resolution: {integrity: sha512-aWw2YTtAdT7CskFyxEX2K21/zSDStuf/ikI3yBqmwpwJF0pS+/IX5DWv+1UFffZIbruP6cnT9/LAJV1gFwAT1A==}

  '@types/lodash.mergewith@4.6.7':
    resolution: {integrity: sha512-3m+lkO5CLRRYU0fhGRp7zbsGi6+BZj0uTVSwvcKU+nSlhjA9/QRNfuSGnD2mX6hQA7ZbmcCkzk5h4ZYGOtk14A==}

  '@types/lodash@4.17.16':
    resolution: {integrity: sha512-HX7Em5NYQAXKW+1T+FiuG27NGwzJfCX3s1GjOa7ujxZa52kjJLOr4FUxT+giF6Tgxv1e+/czV/iTtBw27WTU9g==}

  '@types/mdast@4.0.4':
    resolution: {integrity: sha512-kGaNbPh1k7AFzgpud/gMdvIm5xuECykRR+JnWKQno9TAXVa6WIVCGTPvYGekIDL4uwCZQSYbUxNBSb1aUo79oA==}

  '@types/ms@2.1.0':
    resolution: {integrity: sha512-GsCCIZDE/p3i96vtEqx+7dBUGXrc7zeSK3wwPHIaRThS+9OhWIXRqzs4d6k1SVU8g91DrNRWxWUGhp5KXQb2VA==}

  '@types/node@20.17.41':
    resolution: {integrity: sha512-bOB0a6u/e7Ey/Gyc+ghRg+xoXFGYug4I7pdvwxudh+Ewmk93Z4wTudn4NIKiIRYQyujf9jm2uTBzQK8tg8oUeQ==}

  '@types/parse-json@4.0.2':
    resolution: {integrity: sha512-dISoDXWWQwUquiKsyZ4Ng+HX2KsPL7LyHKHQwgGFEA3IaKac4Obd+h2a/a6waisAoepJlBcx9paWqjA8/HVjCw==}

  '@types/prop-types@15.7.14':
    resolution: {integrity: sha512-gNMvNH49DJ7OJYv+KAKn0Xp45p8PLl6zo2YnvDIbTd4J6MER2BmWN49TG7n9LvkyihINxeKW8+3bfS2yDC9dzQ==}

  '@types/react-dom@18.3.7':
    resolution: {integrity: sha512-MEe3UeoENYVFXzoXEWsvcpg6ZvlrFNlOQ7EOsvhI3CfAXwzPfO8Qwuxd40nepsYKqyyVQnTdEfv68q91yLcKrQ==}
    peerDependencies:
      '@types/react': ^18.0.0

  '@types/react@18.3.21':
    resolution: {integrity: sha512-gXLBtmlcRJeT09/sI4PxVwyrku6SaNUj/6cMubjE6T6XdY1fDmBL7r0nX0jbSZPU/Xr0KuwLLZh6aOYY5d91Xw==}

  '@types/unist@2.0.11':
    resolution: {integrity: sha512-CmBKiL6NNo/OqgmMn95Fk9Whlp2mtvIv+KNpQKN2F4SjvrEesubTRWGYSg+BnWZOnlCaSTU1sMpsBOzgbYhnsA==}

  '@types/unist@3.0.3':
    resolution: {integrity: sha512-ko/gIFJRv177XgZsZcBwnqJN5x/Gien8qNOn0D5bQU/zAzVf9Zt3BlcUiLqhV9y4ARk0GbT3tnUiPNgnTXzc/Q==}

  '@ungap/structured-clone@1.3.0':
    resolution: {integrity: sha512-WmoN8qaIAo7WTYWbAZuG8PYEhn5fkz7dZrqTBZ7dtt//lL2Gwms1IcnQ5yHqjDfX8Ft5j4YzDM23f87zBfDe9g==}

  '@zag-js/dom-query@0.16.0':
    resolution: {integrity: sha512-Oqhd6+biWyKnhKwFFuZrrf6lxBz2tX2pRQe6grUnYwO6HJ8BcbqZomy2lpOdr+3itlaUqx+Ywj5E5ZZDr/LBfQ==}

  '@zag-js/element-size@0.10.5':
    resolution: {integrity: sha512-uQre5IidULANvVkNOBQ1tfgwTQcGl4hliPSe69Fct1VfYb2Fd0jdAcGzqQgPhfrXFpR62MxLPB7erxJ/ngtL8w==}

  '@zag-js/focus-visible@0.16.0':
    resolution: {integrity: sha512-a7U/HSopvQbrDU4GLerpqiMcHKEkQkNPeDZJWz38cw/6Upunh41GjHetq5TB84hxyCaDzJ6q2nEdNoBQfC0FKA==}

  ansi-regex@5.0.1:
    resolution: {integrity: sha512-quJQXlTSUGL2LH9SUXo8VwsY4soanhgo6LNSm84E1LBcE8s3O0wpdiRzyR9z/ZZJMlMWv37qOOb9pdJlMUEKFQ==}
    engines: {node: '>=8'}

  ansi-regex@6.1.0:
    resolution: {integrity: sha512-7HSX4QQb4CspciLpVFwyRe79O3xsIZDDLER21kERQ71oaPodF8jL725AgJMFAYbooIqolJoRLuM81SpeUkpkvA==}
    engines: {node: '>=12'}

  ansi-styles@4.3.0:
    resolution: {integrity: sha512-zbB9rCJAT1rbjiVDb2hqKFHNYLxgtk8NURxZ3IZwD3F6NtxbXZQCnnSi1Lkx+IDohdPlFp222wVALIheZJQSEg==}
    engines: {node: '>=8'}

  ansi-styles@6.2.1:
    resolution: {integrity: sha512-bN798gFfQX+viw3R7yrGWRqnrN2oRkEkUjjl4JNn4E8GxxbjtG3FbrEIIY3l8/hrwUwIeCZvi4QuOTP4MErVug==}
    engines: {node: '>=12'}

  any-promise@1.3.0:
    resolution: {integrity: sha512-7UvmKalWRt1wgjL1RrGxoSJW/0QZFIegpeGvZG9kjp8vrRu55XTHbwnqq2GpXm9uLbcuhxm3IqX9OB4MZR1b2A==}

  anymatch@3.1.3:
    resolution: {integrity: sha512-KMReFUr0B4t+D+OBkjR3KYqvocp2XaSzO55UcB6mgQMd3KbcE+mWTyvVV7D/zsdEbNnV6acZUutkiHQXvTr1Rw==}
    engines: {node: '>= 8'}

  app-root-path@3.1.0:
    resolution: {integrity: sha512-biN3PwB2gUtjaYy/isrU3aNWI5w+fAfvHkSvCKeQGxhmYpwKFUxudR3Yya+KqVRHBmEDYh+/lTozYCFbmzX4nA==}
    engines: {node: '>= 6.0.0'}

  arg@5.0.2:
    resolution: {integrity: sha512-PYjyFOLKQ9y57JvQ6QLo8dAgNqswh8M1RMJYdQduT6xbWSgK36P/Z/v+p888pM69jMMfS8Xd8F6I1kQ/I9HUGg==}

  argparse@2.0.1:
    resolution: {integrity: sha512-8+9WqebbFzpX9OR+Wa6O29asIogeRMzcGtAINdpMHHyAg10f05aSFVBbcEqGf/PXw1EjAZ+q2/bEBg3DvurK3Q==}

  aria-hidden@1.2.4:
    resolution: {integrity: sha512-y+CcFFwelSXpLZk/7fMB2mUbGtX9lKycf1MWJ7CaTIERyitVlyQx6C+sxcROU2BAJ24OiZyK+8wj2i8AlBoS3A==}
    engines: {node: '>=10'}

  asynckit@0.4.0:
    resolution: {integrity: sha512-Oei9OH4tRh0YqU3GxhX79dM/mwVgvbZJaSNaRk+bshkj0S5cfHcgYakreBjrHwatXKbz+IoIdYLxrKim2MjW0Q==}

  autoprefixer@10.4.21:
    resolution: {integrity: sha512-O+A6LWV5LDHSJD3LjHYoNi4VLsj/Whi7k6zG12xTYaU4cQ8oxQGckXNX8cRHK5yOZ/ppVHe0ZBXGzSV9jXdVbQ==}
    engines: {node: ^10 || ^12 || >=14}
    hasBin: true
    peerDependencies:
      postcss: ^8.1.0

  axios@1.9.0:
    resolution: {integrity: sha512-re4CqKTJaURpzbLHtIi6XpDv20/CnpXOtjRY5/CU32L8gU8ek9UIivcfvSWvmKEngmVbrUtPpdDwWDWL7DNHvg==}

  babel-plugin-macros@3.1.0:
    resolution: {integrity: sha512-Cg7TFGpIr01vOQNODXOOaGz2NpCU5gl8x1qJFbb6hbZxR7XrcE2vtbAsTAbJ7/xwJtUuJEw8K8Zr/AE0LHlesg==}
    engines: {node: '>=10', npm: '>=6'}

  bail@2.0.2:
    resolution: {integrity: sha512-0xO6mYd7JB2YesxDKplafRpsiOzPt9V02ddPCLbY1xYGPOX24NTyN50qnUxgCPcSoYMhKpAuBTjQoRZCAkUDRw==}

  balanced-match@1.0.2:
    resolution: {integrity: sha512-3oSeUO0TMV67hN1AmbXsK4yaqU7tjiHlbxRDZOpH0KW9+CeX4bRAaX0Anxt0tx2MrpRpWwQaPwIlISEJhYU5Pw==}

  base64-js@1.5.1:
    resolution: {integrity: sha512-AKpaYlHn8t4SVbOHCy+b5+KKgvR4vrsD8vbvrbiQJps7fKDTkjkDry6ji0rUJjC0kzbNePLwzxq8iypo41qeWA==}

  binary-extensions@2.3.0:
    resolution: {integrity: sha512-Ceh+7ox5qe7LJuLHoY0feh3pHuUDHAcRUeyL2VYghZwfpkNIy/+8Ocg0a3UuSoYzavmylwuLWQOf3hl0jjMMIw==}
    engines: {node: '>=8'}

  bl@5.1.0:
    resolution: {integrity: sha512-tv1ZJHLfTDnXE6tMHv73YgSJaWR2AFuPwMntBe7XL/GBFHnT0CLnsHMogfk5+GzCDC5ZWarSCYaIGATZt9dNsQ==}

  brace-expansion@1.1.11:
    resolution: {integrity: sha512-iCuPHDFgrHX7H2vEI/5xpz07zSHB00TpugqhmYtVmMO6518mCuRMoOYFldEBl0g187ufozdaHgWKcYFb61qGiA==}

  brace-expansion@2.0.1:
    resolution: {integrity: sha512-XnAIvQ8eM+kC6aULx6wuQiwVsnzsi9d3WxzV3FpWTGA19F621kwdbsAcFKXgKUHZWsy+mY6iL1sHTxWEFCytDA==}

  braces@3.0.3:
    resolution: {integrity: sha512-yQbXgO/OSZVD2IsiLlro+7Hf6Q18EJrKSEsdoMzKePKXct3gvD8oLcOQdIzGupr5Fj+EDe8gO/lxc1BzfMpxvA==}
    engines: {node: '>=8'}

  browserslist@4.24.5:
    resolution: {integrity: sha512-FDToo4Wo82hIdgc1CQ+NQD0hEhmpPjrZ3hiUgwgOG6IuTdlpr8jdjyG24P6cNP1yJpTLzS5OcGgSw0xmDU1/Tw==}
    engines: {node: ^6 || ^7 || ^8 || ^9 || ^10 || ^11 || ^12 || >=13.7}
    hasBin: true

  buffer@6.0.3:
    resolution: {integrity: sha512-FTiCpNxtwiZZHEZbcbTIcZjERVICn9yq/pDFkTl95/AxzD1naBctN7YO68riM/gLSDY7sdrMby8hofADYuuqOA==}

  busboy@1.6.0:
    resolution: {integrity: sha512-8SFQbg/0hQ9xy3UNTB0YEnsNBbWfhf7RtnzpL7TkBiTBRfrQ9Fxcnz7VJsleJpyp6rVLvXiuORqjlHi5q+PYuA==}
    engines: {node: '>=10.16.0'}

  call-bind-apply-helpers@1.0.2:
    resolution: {integrity: sha512-Sp1ablJ0ivDkSzjcaJdxEunN5/XvksFJ2sMBFfq6x0ryhQV/2b/KwFe21cMpmHtPOSij8K99/wSfoEuTObmuMQ==}
    engines: {node: '>= 0.4'}

  callsites@3.1.0:
    resolution: {integrity: sha512-P8BjAsXvZS+VIDUI11hHCQEv74YT67YUi5JJFNWIqL235sBmjX4+qx9Muvls5ivyNENctx46xQLQ3aTuE7ssaQ==}
    engines: {node: '>=6'}

  camelcase-css@2.0.1:
    resolution: {integrity: sha512-QOSvevhslijgYwRx6Rv7zKdMF8lbRmx+uQGx2+vDc+KI/eBnsy9kit5aj23AgGu3pa4t9AgwbnXWqS+iOY+2aA==}
    engines: {node: '>= 6'}

  caniuse-lite@1.0.30001717:
    resolution: {integrity: sha512-auPpttCq6BDEG8ZAuHJIplGw6GODhjw+/11e7IjpnYCxZcW/ONgPs0KVBJ0d1bY3e2+7PRe5RCLyP+PfwVgkYw==}

  ccount@2.0.1:
    resolution: {integrity: sha512-eyrF0jiFpY+3drT6383f1qhkbGsLSifNAjA61IUjZjmLCWjItY6LB9ft9YhoDgwfmclB2zhu51Lc7+95b8NRAg==}

  chalk@4.1.2:
    resolution: {integrity: sha512-oKnbhFyRIXpUuez8iBMmyEa4nbj4IOQyuhc/wy9kY7/WVPcwIO9VA668Pu8RkO7+0G76SLROeyw9CpQ061i4mA==}
    engines: {node: '>=10'}

  chalk@5.2.0:
    resolution: {integrity: sha512-ree3Gqw/nazQAPuJJEy+avdl7QfZMcUvmHIKgEZkGL+xOBzRvup5Hxo6LHuMceSxOabuJLJm5Yp/92R9eMmMvA==}
    engines: {node: ^12.17.0 || ^14.13 || >=16.0.0}

  character-entities-html4@2.1.0:
    resolution: {integrity: sha512-1v7fgQRj6hnSwFpq1Eu0ynr/CDEw0rXo2B61qXrLNdHZmPKgb7fqS1a2JwF0rISo9q77jDI8VMEHoApn8qDoZA==}

  character-entities-legacy@1.1.4:
    resolution: {integrity: sha512-3Xnr+7ZFS1uxeiUDvV02wQ+QDbc55o97tIV5zHScSPJpcLm/r0DFPcoY3tYRp+VZukxuMeKgXYmsXQHO05zQeA==}

  character-entities-legacy@3.0.0:
    resolution: {integrity: sha512-RpPp0asT/6ufRm//AJVwpViZbGM/MkjQFxJccQRHmISF/22NBtsHqAWmL+/pmkPWoIUJdWyeVleTl1wydHATVQ==}

  character-entities@1.2.4:
    resolution: {integrity: sha512-iBMyeEHxfVnIakwOuDXpVkc54HijNgCyQB2w0VfGQThle6NXn50zU6V/u+LDhxHcDUPojn6Kpga3PTAD8W1bQw==}

  character-entities@2.0.2:
    resolution: {integrity: sha512-shx7oQ0Awen/BRIdkjkvz54PnEEI/EjwXDSIZp86/KKdbafHh1Df/RYGBhn4hbe2+uKC9FnT5UCEdyPz3ai9hQ==}

  character-reference-invalid@1.1.4:
    resolution: {integrity: sha512-mKKUkUbhPpQlCOfIuZkvSEgktjPFIsZKRRbC6KWVEMvlzblj3i3asQv5ODsrwt0N3pHAEvjP8KTQPHkp0+6jOg==}

  character-reference-invalid@2.0.1:
    resolution: {integrity: sha512-iBZ4F4wRbyORVsu0jPV7gXkOsGYjGHPmAyv+HiHG8gi5PtC9KI2j1+v8/tlibRvjoWX027ypmG/n0HtO5t7unw==}

  chokidar@3.6.0:
    resolution: {integrity: sha512-7VT13fmjotKpGipCW9JEQAusEPE+Ei8nl6/g4FBAmIm0GOOLMua9NDDo/DWp0ZAxCr3cPq5ZpBqmPAQgDda2Pw==}
    engines: {node: '>= 8.10.0'}

  class-variance-authority@0.7.1:
    resolution: {integrity: sha512-Ka+9Trutv7G8M6WT6SeiRWz792K5qEqIGEGzXKhAE6xOWAY6pPH8U+9IY3oCMv6kqTmLsv7Xh/2w2RigkePMsg==}

  classnames@2.5.1:
    resolution: {integrity: sha512-saHYOzhIQs6wy2sVxTM6bUDsQO4F50V9RQ22qBpEdCW+I+/Wmke2HOl6lS6dTpdxVhb88/I6+Hs+438c3lfUow==}

  cli-cursor@4.0.0:
    resolution: {integrity: sha512-VGtlMu3x/4DOtIUwEkRezxUZ2lBacNJCHash0N0WeZDBS+7Ux1dm3XWAgWYxLJFMMdOeXMHXorshEFhbMSGelg==}
    engines: {node: ^12.20.0 || ^14.13.1 || >=16.0.0}

  cli-highlight@2.1.11:
    resolution: {integrity: sha512-9KDcoEVwyUXrjcJNvHD0NFc/hiwe/WPVYIleQh2O1N2Zro5gWJZ/K+3DGn8w8P/F6FxOgzyC5bxDyHIgCSPhGg==}
    engines: {node: '>=8.0.0', npm: '>=5.0.0'}
    hasBin: true

  cli-spinners@2.9.2:
    resolution: {integrity: sha512-ywqV+5MmyL4E7ybXgKys4DugZbX0FC6LnwrhjuykIjnK9k8OQacQ7axGKnjDXWNhns0xot3bZI5h55H8yo9cJg==}
    engines: {node: '>=6'}

  client-only@0.0.1:
    resolution: {integrity: sha512-IV3Ou0jSMzZrd3pZ48nLkT9DA7Ag1pnPzaiQhpW7c3RbcqqzvzzVu+L8gfqMp/8IM2MQtSiqaCxrrcfu8I8rMA==}

  cliui@7.0.4:
    resolution: {integrity: sha512-OcRE68cOsVMXp1Yvonl/fzkQOyjLSu/8bhPDfQt0e0/Eb283TKP20Fs2MqoPsr9SwA595rRCA+QMzYc9nBP+JQ==}

  cliui@8.0.1:
    resolution: {integrity: sha512-BSeNnyus75C4//NQ9gQt1/csTXyo/8Sb+afLAkzAptFuMsod9HFokGNudZpi/oQV73hnVK+sR+5PVRMd+Dr7YQ==}
    engines: {node: '>=12'}

  clone@1.0.4:
    resolution: {integrity: sha512-JQHZ2QMW6l3aH/j6xCqQThY/9OH4D/9ls34cgkUBiEeocRTU04tHfKPBsUK1PqZCUQM7GiA0IIXJSuXHI64Kbg==}
    engines: {node: '>=0.8'}

  clsx@2.1.1:
    resolution: {integrity: sha512-eYm0QWBtUrBWZWG0d386OGAw16Z995PiOVo2B7bjWSbHedGl5e0ZWaq65kOGgUSNesEIDkB9ISbTg/JK9dhCZA==}
    engines: {node: '>=6'}

  cluster-key-slot@1.1.2:
    resolution: {integrity: sha512-RMr0FhtfXemyinomL4hrWcYJxmX6deFdCxpJzhDttxgO1+bcCnkk+9drydLVDmAMG7NE6aN/fl4F7ucU/90gAA==}
    engines: {node: '>=0.10.0'}

  color-convert@2.0.1:
    resolution: {integrity: sha512-RRECPsj7iu/xb5oKYcsFHSppFNnsj/52OVTRKb4zP5onXwVF3zVmmToNcOfGC+CRDpfK/U584fMg38ZHCaElKQ==}
    engines: {node: '>=7.0.0'}

  color-name@1.1.4:
    resolution: {integrity: sha512-dOy+3AuW3a2wNbZHIuMZpTcgjGuLU/uBL/ubcZF9OXbDo8ff4O8yVp5Bf0efS8uEoYo5q4Fx7dY9OgQGXgAsQA==}

  color-string@1.9.1:
    resolution: {integrity: sha512-shrVawQFojnZv6xM40anx4CkoDP+fZsw/ZerEMsW/pyzsRbElpsL/DBVW7q3ExxwusdNXI3lXpuhEZkzs8p5Eg==}

  color2k@2.0.3:
    resolution: {integrity: sha512-zW190nQTIoXcGCaU08DvVNFTmQhUpnJfVuAKfWqUQkflXKpaDdpaYoM0iluLS9lgJNHyBF58KKA2FBEwkD7wog==}

  color@4.2.3:
    resolution: {integrity: sha512-1rXeuUUiGGrykh+CeBdu5Ie7OJwinCgQY0bc7GCRxy5xVHy+moaqkpL/jqQq0MtQOeYcrqEz4abc5f0KtU7W4A==}
    engines: {node: '>=12.5.0'}

  combined-stream@1.0.8:
    resolution: {integrity: sha512-FQN4MRfuJeHf7cBbBMJFXhKSDq+2kAArBlmRBvcvFE5BB1HZKXtSFASDhdlz9zOYwxh8lDdnvmMOe/+5cdoEdg==}
    engines: {node: '>= 0.8'}

  comma-separated-tokens@1.0.8:
    resolution: {integrity: sha512-GHuDRO12Sypu2cV70d1dkA2EUmXHgntrzbpvOB+Qy+49ypNfGgFQIC2fhhXbnyrJRynDCAARsT7Ou0M6hirpfw==}

  comma-separated-tokens@2.0.3:
    resolution: {integrity: sha512-Fu4hJdvzeylCfQPp9SGWidpzrMs7tTrlu6Vb8XGaRGck8QSNZJJp538Wrb60Lax4fPwR64ViY468OIUTbRlGZg==}

  commander@10.0.1:
    resolution: {integrity: sha512-y4Mg2tXshplEbSGzx7amzPwKKOCGuoSRP/CjEdwwk0FOGlUbq6lKuoyDZTNZkmxHdJtp54hdfY/JUrdL7Xfdug==}
    engines: {node: '>=14'}

  commander@4.1.1:
    resolution: {integrity: sha512-NOKm8xhkzAjzFx8B2v5OAHT+u5pRQc2UCa2Vq9jYL/31o2wi9mxBA7LIFs3sV5VSC49z6pEhfbMULvShKj26WA==}
    engines: {node: '>= 6'}

  compute-scroll-into-view@3.0.3:
    resolution: {integrity: sha512-nadqwNxghAGTamwIqQSG433W6OADZx2vCo3UXHNrzTRHK/htu+7+L0zhjEoaeaQVNAi3YgqWDv8+tzf0hRfR+A==}

  concat-map@0.0.1:
    resolution: {integrity: sha512-/Srv4dswyQNBfohGpz9o6Yb3Gz3SrUDqBH5rTuhGR7ahtlbYKnVxw2bCFMRljaA7EXHaXZ8wsHdodFvbkhKmqg==}

  convert-source-map@1.9.0:
    resolution: {integrity: sha512-ASFBup0Mz1uyiIjANan1jzLQami9z1PoYSZCiiYW2FczPbenXc45FZdBZLzOT+r6+iciuEModtmCti+hjaAk0A==}

  cookie@0.7.2:
    resolution: {integrity: sha512-yki5XnKuf750l50uGTllt6kKILY4nQ1eNIQatoXEByZ5dWgnKqbnqmTrBE5B4N7lrMJKQ2ytWMiTO2o0v6Ew/w==}
    engines: {node: '>= 0.6'}

  copy-to-clipboard@3.3.3:
    resolution: {integrity: sha512-2KV8NhB5JqC3ky0r9PMCAZKbUHSwtEo4CwCs0KXgruG43gX5PMqDEBbVU4OUzw2MuAWUfsuFmWvEKG5QRfSnJA==}

  cosmiconfig@7.1.0:
    resolution: {integrity: sha512-AdmX6xUzdNASswsFtmwSt7Vj8po9IuqXm0UXz7QKPuEUmPB4XyjGfaAr2PSuELMwkRMVH1EpIkX5bTZGRB3eCA==}
    engines: {node: '>=10'}

  cross-spawn@7.0.6:
    resolution: {integrity: sha512-uV2QOWP2nWzsy2aMp8aRibhi9dlzF5Hgh5SHaB9OiTGEyDTiJJyx0uy51QXdyWbtAHNua4XJzUKca3OzKUd3vA==}
    engines: {node: '>= 8'}

  css-box-model@1.2.1:
    resolution: {integrity: sha512-a7Vr4Q/kd/aw96bnJG332W9V9LkJO69JRcaCYDUqjp6/z0w6VcZjgAcTbgFxEPfBgdnAwlh3iwu+hLopa+flJw==}

  cssesc@3.0.0:
    resolution: {integrity: sha512-/Tb/JcjK111nNScGob5MNtsntNM1aCNUDipB/TkwZFhyDrrE47SOx/18wF2bbjgc3ZzCSKW1T5nt5EbFoAz/Vg==}
    engines: {node: '>=4'}
    hasBin: true

  csstype@3.1.3:
    resolution: {integrity: sha512-M1uQkMl8rQK/szD0LNhtqxIPLpimGm8sOBwU7lLnCpSbTyY3yeU1Vc7l4KT5zT4s/yOxHH5O7tIuuLOCnLADRw==}

  data-uri-to-buffer@4.0.1:
    resolution: {integrity: sha512-0R9ikRb668HB7QDxT1vkpuUBtqc53YyAwMwGeUFKRojY/NWKvdZ+9UYtRfGmhqNbRkTSVpMbmyhXipFFv2cb/A==}
    engines: {node: '>= 12'}

  date-fns@2.30.0:
    resolution: {integrity: sha512-fnULvOpxnC5/Vg3NCiWelDsLiUc9bRwAPs/+LfTLNvetFCtCTN+yQz15C/fs4AwX1R9K5GLtLfn8QW+dWisaAw==}
    engines: {node: '>=0.11'}

  debug@4.4.0:
    resolution: {integrity: sha512-6WTZ/IxCY/T6BALoZHaE4ctp9xm+Z5kY/pzYaCHRFeyVhojxlrm+46y68HA6hr0TcwEssoxNiDEUJQjfPZ/RYA==}
    engines: {node: '>=6.0'}
    peerDependencies:
      supports-color: '*'
    peerDependenciesMeta:
      supports-color:
        optional: true

  decode-named-character-reference@1.1.0:
    resolution: {integrity: sha512-Wy+JTSbFThEOXQIR2L6mxJvEs+veIzpmqD7ynWxMXGpnk3smkHQOp6forLdHsKpAMW9iJpaBBIxz285t1n1C3w==}

  defaults@1.0.4:
    resolution: {integrity: sha512-eFuaLoy/Rxalv2kr+lqMlUnrDWV+3j4pljOIJgLIhI058IQfWJ7vXhyEIHu+HtC738klGALYxOKDO0bQP3tg8A==}

  delayed-stream@1.0.0:
    resolution: {integrity: sha512-ZySD7Nf91aLB0RxL4KGrKHBXl7Eds1DAmEdcoVawXnLD7SDhpNgtuII2aAkg7a7QS41jxPSZ17p4VdGnMHk3MQ==}
    engines: {node: '>=0.4.0'}

  denque@2.1.0:
    resolution: {integrity: sha512-HVQE3AAb/pxF8fQAoiqpvg9i3evqug3hoiwakOyZAwJm+6vZehbkYXZ0l4JxS+I3QxM97v5aaRNhj8v5oBhekw==}
    engines: {node: '>=0.10'}

  dequal@2.0.3:
    resolution: {integrity: sha512-0je+qPKHEMohvfRTCEo3CrPG6cAzAYgmzKyxRiYSSDkS6eGJdyVJm7WaYA5ECaAD9wLB2T4EEeymA5aFVcYXCA==}
    engines: {node: '>=6'}

  detect-libc@2.0.4:
    resolution: {integrity: sha512-3UDv+G9CsCKO1WKMGw9fwq/SWJYbI0c5Y7LU1AXYoDdbhE2AHQ6N6Nb34sG8Fj7T5APy8qXDCKuuIHd1BR0tVA==}
    engines: {node: '>=8'}

  detect-node-es@1.1.0:
    resolution: {integrity: sha512-ypdmJU/TbBby2Dxibuv7ZLW3Bs1QEmM7nHjEANfohJLvE0XVujisn1qPJcZxg+qDucsr+bP6fLD1rPS3AhJ7EQ==}

  devlop@1.1.0:
    resolution: {integrity: sha512-RWmIqhcFf1lRYBvNmr7qTNuyCt/7/ns2jbpp1+PalgE/rDQcBT0fioSMUpJ93irlUhC5hrg4cYqe6U+0ImW0rA==}

  didyoumean@1.2.2:
    resolution: {integrity: sha512-gxtyfqMg7GKyhQmb056K7M3xszy/myH8w+B4RT+QXBQsvAOdc3XymqDDPHx1BgPgsdAA5SIifona89YtRATDzw==}

  dlv@1.1.3:
    resolution: {integrity: sha512-+HlytyjlPKnIG8XuRG8WvmBP8xs8P71y+SKKS6ZXWoEgLuePxtDoUEiH7WkdePWrQ5JBpE6aoVqfZfJUQkjXwA==}

  dotenv@16.5.0:
    resolution: {integrity: sha512-m/C+AwOAr9/W1UOIZUo232ejMNnJAJtYQjUbHoNTBNTJSvqzzDh7vnrei3o3r3m9blf6ZoDkvcw0VmozNRFJxg==}
    engines: {node: '>=12'}

  dunder-proto@1.0.1:
    resolution: {integrity: sha512-KIN/nDJBQRcXw0MLVhZE9iQHmG68qAVIBg9CqmUYjmQIhgij9U5MFvrqkUL5FbtyyzZuOeOt0zdeRe4UY7ct+A==}
    engines: {node: '>= 0.4'}

  eastasianwidth@0.2.0:
    resolution: {integrity: sha512-I88TYZWc9XiYHRQ4/3c5rjjfgkjhLyW2luGIheGERbNQ6OY7yTybanSpDXZa8y7VUP9YmDcYa+eyq4ca7iLqWA==}

  electron-to-chromium@1.5.150:
    resolution: {integrity: sha512-rOOkP2ZUMx1yL4fCxXQKDHQ8ZXwisb2OycOQVKHgvB3ZI4CvehOd4y2tfnnLDieJ3Zs1RL1Dlp3cMkyIn7nnXA==}

  emoji-regex@8.0.0:
    resolution: {integrity: sha512-MSjYzcWNOA0ewAHpz0MxpYFvwg6yjy1NG3xteoqz644VCo/RPgnr1/GGt+ic3iJTzQ8Eu3TdM14SawnVUmGE6A==}

  emoji-regex@9.2.2:
    resolution: {integrity: sha512-L18DaJsXSUk2+42pv8mLs5jJT2hqFkFE4j21wOmgbUqsZ2hL72NsUU785g9RXgo3s0ZNgVl42TiHp3ZtOv/Vyg==}

  entities@6.0.0:
    resolution: {integrity: sha512-aKstq2TDOndCn4diEyp9Uq/Flu2i1GlLkc6XIDQSDMuaFE3OPW5OphLCyQ5SpSJZTb4reN+kTcYru5yIfXoRPw==}
    engines: {node: '>=0.12'}

  error-ex@1.3.2:
    resolution: {integrity: sha512-7dFHNmqeFSEt2ZBsCriorKnn3Z2pj+fd9kmI6QoWw4//DL+icEBfc0U7qJCisqrTsKTjw4fNFy2pW9OqStD84g==}

  es-define-property@1.0.1:
    resolution: {integrity: sha512-e3nRfgfUZ4rNGL232gUgX06QNyyez04KdjFrF+LTRoOXmrOgFKDg4BCdsjW8EnT69eqdYGmRpJwiPVYNrCaW3g==}
    engines: {node: '>= 0.4'}

  es-errors@1.3.0:
    resolution: {integrity: sha512-Zf5H2Kxt2xjTvbJvP2ZWLEICxA6j+hAmMzIlypy4xcBg1vKVnx89Wy0GbS+kf5cwCVFFzdCFh2XSCFNULS6csw==}
    engines: {node: '>= 0.4'}

  es-object-atoms@1.1.1:
    resolution: {integrity: sha512-FGgH2h8zKNim9ljj7dankFPcICIK9Cp5bm+c2gQSYePhpaG5+esrLODihIorn+Pe6FGJzWhXQotPv73jTaldXA==}
    engines: {node: '>= 0.4'}

  es-set-tostringtag@2.1.0:
    resolution: {integrity: sha512-j6vWzfrGVfyXxge+O0x5sh6cvxAog0a/4Rdd2K36zCMV5eJ+/+tOAngRO8cODMNWbVRdVlmGZQL2YS3yR8bIUA==}
    engines: {node: '>= 0.4'}

  escalade@3.2.0:
    resolution: {integrity: sha512-WUj2qlxaQtO4g6Pq5c29GTcWGDyd8itL8zTlipgECz3JesAiiOKotd8JU6otB3PACgG6xkJUyVhboMS+bje/jA==}
    engines: {node: '>=6'}

  escape-string-regexp@4.0.0:
    resolution: {integrity: sha512-TtpcNJ3XAzx3Gq8sWRzJaVajRs0uVxA2YAkdb1jm2YkPz4G6egUFAyA3n5vtEIZefPk5Wa4UXbKuS5fKkJWdgA==}
    engines: {node: '>=10'}

  escape-string-regexp@5.0.0:
    resolution: {integrity: sha512-/veY75JbMK4j1yjvuUxuVsiS/hr/4iHs9FTT6cgTexxdE0Ly/glccBAkloH/DofkjRbZU3bnoj38mOmhkZ0lHw==}
    engines: {node: '>=12'}

  estree-util-is-identifier-name@3.0.0:
    resolution: {integrity: sha512-hFtqIDZTIUZ9BXLb8y4pYGyk6+wekIivNVTcmvk8NoOh+VeRn5y6cEHzbURrWbfp1fIqdVipilzj+lfaadNZmg==}

  execa@7.2.0:
    resolution: {integrity: sha512-UduyVP7TLB5IcAQl+OzLyLcS/l32W/GLg+AhHJ+ow40FOk2U3SAllPwR44v4vmdFwIWqpdwxxpQbF1n5ta9seA==}
    engines: {node: ^14.18.0 || ^16.14.0 || >=18.0.0}

  extend@3.0.2:
    resolution: {integrity: sha512-fjquC59cD7CyW6urNXK0FBufkZcoiGG80wTuPujX590cB5Ttln20E2UB4S/WARVqhXffZl2LNgS+gQdPIIim/g==}

  fast-glob@3.3.3:
    resolution: {integrity: sha512-7MptL8U0cqcFdzIzwOTHoilX9x5BrNqye7Z/LuC7kCMRio1EMSyqRK3BEAUD7sXRq4iT4AzTVuZdhgQ2TCvYLg==}
    engines: {node: '>=8.6.0'}

  fastq@1.19.1:
    resolution: {integrity: sha512-GwLTyxkCXjXbxqIhTsMI2Nui8huMPtnxg7krajPJAjnEG/iiOS7i+zCtWGZR9G0NBKbXKh6X9m9UIsYX/N6vvQ==}

  fault@1.0.4:
    resolution: {integrity: sha512-CJ0HCB5tL5fYTEA7ToAq5+kTwd++Borf1/bifxd9iT70QcXr4MRrO3Llf8Ifs70q+SJcGHFtnIE/Nw6giCtECA==}

  fetch-blob@3.2.0:
    resolution: {integrity: sha512-7yAQpD2UMJzLi1Dqv7qFYnPbaPx7ZfFK6PiIxQ4PfkGPyNyl2Ugx+a/umUonmKqjhM4DnfbMvdX6otXq83soQQ==}
    engines: {node: ^12.20 || >= 14.13}

  fill-range@7.1.1:
    resolution: {integrity: sha512-YsGpe3WHLK8ZYi4tWDg2Jy3ebRz2rXowDxnld4bkQB00cc/1Zw9AWnC0i9ztDJitivtQvaI9KaLyKrc+hBW0yg==}
    engines: {node: '>=8'}

  find-root@1.1.0:
    resolution: {integrity: sha512-NKfW6bec6GfKc0SGx1e07QZY9PE99u0Bft/0rzSD5k3sO/vwkVUpDUKVm5Gpp5Ue3YfShPFTX2070tDs5kB9Ng==}

  focus-lock@1.3.6:
    resolution: {integrity: sha512-Ik/6OCk9RQQ0T5Xw+hKNLWrjSMtv51dD4GRmJjbD5a58TIEpI5a5iXagKVl3Z5UuyslMCA8Xwnu76jQob62Yhg==}
    engines: {node: '>=10'}

  follow-redirects@1.15.9:
    resolution: {integrity: sha512-gew4GsXizNgdoRyqmyfMHyAmXsZDk6mHkSxZFCzW9gwlbtOW44CDtYavM+y+72qD/Vq2l550kMF52DT8fOLJqQ==}
    engines: {node: '>=4.0'}
    peerDependencies:
      debug: '*'
    peerDependenciesMeta:
      debug:
        optional: true

  foreground-child@3.3.1:
    resolution: {integrity: sha512-gIXjKqtFuWEgzFRJA9WCQeSJLZDjgJUOMCMzxtvFq/37KojM1BFGufqsCy0r4qSQmYLsZYMeyRqzIWOMup03sw==}
    engines: {node: '>=14'}

  form-data@4.0.2:
    resolution: {integrity: sha512-hGfm/slu0ZabnNt4oaRZ6uREyfCj6P4fT/n6A1rGV+Z0VdGXjfOhVUpkn6qVQONHGIFwmveGXyDs75+nr6FM8w==}
    engines: {node: '>= 6'}

  format@0.2.2:
    resolution: {integrity: sha512-wzsgA6WOq+09wrU1tsJ09udeR/YZRaeArL9e1wPbFg3GG2yDnC2ldKpxs4xunpFF9DgqCqOIra3bc1HWrJ37Ww==}
    engines: {node: '>=0.4.x'}

  formdata-polyfill@4.0.10:
    resolution: {integrity: sha512-buewHzMvYL29jdeQTVILecSaZKnt/RJWjoZCF5OW60Z67/GmSLBkOFM7qh1PI3zFNtJbaZL5eQu1vLfazOwj4g==}
    engines: {node: '>=12.20.0'}

  fraction.js@4.3.7:
    resolution: {integrity: sha512-ZsDfxO51wGAXREY55a7la9LScWpwv9RxIrYABrlvOFBlH/ShPnrtsXeuUIfXKKOVicNxQ+o8JTbJvjS4M89yew==}

  framer-motion@7.6.8:
    resolution: {integrity: sha512-8yaqF3a47nt4sKgt3TqpxTPY0Ed8mzLQHagdkZ/TOd4VjDbCsc0Ooand+AKdgnCVSimiqgOg1HptS2ILutgkCQ==}
    peerDependencies:
      react: ^18.0.0
      react-dom: ^18.0.0

  framesync@6.1.2:
    resolution: {integrity: sha512-jBTqhX6KaQVDyus8muwZbBeGGP0XgujBRbQ7gM7BRdS3CadCZIHiawyzYLnafYcvZIh5j8WE7cxZKFn7dXhu9g==}

  fs-extra@11.3.0:
    resolution: {integrity: sha512-Z4XaCL6dUDHfP/jT25jJKMmtxvuwbkrD1vNSMFlo9lNLY2c5FHYSQgHPRZUjAB26TpDEoW9HCOgplrdbaPV/ew==}
    engines: {node: '>=14.14'}

  fs.realpath@1.0.0:
    resolution: {integrity: sha512-OO0pH2lK6a0hZnAdau5ItzHPI6pUlvI7jMVnxUQRtw4owF2wk8lOSabtGDCTP4Ggrg2MbGnWO9X8K1t4+fGMDw==}

  fsevents@2.3.3:
    resolution: {integrity: sha512-5xoDfX+fL7faATnagmWPpbFtwh/R77WmMMqqHGS65C3vvB0YHrgF+B1YmZ3441tMj5n63k0212XNoJwzlhffQw==}
    engines: {node: ^8.16.0 || ^10.6.0 || >=11.0.0}
    os: [darwin]

  function-bind@1.1.2:
    resolution: {integrity: sha512-7XHNxH7qX9xG5mIwxkhumTox/MIRNcOgDrxWsMt2pAr23WHp6MrRlN7FBSFpCpr+oVO0F744iUgR82nJMfG2SA==}

  get-caller-file@2.0.5:
    resolution: {integrity: sha512-DyFP3BM/3YHTQOCUL/w0OZHR0lpKeGrxotcHWcqNEdnltqFwXVfhEBQ94eIo34AfQpo0rGki4cyIiftY06h2Fg==}
    engines: {node: 6.* || 8.* || >= 10.*}

  get-intrinsic@1.3.0:
    resolution: {integrity: sha512-9fSjSaos/fRIVIp+xSJlE6lfwhES7LNtKaCBIamHsjr2na1BiABJPo0mOjjz8GJDURarmCPGqaiVg5mfjb98CQ==}
    engines: {node: '>= 0.4'}

  get-nonce@1.0.1:
    resolution: {integrity: sha512-FJhYRoDaiatfEkUK8HKlicmu/3SGFD51q3itKDGoSTysQJBnfOcxU5GxnhE1E6soB76MbT0MBtnKJuXyAx+96Q==}
    engines: {node: '>=6'}

  get-proto@1.0.1:
    resolution: {integrity: sha512-sTSfBjoXBp89JvIKIefqw7U2CCebsc74kiY6awiGogKtoSGbgjYE/G/+l9sF3MWFPNc9IcoOC4ODfKHfxFmp0g==}
    engines: {node: '>= 0.4'}

  get-stream@6.0.1:
    resolution: {integrity: sha512-ts6Wi+2j3jQjqi70w5AlN8DFnkSwC+MqmxEzdEALB2qXZYV3X/b1CTfgPLGJNMeAWxdPfU8FO1ms3NUfaHCPYg==}
    engines: {node: '>=10'}

  glob-parent@5.1.2:
    resolution: {integrity: sha512-AOIgSQCepiJYwP3ARnGx+5VnTu2HBYdzbGP45eLw1vr3zB3vZLeyed1sC9hnbcOc9/SrMyM5RPQrkGz4aS9Zow==}
    engines: {node: '>= 6'}

  glob-parent@6.0.2:
    resolution: {integrity: sha512-XxwI8EOhVQgWp6iDL+3b0r86f4d6AX6zSU55HfB4ydCEuXLXc5FcYeOu+nnGftS4TEju/11rt4KJPTMgbfmv4A==}
    engines: {node: '>=10.13.0'}

  glob@10.4.5:
    resolution: {integrity: sha512-7Bv8RF0k6xjo7d4A/PxYLbUCfb6c+Vpd2/mB2yRDlew7Jb5hEXiCD9ibfO7wpk8i4sevK6DFny9h7EYbM3/sHg==}
    hasBin: true

  glob@7.2.3:
    resolution: {integrity: sha512-nFR0zLpU2YCaRxwoCJvL6UvCH2JFyFVIvwTLsIf21AuHlMskA1hhTdk+LlYJtOlYt9v6dvszD2BGRqBL+iQK9Q==}
    deprecated: Glob versions prior to v9 are no longer supported

  globals@11.12.0:
    resolution: {integrity: sha512-WOBp/EEGUiIsJSp7wcv/y6MO+lV9UoncWqxuFfm8eBwzWNgyfBd6Gz+IeKQ9jCmyhoH99g15M3T+QaVHFjizVA==}
    engines: {node: '>=4'}

  gopd@1.2.0:
    resolution: {integrity: sha512-ZUKRh6/kUFoAiTAtTYPZJ3hw9wNxx+BIBOijnlG9PnrJsCcSjs1wyyD6vJpaYtgnzDrKYRSqf3OO6Rfa93xsRg==}
    engines: {node: '>= 0.4'}

  graceful-fs@4.2.11:
    resolution: {integrity: sha512-RbJ5/jmFcNNCcDV5o9eTnBLJ/HszWV0P73bc+Ff4nS/rJj+YaS6IGyiOL0VoBYX+l1Wrl3k63h/KrH+nhJ0XvQ==}

  has-flag@4.0.0:
    resolution: {integrity: sha512-EykJT/Q1KjTWctppgIAgfSO0tKVuZUjhgMr17kqTumMl6Afv3EISleU7qZUzoXDFTAHTDC4NOoG/ZxU3EvlMPQ==}
    engines: {node: '>=8'}

  has-symbols@1.1.0:
    resolution: {integrity: sha512-1cDNdwJ2Jaohmb3sg4OmKaMBwuC48sYni5HUw2DvsC8LjGTLK9h+eb1X6RyuOHe4hT0ULCW68iomhjUoKUqlPQ==}
    engines: {node: '>= 0.4'}

  has-tostringtag@1.0.2:
    resolution: {integrity: sha512-NqADB8VjPFLM2V0VvHUewwwsw0ZWBaIdgo+ieHtK3hasLz4qeCRjYcqfB6AQrBggRKppKF8L52/VqdVsO47Dlw==}
    engines: {node: '>= 0.4'}

  hasown@2.0.2:
    resolution: {integrity: sha512-0hJU9SCPvmMzIBdZFqNPXWa6dqh7WdH0cII9y+CyS8rG3nL48Bclra9HmKhVVUHyPWNH5Y7xDwAB7bfgSjkUMQ==}
    engines: {node: '>= 0.4'}

  hast-util-from-parse5@8.0.3:
    resolution: {integrity: sha512-3kxEVkEKt0zvcZ3hCRYI8rqrgwtlIOFMWkbclACvjlDw8Li9S2hk/d51OI0nr/gIpdMHNepwgOKqZ/sy0Clpyg==}

  hast-util-is-element@3.0.0:
    resolution: {integrity: sha512-Val9mnv2IWpLbNPqc/pUem+a7Ipj2aHacCwgNfTiK0vJKl0LF+4Ba4+v1oPHFpf3bLYmreq0/l3Gud9S5OH42g==}

  hast-util-parse-selector@2.2.5:
    resolution: {integrity: sha512-7j6mrk/qqkSehsM92wQjdIgWM2/BW61u/53G6xmC8i1OmEdKLHbk419QKQUjz6LglWsfqoiHmyMRkP1BGjecNQ==}

  hast-util-parse-selector@4.0.0:
    resolution: {integrity: sha512-wkQCkSYoOGCRKERFWcxMVMOcYE2K1AaNLU8DXS9arxnLOUEWbOXKXiJUNzEpqZ3JOKpnha3jkFrumEjVliDe7A==}

  hast-util-raw@9.1.0:
    resolution: {integrity: sha512-Y8/SBAHkZGoNkpzqqfCldijcuUKh7/su31kEBp67cFY09Wy0mTRgtsLYsiIxMJxlu0f6AA5SUTbDR8K0rxnbUw==}

  hast-util-sanitize@5.0.2:
    resolution: {integrity: sha512-3yTWghByc50aGS7JlGhk61SPenfE/p1oaFeNwkOOyrscaOkMGrcW9+Cy/QAIOBpZxP1yqDIzFMR0+Np0i0+usg==}

  hast-util-to-jsx-runtime@2.3.6:
    resolution: {integrity: sha512-zl6s8LwNyo1P9uw+XJGvZtdFF1GdAkOg8ujOw+4Pyb76874fLps4ueHXDhXWdk6YHQ6OgUtinliG7RsYvCbbBg==}

  hast-util-to-parse5@8.0.0:
    resolution: {integrity: sha512-3KKrV5ZVI8if87DVSi1vDeByYrkGzg4mEfeu4alwgmmIeARiBLKCZS2uw5Gb6nU9x9Yufyj3iudm6i7nl52PFw==}

  hast-util-to-text@4.0.2:
    resolution: {integrity: sha512-KK6y/BN8lbaq654j7JgBydev7wuNMcID54lkRav1P0CaE1e47P72AWWPiGKXTJU271ooYzcvTAn/Zt0REnvc7A==}

  hast-util-whitespace@3.0.0:
    resolution: {integrity: sha512-88JUN06ipLwsnv+dVn+OIYOvAuvBMy/Qoi6O7mQHxdPXpjy+Cd6xRkWwux7DKO+4sYILtLBRIKgsdpS2gQc7qw==}

  hastscript@6.0.0:
    resolution: {integrity: sha512-nDM6bvd7lIqDUiYEiu5Sl/+6ReP0BMk/2f4U/Rooccxkj0P5nm+acM5PrGJ/t5I8qPGiqZSE6hVAwZEdZIvP4w==}

  hastscript@9.0.1:
    resolution: {integrity: sha512-g7df9rMFX/SPi34tyGCyUBREQoKkapwdY/T04Qn9TDWfHhAYt4/I0gMVirzK5wEzeUqIjEB+LXC/ypb7Aqno5w==}

  hey-listen@1.0.8:
    resolution: {integrity: sha512-COpmrF2NOg4TBWUJ5UVyaCU2A88wEMkUPK4hNqyCkqHbxT92BbvfjoSozkAIIm6XhicGlJHhFdullInrdhwU8Q==}

  highlight.js@10.7.3:
    resolution: {integrity: sha512-tzcUFauisWKNHaRkN4Wjl/ZA07gENAjFl3J/c480dprkGTg5EQstgaNFqBfUqCq54kZRIEcreTsAgF/m2quD7A==}

  highlight.js@11.11.1:
    resolution: {integrity: sha512-Xwwo44whKBVCYoliBQwaPvtd/2tYFkRQtXDWj1nackaV2JPXx3L0+Jvd8/qCJ2p+ML0/XVkJ2q+Mr+UVdpJK5w==}
    engines: {node: '>=12.0.0'}

  highlightjs-vue@1.0.0:
    resolution: {integrity: sha512-PDEfEF102G23vHmPhLyPboFCD+BkMGu+GuJe2d9/eH4FsCwvgBpnc9n0pGE+ffKdph38s6foEZiEjdgHdzp+IA==}

  hoist-non-react-statics@3.3.2:
    resolution: {integrity: sha512-/gGivxi8JPKWNm/W0jSmzcMPpfpPLc3dY/6GxhX2hQ9iGj3aDfklV4ET7NjKpSinLpJ5vafa9iiGIEZg10SfBw==}

  html-url-attributes@3.0.1:
    resolution: {integrity: sha512-ol6UPyBWqsrO6EJySPz2O7ZSr856WDrEzM5zMqp+FJJLGMW35cLYmmZnl0vztAZxRUoNZJFTCohfjuIJ8I4QBQ==}

  html-void-elements@3.0.0:
    resolution: {integrity: sha512-bEqo66MRXsUGxWHV5IP0PUiAWwoEjba4VCzg0LjFJBpchPaTfyfCKTG6bc5F8ucKec3q5y6qOdGyYTSBEvhCrg==}

  human-signals@4.3.1:
    resolution: {integrity: sha512-nZXjEF2nbo7lIw3mgYjItAfgQXog3OjJogSbKa2CQIIvSGWcKgeJnQlNXip6NglNzYH45nSRiEVimMvYL8DDqQ==}
    engines: {node: '>=14.18.0'}

  ieee754@1.2.1:
    resolution: {integrity: sha512-dcyqhDvX1C46lXZcVqCpK+FtMRQVdIMN6/Df5js2zouUsqG7I6sFxitIC+7KYK29KdXOLHdu9zL4sFnoVQnqaA==}

  import-fresh@3.3.1:
    resolution: {integrity: sha512-TR3KfrTZTYLPB6jUjfx6MF9WcWrHL9su5TObK4ZkYgBdWKPOFoSoQIdEuTuR82pmtxH2spWG9h6etwfr1pLBqQ==}
    engines: {node: '>=6'}

  inflight@1.0.6:
    resolution: {integrity: sha512-k92I/b08q4wvFscXCLvqfsHCrjrF7yiXsQuIVvVE7N82W3+aqpzuUdBbfhWcy/FZR3/4IgflMgKLOsvPDrGCJA==}
    deprecated: This module is not supported, and leaks memory. Do not use it. Check out lru-cache if you want a good and tested way to coalesce async requests by a key value, which is much more comprehensive and powerful.

  inherits@2.0.4:
    resolution: {integrity: sha512-k/vGaX4/Yla3WzyMCvTQOXYeIHvqOKtnqBduzTHpzpQZzAskKMhZ2K+EnBiSM9zGSoIFeMpXKxa4dYeZIQqewQ==}

  inline-style-parser@0.2.4:
    resolution: {integrity: sha512-0aO8FkhNZlj/ZIbNi7Lxxr12obT7cL1moPfE4tg1LkX7LlLfC6DeX4l2ZEud1ukP9jNQyNnfzQVqwbwmAATY4Q==}

  ioredis@5.6.1:
    resolution: {integrity: sha512-UxC0Yv1Y4WRJiGQxQkP0hfdL0/5/6YvdfOOClRgJ0qppSarkhneSa6UvkMkms0AkdGimSH3Ikqm+6mkMmX7vGA==}
    engines: {node: '>=12.22.0'}

  is-alphabetical@1.0.4:
    resolution: {integrity: sha512-DwzsA04LQ10FHTZuL0/grVDk4rFoVH1pjAToYwBrHSxcrBIGQuXrQMtD5U1b0U2XVgKZCTLLP8u2Qxqhy3l2Vg==}

  is-alphabetical@2.0.1:
    resolution: {integrity: sha512-FWyyY60MeTNyeSRpkM2Iry0G9hpr7/9kD40mD/cGQEuilcZYS4okz8SN2Q6rLCJ8gbCt6fN+rC+6tMGS99LaxQ==}

  is-alphanumerical@1.0.4:
    resolution: {integrity: sha512-UzoZUr+XfVz3t3v4KyGEniVL9BDRoQtY7tOyrRybkVNjDFWyo1yhXNGrrBTQxp3ib9BLAWs7k2YKBQsFRkZG9A==}

  is-alphanumerical@2.0.1:
    resolution: {integrity: sha512-hmbYhX/9MUMF5uh7tOXyK/n0ZvWpad5caBA17GsC6vyuCqaWliRG5K1qS9inmUhEMaOBIW7/whAnSwveW/LtZw==}

  is-arrayish@0.2.1:
    resolution: {integrity: sha512-zz06S8t0ozoDXMG+ube26zeCTNXcKIPJZJi8hBrF4idCLms4CG9QtK7qBl1boi5ODzFpjswb5JPmHCbMpjaYzg==}

  is-arrayish@0.3.2:
    resolution: {integrity: sha512-eVRqCvVlZbuw3GrM63ovNSNAeA1K16kaR/LRY/92w0zxQ5/1YzwblUX652i4Xs9RwAGjW9d9y6X88t8OaAJfWQ==}

  is-binary-path@2.1.0:
    resolution: {integrity: sha512-ZMERYes6pDydyuGidse7OsHxtbI7WVeUEozgR/g7rd0xUimYNlvZRE/K2MgZTjWy725IfelLeVcEM97mmtRGXw==}
    engines: {node: '>=8'}

  is-core-module@2.16.1:
    resolution: {integrity: sha512-UfoeMA6fIJ8wTYFEUjelnaGI67v6+N7qXJEvQuIGa99l4xsCruSYOVSQ0uPANn4dAzm8lkYPaKLrrijLq7x23w==}
    engines: {node: '>= 0.4'}

  is-decimal@1.0.4:
    resolution: {integrity: sha512-RGdriMmQQvZ2aqaQq3awNA6dCGtKpiDFcOzrTWrDAT2MiWrKQVPmxLGHl7Y2nNu6led0kEyoX0enY0qXYsv9zw==}

  is-decimal@2.0.1:
    resolution: {integrity: sha512-AAB9hiomQs5DXWcRB1rqsxGUstbRroFOPPVAomNk/3XHR5JyEZChOyTWe2oayKnsSsr/kcGqF+z6yuH6HHpN0A==}

  is-extglob@2.1.1:
    resolution: {integrity: sha512-SbKbANkN603Vi4jEZv49LeVJMn4yGwsbzZworEoyEiutsN3nJYdbO36zfhGJ6QEDpOZIFkDtnq5JRxmvl3jsoQ==}
    engines: {node: '>=0.10.0'}

  is-fullwidth-code-point@3.0.0:
    resolution: {integrity: sha512-zymm5+u+sCsSWyD9qNaejV3DFvhCKclKdizYaJUuHA83RLjb7nSuGnddCHGv0hk+KY7BMAlsWeK4Ueg6EV6XQg==}
    engines: {node: '>=8'}

  is-glob@4.0.3:
    resolution: {integrity: sha512-xelSayHH36ZgE7ZWhli7pW34hNbNl8Ojv5KVmkJD4hBdD3th8Tfk9vYasLM+mXWOZhFkgZfxhLSnrwRr4elSSg==}
    engines: {node: '>=0.10.0'}

  is-hexadecimal@1.0.4:
    resolution: {integrity: sha512-gyPJuv83bHMpocVYoqof5VDiZveEoGoFL8m3BXNb2VW8Xs+rz9kqO8LOQ5DH6EsuvilT1ApazU0pyl+ytbPtlw==}

  is-hexadecimal@2.0.1:
    resolution: {integrity: sha512-DgZQp241c8oO6cA1SbTEWiXeoxV42vlcJxgH+B3hi1AiqqKruZR3ZGF8In3fj4+/y/7rHvlOZLZtgJ/4ttYGZg==}

  is-interactive@2.0.0:
    resolution: {integrity: sha512-qP1vozQRI+BMOPcjFzrjXuQvdak2pHNUMZoeG2eRbiSqyvbEf/wQtEOTOX1guk6E3t36RkaqiSt8A/6YElNxLQ==}
    engines: {node: '>=12'}

  is-number@7.0.0:
    resolution: {integrity: sha512-41Cifkg6e8TylSpdtTpeLVMqvSBEVzTttHvERD741+pnZ8ANv0004MRL43QKPDlK9cGvNp6NZWZUBlbGXYxxng==}
    engines: {node: '>=0.12.0'}

  is-plain-obj@4.1.0:
    resolution: {integrity: sha512-+Pgi+vMuUNkJyExiMBt5IlFoMyKnr5zhJ4Uspz58WOhBF5QoIZkFyNHIbBAtHwzVAgk5RtndVNsDRN61/mmDqg==}
    engines: {node: '>=12'}

  is-stream@3.0.0:
    resolution: {integrity: sha512-LnQR4bZ9IADDRSkvpqMGvt/tEJWclzklNgSw48V5EAaAeDd6qGvN8ei6k5p0tvxSR171VmGyHuTiAOfxAbr8kA==}
    engines: {node: ^12.20.0 || ^14.13.1 || >=16.0.0}

  is-unicode-supported@1.3.0:
    resolution: {integrity: sha512-43r2mRvz+8JRIKnWJ+3j8JtjRKZ6GmjzfaE/qiBJnikNnYv/6bagRJ1kUhNk8R5EX/GkobD+r+sfxCPJsiKBLQ==}
    engines: {node: '>=12'}

  isexe@2.0.0:
    resolution: {integrity: sha512-RHxMLp9lnKHGHRng9QFhRCMbYAcVpn69smSGcq3f36xjgVVWThj4qqLbTLlq7Ssj8B+fIQ1EuCEGI2lKsyQeIw==}

  jackspeak@3.4.3:
    resolution: {integrity: sha512-OGlZQpz2yfahA/Rd1Y8Cd9SIEsqvXkLVoSw/cgwhnhFMDbsQFeZYoJJ7bIZBS9BcamUW96asq/npPWugM+RQBw==}

  jiti@1.21.7:
    resolution: {integrity: sha512-/imKNG4EbWNrVjoNC/1H5/9GFy+tqjGBHCaSsN+P2RnPqjsLmv6UD3Ej+Kj8nBWaRAwyk7kK5ZUc+OEatnTR3A==}
    hasBin: true

  jose@4.15.9:
    resolution: {integrity: sha512-1vUQX+IdDMVPj4k8kOxgUqlcK518yluMuGZwqlr44FS1ppZB/5GWh4rZG89erpOBOJjU/OBsnCVFfapsRz6nEA==}

  js-tokens@4.0.0:
    resolution: {integrity: sha512-RdJUflcE3cUzKiMqQgsCu06FPu9UdIJO0beYbPhHN4k6apgJtifcoCtT9bcxOpYBtpD2kCM6Sbzg4CausW/PKQ==}

  js-yaml@4.1.0:
    resolution: {integrity: sha512-wpxZs9NoxZaJESJGIZTyDEaYpl0FKSA+FB9aJiyemKhMwkxQg63h4T1KJgUGHpTqPDNRcmmYLugrRjJlBtWvRA==}
    hasBin: true

  jsesc@3.1.0:
    resolution: {integrity: sha512-/sM3dO2FOzXjKQhJuo0Q173wf2KOo8t4I8vHy6lF9poUp7bKT0/NHE8fPX23PwfhnykfqnC2xRxOnVw5XuGIaA==}
    engines: {node: '>=6'}
    hasBin: true

  json-parse-even-better-errors@2.3.1:
    resolution: {integrity: sha512-xyFwyhro/JEof6Ghe2iz2NcXoj2sloNsWr/XsERDK/oiPCfaNhl5ONfp+jQdAZRQQ0IJWNzH9zIZF7li91kh2w==}

  jsonfile@6.1.0:
    resolution: {integrity: sha512-5dgndWOriYSm5cnYaJNhalLNDKOqFwyDB/rr1E9ZsGciGvKPs8R2xYGCacuf3z6K1YKDz182fd+fY3cn3pMqXQ==}

  jwt-decode@4.0.0:
    resolution: {integrity: sha512-+KJGIyHgkGuIq3IEBNftfhW/LfWhXUIY6OmyVWjliu5KH1y0fw7VQ8YndE2O4qZdMSd9SqbnC8GOcZEy0Om7sA==}
    engines: {node: '>=18'}

  kleur@3.0.3:
    resolution: {integrity: sha512-eTIzlVOSUR+JxdDFepEYcBMtZ9Qqdef+rnzWdRZuMbOywu5tO2w2N7rqjoANZ5k9vywhL6Br1VRjUIgTQx4E8w==}
    engines: {node: '>=6'}

  lilconfig@3.1.3:
    resolution: {integrity: sha512-/vlFKAoH5Cgt3Ie+JLhRbwOsCQePABiU3tJ1egGvyQ+33R/vcwM2Zl2QR/LzjsBeItPt3oSVXapn+m4nQDvpzw==}
    engines: {node: '>=14'}

  lines-and-columns@1.2.4:
    resolution: {integrity: sha512-7ylylesZQ/PV29jhEDl3Ufjo6ZX7gCqJr5F7PKrqc93v7fzSymt1BpwEU8nAUXs8qzzvqhbjhK5QZg6Mt/HkBg==}

  lodash.castarray@4.4.0:
    resolution: {integrity: sha512-aVx8ztPv7/2ULbArGJ2Y42bG1mEQ5mGjpdvrbJcJFU3TbYybe+QlLS4pst9zV52ymy2in1KpFPiZnAOATxD4+Q==}

  lodash.defaults@4.2.0:
    resolution: {integrity: sha512-qjxPLHd3r5DnsdGacqOMU6pb/avJzdh9tFX2ymgoZE27BmjXrNy/y4LoaiTeAb+O3gL8AfpJGtqfX/ae2leYYQ==}

  lodash.isarguments@3.1.0:
    resolution: {integrity: sha512-chi4NHZlZqZD18a0imDHnZPrDeBbTtVN7GXMwuGdRH9qotxAjYs3aVLKc7zNOG9eddR5Ksd8rvFEBc9SsggPpg==}

  lodash.isplainobject@4.0.6:
    resolution: {integrity: sha512-oSXzaWypCMHkPC3NvBEaPHf0KsA5mvPrOPgQWDsbg8n7orZ290M0BmC/jgRZ4vcJ6DTAhjrsSYgdsW/F+MFOBA==}

  lodash.merge@4.6.2:
    resolution: {integrity: sha512-0KpjqXRVvrYyCsX1swR/XTK0va6VQkQM6MNo7PqW77ByjAhoARA8EfrP1N4+KlKj8YS0ZUCtRT/YUuhyYDujIQ==}

  lodash.mergewith@4.6.2:
    resolution: {integrity: sha512-GK3g5RPZWTRSeLSpgP8Xhra+pnjBC56q9FZYe1d5RN3TJ35dbkGy3YqBSMbyCrlbi+CM9Z3Jk5yTL7RCsqboyQ==}

  log-symbols@5.1.0:
    resolution: {integrity: sha512-l0x2DvrW294C9uDCoQe1VSU4gf529FkSZ6leBl4TiqZH/e+0R7hSfHQBNut2mNygDgHwvYHfFLn6Oxb3VWj2rA==}
    engines: {node: '>=12'}

  longest-streak@3.1.0:
    resolution: {integrity: sha512-9Ri+o0JYgehTaVBBDoMqIl8GXtbWg711O3srftcHhZ0dqnETqLaoIK0x17fUw9rFSlK/0NlsKe0Ahhyl5pXE2g==}

  loose-envify@1.4.0:
    resolution: {integrity: sha512-lyuxPGr/Wfhrlem2CL/UcnUc1zcqKAImBDzukY7Y5F/yQiNdko6+fRLevlw1HgMySw7f611UIY408EtxRSoK3Q==}
    hasBin: true

  lowlight@1.20.0:
    resolution: {integrity: sha512-8Ktj+prEb1RoCPkEOrPMYUN/nCggB7qAWe3a7OpMjWQkh3l2RD5wKRQ+o8Q8YuI9RG/xs95waaI/E6ym/7NsTw==}

  lowlight@3.3.0:
    resolution: {integrity: sha512-0JNhgFoPvP6U6lE/UdVsSq99tn6DhjjpAj5MxG49ewd2mOBVtwWYIT8ClyABhq198aXXODMU6Ox8DrGy/CpTZQ==}

  lru-cache@10.4.3:
    resolution: {integrity: sha512-JNAzZcXrCt42VGLuYz0zfAzDfAvJWW6AfYlDBQyDV5DClI2m5sAmK+OIO7s59XfsRsWHp02jAJrRadPRGTt6SQ==}

  lru-cache@6.0.0:
    resolution: {integrity: sha512-Jo6dJ04CmSjuznwJSS3pUeWmd/H0ffTlkXXgwZi+eq1UCmqQwCh+eLsYOYCwY991i2Fah4h1BEMCx4qThGbsiA==}
    engines: {node: '>=10'}

  lucide-react@0.477.0:
    resolution: {integrity: sha512-yCf7aYxerFZAbd8jHJxjwe1j7jEMPptjnaOqdYeirFnEy85cNR3/L+o0I875CYFYya+eEVzZSbNuRk8BZPDpVw==}
    peerDependencies:
      react: ^16.5.1 || ^17.0.0 || ^18.0.0 || ^19.0.0

  markdown-table@3.0.4:
    resolution: {integrity: sha512-wiYz4+JrLyb/DqW2hkFJxP7Vd7JuTDm77fvbM8VfEQdmSMqcImWeeRbHwZjBjIFki/VaMK2BhFi7oUUZeM5bqw==}

  markdown-to-jsx@7.7.6:
    resolution: {integrity: sha512-/PWFFoKKMidk4Ut06F5hs5sluq1aJ0CGvUJWsnCK6hx/LPM8vlhvKAxtGHJ+U+V2Il2wmnfO6r81ICD3xZRVaw==}
    engines: {node: '>= 10'}
    peerDependencies:
      react: '>= 0.14.0'

  math-intrinsics@1.1.0:
    resolution: {integrity: sha512-/IXtbwEk5HTPyEwyKX6hGkYXxM9nbj64B+ilVJnC/R6B0pH5G4V3b0pVbL7DBj4tkhBAppbQUlf6F6Xl9LHu1g==}
    engines: {node: '>= 0.4'}

  mdast-util-find-and-replace@3.0.2:
    resolution: {integrity: sha512-Tmd1Vg/m3Xz43afeNxDIhWRtFZgM2VLyaf4vSTYwudTyeuTneoL3qtWMA5jeLyz/O1vDJmmV4QuScFCA2tBPwg==}

  mdast-util-from-markdown@2.0.2:
    resolution: {integrity: sha512-uZhTV/8NBuw0WHkPTrCqDOl0zVe1BIng5ZtHoDk49ME1qqcjYmmLmOf0gELgcRMxN4w2iuIeVso5/6QymSrgmA==}

  mdast-util-gfm-autolink-literal@2.0.1:
    resolution: {integrity: sha512-5HVP2MKaP6L+G6YaxPNjuL0BPrq9orG3TsrZ9YXbA3vDw/ACI4MEsnoDpn6ZNm7GnZgtAcONJyPhOP8tNJQavQ==}

  mdast-util-gfm-footnote@2.1.0:
    resolution: {integrity: sha512-sqpDWlsHn7Ac9GNZQMeUzPQSMzR6Wv0WKRNvQRg0KqHh02fpTz69Qc1QSseNX29bhz1ROIyNyxExfawVKTm1GQ==}

  mdast-util-gfm-strikethrough@2.0.0:
    resolution: {integrity: sha512-mKKb915TF+OC5ptj5bJ7WFRPdYtuHv0yTRxK2tJvi+BDqbkiG7h7u/9SI89nRAYcmap2xHQL9D+QG/6wSrTtXg==}

  mdast-util-gfm-table@2.0.0:
    resolution: {integrity: sha512-78UEvebzz/rJIxLvE7ZtDd/vIQ0RHv+3Mh5DR96p7cS7HsBhYIICDBCu8csTNWNO6tBWfqXPWekRuj2FNOGOZg==}

  mdast-util-gfm-task-list-item@2.0.0:
    resolution: {integrity: sha512-IrtvNvjxC1o06taBAVJznEnkiHxLFTzgonUdy8hzFVeDun0uTjxxrRGVaNFqkU1wJR3RBPEfsxmU6jDWPofrTQ==}

  mdast-util-gfm@3.1.0:
    resolution: {integrity: sha512-0ulfdQOM3ysHhCJ1p06l0b0VKlhU0wuQs3thxZQagjcjPrlFRqY215uZGHHJan9GEAXd9MbfPjFJz+qMkVR6zQ==}

  mdast-util-mdx-expression@2.0.1:
    resolution: {integrity: sha512-J6f+9hUp+ldTZqKRSg7Vw5V6MqjATc+3E4gf3CFNcuZNWD8XdyI6zQ8GqH7f8169MM6P7hMBRDVGnn7oHB9kXQ==}

  mdast-util-mdx-jsx@3.2.0:
    resolution: {integrity: sha512-lj/z8v0r6ZtsN/cGNNtemmmfoLAFZnjMbNyLzBafjzikOM+glrjNHPlf6lQDOTccj9n5b0PPihEBbhneMyGs1Q==}

  mdast-util-mdxjs-esm@2.0.1:
    resolution: {integrity: sha512-EcmOpxsZ96CvlP03NghtH1EsLtr0n9Tm4lPUJUBccV9RwUOneqSycg19n5HGzCf+10LozMRSObtVr3ee1WoHtg==}

  mdast-util-newline-to-break@2.0.0:
    resolution: {integrity: sha512-MbgeFca0hLYIEx/2zGsszCSEJJ1JSCdiY5xQxRcLDDGa8EPvlLPupJ4DSajbMPAnC0je8jfb9TiUATnxxrHUog==}

  mdast-util-phrasing@4.1.0:
    resolution: {integrity: sha512-TqICwyvJJpBwvGAMZjj4J2n0X8QWp21b9l0o7eXyVJ25YNWYbJDVIyD1bZXE6WtV6RmKJVYmQAKWa0zWOABz2w==}

  mdast-util-to-hast@13.2.0:
    resolution: {integrity: sha512-QGYKEuUsYT9ykKBCMOEDLsU5JRObWQusAolFMeko/tYPufNkRffBAQjIE+99jbA87xv6FgmjLtwjh9wBWajwAA==}

  mdast-util-to-markdown@2.1.2:
    resolution: {integrity: sha512-xj68wMTvGXVOKonmog6LwyJKrYXZPvlwabaryTjLh9LuvovB/KAH+kvi8Gjj+7rJjsFi23nkUxRQv1KqSroMqA==}

  mdast-util-to-string@4.0.0:
    resolution: {integrity: sha512-0H44vDimn51F0YwvxSJSm0eCDOJTRlmN0R1yBh4HLj9wiV1Dn0QoXGbvFAWj2hSItVTlCmBF1hqKlIyUBVFLPg==}

  merge-stream@2.0.0:
    resolution: {integrity: sha512-abv/qOcuPfk3URPfDzmZU1LKmuw8kT+0nIHvKrKgFrwifol/doWcdA4ZqsWQ8ENrFKkd67Mfpo/LovbIUsbt3w==}

  merge2@1.4.1:
    resolution: {integrity: sha512-8q7VEgMJW4J8tcfVPy8g09NcQwZdbwFEqhe/WZkoIzjn/3TGDwtOCYtXGxA3O8tPzpczCCDgv+P2P5y00ZJOOg==}
    engines: {node: '>= 8'}

  micromark-core-commonmark@2.0.3:
    resolution: {integrity: sha512-RDBrHEMSxVFLg6xvnXmb1Ayr2WzLAWjeSATAoxwKYJV94TeNavgoIdA0a9ytzDSVzBy2YKFK+emCPOEibLeCrg==}

  micromark-extension-gfm-autolink-literal@2.1.0:
    resolution: {integrity: sha512-oOg7knzhicgQ3t4QCjCWgTmfNhvQbDDnJeVu9v81r7NltNCVmhPy1fJRX27pISafdjL+SVc4d3l48Gb6pbRypw==}

  micromark-extension-gfm-footnote@2.1.0:
    resolution: {integrity: sha512-/yPhxI1ntnDNsiHtzLKYnE3vf9JZ6cAisqVDauhp4CEHxlb4uoOTxOCJ+9s51bIB8U1N1FJ1RXOKTIlD5B/gqw==}

  micromark-extension-gfm-strikethrough@2.1.0:
    resolution: {integrity: sha512-ADVjpOOkjz1hhkZLlBiYA9cR2Anf8F4HqZUO6e5eDcPQd0Txw5fxLzzxnEkSkfnD0wziSGiv7sYhk/ktvbf1uw==}

  micromark-extension-gfm-table@2.1.1:
    resolution: {integrity: sha512-t2OU/dXXioARrC6yWfJ4hqB7rct14e8f7m0cbI5hUmDyyIlwv5vEtooptH8INkbLzOatzKuVbQmAYcbWoyz6Dg==}

  micromark-extension-gfm-tagfilter@2.0.0:
    resolution: {integrity: sha512-xHlTOmuCSotIA8TW1mDIM6X2O1SiX5P9IuDtqGonFhEK0qgRI4yeC6vMxEV2dgyr2TiD+2PQ10o+cOhdVAcwfg==}

  micromark-extension-gfm-task-list-item@2.1.0:
    resolution: {integrity: sha512-qIBZhqxqI6fjLDYFTBIa4eivDMnP+OZqsNwmQ3xNLE4Cxwc+zfQEfbs6tzAo2Hjq+bh6q5F+Z8/cksrLFYWQQw==}

  micromark-extension-gfm@3.0.0:
    resolution: {integrity: sha512-vsKArQsicm7t0z2GugkCKtZehqUm31oeGBV/KVSorWSy8ZlNAv7ytjFhvaryUiCUJYqs+NoE6AFhpQvBTM6Q4w==}

  micromark-factory-destination@2.0.1:
    resolution: {integrity: sha512-Xe6rDdJlkmbFRExpTOmRj9N3MaWmbAgdpSrBQvCFqhezUn4AHqJHbaEnfbVYYiexVSs//tqOdY/DxhjdCiJnIA==}

  micromark-factory-label@2.0.1:
    resolution: {integrity: sha512-VFMekyQExqIW7xIChcXn4ok29YE3rnuyveW3wZQWWqF4Nv9Wk5rgJ99KzPvHjkmPXF93FXIbBp6YdW3t71/7Vg==}

  micromark-factory-space@2.0.1:
    resolution: {integrity: sha512-zRkxjtBxxLd2Sc0d+fbnEunsTj46SWXgXciZmHq0kDYGnck/ZSGj9/wULTV95uoeYiK5hRXP2mJ98Uo4cq/LQg==}

  micromark-factory-title@2.0.1:
    resolution: {integrity: sha512-5bZ+3CjhAd9eChYTHsjy6TGxpOFSKgKKJPJxr293jTbfry2KDoWkhBb6TcPVB4NmzaPhMs1Frm9AZH7OD4Cjzw==}

  micromark-factory-whitespace@2.0.1:
    resolution: {integrity: sha512-Ob0nuZ3PKt/n0hORHyvoD9uZhr+Za8sFoP+OnMcnWK5lngSzALgQYKMr9RJVOWLqQYuyn6ulqGWSXdwf6F80lQ==}

  micromark-util-character@2.1.1:
    resolution: {integrity: sha512-wv8tdUTJ3thSFFFJKtpYKOYiGP2+v96Hvk4Tu8KpCAsTMs6yi+nVmGh1syvSCsaxz45J6Jbw+9DD6g97+NV67Q==}

  micromark-util-chunked@2.0.1:
    resolution: {integrity: sha512-QUNFEOPELfmvv+4xiNg2sRYeS/P84pTW0TCgP5zc9FpXetHY0ab7SxKyAQCNCc1eK0459uoLI1y5oO5Vc1dbhA==}

  micromark-util-classify-character@2.0.1:
    resolution: {integrity: sha512-K0kHzM6afW/MbeWYWLjoHQv1sgg2Q9EccHEDzSkxiP/EaagNzCm7T/WMKZ3rjMbvIpvBiZgwR3dKMygtA4mG1Q==}

  micromark-util-combine-extensions@2.0.1:
    resolution: {integrity: sha512-OnAnH8Ujmy59JcyZw8JSbK9cGpdVY44NKgSM7E9Eh7DiLS2E9RNQf0dONaGDzEG9yjEl5hcqeIsj4hfRkLH/Bg==}

  micromark-util-decode-numeric-character-reference@2.0.2:
    resolution: {integrity: sha512-ccUbYk6CwVdkmCQMyr64dXz42EfHGkPQlBj5p7YVGzq8I7CtjXZJrubAYezf7Rp+bjPseiROqe7G6foFd+lEuw==}

  micromark-util-decode-string@2.0.1:
    resolution: {integrity: sha512-nDV/77Fj6eH1ynwscYTOsbK7rR//Uj0bZXBwJZRfaLEJ1iGBR6kIfNmlNqaqJf649EP0F3NWNdeJi03elllNUQ==}

  micromark-util-encode@2.0.1:
    resolution: {integrity: sha512-c3cVx2y4KqUnwopcO9b/SCdo2O67LwJJ/UyqGfbigahfegL9myoEFoDYZgkT7f36T0bLrM9hZTAaAyH+PCAXjw==}

  micromark-util-html-tag-name@2.0.1:
    resolution: {integrity: sha512-2cNEiYDhCWKI+Gs9T0Tiysk136SnR13hhO8yW6BGNyhOC4qYFnwF1nKfD3HFAIXA5c45RrIG1ub11GiXeYd1xA==}

  micromark-util-normalize-identifier@2.0.1:
    resolution: {integrity: sha512-sxPqmo70LyARJs0w2UclACPUUEqltCkJ6PhKdMIDuJ3gSf/Q+/GIe3WKl0Ijb/GyH9lOpUkRAO2wp0GVkLvS9Q==}

  micromark-util-resolve-all@2.0.1:
    resolution: {integrity: sha512-VdQyxFWFT2/FGJgwQnJYbe1jjQoNTS4RjglmSjTUlpUMa95Htx9NHeYW4rGDJzbjvCsl9eLjMQwGeElsqmzcHg==}

  micromark-util-sanitize-uri@2.0.1:
    resolution: {integrity: sha512-9N9IomZ/YuGGZZmQec1MbgxtlgougxTodVwDzzEouPKo3qFWvymFHWcnDi2vzV1ff6kas9ucW+o3yzJK9YB1AQ==}

  micromark-util-subtokenize@2.1.0:
    resolution: {integrity: sha512-XQLu552iSctvnEcgXw6+Sx75GflAPNED1qx7eBJ+wydBb2KCbRZe+NwvIEEMM83uml1+2WSXpBAcp9IUCgCYWA==}

  micromark-util-symbol@2.0.1:
    resolution: {integrity: sha512-vs5t8Apaud9N28kgCrRUdEed4UJ+wWNvicHLPxCa9ENlYuAY31M0ETy5y1vA33YoNPDFTghEbnh6efaE8h4x0Q==}

  micromark-util-types@2.0.2:
    resolution: {integrity: sha512-Yw0ECSpJoViF1qTU4DC6NwtC4aWGt1EkzaQB8KPPyCRR8z9TWeV0HbEFGTO+ZY1wB22zmxnJqhPyTpOVCpeHTA==}

  micromark@4.0.2:
    resolution: {integrity: sha512-zpe98Q6kvavpCr1NPVSCMebCKfD7CA2NqZ+rykeNhONIJBpc1tFKt9hucLGwha3jNTNI8lHpctWJWoimVF4PfA==}

  micromatch@4.0.8:
    resolution: {integrity: sha512-PXwfBhYu0hBCPw8Dn0E+WDYb7af3dSLVWKi3HGv84IdF4TyFoC0ysxFd0Goxw7nSv4T/PzEJQxsYsEiFCKo2BA==}
    engines: {node: '>=8.6'}

  mime-db@1.52.0:
    resolution: {integrity: sha512-sPU4uV7dYlvtWJxwwxHD0PuihVNiE7TyAbQ5SWxDCB9mUYvOgroQOwYQQOKPJ8CIbE+1ETVlOoK1UC2nU3gYvg==}
    engines: {node: '>= 0.6'}

  mime-types@2.1.35:
    resolution: {integrity: sha512-ZDY+bPm5zTTF+YpCrAU9nK0UgICYPT0QtT1NZWFv4s++TNkcgVaT0g6+4R2uI4MjQjzysHB1zxuWL50hzaeXiw==}
    engines: {node: '>= 0.6'}

  mimic-fn@2.1.0:
    resolution: {integrity: sha512-OqbOk5oEQeAZ8WXWydlu9HJjz9WVdEIvamMCcXmuqUYjTknH/sqsWvhQ3vgwKFRR1HpjvNBKQ37nbJgYzGqGcg==}
    engines: {node: '>=6'}

  mimic-fn@4.0.0:
    resolution: {integrity: sha512-vqiC06CuhBTUdZH+RYl8sFrL096vA45Ok5ISO6sE/Mr1jRbGH4Csnhi8f3wKVl7x8mO4Au7Ir9D3Oyv1VYMFJw==}
    engines: {node: '>=12'}

  mini-svg-data-uri@1.4.4:
    resolution: {integrity: sha512-r9deDe9p5FJUPZAk3A59wGH7Ii9YrjjWw0jmw/liSbHl2CHiyXj6FcDXDu2K3TjVAXqiJdaw3xxwlZZr9E6nHg==}
    hasBin: true

  minimatch@3.1.2:
    resolution: {integrity: sha512-J7p63hRiAjw1NDEww1W7i37+ByIrOWO5XQQAzZ3VOcL0PNybwpfmV/N05zFAzwQ9USyEcX6t3UO+K5aqBQOIHw==}

  minimatch@9.0.5:
    resolution: {integrity: sha512-G6T0ZX48xgozx7587koeX9Ys2NYy6Gmv//P89sEte9V9whIapMNF4idKxnW2QtCcLiTWlb/wfCabAtAFWhhBow==}
    engines: {node: '>=16 || 14 >=14.17'}

  minipass@7.1.2:
    resolution: {integrity: sha512-qOOzS1cBTWYF4BH8fVePDBOO9iptMnGUEZwNc/cMWnTV2nVLZ7VoNWEPHkYczZA0pdoA7dl6e7FL659nX9S2aw==}
    engines: {node: '>=16 || 14 >=14.17'}

  mkdirp@1.0.4:
    resolution: {integrity: sha512-vVqVZQyf3WLx2Shd0qJ9xuvqgAyKPLAiqITEtqW0oIUjzo3PePDd6fW9iFz30ef7Ysp/oiWqbhszeGWW2T6Gzw==}
    engines: {node: '>=10'}
    hasBin: true

  ms@2.1.3:
    resolution: {integrity: sha512-6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsvoVaHJq/s5xXI6/XXP6tz7R9xAOtHnSO/tXtF3WRTlA==}

  mz@2.7.0:
    resolution: {integrity: sha512-z81GNO7nnYMEhrGh9LeymoE4+Yr0Wn5McHIZMK5cfQCl+NDX08sCZgUc9/6MHni9IWuFLm1Z3HTCXu2z9fN62Q==}

  nanoid@3.3.11:
    resolution: {integrity: sha512-N8SpfPUnUp1bK+PMYW8qSWdl9U+wwNWI4QKxOYDy9JAro3WMX7p2OeVRF9v+347pnakNevPmiHhNmZ2HbFA76w==}
    engines: {node: ^10 || ^12 || ^13.7 || ^14 || >=15.0.1}
    hasBin: true

  next-auth@4.24.11:
    resolution: {integrity: sha512-pCFXzIDQX7xmHFs4KVH4luCjaCbuPRtZ9oBUjUhOk84mZ9WVPf94n87TxYI4rSRf9HmfHEF8Yep3JrYDVOo3Cw==}
    peerDependencies:
      '@auth/core': 0.34.2
      next: ^12.2.5 || ^13 || ^14 || ^15
      nodemailer: ^6.6.5
      react: ^17.0.2 || ^18 || ^19
      react-dom: ^17.0.2 || ^18 || ^19
    peerDependenciesMeta:
      '@auth/core':
        optional: true
      nodemailer:
        optional: true

  next@15.2.0:
    resolution: {integrity: sha512-VaiM7sZYX8KIAHBrRGSFytKknkrexNfGb8GlG6e93JqueCspuGte8i4ybn8z4ww1x3f2uzY4YpTaBEW4/hvsoQ==}
    engines: {node: ^18.18.0 || ^19.8.0 || >= 20.0.0}
    hasBin: true
    peerDependencies:
      '@opentelemetry/api': ^1.1.0
      '@playwright/test': ^1.41.2
      babel-plugin-react-compiler: '*'
      react: ^18.2.0 || 19.0.0-rc-de68d2f4-20241204 || ^19.0.0
      react-dom: ^18.2.0 || 19.0.0-rc-de68d2f4-20241204 || ^19.0.0
      sass: ^1.3.0
    peerDependenciesMeta:
      '@opentelemetry/api':
        optional: true
      '@playwright/test':
        optional: true
      babel-plugin-react-compiler:
        optional: true
      sass:
        optional: true

  node-domexception@1.0.0:
    resolution: {integrity: sha512-/jKZoMpw0F8GRwl4/eLROPA3cfcXtLApP0QzLmUT/HuPCZWyB7IY9ZrMeKw2O/nFIqPQB3PVM9aYm0F312AXDQ==}
    engines: {node: '>=10.5.0'}
    deprecated: Use your platform's native DOMException instead

  node-fetch@3.3.2:
    resolution: {integrity: sha512-dRB78srN/l6gqWulah9SrxeYnxeddIG30+GOqK/9OlLVyLg3HPnr6SqOWTWOXKRwC2eGYCkZ59NNuSgvSrpgOA==}
    engines: {node: ^12.20.0 || ^14.13.1 || >=16.0.0}

  node-releases@2.0.19:
    resolution: {integrity: sha512-xxOWJsBKtzAq7DY0J+DTzuz58K8e7sJbdgwkbMWQe8UYB6ekmsQ45q0M/tJDsGaZmbC+l7n57UV8Hl5tHxO9uw==}

  normalize-path@3.0.0:
    resolution: {integrity: sha512-6eZs5Ls3WtCisHWp9S2GUy8dqkpGi4BVSz3GaqiE6ezub0512ESztXUwUB6C6IKbQkY2Pnb/mD4WYojCRwcwLA==}
    engines: {node: '>=0.10.0'}

  normalize-range@0.1.2:
    resolution: {integrity: sha512-bdok/XvKII3nUpklnV6P2hxtMNrCboOjAcyBuQnWEhO665FwrSNRxU+AqpsyvO6LgGYPspN+lu5CLtw4jPRKNA==}
    engines: {node: '>=0.10.0'}

  npm-run-path@5.3.0:
    resolution: {integrity: sha512-ppwTtiJZq0O/ai0z7yfudtBpWIoxM8yE6nHi1X47eFR2EWORqfbu6CnPlNsjeN683eT0qG6H/Pyf9fCcvjnnnQ==}
    engines: {node: ^12.20.0 || ^14.13.1 || >=16.0.0}

  oauth@0.9.15:
    resolution: {integrity: sha512-a5ERWK1kh38ExDEfoO6qUHJb32rd7aYmPHuyCu3Fta/cnICvYmgd2uhuKXvPD+PXB+gCEYYEaQdIRAjCOwAKNA==}

  object-assign@4.1.1:
    resolution: {integrity: sha512-rJgTQnkUnH1sFw8yT6VSU3zD3sWmu6sZhIseY8VX+GRu3P6F7Fu+JNDoXfklElbLJSnc3FUQHVe4cU5hj+BcUg==}
    engines: {node: '>=0.10.0'}

  object-hash@2.2.0:
    resolution: {integrity: sha512-gScRMn0bS5fH+IuwyIFgnh9zBdo4DV+6GhygmWM9HyNJSgS0hScp1f5vjtm7oIIOiT9trXrShAkLFSc2IqKNgw==}
    engines: {node: '>= 6'}

  object-hash@3.0.0:
    resolution: {integrity: sha512-RSn9F68PjH9HqtltsSnqYC1XXoWe9Bju5+213R98cNGttag9q9yAOTzdbsqvIa7aNm5WffBZFpWYr2aWrklWAw==}
    engines: {node: '>= 6'}

  oidc-token-hash@5.1.0:
    resolution: {integrity: sha512-y0W+X7Ppo7oZX6eovsRkuzcSM40Bicg2JEJkDJ4irIt1wsYAP5MLSNv+QAogO8xivMffw/9OvV3um1pxXgt1uA==}
    engines: {node: ^10.13.0 || >=12.0.0}

  once@1.4.0:
    resolution: {integrity: sha512-lNaJgI+2Q5URQBkccEKHTQOPaXdUxnZZElQTZY0MFUAuaEqe1E+Nyvgdz/aIyNi6Z9MzO5dv1H8n58/GELp3+w==}

  onetime@5.1.2:
    resolution: {integrity: sha512-kbpaSSGJTWdAY5KPVeMOKXSrPtr8C8C7wodJbcsd51jRnmD+GZu8Y0VoU6Dm5Z4vWr0Ig/1NKuWRKf7j5aaYSg==}
    engines: {node: '>=6'}

  onetime@6.0.0:
    resolution: {integrity: sha512-1FlR+gjXK7X+AsAHso35MnyN5KqGwJRi/31ft6x0M194ht7S+rWAvd7PHss9xSKMzE0asv1pyIHaJYq+BbacAQ==}
    engines: {node: '>=12'}

  openid-client@5.7.1:
    resolution: {integrity: sha512-jDBPgSVfTnkIh71Hg9pRvtJc6wTwqjRkN88+gCFtYWrlP4Yx2Dsrow8uPi3qLr/aeymPF3o2+dS+wOpglK04ew==}

  ora@6.3.1:
    resolution: {integrity: sha512-ERAyNnZOfqM+Ao3RAvIXkYh5joP220yf59gVe2X/cI6SiCxIdi4c9HZKZD8R6q/RDXEje1THBju6iExiSsgJaQ==}
    engines: {node: ^12.20.0 || ^14.13.1 || >=16.0.0}

  package-json-from-dist@1.0.1:
    resolution: {integrity: sha512-UEZIS3/by4OC8vL3P2dTXRETpebLI2NiI5vIrjaD/5UtrkFX/tNbwjTSRAGC/+7CAo2pIcBaRgWmcBBHcsaCIw==}

  parent-module@1.0.1:
    resolution: {integrity: sha512-GQ2EWRpQV8/o+Aw8YqtfZZPfNRWZYkbidE9k5rpl/hC3vtHHBfGm2Ifi6qWV+coDGkrUKZAxE3Lot5kcsRlh+g==}
    engines: {node: '>=6'}

  parse-entities@2.0.0:
    resolution: {integrity: sha512-kkywGpCcRYhqQIchaWqZ875wzpS/bMKhz5HnN3p7wveJTkTtyAB/AlnS0f8DFSqYW1T82t6yEAkEcB+A1I3MbQ==}

  parse-entities@4.0.2:
    resolution: {integrity: sha512-GG2AQYWoLgL877gQIKeRPGO1xF9+eG1ujIb5soS5gPvLQ1y2o8FL90w2QWNdf9I361Mpp7726c+lj3U0qK1uGw==}

  parse-json@5.2.0:
    resolution: {integrity: sha512-ayCKvm/phCGxOkYRSCM82iDwct8/EonSEgCSxWxD7ve6jHggsFl4fZVQBPRNgQoKiuV/odhFrGzQXZwbifC8Rg==}
    engines: {node: '>=8'}

  parse5-htmlparser2-tree-adapter@6.0.1:
    resolution: {integrity: sha512-qPuWvbLgvDGilKc5BoicRovlT4MtYT6JfJyBOMDsKoiT+GiuP5qyrPCnR9HcPECIJJmZh5jRndyNThnhhb/vlA==}

  parse5@5.1.1:
    resolution: {integrity: sha512-ugq4DFI0Ptb+WWjAdOK16+u/nHfiIrcE+sh8kZMaM0WllQKLI9rOUq6c2b7cwPkXdzfQESqvoqK6ug7U/Yyzug==}

  parse5@6.0.1:
    resolution: {integrity: sha512-Ofn/CTFzRGTTxwpNEs9PP93gXShHcTq255nzRYSKe8AkVpZY7e1fpmTfOyoIvjP5HG7Z2ZM7VS9PPhQGW2pOpw==}

  parse5@7.3.0:
    resolution: {integrity: sha512-IInvU7fabl34qmi9gY8XOVxhYyMyuH2xUNpb2q8/Y+7552KlejkRvqvD19nMoUW/uQGGbqNpA6Tufu5FL5BZgw==}

  path-is-absolute@1.0.1:
    resolution: {integrity: sha512-AVbw3UJ2e9bq64vSaS9Am0fje1Pa8pbGqTTsmXfaIiMpnr5DlDhfJOuLj9Sf95ZPVDAUerDfEk88MPmPe7UCQg==}
    engines: {node: '>=0.10.0'}

  path-key@3.1.1:
    resolution: {integrity: sha512-ojmeN0qd+y0jszEtoY48r0Peq5dwMEkIlCOu6Q5f41lfkswXuKtYrhgoTpLnyIcHm24Uhqx+5Tqm2InSwLhE6Q==}
    engines: {node: '>=8'}

  path-key@4.0.0:
    resolution: {integrity: sha512-haREypq7xkM7ErfgIyA0z+Bj4AGKlMSdlQE2jvJo6huWD1EdkKYV+G/T4nq0YEF2vgTT8kqMFKo1uHn950r4SQ==}
    engines: {node: '>=12'}

  path-parse@1.0.7:
    resolution: {integrity: sha512-LDJzPVEEEPR+y48z93A0Ed0yXb8pAByGWo/k5YYdYgpY2/2EsOsksJrq7lOHxryrVOn1ejG6oAp8ahvOIQD8sw==}

  path-scurry@1.11.1:
    resolution: {integrity: sha512-Xa4Nw17FS9ApQFJ9umLiJS4orGjm7ZzwUrwamcGQuHSzDyth9boKDaycYdDcZDuqYATXw4HFXgaqWTctW/v1HA==}
    engines: {node: '>=16 || 14 >=14.18'}

  path-type@4.0.0:
    resolution: {integrity: sha512-gDKb8aZMDeD/tZWs9P6+q0J9Mwkdl6xMV8TjnGP3qJVJ06bdMgkbBlLU8IdfOsIsFz2BW1rNVT3XuNEl8zPAvw==}
    engines: {node: '>=8'}

  picocolors@1.1.1:
    resolution: {integrity: sha512-xceH2snhtb5M9liqDsmEw56le376mTZkEX/jEb/RxNFyegNul7eNslCXP9FDj/Lcu0X8KEyMceP2ntpaHrDEVA==}

  picomatch@2.3.1:
    resolution: {integrity: sha512-JU3teHTNjmE2VCGFzuY8EXzCDVwEqB2a8fsIvwaStHhAWJEeVd1o1QD80CU6+ZdEXXSLbSsuLwJjkCBWqRQUVA==}
    engines: {node: '>=8.6'}

  pify@2.3.0:
    resolution: {integrity: sha512-udgsAY+fTnvv7kI7aaxbqwWNb0AHiB0qBO89PZKPkoTmGOgdbrHDKD+0B2X4uTfJ/FT1R09r9gTsjUjNJotuog==}
    engines: {node: '>=0.10.0'}

  pirates@4.0.7:
    resolution: {integrity: sha512-TfySrs/5nm8fQJDcBDuUng3VOUKsd7S+zqvbOTiGXHfxX4wK31ard+hoNuvkicM/2YFzlpDgABOevKSsB4G/FA==}
    engines: {node: '>= 6'}

  popmotion@11.0.5:
    resolution: {integrity: sha512-la8gPM1WYeFznb/JqF4GiTkRRPZsfaj2+kCxqQgr2MJylMmIKUwBfWW8Wa5fml/8gmtlD5yI01MP1QCZPWmppA==}

  postcss-import@15.1.0:
    resolution: {integrity: sha512-hpr+J05B2FVYUAXHeK1YyI267J/dDDhMU6B6civm8hSY1jYJnBXxzKDKDswzJmtLHryrjhnDjqqp/49t8FALew==}
    engines: {node: '>=14.0.0'}
    peerDependencies:
      postcss: ^8.0.0

  postcss-js@4.0.1:
    resolution: {integrity: sha512-dDLF8pEO191hJMtlHFPRa8xsizHaM82MLfNkUHdUtVEV3tgTp5oj+8qbEqYM57SLfc74KSbw//4SeJma2LRVIw==}
    engines: {node: ^12 || ^14 || >= 16}
    peerDependencies:
      postcss: ^8.4.21

  postcss-load-config@4.0.2:
    resolution: {integrity: sha512-bSVhyJGL00wMVoPUzAVAnbEoWyqRxkjv64tUl427SKnPrENtq6hJwUojroMz2VB+Q1edmi4IfrAPpami5VVgMQ==}
    engines: {node: '>= 14'}
    peerDependencies:
      postcss: '>=8.0.9'
      ts-node: '>=9.0.0'
    peerDependenciesMeta:
      postcss:
        optional: true
      ts-node:
        optional: true

  postcss-nested@6.2.0:
    resolution: {integrity: sha512-HQbt28KulC5AJzG+cZtj9kvKB93CFCdLvog1WFLf1D+xmMvPGlBstkpTEZfK5+AN9hfJocyBFCNiqyS48bpgzQ==}
    engines: {node: '>=12.0'}
    peerDependencies:
      postcss: ^8.2.14

  postcss-selector-parser@6.0.10:
    resolution: {integrity: sha512-IQ7TZdoaqbT+LCpShg46jnZVlhWD2w6iQYAcYXfHARZ7X1t/UGhhceQDs5X0cGqKvYlHNOuv7Oa1xmb0oQuA3w==}
    engines: {node: '>=4'}

  postcss-selector-parser@6.1.2:
    resolution: {integrity: sha512-Q8qQfPiZ+THO/3ZrOrO0cJJKfpYCagtMUkXbnEfmgUjwXg6z/WBeOyS9APBBPCTSiDV+s4SwQGu8yFsiMRIudg==}
    engines: {node: '>=4'}

  postcss-value-parser@4.2.0:
    resolution: {integrity: sha512-1NNCs6uurfkVbeXG4S8JFT9t19m45ICnif8zWLd5oPSZ50QnwMfK+H3jv408d4jw/7Bttv5axS5IiHoLaVNHeQ==}

  postcss@8.4.31:
    resolution: {integrity: sha512-PS08Iboia9mts/2ygV3eLpY5ghnUcfLV/EXTOW1E2qYxJKGGBUtNjN76FYHnMs36RmARn41bC0AZmn+rR0OVpQ==}
    engines: {node: ^10 || ^12 || >=14}

  postcss@8.5.3:
    resolution: {integrity: sha512-dle9A3yYxlBSrt8Fu+IpjGT8SY8hN0mlaA6GY8t0P5PjIOZemULz/E2Bnm/2dcUOena75OTNkHI76uZBNUUq3A==}
    engines: {node: ^10 || ^12 || >=14}

  preact-render-to-string@5.2.6:
    resolution: {integrity: sha512-JyhErpYOvBV1hEPwIxc/fHWXPfnEGdRKxc8gFdAZ7XV4tlzyzG847XAyEZqoDnynP88akM4eaHcSOzNcLWFguw==}
    peerDependencies:
      preact: '>=10'

  preact@10.26.5:
    resolution: {integrity: sha512-fmpDkgfGU6JYux9teDWLhj9mKN55tyepwYbxHgQuIxbWQzgFg5vk7Mrrtfx7xRxq798ynkY4DDDxZr235Kk+4w==}

  pretty-format@3.8.0:
    resolution: {integrity: sha512-WuxUnVtlWL1OfZFQFuqvnvs6MiAGk9UNsBostyBOB0Is9wb5uRESevA6rnl/rkksXaGX3GzZhPup5d6Vp1nFew==}

  prismjs@1.27.0:
    resolution: {integrity: sha512-t13BGPUlFDR7wRB5kQDG4jjl7XeuH6jbJGt11JHPL96qwsEHNX2+68tFXqc1/k+/jALsbSWJKUOT/hcYAZ5LkA==}
    engines: {node: '>=6'}

  prismjs@1.30.0:
    resolution: {integrity: sha512-DEvV2ZF2r2/63V+tK8hQvrR2ZGn10srHbXviTlcv7Kpzw8jWiNTqbVgjO3IY8RxrrOUF8VPMQQFysYYYv0YZxw==}
    engines: {node: '>=6'}

  prompts@2.4.2:
    resolution: {integrity: sha512-NxNv/kLguCA7p3jE8oL2aEBsrJWgAakBpgmgK6lpPWV+WuOmY6r2/zbAVnP+T8bQlA0nzHXSJSJW0Hq7ylaD2Q==}
    engines: {node: '>= 6'}

  prop-types@15.8.1:
    resolution: {integrity: sha512-oj87CgZICdulUohogVAR7AjlC0327U4el4L6eAvOqCeudMDVU0NThNaV+b9Df4dXgSP1gXMTnPdhfe/2qDH5cg==}

  property-information@5.6.0:
    resolution: {integrity: sha512-YUHSPk+A30YPv+0Qf8i9Mbfe/C0hdPXk1s1jPVToV8pk8BQtpw10ct89Eo7OWkutrwqvT0eicAxlOg3dOAu8JA==}

  property-information@6.5.0:
    resolution: {integrity: sha512-PgTgs/BlvHxOu8QuEN7wi5A0OmXaBcHpmCSTehcs6Uuu9IkDIEo13Hy7n898RHfrQ49vKCoGeWZSaAK01nwVig==}

  property-information@7.0.0:
    resolution: {integrity: sha512-7D/qOz/+Y4X/rzSB6jKxKUsQnphO046ei8qxG59mtM3RG3DHgTK81HrxrmoDVINJb8NKT5ZsRbwHvQ6B68Iyhg==}

  proxy-from-env@1.1.0:
    resolution: {integrity: sha512-D+zkORCbA9f1tdWRK0RaCR3GPv50cMxcrz4X8k5LTSUD1Dkw47mKJEZQNunItRTkWwgtaUSo1RVFRIG9ZXiFYg==}

  queue-microtask@1.2.3:
    resolution: {integrity: sha512-NuaNSa6flKT5JaSYQzJok04JzTL1CA6aGhv5rfLW3PgqA+M2ChpZQnAC8h8i4ZFkBS8X5RqkDBHA7r4hej3K9A==}

  rc-util@5.44.4:
    resolution: {integrity: sha512-resueRJzmHG9Q6rI/DfK6Kdv9/Lfls05vzMs1Sk3M2P+3cJa+MakaZyWY8IPfehVuhPJFKrIY1IK4GqbiaiY5w==}
    peerDependencies:
      react: '>=16.9.0'
      react-dom: '>=16.9.0'

  react-clientside-effect@1.2.7:
    resolution: {integrity: sha512-gce9m0Pk/xYYMEojRI9bgvqQAkl6hm7ozQvqWPyQx+kULiatdHgkNM1QG4DQRx5N9BAzWSCJmt9mMV8/KsdgVg==}
    peerDependencies:
      react: ^16.8.0 || ^17.0.0 || ^18.0.0 || ^19.0.0 || ^19.0.0-rc

  react-dom@18.2.0:
    resolution: {integrity: sha512-6IMTriUmvsjHUjNtEDudZfuDQUoWXVxKHhlEGSk81n4YFS+r/Kl99wXiwlVXtPBtJenozv2P+hxDsw9eA7Xo6g==}
    peerDependencies:
      react: ^18.2.0

  react-fast-compare@3.2.2:
    resolution: {integrity: sha512-nsO+KSNgo1SbJqJEYRE9ERzo7YtYbou/OqjSQKxV7jcKox7+usiUVZOAC+XnDOABXggQTno0Y1CpVnuWEc1boQ==}

  react-focus-lock@2.13.6:
    resolution: {integrity: sha512-ehylFFWyYtBKXjAO9+3v8d0i+cnc1trGS0vlTGhzFW1vbFXVUTmR8s2tt/ZQG8x5hElg6rhENlLG1H3EZK0Llg==}
    peerDependencies:
      '@types/react': '*'
      react: ^16.8.0 || ^17.0.0 || ^18.0.0 || ^19.0.0 || ^19.0.0-rc
    peerDependenciesMeta:
      '@types/react':
        optional: true

  react-icons@5.5.0:
    resolution: {integrity: sha512-MEFcXdkP3dLo8uumGI5xN3lDFNsRtrjbOEKDLD7yv76v4wpnEq2Lt2qeHaQOr34I/wPN3s3+N08WkQ+CW37Xiw==}
    peerDependencies:
      react: '*'

  react-is@16.13.1:
    resolution: {integrity: sha512-24e6ynE2H+OKt4kqsOvNd8kBpV65zoxbA4BVsEOB3ARVWQki/DHzaUoC5KuON/BiccDaCCTZBuOcfZs70kR8bQ==}

  react-is@18.3.1:
    resolution: {integrity: sha512-/LLMVyas0ljjAtoYiPqYiL8VWXzUUdThrmU5+n20DZv+a+ClRoevUzw5JxU+Ieh5/c87ytoTBV9G1FiKfNJdmg==}

  react-markdown@10.1.0:
    resolution: {integrity: sha512-qKxVopLT/TyA6BX3Ue5NwabOsAzm0Q7kAPwq6L+wWDwisYs7R8vZ0nRXqq6rkueboxpkjvLGU9fWifiX/ZZFxQ==}
    peerDependencies:
      '@types/react': '>=18'
      react: '>=18'

  react-remove-scroll-bar@2.3.8:
    resolution: {integrity: sha512-9r+yi9+mgU33AKcj6IbT9oRCO78WriSj6t/cF8DWBZJ9aOGPOTEDvdUDz1FwKim7QXWwmHqtdHnRJfhAxEG46Q==}
    engines: {node: '>=10'}
    peerDependencies:
      '@types/react': '*'
      react: ^16.8.0 || ^17.0.0 || ^18.0.0 || ^19.0.0
    peerDependenciesMeta:
      '@types/react':
        optional: true

  react-remove-scroll@2.6.3:
    resolution: {integrity: sha512-pnAi91oOk8g8ABQKGF5/M9qxmmOPxaAnopyTHYfqYEwJhyFrbbBtHuSgtKEoH0jpcxx5o3hXqH1mNd9/Oi+8iQ==}
    engines: {node: '>=10'}
    peerDependencies:
      '@types/react': '*'
      react: ^16.8.0 || ^17.0.0 || ^18.0.0 || ^19.0.0 || ^19.0.0-rc
    peerDependenciesMeta:
      '@types/react':
        optional: true

  react-style-singleton@2.2.3:
    resolution: {integrity: sha512-b6jSvxvVnyptAiLjbkWLE/lOnR4lfTtDAl+eUC7RZy+QQWc6wRzIV2CE6xBuMmDxc2qIihtDCZD5NPOFl7fRBQ==}
    engines: {node: '>=10'}
    peerDependencies:
      '@types/react': '*'
      react: ^16.8.0 || ^17.0.0 || ^18.0.0 || ^19.0.0 || ^19.0.0-rc
    peerDependenciesMeta:
      '@types/react':
        optional: true

  react-syntax-highlighter@15.6.1:
    resolution: {integrity: sha512-OqJ2/vL7lEeV5zTJyG7kmARppUjiB9h9udl4qHQjjgEos66z00Ia0OckwYfRxCSFrW8RJIBnsBwQsHZbVPspqg==}
    peerDependencies:
      react: '>= 0.14.0'

  react@18.2.0:
    resolution: {integrity: sha512-/3IjMdb2L9QbBdWiW5e3P2/npwMBaU9mHCSCUzNln0ZCYbcfTsGbTJrU/kGemdH2IWmB2ioZ+zkxtmq6g09fGQ==}
    engines: {node: '>=0.10.0'}

  read-cache@1.0.0:
    resolution: {integrity: sha512-Owdv/Ft7IjOgm/i0xvNDZ1LrRANRfew4b2prF3OWMQLxLfu3bS8FVhCsrSCMK4lR56Y9ya+AThoTpDCTxCmpRA==}

  readable-stream@3.6.2:
    resolution: {integrity: sha512-9u/sniCrY3D5WdsERHzHE4G2YCXqoG5FTHUiCC4SIbr6XcLZBY05ya9EKjYek9O5xOAwjGq+1JdGBAS7Q9ScoA==}
    engines: {node: '>= 6'}

  readdirp@3.6.0:
    resolution: {integrity: sha512-hOS089on8RduqdbhvQ5Z37A0ESjsqz6qnRcffsMU3495FuTdqSm+7bhJ29JvIOsBDEEnan5DPu9t3To9VRlMzA==}
    engines: {node: '>=8.10.0'}

  redis-errors@1.2.0:
    resolution: {integrity: sha512-1qny3OExCf0UvUV/5wpYKf2YwPcOqXzkwKKSmKHiE6ZMQs5heeE/c8eXK+PNllPvmjgAbfnsbpkGZWy8cBpn9w==}
    engines: {node: '>=4'}

  redis-parser@3.0.0:
    resolution: {integrity: sha512-DJnGAeenTdpMEH6uAJRK/uiyEIH9WVsUmoLwzudwGJUwZPp80PDBWPHXSAGNPwNvIXAbe7MSUB1zQFugFml66A==}
    engines: {node: '>=4'}

  reflect-metadata@0.1.14:
    resolution: {integrity: sha512-ZhYeb6nRaXCfhnndflDK8qI6ZQ/YcWZCISRAWICW9XYqMUwjZM9Z0DveWX/ABN01oxSHwVxKQmxeYZSsm0jh5A==}

  refractor@3.6.0:
    resolution: {integrity: sha512-MY9W41IOWxxk31o+YvFCNyNzdkc9M20NoZK5vq6jkv4I/uh2zkWcfudj0Q1fovjUQJrNewS9NMzeTtqPf+n5EA==}

  rehype-highlight@7.0.2:
    resolution: {integrity: sha512-k158pK7wdC2qL3M5NcZROZ2tR/l7zOzjxXd5VGdcfIyoijjQqpHd3JKtYSBDpDZ38UI2WJWuFAtkMDxmx5kstA==}

  rehype-raw@7.0.0:
    resolution: {integrity: sha512-/aE8hCfKlQeA8LmyeyQvQF3eBiLRGNlfBJEvWH7ivp9sBqs7TNqBL5X3v157rM4IFETqDnIOO+z5M/biZbo9Ww==}

  rehype-sanitize@6.0.0:
    resolution: {integrity: sha512-CsnhKNsyI8Tub6L4sm5ZFsme4puGfc6pYylvXo1AeqaGbjOYyzNv3qZPwvs0oMJ39eryyeOdmxwUIo94IpEhqg==}

  remark-breaks@4.0.0:
    resolution: {integrity: sha512-IjEjJOkH4FuJvHZVIW0QCDWxcG96kCq7An/KVH2NfJe6rKZU2AsHeB3OEjPNRxi4QC34Xdx7I2KGYn6IpT7gxQ==}

  remark-gfm@4.0.1:
    resolution: {integrity: sha512-1quofZ2RQ9EWdeN34S79+KExV1764+wCUGop5CPL1WGdD0ocPpu91lzPGbwWMECpEpd42kJGQwzRfyov9j4yNg==}

  remark-parse@11.0.0:
    resolution: {integrity: sha512-FCxlKLNGknS5ba/1lmpYijMUzX2esxW5xQqjWxw2eHFfS2MSdaHVINFmhjo+qN1WhZhNimq0dZATN9pH0IDrpA==}

  remark-rehype@11.1.2:
    resolution: {integrity: sha512-Dh7l57ianaEoIpzbp0PC9UKAdCSVklD8E5Rpw7ETfbTl3FqcOOgq5q2LVDhgGCkaBv7p24JXikPdvhhmHvKMsw==}

  remark-stringify@11.0.0:
    resolution: {integrity: sha512-1OSmLd3awB/t8qdoEOMazZkNsfVTeY4fTsgzcQFdXNq8ToTN4ZGwrMnlda4K6smTFKD+GRV6O48i6Z4iKgPPpw==}

  require-directory@2.1.1:
    resolution: {integrity: sha512-fGxEI7+wsG9xrvdjsrlmL22OMTTiHRwAMroiEeMgq8gzoLC/PQr7RsRDSTLUg/bZAZtF+TVIkHc6/4RIKrui+Q==}
    engines: {node: '>=0.10.0'}

  resolve-from@4.0.0:
    resolution: {integrity: sha512-pb/MYmXstAkysRFx8piNI1tGFNQIFA3vkE3Gq4EuA1dF6gHp/+vgZqsCGJapvy8N3Q+4o7FwvquPJcnZ7RYy4g==}
    engines: {node: '>=4'}

  resolve@1.22.10:
    resolution: {integrity: sha512-NPRy+/ncIMeDlTAsuqwKIiferiawhefFJtkNSW0qZJEqMEb+qBt/77B/jGeeek+F0uOeN05CDa6HXbbIgtVX4w==}
    engines: {node: '>= 0.4'}
    hasBin: true

  restore-cursor@4.0.0:
    resolution: {integrity: sha512-I9fPXU9geO9bHOt9pHHOhOkYerIMsmVaWB0rA2AI9ERh/+x/i7MV5HKBNrg+ljO5eoPVgCcnFuRjJ9uH6I/3eg==}
    engines: {node: ^12.20.0 || ^14.13.1 || >=16.0.0}

  reusify@1.1.0:
    resolution: {integrity: sha512-g6QUff04oZpHs0eG5p83rFLhHeV00ug/Yf9nZM6fLeUrPguBTkTQOdpAWWspMh55TZfVQDPaN3NQJfbVRAxdIw==}
    engines: {iojs: '>=1.0.0', node: '>=0.10.0'}

  run-parallel@1.2.0:
    resolution: {integrity: sha512-5l4VyZR86LZ/lDxZTR6jqL8AFE2S0IFLMP26AbjsLVADxHdhB/c0GUsH+y39UfCi3dzz8OlQuPmnaJOMoDHQBA==}

  safe-buffer@5.2.1:
    resolution: {integrity: sha512-rp3So07KcdmmKbGvgaNxQSJr7bGVSVk5S9Eq1F+ppbRo70+YeaDxkw5Dd8NPN+GD6bjnYm2VuPuCXmpuYvmCXQ==}

  sax@1.4.1:
    resolution: {integrity: sha512-+aWOz7yVScEGoKNd4PA10LZ8sk0A/z5+nXQG5giUO5rprX9jgYsTdov9qCchZiPIZezbZH+jRut8nPodFAX4Jg==}

  scheduler@0.23.2:
    resolution: {integrity: sha512-UOShsPwz7NrMUqhR6t0hWjFduvOzbtv7toDH1/hIrfRNIDBnnBWd0CwJTGvTpngVlmwGCdP9/Zl/tVrDqcuYzQ==}

  semver@7.7.1:
    resolution: {integrity: sha512-hlq8tAfn0m/61p4BVRcPzIGr6LKiMwo4VM6dGi6pt4qcRkmNzTcWq6eCEjEh+qXjkMDvPlOFFSGwQjoEa6gyMA==}
    engines: {node: '>=10'}
    hasBin: true

  sha.js@2.4.11:
    resolution: {integrity: sha512-QMEp5B7cftE7APOjk5Y6xgrbWu+WkLVQwk8JNjZ8nKRciZaByEW6MubieAiToS7+dwvrjGhH8jRXz3MVd0AYqQ==}
    hasBin: true

  sharp@0.33.5:
    resolution: {integrity: sha512-haPVm1EkS9pgvHrQ/F3Xy+hgcuMV0Wm9vfIBSiwZ05k+xgb0PkBQpGsAA/oWdDobNaZTH5ppvHtzCFbnSEwHVw==}
    engines: {node: ^18.17.0 || ^20.3.0 || >=21.0.0}

  shebang-command@2.0.0:
    resolution: {integrity: sha512-kHxr2zZpYtdmrN1qDjrrX/Z1rR1kG8Dx+gkpK1G4eXmvXswmcE1hTWBWYUzlraYw1/yZp6YuDY77YtvbN0dmDA==}
    engines: {node: '>=8'}

  shebang-regex@3.0.0:
    resolution: {integrity: sha512-7++dFhtcx3353uBaq8DDR4NuxBetBzC7ZQOhmTQInHEd6bSrXdiEyzCvG07Z44UYdLShWUyXt5M/yhz8ekcb1A==}
    engines: {node: '>=8'}

  signal-exit@3.0.7:
    resolution: {integrity: sha512-wnD2ZE+l+SPC/uoS0vXeE9L1+0wuaMqKlfz9AMUo38JsyLSBWSFcHR1Rri62LZc12vLr1gb3jl7iwQhgwpAbGQ==}

  signal-exit@4.1.0:
    resolution: {integrity: sha512-bzyZ1e88w9O1iNJbKnOlvYTrWPDl46O1bG0D3XInv+9tkPrxrN8jUUTiFlDkkmKWgn1M6CfIA13SuGqOa9Korw==}
    engines: {node: '>=14'}

  simple-swizzle@0.2.2:
    resolution: {integrity: sha512-JA//kQgZtbuY83m+xT+tXJkmJncGMTFT+C+g2h2R9uxkYIrE2yy9sgmcLhCnw57/WSD+Eh3J97FPEDFnbXnDUg==}

  sisteransi@1.0.5:
    resolution: {integrity: sha512-bLGGlR1QxBcynn2d5YmDX4MGjlZvy2MRBDRNHLJ8VI6l6+9FUiyTFNJ0IveOSP0bcXgVDPRcfGqA0pjaqUpfVg==}

  source-map-js@1.2.1:
    resolution: {integrity: sha512-UXWMKhLOwVKb728IUtQPXxfYU+usdybtUrK/8uGE8CQMvrhOpwvzDBwj0QhSL7MQc7vIsISBG8VQ8+IDQxpfQA==}
    engines: {node: '>=0.10.0'}

  source-map@0.5.7:
    resolution: {integrity: sha512-LbrmJOMUSdEVxIKvdcJzQC+nQhe8FUZQTXQy6+I75skNgn3OoQ0DZA8YnFa7gp8tqtL3KPf1kmo0R5DoApeSGQ==}
    engines: {node: '>=0.10.0'}

  space-separated-tokens@1.1.5:
    resolution: {integrity: sha512-q/JSVd1Lptzhf5bkYm4ob4iWPjx0KiRe3sRFBNrVqbJkFaBm5vbbowy1mymoPNLRa52+oadOhJ+K49wsSeSjTA==}

  space-separated-tokens@2.0.2:
    resolution: {integrity: sha512-PEGlAwrG8yXGXRjW32fGbg66JAlOAwbObuqVoJpv/mRgoWDQfgH1wDPvtzWyUSNAXBGSk8h755YDbbcEy3SH2Q==}

  standard-as-callback@2.1.0:
    resolution: {integrity: sha512-qoRRSyROncaz1z0mvYqIE4lCd9p2R90i6GxW3uZv5ucSu8tU7B5HXUP1gG8pVZsYNVaXjk8ClXHPttLyxAL48A==}

  stdin-discarder@0.1.0:
    resolution: {integrity: sha512-xhV7w8S+bUwlPTb4bAOUQhv8/cSS5offJuX8GQGq32ONF0ZtDWKfkdomM3HMRA+LhX6um/FZ0COqlwsjD53LeQ==}
    engines: {node: ^12.20.0 || ^14.13.1 || >=16.0.0}

  streamsearch@1.1.0:
    resolution: {integrity: sha512-Mcc5wHehp9aXz1ax6bZUyY5afg9u2rv5cqQI3mRrYkGC8rW2hM02jWuwjtL++LS5qinSyhj2QfLyNsuc+VsExg==}
    engines: {node: '>=10.0.0'}

  string-width@4.2.3:
    resolution: {integrity: sha512-wKyQRQpjJ0sIp62ErSZdGsjMJWsap5oRNihHhu6G7JVO/9jIB6UyevL+tXuOqrng8j/cxKTWyWUwvSTriiZz/g==}
    engines: {node: '>=8'}

  string-width@5.1.2:
    resolution: {integrity: sha512-HnLOCR3vjcY8beoNLtcjZ5/nxn2afmME6lhrDrebokqMap+XbeW8n9TXpPDOqdGK5qcI3oT0GKTW6wC7EMiVqA==}
    engines: {node: '>=12'}

  string_decoder@1.3.0:
    resolution: {integrity: sha512-hkRX8U1WjJFd8LsDJ2yQ/wWWxaopEsABU1XfkM8A+j0+85JAGppt16cr1Whg6KIbb4okU6Mql6BOj+uup/wKeA==}

  stringify-entities@4.0.4:
    resolution: {integrity: sha512-IwfBptatlO+QCJUo19AqvrPNqlVMpW9YEL2LIVY+Rpv2qsjCGxaDLNRgeGsQWJhfItebuJhsGSLjaBbNSQ+ieg==}

  strip-ansi@6.0.1:
    resolution: {integrity: sha512-Y38VPSHcqkFrCpFnQ9vuSXmquuv5oXOKpGeT6aGrr3o3Gc9AlVa6JBfUSOCnbxGGZF+/0ooI7KrPuUSztUdU5A==}
    engines: {node: '>=8'}

  strip-ansi@7.1.0:
    resolution: {integrity: sha512-iq6eVVI64nQQTRYq2KtEg2d2uU7LElhTJwsH4YzIHZshxlgZms/wIc4VoDQTlG/IvVIrBKG06CrZnp0qv7hkcQ==}
    engines: {node: '>=12'}

  strip-final-newline@3.0.0:
    resolution: {integrity: sha512-dOESqjYr96iWYylGObzd39EuNTa5VJxyvVAEm5Jnh7KGo75V43Hk1odPQkNDyXNmUR6k+gEiDVXnjB8HJ3crXw==}
    engines: {node: '>=12'}

  style-to-js@1.1.16:
    resolution: {integrity: sha512-/Q6ld50hKYPH3d/r6nr117TZkHR0w0kGGIVfpG9N6D8NymRPM9RqCUv4pRpJ62E5DqOYx2AFpbZMyCPnjQCnOw==}

  style-to-object@1.0.8:
    resolution: {integrity: sha512-xT47I/Eo0rwJmaXC4oilDGDWLohVhR6o/xAQcPQN8q6QBuZVL8qMYL85kLmST5cPjAorwvqIA4qXTRQoYHaL6g==}

  style-value-types@5.1.2:
    resolution: {integrity: sha512-Vs9fNreYF9j6W2VvuDTP7kepALi7sk0xtk2Tu8Yxi9UoajJdEVpNpCov0HsLTqXvNGKX+Uv09pkozVITi1jf3Q==}

  styled-jsx@5.1.6:
    resolution: {integrity: sha512-qSVyDTeMotdvQYoHWLNGwRFJHC+i+ZvdBRYosOFgC+Wg1vx4frN2/RG/NA7SYqqvKNLf39P2LSRA2pu6n0XYZA==}
    engines: {node: '>= 12.0.0'}
    peerDependencies:
      '@babel/core': '*'
      babel-plugin-macros: '*'
      react: '>= 16.8.0 || 17.x.x || ^18.0.0-0 || ^19.0.0-0'
    peerDependenciesMeta:
      '@babel/core':
        optional: true
      babel-plugin-macros:
        optional: true

  stylis@4.2.0:
    resolution: {integrity: sha512-Orov6g6BB1sDfYgzWfTHDOxamtX1bE/zo104Dh9e6fqJ3PooipYyfJ0pUmrZO2wAvO8YbEyeFrkV91XTsGMSrw==}

  sucrase@3.35.0:
    resolution: {integrity: sha512-8EbVDiu9iN/nESwxeSxDKe0dunta1GOlHufmSSXxMD2z2/tMZpDMpvXQGsc+ajGo8y2uYUmixaSRUc/QPoQ0GA==}
    engines: {node: '>=16 || 14 >=14.17'}
    hasBin: true

  supports-color@7.2.0:
    resolution: {integrity: sha512-qpCAvRl9stuOHveKsn7HncJRvv501qIacKzQlO/+Lwxc9+0q2wLyv4Dfvt80/DPn2pqOBsJdDiogXGR9+OvwRw==}
    engines: {node: '>=8'}

  supports-preserve-symlinks-flag@1.0.0:
    resolution: {integrity: sha512-ot0WnXS9fgdkgIcePe6RHNk1WA8+muPa6cSjeR3V8K27q9BB1rTE3R1p7Hv0z1ZyAc8s6Vvv8DIyWf681MAt0w==}
    engines: {node: '>= 0.4'}

  tailwind-merge@3.2.0:
    resolution: {integrity: sha512-FQT/OVqCD+7edmmJpsgCsY820RTD5AkBryuG5IUqR5YQZSdj5xlH5nLgH7YPths7WsLPSpSBNneJdM8aS8aeFA==}

  tailwindcss-animate@1.0.7:
    resolution: {integrity: sha512-bl6mpH3T7I3UFxuvDEXLxy/VuFxBk5bbzplh7tXI68mwMokNYd1t9qPBHlnyTwfa4JGC4zP516I1hYYtQ/vspA==}
    peerDependencies:
      tailwindcss: '>=3.0.0 || insiders'

  tailwindcss@3.4.17:
    resolution: {integrity: sha512-w33E2aCvSDP0tW9RZuNXadXlkHXqFzSkQew/aIa2i/Sj8fThxwovwlXHSPXTbAHwEIhBFXAedUhP2tueAKP8Og==}
    engines: {node: '>=14.0.0'}
    hasBin: true

  thenify-all@1.6.0:
    resolution: {integrity: sha512-RNxQH/qI8/t3thXJDwcstUO4zeqo64+Uy/+sNVRBx4Xn2OX+OZ9oP+iJnNFqplFra2ZUVeKCSa2oVWi3T4uVmA==}
    engines: {node: '>=0.8'}

  thenify@3.3.1:
    resolution: {integrity: sha512-RVZSIV5IG10Hk3enotrhvz0T9em6cyHBLkH/YAZuKqd8hRkKhSfCGIcP2KUY0EPxndzANBmNllzWPwak+bheSw==}

  tiny-invariant@1.3.3:
    resolution: {integrity: sha512-+FbBPE1o9QAYvviau/qC5SE3caw21q3xkvWKBtja5vgqOWIHHJ3ioaq1VPfn/Szqctz2bU/oYeKd9/z5BL+PVg==}

  to-regex-range@5.0.1:
    resolution: {integrity: sha512-65P7iz6X5yEr1cwcgvQxbbIw7Uk3gOy5dIdtZ4rDveLqhrdJP+Li/Hx6tyK0NEb+2GCyneCMJiGqrADCSNk8sQ==}
    engines: {node: '>=8.0'}

  toggle-selection@1.0.6:
    resolution: {integrity: sha512-BiZS+C1OS8g/q2RRbJmy59xpyghNBqrr6k5L/uKBGRsTfxmu3ffiRnd8mlGPUVayg8pvfi5urfnu8TU7DVOkLQ==}

  trim-lines@3.0.1:
    resolution: {integrity: sha512-kRj8B+YHZCc9kQYdWfJB2/oUl9rA99qbowYYBtr4ui4mZyAQ2JpvVBd/6U2YloATfqBhBTSMhTpgBHtU0Mf3Rg==}

  trough@2.2.0:
    resolution: {integrity: sha512-tmMpK00BjZiUyVyvrBK7knerNgmgvcV/KLVyuma/SC+TQN167GrMRciANTz09+k3zW8L8t60jWO1GpfkZdjTaw==}

  ts-interface-checker@0.1.13:
    resolution: {integrity: sha512-Y/arvbn+rrz3JCKl9C4kVNfTfSm2/mEp5FSz5EsZSANGPSlQrpRI5M4PKF+mJnE52jOO90PnPSc3Ur3bTQw0gA==}

  tslib@2.4.0:
    resolution: {integrity: sha512-d6xOpEDfsi2CZVlPQzGeux8XMwLT9hssAsaPYExaQMuYskwb+x1x7J371tWlbBdWHroy99KnVB6qIkUbs5X3UQ==}

  tslib@2.8.1:
    resolution: {integrity: sha512-oJFu94HQb+KVduSUQL7wnpmqnfmLsOA/nAh6b6EH0wCEoK0/mPeXU6c3wKDV83MkOuHPRHtSXKKU99IBazS/2w==}

  typeorm@0.3.7:
    resolution: {integrity: sha512-MsPJeP6Zuwfe64c++l80+VRqpGEGxf0CkztIEnehQ+CMmQPSHjOnFbFxwBuZ2jiLqZTjLk2ZqQdVF0RmvxNF3Q==}
    engines: {node: '>= 12.9.0'}
    hasBin: true
    peerDependencies:
      '@google-cloud/spanner': ^5.18.0
      '@sap/hana-client': ^2.12.25
      better-sqlite3: ^7.1.2
      hdb-pool: ^0.1.6
      ioredis: ^5.0.4
      mongodb: ^3.6.0
      mssql: ^7.3.0
      mysql2: ^2.2.5
      oracledb: ^5.1.0
      pg: ^8.5.1
      pg-native: ^3.0.0
      pg-query-stream: ^4.0.0
      redis: ^3.1.1 || ^4.0.0
      sql.js: ^1.4.0
      sqlite3: ^5.0.3
      ts-node: ^10.7.0
      typeorm-aurora-data-api-driver: ^2.0.0
    peerDependenciesMeta:
      '@google-cloud/spanner':
        optional: true
      '@sap/hana-client':
        optional: true
      better-sqlite3:
        optional: true
      hdb-pool:
        optional: true
      ioredis:
        optional: true
      mongodb:
        optional: true
      mssql:
        optional: true
      mysql2:
        optional: true
      oracledb:
        optional: true
      pg:
        optional: true
      pg-native:
        optional: true
      pg-query-stream:
        optional: true
      redis:
        optional: true
      sql.js:
        optional: true
      sqlite3:
        optional: true
      ts-node:
        optional: true
      typeorm-aurora-data-api-driver:
        optional: true

  typescript@5.8.3:
    resolution: {integrity: sha512-p1diW6TqL9L07nNxvRMM7hMMw4c5XOo/1ibL4aAIGmSAt9slTE1Xgw5KWuof2uTOvCg9BY7ZRi+GaF+7sfgPeQ==}
    engines: {node: '>=14.17'}
    hasBin: true

  undici-types@6.19.8:
    resolution: {integrity: sha512-ve2KP6f/JnbPBFyobGHuerC9g1FYGn/F8n1LWTwNxCEzd6IfqTwUQcNXgEtmmQ6DlRrC1hrSrBnCZPokRrDHjw==}

  unified@11.0.5:
    resolution: {integrity: sha512-xKvGhPWw3k84Qjh8bI3ZeJjqnyadK+GEFtazSfZv/rKeTkTjOJho6mFqh2SM96iIcZokxiOpg78GazTSg8+KHA==}

  unist-util-find-after@5.0.0:
    resolution: {integrity: sha512-amQa0Ep2m6hE2g72AugUItjbuM8X8cGQnFoHk0pGfrFeT9GZhzN5SW8nRsiGKK7Aif4CrACPENkA6P/Lw6fHGQ==}

  unist-util-is@6.0.0:
    resolution: {integrity: sha512-2qCTHimwdxLfz+YzdGfkqNlH0tLi9xjTnHddPmJwtIG9MGsdbutfTc4P+haPD7l7Cjxf/WZj+we5qfVPvvxfYw==}

  unist-util-position@5.0.0:
    resolution: {integrity: sha512-fucsC7HjXvkB5R3kTCO7kUjRdrS0BJt3M/FPxmHMBOm8JQi2BsHAHFsy27E0EolP8rp0NzXsJ+jNPyDWvOJZPA==}

  unist-util-stringify-position@4.0.0:
    resolution: {integrity: sha512-0ASV06AAoKCDkS2+xw5RXJywruurpbC4JZSm7nr7MOt1ojAzvyyaO+UxZf18j8FCF6kmzCZKcAgN/yu2gm2XgQ==}

  unist-util-visit-parents@6.0.1:
    resolution: {integrity: sha512-L/PqWzfTP9lzzEa6CKs0k2nARxTdZduw3zyh8d2NVBnsyvHjSX4TWse388YrrQKbvI8w20fGjGlhgT96WwKykw==}

  unist-util-visit@5.0.0:
    resolution: {integrity: sha512-MR04uvD+07cwl/yhVuVWAtw+3GOR/knlL55Nd/wAdblk27GCVt3lqpTivy/tkJcZoNPzTwS1Y+KMojlLDhoTzg==}

  universalify@2.0.1:
    resolution: {integrity: sha512-gptHNQghINnc/vTGIk0SOFGFNXw7JVrlRUtConJRlvaw6DuX0wO5Jeko9sWrMBhh+PsYAZ7oXAiOnf/UKogyiw==}
    engines: {node: '>= 10.0.0'}

  update-browserslist-db@1.1.3:
    resolution: {integrity: sha512-UxhIZQ+QInVdunkDAaiazvvT/+fXL5Osr0JZlJulepYu6Jd7qJtDZjlur0emRlT71EN3ScPoE7gvsuIKKNavKw==}
    hasBin: true
    peerDependencies:
      browserslist: '>= 4.21.0'

  use-callback-ref@1.3.3:
    resolution: {integrity: sha512-jQL3lRnocaFtu3V00JToYz/4QkNWswxijDaCVNZRiRTO3HQDLsdu1ZtmIUvV4yPp+rvWm5j0y0TG/S61cuijTg==}
    engines: {node: '>=10'}
    peerDependencies:
      '@types/react': '*'
      react: ^16.8.0 || ^17.0.0 || ^18.0.0 || ^19.0.0 || ^19.0.0-rc
    peerDependenciesMeta:
      '@types/react':
        optional: true

  use-sidecar@1.1.3:
    resolution: {integrity: sha512-Fedw0aZvkhynoPYlA5WXrMCAMm+nSWdZt6lzJQ7Ok8S6Q+VsHmHpRWndVRJ8Be0ZbkfPc5LRYH+5XrzXcEeLRQ==}
    engines: {node: '>=10'}
    peerDependencies:
      '@types/react': '*'
      react: ^16.8.0 || ^17.0.0 || ^18.0.0 || ^19.0.0 || ^19.0.0-rc
    peerDependenciesMeta:
      '@types/react':
        optional: true

  util-deprecate@1.0.2:
    resolution: {integrity: sha512-EPD5q1uXyFxJpCrLnCc1nHnq3gOa6DZBocAIiI2TaSCA7VCJ1UJDMagCzIkXNsUYfD1daK//LTEQ8xiIbrHtcw==}

  uuid@11.1.0:
    resolution: {integrity: sha512-0/A9rDy9P7cJ+8w1c9WD9V//9Wj15Ce2MPz8Ri6032usz+NfePxx5AcN3bN+r6ZL6jEo066/yNYB3tn4pQEx+A==}
    hasBin: true

  uuid@8.3.2:
    resolution: {integrity: sha512-+NYs2QeMWy+GWFOEm9xnn6HCDp0l7QBD7ml8zLUmJ+93Q5NF0NocErnwkTkXVFNiX3/fpC6afS8Dhb/gz7R7eg==}
    hasBin: true

  vfile-location@5.0.3:
    resolution: {integrity: sha512-5yXvWDEgqeiYiBe1lbxYF7UMAIm/IcopxMHrMQDq3nvKcjPKIhZklUKL+AE7J7uApI4kwe2snsK+eI6UTj9EHg==}

  vfile-message@4.0.2:
    resolution: {integrity: sha512-jRDZ1IMLttGj41KcZvlrYAaI3CfqpLpfpf+Mfig13viT6NKvRzWZ+lXz0Y5D60w6uJIBAOGq9mSHf0gktF0duw==}

  vfile@6.0.3:
    resolution: {integrity: sha512-KzIbH/9tXat2u30jf+smMwFCsno4wHVdNmzFyL+T/L3UGqqk6JKfVqOFOZEpZSHADH1k40ab6NUIXZq422ov3Q==}

  wcwidth@1.0.1:
    resolution: {integrity: sha512-XHPEwS0q6TaxcvG85+8EYkbiCux2XtWG2mkc47Ng2A77BQu9+DqIOJldST4HgPkuea7dvKSj5VgX3P1d4rW8Tg==}

  web-namespaces@2.0.1:
    resolution: {integrity: sha512-bKr1DkiNa2krS7qxNtdrtHAmzuYGFQLiQ13TsorsdT6ULTkPLKuu5+GsFpDlg6JFjUTwX2DyhMPG2be8uPrqsQ==}

  web-streams-polyfill@3.3.3:
    resolution: {integrity: sha512-d2JWLCivmZYTSIoge9MsgFCZrt571BikcWGYkjC1khllbTeDlGqZ2D8vD8E/lJa8WGWbb7Plm8/XJYV7IJHZZw==}
    engines: {node: '>= 8'}

  which@2.0.2:
    resolution: {integrity: sha512-BLI3Tl1TW3Pvl70l3yq3Y64i+awpwXqsGBYWkkqMtnbXgrMD+yj7rhW0kuEDxzJaYXGjEW5ogapKNMEKNMjibA==}
    engines: {node: '>= 8'}
    hasBin: true

  wrap-ansi@7.0.0:
    resolution: {integrity: sha512-YVGIj2kamLSTxw6NsZjoBxfSwsn0ycdesmc4p+Q21c5zPuZ1pl+NfxVdxPtdHvmNVOQ6XSYG4AUtyt/Fi7D16Q==}
    engines: {node: '>=10'}

  wrap-ansi@8.1.0:
    resolution: {integrity: sha512-si7QWI6zUMq56bESFvagtmzMdGOtoxfR+Sez11Mobfc7tm+VkUckk9bW2UeffTGVUbOksxmSw0AA2gs8g71NCQ==}
    engines: {node: '>=12'}

  wrappy@1.0.2:
    resolution: {integrity: sha512-l4Sp/DRseor9wL6EvV2+TuQn63dMkPjZ/sp9XkghTEbV9KlPS1xUsZ3u7/IQO4wxtcFB4bgpQPRcR3QCvezPcQ==}

  xml2js@0.4.23:
    resolution: {integrity: sha512-ySPiMjM0+pLDftHgXY4By0uswI3SPKLDw/i3UXbnO8M/p28zqexCUoPmQFrYD+/1BzhGJSs2i1ERWKJAtiLrug==}
    engines: {node: '>=4.0.0'}

  xmlbuilder@11.0.1:
    resolution: {integrity: sha512-fDlsI/kFEx7gLvbecc0/ohLG50fugQp8ryHzMTuW9vSa1GJ0XYWKnhsUx7oie3G98+r56aTQIUB4kht42R3JvA==}
    engines: {node: '>=4.0'}

  xtend@4.0.2:
    resolution: {integrity: sha512-LKYU1iAXJXUgAXn9URjiu+MWhyUXHsvfp7mcuYm9dSUKK0/CjtrUwFAxD82/mCWbtLsGjFIad0wIsod4zrTAEQ==}
    engines: {node: '>=0.4'}

  y18n@5.0.8:
    resolution: {integrity: sha512-0pfFzegeDWJHJIAmTLRP2DwHjdF5s7jo9tuztdQxAhINCdvS+3nGINqPd00AphqJR/0LhANUS6/+7SCb98YOfA==}
    engines: {node: '>=10'}

  yallist@4.0.0:
    resolution: {integrity: sha512-3wdGidZyq5PB084XLES5TpOSRA3wjXAlIWMhum2kRcv/41Sn2emQ0dycQW4uZXLejwKvg6EsvbdlVL+FYEct7A==}

  yaml@1.10.2:
    resolution: {integrity: sha512-r3vXyErRCYJ7wg28yvBY5VSoAF8ZvlcW9/BwUzEtUsjvX/DKs24dIkuwjtuprwJJHsbyUbLApepYTR1BN4uHrg==}
    engines: {node: '>= 6'}

  yaml@2.7.1:
    resolution: {integrity: sha512-10ULxpnOCQXxJvBgxsn9ptjq6uviG/htZKk9veJGhlqn3w/DxQ631zFF+nlQXLwmImeS5amR2dl2U8sg6U9jsQ==}
    engines: {node: '>= 14'}
    hasBin: true

  yargs-parser@20.2.9:
    resolution: {integrity: sha512-y11nGElTIV+CT3Zv9t7VKl+Q3hTQoT9a1Qzezhhl6Rp21gJ/IVTW7Z3y9EWXhuUBC2Shnf+DX0antecpAwSP8w==}
    engines: {node: '>=10'}

  yargs-parser@21.1.1:
    resolution: {integrity: sha512-tVpsJW7DdjecAiFpbIB1e3qxIQsE6NoPc5/eTdrbbIC4h0LVsWhnoa3g+m2HclBIujHzsxZ4VJVA+GUuc2/LBw==}
    engines: {node: '>=12'}

  yargs@16.2.0:
    resolution: {integrity: sha512-D1mvvtDG0L5ft/jGWkLpG1+m0eQxOfaBvTNELraWj22wSVUMWxZUvYgJYcKh6jGGIkJFhH4IZPQhR4TKpc8mBw==}
    engines: {node: '>=10'}

  yargs@17.7.2:
    resolution: {integrity: sha512-7dSzzRQ++CKnNI/krKnYRV7JKKPUXMEh61soaHKg9mrWEhzFWhFnxPxGl+69cD1Ou63C13NUPCnmIcrvqCuM6w==}
    engines: {node: '>=12'}

  zod@3.24.4:
    resolution: {integrity: sha512-OdqJE9UDRPwWsrHjLN2F8bPxvwJBK22EHLWtanu0LSYr5YqzsaaW3RMgmjwr8Rypg5k+meEJdSPXJZXE/yqOMg==}

  zwitch@2.0.4:
    resolution: {integrity: sha512-bXE4cR/kVZhKZX/RjPEflHaKVhUVl85noU3v6b8apfQEc1x4A+zBxjZ4lN8LqGd6WZ3dl98pY4o717VFmoPp+A==}

snapshots:

  '@alloc/quick-lru@5.2.0': {}

  '@ant-design/colors@7.2.0':
    dependencies:
      '@ant-design/fast-color': 2.0.6

  '@ant-design/fast-color@2.0.6':
    dependencies:
      '@babel/runtime': 7.27.1

  '@ant-design/icons-svg@4.4.2': {}

  '@ant-design/icons@5.6.1(react-dom@18.2.0(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@ant-design/colors': 7.2.0
      '@ant-design/icons-svg': 4.4.2
      '@babel/runtime': 7.27.1
      classnames: 2.5.1
      rc-util: 5.44.4(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)

  '@babel/code-frame@7.27.1':
    dependencies:
      '@babel/helper-validator-identifier': 7.27.1
      js-tokens: 4.0.0
      picocolors: 1.1.1

  '@babel/generator@7.27.1':
    dependencies:
      '@babel/parser': 7.27.1
      '@babel/types': 7.27.1
      '@jridgewell/gen-mapping': 0.3.8
      '@jridgewell/trace-mapping': 0.3.25
      jsesc: 3.1.0

  '@babel/helper-module-imports@7.27.1':
    dependencies:
      '@babel/traverse': 7.27.1
      '@babel/types': 7.27.1
    transitivePeerDependencies:
      - supports-color

  '@babel/helper-string-parser@7.27.1': {}

  '@babel/helper-validator-identifier@7.27.1': {}

  '@babel/parser@7.27.1':
    dependencies:
      '@babel/types': 7.27.1

  '@babel/runtime@7.27.1': {}

  '@babel/template@7.27.1':
    dependencies:
      '@babel/code-frame': 7.27.1
      '@babel/parser': 7.27.1
      '@babel/types': 7.27.1

  '@babel/traverse@7.27.1':
    dependencies:
      '@babel/code-frame': 7.27.1
      '@babel/generator': 7.27.1
      '@babel/parser': 7.27.1
      '@babel/template': 7.27.1
      '@babel/types': 7.27.1
      debug: 4.4.0
      globals: 11.12.0
    transitivePeerDependencies:
      - supports-color

  '@babel/types@7.27.1':
    dependencies:
      '@babel/helper-string-parser': 7.27.1
      '@babel/helper-validator-identifier': 7.27.1

  '@chakra-ui/accordion@2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/descendant': 3.1.0(react@18.2.0)
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-controllable-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/transition': 2.1.0(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/alert@2.2.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/spinner': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/anatomy@2.2.1': {}

  '@chakra-ui/avatar@2.3.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/image': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-children-utils': 2.0.6(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/breadcrumb@2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-children-utils': 2.0.6(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/breakpoint-utils@2.0.8':
    dependencies:
      '@chakra-ui/shared-utils': 2.0.5

  '@chakra-ui/button@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/spinner': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/card@2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/checkbox@2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/form-control': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-controllable-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-update-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/visually-hidden': 2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@zag-js/focus-visible': 0.16.0
      react: 18.2.0

  '@chakra-ui/clickable@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      react: 18.2.0

  '@chakra-ui/close-button@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/color-mode@2.2.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/control-box@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/counter@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/number-utils': 2.0.7
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      react: 18.2.0

  '@chakra-ui/css-reset@2.3.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@emotion/react': 11.11.0(@types/react@18.3.21)(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/descendant@3.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/dom-utils@2.1.0': {}

  '@chakra-ui/editable@3.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-controllable-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-focus-on-pointer-down': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-update-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/event-utils@2.0.8': {}

  '@chakra-ui/focus-lock@2.1.0(@types/react@18.3.21)(react@18.2.0)':
    dependencies:
      '@chakra-ui/dom-utils': 2.1.0
      react: 18.2.0
      react-focus-lock: 2.13.6(@types/react@18.3.21)(react@18.2.0)
    transitivePeerDependencies:
      - '@types/react'

  '@chakra-ui/form-control@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/hooks@2.2.1(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-utils': 2.0.12(react@18.2.0)
      '@chakra-ui/utils': 2.0.15
      compute-scroll-into-view: 3.0.3
      copy-to-clipboard: 3.3.3
      react: 18.2.0

  '@chakra-ui/icon@3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/image@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/input@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/form-control': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/object-utils': 2.1.0
      '@chakra-ui/react-children-utils': 2.0.6(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/layout@2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/breakpoint-utils': 2.0.8
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/object-utils': 2.1.0
      '@chakra-ui/react-children-utils': 2.0.6(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/lazy-utils@2.0.5': {}

  '@chakra-ui/live-region@2.1.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/media-query@3.3.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/breakpoint-utils': 2.0.8
      '@chakra-ui/react-env': 3.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/menu@2.2.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/clickable': 2.1.0(react@18.2.0)
      '@chakra-ui/descendant': 3.1.0(react@18.2.0)
      '@chakra-ui/lazy-utils': 2.0.5
      '@chakra-ui/popper': 3.1.0(react@18.2.0)
      '@chakra-ui/react-children-utils': 2.0.6(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-animation-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-controllable-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-disclosure': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-focus-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-outside-click': 2.2.0(react@18.2.0)
      '@chakra-ui/react-use-update-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/transition': 2.1.0(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/modal@2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(@types/react@18.3.21)(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/close-button': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/focus-lock': 2.1.0(@types/react@18.3.21)(react@18.2.0)
      '@chakra-ui/portal': 2.1.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/transition': 2.1.0(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)
      aria-hidden: 1.2.4
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)
      react-remove-scroll: 2.6.3(@types/react@18.3.21)(react@18.2.0)
    transitivePeerDependencies:
      - '@types/react'

  '@chakra-ui/number-input@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/counter': 2.1.0(react@18.2.0)
      '@chakra-ui/form-control': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-event-listener': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-interval': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-update-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/number-utils@2.0.7': {}

  '@chakra-ui/object-utils@2.1.0': {}

  '@chakra-ui/pin-input@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/descendant': 3.1.0(react@18.2.0)
      '@chakra-ui/react-children-utils': 2.0.6(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-controllable-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/popover@2.2.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/close-button': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/lazy-utils': 2.0.5
      '@chakra-ui/popper': 3.1.0(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-animation-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-disclosure': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-focus-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-focus-on-pointer-down': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/popper@3.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@popperjs/core': 2.11.8
      react: 18.2.0

  '@chakra-ui/portal@2.1.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)

  '@chakra-ui/progress@2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/provider@2.4.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/css-reset': 2.3.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/portal': 2.1.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-env': 3.1.0(react@18.2.0)
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/utils': 2.0.15
      '@emotion/react': 11.11.0(@types/react@18.3.21)(react@18.2.0)
      '@emotion/styled': 11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0)
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)

  '@chakra-ui/radio@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/form-control': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@zag-js/focus-visible': 0.16.0
      react: 18.2.0

  '@chakra-ui/react-children-utils@2.0.6(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-context@2.1.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-env@3.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-types@2.0.7(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-use-animation-state@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/dom-utils': 2.1.0
      '@chakra-ui/react-use-event-listener': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-callback-ref@2.1.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-use-controllable-state@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-disclosure@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-event-listener@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-focus-effect@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/dom-utils': 2.1.0
      '@chakra-ui/react-use-event-listener': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-update-effect': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-focus-on-pointer-down@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-event-listener': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-interval@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-latest-ref@2.1.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-use-merge-refs@2.1.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-use-outside-click@2.2.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-pan-event@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/event-utils': 2.0.8
      '@chakra-ui/react-use-latest-ref': 2.1.0(react@18.2.0)
      framesync: 6.1.2
      react: 18.2.0

  '@chakra-ui/react-use-previous@2.1.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-use-safe-layout-effect@2.1.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-use-size@2.1.0(react@18.2.0)':
    dependencies:
      '@zag-js/element-size': 0.10.5
      react: 18.2.0

  '@chakra-ui/react-use-timeout@2.1.0(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/react-use-update-effect@2.1.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@chakra-ui/react-utils@2.0.12(react@18.2.0)':
    dependencies:
      '@chakra-ui/utils': 2.0.15
      react: 18.2.0

  '@chakra-ui/react@2.8.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/accordion': 2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/alert': 2.2.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/avatar': 2.3.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/breadcrumb': 2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/button': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/card': 2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/checkbox': 2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/close-button': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/control-box': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/counter': 2.1.0(react@18.2.0)
      '@chakra-ui/css-reset': 2.3.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/editable': 3.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/focus-lock': 2.1.0(@types/react@18.3.21)(react@18.2.0)
      '@chakra-ui/form-control': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/hooks': 2.2.1(react@18.2.0)
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/image': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/input': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/layout': 2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/live-region': 2.1.0(react@18.2.0)
      '@chakra-ui/media-query': 3.3.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/menu': 2.2.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/modal': 2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(@types/react@18.3.21)(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/number-input': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/pin-input': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/popover': 2.2.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/popper': 3.1.0(react@18.2.0)
      '@chakra-ui/portal': 2.1.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/progress': 2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/provider': 2.4.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/radio': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-env': 3.1.0(react@18.2.0)
      '@chakra-ui/select': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/skeleton': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/skip-nav': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/slider': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/spinner': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/stat': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/stepper': 2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/styled-system': 2.9.1
      '@chakra-ui/switch': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/table': 2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/tabs': 3.0.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/tag': 3.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/textarea': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/theme': 3.3.0(@chakra-ui/styled-system@2.9.1)
      '@chakra-ui/theme-utils': 2.0.20
      '@chakra-ui/toast': 7.0.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/tooltip': 2.3.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/transition': 2.1.0(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/utils': 2.0.15
      '@chakra-ui/visually-hidden': 2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@emotion/react': 11.11.0(@types/react@18.3.21)(react@18.2.0)
      '@emotion/styled': 11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0)
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)
    transitivePeerDependencies:
      - '@types/react'

  '@chakra-ui/select@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/form-control': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/shared-utils@2.0.5': {}

  '@chakra-ui/skeleton@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/media-query': 3.3.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-use-previous': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/skip-nav@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/slider@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/number-utils': 2.0.7
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-callback-ref': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-controllable-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-latest-ref': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-pan-event': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-size': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-update-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/spinner@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/stat@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/stepper@2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/styled-system@2.9.1':
    dependencies:
      '@chakra-ui/shared-utils': 2.0.5
      csstype: 3.1.3
      lodash.mergewith: 4.6.2

  '@chakra-ui/switch@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/checkbox': 2.3.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/color-mode': 2.2.0(react@18.2.0)
      '@chakra-ui/object-utils': 2.1.0
      '@chakra-ui/react-utils': 2.0.12(react@18.2.0)
      '@chakra-ui/styled-system': 2.9.1
      '@chakra-ui/theme-utils': 2.0.20
      '@chakra-ui/utils': 2.0.15
      '@emotion/react': 11.11.0(@types/react@18.3.21)(react@18.2.0)
      '@emotion/styled': 11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0)
      react: 18.2.0
      react-fast-compare: 3.2.2

  '@chakra-ui/table@2.1.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/tabs@3.0.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/clickable': 2.1.0(react@18.2.0)
      '@chakra-ui/descendant': 3.1.0(react@18.2.0)
      '@chakra-ui/lazy-utils': 2.0.5
      '@chakra-ui/react-children-utils': 2.0.6(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-controllable-state': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-safe-layout-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/tag@3.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/icon': 3.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/textarea@2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/form-control': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/theme-tools@2.1.1(@chakra-ui/styled-system@2.9.1)':
    dependencies:
      '@chakra-ui/anatomy': 2.2.1
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/styled-system': 2.9.1
      color2k: 2.0.3

  '@chakra-ui/theme-utils@2.0.20':
    dependencies:
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/styled-system': 2.9.1
      '@chakra-ui/theme': 3.3.0(@chakra-ui/styled-system@2.9.1)
      lodash.mergewith: 4.6.2

  '@chakra-ui/theme@3.3.0(@chakra-ui/styled-system@2.9.1)':
    dependencies:
      '@chakra-ui/anatomy': 2.2.1
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/styled-system': 2.9.1
      '@chakra-ui/theme-tools': 2.1.1(@chakra-ui/styled-system@2.9.1)

  '@chakra-ui/toast@7.0.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/alert': 2.2.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/close-button': 2.1.1(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)
      '@chakra-ui/portal': 2.1.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-context': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-timeout': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-update-effect': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/styled-system': 2.9.1
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      '@chakra-ui/theme': 3.3.0(@chakra-ui/styled-system@2.9.1)
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)

  '@chakra-ui/tooltip@2.3.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/dom-utils': 2.1.0
      '@chakra-ui/popper': 3.1.0(react@18.2.0)
      '@chakra-ui/portal': 2.1.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      '@chakra-ui/react-types': 2.0.7(react@18.2.0)
      '@chakra-ui/react-use-disclosure': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-event-listener': 2.1.0(react@18.2.0)
      '@chakra-ui/react-use-merge-refs': 2.1.0(react@18.2.0)
      '@chakra-ui/shared-utils': 2.0.5
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)

  '@chakra-ui/transition@2.1.0(framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/shared-utils': 2.0.5
      framer-motion: 7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@chakra-ui/utils@2.0.15':
    dependencies:
      '@types/lodash.mergewith': 4.6.7
      css-box-model: 1.2.1
      framesync: 6.1.2
      lodash.mergewith: 4.6.2

  '@chakra-ui/visually-hidden@2.2.0(@chakra-ui/system@2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0))(react@18.2.0)':
    dependencies:
      '@chakra-ui/system': 2.6.1(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0))(react@18.2.0)
      react: 18.2.0

  '@emnapi/runtime@1.4.3':
    dependencies:
      tslib: 2.8.1
    optional: true

  '@emotion/babel-plugin@11.13.5':
    dependencies:
      '@babel/helper-module-imports': 7.27.1
      '@babel/runtime': 7.27.1
      '@emotion/hash': 0.9.2
      '@emotion/memoize': 0.9.0
      '@emotion/serialize': 1.3.3
      babel-plugin-macros: 3.1.0
      convert-source-map: 1.9.0
      escape-string-regexp: 4.0.0
      find-root: 1.1.0
      source-map: 0.5.7
      stylis: 4.2.0
    transitivePeerDependencies:
      - supports-color

  '@emotion/cache@11.14.0':
    dependencies:
      '@emotion/memoize': 0.9.0
      '@emotion/sheet': 1.4.0
      '@emotion/utils': 1.4.2
      '@emotion/weak-memoize': 0.4.0
      stylis: 4.2.0

  '@emotion/hash@0.9.2': {}

  '@emotion/is-prop-valid@0.8.8':
    dependencies:
      '@emotion/memoize': 0.7.4
    optional: true

  '@emotion/is-prop-valid@1.3.1':
    dependencies:
      '@emotion/memoize': 0.9.0

  '@emotion/memoize@0.7.4':
    optional: true

  '@emotion/memoize@0.9.0': {}

  '@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0)':
    dependencies:
      '@babel/runtime': 7.27.1
      '@emotion/babel-plugin': 11.13.5
      '@emotion/cache': 11.14.0
      '@emotion/serialize': 1.3.3
      '@emotion/use-insertion-effect-with-fallbacks': 1.2.0(react@18.2.0)
      '@emotion/utils': 1.4.2
      '@emotion/weak-memoize': 0.3.1
      hoist-non-react-statics: 3.3.2
      react: 18.2.0
    optionalDependencies:
      '@types/react': 18.3.21
    transitivePeerDependencies:
      - supports-color

  '@emotion/serialize@1.3.3':
    dependencies:
      '@emotion/hash': 0.9.2
      '@emotion/memoize': 0.9.0
      '@emotion/unitless': 0.10.0
      '@emotion/utils': 1.4.2
      csstype: 3.1.3

  '@emotion/sheet@1.4.0': {}

  '@emotion/styled@11.11.0(@emotion/react@11.11.0(@types/react@18.3.21)(react@18.2.0))(@types/react@18.3.21)(react@18.2.0)':
    dependencies:
      '@babel/runtime': 7.27.1
      '@emotion/babel-plugin': 11.13.5
      '@emotion/is-prop-valid': 1.3.1
      '@emotion/react': 11.11.0(@types/react@18.3.21)(react@18.2.0)
      '@emotion/serialize': 1.3.3
      '@emotion/use-insertion-effect-with-fallbacks': 1.2.0(react@18.2.0)
      '@emotion/utils': 1.4.2
      react: 18.2.0
    optionalDependencies:
      '@types/react': 18.3.21
    transitivePeerDependencies:
      - supports-color

  '@emotion/unitless@0.10.0': {}

  '@emotion/use-insertion-effect-with-fallbacks@1.2.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@emotion/utils@1.4.2': {}

  '@emotion/weak-memoize@0.3.1': {}

  '@emotion/weak-memoize@0.4.0': {}

  '@heroicons/react@2.2.0(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@img/sharp-darwin-arm64@0.33.5':
    optionalDependencies:
      '@img/sharp-libvips-darwin-arm64': 1.0.4
    optional: true

  '@img/sharp-darwin-x64@0.33.5':
    optionalDependencies:
      '@img/sharp-libvips-darwin-x64': 1.0.4
    optional: true

  '@img/sharp-libvips-darwin-arm64@1.0.4':
    optional: true

  '@img/sharp-libvips-darwin-x64@1.0.4':
    optional: true

  '@img/sharp-libvips-linux-arm64@1.0.4':
    optional: true

  '@img/sharp-libvips-linux-arm@1.0.5':
    optional: true

  '@img/sharp-libvips-linux-s390x@1.0.4':
    optional: true

  '@img/sharp-libvips-linux-x64@1.0.4':
    optional: true

  '@img/sharp-libvips-linuxmusl-arm64@1.0.4':
    optional: true

  '@img/sharp-libvips-linuxmusl-x64@1.0.4':
    optional: true

  '@img/sharp-linux-arm64@0.33.5':
    optionalDependencies:
      '@img/sharp-libvips-linux-arm64': 1.0.4
    optional: true

  '@img/sharp-linux-arm@0.33.5':
    optionalDependencies:
      '@img/sharp-libvips-linux-arm': 1.0.5
    optional: true

  '@img/sharp-linux-s390x@0.33.5':
    optionalDependencies:
      '@img/sharp-libvips-linux-s390x': 1.0.4
    optional: true

  '@img/sharp-linux-x64@0.33.5':
    optionalDependencies:
      '@img/sharp-libvips-linux-x64': 1.0.4
    optional: true

  '@img/sharp-linuxmusl-arm64@0.33.5':
    optionalDependencies:
      '@img/sharp-libvips-linuxmusl-arm64': 1.0.4
    optional: true

  '@img/sharp-linuxmusl-x64@0.33.5':
    optionalDependencies:
      '@img/sharp-libvips-linuxmusl-x64': 1.0.4
    optional: true

  '@img/sharp-wasm32@0.33.5':
    dependencies:
      '@emnapi/runtime': 1.4.3
    optional: true

  '@img/sharp-win32-ia32@0.33.5':
    optional: true

  '@img/sharp-win32-x64@0.33.5':
    optional: true

  '@ioredis/commands@1.2.0': {}

  '@isaacs/cliui@8.0.2':
    dependencies:
      string-width: 5.1.2
      string-width-cjs: string-width@4.2.3
      strip-ansi: 7.1.0
      strip-ansi-cjs: strip-ansi@6.0.1
      wrap-ansi: 8.1.0
      wrap-ansi-cjs: wrap-ansi@7.0.0

  '@jridgewell/gen-mapping@0.3.8':
    dependencies:
      '@jridgewell/set-array': 1.2.1
      '@jridgewell/sourcemap-codec': 1.5.0
      '@jridgewell/trace-mapping': 0.3.25

  '@jridgewell/resolve-uri@3.1.2': {}

  '@jridgewell/set-array@1.2.1': {}

  '@jridgewell/sourcemap-codec@1.5.0': {}

  '@jridgewell/trace-mapping@0.3.25':
    dependencies:
      '@jridgewell/resolve-uri': 3.1.2
      '@jridgewell/sourcemap-codec': 1.5.0

  '@motionone/animation@10.18.0':
    dependencies:
      '@motionone/easing': 10.18.0
      '@motionone/types': 10.17.1
      '@motionone/utils': 10.18.0
      tslib: 2.4.0

  '@motionone/dom@10.13.1':
    dependencies:
      '@motionone/animation': 10.18.0
      '@motionone/generators': 10.18.0
      '@motionone/types': 10.17.1
      '@motionone/utils': 10.18.0
      hey-listen: 1.0.8
      tslib: 2.4.0

  '@motionone/easing@10.18.0':
    dependencies:
      '@motionone/utils': 10.18.0
      tslib: 2.4.0

  '@motionone/generators@10.18.0':
    dependencies:
      '@motionone/types': 10.17.1
      '@motionone/utils': 10.18.0
      tslib: 2.4.0

  '@motionone/types@10.17.1': {}

  '@motionone/utils@10.18.0':
    dependencies:
      '@motionone/types': 10.17.1
      hey-listen: 1.0.8
      tslib: 2.4.0

  '@next-auth/typeorm-legacy-adapter@2.0.2(next-auth@4.24.11(next@15.2.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(typeorm@0.3.7(ioredis@5.6.1))':
    dependencies:
      next-auth: 4.24.11(next@15.2.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      typeorm: 0.3.7(ioredis@5.6.1)

  '@next/env@15.2.0': {}

  '@next/swc-darwin-arm64@15.2.0':
    optional: true

  '@next/swc-darwin-x64@15.2.0':
    optional: true

  '@next/swc-linux-arm64-gnu@15.2.0':
    optional: true

  '@next/swc-linux-arm64-musl@15.2.0':
    optional: true

  '@next/swc-linux-x64-gnu@15.2.0':
    optional: true

  '@next/swc-linux-x64-musl@15.2.0':
    optional: true

  '@next/swc-win32-arm64-msvc@15.2.0':
    optional: true

  '@next/swc-win32-x64-msvc@15.2.0':
    optional: true

  '@nodelib/fs.scandir@2.1.5':
    dependencies:
      '@nodelib/fs.stat': 2.0.5
      run-parallel: 1.2.0

  '@nodelib/fs.stat@2.0.5': {}

  '@nodelib/fs.walk@1.2.8':
    dependencies:
      '@nodelib/fs.scandir': 2.1.5
      fastq: 1.19.1

  '@panva/hkdf@1.2.1': {}

  '@pkgjs/parseargs@0.11.0':
    optional: true

  '@popperjs/core@2.11.8': {}

  '@radix-ui/react-compose-refs@1.1.2(@types/react@18.3.21)(react@18.2.0)':
    dependencies:
      react: 18.2.0
    optionalDependencies:
      '@types/react': 18.3.21

  '@radix-ui/react-icons@1.3.2(react@18.2.0)':
    dependencies:
      react: 18.2.0

  '@radix-ui/react-slot@1.2.2(@types/react@18.3.21)(react@18.2.0)':
    dependencies:
      '@radix-ui/react-compose-refs': 1.1.2(@types/react@18.3.21)(react@18.2.0)
      react: 18.2.0
    optionalDependencies:
      '@types/react': 18.3.21

  '@shadcn/ui@0.0.4':
    dependencies:
      chalk: 5.2.0
      commander: 10.0.1
      execa: 7.2.0
      fs-extra: 11.3.0
      node-fetch: 3.3.2
      ora: 6.3.1
      prompts: 2.4.2
      zod: 3.24.4

  '@sqltools/formatter@1.2.5': {}

  '@swc/counter@0.1.3': {}

  '@swc/helpers@0.5.15':
    dependencies:
      tslib: 2.8.1

  '@tailwindcss/forms@0.5.10(tailwindcss@3.4.17)':
    dependencies:
      mini-svg-data-uri: 1.4.4
      tailwindcss: 3.4.17

  '@tailwindcss/typography@0.5.16(tailwindcss@3.4.17)':
    dependencies:
      lodash.castarray: 4.4.0
      lodash.isplainobject: 4.0.6
      lodash.merge: 4.6.2
      postcss-selector-parser: 6.0.10
      tailwindcss: 3.4.17

  '@types/debug@4.1.12':
    dependencies:
      '@types/ms': 2.1.0

  '@types/estree-jsx@1.0.5':
    dependencies:
      '@types/estree': 1.0.7

  '@types/estree@1.0.7': {}

  '@types/hast@2.3.10':
    dependencies:
      '@types/unist': 2.0.11

  '@types/hast@3.0.4':
    dependencies:
      '@types/unist': 3.0.3

  '@types/jwt-decode@2.2.1': {}

  '@types/lodash.mergewith@4.6.7':
    dependencies:
      '@types/lodash': 4.17.16

  '@types/lodash@4.17.16': {}

  '@types/mdast@4.0.4':
    dependencies:
      '@types/unist': 3.0.3

  '@types/ms@2.1.0': {}

  '@types/node@20.17.41':
    dependencies:
      undici-types: 6.19.8

  '@types/parse-json@4.0.2': {}

  '@types/prop-types@15.7.14': {}

  '@types/react-dom@18.3.7(@types/react@18.3.21)':
    dependencies:
      '@types/react': 18.3.21

  '@types/react@18.3.21':
    dependencies:
      '@types/prop-types': 15.7.14
      csstype: 3.1.3

  '@types/unist@2.0.11': {}

  '@types/unist@3.0.3': {}

  '@ungap/structured-clone@1.3.0': {}

  '@zag-js/dom-query@0.16.0': {}

  '@zag-js/element-size@0.10.5': {}

  '@zag-js/focus-visible@0.16.0':
    dependencies:
      '@zag-js/dom-query': 0.16.0

  ansi-regex@5.0.1: {}

  ansi-regex@6.1.0: {}

  ansi-styles@4.3.0:
    dependencies:
      color-convert: 2.0.1

  ansi-styles@6.2.1: {}

  any-promise@1.3.0: {}

  anymatch@3.1.3:
    dependencies:
      normalize-path: 3.0.0
      picomatch: 2.3.1

  app-root-path@3.1.0: {}

  arg@5.0.2: {}

  argparse@2.0.1: {}

  aria-hidden@1.2.4:
    dependencies:
      tslib: 2.8.1

  asynckit@0.4.0: {}

  autoprefixer@10.4.21(postcss@8.5.3):
    dependencies:
      browserslist: 4.24.5
      caniuse-lite: 1.0.30001717
      fraction.js: 4.3.7
      normalize-range: 0.1.2
      picocolors: 1.1.1
      postcss: 8.5.3
      postcss-value-parser: 4.2.0

  axios@1.9.0:
    dependencies:
      follow-redirects: 1.15.9
      form-data: 4.0.2
      proxy-from-env: 1.1.0
    transitivePeerDependencies:
      - debug

  babel-plugin-macros@3.1.0:
    dependencies:
      '@babel/runtime': 7.27.1
      cosmiconfig: 7.1.0
      resolve: 1.22.10

  bail@2.0.2: {}

  balanced-match@1.0.2: {}

  base64-js@1.5.1: {}

  binary-extensions@2.3.0: {}

  bl@5.1.0:
    dependencies:
      buffer: 6.0.3
      inherits: 2.0.4
      readable-stream: 3.6.2

  brace-expansion@1.1.11:
    dependencies:
      balanced-match: 1.0.2
      concat-map: 0.0.1

  brace-expansion@2.0.1:
    dependencies:
      balanced-match: 1.0.2

  braces@3.0.3:
    dependencies:
      fill-range: 7.1.1

  browserslist@4.24.5:
    dependencies:
      caniuse-lite: 1.0.30001717
      electron-to-chromium: 1.5.150
      node-releases: 2.0.19
      update-browserslist-db: 1.1.3(browserslist@4.24.5)

  buffer@6.0.3:
    dependencies:
      base64-js: 1.5.1
      ieee754: 1.2.1

  busboy@1.6.0:
    dependencies:
      streamsearch: 1.1.0

  call-bind-apply-helpers@1.0.2:
    dependencies:
      es-errors: 1.3.0
      function-bind: 1.1.2

  callsites@3.1.0: {}

  camelcase-css@2.0.1: {}

  caniuse-lite@1.0.30001717: {}

  ccount@2.0.1: {}

  chalk@4.1.2:
    dependencies:
      ansi-styles: 4.3.0
      supports-color: 7.2.0

  chalk@5.2.0: {}

  character-entities-html4@2.1.0: {}

  character-entities-legacy@1.1.4: {}

  character-entities-legacy@3.0.0: {}

  character-entities@1.2.4: {}

  character-entities@2.0.2: {}

  character-reference-invalid@1.1.4: {}

  character-reference-invalid@2.0.1: {}

  chokidar@3.6.0:
    dependencies:
      anymatch: 3.1.3
      braces: 3.0.3
      glob-parent: 5.1.2
      is-binary-path: 2.1.0
      is-glob: 4.0.3
      normalize-path: 3.0.0
      readdirp: 3.6.0
    optionalDependencies:
      fsevents: 2.3.3

  class-variance-authority@0.7.1:
    dependencies:
      clsx: 2.1.1

  classnames@2.5.1: {}

  cli-cursor@4.0.0:
    dependencies:
      restore-cursor: 4.0.0

  cli-highlight@2.1.11:
    dependencies:
      chalk: 4.1.2
      highlight.js: 10.7.3
      mz: 2.7.0
      parse5: 5.1.1
      parse5-htmlparser2-tree-adapter: 6.0.1
      yargs: 16.2.0

  cli-spinners@2.9.2: {}

  client-only@0.0.1: {}

  cliui@7.0.4:
    dependencies:
      string-width: 4.2.3
      strip-ansi: 6.0.1
      wrap-ansi: 7.0.0

  cliui@8.0.1:
    dependencies:
      string-width: 4.2.3
      strip-ansi: 6.0.1
      wrap-ansi: 7.0.0

  clone@1.0.4: {}

  clsx@2.1.1: {}

  cluster-key-slot@1.1.2: {}

  color-convert@2.0.1:
    dependencies:
      color-name: 1.1.4

  color-name@1.1.4: {}

  color-string@1.9.1:
    dependencies:
      color-name: 1.1.4
      simple-swizzle: 0.2.2
    optional: true

  color2k@2.0.3: {}

  color@4.2.3:
    dependencies:
      color-convert: 2.0.1
      color-string: 1.9.1
    optional: true

  combined-stream@1.0.8:
    dependencies:
      delayed-stream: 1.0.0

  comma-separated-tokens@1.0.8: {}

  comma-separated-tokens@2.0.3: {}

  commander@10.0.1: {}

  commander@4.1.1: {}

  compute-scroll-into-view@3.0.3: {}

  concat-map@0.0.1: {}

  convert-source-map@1.9.0: {}

  cookie@0.7.2: {}

  copy-to-clipboard@3.3.3:
    dependencies:
      toggle-selection: 1.0.6

  cosmiconfig@7.1.0:
    dependencies:
      '@types/parse-json': 4.0.2
      import-fresh: 3.3.1
      parse-json: 5.2.0
      path-type: 4.0.0
      yaml: 1.10.2

  cross-spawn@7.0.6:
    dependencies:
      path-key: 3.1.1
      shebang-command: 2.0.0
      which: 2.0.2

  css-box-model@1.2.1:
    dependencies:
      tiny-invariant: 1.3.3

  cssesc@3.0.0: {}

  csstype@3.1.3: {}

  data-uri-to-buffer@4.0.1: {}

  date-fns@2.30.0:
    dependencies:
      '@babel/runtime': 7.27.1

  debug@4.4.0:
    dependencies:
      ms: 2.1.3

  decode-named-character-reference@1.1.0:
    dependencies:
      character-entities: 2.0.2

  defaults@1.0.4:
    dependencies:
      clone: 1.0.4

  delayed-stream@1.0.0: {}

  denque@2.1.0: {}

  dequal@2.0.3: {}

  detect-libc@2.0.4:
    optional: true

  detect-node-es@1.1.0: {}

  devlop@1.1.0:
    dependencies:
      dequal: 2.0.3

  didyoumean@1.2.2: {}

  dlv@1.1.3: {}

  dotenv@16.5.0: {}

  dunder-proto@1.0.1:
    dependencies:
      call-bind-apply-helpers: 1.0.2
      es-errors: 1.3.0
      gopd: 1.2.0

  eastasianwidth@0.2.0: {}

  electron-to-chromium@1.5.150: {}

  emoji-regex@8.0.0: {}

  emoji-regex@9.2.2: {}

  entities@6.0.0: {}

  error-ex@1.3.2:
    dependencies:
      is-arrayish: 0.2.1

  es-define-property@1.0.1: {}

  es-errors@1.3.0: {}

  es-object-atoms@1.1.1:
    dependencies:
      es-errors: 1.3.0

  es-set-tostringtag@2.1.0:
    dependencies:
      es-errors: 1.3.0
      get-intrinsic: 1.3.0
      has-tostringtag: 1.0.2
      hasown: 2.0.2

  escalade@3.2.0: {}

  escape-string-regexp@4.0.0: {}

  escape-string-regexp@5.0.0: {}

  estree-util-is-identifier-name@3.0.0: {}

  execa@7.2.0:
    dependencies:
      cross-spawn: 7.0.6
      get-stream: 6.0.1
      human-signals: 4.3.1
      is-stream: 3.0.0
      merge-stream: 2.0.0
      npm-run-path: 5.3.0
      onetime: 6.0.0
      signal-exit: 3.0.7
      strip-final-newline: 3.0.0

  extend@3.0.2: {}

  fast-glob@3.3.3:
    dependencies:
      '@nodelib/fs.stat': 2.0.5
      '@nodelib/fs.walk': 1.2.8
      glob-parent: 5.1.2
      merge2: 1.4.1
      micromatch: 4.0.8

  fastq@1.19.1:
    dependencies:
      reusify: 1.1.0

  fault@1.0.4:
    dependencies:
      format: 0.2.2

  fetch-blob@3.2.0:
    dependencies:
      node-domexception: 1.0.0
      web-streams-polyfill: 3.3.3

  fill-range@7.1.1:
    dependencies:
      to-regex-range: 5.0.1

  find-root@1.1.0: {}

  focus-lock@1.3.6:
    dependencies:
      tslib: 2.8.1

  follow-redirects@1.15.9: {}

  foreground-child@3.3.1:
    dependencies:
      cross-spawn: 7.0.6
      signal-exit: 4.1.0

  form-data@4.0.2:
    dependencies:
      asynckit: 0.4.0
      combined-stream: 1.0.8
      es-set-tostringtag: 2.1.0
      mime-types: 2.1.35

  format@0.2.2: {}

  formdata-polyfill@4.0.10:
    dependencies:
      fetch-blob: 3.2.0

  fraction.js@4.3.7: {}

  framer-motion@7.6.8(react-dom@18.2.0(react@18.2.0))(react@18.2.0):
    dependencies:
      '@motionone/dom': 10.13.1
      framesync: 6.1.2
      hey-listen: 1.0.8
      popmotion: 11.0.5
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)
      style-value-types: 5.1.2
      tslib: 2.4.0
    optionalDependencies:
      '@emotion/is-prop-valid': 0.8.8

  framesync@6.1.2:
    dependencies:
      tslib: 2.4.0

  fs-extra@11.3.0:
    dependencies:
      graceful-fs: 4.2.11
      jsonfile: 6.1.0
      universalify: 2.0.1

  fs.realpath@1.0.0: {}

  fsevents@2.3.3:
    optional: true

  function-bind@1.1.2: {}

  get-caller-file@2.0.5: {}

  get-intrinsic@1.3.0:
    dependencies:
      call-bind-apply-helpers: 1.0.2
      es-define-property: 1.0.1
      es-errors: 1.3.0
      es-object-atoms: 1.1.1
      function-bind: 1.1.2
      get-proto: 1.0.1
      gopd: 1.2.0
      has-symbols: 1.1.0
      hasown: 2.0.2
      math-intrinsics: 1.1.0

  get-nonce@1.0.1: {}

  get-proto@1.0.1:
    dependencies:
      dunder-proto: 1.0.1
      es-object-atoms: 1.1.1

  get-stream@6.0.1: {}

  glob-parent@5.1.2:
    dependencies:
      is-glob: 4.0.3

  glob-parent@6.0.2:
    dependencies:
      is-glob: 4.0.3

  glob@10.4.5:
    dependencies:
      foreground-child: 3.3.1
      jackspeak: 3.4.3
      minimatch: 9.0.5
      minipass: 7.1.2
      package-json-from-dist: 1.0.1
      path-scurry: 1.11.1

  glob@7.2.3:
    dependencies:
      fs.realpath: 1.0.0
      inflight: 1.0.6
      inherits: 2.0.4
      minimatch: 3.1.2
      once: 1.4.0
      path-is-absolute: 1.0.1

  globals@11.12.0: {}

  gopd@1.2.0: {}

  graceful-fs@4.2.11: {}

  has-flag@4.0.0: {}

  has-symbols@1.1.0: {}

  has-tostringtag@1.0.2:
    dependencies:
      has-symbols: 1.1.0

  hasown@2.0.2:
    dependencies:
      function-bind: 1.1.2

  hast-util-from-parse5@8.0.3:
    dependencies:
      '@types/hast': 3.0.4
      '@types/unist': 3.0.3
      devlop: 1.1.0
      hastscript: 9.0.1
      property-information: 7.0.0
      vfile: 6.0.3
      vfile-location: 5.0.3
      web-namespaces: 2.0.1

  hast-util-is-element@3.0.0:
    dependencies:
      '@types/hast': 3.0.4

  hast-util-parse-selector@2.2.5: {}

  hast-util-parse-selector@4.0.0:
    dependencies:
      '@types/hast': 3.0.4

  hast-util-raw@9.1.0:
    dependencies:
      '@types/hast': 3.0.4
      '@types/unist': 3.0.3
      '@ungap/structured-clone': 1.3.0
      hast-util-from-parse5: 8.0.3
      hast-util-to-parse5: 8.0.0
      html-void-elements: 3.0.0
      mdast-util-to-hast: 13.2.0
      parse5: 7.3.0
      unist-util-position: 5.0.0
      unist-util-visit: 5.0.0
      vfile: 6.0.3
      web-namespaces: 2.0.1
      zwitch: 2.0.4

  hast-util-sanitize@5.0.2:
    dependencies:
      '@types/hast': 3.0.4
      '@ungap/structured-clone': 1.3.0
      unist-util-position: 5.0.0

  hast-util-to-jsx-runtime@2.3.6:
    dependencies:
      '@types/estree': 1.0.7
      '@types/hast': 3.0.4
      '@types/unist': 3.0.3
      comma-separated-tokens: 2.0.3
      devlop: 1.1.0
      estree-util-is-identifier-name: 3.0.0
      hast-util-whitespace: 3.0.0
      mdast-util-mdx-expression: 2.0.1
      mdast-util-mdx-jsx: 3.2.0
      mdast-util-mdxjs-esm: 2.0.1
      property-information: 7.0.0
      space-separated-tokens: 2.0.2
      style-to-js: 1.1.16
      unist-util-position: 5.0.0
      vfile-message: 4.0.2
    transitivePeerDependencies:
      - supports-color

  hast-util-to-parse5@8.0.0:
    dependencies:
      '@types/hast': 3.0.4
      comma-separated-tokens: 2.0.3
      devlop: 1.1.0
      property-information: 6.5.0
      space-separated-tokens: 2.0.2
      web-namespaces: 2.0.1
      zwitch: 2.0.4

  hast-util-to-text@4.0.2:
    dependencies:
      '@types/hast': 3.0.4
      '@types/unist': 3.0.3
      hast-util-is-element: 3.0.0
      unist-util-find-after: 5.0.0

  hast-util-whitespace@3.0.0:
    dependencies:
      '@types/hast': 3.0.4

  hastscript@6.0.0:
    dependencies:
      '@types/hast': 2.3.10
      comma-separated-tokens: 1.0.8
      hast-util-parse-selector: 2.2.5
      property-information: 5.6.0
      space-separated-tokens: 1.1.5

  hastscript@9.0.1:
    dependencies:
      '@types/hast': 3.0.4
      comma-separated-tokens: 2.0.3
      hast-util-parse-selector: 4.0.0
      property-information: 7.0.0
      space-separated-tokens: 2.0.2

  hey-listen@1.0.8: {}

  highlight.js@10.7.3: {}

  highlight.js@11.11.1: {}

  highlightjs-vue@1.0.0: {}

  hoist-non-react-statics@3.3.2:
    dependencies:
      react-is: 16.13.1

  html-url-attributes@3.0.1: {}

  html-void-elements@3.0.0: {}

  human-signals@4.3.1: {}

  ieee754@1.2.1: {}

  import-fresh@3.3.1:
    dependencies:
      parent-module: 1.0.1
      resolve-from: 4.0.0

  inflight@1.0.6:
    dependencies:
      once: 1.4.0
      wrappy: 1.0.2

  inherits@2.0.4: {}

  inline-style-parser@0.2.4: {}

  ioredis@5.6.1:
    dependencies:
      '@ioredis/commands': 1.2.0
      cluster-key-slot: 1.1.2
      debug: 4.4.0
      denque: 2.1.0
      lodash.defaults: 4.2.0
      lodash.isarguments: 3.1.0
      redis-errors: 1.2.0
      redis-parser: 3.0.0
      standard-as-callback: 2.1.0
    transitivePeerDependencies:
      - supports-color

  is-alphabetical@1.0.4: {}

  is-alphabetical@2.0.1: {}

  is-alphanumerical@1.0.4:
    dependencies:
      is-alphabetical: 1.0.4
      is-decimal: 1.0.4

  is-alphanumerical@2.0.1:
    dependencies:
      is-alphabetical: 2.0.1
      is-decimal: 2.0.1

  is-arrayish@0.2.1: {}

  is-arrayish@0.3.2:
    optional: true

  is-binary-path@2.1.0:
    dependencies:
      binary-extensions: 2.3.0

  is-core-module@2.16.1:
    dependencies:
      hasown: 2.0.2

  is-decimal@1.0.4: {}

  is-decimal@2.0.1: {}

  is-extglob@2.1.1: {}

  is-fullwidth-code-point@3.0.0: {}

  is-glob@4.0.3:
    dependencies:
      is-extglob: 2.1.1

  is-hexadecimal@1.0.4: {}

  is-hexadecimal@2.0.1: {}

  is-interactive@2.0.0: {}

  is-number@7.0.0: {}

  is-plain-obj@4.1.0: {}

  is-stream@3.0.0: {}

  is-unicode-supported@1.3.0: {}

  isexe@2.0.0: {}

  jackspeak@3.4.3:
    dependencies:
      '@isaacs/cliui': 8.0.2
    optionalDependencies:
      '@pkgjs/parseargs': 0.11.0

  jiti@1.21.7: {}

  jose@4.15.9: {}

  js-tokens@4.0.0: {}

  js-yaml@4.1.0:
    dependencies:
      argparse: 2.0.1

  jsesc@3.1.0: {}

  json-parse-even-better-errors@2.3.1: {}

  jsonfile@6.1.0:
    dependencies:
      universalify: 2.0.1
    optionalDependencies:
      graceful-fs: 4.2.11

  jwt-decode@4.0.0: {}

  kleur@3.0.3: {}

  lilconfig@3.1.3: {}

  lines-and-columns@1.2.4: {}

  lodash.castarray@4.4.0: {}

  lodash.defaults@4.2.0: {}

  lodash.isarguments@3.1.0: {}

  lodash.isplainobject@4.0.6: {}

  lodash.merge@4.6.2: {}

  lodash.mergewith@4.6.2: {}

  log-symbols@5.1.0:
    dependencies:
      chalk: 5.2.0
      is-unicode-supported: 1.3.0

  longest-streak@3.1.0: {}

  loose-envify@1.4.0:
    dependencies:
      js-tokens: 4.0.0

  lowlight@1.20.0:
    dependencies:
      fault: 1.0.4
      highlight.js: 10.7.3

  lowlight@3.3.0:
    dependencies:
      '@types/hast': 3.0.4
      devlop: 1.1.0
      highlight.js: 11.11.1

  lru-cache@10.4.3: {}

  lru-cache@6.0.0:
    dependencies:
      yallist: 4.0.0

  lucide-react@0.477.0(react@18.2.0):
    dependencies:
      react: 18.2.0

  markdown-table@3.0.4: {}

  markdown-to-jsx@7.7.6(react@18.2.0):
    dependencies:
      react: 18.2.0

  math-intrinsics@1.1.0: {}

  mdast-util-find-and-replace@3.0.2:
    dependencies:
      '@types/mdast': 4.0.4
      escape-string-regexp: 5.0.0
      unist-util-is: 6.0.0
      unist-util-visit-parents: 6.0.1

  mdast-util-from-markdown@2.0.2:
    dependencies:
      '@types/mdast': 4.0.4
      '@types/unist': 3.0.3
      decode-named-character-reference: 1.1.0
      devlop: 1.1.0
      mdast-util-to-string: 4.0.0
      micromark: 4.0.2
      micromark-util-decode-numeric-character-reference: 2.0.2
      micromark-util-decode-string: 2.0.1
      micromark-util-normalize-identifier: 2.0.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2
      unist-util-stringify-position: 4.0.0
    transitivePeerDependencies:
      - supports-color

  mdast-util-gfm-autolink-literal@2.0.1:
    dependencies:
      '@types/mdast': 4.0.4
      ccount: 2.0.1
      devlop: 1.1.0
      mdast-util-find-and-replace: 3.0.2
      micromark-util-character: 2.1.1

  mdast-util-gfm-footnote@2.1.0:
    dependencies:
      '@types/mdast': 4.0.4
      devlop: 1.1.0
      mdast-util-from-markdown: 2.0.2
      mdast-util-to-markdown: 2.1.2
      micromark-util-normalize-identifier: 2.0.1
    transitivePeerDependencies:
      - supports-color

  mdast-util-gfm-strikethrough@2.0.0:
    dependencies:
      '@types/mdast': 4.0.4
      mdast-util-from-markdown: 2.0.2
      mdast-util-to-markdown: 2.1.2
    transitivePeerDependencies:
      - supports-color

  mdast-util-gfm-table@2.0.0:
    dependencies:
      '@types/mdast': 4.0.4
      devlop: 1.1.0
      markdown-table: 3.0.4
      mdast-util-from-markdown: 2.0.2
      mdast-util-to-markdown: 2.1.2
    transitivePeerDependencies:
      - supports-color

  mdast-util-gfm-task-list-item@2.0.0:
    dependencies:
      '@types/mdast': 4.0.4
      devlop: 1.1.0
      mdast-util-from-markdown: 2.0.2
      mdast-util-to-markdown: 2.1.2
    transitivePeerDependencies:
      - supports-color

  mdast-util-gfm@3.1.0:
    dependencies:
      mdast-util-from-markdown: 2.0.2
      mdast-util-gfm-autolink-literal: 2.0.1
      mdast-util-gfm-footnote: 2.1.0
      mdast-util-gfm-strikethrough: 2.0.0
      mdast-util-gfm-table: 2.0.0
      mdast-util-gfm-task-list-item: 2.0.0
      mdast-util-to-markdown: 2.1.2
    transitivePeerDependencies:
      - supports-color

  mdast-util-mdx-expression@2.0.1:
    dependencies:
      '@types/estree-jsx': 1.0.5
      '@types/hast': 3.0.4
      '@types/mdast': 4.0.4
      devlop: 1.1.0
      mdast-util-from-markdown: 2.0.2
      mdast-util-to-markdown: 2.1.2
    transitivePeerDependencies:
      - supports-color

  mdast-util-mdx-jsx@3.2.0:
    dependencies:
      '@types/estree-jsx': 1.0.5
      '@types/hast': 3.0.4
      '@types/mdast': 4.0.4
      '@types/unist': 3.0.3
      ccount: 2.0.1
      devlop: 1.1.0
      mdast-util-from-markdown: 2.0.2
      mdast-util-to-markdown: 2.1.2
      parse-entities: 4.0.2
      stringify-entities: 4.0.4
      unist-util-stringify-position: 4.0.0
      vfile-message: 4.0.2
    transitivePeerDependencies:
      - supports-color

  mdast-util-mdxjs-esm@2.0.1:
    dependencies:
      '@types/estree-jsx': 1.0.5
      '@types/hast': 3.0.4
      '@types/mdast': 4.0.4
      devlop: 1.1.0
      mdast-util-from-markdown: 2.0.2
      mdast-util-to-markdown: 2.1.2
    transitivePeerDependencies:
      - supports-color

  mdast-util-newline-to-break@2.0.0:
    dependencies:
      '@types/mdast': 4.0.4
      mdast-util-find-and-replace: 3.0.2

  mdast-util-phrasing@4.1.0:
    dependencies:
      '@types/mdast': 4.0.4
      unist-util-is: 6.0.0

  mdast-util-to-hast@13.2.0:
    dependencies:
      '@types/hast': 3.0.4
      '@types/mdast': 4.0.4
      '@ungap/structured-clone': 1.3.0
      devlop: 1.1.0
      micromark-util-sanitize-uri: 2.0.1
      trim-lines: 3.0.1
      unist-util-position: 5.0.0
      unist-util-visit: 5.0.0
      vfile: 6.0.3

  mdast-util-to-markdown@2.1.2:
    dependencies:
      '@types/mdast': 4.0.4
      '@types/unist': 3.0.3
      longest-streak: 3.1.0
      mdast-util-phrasing: 4.1.0
      mdast-util-to-string: 4.0.0
      micromark-util-classify-character: 2.0.1
      micromark-util-decode-string: 2.0.1
      unist-util-visit: 5.0.0
      zwitch: 2.0.4

  mdast-util-to-string@4.0.0:
    dependencies:
      '@types/mdast': 4.0.4

  merge-stream@2.0.0: {}

  merge2@1.4.1: {}

  micromark-core-commonmark@2.0.3:
    dependencies:
      decode-named-character-reference: 1.1.0
      devlop: 1.1.0
      micromark-factory-destination: 2.0.1
      micromark-factory-label: 2.0.1
      micromark-factory-space: 2.0.1
      micromark-factory-title: 2.0.1
      micromark-factory-whitespace: 2.0.1
      micromark-util-character: 2.1.1
      micromark-util-chunked: 2.0.1
      micromark-util-classify-character: 2.0.1
      micromark-util-html-tag-name: 2.0.1
      micromark-util-normalize-identifier: 2.0.1
      micromark-util-resolve-all: 2.0.1
      micromark-util-subtokenize: 2.1.0
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-extension-gfm-autolink-literal@2.1.0:
    dependencies:
      micromark-util-character: 2.1.1
      micromark-util-sanitize-uri: 2.0.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-extension-gfm-footnote@2.1.0:
    dependencies:
      devlop: 1.1.0
      micromark-core-commonmark: 2.0.3
      micromark-factory-space: 2.0.1
      micromark-util-character: 2.1.1
      micromark-util-normalize-identifier: 2.0.1
      micromark-util-sanitize-uri: 2.0.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-extension-gfm-strikethrough@2.1.0:
    dependencies:
      devlop: 1.1.0
      micromark-util-chunked: 2.0.1
      micromark-util-classify-character: 2.0.1
      micromark-util-resolve-all: 2.0.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-extension-gfm-table@2.1.1:
    dependencies:
      devlop: 1.1.0
      micromark-factory-space: 2.0.1
      micromark-util-character: 2.1.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-extension-gfm-tagfilter@2.0.0:
    dependencies:
      micromark-util-types: 2.0.2

  micromark-extension-gfm-task-list-item@2.1.0:
    dependencies:
      devlop: 1.1.0
      micromark-factory-space: 2.0.1
      micromark-util-character: 2.1.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-extension-gfm@3.0.0:
    dependencies:
      micromark-extension-gfm-autolink-literal: 2.1.0
      micromark-extension-gfm-footnote: 2.1.0
      micromark-extension-gfm-strikethrough: 2.1.0
      micromark-extension-gfm-table: 2.1.1
      micromark-extension-gfm-tagfilter: 2.0.0
      micromark-extension-gfm-task-list-item: 2.1.0
      micromark-util-combine-extensions: 2.0.1
      micromark-util-types: 2.0.2

  micromark-factory-destination@2.0.1:
    dependencies:
      micromark-util-character: 2.1.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-factory-label@2.0.1:
    dependencies:
      devlop: 1.1.0
      micromark-util-character: 2.1.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-factory-space@2.0.1:
    dependencies:
      micromark-util-character: 2.1.1
      micromark-util-types: 2.0.2

  micromark-factory-title@2.0.1:
    dependencies:
      micromark-factory-space: 2.0.1
      micromark-util-character: 2.1.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-factory-whitespace@2.0.1:
    dependencies:
      micromark-factory-space: 2.0.1
      micromark-util-character: 2.1.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-util-character@2.1.1:
    dependencies:
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-util-chunked@2.0.1:
    dependencies:
      micromark-util-symbol: 2.0.1

  micromark-util-classify-character@2.0.1:
    dependencies:
      micromark-util-character: 2.1.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-util-combine-extensions@2.0.1:
    dependencies:
      micromark-util-chunked: 2.0.1
      micromark-util-types: 2.0.2

  micromark-util-decode-numeric-character-reference@2.0.2:
    dependencies:
      micromark-util-symbol: 2.0.1

  micromark-util-decode-string@2.0.1:
    dependencies:
      decode-named-character-reference: 1.1.0
      micromark-util-character: 2.1.1
      micromark-util-decode-numeric-character-reference: 2.0.2
      micromark-util-symbol: 2.0.1

  micromark-util-encode@2.0.1: {}

  micromark-util-html-tag-name@2.0.1: {}

  micromark-util-normalize-identifier@2.0.1:
    dependencies:
      micromark-util-symbol: 2.0.1

  micromark-util-resolve-all@2.0.1:
    dependencies:
      micromark-util-types: 2.0.2

  micromark-util-sanitize-uri@2.0.1:
    dependencies:
      micromark-util-character: 2.1.1
      micromark-util-encode: 2.0.1
      micromark-util-symbol: 2.0.1

  micromark-util-subtokenize@2.1.0:
    dependencies:
      devlop: 1.1.0
      micromark-util-chunked: 2.0.1
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2

  micromark-util-symbol@2.0.1: {}

  micromark-util-types@2.0.2: {}

  micromark@4.0.2:
    dependencies:
      '@types/debug': 4.1.12
      debug: 4.4.0
      decode-named-character-reference: 1.1.0
      devlop: 1.1.0
      micromark-core-commonmark: 2.0.3
      micromark-factory-space: 2.0.1
      micromark-util-character: 2.1.1
      micromark-util-chunked: 2.0.1
      micromark-util-combine-extensions: 2.0.1
      micromark-util-decode-numeric-character-reference: 2.0.2
      micromark-util-encode: 2.0.1
      micromark-util-normalize-identifier: 2.0.1
      micromark-util-resolve-all: 2.0.1
      micromark-util-sanitize-uri: 2.0.1
      micromark-util-subtokenize: 2.1.0
      micromark-util-symbol: 2.0.1
      micromark-util-types: 2.0.2
    transitivePeerDependencies:
      - supports-color

  micromatch@4.0.8:
    dependencies:
      braces: 3.0.3
      picomatch: 2.3.1

  mime-db@1.52.0: {}

  mime-types@2.1.35:
    dependencies:
      mime-db: 1.52.0

  mimic-fn@2.1.0: {}

  mimic-fn@4.0.0: {}

  mini-svg-data-uri@1.4.4: {}

  minimatch@3.1.2:
    dependencies:
      brace-expansion: 1.1.11

  minimatch@9.0.5:
    dependencies:
      brace-expansion: 2.0.1

  minipass@7.1.2: {}

  mkdirp@1.0.4: {}

  ms@2.1.3: {}

  mz@2.7.0:
    dependencies:
      any-promise: 1.3.0
      object-assign: 4.1.1
      thenify-all: 1.6.0

  nanoid@3.3.11: {}

  next-auth@4.24.11(next@15.2.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0))(react-dom@18.2.0(react@18.2.0))(react@18.2.0):
    dependencies:
      '@babel/runtime': 7.27.1
      '@panva/hkdf': 1.2.1
      cookie: 0.7.2
      jose: 4.15.9
      next: 15.2.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0)
      oauth: 0.9.15
      openid-client: 5.7.1
      preact: 10.26.5
      preact-render-to-string: 5.2.6(preact@10.26.5)
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)
      uuid: 8.3.2

  next@15.2.0(react-dom@18.2.0(react@18.2.0))(react@18.2.0):
    dependencies:
      '@next/env': 15.2.0
      '@swc/counter': 0.1.3
      '@swc/helpers': 0.5.15
      busboy: 1.6.0
      caniuse-lite: 1.0.30001717
      postcss: 8.4.31
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)
      styled-jsx: 5.1.6(react@18.2.0)
    optionalDependencies:
      '@next/swc-darwin-arm64': 15.2.0
      '@next/swc-darwin-x64': 15.2.0
      '@next/swc-linux-arm64-gnu': 15.2.0
      '@next/swc-linux-arm64-musl': 15.2.0
      '@next/swc-linux-x64-gnu': 15.2.0
      '@next/swc-linux-x64-musl': 15.2.0
      '@next/swc-win32-arm64-msvc': 15.2.0
      '@next/swc-win32-x64-msvc': 15.2.0
      sharp: 0.33.5
    transitivePeerDependencies:
      - '@babel/core'
      - babel-plugin-macros

  node-domexception@1.0.0: {}

  node-fetch@3.3.2:
    dependencies:
      data-uri-to-buffer: 4.0.1
      fetch-blob: 3.2.0
      formdata-polyfill: 4.0.10

  node-releases@2.0.19: {}

  normalize-path@3.0.0: {}

  normalize-range@0.1.2: {}

  npm-run-path@5.3.0:
    dependencies:
      path-key: 4.0.0

  oauth@0.9.15: {}

  object-assign@4.1.1: {}

  object-hash@2.2.0: {}

  object-hash@3.0.0: {}

  oidc-token-hash@5.1.0: {}

  once@1.4.0:
    dependencies:
      wrappy: 1.0.2

  onetime@5.1.2:
    dependencies:
      mimic-fn: 2.1.0

  onetime@6.0.0:
    dependencies:
      mimic-fn: 4.0.0

  openid-client@5.7.1:
    dependencies:
      jose: 4.15.9
      lru-cache: 6.0.0
      object-hash: 2.2.0
      oidc-token-hash: 5.1.0

  ora@6.3.1:
    dependencies:
      chalk: 5.2.0
      cli-cursor: 4.0.0
      cli-spinners: 2.9.2
      is-interactive: 2.0.0
      is-unicode-supported: 1.3.0
      log-symbols: 5.1.0
      stdin-discarder: 0.1.0
      strip-ansi: 7.1.0
      wcwidth: 1.0.1

  package-json-from-dist@1.0.1: {}

  parent-module@1.0.1:
    dependencies:
      callsites: 3.1.0

  parse-entities@2.0.0:
    dependencies:
      character-entities: 1.2.4
      character-entities-legacy: 1.1.4
      character-reference-invalid: 1.1.4
      is-alphanumerical: 1.0.4
      is-decimal: 1.0.4
      is-hexadecimal: 1.0.4

  parse-entities@4.0.2:
    dependencies:
      '@types/unist': 2.0.11
      character-entities-legacy: 3.0.0
      character-reference-invalid: 2.0.1
      decode-named-character-reference: 1.1.0
      is-alphanumerical: 2.0.1
      is-decimal: 2.0.1
      is-hexadecimal: 2.0.1

  parse-json@5.2.0:
    dependencies:
      '@babel/code-frame': 7.27.1
      error-ex: 1.3.2
      json-parse-even-better-errors: 2.3.1
      lines-and-columns: 1.2.4

  parse5-htmlparser2-tree-adapter@6.0.1:
    dependencies:
      parse5: 6.0.1

  parse5@5.1.1: {}

  parse5@6.0.1: {}

  parse5@7.3.0:
    dependencies:
      entities: 6.0.0

  path-is-absolute@1.0.1: {}

  path-key@3.1.1: {}

  path-key@4.0.0: {}

  path-parse@1.0.7: {}

  path-scurry@1.11.1:
    dependencies:
      lru-cache: 10.4.3
      minipass: 7.1.2

  path-type@4.0.0: {}

  picocolors@1.1.1: {}

  picomatch@2.3.1: {}

  pify@2.3.0: {}

  pirates@4.0.7: {}

  popmotion@11.0.5:
    dependencies:
      framesync: 6.1.2
      hey-listen: 1.0.8
      style-value-types: 5.1.2
      tslib: 2.4.0

  postcss-import@15.1.0(postcss@8.5.3):
    dependencies:
      postcss: 8.5.3
      postcss-value-parser: 4.2.0
      read-cache: 1.0.0
      resolve: 1.22.10

  postcss-js@4.0.1(postcss@8.5.3):
    dependencies:
      camelcase-css: 2.0.1
      postcss: 8.5.3

  postcss-load-config@4.0.2(postcss@8.5.3):
    dependencies:
      lilconfig: 3.1.3
      yaml: 2.7.1
    optionalDependencies:
      postcss: 8.5.3

  postcss-nested@6.2.0(postcss@8.5.3):
    dependencies:
      postcss: 8.5.3
      postcss-selector-parser: 6.1.2

  postcss-selector-parser@6.0.10:
    dependencies:
      cssesc: 3.0.0
      util-deprecate: 1.0.2

  postcss-selector-parser@6.1.2:
    dependencies:
      cssesc: 3.0.0
      util-deprecate: 1.0.2

  postcss-value-parser@4.2.0: {}

  postcss@8.4.31:
    dependencies:
      nanoid: 3.3.11
      picocolors: 1.1.1
      source-map-js: 1.2.1

  postcss@8.5.3:
    dependencies:
      nanoid: 3.3.11
      picocolors: 1.1.1
      source-map-js: 1.2.1

  preact-render-to-string@5.2.6(preact@10.26.5):
    dependencies:
      preact: 10.26.5
      pretty-format: 3.8.0

  preact@10.26.5: {}

  pretty-format@3.8.0: {}

  prismjs@1.27.0: {}

  prismjs@1.30.0: {}

  prompts@2.4.2:
    dependencies:
      kleur: 3.0.3
      sisteransi: 1.0.5

  prop-types@15.8.1:
    dependencies:
      loose-envify: 1.4.0
      object-assign: 4.1.1
      react-is: 16.13.1

  property-information@5.6.0:
    dependencies:
      xtend: 4.0.2

  property-information@6.5.0: {}

  property-information@7.0.0: {}

  proxy-from-env@1.1.0: {}

  queue-microtask@1.2.3: {}

  rc-util@5.44.4(react-dom@18.2.0(react@18.2.0))(react@18.2.0):
    dependencies:
      '@babel/runtime': 7.27.1
      react: 18.2.0
      react-dom: 18.2.0(react@18.2.0)
      react-is: 18.3.1

  react-clientside-effect@1.2.7(react@18.2.0):
    dependencies:
      '@babel/runtime': 7.27.1
      react: 18.2.0

  react-dom@18.2.0(react@18.2.0):
    dependencies:
      loose-envify: 1.4.0
      react: 18.2.0
      scheduler: 0.23.2

  react-fast-compare@3.2.2: {}

  react-focus-lock@2.13.6(@types/react@18.3.21)(react@18.2.0):
    dependencies:
      '@babel/runtime': 7.27.1
      focus-lock: 1.3.6
      prop-types: 15.8.1
      react: 18.2.0
      react-clientside-effect: 1.2.7(react@18.2.0)
      use-callback-ref: 1.3.3(@types/react@18.3.21)(react@18.2.0)
      use-sidecar: 1.1.3(@types/react@18.3.21)(react@18.2.0)
    optionalDependencies:
      '@types/react': 18.3.21

  react-icons@5.5.0(react@18.2.0):
    dependencies:
      react: 18.2.0

  react-is@16.13.1: {}

  react-is@18.3.1: {}

  react-markdown@10.1.0(@types/react@18.3.21)(react@18.2.0):
    dependencies:
      '@types/hast': 3.0.4
      '@types/mdast': 4.0.4
      '@types/react': 18.3.21
      devlop: 1.1.0
      hast-util-to-jsx-runtime: 2.3.6
      html-url-attributes: 3.0.1
      mdast-util-to-hast: 13.2.0
      react: 18.2.0
      remark-parse: 11.0.0
      remark-rehype: 11.1.2
      unified: 11.0.5
      unist-util-visit: 5.0.0
      vfile: 6.0.3
    transitivePeerDependencies:
      - supports-color

  react-remove-scroll-bar@2.3.8(@types/react@18.3.21)(react@18.2.0):
    dependencies:
      react: 18.2.0
      react-style-singleton: 2.2.3(@types/react@18.3.21)(react@18.2.0)
      tslib: 2.8.1
    optionalDependencies:
      '@types/react': 18.3.21

  react-remove-scroll@2.6.3(@types/react@18.3.21)(react@18.2.0):
    dependencies:
      react: 18.2.0
      react-remove-scroll-bar: 2.3.8(@types/react@18.3.21)(react@18.2.0)
      react-style-singleton: 2.2.3(@types/react@18.3.21)(react@18.2.0)
      tslib: 2.8.1
      use-callback-ref: 1.3.3(@types/react@18.3.21)(react@18.2.0)
      use-sidecar: 1.1.3(@types/react@18.3.21)(react@18.2.0)
    optionalDependencies:
      '@types/react': 18.3.21

  react-style-singleton@2.2.3(@types/react@18.3.21)(react@18.2.0):
    dependencies:
      get-nonce: 1.0.1
      react: 18.2.0
      tslib: 2.8.1
    optionalDependencies:
      '@types/react': 18.3.21

  react-syntax-highlighter@15.6.1(react@18.2.0):
    dependencies:
      '@babel/runtime': 7.27.1
      highlight.js: 10.7.3
      highlightjs-vue: 1.0.0
      lowlight: 1.20.0
      prismjs: 1.30.0
      react: 18.2.0
      refractor: 3.6.0

  react@18.2.0:
    dependencies:
      loose-envify: 1.4.0

  read-cache@1.0.0:
    dependencies:
      pify: 2.3.0

  readable-stream@3.6.2:
    dependencies:
      inherits: 2.0.4
      string_decoder: 1.3.0
      util-deprecate: 1.0.2

  readdirp@3.6.0:
    dependencies:
      picomatch: 2.3.1

  redis-errors@1.2.0: {}

  redis-parser@3.0.0:
    dependencies:
      redis-errors: 1.2.0

  reflect-metadata@0.1.14: {}

  refractor@3.6.0:
    dependencies:
      hastscript: 6.0.0
      parse-entities: 2.0.0
      prismjs: 1.27.0

  rehype-highlight@7.0.2:
    dependencies:
      '@types/hast': 3.0.4
      hast-util-to-text: 4.0.2
      lowlight: 3.3.0
      unist-util-visit: 5.0.0
      vfile: 6.0.3

  rehype-raw@7.0.0:
    dependencies:
      '@types/hast': 3.0.4
      hast-util-raw: 9.1.0
      vfile: 6.0.3

  rehype-sanitize@6.0.0:
    dependencies:
      '@types/hast': 3.0.4
      hast-util-sanitize: 5.0.2

  remark-breaks@4.0.0:
    dependencies:
      '@types/mdast': 4.0.4
      mdast-util-newline-to-break: 2.0.0
      unified: 11.0.5

  remark-gfm@4.0.1:
    dependencies:
      '@types/mdast': 4.0.4
      mdast-util-gfm: 3.1.0
      micromark-extension-gfm: 3.0.0
      remark-parse: 11.0.0
      remark-stringify: 11.0.0
      unified: 11.0.5
    transitivePeerDependencies:
      - supports-color

  remark-parse@11.0.0:
    dependencies:
      '@types/mdast': 4.0.4
      mdast-util-from-markdown: 2.0.2
      micromark-util-types: 2.0.2
      unified: 11.0.5
    transitivePeerDependencies:
      - supports-color

  remark-rehype@11.1.2:
    dependencies:
      '@types/hast': 3.0.4
      '@types/mdast': 4.0.4
      mdast-util-to-hast: 13.2.0
      unified: 11.0.5
      vfile: 6.0.3

  remark-stringify@11.0.0:
    dependencies:
      '@types/mdast': 4.0.4
      mdast-util-to-markdown: 2.1.2
      unified: 11.0.5

  require-directory@2.1.1: {}

  resolve-from@4.0.0: {}

  resolve@1.22.10:
    dependencies:
      is-core-module: 2.16.1
      path-parse: 1.0.7
      supports-preserve-symlinks-flag: 1.0.0

  restore-cursor@4.0.0:
    dependencies:
      onetime: 5.1.2
      signal-exit: 3.0.7

  reusify@1.1.0: {}

  run-parallel@1.2.0:
    dependencies:
      queue-microtask: 1.2.3

  safe-buffer@5.2.1: {}

  sax@1.4.1: {}

  scheduler@0.23.2:
    dependencies:
      loose-envify: 1.4.0

  semver@7.7.1:
    optional: true

  sha.js@2.4.11:
    dependencies:
      inherits: 2.0.4
      safe-buffer: 5.2.1

  sharp@0.33.5:
    dependencies:
      color: 4.2.3
      detect-libc: 2.0.4
      semver: 7.7.1
    optionalDependencies:
      '@img/sharp-darwin-arm64': 0.33.5
      '@img/sharp-darwin-x64': 0.33.5
      '@img/sharp-libvips-darwin-arm64': 1.0.4
      '@img/sharp-libvips-darwin-x64': 1.0.4
      '@img/sharp-libvips-linux-arm': 1.0.5
      '@img/sharp-libvips-linux-arm64': 1.0.4
      '@img/sharp-libvips-linux-s390x': 1.0.4
      '@img/sharp-libvips-linux-x64': 1.0.4
      '@img/sharp-libvips-linuxmusl-arm64': 1.0.4
      '@img/sharp-libvips-linuxmusl-x64': 1.0.4
      '@img/sharp-linux-arm': 0.33.5
      '@img/sharp-linux-arm64': 0.33.5
      '@img/sharp-linux-s390x': 0.33.5
      '@img/sharp-linux-x64': 0.33.5
      '@img/sharp-linuxmusl-arm64': 0.33.5
      '@img/sharp-linuxmusl-x64': 0.33.5
      '@img/sharp-wasm32': 0.33.5
      '@img/sharp-win32-ia32': 0.33.5
      '@img/sharp-win32-x64': 0.33.5
    optional: true

  shebang-command@2.0.0:
    dependencies:
      shebang-regex: 3.0.0

  shebang-regex@3.0.0: {}

  signal-exit@3.0.7: {}

  signal-exit@4.1.0: {}

  simple-swizzle@0.2.2:
    dependencies:
      is-arrayish: 0.3.2
    optional: true

  sisteransi@1.0.5: {}

  source-map-js@1.2.1: {}

  source-map@0.5.7: {}

  space-separated-tokens@1.1.5: {}

  space-separated-tokens@2.0.2: {}

  standard-as-callback@2.1.0: {}

  stdin-discarder@0.1.0:
    dependencies:
      bl: 5.1.0

  streamsearch@1.1.0: {}

  string-width@4.2.3:
    dependencies:
      emoji-regex: 8.0.0
      is-fullwidth-code-point: 3.0.0
      strip-ansi: 6.0.1

  string-width@5.1.2:
    dependencies:
      eastasianwidth: 0.2.0
      emoji-regex: 9.2.2
      strip-ansi: 7.1.0

  string_decoder@1.3.0:
    dependencies:
      safe-buffer: 5.2.1

  stringify-entities@4.0.4:
    dependencies:
      character-entities-html4: 2.1.0
      character-entities-legacy: 3.0.0

  strip-ansi@6.0.1:
    dependencies:
      ansi-regex: 5.0.1

  strip-ansi@7.1.0:
    dependencies:
      ansi-regex: 6.1.0

  strip-final-newline@3.0.0: {}

  style-to-js@1.1.16:
    dependencies:
      style-to-object: 1.0.8

  style-to-object@1.0.8:
    dependencies:
      inline-style-parser: 0.2.4

  style-value-types@5.1.2:
    dependencies:
      hey-listen: 1.0.8
      tslib: 2.4.0

  styled-jsx@5.1.6(react@18.2.0):
    dependencies:
      client-only: 0.0.1
      react: 18.2.0

  stylis@4.2.0: {}

  sucrase@3.35.0:
    dependencies:
      '@jridgewell/gen-mapping': 0.3.8
      commander: 4.1.1
      glob: 10.4.5
      lines-and-columns: 1.2.4
      mz: 2.7.0
      pirates: 4.0.7
      ts-interface-checker: 0.1.13

  supports-color@7.2.0:
    dependencies:
      has-flag: 4.0.0

  supports-preserve-symlinks-flag@1.0.0: {}

  tailwind-merge@3.2.0: {}

  tailwindcss-animate@1.0.7(tailwindcss@3.4.17):
    dependencies:
      tailwindcss: 3.4.17

  tailwindcss@3.4.17:
    dependencies:
      '@alloc/quick-lru': 5.2.0
      arg: 5.0.2
      chokidar: 3.6.0
      didyoumean: 1.2.2
      dlv: 1.1.3
      fast-glob: 3.3.3
      glob-parent: 6.0.2
      is-glob: 4.0.3
      jiti: 1.21.7
      lilconfig: 3.1.3
      micromatch: 4.0.8
      normalize-path: 3.0.0
      object-hash: 3.0.0
      picocolors: 1.1.1
      postcss: 8.5.3
      postcss-import: 15.1.0(postcss@8.5.3)
      postcss-js: 4.0.1(postcss@8.5.3)
      postcss-load-config: 4.0.2(postcss@8.5.3)
      postcss-nested: 6.2.0(postcss@8.5.3)
      postcss-selector-parser: 6.1.2
      resolve: 1.22.10
      sucrase: 3.35.0
    transitivePeerDependencies:
      - ts-node

  thenify-all@1.6.0:
    dependencies:
      thenify: 3.3.1

  thenify@3.3.1:
    dependencies:
      any-promise: 1.3.0

  tiny-invariant@1.3.3: {}

  to-regex-range@5.0.1:
    dependencies:
      is-number: 7.0.0

  toggle-selection@1.0.6: {}

  trim-lines@3.0.1: {}

  trough@2.2.0: {}

  ts-interface-checker@0.1.13: {}

  tslib@2.4.0: {}

  tslib@2.8.1: {}

  typeorm@0.3.7(ioredis@5.6.1):
    dependencies:
      '@sqltools/formatter': 1.2.5
      app-root-path: 3.1.0
      buffer: 6.0.3
      chalk: 4.1.2
      cli-highlight: 2.1.11
      date-fns: 2.30.0
      debug: 4.4.0
      dotenv: 16.5.0
      glob: 7.2.3
      js-yaml: 4.1.0
      mkdirp: 1.0.4
      reflect-metadata: 0.1.14
      sha.js: 2.4.11
      tslib: 2.8.1
      uuid: 8.3.2
      xml2js: 0.4.23
      yargs: 17.7.2
    optionalDependencies:
      ioredis: 5.6.1
    transitivePeerDependencies:
      - supports-color

  typescript@5.8.3: {}

  undici-types@6.19.8: {}

  unified@11.0.5:
    dependencies:
      '@types/unist': 3.0.3
      bail: 2.0.2
      devlop: 1.1.0
      extend: 3.0.2
      is-plain-obj: 4.1.0
      trough: 2.2.0
      vfile: 6.0.3

  unist-util-find-after@5.0.0:
    dependencies:
      '@types/unist': 3.0.3
      unist-util-is: 6.0.0

  unist-util-is@6.0.0:
    dependencies:
      '@types/unist': 3.0.3

  unist-util-position@5.0.0:
    dependencies:
      '@types/unist': 3.0.3

  unist-util-stringify-position@4.0.0:
    dependencies:
      '@types/unist': 3.0.3

  unist-util-visit-parents@6.0.1:
    dependencies:
      '@types/unist': 3.0.3
      unist-util-is: 6.0.0

  unist-util-visit@5.0.0:
    dependencies:
      '@types/unist': 3.0.3
      unist-util-is: 6.0.0
      unist-util-visit-parents: 6.0.1

  universalify@2.0.1: {}

  update-browserslist-db@1.1.3(browserslist@4.24.5):
    dependencies:
      browserslist: 4.24.5
      escalade: 3.2.0
      picocolors: 1.1.1

  use-callback-ref@1.3.3(@types/react@18.3.21)(react@18.2.0):
    dependencies:
      react: 18.2.0
      tslib: 2.8.1
    optionalDependencies:
      '@types/react': 18.3.21

  use-sidecar@1.1.3(@types/react@18.3.21)(react@18.2.0):
    dependencies:
      detect-node-es: 1.1.0
      react: 18.2.0
      tslib: 2.8.1
    optionalDependencies:
      '@types/react': 18.3.21

  util-deprecate@1.0.2: {}

  uuid@11.1.0: {}

  uuid@8.3.2: {}

  vfile-location@5.0.3:
    dependencies:
      '@types/unist': 3.0.3
      vfile: 6.0.3

  vfile-message@4.0.2:
    dependencies:
      '@types/unist': 3.0.3
      unist-util-stringify-position: 4.0.0

  vfile@6.0.3:
    dependencies:
      '@types/unist': 3.0.3
      vfile-message: 4.0.2

  wcwidth@1.0.1:
    dependencies:
      defaults: 1.0.4

  web-namespaces@2.0.1: {}

  web-streams-polyfill@3.3.3: {}

  which@2.0.2:
    dependencies:
      isexe: 2.0.0

  wrap-ansi@7.0.0:
    dependencies:
      ansi-styles: 4.3.0
      string-width: 4.2.3
      strip-ansi: 6.0.1

  wrap-ansi@8.1.0:
    dependencies:
      ansi-styles: 6.2.1
      string-width: 5.1.2
      strip-ansi: 7.1.0

  wrappy@1.0.2: {}

  xml2js@0.4.23:
    dependencies:
      sax: 1.4.1
      xmlbuilder: 11.0.1

  xmlbuilder@11.0.1: {}

  xtend@4.0.2: {}

  y18n@5.0.8: {}

  yallist@4.0.0: {}

  yaml@1.10.2: {}

  yaml@2.7.1: {}

  yargs-parser@20.2.9: {}

  yargs-parser@21.1.1: {}

  yargs@16.2.0:
    dependencies:
      cliui: 7.0.4
      escalade: 3.2.0
      get-caller-file: 2.0.5
      require-directory: 2.1.1
      string-width: 4.2.3
      y18n: 5.0.8
      yargs-parser: 20.2.9

  yargs@17.7.2:
    dependencies:
      cliui: 8.0.1
      escalade: 3.2.0
      get-caller-file: 2.0.5
      require-directory: 2.1.1
      string-width: 4.2.3
      y18n: 5.0.8
      yargs-parser: 21.1.1

  zod@3.24.4: {}

  zwitch@2.0.4: {}

```


## frontend/postcss.config.js

```js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

```


## frontend/src/app/api/ai/chat/stream/route.ts

```ts
import { NextRequest } from "next/server";
export const runtime = "edge";
const BASE = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || "http://backend:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const body = await req.text();
  const headers = new Headers({ "Content-Type": "application/json", Accept: "text/event-stream" });
  const auth = req.headers.get("authorization");
  if (auth) headers.set("authorization", auth);

  const r = await fetch(`${BASE}/api/v1/langgraph/chat/stream2`, { method: "POST", headers, body });
  return new Response(r.body, {
    status: r.status,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform, no-store", Connection: "keep-alive", "X-Accel-Buffering": "no" }
  });
}

```


## frontend/src/app/api/auth/[...nextauth]/route.ts

```ts
import NextAuth, { type NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";

const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },

  providers: [
    KeycloakProvider({
      issuer: process.env.KEYCLOAK_ISSUER,
      clientId: process.env.KEYCLOAK_CLIENT_ID!,
      clientSecret: process.env.KEYCLOAK_CLIENT_SECRET || "dummy",
      authorization: { params: { scope: "openid profile email" } },
    }),
  ],

  callbacks: {
    // legt das access/id/refresh token beim ersten Login in den JWT und erneuert es ggf.
    async jwt({ token, account }) {
      if (account) {
        (token as any).accessToken  = (account as any).access_token ?? null;
        (token as any).idToken      = (account as any).id_token ?? null;
        (token as any).refreshToken = (account as any).refresh_token ?? null;
        (token as any).expires_at   = (account as any).expires_at ?? null; // epoch seconds
      }
      return token;
    },

    // macht Tokens in der Client-Session verfügbar
    async session({ session, token }) {
      (session as any).accessToken = (token as any).accessToken ?? null;
      (session as any).idToken     = (token as any).idToken ?? null;
      (session as any).expires_at  = (token as any).expires_at ?? null;
      return session;
    },
  },

  pages: {
    signIn: "/auth/signin",
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };

```


## frontend/src/app/api/auth/custom-logout/route.ts

```ts
import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  // Legacy-Route -> auf neue SSO-Logout-Route umleiten
  const base = process.env.NEXTAUTH_URL || req.nextUrl.origin;
  return NextResponse.redirect(`${base}/api/auth/sso-logout`);
}

export const dynamic = "force-dynamic";

```


## frontend/src/app/api/auth/sso-logout/route.ts

```ts
import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    const issuer = (process.env.KEYCLOAK_ISSUER ?? "").replace(/\/$/, "");
    const base = process.env.NEXTAUTH_URL || req.nextUrl.origin;
    const clientId = process.env.KEYCLOAK_CLIENT_ID!;
    if (!issuer || !clientId) throw new Error("Missing KEYCLOAK_ISSUER or KEYCLOAK_CLIENT_ID");

    const jwt = (await getToken({ req }).catch(() => null)) as any;
    const idToken = jwt?.idToken;

    // Nach Keycloak-Logout auf Seite leiten, die NextAuth signOut automatisch POSTet
    const postLogout = new URL("/auth/signed-out", base);

    const url = new URL(`${issuer}/protocol/openid-connect/logout`);
    url.searchParams.set("client_id", clientId);
    url.searchParams.set("post_logout_redirect_uri", postLogout.toString());
    if (idToken) url.searchParams.set("id_token_hint", idToken);

    return NextResponse.redirect(url.toString());
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "logout_build_failed" }, { status: 500 });
  }
}

// Akzeptiere POST ebenfalls
export const POST = GET;

```


## frontend/src/app/api/ccx/jobs/[jobId]/events/route.js

```js
export const dynamic = "force-dynamic";

export async function GET() {
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const send = (obj) => controller.enqueue(enc.encode(`data: ${JSON.stringify(obj)}\n\n`));
      send({ status: "running" });
      setTimeout(() => { send({ status: "finished", converged: true }); controller.close(); }, 500);
    }
  });
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive"
    }
  });
}

```


## frontend/src/app/api/ccx/jobs/[jobId]/summary/route.js

```js
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

function fileUrlIfExists(dir, jobId, ext) {
  const p = path.join(dir, `${jobId}.${ext}`);
  return fs.existsSync(p) ? `/files/${jobId}.${ext}` : undefined;
}

function tailLines(p, n = 50) {
  try {
    const txt = fs.readFileSync(p, "utf8");
    const lines = txt.split(/\r?\n/).filter(Boolean);
    return lines.slice(-n);
  } catch {
    return [];
  }
}

export async function GET(_req, { params }) {
  const jobId = params?.jobId ?? "unknown";
  const filesDir = process.env.JOB_FILES_DIR
    ? path.resolve(process.env.JOB_FILES_DIR)
    : path.join(process.cwd(), "public", "files");

  const datP = path.join(filesDir, `${jobId}.dat`);
  const frdP = path.join(filesDir, `${jobId}.frd`);
  const msgP = path.join(filesDir, `${jobId}.msg`);

  const logTail =
    tailLines(msgP, 50).length ? tailLines(msgP, 50)
    : tailLines(datP, 50).length ? tailLines(datP, 50)
    : tailLines(frdP, 50).length ? tailLines(frdP, 50)
    : ["kein Log verfügbar"];

  const body = {
    jobId,
    jobName: jobId,
    version: "2.22",
    status: "finished",
    runtimeSec: 0.01,
    converged: true,
    iterations: 1,
    lastUpdated: new Date().toISOString(),
    files: {
      dat: fileUrlIfExists(filesDir, jobId, "dat"),
      frd: fileUrlIfExists(filesDir, jobId, "frd"),
      vtu: fileUrlIfExists(filesDir, jobId, "vtu"),
    },
    logTail,
  };

  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}

```


## frontend/src/app/api/ccx/jobs/route.js

```js
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

/**
 * Listet vorhandene CCX-Jobs aus JOB_FILES_DIR oder ./public/files.
 * Ein Job gilt als finished, wenn .frd existiert.
 */
export async function GET() {
  const filesDir = process.env.JOB_FILES_DIR
    ? path.resolve(process.env.JOB_FILES_DIR)
    : path.join(process.cwd(), "public", "files");

  let entries = [];
  try {
    entries = fs.readdirSync(filesDir);
  } catch {
    return new Response(JSON.stringify({ jobs: [] }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  const jobIds = new Set(
    entries
      .map((f) => /^(.+)\.(dat|frd|vtu|msg)$/i.exec(f)?.[1])
      .filter(Boolean)
  );

  const jobs = Array.from(jobIds).map((jobId) => {
    const p = (ext) => path.join(filesDir, `${jobId}.${ext}`);
    const has = (ext) => fs.existsSync(p(ext));
    const mtimes = ["msg", "dat", "frd", "vtu"]
      .filter(has)
      .map((ext) => fs.statSync(p(ext)).mtimeMs);
    const lastUpdated =
      mtimes.length ? new Date(Math.max(...mtimes)).toISOString() : null;

    return {
      jobId,
      status: has("frd") ? "finished" : has("dat") ? "running" : "queued",
      lastUpdated,
      files: {
        dat: has("dat") ? `/files/${jobId}.dat` : undefined,
        frd: has("frd") ? `/files/${jobId}.frd` : undefined,
        vtu: has("vtu") ? `/files/${jobId}.vtu` : undefined,
      },
    };
  });

  return new Response(JSON.stringify({ jobs }), {
    headers: { "Content-Type": "application/json" },
  });
}

```


## frontend/src/app/api/langgraph/chat/[conversationId]/chat_stream/route.ts

```ts
// WS-only: SSE-Proxy deaktiviert.
// Gibt 410 zurück, damit nichts mehr über SSE läuft.

export const runtime = "edge";
export const dynamic = "force-dynamic";

function gone() {
  return new Response(
    JSON.stringify({
      error: "SSE removed. Please use WebSocket at /api/v1/ai/ws.",
    }),
    {
      status: 410,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    }
  );
}

export async function GET() {
  return gone();
}

export async function POST() {
  return gone();
}

```


## frontend/src/app/api/langgraph/chat/route.ts

```ts
import { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";
export const dynamic = "force-dynamic";

const BASE = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || "http://backend:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  let accessToken: string | undefined;
  if (authHeader?.startsWith("Bearer ")) accessToken = authHeader.slice(7);
  else {
    const token = await getToken({ req });
    if (token && typeof token === "object") accessToken = (token as any).accessToken || (token as any).access_token;
  }
  if (!accessToken) return new Response("Unauthorized", { status: 401, headers: { "Cache-Control": "no-store" } });

  const body = await req.text();
  const r = await fetch(`${BASE}/api/v1/langgraph/chat/stream`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json", Accept: "text/event-stream" },
    body
  });
  return new Response(r.body, {
    status: r.status,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform, no-store", Connection: "keep-alive", "X-Accel-Buffering": "no" }
  });
}

```


## frontend/src/app/auth/error/error-client.tsx

```tsx
'use client'

import { useSearchParams, useRouter } from 'next/navigation'

export default function ErrorClient() {
  const params = useSearchParams()
  const router = useRouter()
  const error = params?.get('error') || 'Unbekannter Fehler'

  return (
    <div className="flex h-screen items-center justify-center bg-gray-100 p-4">
      <div className="max-w-md bg-white rounded shadow-lg p-8 text-center">
        <h1 className="text-2xl font-bold mb-4">Anmeldefehler</h1>
        <p className="mb-4 text-red-600">{error}</p>
        <button
          onClick={() => router.replace('/auth/signin')}
          className="mt-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
        >
          Zurück zur Anmeldung
        </button>
      </div>
    </div>
  )
}

```


## frontend/src/app/auth/error/page.tsx

```tsx
// src/app/auth/error/page.tsx
import React, { Suspense } from 'react'
import ErrorClient from './error-client'

export const dynamic = 'force-dynamic'  // zwingt dynamisches Rendering

export default function ErrorPage() {
  return (
    <Suspense fallback={<div>Lade Fehlerseite…</div>}>
      <ErrorClient />
    </Suspense>
  )
}

```


## frontend/src/app/auth/signin/page.tsx

```tsx
'use client';

import { signIn } from 'next-auth/react';

export default function SignIn() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <button
        onClick={() => signIn('keycloak', { callbackUrl: `${process.env.NEXT_PUBLIC_SITE_URL || window.location.origin}/dashboard` })}
        className="px-6 py-3 rounded bg-blue-600 text-white hover:bg-blue-700"
      >
        Sign in with Keycloak
      </button>
    </div>
  );
}

```


## frontend/src/app/auth/signin/signin-client.tsx

```tsx
'use client'

import { signIn } from 'next-auth/react'

export default function SignInButton() {
  return (
    <button
      onClick={() =>
        signIn('keycloak', { callbackUrl: '/dashboard' })  // ← wichtig!
      }
      className="px-6 py-3 rounded bg-blue-600 text-white hover:bg-blue-700"
    >
      <span className="mr-2 inline-block">
        <img src="/keycloak.svg" alt="" width={20} height={20} />
      </span>
      Sign in with Keycloak
    </button>
  )
}

```


## frontend/src/app/components/ui/card.tsx

```tsx
// 📁 frontend/src/app/components/ui/card.tsx

import * as React from "react";
// vorher: import { cn } from "@lib/utils";
// korrekt mit dem Slash nach @:
import { cn } from "@/lib/utils";

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800",
      className
    )}
    {...props}
  />
));
Card.displayName = "Card";

export { Card };

```


## frontend/src/app/dashboard/ChatScreen.tsx

```tsx
'use client';
import Chat from './components/Chat/ChatContainer';

export default function ChatScreen() {
  return <Chat />;
}

```


## frontend/src/app/dashboard/Dashboard.tsx

```tsx
import Chat from "./components/Chat/ChatContainer";
// import FormResultsCards from "./components/FormResultsCards";
// import SidebarForm from "./components/Sidebar/SidebarForm";

export default function Dashboard() {
  return (
    <>
      <Chat />
      {/* <FormResultsCards /> */}
      {/* <SidebarForm /> */}
    </>
  );
}

```


## frontend/src/app/dashboard/DashboardClient.tsx

```tsx
'use client';

import { useSession, signIn } from 'next-auth/react';
import { useEffect } from 'react';
import ChatContainer from "./components/Chat/ChatContainer";

export default function DashboardClient() {
  const { status } = useSession();

  useEffect(() => {
    if (status === 'unauthenticated') {
      const base = process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
      signIn('keycloak', { callbackUrl: `${base}/dashboard` });
    }
  }, [status]);

  if (status === 'loading') {
    return <div className="flex items-center justify-center min-h-screen text-lg text-gray-500">Lade Authentifizierung …</div>;
  }

  return status === 'authenticated'
    ? <ChatContainer />
    : <div className="flex items-center justify-center min-h-screen text-lg text-gray-500">Weiterleitung zum Login …</div>;
}

```


## frontend/src/app/dashboard/DashboardShell.tsx

```tsx
"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { logout } from "../../lib/logout";
import SidebarLeft from "./components/Sidebar/SidebarLeft";

function LogoutButton() {
  const { status } = useSession();
  if (status !== "authenticated") return null;

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error("Logout failed", error);
      window.location.assign("/");
    }
  };

  return (
    <button
      onClick={handleLogout}
      className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition"
      aria-label="Abmelden"
      title="Abmelden"
    >
      <span className="i-logout h-[14px] w-[14px] inline-block" />
      Abmelden
    </button>
  );
}

export default function DashboardShell({ children }: { children: ReactNode }) {
  const [showAskMissing, setShowAskMissing] = useState(false);

  useEffect(() => {
    const onUi = (ev: Event) => {
      const ua: any = (ev as CustomEvent<any>).detail ?? (ev as any);
      const action = ua?.ui_action ?? ua?.action ?? ua?.event;
      try { console.debug("[sealai] UI event received", ua); } catch {}
      if (action) setShowAskMissing(true);
    };
    window.addEventListener("sealai:ui", onUi as EventListener);
    window.addEventListener("sealai:ui_action", onUi as EventListener);
    window.addEventListener("sai:need-params", onUi as EventListener);
    return () => {
      window.removeEventListener("sealai:ui", onUi as EventListener);
      window.removeEventListener("sealai:ui_action", onUi as EventListener);
      window.removeEventListener("sai:need-params", onUi as EventListener);
    };
  }, []);

  return (
    <div className="min-h-screen w-full bg-white">
      <header className="sticky top-0 z-30 flex items-center justify-end px-4 py-3 bg-white/80 backdrop-blur border-b">
        <LogoutButton />
      </header>
      <div className="flex min-h-[calc(100vh-56px)]">
        <SidebarLeft open={showAskMissing} onOpenChange={(v) => setShowAskMissing(v)} />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}

```


## frontend/src/app/dashboard/ccx/[jobId]/page.tsx

```tsx
export const dynamic = "force-dynamic";
export const revalidate = 0;

import CcxResultCard from "../../components/CcxResultCard";

export default function Page(props: { params?: { jobId?: string } }) {
  const jobId = props?.params?.jobId ?? "";
  return (
    <div className="p-6">
      {jobId ? (
        <CcxResultCard jobId={jobId} />
      ) : (
        <div className="text-sm text-zinc-500">Keine Job-ID übergeben.</div>
      )}
    </div>
  );
}

```


## frontend/src/app/dashboard/ccx/page.tsx

```tsx
export const dynamic = "force-dynamic";
export const revalidate = 0;

// Server Component – KEIN "use client", KEINE Hooks.
// "params" ist optional, damit kein Runtime-Fehler entsteht.
export default function CcxPage(props: { params?: { chatId?: string } }) {
  const chatId = props?.params?.chatId ?? null;

  return (
    <main className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-semibold tracking-tight">CCX</h1>
      <p className="text-zinc-600 dark:text-zinc-300 mt-2">
        {chatId ? <>Chat-ID: <code>{chatId}</code></> : "Keine Chat-ID übergeben."}
      </p>
    </main>
  );
}

```


## frontend/src/app/dashboard/components/CcxResultCard.tsx

```tsx
'use client';
import React, { useEffect, useMemo, useState } from "react";

type CcxSummary = {
  jobId: string;
  jobName: string;
  version?: string;
  status: "queued" | "running" | "finished" | "error";
  runtimeSec?: number;
  converged?: boolean;
  iterations?: number;
  lastUpdated?: string; // ISO-8601
  files?: { dat?: string; frd?: string; vtu?: string };
  logTail?: string[]; // last N lines
};

function fmtSec(s?: number): string {
  if (s === undefined || s === null) return "–";
  if (s < 60) return `${s.toFixed(2)} s`;
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}m ${r.toFixed(1)}s`;
}

function Pill({
  label,
  tone,
}: {
  label: string;
  tone: "ok" | "warn" | "err" | "muted";
}) {
  const map = {
    ok: "bg-green-100 text-green-700",
    warn: "bg-amber-100 text-amber-700",
    err: "bg-red-100 text-red-700",
    muted: "bg-gray-100 text-gray-600",
  } as const;
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${map[tone]}`}>
      {label}
    </span>
  );
}

export default function CcxResultCard({ jobId }: { jobId: string }) {
  const [data, setData] = useState<CcxSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);

  async function load() {
    try {
      setLoading(true);
      setErr(null);
      const res = await fetch(
        `/api/ccx/jobs/${encodeURIComponent(jobId)}/summary`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = (await res.json()) as CcxSummary;
      setData(j);
    } catch (e: any) {
      setErr(e?.message ?? "Fetch error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const es = new EventSource(
      `/api/ccx/jobs/${encodeURIComponent(jobId)}/events`
    );
    es.onmessage = (ev) => {
      try {
        const patch = JSON.parse(ev.data) as Partial<CcxSummary>;
        setData((prev) => ({ ...(prev ?? ({} as CcxSummary)), ...patch }));
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => {
      /* auto-retry by browser */
    };
    return () => es.close();
  }, [jobId]);

  const statusPill = useMemo(() => {
    if (!data) return <Pill label="lädt…" tone="muted" />;
    const map: Record<CcxSummary["status"], JSX.Element> = {
      queued: <Pill label="Wartend" tone="muted" />,
      running: <Pill label="Läuft" tone="warn" />,
      finished: (
        <Pill
          label={data.converged ? "Fertig · konvergiert" : "Fertig"}
          tone={data.converged ? "ok" : "muted"}
        />
      ),
      error: <Pill label="Fehler" tone="err" />,
    };
    return map[data.status];
  }, [data]);

  const files = data?.files ?? {};

  return (
    <div className="rounded-2xl border border-gray-200 p-4 shadow-sm bg-white">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm text-gray-500">CalculiX Ergebnis</h3>
          <div className="mt-0.5 text-lg font-semibold">
            {data?.jobName ?? jobId}
          </div>
        </div>
        {statusPill}
      </div>

      <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div className="p-2 rounded-xl bg-gray-50">
          <div className="text-gray-500">Version</div>
          <div className="font-medium">{data?.version ?? "–"}</div>
        </div>
        <div className="p-2 rounded-xl bg-gray-50">
          <div className="text-gray-500">Laufzeit</div>
          <div className="font-medium">{fmtSec(data?.runtimeSec)}</div>
        </div>
        <div className="p-2 rounded-xl bg-gray-50">
          <div className="text-gray-500">Iterationen</div>
          <div className="font-medium">{data?.iterations ?? "–"}</div>
        </div>
        <div className="p-2 rounded-xl bg-gray-50">
          <div className="text-gray-500">Aktualisiert</div>
          <div className="font-medium">
            {data?.lastUpdated
              ? new Date(data.lastUpdated).toLocaleString()
              : "–"}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <a
          className={`px-3 py-1.5 rounded-lg text-sm ${
            files.dat
              ? "border hover:bg-gray-50"
              : "border-dashed border text-gray-400 cursor-not-allowed"
          }`}
          href={files.dat ?? "#"}
          onClick={(e) => {
            if (!files.dat) e.preventDefault();
          }}
        >
          {files.dat ? "Download .dat" : "kein .dat"}
        </a>
        <a
          className={`px-3 py-1.5 rounded-lg text-sm ${
            files.frd
              ? "border hover:bg-gray-50"
              : "border-dashed border text-gray-400 cursor-not-allowed"
          }`}
          href={files.frd ?? "#"}
          onClick={(e) => {
            if (!files.frd) e.preventDefault();
          }}
        >
          {files.frd ? "Download .frd" : "kein .frd"}
        </a>
        <a
          className={`px-3 py-1.5 rounded-lg text-sm ${
            files.vtu
              ? "border hover:bg-gray-50"
              : "border-dashed border text-gray-400 cursor-not-allowed"
          }`}
          href={files.vtu ?? "#"}
          onClick={(e) => {
            if (!files.vtu) e.preventDefault();
          }}
        >
          {files.vtu ? "Download .vtu" : "kein .vtu (Export nötig)"}
        </a>
      </div>

      <button
        onClick={() => setShowLog((v) => !v)}
        className="mt-4 text-xs text-gray-600 underline"
        type="button"
      >
        {showLog ? "Log ausblenden" : "Log einblenden"}
      </button>

      {showLog && (
        <pre className="mt-2 max-h-48 overflow-auto text-xs bg-black text-green-200 p-3 rounded-xl">
{(data?.logTail ??
  (loading ? ["lade…"] : err ? [err] : ["kein Log verfügbar"])
).join("\n")}
        </pre>
      )}
    </div>
  );
}

```


## frontend/src/app/dashboard/components/Chat/ChatContainer.tsx

```tsx
'use client';

import { useSession } from "next-auth/react";
import { useAccessToken } from "@/lib/useAccessToken";
import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import ChatHistory from "./ChatHistory";
import Thinking from "./Thinking";
import ChatInput from "./ChatInput";
import type { Message } from "@/types/chat";
import { useChatWs } from "@/lib/useChatWs";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ChatContainer() {
  const { data: session, status } = useSession();
  const isAuthed = status === "authenticated";

  const chatId = "default";
  const token = useAccessToken();
  const { connected, streaming, text, lastError, send, cancel } =
    useChatWs({ chatId, token });

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [hasStarted, setHasStarted] = useState(false);

  // === Scroll "anchor-then-hold" ===
  const scrollRef = useRef<HTMLDivElement>(null);
  const anchorRef = useRef<HTMLDivElement>(null);
  const prevStreamingRef = useRef(streaming);
  const [autoAnchor, setAutoAnchor] = useState(false);
  const targetTopRef = useRef<number | null>(null);

  const cancelAutoAnchor = useCallback(() => {
    targetTopRef.current = null;
    setAutoAnchor(false);
  }, []);

  const onScroll = useCallback(() => {
    if (!autoAnchor || targetTopRef.current == null) return;
    const cont = scrollRef.current;
    if (!cont) return;
    if (Math.abs(cont.scrollTop - targetTopRef.current) > 150) cancelAutoAnchor();
  }, [autoAnchor, cancelAutoAnchor]);

  const onWheel = cancelAutoAnchor;
  const onTouchStart = cancelAutoAnchor;

  // Beim Streamstart Anker ins obere Drittel
  useEffect(() => {
    const was = prevStreamingRef.current;
    prevStreamingRef.current = streaming;
    if (!was && streaming) {
      requestAnimationFrame(() => {
        const cont = scrollRef.current;
        const anchor = anchorRef.current;
        if (!cont || !anchor) return;
        const desiredTop = Math.max(0, anchor.offsetTop - Math.round(cont.clientHeight / 3));
        targetTopRef.current = desiredTop;
        setAutoAnchor(true);
        cont.scrollTo({ top: desiredTop, behavior: "smooth" });
      });
    }
  }, [streaming]);

  // Während des Streams dezent nachführen
  useEffect(() => {
    if (!streaming || !autoAnchor) return;
    const cont = scrollRef.current;
    const t = targetTopRef.current;
    if (!cont || t == null) return;
    if (Math.abs(cont.scrollTop - t) > 40) cont.scrollTo({ top: t, behavior: "auto" });
  }, [text, streaming, autoAnchor]);

  // Nach Streamende lösen
  useEffect(() => {
    if (!streaming) {
      targetTopRef.current = null;
      setAutoAnchor(false);
    }
  }, [streaming]);

  // ==== WICHTIG: Live-Text in History mergen – nur wenn text !== '' ====
  useEffect(() => {
    if (text === "") return; // verhindert, dass am Ende/leeren Start etwas überschrieben wird
    setMessages((prev) => {
      const lastIdx = prev.length - 1;
      if (lastIdx >= 0 && prev[lastIdx].role === "assistant") {
        const copy = [...prev];
        copy[lastIdx] = { ...copy[lastIdx], content: text };
        return copy;
      }
      return [...prev, { role: "assistant", content: text }];
    });
  }, [text]); // absichtlich NUR von text abhängig

  // History während Streaming ohne die live-assistant-Zeile
  const historyMessages = useMemo(() => {
    if (!streaming || messages.length === 0) return messages;
    const last = messages[messages.length - 1];
    return last.role === "assistant" ? messages.slice(0, -1) : messages;
  }, [messages, streaming]);

  const firstName = (session?.user?.name || "").split(" ")[0] || "";
  const sendingDisabled = !isAuthed || !connected;
  const isInitial = messages.length === 0 && !hasStarted;

  const handleSend = useCallback((msg: string) => {
    if (sendingDisabled) return;
    const content = msg.trim();
    if (!content) return;
    setMessages((m) => [...m, { role: "user", content }]);
    setHasStarted(true);
    send(content);
    setInputValue("");
  }, [sendingDisabled, send]);

  const hasFirstToken = text.trim().length > 0;

  return (
    <div className="flex flex-col h-full w-full bg-transparent relative">
      {isInitial ? (
        <div className="flex min-h-[80vh] w-full items-center justify-center">
          <div className="w-full max-w-[768px] px-4">
            <div className="text-2xl md:text-3xl font-bold text-gray-800 text-center leading-tight select-none">
              Willkommen zurück{firstName ? `, ${firstName}` : ""}!
            </div>
            <div className="text-base md:text-lg text-gray-500 mb-3 text-center leading-snug font-medium select-none">
              Schön, dass du hier bist.
            </div>
            <div className="text-xs text-center mb-4">
              {isAuthed ? (
                connected ? <span className="text-emerald-600">WebSocket verbunden</span>
                          : <span className="text-amber-600">Verbinde WebSocket…</span>
              ) : <span className="text-gray-500">Bitte anmelden</span>}
            </div>

            <ChatInput
              value={inputValue}
              setValue={setInputValue}
              onSend={handleSend}
              onStop={() => cancel()}
              disabled={sendingDisabled}
              streaming={streaming}
              placeholder={
                isAuthed
                  ? (connected ? "Was möchtest du wissen?" : "Verbinde…")
                  : "Bitte anmelden, um zu schreiben"
              }
            />

            {!isAuthed && (
              <div className="mt-2 text-xs text-gray-500 text-center">
                Du musst angemeldet sein, um Nachrichten zu senden.
              </div>
            )}
            {lastError && (
              <div className="mt-2 text-xs text-red-500 text-center select-none">
                Fehler: {lastError}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          {/* Scroll-Container */}
          <div
            ref={scrollRef}
            onScroll={onScroll}
            onWheel={onWheel}
            onTouchStart={onTouchStart}
            className="flex-1 overflow-y-auto w-full pb-36"
            style={{ minHeight: 0 }}
          >
            <ChatHistory messages={historyMessages} />

            {/* Anker vor der Live-Bubble */}
            <div ref={anchorRef} aria-hidden />

            {/* Live-Stream-Bubble */}
            {streaming && (
              <div className="w-full max-w-[768px] mx-auto px-4 py-2">
                <div className="inline-flex items-start gap-2">
                  {!hasFirstToken ? <Thinking /> : null}
                  <div className="max-w-[680px] chat-markdown cm-assistant">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {text || (hasFirstToken ? "" : " ")}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Eingabe */}
          <div className="sticky bottom-0 left-0 right-0 z-20 flex justify-center bg-transparent pb-0 w-full">
            <div className="w-full max-w-[768px] pointer-events-auto">
              <ChatInput
                value={inputValue}
                setValue={setInputValue}
                onSend={handleSend}
                onStop={() => cancel()}
                disabled={sendingDisabled}
                streaming={streaming}
                placeholder={
                  isAuthed
                    ? (connected ? "Was möchtest du wissen?" : "Verbinde…")
                    : "Bitte anmelden, um zu schreiben"
                }
              />
              {!isAuthed && (
                <div className="mt-2 text-xs text-gray-500">
                  Du musst angemeldet sein, um Nachrichten zu senden.
                </div>
              )}
              {lastError && (
                <div className="mt-2 text-xs text-red-500 select-none">
                  Fehler: {lastError}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

```


## frontend/src/app/dashboard/components/Chat/ChatHistory.tsx

```tsx
// frontend/src/app/dashboard/components/Chat/ChatHistory.tsx
'use client';

import React, { memo } from 'react';
import type { Message } from '@/types/chat';
import MarkdownMessage from './MarkdownMessage';

type Props = {
  messages: Message[];
  className?: string;
};

function ChatHistoryBase({ messages, className }: Props) {
  if (!messages || messages.length === 0) return null;

  return (
    <div className={className}>
      <div className="w-full max-w-[768px] mx-auto px-4 py-4 space-y-6">
        {messages.map((m, i) => {
          const isUser = m.role === 'user';
          // >>> stabile Keys: NICHT vom (sich ändernden) Inhalt ableiten!
          const key = `m-${i}-${m.role}`;

          return (
            <div key={key} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={[
                  'max-w-[680px]',
                  'rounded-2xl',
                  'px-4 py-3',
                  'shadow-sm',
                  isUser
                    ? 'bg-blue-600 text-white cm-user'
                    : 'bg-white text-gray-900 cm-assistant',
                ].join(' ')}
              >
                {isUser ? (
                  <div className="whitespace-pre-wrap break-words leading-relaxed">
                    {m.content}
                  </div>
                ) : (
                  <MarkdownMessage>{m.content || ''}</MarkdownMessage>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const ChatHistory = memo(ChatHistoryBase);
export default ChatHistory;

```


## frontend/src/app/dashboard/components/Chat/ChatInput.tsx

```tsx
'use client';

import React, { useRef, useEffect, useCallback } from 'react';

interface ChatInputProps {
  value: string;
  setValue: (v: string) => void;
  onSend?: (value: string) => void;
  onStop?: () => void;
  /** Bedeutet: Senden-Button sperren – NICHT das Tippen */
  disabled?: boolean;
  streaming?: boolean;
  placeholder?: string;
}

/**
 * ChatInput – tippen immer möglich, auch offline.
 * Nur Senden/Stop werden je nach Status deaktiviert.
 */
export default function ChatInput({
  value,
  setValue,
  onSend,
  onStop,
  disabled = false,   // -> sperrt NUR Buttons
  streaming = false,  // -> sperrt Textarea (während Stream)
  placeholder = 'Was möchtest du wissen?',
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // --- Autosize Textarea, max 4 Zeilen (~104px) ---
  const autosize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const next = Math.min(el.scrollHeight, 104);
    el.style.height = `${next}px`;
  }, []);

  useEffect(() => {
    autosize();
  }, [value, autosize]);

  const focusTextarea = useCallback(() => {
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, []);

  const doSend = useCallback(() => {
    const text = value.trim();
    if (!onSend || !text) return;
    onSend(text);
    setValue('');
    focusTextarea();
  }, [onSend, setValue, value, focusTextarea]);

  const doStop = useCallback(() => {
    if (onStop) onStop();
    focusTextarea();
  }, [onStop, focusTextarea]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Während Streaming nicht senden
    if (streaming) return;

    // Shift+Enter = Zeilenumbruch
    if (e.key === 'Enter' && e.shiftKey) return;

    // Enter / Ctrl+Enter senden – aber nur, wenn Buttons nicht gesperrt
    if ((e.key === 'Enter' && !e.shiftKey) || (e.key === 'Enter' && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      if (!disabled) doSend();
    }
  };

  const canSend = !disabled && !streaming && value.trim().length > 0;
  const canStop = !disabled && streaming;

  return (
    <div
      className="flex flex-col w-full items-center"
      style={{ maxWidth: '768px', minWidth: '320px', width: '100%' }}
    >
      <div
        className={[
          'bg-white rounded-3xl',
          'border border-gray-200',
          'shadow-[0_8px_28px_rgba(60,80,120,0.10)]',
          'flex flex-col justify-between',
          'transition-all',
          // kompaktere Innenabstände
          'px-5 pt-4 pb-3',
          streaming ? 'opacity-90' : '',
        ].join(' ')}
        style={{ minHeight: '92px', maxWidth: '768px', width: '100%' }}
      >
        {/* Eingabe (Textarea): nur während Streaming gesperrt */}
        <textarea
          ref={textareaRef}
          className={[
            'w-full resize-none border-none outline-none bg-transparent',
            'text-[0.97rem] leading-[1.5]',
            'text-gray-900 placeholder-gray-400',
            'min-h-[26px] max-h-[104px]',
            'pr-2 pl-2',
            'transition',
            'scrollbar-thin',
            'overflow-y-auto',
            streaming ? 'cursor-not-allowed' : '',
          ].join(' ')}
          rows={1}
          maxLength={3000}
          autoFocus
          value={value}
          disabled={streaming}             // <-- wichtig: NICHT mehr „disabled || streaming“
          placeholder={
            disabled ? 'Offline – du kannst tippen, Senden ist deaktiviert' : placeholder
          }
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Chat-Eingabe"
          aria-disabled={streaming}
          style={{
            borderRadius: 0,
            fontSize: '0.97rem',
            background: 'transparent',
            minHeight: '26px',
            maxHeight: '104px',
            boxSizing: 'border-box',
            paddingTop: 2,
            paddingBottom: 2,
            paddingLeft: 6,
            paddingRight: 10,
          }}
        />

        {/* Bottom Row */}
        <div className="flex flex-row justify-between items-center mt-2">
          {/* Platzhalter-Button links */}
          <button
            type="button"
            tabIndex={-1}
            className="flex items-center gap-1 px-3 py-1.5 rounded-full text-[11.5px] bg-gray-100 text-gray-700 font-normal select-none shadow-sm hover:bg-gray-200 transition"
            disabled
            aria-disabled="true"
            title="Kompetenz wählen (Demo)"
          >
            🧑‍💼 Kompetenz wählen [Demo]
          </button>

          {/* Rechts: Stop- oder Send-Button */}
          {streaming ? (
            <button
              type="button"
              onClick={doStop}
              disabled={!canStop}
              className={[
                'flex items-center justify-center',
                'h-8 px-3 ml-2',
                'rounded-full',
                'shadow',
                'transition',
                canStop
                  ? 'bg-red-500 hover:bg-red-600 text-white'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed',
              ].join(' ')}
              style={{ zIndex: 20 }}
              aria-label="Stopp"
              title="Stopp"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              type="button"
              onClick={doSend}
              disabled={!canSend}
              className={[
                'flex items-center justify-center',
                'h-8 w-8 ml-2',
                'rounded-full',
                'shadow',
                'transition',
                canSend
                  ? 'bg-[#343541] hover:bg-[#202123] text-white'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed',
              ].join(' ')}
              style={{ zIndex: 20 }}
              aria-label="Senden"
              title={disabled ? 'Offline – Senden deaktiviert' : 'Senden (Enter)'}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* kleine Shortcut-Hilfe */}
      <div className="mt-1.5 text-[11px] text-gray-500">
        {disabled ? 'Offline – du kannst schon tippen; Senden ist aus.' : 'Enter: senden · Shift+Enter: neue Zeile · Strg/⌘+Enter: senden'}
      </div>
    </div>
  );
}

```


## frontend/src/app/dashboard/components/Chat/MarkdownMessage.tsx

```tsx
'use client';

import React, { ReactNode, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import '@/styles/chat-markdown.css';

function CodeBlock({
  inline,
  className,
  children,
  ...rest
}: {
  inline?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const [copied, setCopied] = useState(false);

  if (inline) {
    return (
      <code className="cm-inline" {...rest}>
        {children}
      </code>
    );
  }

  const text =
    typeof children === 'string'
      ? children
      : Array.isArray(children)
      ? children.join('')
      : String(children ?? '');

  const match = /language-([\w-]+)/.exec(className || '');
  const lang = (match?.[1] || 'text').toLowerCase();

  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1100);
    } catch {}
  };

  return (
    <div className="cm-codeblock">
      <div className="cm-codeblock__toolbar">
        <span className="cm-lang">{lang}</span>
        <button className="cm-copy" onClick={doCopy} type="button">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="cm-pre">
        <code className={`language-${lang}`} {...rest}>
          {text}
        </code>
      </pre>
    </div>
  );
}

export default function MarkdownMessage({
  children,
  isUser,
  isTool,
}: {
  children: ReactNode;
  isUser?: boolean;
  isTool?: boolean;
}) {
  // 1) Rohtext ermitteln
  const raw =
    typeof children === 'string'
      ? children
      : Array.isArray(children)
      ? children.filter(Boolean).join('')
      : String(children ?? '');

  // 2) Nur OPTISCH vornweg „…denke nach…“ entfernen (u2026 = Ellipse …)
  const content = raw.replace(
    /^\s*(?:\u2026|\.)*\s*denke\s*nach(?:\s*(?:\u2026|\.))*\s*[:\-–]?\s*/i,
    ''
  );

  const toneClass = isTool ? 'cm-tool' : isUser ? 'cm-user' : 'cm-assistant';

  return (
    <div className={`chat-markdown ${toneClass}`} aria-live="polite">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[]}
        components={{
          h1: (p) => <h1 className="cm-h1" {...p} />,
          h2: (p) => <h2 className="cm-h2" {...p} />,
          h3: (p) => <h3 className="cm-h3" {...p} />,
          h4: (p) => <h4 className="cm-h4" {...p} />,
          p: ({ node, ...props }) => <p className="cm-p" {...props} />,
          a: ({ node, ...props }) => <a className="cm-a" target="_blank" rel="noreferrer" {...props} />,
          ul: (p) => <ul className="cm-ul" {...p} />,
          ol: (p) => <ol className="cm-ol" {...p} />,
          li: (p) => <li className="cm-li" {...p} />,
          blockquote: (p) => <blockquote className="cm-quote" {...p} />,
          hr: () => <hr className="cm-hr" />,
          table: (p) => (
            <div className="cm-tablewrap">
              <table className="cm-table" {...p} />
            </div>
          ),
          thead: (p) => <thead className="cm-thead" {...p} />,
          th: (p) => <th className="cm-th" {...p} />,
          td: (p) => <td className="cm-td" {...p} />,
          img: (p) => <img className="cm-img" {...p} />,
          code: CodeBlock,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

```


## frontend/src/app/dashboard/components/Chat/Thinking.tsx

```tsx
'use client';
export default function Thinking() {
  return (
    <div
      className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
      aria-live="polite"
      role="status"
      title="Antwort wird generiert …"
    >
      <span className="sr-only">Antwort wird generiert …</span>
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '0ms' }} />
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '120ms' }} />
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '240ms' }} />
    </div>
  );
}

```


## frontend/src/app/dashboard/components/InfoBar.tsx

```tsx
'use client';

import { useState } from 'react';
import clsx from 'clsx';
import { XMarkIcon, Bars3Icon } from '@heroicons/react/24/solid';

export default function InfoBar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Drawer */}
      <aside
        className={clsx(
          'fixed right-0 top-0 h-full w-72 bg-white shadow-lg z-40',
          'transition-transform duration-300',
          open ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold">Info</h3>
          <button onClick={() => setOpen(false)}>
            <XMarkIcon className="w-5 h-5 text-gray-500" />
          </button>
        </div>
        <div className="p-4 text-sm leading-relaxed">
          {/* z. B. RAG-Treffer, System-Status, Token-Verbrauch … */}
          Noch keine Inhalte.
        </div>
      </aside>

      {/* Toggle-FAB */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 right-6 z-50 rounded-full p-3 shadow-lg
                   bg-blue-600 text-white hover:bg-blue-700 transition-colors"
      >
        {open ? <XMarkIcon className="w-6 h-6" /> : <Bars3Icon className="w-6 h-6" />}
      </button>
    </>
  );
}

```


## frontend/src/app/dashboard/components/LogoutButton.tsx

```tsx
"use client";

export default function LogoutButton() {
  return (
    <div className="fixed top-4 right-4 z-50">
      <button
        onClick={() => window.location.assign("/api/auth/sso-logout")}
        aria-label="Abmelden"
        className="backdrop-blur-sm bg-white/70 hover:bg-white/90 active:bg-white
                   border border-black/10 shadow-sm rounded-full px-3.5 h-8
                   inline-flex items-center gap-2 text-[13px] font-medium text-gray-800 transition"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 3v7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M6.3 7.5a7.5 7.5 0 1 0 11.4 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
        </svg>
        <span>Abmelden</span>
      </button>
    </div>
  );
}

```


## frontend/src/app/dashboard/components/Sidebar.tsx

```tsx
import Link from "next/link";

export default function Sidebar({ className = "" }: { className?: string }) {
  return (
    <aside className={className + " flex flex-col p-6"}>
      <h2 className="text-2xl font-bold mb-8 dark:text-gray-100">SealAI</h2>
      <nav className="flex-1 space-y-2">
        <Link
          href="/dashboard"
          className="block px-4 py-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
        >
          Chat
        </Link>
        <Link
          href="/dashboard/history"
          className="block px-4 py-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
        >
          Verlauf
        </Link>
      </nav>
    </aside>
  );
}

```


## frontend/src/app/dashboard/components/Sidebar/AccordionTabs.tsx

```tsx
'use client';

import { useState, ReactNode } from 'react';
import {
  ChevronDown,
  ClipboardList,
  MessageCircle,
  Settings,
} from 'lucide-react';

/* -------------------------------------------------
   Typdefinition für eine Accordion-Sektion
--------------------------------------------------*/
interface Section {
  id: 'form' | 'history' | 'settings';
  title: string;
  icon: ReactNode;
  content: ReactNode;
}

/* -------------------------------------------------
   AccordionTabs – vertikale Tabs, die nach unten
   ausklappen. Vollständig animiert mit Tailwind.
--------------------------------------------------*/
export default function AccordionTabs() {
  /* ---------- FIX: null zulassen, damit man alles einklappen kann ---------- */
  const [openId, setOpenId] =
    useState<'form' | 'history' | 'settings' | null>('form');

  /* ---------- Sektionen definieren ---------- */
  const SECTIONS: Section[] = [
    {
      id: 'form',
      title: 'Formular',
      icon: <ClipboardList className="h-4 w-4" />,
      content: (
        <form className="grid grid-cols-1 md:grid-cols-3 gap-4 py-4">
          <input className="border rounded px-3 py-2" placeholder="Feld A" />
          <input className="border rounded px-3 py-2" placeholder="Feld B" />
          <input className="border rounded px-3 py-2" placeholder="Feld C" />
          <textarea
            className="border rounded px-3 py-2 col-span-full"
            rows={4}
            placeholder="Beschreibung"
          />
          <button className="col-span-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition">
            Speichern
          </button>
        </form>
      ),
    },
    {
      id: 'history',
      title: 'Chat-History',
      icon: <MessageCircle className="h-4 w-4" />,
      content: (
        <div className="py-4 space-y-2 text-sm text-gray-600">
          {/* Hier später echten Verlauf laden */}
          <p>(Noch kein Verlauf geladen …)</p>
        </div>
      ),
    },
    {
      id: 'settings',
      title: 'Einstellungen',
      icon: <Settings className="h-4 w-4" />,
      content: (
        <div className="py-4 space-y-3 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" className="accent-blue-600" />
            Dark-Mode&nbsp;aktivieren
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="accent-blue-600" />
            Benachrichtigungen
          </label>
        </div>
      ),
    },
  ];

  /* ---------- Render ---------- */
  return (
    <div className="w-full space-y-2 pr-1 overflow-y-auto">
      {SECTIONS.map(sec => {
        const open = openId === sec.id;
        return (
          <div key={sec.id} className="border rounded-lg bg-white">
            {/* Header / Toggle */}
            <button
              onClick={() => setOpenId(open ? null : sec.id)}
              className={`flex w-full items-center justify-between px-3 py-2 text-sm font-medium
                ${open ? 'bg-blue-600 text-white' : 'bg-gray-50 hover:bg-gray-100 text-gray-700'}`}
            >
              <span className="flex items-center gap-2">
                {sec.icon}
                {sec.title}
              </span>
              <ChevronDown
                className={`h-4 w-4 transform transition-transform ${open ? 'rotate-180' : ''}`}
              />
            </button>

            {/* Panel */}
            <div
              className={`overflow-hidden transition-[max-height] duration-300 ease-in-out
                ${open ? 'max-h-screen' : 'max-h-0'}`}
            >
              {open && <div className="px-3">{sec.content}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

```


## frontend/src/app/dashboard/components/Sidebar/CalcCard.tsx

```tsx
"use client";

import React from "react";
import type { UiAction } from "@/types/ui";

function prettyKey(k: string) {
  if (k === "umfangsgeschwindigkeit_m_s") return "v (m/s)";
  if (k === "surface_speed_m_s") return "v (m/s)";
  if (k === "omega_rad_s") return "ω (rad/s)";
  if (k === "p_bar") return "p (bar)";
  if (k === "p_pa") return "p (Pa)";
  if (k === "p_mpa") return "p (MPa)";
  if (k === "pv_bar_ms") return "PV (bar·m/s)";
  if (k === "pv_mpa_ms") return "PV (MPa·m/s)";
  if (k === "friction_force_n") return "Reibkraft (N)";
  if (k === "friction_power_w") return "Reibleistung (W)";
  return k.replaceAll("_", " ");
}

export default function CalcCard() {
  const [calc, setCalc] = React.useState<Record<string, number | string>>({});
  const [warnings, setWarnings] = React.useState<string[]>([]);

  React.useEffect(() => {
    const handler = (ev: Event) => {
      const detail = (ev as CustomEvent).detail as UiAction | any;
      if (!detail) return;
      const action = (detail.ui_action || "").toString();
      if (action !== "calc_snapshot") return;

      const d = (detail.derived || {}) as any;
      const c = (d.calculated || {}) as Record<string, number | string>;
      setCalc(c);
      setWarnings(Array.isArray(d.warnings) ? d.warnings : []);
    };
    window.addEventListener("sealai:ui_action", handler as EventListener);
    return () => window.removeEventListener("sealai:ui_action", handler as EventListener);
  }, []);

  const entries = Object.entries(calc)
    .filter(([k, v]) => v !== null && v !== undefined && k !== "")
    .sort(([a], [b]) => a.localeCompare(b));

  if (entries.length === 0 && warnings.length === 0) return null;

  return (
    <div className="rounded-2xl border p-4 shadow-sm bg-white/60 dark:bg-zinc-900/60">
      <div className="mb-2 text-sm font-semibold opacity-80">Berechnungen</div>

      <div className="grid grid-cols-1 gap-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between text-sm">
            <span className="opacity-70">{prettyKey(k)}</span>
            <span className="font-mono tabular-nums">
              {typeof v === "number"
                ? (Math.abs(v) < 1e-3 ? v.toExponential(3) : Number(v).toPrecision(6))
                : String(v)}
            </span>
          </div>
        ))}
      </div>

      {warnings.length > 0 && (
        <div className="mt-3 space-y-1">
          {warnings.map((w, i) => (
            <div key={i} className="text-xs text-amber-700 dark:text-amber-300">
              • {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

```


## frontend/src/app/dashboard/components/Sidebar/Sidebar.tsx

```tsx
// frontend/src/app/dashboard/components/Sidebar/Sidebar.tsx

"use client";
interface SidebarProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  tabs: { key: string; label: string }[];
}

export default function Sidebar({
  open,
  setOpen,
  activeTab,
  setActiveTab,
  tabs,
}: SidebarProps) {
  return (
    <aside
      className={`
        fixed top-0 left-0 h-full z-50 bg-white shadow-2xl border-r transition-all duration-300
        ${open ? "w-[35vw] min-w-[320px]" : "w-0 min-w-0"}
        flex flex-col overflow-x-hidden
      `}
      style={{ willChange: "width" }}
    >
      {/* Logo nur einmal ganz oben */}
      {open && (
        <>
          <div className="flex items-center space-x-2 pl-6 pt-6">
            <img src="/logo_sai.svg" alt="SealAI Logo" className="h-8 w-auto" />
            <span className="text-2xl font-semibold text-gray-700">SealAI</span>
          </div>

          {/* Tabs */}
          <div className="pt-8">
            <div className="flex border-b border-gray-200">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  className={`flex-1 py-2 text-center font-medium transition
                    ${activeTab === tab.key
                      ? "border-b-2 border-blue-600 text-blue-700 bg-blue-50"
                      : "text-gray-500 hover:bg-gray-100"}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {/* Tab-Inhalt */}
            <div className="p-6">
              {activeTab === "form" && <div>Formular kommt hier hin</div>}
              {activeTab === "material" && <div>Materialauswahl kommt hier hin</div>}
              {activeTab === "result" && <div>Ergebnisanzeige kommt hier hin</div>}
            </div>
          </div>

          {/* Close-Button UNTER dem Logo */}
          <button
            className="ml-8 mt-6 p-3 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 transition"
            onClick={() => setOpen(false)}
            title="Sidebar schließen"
            style={{ minWidth: 48, minHeight: 48 }}
          >
            <span style={{ fontSize: 24 }}>&#10005;</span>
          </button>
        </>
      )}
    </aside>
  );
}

```


## frontend/src/app/dashboard/components/Sidebar/SidebarForm.tsx

```tsx
"use client";

import * as React from "react";
import { useAccessToken } from "@/lib/useAccessToken";
import { useChatWs } from "@/lib/useChatWs";

type Props = { embedded?: boolean };

type FormState = {
  // RWDR
  wellen_mm?: number;
  gehause_mm?: number;
  breite_mm?: number;
  medium?: string;
  temp_max_c?: number;
  druck_bar?: number;
  drehzahl_u_min?: number;
  // Hydraulik – Stange
  stange_mm?: number;
  nut_d_mm?: number;
  nut_b_mm?: number;
  geschwindigkeit_m_s?: number;
};

const LABELS: Record<string, string> = {
  falltyp: "Anwendungsfall",
  bauform: "Bauform/Profil",
  wellen_mm: "Welle (mm)",
  gehause_mm: "Gehäuse (mm)",
  breite_mm: "Breite (mm)",
  medium: "Medium",
  temp_max_c: "Tmax (°C)",
  druck_bar: "Druck (bar)",
  drehzahl_u_min: "Drehzahl (U/min)",
  stange_mm: "Stange (mm)",
  nut_d_mm: "Nut-Ø D (mm)",
  nut_b_mm: "Nutbreite B (mm)",
  geschwindigkeit_m_s: "v (m/s)",
};

function toNum(v: string): number | undefined {
  if (v === "" || v == null) return undefined;
  const n = Number(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : undefined;
}

function formatOneLine(f: FormState): string {
  const parts: string[] = [];
  if (f.wellen_mm) parts.push(`Welle ${f.wellen_mm}`);
  if (f.gehause_mm) parts.push(`Gehäuse ${f.gehause_mm}`);
  if (f.breite_mm) parts.push(`Breite ${f.breite_mm}`);
  if (f.stange_mm) parts.push(`Stange ${f.stange_mm}`);
  if (f.nut_d_mm) parts.push(`Nut D ${f.nut_d_mm}`);
  if (f.nut_b_mm) parts.push(`Nut B ${f.nut_b_mm}`);
  if (typeof f.geschwindigkeit_m_s !== "undefined") parts.push(`v ${f.geschwindigkeit_m_s} m/s`);
  if (f.medium) parts.push(`Medium ${f.medium}`);
  if (typeof f.temp_max_c !== "undefined") parts.push(`Tmax ${f.temp_max_c}`);
  if (typeof f.druck_bar !== "undefined") parts.push(`Druck ${f.druck_bar} bar`);
  if (typeof f.drehzahl_u_min !== "undefined") parts.push(`n ${f.drehzahl_u_min}`);
  return parts.join(", ");
}

function filled(v: unknown) {
  return !(v === undefined || v === null || v === "");
}

const baseInput =
  "mt-1 w-full rounded px-3 py-2 text-sm transition border outline-none focus:ring-2 focus:ring-blue-200";
const cls = (isFilled: boolean) =>
  [
    baseInput,
    isFilled ? "text-black font-semibold border-gray-900" : "text-gray-700 border-gray-300 placeholder-gray-400",
  ].join(" ");

function FormInner({
  form,
  setForm,
  missing,
  patch,
  submitAll,
  clearAll,
  containerRef,
}: {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
  missing: string[];
  patch: (k: keyof FormState, v: any) => void;
  submitAll: () => void;
  clearAll: () => void;
  containerRef: React.RefObject<HTMLDivElement>;
}) {
  return (
    <>
      {missing.length > 0 && (
        <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Fehlend: {missing.join(", ")}
        </div>
      )}

      <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
        {/* RWDR */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.wellen_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 25"
              className={cls(filled(form.wellen_mm))}
              value={form.wellen_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, wellen_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("wellen_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.gehause_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 47"
              className={cls(filled(form.gehause_mm))}
              value={form.gehause_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, gehause_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("gehause_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.breite_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 7"
              className={cls(filled(form.breite_mm))}
              value={form.breite_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, breite_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("breite_mm", toNum(e.target.value))}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="md:col-span-1">
            <label className="block text-sm font-medium text-gray-700">{LABELS.medium}</label>
            <input
              type="text"
              placeholder="z. B. Hydrauliköl"
              className={cls(filled(form.medium))}
              value={form.medium ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, medium: e.target.value }))}
              onBlur={(e) => patch("medium", e.target.value.trim() || undefined)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.temp_max_c}</label>
            <input
              type="number"
              inputMode="decimal"
              step="1"
              placeholder="z. B. 80"
              className={cls(filled(form.temp_max_c))}
              value={form.temp_max_c ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, temp_max_c: toNum(e.target.value) }))}
              onBlur={(e) => patch("temp_max_c", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.druck_bar}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.1"
              placeholder="z. B. 2"
              className={cls(filled(form.druck_bar))}
              value={form.druck_bar ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, druck_bar: toNum(e.target.value) }))}
              onBlur={(e) => patch("druck_bar", toNum(e.target.value))}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.drehzahl_u_min}</label>
            <input
              type="number"
              inputMode="numeric"
              step="1"
              placeholder="z. B. 1500"
              className={cls(filled(form.drehzahl_u_min))}
              value={form.drehzahl_u_min ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, drehzahl_u_min: toNum(e.target.value) }))}
              onBlur={(e) => patch("drehzahl_u_min", toNum(e.target.value))}
            />
          </div>
        </div>

        {/* Hydraulik – Stange */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.stange_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 25"
              className={cls(filled(form.stange_mm))}
              value={form.stange_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, stange_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("stange_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.nut_d_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 32"
              className={cls(filled(form.nut_d_mm))}
              value={form.nut_d_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, nut_d_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("nut_d_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.nut_b_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 6"
              className={cls(filled(form.nut_b_mm))}
              value={form.nut_b_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, nut_b_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("nut_b_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.geschwindigkeit_m_s}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 0.3"
              className={cls(filled(form.geschwindigkeit_m_s))}
              value={form.geschwindigkeit_m_s ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, geschwindigkeit_m_s: toNum(e.target.value) }))}
              onBlur={(e) => patch("geschwindigkeit_m_s", toNum(e.target.value))}
            />
          </div>
        </div>
      </form>

      <div className="border-t px-4 py-3 mt-4 flex items-center justify-between gap-2">
        <div className="text-xs text-gray-500">
          {missing.length > 0 ? "Bitte Felder ergänzen und übernehmen." : "\u00A0"}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50"
            onClick={clearAll}
          >
            Zurücksetzen
          </button>
          <button
            type="button"
            className="rounded-md bg-emerald-600 text-white px-3 py-1.5 text-sm hover:bg-emerald-700"
            onClick={submitAll}
          >
            Übernehmen
          </button>
        </div>
      </div>
    </>
  );
}

export default function SidebarForm({ embedded = false }: Props) {
  const token = useAccessToken();
  const { send } = useChatWs({ chatId: "default", token });

  const [open, setOpen] = React.useState(false);
  const [missing, setMissing] = React.useState<string[]>([]);
  const [form, setForm] = React.useState<FormState>({});
  const containerRef = React.useRef<HTMLDivElement>(null);
  const patchTimer = React.useRef<number | null>(null);

  const mergePrefill = React.useCallback((ua: any) => {
    const pre = ua?.prefill ?? ua?.params ?? {};
    const miss = Array.isArray(ua?.missing) ? ua.missing : undefined;
    if (miss) setMissing(miss);
    if (pre && typeof pre === "object") setForm((prev) => ({ ...prev, ...pre }));
  }, []);

  React.useEffect(() => {
    const onUi = (ev: Event) => {
      const ua: any = (ev as CustomEvent<any>).detail ?? (ev as any);
      const action = ua?.ui_action ?? ua?.action;
      if (action === "open_form" || ua?.prefill || ua?.params) {
        mergePrefill(ua);
        if (!embedded && action === "open_form") setOpen(true);
        setTimeout(() => {
          const root = containerRef.current;
          const first =
            root?.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
              "input, textarea, select",
            );
          first?.focus();
        }, 0);
      }
    };
    // Neuer Standard-Eventname
    window.addEventListener("sealai:ui", onUi as EventListener);
    // Abwärtskompatibel
    window.addEventListener("sealai:ui_action", onUi as EventListener);
    window.addEventListener("sai:need-params", onUi as EventListener);
    window.addEventListener("sealai:form:patch", onUi as EventListener);
    return () => {
      window.removeEventListener("sealai:ui", onUi as EventListener);
      window.removeEventListener("sealai:ui_action", onUi as EventListener);
      window.removeEventListener("sai:need-params", onUi as EventListener);
      window.removeEventListener("sealai:form:patch", onUi as EventListener);
    };
  }, [embedded, mergePrefill]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const patch = React.useCallback(
    (k: keyof FormState, v: any) => {
      setForm((cur) => ({ ...cur, [k]: v }));
      const payloadValue =
        typeof v === "number"
          ? Number.isFinite(v)
            ? v
            : undefined
          : (v && String(v).trim()) || undefined;
      if (patchTimer.current) window.clearTimeout(patchTimer.current);
      patchTimer.current = window.setTimeout(() => {
        if (typeof payloadValue !== "undefined") {
          send("📝 form patch", { params: { [k]: payloadValue } });
        }
      }, 180);
    },
    [send],
  );

  const submitAll = () => {
    const cleaned: Record<string, any> = {};
    for (const [k, v] of Object.entries(form)) {
      if (v === "" || v == null) continue;
      cleaned[k] = v;
    }
    send("📝 form submit", { params: cleaned });
    const summary = formatOneLine(cleaned as FormState);
    if (summary) {
      window.dispatchEvent(
        new CustomEvent("sealai:chat:add", {
          detail: { text: summary, source: "sidebar_form", action: "submit", params: cleaned },
        }),
      );
    }
    if (!embedded) setOpen(false);
  };

  const clearAll = () => setForm({});

  if (embedded) {
    return (
      <div className="p-2" ref={containerRef}>
        <FormInner
          form={form}
          setForm={setForm}
          missing={missing}
          patch={patch}
          submitAll={submitAll}
          clearAll={clearAll}
          containerRef={containerRef}
        />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-40 pointer-events-none" aria-hidden={!open}>
      <div
        className={[
          "pointer-events-auto absolute right-0 top-0 h-full w-[360px] max-w-[90vw]",
          "bg-white shadow-xl border-l border-gray-200",
          "transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        ].join(" ")}
        role="dialog"
        aria-modal="false"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="font-semibold">Beratungs-Formular</div>
          <button
            type="button"
            className="rounded px-2 py-1 text-sm hover:bg-gray-100"
            onClick={() => setOpen(false)}
            aria-label="Schließen"
          >
            ✕
          </button>
        </div>
        <div className="p-4 overflow-y-auto h-[calc(100%-56px)]" ref={containerRef}>
          <FormInner
            form={form}
            setForm={setForm}
            missing={missing}
            patch={patch}
            submitAll={submitAll}
            clearAll={clearAll}
            containerRef={containerRef}
          />
        </div>
      </div>
    </div>
  );
}

```


## frontend/src/app/dashboard/components/Sidebar/SidebarLeft.tsx

```tsx
"use client";

import * as React from "react";
import SidebarForm from "./SidebarForm";

export default function SidebarLeft({
  open = true,
  onOpenChange,
}: {
  open?: boolean;
  onOpenChange?: (v: boolean) => void;
}) {
  return (
    <aside
      className={[
        "relative border-r border-zinc-200 bg-white transition-all",
        open ? "w-[360px] max-w-[40vw]" : "w-0 max-w-0 overflow-hidden",
      ].join(" ")}
      aria-hidden={!open}
    >
      <div className="p-3 text-xs text-zinc-500 flex items-center justify-between">
        <span>Beratung</span>
        {onOpenChange && (
          <button
            className="rounded px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100"
            onClick={() => onOpenChange(false)}
            aria-label="Sidebar schließen"
            title="Sidebar schließen"
          >
            ✕
          </button>
        )}
      </div>
      <SidebarForm embedded />
    </aside>
  );
}

```


## frontend/src/app/dashboard/components/Sidebar/SidebarRight.tsx

```tsx
'use client';

import { FC } from 'react';
import CalcCard from './CalcCard'; // ← hinzugefügt

const SidebarRight: FC = () => {
  return (
    <div className="h-full w-full p-4 space-y-4">
      {/* neue Berechnungs-Kachel */}
      <CalcCard />

      <h2 className="text-lg font-semibold">Optionen</h2>
      <ul className="space-y-2 text-sm">
        <li><button className="hover:underline">🌙 Dark Mode</button></li>
        <li><button className="hover:underline">⚙️ Einstellungen</button></li>
        <li><button className="hover:underline">📤 Export</button></li>
      </ul>
    </div>
  );
};

export default SidebarRight;

```


## frontend/src/app/dashboard/layout.tsx

```tsx
import type { ReactNode } from "react";
import DashboardShell from "./DashboardShell";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}

```


## frontend/src/app/dashboard/page.tsx

```tsx
// Server Component
export const dynamic = "force-dynamic";
export const revalidate = 0;

import DashboardClient from "./DashboardClient";

export default function DashboardPage() {
  return <DashboardClient />;
}

```


## frontend/src/app/layout.tsx

```tsx
// src/app/layout.tsx
import Providers from './providers'
import type { ReactNode } from 'react'
import '../styles/globals.css'
import SiteBackground from '../components/SiteBackground'

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de">
      <body className="bg-black text-zinc-200 antialiased">
        {/* Globaler Hintergrund für die komplette Seite */}
        <SiteBackground />

        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}

```


## frontend/src/app/page.tsx

```tsx
// src/app/page.tsx — x.ai/Grok-Stil, Sektionen ohne harte Übergänge (transparent)
"use client";

import { signIn } from "next-auth/react";
import HeroGrok from "../components/HeroGrok";

function Header() {
  return (
    <header className="absolute top-0 left-0 right-0 z-50 bg-transparent">
      <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
        <a href="/" className="flex items-center gap-3">
          <img src="/logo_sai.svg" alt="SealAI" className="h-6 w-auto" />
          <span className="sr-only">SealAI</span>
        </a>
        <nav aria-label="Primary" className="hidden md:block">
          <ul className="flex items-center gap-8 text-sm text-zinc-300">
            <li><a href="#products" className="hover:text-white">Products</a></li>
            <li><a href="#api" className="hover:text-white">API</a></li>
            <li><a href="#company" className="hover:text-white">Company</a></li>
            <li><a href="#careers" className="hover:text-white">Careers</a></li>
            <li><a href="#news" className="hover:text-white">News</a></li>
          </ul>
        </nav>
        <div className="flex items-center gap-3">
          <a
            href="/auth/signin"
            onClick={(e) => {
              e.preventDefault();
              const base = process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
              signIn("keycloak", { callbackUrl: `${base}/dashboard` });
            }}
            className="inline-flex items-center rounded-xl border border-white/20 px-4 py-2 text-sm font-medium text-white hover:bg-white/10"
          >
            Try SealAI
          </a>
        </div>
      </div>
    </header>
  );
}

export default function Landing() {
  return (
    // bg-transparent: globaler SiteBackground scheint durch (kein Übergang)
    <main className="min-h-[100dvh] bg-transparent text-zinc-200">
      <Header />

      {/* Hero (Gradients + Spotlights, 100dvh) */}
      <HeroGrok />

      {/* Products — ohne border, transparenter Bereich */}
      <section id="products" className="relative bg-transparent">
        {/* ganz dezente weiche Trennung via Schattenverlauf (kein harter Strich) */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-10 bg-gradient-to-b from-black/0 via-black/0 to-black/10" aria-hidden />

        <div className="mx-auto max-w-7xl px-6 py-16 sm:py-20">
          <h2 className="text-2xl font-medium text-white">Products</h2>
          <div className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <Card title="Advisor" desc="Fachberater für Dichtungstechnik mit Retrieval, Tools und Reports." cta="Use now" href="/auth/signin" />
            <Card id="api" title="API" desc="Nutze SealAI programmatically. Secure auth, streaming, webhooks." cta="Build now" href="/api" secondary />
            <Card title="Developer Docs" desc="Schnellstart, Beispiele und Best Practices für Integration." cta="Learn more" href="/docs" secondary />
          </div>
        </div>
      </section>

      {/* News — ohne border, transparent */}
      <section id="news" className="relative bg-transparent">
        <div className="mx-auto max-w-7xl px-6 py-16 sm:py-20">
          <h2 className="text-2xl font-medium text-white">Latest news</h2>
          <ul className="mt-6 space-y-6">
            <li className="flex flex-col sm:flex-row sm:items-baseline gap-2">
              <span className="text-sm text-zinc-400 w-32 shrink-0">July 2025</span>
              <a href="#" className="text-zinc-100 hover:underline">
                SealAI Advisor v0.9 – neue Material- und Profilagenten, schnellere Streams.
              </a>
            </li>
            <li className="flex flex-col sm:flex-row sm:items-baseline gap-2">
              <span className="text-sm text-zinc-400 w-32 shrink-0">June 2025</span>
              <a href="#" className="text-zinc-100 hover:underline">
                API Preview – Auth via Keycloak, LangGraph Streaming, Redis Checkpointer.
              </a>
            </li>
          </ul>
        </div>
      </section>

      {/* Footer — ohne border, transparent */}
      <footer id="company" className="relative bg-transparent mt-8">
        <div className="mx-auto max-w-7xl px-6 py-12 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-8 text-sm">
          <div className="col-span-2">
            <img src="/logo_sai.svg" alt="SealAI" className="h-6 w-auto mb-4" />
            <p className="text-zinc-400">© {new Date().getFullYear()} SealAI</p>
          </div>
          <div>
            <p className="mb-3 text-zinc-300">Products</p>
            <ul className="space-y-2 text-zinc-400">
              <li><a href="#products" className="hover:text-white">Advisor</a></li>
              <li><a href="#api" className="hover:text-white">API</a></li>
            </ul>
          </div>
          <div>
            <p className="mb-3 text-zinc-300">Company</p>
            <ul className="space-y-2 text-zinc-400">
              <li><a href="#company" className="hover:text-white">About</a></li>
              <li><a href="#careers" className="hover:text-white">Careers</a></li>
              <li><a href="/impressum" className="hover:text-white">Impressum</a></li>
              <li><a href="/datenschutz" className="hover:text-white">Datenschutz</a></li>
            </ul>
          </div>
          <div>
            <p className="mb-3 text-zinc-300">Resources</p>
            <ul className="space-y-2 text-zinc-400">
              <li><a href="/status" className="hover:text-white">Status</a></li>
              <li><a href="/docs" className="hover:text-white">Docs</a></li>
            </ul>
          </div>
        </div>
      </footer>
    </main>
  );
}

function Card({
  title, desc, cta, href, secondary, id
}: {
  title: string; desc: string; cta: string; href: string; secondary?: boolean; id?: string
}) {
  return (
    <a
      id={id}
      href={href}
      onClick={(event) => {
        if (href !== "/auth/signin") return;
        event.preventDefault();
        const base = process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
        signIn("keycloak", { callbackUrl: `${base}/dashboard` });
      }}
      className={[
        "group block rounded-2xl border p-6 transition bg-white/[0.03]",
        secondary ? "border-white/15 hover:bg-white/5" : "border-white/20 hover:bg-white/[0.06]",
      ].join(" ")}
    >
      <div className="text-base font-medium text-white">{title}</div>
      <p className="mt-2 text-sm text-zinc-400">{desc}</p>
      <div className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-white">
        {cta}
        <svg className="size-4 opacity-70 group-hover:translate-x-0.5 transition" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 12h14M13 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </a>
  );
}

```


## frontend/src/app/providers.tsx

```tsx
// src/app/providers.tsx
'use client'

import { SessionProvider } from 'next-auth/react'
import type { ReactNode } from 'react'

export default function Providers({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>
}

```


## frontend/src/app/register/page.js

```js
"use client";

import { useState } from 'react';

const RegisterPage = () => {
  const [formData, setFormData] = useState({ email: '', password: '' });

  const handleSubmit = async (e) => {
    e.preventDefault();
    // Registrierung-Logik hier
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="email"
        placeholder="Email"
        value={formData.email}
        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
      />
      <input
        type="password"
        placeholder="Password"
        value={formData.password}
        onChange={(e) => setFormData({ ...formData, password: e.target.value })}
      />
      <button type="submit">Register</button>
    </form>
  );
};

export default RegisterPage;

```


## frontend/src/components/Fog.tsx

```tsx
// src/components/Fog.tsx — bottom-only clouds, stronger & slower, no edge seam
"use client";
import React, { useEffect, useRef } from "react";

export default function Fog() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d", { alpha: true })!;
    let running = true;

    // Tunables (sichtbarer Nebel)
    const BLUR_PX = 22;          // etwas weniger Weichzeichnung -> mehr Struktur
    const PAD = BLUR_PX * 4;     // Offscreen-Puffer gegen Randartefakte
    const TILE = 256;            // Größe der Rausch-Kachel

    // Kleine wiederholbare Rauschkachel (gaussian-ish, leicht kontrastiert)
    const noiseTile = document.createElement("canvas");
    noiseTile.width = TILE; noiseTile.height = TILE;
    {
      const nctx = noiseTile.getContext("2d")!;
      const img = nctx.createImageData(TILE, TILE);
      const d = img.data;
      for (let i = 0; i < d.length; i += 4) {
        // Summe zweier Zufälle -> Glockenkurve; danach leicht kontrastverstärkt
        let v = (Math.random() + Math.random()) * 127; // 0..254
        // Simple contrast curve around mid gray
        const c = 1.18; // Kontrastfaktor
        v = (v - 127) * c + 127;
        v = Math.max(0, Math.min(255, v));
        d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255;
      }
      nctx.putImageData(img, 0, 0);
    }

    // Großes Offscreen-Canvas (mit Rand)
    const frame = document.createElement("canvas");
    const fctx = frame.getContext("2d")!;

    function resize() {
      const parent = canvas.parentElement!;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(parent.clientWidth * dpr);
      canvas.height = Math.floor(parent.clientHeight * dpr);
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      frame.width = parent.clientWidth + PAD * 2;
      frame.height = parent.clientHeight + PAD * 2;
    }

    function draw(time: number) {
      if (!running) return;
      const t = time * 0.001;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;

      // Offscreen mit zwei driftenden Schichten füllen
      fctx.clearRect(0, 0, frame.width, frame.height);
      const pat = fctx.createPattern(noiseTile, "repeat")!;

      // Layer A (breit)
      fctx.save();
      fctx.globalAlpha = 0.95;
      fctx.setTransform(1, 0, 0, 1, (-((t * 6) % TILE)) - PAD, Math.sin(t * 0.10) * 10 - PAD);
      fctx.fillStyle = pat;
      fctx.fillRect(0, 0, frame.width + PAD * 2, frame.height + PAD * 2);
      fctx.restore();

      // Layer B (gegengesetzt, etwas schneller)
      fctx.save();
      fctx.globalAlpha = 0.75;
      fctx.setTransform(1, 0, 0, 1, (-((t * -9) % TILE)) - PAD, Math.cos(t * 0.08) * 12 - PAD);
      fctx.fillStyle = pat;
      fctx.fillRect(0, 0, frame.width + PAD * 2, frame.height + PAD * 2);
      fctx.restore();

      // Haupt-Render: weichzeichnen + kräftiger Alpha
      ctx.clearRect(0, 0, w, h);
      ctx.save();
      ctx.filter = `blur(${BLUR_PX}px)`;
      ctx.globalAlpha = 0.50; // vorher ~0.32
      ctx.drawImage(frame, -PAD, -PAD, frame.width, frame.height, 0, 0, w, h);
      ctx.restore();

      // Zweite Tiefen-Schicht (minimal skaliert) für volumen
      ctx.save();
      ctx.filter = `blur(${Math.round(BLUR_PX * 1.2)}px)`;
      ctx.globalAlpha = 0.25;
      ctx.drawImage(frame, -PAD - 12, -PAD - 8, frame.width + 24, frame.height + 16, 0, 0, w, h);
      ctx.restore();

      // Blaue Bodentönung etwas kräftiger
      const tint = ctx.createLinearGradient(0, h * 0.45, 0, h);
      tint.addColorStop(0.0, "rgba(0,0,0,0)");
      tint.addColorStop(1.0, "rgba(99,102,241,0.22)");
      ctx.fillStyle = tint;
      ctx.fillRect(0, 0, w, h);

      // Maske: weiter oben sichtbar machen
      const mask = ctx.createLinearGradient(0, 0, 0, h);
      mask.addColorStop(0.00, "rgba(0,0,0,0)");
      mask.addColorStop(0.45, "rgba(0,0,0,0.25)");
      mask.addColorStop(0.65, "rgba(0,0,0,0.75)");
      mask.addColorStop(1.00, "rgba(0,0,0,1)");
      ctx.globalCompositeOperation = "destination-in";
      ctx.fillStyle = mask;
      ctx.fillRect(0, 0, w, h);
      ctx.globalCompositeOperation = "source-over";

      rafRef.current = requestAnimationFrame(draw);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas.parentElement!);
    rafRef.current = requestAnimationFrame(draw);

    return () => {
      running = false;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
  }, []);

  // etwas höhere Nebelhöhe, damit er deutlicher sichtbar ist
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[48svh] md:h-[46svh] lg:h-[44svh]">
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
}

```


## frontend/src/components/HeroBackground.tsx

```tsx
"use client";
import * as React from "react";
import { Canvas, useFrame } from "@react-three/fiber";

const vertexShader = `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
  }
`;

const fragmentShader = `
  varying vec2 vUv;
  uniform float uTime;
  float rand(vec2 co){
      return fract(sin(dot(co.xy,vec2(12.9898,78.233)))*43758.5453);
  }
  float noise(vec2 p){
      vec2 i = floor(p);
      vec2 f = fract(p);
      float a = rand(i);
      float b = rand(i + vec2(1.0, 0.0));
      float c = rand(i + vec2(0.0, 1.0));
      float d = rand(i + vec2(1.0, 1.0));
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(a, b, u.x) +
              (c - a)* u.y * (1.0 - u.x) +
              (d - b) * u.x * u.y;
  }
  float fbm(vec2 p) {
      float value = 0.0;
      float amplitude = 0.5;
      for (int i = 0; i < 6; i++) {
          value += amplitude * noise(p);
          p *= 2.0;
          amplitude *= 0.5;
      }
      return value;
  }

  void main() {
    vec2 uv = vUv * 2.0 - 1.0;
    float t = uTime * 0.06;
    float q = fbm(uv * 1.4 + t * 0.6);
    float r = fbm(uv * 2.3 - t * 0.3 + q);
    float mask = smoothstep(0.25, 0.7, r);
    float beam = smoothstep(0.3, 1.0, uv.x + uv.y + 0.5) * 0.6;
    float intensity = (r * 0.7 + q * 0.3) * (1.2 + beam);
    vec3 color = mix(vec3(0.13,0.17,0.26), vec3(0.60,0.75,1.0), intensity);
    color += beam * vec3(1.2,1.2,2.5);
    float alpha = mask * 0.84;
    gl_FragColor = vec4(color, alpha);
  }
`;

export default function HeroBackground() {
  const materialRef = React.useRef<any>(null);
  useFrame(({ clock }) => {
    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value = clock.getElapsedTime();
    }
  });

  return (
    <div className="absolute inset-0 w-full h-full z-0 pointer-events-none">
      <Canvas
        camera={{ position: [0, 0, 1], fov: 40 }}
        style={{ width: "100%", height: "100%" }}
        gl={{ alpha: true, antialias: true }}
      >
        <mesh scale={[3.6, 2.2, 1]}>
          <planeGeometry args={[1, 1, 128, 128]} />
          <shaderMaterial
            ref={materialRef}
            uniforms={{ uTime: { value: 0 } }}
            vertexShader={vertexShader}
            fragmentShader={fragmentShader}
            transparent
            depthWrite={false}
          />
        </mesh>
      </Canvas>
    </div>
  );
}

```


## frontend/src/components/HeroGrok.tsx

```tsx
// src/components/HeroGrok.tsx — Hero (100dvh) mit Gradients & Spotlights, ohne Nebel
"use client";

import React from "react";
import { signIn } from "next-auth/react";
import Starfield from "./Starfield";

export default function HeroGrok() {
  return (
    <section className="relative overflow-hidden h-[100dvh] min-h-[100dvh] flex">
      {/* Sternenhimmel */}
      <Starfield />

      {/* Sehr dunkler, fast schwarzer Blauverlauf von oben */}
      <div
        className="pointer-events-none absolute inset-0 bg-gradient-to-b
                   from-[#040815] via-[#0A1328]/80 to-transparent"
        aria-hidden
      />

      {/* Spotlight rechts (volumetrisch, atmend) */}
      <div
        className="pointer-events-none absolute right-[-18%] top-1/2 -translate-y-1/2
                   w-[70vw] h-[70vw]
                   bg-[radial-gradient(closest-side,rgba(255,255,255,0.9),rgba(99,102,241,0.35),transparent_70%)]
                   blur-3xl opacity-80 animate-glow-pulse"
        aria-hidden
      />

      {/* Sekundäres leises Spotlight links */}
      <div
        className="pointer-events-none absolute left-[-25%] top-1/2 -translate-y-1/2
                   w-[55vw] h-[55vw]
                   bg-[radial-gradient(closest-side,rgba(37,99,235,0.35),rgba(59,130,246,0.18),transparent_70%)]
                   blur-3xl opacity-35 animate-glow-pulse"
        aria-hidden
      />

      {/* Horizontaler Light-Sweep rechts */}
      <div
        className="pointer-events-none absolute inset-y-0 right-[8%] w-[60vw]
                   bg-[linear-gradient(90deg,transparent,rgba(180,200,255,0.25)_40%,transparent)]
                   blur-2xl opacity-60 animate-glow-sweep"
        aria-hidden
      />

      {/* Boden-Glow (Gradient statt Nebel; Video kommt später hier drüber) */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[46svh]
                   bg-gradient-to-t from-[#1b2142]/70 via-[#121936]/35 to-transparent"
        aria-hidden
      />

      {/* Platzhalter-Layer für späteres Video (wabernder Nebel) */}
      <div className="pointer-events-none absolute inset-0 z-[5]" aria-hidden />

      {/* Inhalt zentriert */}
      <div className="relative z-10 mx-auto max-w-7xl px-6 w-full h-full flex">
        <div className="max-w-4xl m-auto text-center flex flex-col items-center justify-center gap-6">
          <p className="text-xs uppercase tracking-widest text-zinc-400 mx-auto">SealAI</p>

          <h1
            className="text-[16vw] leading-none font-semibold text-white/90
                       sm:text-[12vw] md:text-[10vw] lg:text-[9vw]
                       [text-shadow:0_0_30px_rgba(120,140,255,0.18),0_0_10px_rgba(255,255,255,0.05)]"
          >
            SealAI
          </h1>

          <p className="max-w-2xl text-lg text-zinc-300">
            Dein Assistent für Werkstoffauswahl, Profile und Konstruktion – mit Echtzeit-Recherche,
            fundierter Beratung und Integration in deinen Workflow.
          </p>

          {/* Eingabe-Box */}
          <div className="mt-2 max-w-2xl w-full mx-auto rounded-2xl border border-white/10 bg-black/50 backdrop-blur">
            <div className="flex items-center">
              <input
                readOnly
                value="What do you want to know?"
                className="w-full bg-transparent px-5 py-4 text-sm text-zinc-400 outline-none"
              />
              <button
                onClick={() => signIn(undefined, { callbackUrl: "/dashboard" })}
                className="m-2 inline-flex items-center justify-center rounded-xl border border-white/15 px-3 py-2 text-sm font-medium text-white hover:bg-white/10"
                aria-label="Try SealAI"
              >
                →
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Scroll-Hinweis */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 text-white/40 text-xl animate-bounce">▾</div>
    </section>
  );
}

```


## frontend/src/components/SiteBackground.tsx

```tsx
// src/components/SiteBackground.tsx
// Globaler Seitenhintergrund: sehr dunkles Blau + dezenter Starfield, fixiert
"use client";

import React from "react";
import Starfield from "./Starfield";

export default function SiteBackground() {
  return (
    <>
      {/* Tiefschwarz als Fallback */}
      <div className="pointer-events-none fixed inset-0 z-[-3] bg-black" />

      {/* Dunkelblauer Verlauf wie im Hero */}
      <div
        className="pointer-events-none fixed inset-0 z-[-2]
                   bg-gradient-to-b from-[#040815] via-[#0A1328] to-[#0B1020]"
        aria-hidden
      />

      {/* Dezenter Sternenhimmel über gesamte Seite */}
      <div className="pointer-events-none fixed inset-0 z-[-1] opacity-35">
        <Starfield />
      </div>
    </>
  );
}

```


## frontend/src/components/Starfield.tsx

```tsx
// src/components/Starfield.tsx — subtiler Sternenhimmel (twinkle)
"use client";
import React, { useEffect, useRef } from "react";

type Star = { x: number; y: number; r: number; phase: number; speed: number };

export default function Starfield({ density = 240 }: { density?: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    const stars: Star[] = [];
    let running = true;

    function resize() {
      const parent = c.parentElement!;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      c.width = Math.floor(parent.clientWidth * dpr);
      c.height = Math.floor(parent.clientHeight * dpr);
      c.style.width = "100%";
      c.style.height = "100%";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      stars.length = 0;
      const count = Math.floor((parent.clientWidth * parent.clientHeight) / 18000);
      for (let i = 0; i < Math.min(density, Math.max(80, count)); i++) {
        stars.push({
          x: Math.random() * parent.clientWidth,
          y: Math.random() * parent.clientHeight,
          r: Math.random() * 1.2 + 0.2,
          phase: Math.random() * Math.PI * 2,
          speed: 0.6 + Math.random() * 0.6,
        });
      }
    }

    function draw(t: number) {
      if (!running) return;
      ctx.clearRect(0, 0, c.width, c.height);
      ctx.fillStyle = "#fff";
      for (const s of stars) {
        const a = 0.08 + Math.abs(Math.sin(s.phase + t * 0.001 * s.speed)) * 0.18;
        ctx.globalAlpha = a;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      raf.current = requestAnimationFrame(draw);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(c.parentElement!);
    raf.current = requestAnimationFrame(draw);

    return () => { running = false; if (raf.current) cancelAnimationFrame(raf.current); ro.disconnect(); };
  }, [density]);

  return <canvas ref={ref} className="absolute inset-0 w-full h-full" aria-hidden />;
}

```


## frontend/src/components/organisms/Header.tsx

```tsx
'use client';

import React from 'react';

interface HeaderProps {
  onToggle: () => void;
  isSidebarOpen: boolean;
}

export default function Header({ onToggle, isSidebarOpen }: HeaderProps) {
  return (
    <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200">
      <button 
        onClick={onToggle}
        className="p-2 rounded hover:bg-gray-100"
        aria-label="Toggle Sidebar"
      >
        {isSidebarOpen ? '←' : '☰'}
      </button>
      <span className="font-semibold text-lg">🦭 SealAI</span>
      <div /> {/* Platzhalter für Rechtsshift */}
    </div>
  );
}

```


## frontend/src/components/organisms/Sidebar.tsx

```tsx
'use client';
// frontend/src/components/organisms/Sidebar.tsx

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, MessageSquare } from 'lucide-react';

export default function Sidebar() {
  const path = usePathname();

  const items = [
    { label: 'Home', href: '/', icon: Home },
    { label: 'Chat', href: '/dashboard', icon: MessageSquare },
  ];

  return (
    <nav className="flex flex-col p-4 space-y-2">
      {items.map(({ label, href, icon: Icon }) => {
        const active = path === href;
        return (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 px-3 py-2 rounded-md ${
              active
                ? 'bg-brand-600 text-white'
                : 'hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            <Icon className="w-5 h-5" />
            <span className="font-medium">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

```


## frontend/src/components/ui/card.tsx

```tsx
// 📄 frontend/components/ui/card.tsx

import React from "react";

export function Card({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        border: "1px solid #ccc",
        borderRadius: "0.5rem",
        padding: "1rem",
        backgroundColor: "#fff",
        boxShadow: "0 2px 6px rgba(0,0,0,0.05)"
      }}
    >
      {children}
    </div>
  );
}

```


## frontend/src/lib/logout.ts

```ts
"use client"

import { signOut } from "next-auth/react"

const CLIENT_ID =
  process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ||
  process.env.KEYCLOAK_CLIENT_ID ||
  "nextauth"

const ISSUER =
  process.env.NEXT_PUBLIC_KEYCLOAK_ISSUER ||
  process.env.KEYCLOAK_ISSUER ||
  "https://auth.sealai.net/realms/sealAI"

export const logout = async (idToken?: string, redirectTo = "/") => {
  const origin = typeof window !== "undefined" ? window.location.origin : ""
  const safePath = redirectTo.startsWith("/") ? redirectTo : "/"
  const postLogout = `${origin}${safePath}`

  // 1) lokale NextAuth-Session beenden
  await signOut({ redirect: false })

  // 2) RP-initiated logout URL bauen
  const base = `${ISSUER}/protocol/openid-connect/logout`
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    post_logout_redirect_uri: postLogout,
  })

  // Nur ein id_token_hint mitsenden, wenn wirklich vorhanden
  if (idToken && idToken.split(".").length === 3) {
    params.set("id_token_hint", idToken)
  }

  // 3) Browser zu Keycloak umleiten
  window.location.href = `${base}?${params.toString()}`
}

// Alias für alte Importe
export const handleLogout = logout

```


## frontend/src/lib/useAccessToken.ts

```ts
"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

/**
 * Liefert direkt den Token-String (oder undefined).
 * Zieht bevorzugt accessToken, fällt ansonsten auf idToken & Varianten zurück.
 */
export function useAccessToken(): string | undefined {
  const { data, status } = useSession();
  const [token, setToken] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (status !== "authenticated") {
      setToken(undefined);
      return;
    }
    const s: any = data || {};
    const t =
      s.accessToken ??
      s.idToken ??
      s.user?.accessToken ??
      s.user?.token ??
      s.access_token;
    setToken(typeof t === "string" && t.length > 0 ? t : undefined);
  }, [status, data]);

  return token;
}

/**
 * Holt immer die frischeste Session-Ansicht vom Server
 * und extrahiert den Token-String (accessToken/idToken/Fallbacks).
 */
export async function fetchFreshAccessToken(): Promise<string | undefined> {
  try {
    const res = await fetch("/api/auth/session", { cache: "no-store" });
    if (!res.ok) return undefined;
    const json: any = await res.json();
    const t =
      json?.accessToken ??
      json?.idToken ??
      json?.user?.accessToken ??
      json?.user?.token ??
      json?.access_token;
    return typeof t === "string" && t.length > 0 ? t : undefined;
  } catch {
    return undefined;
  }
}

```


## frontend/src/lib/useChatSse.ts

```ts
"use client";

import * as React from "react";
import { useSession } from "next-auth/react";

type State = {
  streaming: boolean;
  text: string;
  error: string | null;
};

export function useChatSse(endpoint: string = "/api/langgraph/chat") {
  const { status } = useSession();
  const [state, setState] = React.useState<State>({ streaming: false, text: "", error: null });
  const controllerRef = React.useRef<AbortController | null>(null);

  const send = React.useCallback(async (input: string, bodyExtra?: Record<string, unknown>) => {
    if (status !== "authenticated") {
      setState((s) => ({ ...s, error: "unauthenticated" }));
      return;
    }
    const trimmed = input.trim();
    if (!trimmed) return;

    controllerRef.current?.abort();
    controllerRef.current = new AbortController();

    setState({ streaming: true, text: "", error: null });

    const resp = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ input: trimmed, stream: true, ...(bodyExtra || {}) }),
      signal: controllerRef.current.signal,
    }).catch((e) => {
      setState({ streaming: false, text: "", error: String(e?.message || "network_error") });
      return null as any;
    });

    if (!resp || !resp.ok || !resp.body) {
      if (resp) setState({ streaming: false, text: "", error: `http_${resp.status}` });
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const frame of frames) {
          const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(6));
            if (typeof payload?.delta === "string" && payload.delta.length) {
              setState((s) => ({ ...s, text: s.text + payload.delta }));
            } else if (payload?.final?.text) {
              setState((s) => ({ ...s, text: payload.final.text }));
            } else if (payload?.error) {
              setState((s) => ({ ...s, error: String(payload.error) }));
            }
          } catch {
            // ignore malformed frames
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        setState((s) => ({ ...s, error: String(e?.message || "stream_error") }));
      }
    } finally {
      try { await reader.cancel(); } catch {}
      setState((s) => ({ ...s, streaming: false }));
    }
  }, [status, endpoint]);

  const cancel = React.useCallback(() => {
    controllerRef.current?.abort();
    setState((s) => ({ ...s, streaming: false }));
  }, []);

  const reset = React.useCallback(() => {
    controllerRef.current?.abort();
    setState({ streaming: false, text: "", error: null });
  }, []);

  return { ...state, send, cancel, reset };
}

```


## frontend/src/lib/useChatWs.ts

```ts
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type UseChatWsOpts = {
  chatId: string;
  token?: string | null; // Keycloak Access Token
};

type WsState = {
  connected: boolean;
  streaming: boolean;
  text: string;
  lastError: string | null;
  send: (input: string, params?: Record<string, any>) => void;
  cancel: () => void;
};

function buildWsUrl(token?: string | null) {
  if (typeof window === 'undefined') return '';
  const { protocol, host } = window.location;
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:';
  const qp = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${wsProto}//${host}/api/v1/ai/ws${qp}`;
}

// kleine Helfer
function safeParse(data: string) {
  try { return JSON.parse(data); } catch { return data; }
}

export function useChatWs({ chatId, token }: UseChatWsOpts): WsState {
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [text, setText] = useState('');
  const [lastError, setLastError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const backoffRef = useRef(1000);
  const lastThreadIdRef = useRef<string | null>(null);
  const firedNeedParamsRef = useRef(false);

  const url = useMemo(() => buildWsUrl(token), [token]);

  const clearHeartbeat = () => {
    if (heartbeatRef.current) {
      window.clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  };

  const startHeartbeat = () => {
    clearHeartbeat();
    heartbeatRef.current = window.setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping', ts: Date.now() }));
      }
    }, 12_000);
  };

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) return;
    const delay = Math.min(backoffRef.current, 10_000);
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
      backoffRef.current = Math.min(backoffRef.current * 2, 10_000);
    }, delay) as unknown as number;
  }, []);

  const cleanup = useCallback(() => {
    clearHeartbeat();
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    try { wsRef.current?.close(); } catch {}
    wsRef.current = null;
    setConnected(false);
    setStreaming(false);
  }, []);

  // ---- zentrale UI-Event-Brücke ----
  const emitUiAction = useCallback((ua: any) => {
    try {
      // Normalisieren
      const payload = typeof ua === 'object' && ua !== null
        ? ua
        : { ui_action: String(ua || '') };

      // einheitliches CustomEvent
      window.dispatchEvent(new CustomEvent('sealai:ui', { detail: payload }));
      window.dispatchEvent(new CustomEvent('sealai:ui_action', { detail: payload }));
    } catch {}
  }, []);

  // Wenn Text-Rückfrage nach Pflichtfeldern erkannt wird, Sidebar öffnen
  const maybeOpenFormFromText = useCallback((s: string) => {
    if (firedNeedParamsRef.current) return;
    if (!s) return;
    if (/(mir fehlen.*angaben|kannst du.*bitte nennen|präzise.*empfehlung.*brauche.*noch kurz|in einer zeile.*angabe)/i.test(s)) {
      firedNeedParamsRef.current = true;
      emitUiAction({ ui_action: 'open_form' });
    }
  }, [emitUiAction]);

  const handleMessage = useCallback((ev: MessageEvent) => {
    const payload: any = typeof ev.data === 'string' ? safeParse(ev.data) : ev.data;
    if (!payload) return;

    // Roh-Frames ignorieren
    if (payload?.event === 'idle') return;
    if (payload?.event === 'error' && payload?.code === 'idle_timeout') return;

    // ---- Debug-Routing (z. B. ask_missing) -> sofort Formular öffnen
    if (payload?.event === 'dbg') {
      const node = (payload?.meta?.langgraph_node || payload?.meta?.run_name || '').toString().toLowerCase();
      if (node === 'ask_missing' && !firedNeedParamsRef.current) {
        firedNeedParamsRef.current = true;
        emitUiAction({ ui_action: 'open_form' });
      }
    }

    // ---- UI-Event: unterstützt event:'ui_action', ui_event:{} oder ui_action:'open_form'
    if (payload?.event === 'ui_action' || payload?.ui_event || typeof payload?.ui_action !== 'undefined') {
      const ua = typeof payload?.ui_action === 'string'
        ? { ui_action: payload.ui_action }
        : (payload?.ui_event && typeof payload.ui_event === 'object' ? payload.ui_event : payload);
      emitUiAction(ua);
    }

    switch (payload.event) {
      case 'start':
        lastThreadIdRef.current = payload.thread_id ?? null;
        setStreaming(true);
        setText('');
        break;

      case 'token': {
        const delta: string = payload.delta ?? '';
        if (delta) {
          setText(prev => prev + delta);
          maybeOpenFormFromText(delta);
        }
        break;
      }

      case 'final': {
        const t: string = payload.text ?? '';
        if (t) {
          setText(t);
          maybeOpenFormFromText(t);
        }
        break;
      }

      case 'done':
        setStreaming(false);
        backoffRef.current = 1000;
        break;

      case 'error':
        setLastError(payload.message || 'Unbekannter Fehler');
        setStreaming(false);
        break;

      case 'pong':
        break;

      default:
        // Falls ein Textfeld außerhalb obiger Events kommt (LCEL frames o.ä.)
        const maybeText =
          payload?.message?.data?.content ??
          payload?.message?.content ??
          payload?.content;
        if (typeof maybeText === 'string') {
          setText(prev => prev + maybeText);
          maybeOpenFormFromText(maybeText);
        }
        break;
    }
  }, [emitUiAction, maybeOpenFormFromText]);

  const connect = useCallback(() => {
    if (!url) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(url, 'json');
      wsRef.current = ws;
      setLastError(null);

      ws.onopen = () => {
        setConnected(true);
        backoffRef.current = 1000;
        firedNeedParamsRef.current = false;
        startHeartbeat();
      };

      ws.onmessage = handleMessage;
      ws.onerror = () => setLastError('WebSocket Fehler');
      ws.onclose = () => {
        setConnected(false);
        setStreaming(false);
        clearHeartbeat();
        scheduleReconnect();
      };
    } catch (e: any) {
      setLastError(e?.message ?? 'Verbindungsfehler');
      scheduleReconnect();
    }
  }, [handleMessage, scheduleReconnect, url]);

  useEffect(() => {
    if (!token) return;
    connect();
    return () => cleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  const send = useCallback(
    (input: string, params?: Record<string, any>) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        setLastError('Nicht verbunden');
        return;
      }
      setStreaming(true);
      setText('');
      firedNeedParamsRef.current = false;

      // Graph-Modus + expliziter Graph-Name (consult), damit der Consult-Flow sicher läuft
      const payload: any = { chat_id: chatId, input, mode: 'graph', graph: 'consult' };
      if (params && typeof params === 'object') payload.params = params;

      try {
        ws.send(JSON.stringify(payload));
      } catch (e: any) {
        setLastError(e?.message ?? 'Senden fehlgeschlagen');
        setStreaming(false);
      }
    },
    [chatId]
  );

  const cancel = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const threadId = lastThreadIdRef.current || `api:${chatId}`;
    try {
      ws.send(JSON.stringify({ type: 'cancel', chat_id: chatId, thread_id: threadId }));
    } catch {}
    setStreaming(false);
  }, [chatId]);

  return { connected, streaming, text, lastError, send, cancel };
}

```


## frontend/src/lib/utils.ts

```ts
// 📁 frontend/app/lib/utils.ts
export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

```


## frontend/src/lib/ws.ts

```ts
// WebSocket-Client mit Token-Refresh, Reconnect, Heartbeat und Stream-Events.

export type StreamStartPayload = { threadId: string; agent?: string };
export type StreamDeltaPayload = { delta: string; done?: boolean };
export type StreamDonePayload = { threadId?: string };

export type ChatWsEvents = {
  onOpen?: () => void;
  onClose?: (ev: CloseEvent) => void;
  onError?: (ev: Event) => void;
  onMessage?: (msg: unknown) => void;
  onStreamStart?: (p: StreamStartPayload) => void;
  onStreamDelta?: (p: StreamDeltaPayload) => void;
  onStreamDone?: (p: StreamDonePayload) => void;
  onUiAction?: (ui: any) => void; // ← hinzugefügt
};

export type WSOptions = {
  token?: string; // Fallback-Token (besser: getToken)
  url?: string; // ws[s]://… oder Pfad (/api/v1/ai/ws)
  protocols?: string | string[];
  heartbeatMs?: number;
  maxBackoffMs?: number;
  getToken?: () => Promise<string | undefined>;
};

function wsOrigin(): { proto: "ws:" | "wss:"; host: string } {
  const { protocol, host } = window.location;
  return { proto: protocol === "https:" ? "wss:" : "ws:", host };
}

function withToken(urlOrPath: string, token: string | undefined): string {
  const { proto, host } = wsOrigin();
  const isAbs = urlOrPath.startsWith("ws://") || urlOrPath.startsWith("wss://");
  const base = isAbs ? urlOrPath : `${proto}//${host}${urlOrPath.startsWith("/") ? "" : "/"}${urlOrPath}`;
  if (!token) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}token=${encodeURIComponent(token)}`;
}

function safeParse(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}

class ChatWsClient {
  private ws?: WebSocket;
  private hb?: number;
  private backoff = 1000;
  private closed = false;
  private openPromise?: Promise<void>;
  private started = false;
  private lastThreadId?: string;
  private firedNeedParams = false;

  private readonly opts: Required<Pick<WSOptions, "heartbeatMs" | "maxBackoffMs">> & Omit<WSOptions, "heartbeatMs" | "maxBackoffMs">;
  private readonly ev: ChatWsEvents;
  private readonly subs = new Set<(msg: unknown) => void>();

  constructor(options: WSOptions & ChatWsEvents) {
    this.opts = {
      url: options.url ?? "/api/v1/ai/ws",
      protocols: options.protocols ?? ["json"],
      heartbeatMs: options.heartbeatMs ?? 15000,
      maxBackoffMs: options.maxBackoffMs ?? 30000,
      token: options.token,
      getToken: options.getToken,
    };
    this.ev = {
      onOpen: options.onOpen,
      onClose: options.onClose,
      onError: options.onError,
      onMessage: options.onMessage,
      onStreamStart: options.onStreamStart,
      onStreamDelta: options.onStreamDelta,
      onStreamDone: options.onStreamDone,
      onUiAction: options.onUiAction, // ← hinzugefügt
    };
  }

  async connect(): Promise<void> {
    if (this.openPromise) return this.openPromise;
    this.closed = false;

    this.openPromise = new Promise<void>(async (resolve, reject) => {
      let token: string | undefined = undefined;
      try {
        token = (await this.opts.getToken?.()) ?? this.opts.token;
      } catch {}

      const url = withToken(this.opts.url!, token);
      try {
        this.ws = new WebSocket(url, this.opts.protocols as string[]);
      } catch (e) {
        reject(e);
        return;
      }

      const ws = this.ws;

      ws.onopen = () => {
        this.backoff = 1000;
        this.started = false;
        this.firedNeedParams = false;
        this.startHeartbeat();
        this.ev.onOpen?.();
        resolve();
      };

      ws.onmessage = (ev) => {
        const data = typeof ev.data === "string" ? safeParse(ev.data) : ev.data;
        this.ev.onMessage?.(data);
        for (const cb of this.subs) cb(data);
        this.routeStreamEvents(data);
      };

      ws.onclose = (ev) => {
        this.stopHeartbeat();
        this.ev.onClose?.(ev);
        if (!this.closed) this.scheduleReconnect();
      };

      ws.onerror = (ev) => {
        this.ev.onError?.(ev);
      };
    });

    return this.openPromise;
  }

  subscribe(handler: (msg: unknown) => void): () => void {
    this.subs.add(handler);
    return () => this.subs.delete(handler);
  }

  private sendInternal(payload: unknown): void {
    const s = JSON.stringify(payload);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(s);
  }

  send(payload: unknown): void {
    this.sendInternal(payload);
  }

  request(input: string, chatId = "default", extra?: Record<string, unknown>): void {
    this.firedNeedParams = false;
    this.sendInternal({ chat_id: chatId || "default", input, ...(extra || {}) });
  }

  cancel(threadId?: string): void {
    const tid = threadId ?? this.lastThreadId ?? "default";
    this.sendInternal({ type: "cancel", thread_id: tid });
  }

  close(): void {
    this.closed = true;
    this.stopHeartbeat();
    try {
      this.ws?.close();
    } catch {}
    this.ws = undefined;
    this.openPromise = undefined;
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.hb = window.setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      try {
        this.ws.send(JSON.stringify({ type: "ping", ts: Date.now() }));
      } catch {}
    }, this.opts.heartbeatMs);
  }

  private stopHeartbeat() {
    if (this.hb) {
      window.clearInterval(this.hb);
      this.hb = undefined;
    }
  }

  private scheduleReconnect() {
    const delay = Math.min(this.backoff, this.opts.maxBackoffMs);
    this.backoff = Math.min(this.backoff * 2, this.opts.maxBackoffMs);
    window.setTimeout(() => {
      if (this.closed) return;
      this.openPromise = undefined; // neues connect() → neuer Token
      this.connect().catch(() => this.scheduleReconnect());
    }, delay);
  }

  private routeStreamEvents(raw: unknown) {
    const d = raw as any;

    // Backend: {"phase":"starting", thread_id, ...}
    if (d?.phase === "starting") {
      this.started = true;
      const tid = d.thread_id ?? "default";
      this.lastThreadId = tid;
      this.ev.onStreamStart?.({ threadId: tid, agent: d?.agent });
    }

    // Debug-Events: {"event":"dbg", "meta":{"langgraph_node":"ask_missing"}, ...}
    if (d?.event === "dbg") {
      const node = (d?.meta?.langgraph_node || d?.meta?.run_name || d?.name || "").toString().toLowerCase();
      if (!this.firedNeedParams && node === "ask_missing") {
        this.firedNeedParams = true;
        window.dispatchEvent(new CustomEvent("sai:need-params", { detail: { node } }));
        // echtes UI-Open-Event
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: { ui_action: "open_form" } }));
      }
    }

    // UI-Events: {"event":"ui_action", ...} oder Backward-Compat {"ui_event": {...}}: {"event":"ui_action", ...} oder Backward-Compat {"ui_event": {...}}
      if (d?.event === "ui_action" || d?.ui_event || typeof d?.ui_action !== "undefined") {
        const ua = typeof d?.ui_action === "string"
          ? { ui_action: d.ui_action }
          : (d?.ui_event && typeof d.ui_event === "object" ? d.ui_event : d);
        this.ev.onUiAction?.(ua);
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: ua }));
      }

    // Token-Stream
    if (typeof d?.delta !== "undefined") {
      if (
        !this.firedNeedParams &&
        typeof d.delta === "string" &&
        /mir fehlen noch folgende angaben|kannst du mir diese bitte nennen|präzise.*empfehlung.*brauche.*noch kurz|pack die werte gern.*eine zeile/i.test(d.delta)
      ) {
        this.firedNeedParams = true;
        window.dispatchEvent(new CustomEvent("sai:need-params", { detail: { hint: "text" } }));
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: { ui_action: "open_form" } }));
      }
      this.ev.onStreamDelta?.({ delta: String(d.delta), done: false });
    }

    // Optional final text
    if (d?.final?.text && !d?.delta) {
      if (
        !this.firedNeedParams &&
        typeof d.final.text === "string" &&
        /mir fehlen noch folgende angaben|kannst du mir diese bitte nennen|präzise.*empfehlung.*brauche.*noch kurz|pack die werte gern.*eine zeile/i.test(d.final.text)
      ) {
        this.firedNeedParams = true;
        window.dispatchEvent(new CustomEvent("sai:need-params", { detail: { hint: "final" } }));
        window.dispatchEvent(new CustomEvent("sealai:ui_action", { detail: { ui_action: "open_form" } }));
      }
      this.ev.onStreamDelta?.({ delta: String(d.final.text), done: false });
    }

    // Done
    if (d?.event === "done" || d?.done === true) {
      this.ev.onStreamDone?.({ threadId: d.thread_id });
    }

    // LCEL / frames
    if (d?.message) {
      if (!this.started) {
        this.started = true;
        const tid = d?.meta?.thread_id ?? "default";
        this.lastThreadId = tid;
        this.ev.onStreamStart?.({ threadId: tid, agent: d?.message?.name });
      }
      const content = d?.message?.data?.content ?? d?.message?.content;
      if (typeof content === "string") this.ev.onStreamDelta?.({ delta: content, done: false });
    }
  }
}

export default ChatWsClient;

```


## frontend/src/styles/chat-markdown.css

```css
/* ===== Grok-like Markdown UX for SealAI ===== */
:root{
  --md-font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Apple Color Emoji","Segoe UI Emoji","Segoe UI Symbol", sans-serif;
  --md-font-size: 15.5px;
  --md-line-height: 1.65;
  --md-tight-line: 1.45;

  --md-fg: #111827;        /* text */
  --md-fg-soft: #4B5563;   /* muted */
  --md-fg-strong: #0F172A;

  --md-hr: #E5E7EB;
  --md-border: #E5E7EB;

  --code-bg: #0F172A;      /* Grok: dark code blocks */
  --code-fg: #F9FAFB;
  --code-inline-bg: #F3F4F6;
  --code-inline-fg: #374151;

  --space-xxs: 0.25rem;
  --space-xs:  0.375rem;
  --space-sm:  0.5rem;
  --space-md:  0.75rem;   /* primary paragraph gap ~12px */
  --space-lg:  1rem;
  --space-xl:  1.25rem;
}

/* Root container used by MarkdownMessage */
.chat-markdown,
.markdown-content,
.markdown-body{
  font-family: var(--md-font-family);
  font-size: var(--md-font-size);
  line-height: var(--md-line-height);
  color: var(--md-fg);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Paragraphs: compact like Grok */
.chat-markdown p,
.markdown-content p,
.markdown-body p{
  margin: var(--space-md) 0;
}

/* Headings: clear, not oversized */
.chat-markdown h1, .markdown-content h1, .markdown-body h1{
  font-size: 1.35rem;
  line-height: var(--md-tight-line);
  font-weight: 600;
  letter-spacing: -0.01em;
  margin: var(--space-lg) 0 var(--space-sm);
  color: var(--md-fg);
}
.chat-markdown h2, .markdown-content h2, .markdown-body h2{
  font-size: 1.18rem;
  line-height: var(--md-tight-line);
  font-weight: 600;
  margin: var(--space-lg) 0 var(--space-sm);
}
.chat-markdown h3, .markdown-content h3, .markdown-body h3{
  font-size: 1.05rem;
  line-height: var(--md-tight-line);
  font-weight: 600;
  margin: var(--space-md) 0 var(--space-xs);
}
.chat-markdown h4, .markdown-content h4, .markdown-body h4{
  font-size: .98rem;
  line-height: var(--md-tight-line);
  font-weight: 600;
  margin: var(--space-sm) 0 var(--space-xxs);
}

/* Links */
.chat-markdown a,
.markdown-content a,
.markdown-body a{
  color: #2563EB;
  text-decoration: none;
}
.chat-markdown a:hover,
.markdown-content a:hover,
.markdown-body a:hover{
  text-decoration: underline;
}

/* Blockquote: subtle */
.chat-markdown blockquote,
.markdown-content blockquote,
.markdown-body blockquote{
  margin: var(--space-md) 0;
  padding: var(--space-xs) var(--space-md);
  border-left: 3px solid var(--md-border);
  color: var(--md-fg-soft);
  background: #FAFAFA;
  border-radius: 0 8px 8px 0;
}

/* Strong */
.chat-markdown strong,
.markdown-content strong,
.markdown-body strong{
  font-weight: 600;
  color: var(--md-fg-strong);
}

/* Lists: top-level compact bullets, nested level as indented "–" dashes */
.chat-markdown ul,
.markdown-content ul,
.markdown-body ul,
.chat-markdown ol,
.markdown-content ol,
.markdown-body ol{
  margin: var(--space-sm) 0;
  padding-left: 1.15rem;
}

.chat-markdown li,
.markdown-content li,
.markdown-body li{
  margin: 0.18rem 0;
}

/* Nested UL one level deeper → dash style with extra indent */
.chat-markdown ul ul,
.markdown-content ul ul,
.markdown-body ul ul{
  list-style: none;
  padding-left: 1.25rem;
  margin-top: 0.15rem;
}
.chat-markdown ul ul > li,
.markdown-content ul ul > li,
.markdown-body ul ul > li{
  position: relative;
  padding-left: 0.8rem;
}
.chat-markdown ul ul > li::before,
.markdown-content ul ul > li::before,
.markdown-body ul ul > li::before{
  content: "–";
  position: absolute;
  left: 0;
  top: 0;
  color: #374151;
}

/* Horizontal rule */
.chat-markdown hr,
.markdown-content hr,
.markdown-body hr{
  border: none;
  border-top: 1px solid var(--md-hr);
  margin: var(--space-lg) 0;
}

/* Images */
.chat-markdown img,
.markdown-content img,
.markdown-body img{
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: var(--space-sm) 0;
}

/* Inline code */
.chat-markdown code,
.markdown-content code,
.markdown-body code{
  font-size: 0.92em;
  padding: 0.15em 0.35em;
  border-radius: 0.3em;
  background: var(--code-inline-bg);
  color: var(--code-inline-fg);
}

/* Code blocks */
.chat-markdown pre,
.markdown-content pre,
.markdown-body pre{
  background: var(--code-bg);
  color: var(--code-fg);
  border-radius: 10px;
  padding: 0.9em 1em;
  margin: var(--space-sm) 0;
  overflow-x: auto;
  font-size: 0.92rem;
  line-height: 1.5;
}

/* Tables */
.chat-markdown table,
.markdown-content table,
.markdown-body table{
  border-collapse: collapse;
  margin: var(--space-sm) 0;
  width: 100%;
}
.chat-markdown th, .chat-markdown td,
.markdown-content th, .markdown-content td,
.markdown-body th, .markdown-body td{
  border: 1px solid var(--md-border);
  padding: 0.45rem 0.6rem;
}
.chat-markdown th,
.markdown-content th,
.markdown-body th{
  background: #F8FAFC;
  font-weight: 600;
}

/* Trim first/last margins inside message bubbles */
.chat-markdown > :first-child,
.markdown-content > :first-child,
.markdown-body > :first-child{ margin-top: 0 !important; }
.chat-markdown > :last-child,
.markdown-content > :last-child,
.markdown-body > :last-child{ margin-bottom: 0 !important; }

/* ===== Components used by MarkdownMessage (cm-*) ===== */
.cm-p,
.cm-h1, .cm-h2, .cm-h3, .cm-h4,
.cm-li, .cm-ul, .cm-ol,
.cm-quote, .cm-a, .cm-th, .cm-td, .cm-table{
  color: var(--md-fg);
  font-size: var(--md-font-size);
  line-height: var(--md-line-height);
}

.cm-h1 { font-size: 1.35rem; font-weight: 600; margin: var(--space-lg) 0 var(--space-sm); }
.cm-h2 { font-size: 1.18rem; font-weight: 600; margin: var(--space-lg) 0 var(--space-sm); }
.cm-h3 { font-size: 1.05rem; font-weight: 600; margin: var(--space-md) 0 var(--space-xs); }
.cm-h4 { font-size: .98rem;  font-weight: 600; margin: var(--space-sm) 0 var(--space-xxs); }

.cm-quote{
  border-left: 3px solid var(--md-border);
  background: #FAFAFA;
  padding: var(--space-xs) var(--space-md);
  border-radius: 0 8px 8px 0;
  color: var(--md-fg-soft);
}

.cm-a{ color:#2563EB; text-decoration:none; }
.cm-a:hover{ text-decoration:underline; }

.cm-th, .cm-td{
  border: 1px solid var(--md-border);
  padding: 0.45rem 0.6rem;
}
.cm-th{ background:#F8FAFC; font-weight:600; }


/* --- Assistant ohne Rahmen + Letterpress-Optik --- */
.cm-assistant{
  background: transparent !important;
  box-shadow: none !important;
  color: #1f2937;        /* slate-800 */
  font-weight: 500;
  /* sanfte Prägung: Licht von oben, Mini-Schatten unten */
  text-shadow:
    0 1px 0 rgba(255,255,255,0.92),
    0 -1px 0 rgba(0,0,0,0.03);
}

/* optional: Headings beim Assistant minimal dichter setzen */
.cm-assistant .cm-h1,
.cm-assistant .cm-h2,
.cm-assistant .cm-h3,
.cm-assistant .cm-h4 {
  letter-spacing: -0.003em;
}

```


## frontend/src/styles/globals.css

```css
/* Inter – leicht, kompakt */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

@tailwind base;
@tailwind components;
@tailwind utilities;

/* Basistypo: minimal kleiner für “Grok-Look” */
html {
  font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif;
  font-size: 15px;                 /* ↓ von 16px */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
  font-feature-settings: "liga","calt","ss01","cv05";
  font-variation-settings: normal;
}

body {
  @apply bg-white text-gray-800;
}

/* Scrollbar dezent */
.scrollbar-thin { scrollbar-width: thin; }
.scrollbar-thumb-blue-200::-webkit-scrollbar-thumb { background-color: #bfdbfe; }
.scrollbar-thumb-blue-200::-webkit-scrollbar { width: 8px; }

.chat-scroll-container { scrollbar-gutter: stable both-edges; }

/* Optional generelles Ausblenden der Scrollbar im Chatbereich */
::-webkit-scrollbar { width: 0px !important; background: transparent !important; }
.chat-scroll-hide { scrollbar-width: none !important; -ms-overflow-style: none !important; }
.chat-scroll-hide::-webkit-scrollbar { display: none !important; }

/* Markdown-Reset: kompakte Abstände (falls andere Render-Pfade) */
.markdown-body, .markdown-content { font-family: inherit; }

.markdown-body p,
.markdown-body ul,
.markdown-body ol,
.markdown-body li,
.markdown-body blockquote,
.markdown-content p,
.markdown-content ul,
.markdown-content ol,
.markdown-content li,
.markdown-content blockquote {
  margin: 0 !important;
  padding: 0 !important;
  line-height: 1.45;
}

.markdown-body ul,
.markdown-body ol,
.markdown-content ul,
.markdown-content ol {
  padding-left: 1.25rem !important;
}

.markdown-body li,
.markdown-content li {
  display: list-item !important;
  margin: 0.18rem 0 !important;
}

/* Optional kompakter Code außerhalb von cm-Styles */
.markdown-body code, .markdown-content code {
  font-size: 90%;
  padding: 0.15em 0.35em;
  border-radius: 0.3em;
  background: #f3f4f6;
  color: #374151;
}

.markdown-body pre, .markdown-content pre {
  background: #111827;
  color: #f3f4f6;
  border-radius: 8px;
  padding: 0.9em;
  margin: 0.45em 0;
  font-size: 92%;
  overflow-x: auto;
}

/* Kleinere, angenehm dichte Tabellen global */
.markdown-body table, .markdown-content table {
  border-collapse: collapse;
  margin: 0.45em 0 !important;
}
.markdown-body th, .markdown-content th {
  background: #f4f4f4;
  font-weight: 600;
}

```


## frontend/src/types/chat.ts

```ts
export type Message = {
  role: "user" | "assistant" | "system";
  content: string;
};

```


## frontend/src/types/markdown-to-jsx.d.ts

```ts
declare module 'markdown-to-jsx';

```


## frontend/src/types/next-auth.d.ts

```ts
import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    accessToken?: string | null;
    idToken?: string | null;
    expires_at?: number | null;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string | null;
    idToken?: string | null;
    expires_at?: number | null;
  }
}

```


## frontend/src/types/ui.ts

```ts
export type UiAction =
  | {
      ui_action: "open_form";
      form_id: string;
      schema_ref?: string;   // z.B. "domains/rwdr/params@1.0.0"
      missing: string[];
      prefill: Record<string, unknown>;
    }
  | {
      ui_action: "calc_snapshot";
      derived: {
        calculated?: Record<string, number | string>;
        flags?: Record<string, unknown>;
        warnings?: string[];
        [k: string]: unknown;
      };
    }
  | Record<string, unknown>; // fallback


```


## frontend/tailwind.config.js

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        // OpenAI-Hausschrift, Fallback auf SystemSans
        sans: ['Söhne', 'Inter', 'ui-sans-serif', 'system-ui'],
      },
      colors: {
        // Chat-Hintergrund
        chatBg: '#FFFFFF',           // Main chat area
        userBg: '#FFFFFF',           // User bubble
        assistantBg: '#F7F7F8',      // Assistant bubble
        inputBorder: '#D1D5DB',      // Input-Feld-Rand
        inputFocus: '#10B981',       // Input-Fokusring (emerald-500)
      },
      borderRadius: {
        md: '6px',  // für Message-Bubbles
        lg: '8px',  // für Input-Feld
      },
      fontSize: {
        base: ['16px', '24px'],            // Fließtext
        'xl-title': ['20px', '1.75'],      // Header im Chat
        sm: ['12px', '18px'],              // Kleintexte
      },
      typography: (theme) => ({
        DEFAULT: {
          css: {
            color: theme('colors.gray.800'),
            a: { color: theme('colors.blue.600'), textDecoration: 'underline' },
            strong: { fontWeight: '600' },
            code: {
              backgroundColor: theme('colors.gray.100'),
              padding: '0.2rem 0.4rem',
              borderRadius: '0.25rem',
              fontSize: '0.875em',
            },
            pre: {
              backgroundColor: theme('colors.gray.800'),
              color: theme('colors.white'),
              borderRadius: '0.5rem',
              padding: '1rem',
              overflowX: 'auto',
            },
            h1: { fontSize: '1.5em', marginTop: '1em', marginBottom: '0.5em', fontWeight: '700' },
            h2: { fontSize: '1.25em', marginTop: '1em', marginBottom: '0.5em', fontWeight: '600' },
            h3: { fontSize: '1.1em', marginTop: '1em', marginBottom: '0.5em', fontWeight: '600' },
            ul: { paddingLeft: '1.25em' },
            ol: { paddingLeft: '1.25em' },
            li: { marginTop: '0.25em', marginBottom: '0.25em' },
            blockquote: {
              borderLeft: `4px solid ${theme('colors.blue.300')}`,
              color: theme('colors.gray.500'),
              fontStyle: 'italic',
              paddingLeft: '1em',
              marginTop: '1em',
              marginBottom: '1em',
            },
          },
        },
      }),
    },
  },
  plugins: [require('@tailwindcss/typography')],
}

```


## nginx/00-tuning.conf

```nginx
# ---- Globales Nginx-Tuning (http-Kontext) ----
# Für WebSockets/Upgrade: definiert $connection_upgrade
map $http_upgrade $connection_upgrade {
  default upgrade;
  ''      close;
}

# Größere Header-/Cookie-/Proxy-Puffer für NextAuth
client_max_body_size            20m;
client_header_buffer_size       64k;
large_client_header_buffers     8 64k;

# Proxy-Puffer (Antwort-Header/Set-Cookie vom Upstream)
proxy_buffer_size               256k;
proxy_buffers                   16 256k;
proxy_busy_buffers_size         512k;

# Zeitlimits
proxy_connect_timeout           30s;
proxy_send_timeout              180s;
proxy_read_timeout              180s;

# HTTP/1.1 für Upstreams (WebSocket etc.)
proxy_http_version              1.1;

# Seltene Header mit Unterstrich (optional)
underscores_in_headers          on;

```


## nginx/Dockerfile

```nginx/Dockerfile
FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80 443

```


## nginx/backend.conf

```nginx
# Umleitung von HTTP zu HTTPS
server {
    listen 80;
    server_name sealai.net www.sealai.net auth.sealai.net;
    return 301 https://$host$request_uri;
}

# Hauptserver für HTTPS
server {
    listen 443 ssl http2;
    server_name sealai.net www.sealai.net;

    ssl_certificate /etc/letsencrypt/live/www.sealai.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.sealai.net/privkey.pem;

    # HSTS für Sicherheit
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # API an Backend weiterleiten
    location /ai/ {
        proxy_pass http://backend:8000/ai/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_http_version 1.1;
        proxy_set_header Connection "keep-alive";
        proxy_buffering off;  # Für Streaming
        proxy_cache off;
    }

    # Next.js Frontend weiterleiten
    location / {
        proxy_pass http://frontend:3000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_http_version 1.1;
        proxy_set_header Connection "upgrade";
        proxy_set_header Upgrade $http_upgrade;
        try_files $uri /index.html;
    }
}

# Keycloak-Server unter auth.sealai.net
server {
    listen 443 ssl http2;
    server_name auth.sealai.net;

    ssl_certificate /etc/letsencrypt/live/www.sealai.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.sealai.net/privkey.pem;

    location / {
        proxy_pass http://keycloak:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

```


## nginx/default.conf

```nginx
##
## NGINX Reverse Proxy für SealAI
##

# Upgrade-Header sauber setzen (http-Kontext, außerhalb von server{}-Blöcken)
map $http_upgrade $connection_upgrade {
  default upgrade;
  ''      close;
}

# HTTP: ACME + Redirect
server {
  listen 80;
  listen [::]:80;
  server_name sealai.net www.sealai.net auth.sealai.net;

  location ^~ /.well-known/acme-challenge/ {
    root /var/www/certbot;
    default_type "text/plain";
  }

  location = /health { return 200 'ok'; add_header Content-Type text/plain; }

  return 301 https://$host$request_uri;
}

# HTTPS Hauptdomain
server {
  listen 443 ssl;
  listen [::]:443 ssl;
  http2 on;
  server_name sealai.net www.sealai.net;

  ssl_certificate     /etc/letsencrypt/live/sealai.net/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/sealai.net/privkey.pem;

  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

  # NextAuth: große Header -> eigene Location
  location ^~ /api/auth/ {
    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade           $http_upgrade;
    proxy_set_header Connection        $connection_upgrade;

    proxy_buffer_size       256k;
    proxy_buffers           16 256k;
    proxy_busy_buffers_size 512k;

    proxy_read_timeout 120s;
    proxy_send_timeout 120s;
    proxy_pass http://frontend:3000;
  }

  # Frontend (Next.js)
  location / {
    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade           $http_upgrade;
    proxy_set_header Connection        $connection_upgrade;
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;
    proxy_pass http://frontend:3000;
  }

  # Backend API (REST)
  location ^~ /api/v1/ {
    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;
    proxy_pass http://backend:8000/api/v1/;
  }

# WebSocket (neuer Frontend-Pfad) -> map auf Backend /api/v1/ai/ws
location = /api/v1/chat/ws {
  proxy_http_version 1.1;
  proxy_set_header Upgrade           $http_upgrade;
  proxy_set_header Connection        $connection_upgrade;
  proxy_set_header Host              $host;
  proxy_set_header X-Real-IP         $remote_addr;
  proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_read_timeout 86400s;
  proxy_send_timeout 86400s;
  proxy_buffering off;
  proxy_pass http://backend:8000/api/v1/ai/ws;   # <— WICHTIG: ai/ws!
}

  # WebSocket (bestehender Alias) -> /api/v1/ai/ws
  location = /api/v1/ai/ws {
    proxy_http_version 1.1;
    proxy_set_header Upgrade           $http_upgrade;
    proxy_set_header Connection        $connection_upgrade;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
    proxy_buffering off;
    proxy_pass http://backend:8000/api/v1/ai/ws;
  }

location = /api/v1/chat/sse {
  proxy_http_version 1.1;
  proxy_set_header Host              $host;
  proxy_set_header X-Real-IP         $remote_addr;
  proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_read_timeout 86400s;
  proxy_send_timeout 86400s;
  proxy_buffering off;
  proxy_request_buffering off;
  chunked_transfer_encoding on;
  add_header X-Accel-Buffering no;
  add_header Cache-Control "no-cache, no-transform";
  proxy_pass http://backend:8000/api/v1/langgraph/sse;  # <— Pfad an dein Backend anpassen
}

  # SSE (bestehender Pfad) -> /api/v1/langgraph/
  location ^~ /api/v1/langgraph/ {
    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
    proxy_buffering off;
    proxy_request_buffering off;
    chunked_transfer_encoding on;
    add_header X-Accel-Buffering no;
    add_header Cache-Control "no-cache, no-transform";
    proxy_pass http://backend:8000/api/v1/langgraph/;
  }

  location = /health { proxy_pass http://backend:8000/health; }
}

# HTTPS Auth-Subdomain → Keycloak
server {
  listen 443 ssl;
  listen [::]:443 ssl;
  http2 on;
  server_name auth.sealai.net;

  ssl_certificate     /etc/letsencrypt/live/auth.sealai.net/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/auth.sealai.net/privkey.pem;

  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

  location / {
    proxy_http_version 1.1;

    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Host  $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port  443;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;

    proxy_set_header Upgrade           $http_upgrade;
    proxy_set_header Connection        $connection_upgrade;

    proxy_read_timeout 300s;

    proxy_redirect ~^https?://localhost(/.*)$ https://auth.sealai.net$1;

    proxy_pass http://keycloak:8080;
  }
}

```


## nginx/docker-entrypoint-wait.sh

```sh
#!/bin/sh
set -e
echo "Warte, bis der Backend-Host erreichbar ist..."
until getent hosts backend; do
  echo "Backend noch nicht bereit – warte 2 Sekunden..."
  sleep 2
done
echo "Backend-Host gefunden, starte nginx!"
exec nginx -g 'daemon off;'

```


## nginx/snippets/keycloak_proxy.conf

```nginx
# Proxy-Header für Keycloak hinter Nginx (intern HTTPS:8443)
proxy_set_header Host               $host;
proxy_set_header X-Real-IP          $remote_addr;
proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;

# Nach außen sind wir HTTPS:443 – das will Keycloak wissen:
proxy_set_header X-Forwarded-Proto  https;
proxy_set_header X-Forwarded-Host   $host;
proxy_set_header X-Forwarded-Port   443;

# Keine automatische Umschreibung von Location-Headern
proxy_redirect off;

```


## nginx/snippets/sealai_proxy_headers.conf

```nginx
# Gemeinsame Proxy-Header (keine Duplikate von http_version/upgrade/etc.)
proxy_set_header Host               $host;
proxy_set_header X-Real-IP          $remote_addr;
proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto  $scheme;
proxy_set_header X-Forwarded-Host   $host;
proxy_set_header X-Forwarded-Port   $server_port;

# Keine proxy_http_version hier (nur im WS-Location setzen!)
# Kein proxy_redirect hier (nur dort, wo unbedingt nötig)
# Kein proxy_buffering off hier (nur für WS)

```


## nginx/streaming.conf

```nginx
server {
    listen 80;
    server_name 192.168.208.3;  # oder deine Domain

    location /ai/stream-test {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_cache off;
    }
}

```


## nginx/tuning.conf

```nginx
# wird automatisch im http-Block geladen (über /etc/nginx/conf.d/*.conf)
proxy_headers_hash_max_size 1024;
proxy_headers_hash_bucket_size 128;

large_client_header_buffers 8 32k;

gzip on;
gzip_comp_level 5;
gzip_min_length 1024;
gzip_vary on;
gzip_proxied any;
gzip_types
  text/plain
  text/css
  text/javascript
  application/javascript
  application/x-javascript
  application/json
  application/xml
  application/rss+xml
  application/vnd.ms-fontobject
  application/x-font-ttf
  font/opentype
  image/svg+xml
  image/x-icon;

```
