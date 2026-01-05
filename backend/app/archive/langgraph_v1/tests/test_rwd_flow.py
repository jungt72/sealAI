from app.langgraph.compile import create_main_graph
from app.langgraph.state import MetaInfo, SealAIState


def test_rwd_flow_advances_phases(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    initial_state = SealAIState(
        slots={
            "user_query": "Bitte analysiere diese Radialwellendichtung für eine Pumpe.",
            "rwd_requirements": {
                "machine": "Pumpe",
                "application": "Radialwellendichtung",
                "medium": "Öl",
                "temperature_min": -10,
                "temperature_max": 130,
                "speed_rpm": 1450,
                "pressure_inner": 4.5,
                "pressure_outer": 1.0,
                "shaft_diameter": 48.0,
                "housing_diameter": 72.0,
            },
        },
        meta=MetaInfo(thread_id="t-rwd", user_id="u-test", trace_id="tr-test"),
    )

    graph = create_main_graph(require_async=False)
    result = graph.invoke(initial_state)

    assert result.get("phase") == "auswahl"
    assert result.get("requirements_coverage", 0.0) >= 0.5
    calc = result.get("rwd_calc_results")
    assert calc is not None
    assert "surface_speed_m_per_s" in calc
    assert "pv_value" in calc
