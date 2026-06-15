"""
client.py — Shared async HTTP client for the Aruba ClearPass REST API.

Features
--------
- Single persistent ``httpx.AsyncClient`` (connection pool reuse across all requests).
- OAuth2 ``client_credentials`` token caching with ``asyncio.Lock`` to prevent
  thundering-herd duplicate refreshes under concurrency.
- Automatic 401 → token invalidation → one refresh-and-retry cycle.
- Tenacity retry with exponential backoff (3 attempts, 1–10 s delay) for 5xx
  responses and connection/read timeouts.
- ``paginate()`` async generator that follows ``_links.next`` automatically up to a
  configurable ``max_pages`` limit.
- Consistent error helper ``format_error()`` for all MCP tool responses.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from clearpass_mcp.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def format_error(
    error: str,
    *,
    status_code: int | None = None,
    detail: str | None = None,
    path: str = "",
) -> dict[str, Any]:
    """
    Return a consistent error dict for MCP tool responses.

    Args:
        error: Human-readable error summary.
        status_code: HTTP status code, if available.
        detail: Raw server error body or exception message.
        path: The API path that was being called.

    Returns:
        ``{"error": ..., "status_code": ..., "detail": ..., "path": ...}``
    """
    return {"error": error, "status_code": status_code, "detail": detail, "path": path}


# ---------------------------------------------------------------------------
# Retry predicate
# ---------------------------------------------------------------------------


def _should_retry(exc: BaseException) -> bool:
    """Return ``True`` for 5xx HTTP errors and connection/read timeouts."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    return False


# ---------------------------------------------------------------------------
# ClearPassClient
# ---------------------------------------------------------------------------


