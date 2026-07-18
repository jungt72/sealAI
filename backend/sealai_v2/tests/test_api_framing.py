"""Phase 1a (cutover) — /api/v2/framing is the single backend-owned source of the safety-framing
texts. Public by design (no auth dependency — must serve pre-login and during auth outages), and
contract-pinned against ``contracts/framing.v2.json``: the SPA's build-time fallback is pinned to
the SAME file by its own suite, so the two ends cannot drift while both suites are green.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sealai_v2.api.main import app
from sealai_v2.core import framing as core_framing
from sealai_v2.render import renderer

_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "framing.v2.json"
_CONTRACT = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def test_framing_is_public_even_with_auth_unconfigured():
    # No dependency overrides, no auth settings: every other /api/v2 route fails closed,
    # the framing route must still serve (the documented exception).
    res = TestClient(app).get("/api/v2/framing")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "public, max-age=300"


def test_framing_payload_matches_contract():
    body = TestClient(app).get("/api/v2/framing").json()
    version = body.pop("version")
    assert body == _CONTRACT
    assert version == core_framing.framing_version()


def test_renderer_note_is_the_same_source():
    # Byte-identical single source: the briefing's Geltungsrahmen note IS core.framing's text.
    assert renderer.CLAIM_BOUNDARY is core_framing.GELTUNGSRAHMEN
    assert renderer.CLAIM_BOUNDARY == _CONTRACT["geltungsrahmen"]


def test_api_v2_health_alias():
    # The nginx /api/v2 proxy preserves the path — the routed liveness probe must exist.
    res = TestClient(app).get("/api/v2/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "sealai_v2"}


def test_metrics_endpoint_is_exposed_for_internal_prometheus_scraping():
    res = TestClient(app).get("/metrics")
    assert res.status_code == 200
    assert "http_requests_total" in res.text
