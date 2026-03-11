from typing import Annotated, Any, Dict, List, Optional, TypedDict, Union
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

class ObservedLayer(TypedDict):
    """
    Observed Layer (Rohwerte, Units, Originalformulierungen).
    Capture Layer zur Erhöhung der Auditierbarkeit (Blueprint Section 02).
    """
    observed_inputs: List[Dict[str, Any]]
    raw_parameters: Dict[str, Any]

class NormalizedLayer(TypedDict):
    """
    Normalized Layer (Identity Gating).
    Strikte Trennung zwischen Rohdaten und validierten Identitäten (identity_class).
    """
    identity_records: Dict[str, Any]
    normalized_parameters: Dict[str, Any]

class AssertedLayer(TypedDict):
    """
    Asserted Layer (Typed Profiles).
    Fachlich validierter technischer State (Medium, Machine, Installation).
    """
    medium_profile: Dict[str, Any]
    machine_profile: Dict[str, Any]
    installation_profile: Dict[str, Any]
    operating_conditions: Dict[str, Any]  # temperature, pressure
    sealing_requirement_spec: Dict[str, Any]

class GovernanceLayer(TypedDict):
    """
    Governance Layer (Compliance & Readiness).
    Überwachung der Engineering Firewall und RFQ-Admissibility.
    """
    release_status: str  # inadmissible / precheck_only / manufacturer_validation_required / rfq_ready
    rfq_admissibility: str  # inadmissible / provisional / ready
    scope_of_validity: List[str]
    conflicts: List[Dict[str, Any]]

class CycleLayer(TypedDict):
    """
    Cycle Control (Determinismus & Revision).
    Revision-Tracking und deterministischer Assertion-Cycle (Blueprint Section 03).
    """
    analysis_cycle_id: str
    snapshot_parent_revision: int
    contract_obsolete: bool
    state_revision: int

class SealingAIState(TypedDict):
    """
    Unser striktes 5-Schichten-Modell aus Phase A.
    Verbindet technische Tiefe mit LLM-Orchestrierung ohne Engineering-Firewall-Bruch.
    """
    observed: ObservedLayer
    normalized: NormalizedLayer
    asserted: AssertedLayer
    governance: GovernanceLayer
    cycle: CycleLayer

class AgentState(TypedDict):
    """
    LangGraph Orchestration Layer State.
    Integriert LLM-Kontext (messages) und fachlichen State (sealing_state).
    """
    messages: Annotated[List[AnyMessage], add_messages]
    sealing_state: SealingAIState
    relevant_fact_cards: List[Dict[str, Any]]  # Speichert FactCards für Tool-Nodes (Phase H6)
    working_profile: Dict[str, Any]  # Extrahiertes Live-Profil (Druck, Temperatur, etc.)
    tenant_id: Optional[str]
