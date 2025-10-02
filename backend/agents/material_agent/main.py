from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="SealAI Material-Agent", version="0.1.0")


class SearchIn(BaseModel):
    query: str = Field(default="", description="Freitext-Frage/Materialbezug")
    k: int = Field(default=6, ge=1, le=20)
    tenant: Optional[str] = None


@app.get("/health")
def health() -> Dict[str, str]:
    return {"ok": "1"}


@app.post("/v1/search")
def search(payload: SearchIn) -> List[Dict[str, Any]]:
    """
    Minimaler Stub: liefert deterministische, fachliche Dummy-Ergebnisse zum Material.
    Dieser Service steht exemplarisch für einen ausgelagerten Spezial-Agenten.
    """
    q = (payload.query or "").strip()
    base = [
        {
            "text": (
                "Material-Hinweis: Prüfe chemische Beständigkeit, Temperatur- und Druckbereich. "
                "Einsatz der Dichtungswerkstoffe abhängig von Medium und Norm. Anfrage: '%s'"
            )
            % q,
            "source": "material_agent",
            "score": 0.41,
            "metadata": {"tenant": payload.tenant},
        },
        {
            "text": (
                "Typische Zuordnung: NBR für Öle/Fette (bis ~100 °C), FKM für höhere Temperaturen, "
                "EPDM für Wasser/Heißwasser/Dampf (je nach Druck)."
            ),
            "source": "material_agent",
            "score": 0.4,
            "metadata": {},
        },
    ]
    return base[: payload.k]

