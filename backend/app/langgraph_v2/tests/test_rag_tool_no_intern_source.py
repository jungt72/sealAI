from app.langgraph_v2.utils import rag_tool


def test_format_hit_does_not_emit_intern_source_when_missing_metadata() -> None:
    rendered = rag_tool._format_hit({"metadata": {}, "text": "x", "vector_score": 0.1})
    assert "Quelle:" not in rendered
    assert "intern" not in rendered


def test_search_knowledge_base_norms_without_params_blocked(monkeypatch) -> None:
    # Hard block: category="norms" without material/temp/pressure must never
    # reach Qdrant — it returns an actionable error instead.
    captured = {}

    def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(rag_tool, "hybrid_retrieve", fake_retrieve)
    result = rag_tool.search_knowledge_base.invoke(
        {
            "query": "test",
            "category": "norms",
            "k": 3,
            "tenant": "tenant-1",
        }
    )
    assert "fehlende Parameter" in result
    assert "Material" in result
    assert not captured  # hybrid_retrieve was never called


def test_search_knowledge_base_applies_tenant_filter(monkeypatch) -> None:
    # Non-norm category falls through to Qdrant with tenant filter applied.
    captured = {}

    def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(rag_tool, "hybrid_retrieve", fake_retrieve)
    _ = rag_tool.search_knowledge_base.invoke(
        {
            "query": "test",
            "category": "troubleshooting",
            "k": 3,
            "tenant": "tenant-1",
        }
    )
    assert captured.get("metadata_filters") == {"tenant_id": "tenant-1", "category": "troubleshooting"}
    assert captured.get("tenant") == "tenant-1"


def test_search_knowledge_base_uses_deterministic_norms_for_numeric_limits(monkeypatch) -> None:
    called = {"deterministic": False, "vector": False}

    def fake_det(*, material, temp, pressure, tenant_id):  # noqa: ANN001
        called["deterministic"] = True
        assert material == "FKM"
        assert temp == 80.0
        assert pressure == 120.0
        assert tenant_id == "tenant-1"
        return {
            "matches": {
                "din_norms": [
                    {
                        "norm_code": "DIN 3770",
                        "temperature_min_c": -20.0,
                        "temperature_max_c": 120.0,
                        "pressure_min_bar": 10.0,
                        "pressure_max_bar": 350.0,
                        "version": 2,
                        "effective_date": "2025-01-01",
                    }
                ],
                "material_limits": [],
            }
        }

    def fake_retrieve(**kwargs):  # noqa: ANN003
        called["vector"] = True
        return []

    monkeypatch.setattr(rag_tool, "query_deterministic_norms", fake_det)
    monkeypatch.setattr(rag_tool, "hybrid_retrieve", fake_retrieve)

    rendered = rag_tool.search_knowledge_base.invoke(
        {
            "query": "Ist FKM bei 120 bar und 80°C zulässig?",
            "category": "norms",
            "k": 3,
            "tenant": "tenant-1",
            "material": "FKM",
            "temp": 80.0,
            "pressure": 120.0,
        }
    )

    assert called["deterministic"] is True
    assert called["vector"] is False
    assert "Deterministischer Normabgleich" in rendered
