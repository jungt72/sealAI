# backend/app/services/chat/rate_limit.py
from __future__ import annotations

import math
import time
from typing import Optional

from redis.asyncio import Redis  # im requirements vorhanden
from app.services.chat.ws_config import get_ws_config

# Token Bucket pro Key (user_id/IP)
#   capacity = rate_limit_per_min
#   refill pro Sekunde = capacity / 60
# Redis Keys: ws:rl:<key> -> {"tokens": float, "ts": float}

async def _get_client() -> Redis:
    cfg = get_ws_config()
    return Redis.from_url(cfg.redis_url, encoding="utf-8", decode_responses=True)

async def token_bucket_allow(key: str) -> bool:
    cfg = get_ws_config()
    capacity = max(1, cfg.rate_limit_per_min)
    refill_per_sec = capacity / 60.0
    now = time.time()

    r = await _get_client()
    pipe = r.pipeline()
    # Mehrfach-GET vermeiden: packe alles in ein HGETALL
    data = await r.hgetall(key)

    if not data:
        # Erster Zugriff: voll gefüllter Bucket – nimm 1 Token weg
        await r.hset(key, mapping={"tokens": str(capacity - 1), "ts": str(now)})
        await r.expire(key, 120)
        return True

    try:
        tokens = float(data.get("tokens", str(capacity)))
        last_ts = float(data.get("ts", str(now)))
    except Exception:
        tokens = float(capacity)
        last_ts = now

    # Nachfüllen
    elapsed = max(0.0, now - last_ts)
    tokens = min(capacity, tokens + elapsed * refill_per_sec)

    if tokens < 1.0:
        # zu wenig Tokens
        await r.hset(key, mapping={"tokens": str(tokens), "ts": str(now)})
        await r.expire(key, 120)
        return False

    # 1 Token verbrauchen
    tokens -= 1.0
    await r.hset(key, mapping={"tokens": str(tokens), "ts": str(now)})
    await r.expire(key, 120)
    return True
