from io import BytesIO
from urllib.error import HTTPError

import pytest

from sealai_seo import gsc_client
from sealai_seo.gsc_client import GscApiError, GscClient


def test_oauth_error_is_actionable_and_redacted(monkeypatch):
    def fail_urlopen(req, timeout):
        raise HTTPError(
            req.full_url,
            400,
            "Bad Request",
            {},
            BytesIO(
                b'{"error":"invalid_grant","error_description":"Token has been expired or revoked."}'
            ),
        )

    monkeypatch.setattr(gsc_client.request, "urlopen", fail_urlopen)

    client = GscClient(
        site_url="sc-domain:sealingai.com",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
    )

    with pytest.raises(GscApiError) as exc:
        client.token()

    message = str(exc.value)
    assert "GSC OAuth token refresh failed with HTTP 400" in message
    assert "invalid_grant" in message
    assert "expired or revoked" in message
    assert "client-secret" not in message
    assert "refresh-token" not in message
