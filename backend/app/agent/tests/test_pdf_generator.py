from __future__ import annotations

import httpx
import pytest

from app.agent.documents import pdf_generator


class _DummyResponse:
    def __init__(self, *, status_code: int, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://gotenberg.example/forms/chromium/convert/html")
            response = httpx.Response(
                self.status_code,
                request=request,
                content=self.text.encode("utf-8"),
            )
            raise httpx.HTTPStatusError("request failed", request=request, response=response)


class _DummyAsyncClient:
    def __init__(self, *, timeout: float, response: _DummyResponse, capture: dict[str, object]) -> None:
        self.timeout = timeout
        self._response = response
        self._capture = capture

    async def __aenter__(self) -> "_DummyAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, url: str, *, files=None, data=None, headers=None):
        self._capture["url"] = url
        self._capture["files"] = files
        self._capture["data"] = data
        self._capture["headers"] = headers
        return self._response


@pytest.mark.anyio
async def test_generate_pdf_from_html_uses_configured_gotenberg_url(monkeypatch: pytest.MonkeyPatch) -> None:
    html = "<html><body>demo</body></html>"
    capture: dict[str, object] = {}
    response = _DummyResponse(status_code=200, content=b"%PDF-1.7")

    monkeypatch.setattr(
        pdf_generator.settings,
        "gotenberg_url",
        "https://gotenberg.example",
        raising=False,
    )
    monkeypatch.setattr(
        pdf_generator.httpx,
        "AsyncClient",
        lambda timeout=30.0: _DummyAsyncClient(timeout=timeout, response=response, capture=capture),
    )

    result = await pdf_generator.generate_pdf_from_html(html, idempotency_key="idem-123")

    assert result == b"%PDF-1.7"
    assert capture["url"] == "https://gotenberg.example/forms/chromium/convert/html"
    assert capture["data"] == {
        "marginTop": "1",
        "marginBottom": "1",
        "marginLeft": "1",
        "marginRight": "1",
        "paperWidth": "8.27",
        "paperHeight": "11.69",
    }
    assert capture["headers"] == {"X-Idempotency-Key": "idem-123"}
    assert capture["files"] == {
        "files": ("index.html", html.encode("utf-8"), "text/html"),
    }


@pytest.mark.anyio
async def test_generate_pdf_from_html_raises_clean_error_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture: dict[str, object] = {}
    response = _DummyResponse(status_code=503, text="service unavailable")

    monkeypatch.setattr(
        pdf_generator.settings,
        "gotenberg_url",
        "https://gotenberg.example/",
        raising=False,
    )
    monkeypatch.setattr(
        pdf_generator.httpx,
        "AsyncClient",
        lambda timeout=30.0: _DummyAsyncClient(timeout=timeout, response=response, capture=capture),
    )

    with pytest.raises(pdf_generator.PdfGenerationError, match="service unavailable"):
        await pdf_generator.generate_pdf_from_html("<html></html>")

    assert capture["url"] == "https://gotenberg.example/forms/chromium/convert/html"