class ClearPassClient:
    """
    Shared async HTTP client for the Aruba ClearPass Policy Manager REST API.

    Intended to be created once at server startup (via :func:`set_client`) and
    closed gracefully at shutdown (``await client.close()``).

    Example::

        settings = Settings()
        client = ClearPassClient(settings)
        data = await client.request("GET", "/endpoint", params={"limit": 25})
        await client.close()
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(
            verify=settings.CLEARPASS_VERIFY_SSL,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0),
            follow_redirects=True,
        )
        self._token_cache: dict[str, Any] = {
            "access_token": None,
            "expires_at": None,
        }
        self._token_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying httpx client and release all connections."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    async def _fetch_token(self) -> str:
        """
        Fetch a fresh OAuth2 token from ClearPass.

        Must only be called while holding ``self._token_lock``.
        """
        url = f"{self._settings.CLEARPASS_HOST}/api/oauth"
        payload: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self._settings.CLEARPASS_CLIENT_ID,
            "client_secret": self._settings.CLEARPASS_CLIENT_SECRET,
        }
        resp = await self._http.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        now = datetime.now(timezone.utc)
        access_token: str = str(data["access_token"])
        self._token_cache["access_token"] = access_token
        # Subtract 60 s from expires_in as a safety margin
        self._token_cache["expires_at"] = now + timedelta(
            seconds=int(data.get("expires_in", 3600)) - 60
        )
        logger.debug(
            "OAuth2 token refreshed. Expires at %s (UTC).", self._token_cache["expires_at"]
        )
        return access_token

    def _invalidate_token(self) -> None:
        """Clear the token cache so the next call forces a fresh fetch."""
        self._token_cache["access_token"] = None
        self._token_cache["expires_at"] = None

    async def get_token(self) -> str:
        """
        Return a valid OAuth2 bearer token, fetching or refreshing as needed.

        Uses a double-checked locking pattern to ensure only one coroutine
        performs the token refresh even under high concurrency.
        """
        now = datetime.now(timezone.utc)
        # Fast path — cached token still valid, no lock needed
        if (
            self._token_cache["access_token"] is not None
            and self._token_cache["expires_at"] is not None
            and self._token_cache["expires_at"] > now
        ):
            return str(self._token_cache["access_token"])

        # Slow path — acquire lock
        async with self._token_lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            if (
                self._token_cache["access_token"] is not None
                and self._token_cache["expires_at"] is not None
                and self._token_cache["expires_at"] > now
            ):
                return str(self._token_cache["access_token"])
            return await self._fetch_token()

    # ------------------------------------------------------------------
    # HTTP execution
    # ------------------------------------------------------------------

    async def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        *,
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> httpx.Response:
        """Send a single HTTP request (no retry logic at this level)."""
        return await self._http.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=json_body,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_should_retry),
        reraise=True,
    )
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make an authenticated request to the ClearPass REST API.

        Handles 401 → token refresh → one retry automatically **before**
        tenacity gets involved.  Tenacity then retries the whole call
        (including a fresh ``get_token()``) on 5xx and timeouts.

        Args:
            method: HTTP method — GET, POST, PATCH, PUT, or DELETE.
            path: API path relative to ``/api``, e.g. ``/endpoint`` or
                ``/session/abc123/disconnect``.
            params: Optional query parameters (GET only; ignored for writes).
            body: Optional JSON request body.

        Returns:
            Parsed JSON response dict, or ``{"status": "success", "code": 204}``
            for empty 204 responses.

        Raises:
            httpx.HTTPStatusError: For non-retryable 4xx errors (and 5xx after
                all retry attempts are exhausted).
            httpx.TimeoutException: If all retry attempts time out.
        """
        token = await self.get_token()
        url = f"{self._settings.CLEARPASS_HOST}/api{path}"
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        resp = await self._send(method, url, headers, params=params, json_body=body)

        # 401 — refresh token once and retry the same request
        if resp.status_code == 401:
            logger.warning("401 Unauthorized on %s %s — refreshing token and retrying.", method, path)
            self._invalidate_token()
            token = await self.get_token()
            headers["Authorization"] = f"Bearer {token}"
            resp = await self._send(method, url, headers, params=params, json_body=body)

        # Empty success
        if resp.status_code == 204:
            return {"status": "success", "code": 204}

        # Raise for 4xx/5xx so tenacity can decide whether to retry
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    async def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Async generator that yields each page of results, following ``_links.next``.

        ClearPass list endpoints return a HAL-style envelope::

            {
                "_links": {"next": {"href": "https://host/api/session?offset=25"}},
                "_embedded": {"items": [...]},
                "count": 100,
                "total": 250
            }

        This generator yields each full page dict.  Callers read ``_embedded``
        and can check whether ``"_links.next"`` is absent to know pagination ended.

        Args:
            path: Initial API path (e.g. ``/session``).
            params: Query parameters for the **first** request only.
            max_pages: Override the ``CLEARPASS_MAX_PAGES`` setting for this call.

        Yields:
            Each page's full response dict (including ``_links``, ``_embedded``,
            ``count``, and ``total``).

        Example::

            pages = []
            async for page in client.paginate("/session", params={"limit": 50}):
                pages.extend(page.get("_embedded", {}).get("items", []))
        """
        limit = max_pages if max_pages is not None else self._settings.CLEARPASS_MAX_PAGES
        current_path = path
        current_params: dict[str, Any] = dict(params or {})
        follow_params: dict[str, Any] = {}
        page_num = 0

        while page_num < limit:
            data = await self.request(
                "GET",
                current_path,
                params=current_params if page_num == 0 else follow_params,
            )
            yield data
            page_num += 1

            # Follow _links.next if present
            next_href: str | None = None
            links = data.get("_links")
            if isinstance(links, dict):
                next_link = links.get("next")
                if isinstance(next_link, dict):
                    next_href = next_link.get("href")

            if not next_href:
                break

            # Extract path and query params from the next URL
            parsed = urlparse(next_href)
            # Strip the "/api" prefix that ClearPass includes in full URLs
            raw_path: str = parsed.path
            if raw_path.startswith("/api"):
                raw_path = raw_path[4:]
            current_path = raw_path
            follow_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: ClearPassClient | None = None


def get_client() -> ClearPassClient:
    """
    Return the shared :class:`ClearPassClient` singleton.

    Raises ``RuntimeError`` if called before the server lifespan has initialized
    the client.  In tests, call :func:`set_client` with a mock instead.
    """
    if _instance is None:
        raise RuntimeError(
            "ClearPassClient is not initialized. "
            "Ensure the MCP server lifespan has started, or call set_client() in tests."
        )
    return _instance


def set_client(client: ClearPassClient | None) -> None:
    """
    Set the shared :class:`ClearPassClient` singleton.

    Called by the server lifespan on startup (with a real client) and on
    shutdown (with ``None``).  Also used by tests to inject a mock.
    """
    global _instance
    _instance = client
