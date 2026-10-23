"""Deprecated compatibility module; GraceDays runtime now uses TursoDatabase.

This legacy HTTP client is retained temporarily so older local tests/integrations
that import WorkerClient do not break. The MCP server no longer depends on it.
"""
from __future__ import annotations

from typing import Any

import httpx


class WorkerAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class WorkerClient:
    """HTTP repository adapter. All persistence flows through a Cloudflare Worker."""

    def __init__(self, base_url: str, shared_secret: str | None, timeout: float = 8.0, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.shared_secret = shared_secret
        self.timeout = timeout
        self._transport = transport

    def _request(self, method: str, path: str, *, payload: dict[str, Any] | None = None, allow_missing_secret: bool = False) -> Any:
        if not self.shared_secret and not allow_missing_secret:
            raise WorkerAPIError("GRACEDAYS_SHARED_SECRET is missing. Configure the Python/Worker shared secret before accessing D1.")
        headers = {"Accept": "application/json"}
        if self.shared_secret:
            headers["X-GraceDays-Secret"] = self.shared_secret
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.request(method, f"{self.base_url}{path}", headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise WorkerAPIError(f"Cloudflare Worker request failed: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = {"error": response.text[:300]}
        if response.status_code >= 400:
            message = body.get("error", f"Worker returned HTTP {response.status_code}") if isinstance(body, dict) else f"Worker returned HTTP {response.status_code}"
            raise WorkerAPIError(str(message), response.status_code)
        return body

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", allow_missing_secret=True)

    def list_purchases(self, query: str = "", limit: int = 50) -> dict[str, Any]:
        import urllib.parse
        return self._request("GET", f"/api/purchases?q={urllib.parse.quote(query)}&limit={max(1, min(limit, 100))}")

    def get_purchase(self, purchase_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/purchases/{purchase_id}")

    def save_purchase(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/purchases", payload=payload)

    def delete_purchase(self, purchase_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/api/purchases/{purchase_id}")

    def update_purchase_status(self, purchase_id: str, status: str) -> dict[str, Any]:
        return self._request("PATCH", f"/api/purchases/{purchase_id}/status", payload={"status": status})

    def list_deadlines(self, include_closed: bool = False, limit: int = 200) -> dict[str, Any]:
        return self._request("GET", f"/api/deadlines?include_closed={'true' if include_closed else 'false'}&limit={max(1, min(limit, 300))}")

    def seed_demo(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("POST", "/api/demo/seed", payload={"purchases": records})

    def reset_demo(self) -> dict[str, Any]:
        return self._request("POST", "/api/demo/reset", payload={"scope": "demo_only"})
