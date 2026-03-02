from __future__ import annotations

import sys
import types


class _DummyMetric:
    def labels(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self

    def inc(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None

    def observe(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None

    def set(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


sys.modules.setdefault(
    "prometheus_client",
    types.SimpleNamespace(Counter=lambda *a, **k: _DummyMetric(), Gauge=lambda *a, **k: _DummyMetric(), Histogram=lambda *a, **k: _DummyMetric()),
)
sys.modules.setdefault(
    "app.services.rag.bm25_store",
    types.SimpleNamespace(
        bm25_repo=types.SimpleNamespace(search=lambda *a, **k: []),
        BM25Repository=object,
    ),
)
sys.modules.setdefault(
    "app.langgraph_v2.utils.rag_cache",
    types.SimpleNamespace(
        RAGCache=type(
            "RAGCache",
            (),
            {
                "__init__": lambda self, *a, **k: None,
                "get": lambda self, *a, **k: None,
                "set": lambda self, *a, **k: None,
            },
        )
    ),
)

from app.langgraph_v2.sealai_graph_v2 import _deterministic_termination_router
from app.langgraph_v2.state import SealAIState
from app.services.rag.state import ConflictRecord, WorkingProfile


def test_deterministic_termination_router_routes_to_contract_output_when_all_gates_green() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            material="FKM",
            knowledge_coverage_check={"pressure_max_bar": True, "temperature_max_c": True, "extrusion_gap_mm": True},
            risk_mitigated=True,
            conflicts_detected=[],
        ),
        critical={"iteration_count": 2},
        turn_count=0,
    )

    assert _deterministic_termination_router(state) == "request_clarification_node"


def test_deterministic_termination_router_loops_back_when_coverage_or_risk_is_incomplete_before_turn_12() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            material="FKM",
            knowledge_coverage_check={"pressure_max_bar": True, "temperature_max_c": False},
            risk_mitigated=False,
            conflicts_detected=[],
        ),
        critical={"iteration_count": 5},
        turn_count=0,
    )

    assert _deterministic_termination_router(state) == "request_clarification_node"


def test_deterministic_termination_router_escalates_to_hitl_after_turn_12_with_unhandled_blocker() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            material="FKM",
            knowledge_coverage_check={"pressure_max_bar": True, "temperature_max_c": True},
            risk_mitigated=True,
            conflicts_detected=[
                ConflictRecord(
                    rule_id="CHEM_FKM_AMINE_BLOCKER",
                    severity="BLOCKER",
                    title="FKM + amines",
                    condition="material=FKM and medium_additives has amine",
                    reason="Chemical incompatibility",
                )
            ],
        ),
        critical={"iteration_count": 12},
        turn_count=12,
    )

    assert _deterministic_termination_router(state) == "request_clarification_node"
