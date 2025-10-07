from __future__ import annotations
from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import Annotated
from langgraph.graph import add_messages

class Params(TypedDict, total=False):
    shaft_d: float
    housing_d: float
    width: float
    medium: str
    pressure_bar: float
    temp_min_c: float
    temp_max_c: float
    speed_rpm: float

class Derived(TypedDict, total=False):
    v_m_s: float
    dn_value: float
    pv_indicator_bar_ms: float
    notes: List[str]

class Candidate(TypedDict, total=False):
    doc_id: str
    vendor_id: str
    title: str
    profile: str
    material: str
    paid_tier: str
    contract_valid_until: str
    active: bool
    score: float
    url: Optional[str]

class RFQPdfInfo(TypedDict, total=False):
    path: str
    created_at: str
    download_token: str

class UIEvent(TypedDict, total=False):
    ui_action: str
    payload: Dict[str, Any]

class SealAIState(TypedDict, total=False):
    messages: Annotated[List[Any], add_messages]
    mode: str
    params: Params
    derived: Derived
    candidates: List[Candidate]
    sources: List[Dict[str, Any]]
    user_action: Optional[str]
    rfq_pdf: Optional[RFQPdfInfo]
    ui_events: List[UIEvent]
    telemetry: Dict[str, Any]
    confidence: Optional[float]
    red_flags: bool
    regulatory: bool
