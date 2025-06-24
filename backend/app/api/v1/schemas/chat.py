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
