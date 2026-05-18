from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass
from hashlib import sha256
import json
import time
from pathlib import Path
from urllib import error
from urllib import parse, request

from .config import MAX_ROWS_PER_REQUEST


def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class GscApiError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        status: int,
        reason: str | None = None,
        description: str | None = None,
    ) -> None:
        parts = [f"{operation} failed with HTTP {status}"]
        if reason:
            parts.append(reason)
        if description:
            parts.append(description)
        super().__init__(": ".join(parts))
        self.operation = operation
        self.status = status
        self.reason = reason
        self.description = description


def _safe_http_error(exc: error.HTTPError, *, operation: str) -> GscApiError:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}
    reason = payload.get("error")
    description = payload.get("error_description")
    if not description and isinstance(payload.get("error"), dict):
        description = payload["error"].get("message")
        reason = payload["error"].get("status") or reason
    return GscApiError(
        operation=operation,
        status=exc.code,
        reason=reason,
        description=description,
    )


def _post_form(url: str, data: dict[str, str], *, operation: str) -> dict:
    body = parse.urlencode(data).encode("utf-8")
    req = request.Request(url, data=body, headers={"content-type": "application/x-www-form-urlencoded"})
    try:
        with request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise _safe_http_error(exc, operation=operation) from exc


def _post_json(url: str, token: str, payload: dict, *, operation: str = "GSC API request") -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=60) as res:
            text = res.read().decode("utf-8")
            return json.loads(text) if text else {}
    except error.HTTPError as exc:
        raise _safe_http_error(exc, operation=operation) from exc


@dataclass
class GscClient:
    site_url: str
    service_account_file: Path | None = None
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None

    def token(self) -> str:
        if self.access_token:
            return self.access_token
        if self.refresh_token and self.client_id and self.client_secret:
            payload = _post_form(
                "https://oauth2.googleapis.com/token",
                {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                operation="GSC OAuth token refresh",
            )
            self.access_token = payload["access_token"]
            return self.access_token
        if self.service_account_file:
            self.access_token = self._service_account_token()
            return self.access_token
        raise RuntimeError("No GSC credentials configured")

    def _service_account_token(self) -> str:
        # Minimal RS256 JWT assertion using openssl through Python stdlib would be fragile.
        # Phase 1 production currently uses OAuth refresh-token credentials; service-account
        # JSON is documented for future migration once GSC accepts that identity.
        raise RuntimeError("Service account auth is documented but not enabled in this minimal runtime")

    def query(self, *, date: str, search_type: str, dimensions: list[str], start_row: int) -> dict:
        site = parse.quote(self.site_url, safe="")
        url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
        payload = {
            "startDate": date,
            "endDate": date,
            "dimensions": dimensions,
            "searchType": search_type,
            "rowLimit": MAX_ROWS_PER_REQUEST,
            "startRow": start_row,
        }
        return _post_json(url, self.token(), payload, operation="GSC Search Analytics query")

    def inspect_url(self, *, inspection_url: str, site_url: str | None = None, language_code: str = "de-DE") -> dict:
        payload = {
            "inspectionUrl": inspection_url,
            "siteUrl": site_url or self.site_url,
            "languageCode": language_code,
        }
        return _post_json(
            "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
            self.token(),
            payload,
            operation="GSC URL Inspection",
        )


class MockGscClient:
    def __init__(self, responses: dict[tuple[str, tuple[str, ...], int], list[dict]]):
        self.responses = responses
        self.calls: list[tuple[str, tuple[str, ...], int]] = []

    def query(self, *, date: str, search_type: str, dimensions: list[str], start_row: int) -> dict:
        key = (date, tuple(dimensions), start_row)
        self.calls.append(key)
        return {"rows": self.responses.get(key, [])}
