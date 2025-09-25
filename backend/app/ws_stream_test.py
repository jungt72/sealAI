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
