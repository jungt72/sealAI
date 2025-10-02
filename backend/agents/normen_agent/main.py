from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="SealAI Normen-Agent", version="0.1.0")


class SearchIn(BaseModel):
    query: str = Field(default="", description="Freitext-Frage/Normenbezug")
    k: int = Field(default=6, ge=1, le=20)
    tenant: Optional[str] = None


@app.get("/health")
def health() -> Dict[str, str]:
    return {"ok": "1"}


@app.post("/v1/search")
def search(payload: SearchIn) -> List[Dict[str, Any]]:
    """
    Minimaler Stub: liefert deterministische, erklärende Dummy-Ergebnisse.
    Dieser Service steht exemplarisch für einen ausgelagerten Spezial-Agenten.
    """
    q = (payload.query or "").strip()
    base = [
        {
            "text": f"Hinweis: Keine internen Dokumente gefunden. Prüfe Normenbezug zur Anfrage: '{q}'.",
            "source": "normen_agent",
            "score": 0.42,
            "metadata": {"tenant": payload.tenant},
        },
        {
            "text": "Allgemeine Leitlinie: Bei hohen Temperaturen Material mit höherer Temperaturbeständigkeit (z.B. FKM, FFKM).",
            "source": "normen_agent",
            "score": 0.4,
            "metadata": {},
        },
    ]
    return base[: payload.k]

