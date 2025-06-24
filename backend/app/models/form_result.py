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
