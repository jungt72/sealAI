from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.config.settings import Settings


def test_maturity_endpoint_distinguishes_status_from_runtime_activation() -> None:
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        knowledge_mode_enabled=False,
        manufacturer_handoff_enabled=False,
        compute_enabled=True,
        memory_enabled=True,
    )
    response = TestClient(app).get("/api/v2/meta/maturity")

    assert response.status_code == 200
    body = response.json()
    assert body["ssot_version"] == "2.0"
    assert body["modes"]["knowledge"] == {
        "horizon": "H1",
        "status": "in_build",
        "activation_gate": "M15",
        "activation_blockers": [
            "independent_domain_review_of_seed_claims",
            "exact_final_adjudicated_replay",
        ],
        "active": False,
    }
    assert body["modes"]["engineering"]["status"] == "in_build"
    assert body["modes"]["engineering"]["active"] is True
    assert body["modes"]["case"]["active"] is False
    assert body["modes"]["manufacturer_fit"]["active"] is False
