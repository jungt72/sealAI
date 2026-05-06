from __future__ import annotations

import json
from typing import Any
import urllib.request


class DataForSeoClient:
    def __init__(self, *, login: str, password: str, base_url: str = "https://api.dataforseo.com/v3") -> None:
        self.login = login
        self.password = password
        self.base_url = base_url.rstrip("/")

    def get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        return self._request("GET", url)

    def post(self, path: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        body = json.dumps(payload).encode("utf-8")
        return self._request("POST", url, body)

    def _request(self, method: str, url: str, body: bytes | None = None) -> dict[str, Any]:
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, url, self.login, self.password)
        opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_mgr))
        request = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def user_data(self) -> dict[str, Any]:
        return self.get("/appendix/user_data")

    def google_ads_search_volume_live(
        self,
        *,
        keywords: list[str],
        location_code: int,
        language_code: str,
    ) -> dict[str, Any]:
        return self.post(
            "/keywords_data/google_ads/search_volume/live",
            [
                {
                    "location_code": location_code,
                    "language_code": language_code,
                    "keywords": keywords,
                }
            ],
        )


def summarize_user_data(payload: dict[str, Any]) -> dict[str, Any]:
    task = (payload.get("tasks") or [{}])[0]
    result = (task.get("result") or [{}])[0]
    money = result.get("money") or {}
    return {
        "status_code": payload.get("status_code"),
        "status_message": payload.get("status_message"),
        "cost": payload.get("cost"),
        "tasks_error": payload.get("tasks_error"),
        "login": result.get("login"),
        "balance": money.get("balance"),
    }
