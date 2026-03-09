from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any

class ChatRequest(BaseModel):
    """
    API Request Modell für Chat-Anfragen (Phase F1).
    Erzwingt einen strikten API-Vertrag (Engineering before Language).
    """
    message: str = Field(..., min_length=1, description="Die Nutzereingabe an den Agenten.")
    session_id: Optional[str] = Field(default="default", description="Eindeutige ID zur Session-Nachverfolgung.")

    model_config = ConfigDict(extra="forbid")

class ChatResponse(BaseModel):
    """
    API Response Modell für Agenten-Antworten (Phase F1).
    Enthält die sprachliche Antwort sowie den technischen System-State.
    """
    reply: str = Field(..., description="Die Antwort des Agenten.")
    session_id: str = Field(..., description="Die Session-ID zur Nachverfolgung.")
    sealing_state: Dict[str, Any] = Field(..., description="Der aktuelle technische Zustand (SealingAIState).")

    model_config = ConfigDict(extra="forbid")
