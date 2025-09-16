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
