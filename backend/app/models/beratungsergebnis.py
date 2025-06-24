from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Beratungsergebnis(Base):
    __tablename__ = "beratungsergebnisse"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    session_id = Column(String, index=True)
    frage = Column(String)
    parameter = Column(JSON)
    antworten = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)
