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
