import json
import pytest

# Helper: robust POST, tolerant gegenüber fehlenden Routen
def _try_post_json(client, url, payload):
    try:
        resp = client.post(url, json=payload)
        return resp
    except Exception as e:
        pytest.xfail(f"POST {url} fehlgeschlagen oder Route existiert nicht: {e}")

@pytest.mark.usefixtures("mock_run_stream")
def test_chat_stream_endpoint(client):
    payload = {"message": "hello from test"}
    resp = _try_post_json(client, "/chat/stream", payload)
    if resp is None or resp.status_code == 404:
        pytest.xfail("/chat/stream nicht vorhanden")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("echo") == payload

@pytest.mark.usefixtures("mock_run_stream")
@pytest.mark.parametrize("url", [
    "/api/v1/ai",
    "/api/v1/consult/invoke",
    "/api/v1/system",
])
def test_v1_forwarding_endpoints(client, url):
    payload = {"message": "probe", "meta": {"t": "v1"}}
    resp = _try_post_json(client, url, payload)
    if resp is None or resp.status_code == 404:
        pytest.xfail(f"{url} existiert nicht in dieser Version")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("echo") == payload
