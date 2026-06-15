"""
test_client.py — Unit tests for ClearPassClient.

Covers:
- OAuth2 token fetch and caching
- Token expiry (stale cache triggers refresh)
- Concurrent refresh (only one fetch under lock)
- 401 auto-refresh-and-retry
- Tenacity retry on 5xx
- Tenacity retry on timeout
- Pagination following _links.next
- Pagination stops at max_pages
- Error dict shape
- 204 response handling
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx

from clearpass_mcp.client import ClearPassClient, format_error
from clearpass_mcp.config import Settings
from tests.conftest import (
    REFRESHED_TOKEN_RESPONSE,
    TOKEN_RESPONSE,
    register_token_route,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_hal_page(items: list[Any], next_offset: int | None = None) -> dict[str, Any]:
    """Return a minimal HAL-envelope page dict."""
    data: dict[str, Any] = {
        "_embedded": {"items": items},
        "count": len(items),
        "total": 100,
    }
    if next_offset is not None:
        data["_links"] = {
            "next": {"href": f"https://clearpass.test/api/session?offset={next_offset}"}
        }
    return data


# ---------------------------------------------------------------------------
# Token fetch & caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_fetch_on_first_call(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """get_token() calls /api/oauth on the first invocation."""
    register_token_route(mock_router)
    client = ClearPassClient(settings)
    token = await client.get_token()
    assert token == TOKEN_RESPONSE["access_token"]
    calls = [c for c in mock_router.calls if "oauth" in str(c.request.url)]
    assert len(calls) == 1
    await client.close()


@pytest.mark.asyncio
async def test_token_cached_on_second_call(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """get_token() returns cached token without a second HTTP call."""
    register_token_route(mock_router)
    mock_router.post("https://clearpass.test/api/oauth").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    client = ClearPassClient(settings)
    t1 = await client.get_token()
    t2 = await client.get_token()
    assert t1 == t2
    # Only one HTTP call should have been made
    calls = [c for c in mock_router.calls if "/oauth" in str(c.request.url)]
    assert len(calls) == 1
    await client.close()


@pytest.mark.asyncio
async def test_token_refresh_when_expired(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """get_token() fetches a new token when the cached one has expired."""
    mock_router.post("https://clearpass.test/api/oauth").mock(
        side_effect=[
            httpx.Response(200, json=TOKEN_RESPONSE),
            httpx.Response(200, json=REFRESHED_TOKEN_RESPONSE),
        ]
    )
    client = ClearPassClient(settings)
    # Pre-warm with an already-expired token
    await client.get_token()
    client._token_cache["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

    token = await client.get_token()
    assert token == REFRESHED_TOKEN_RESPONSE["access_token"]
    await client.close()


@pytest.mark.asyncio
async def test_concurrent_token_refresh_only_fetches_once(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """Concurrent calls to get_token() should result in exactly one OAuth fetch."""
    fetch_count = 0

    async def _slow_oauth(*args: Any, **kwargs: Any) -> httpx.Response:
        nonlocal fetch_count
        fetch_count += 1
        await asyncio.sleep(0.05)  # simulate latency
        return httpx.Response(200, json=TOKEN_RESPONSE)

    mock_router.post("https://clearpass.test/api/oauth").mock(side_effect=_slow_oauth)
    client = ClearPassClient(settings)

    # Fire 10 concurrent get_token() calls
    tokens = await asyncio.gather(*[client.get_token() for _ in range(10)])

    assert all(t == TOKEN_RESPONSE["access_token"] for t in tokens)
    assert fetch_count == 1, f"Expected 1 token fetch, got {fetch_count}"
    await client.close()


# ---------------------------------------------------------------------------
# 401 auto-refresh-and-retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_triggers_token_refresh_and_retry(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """A 401 response triggers a token refresh and retries the original request."""
    # First token fetch
    mock_router.post("https://clearpass.test/api/oauth").mock(
        side_effect=[
            httpx.Response(200, json=TOKEN_RESPONSE),
            httpx.Response(200, json=REFRESHED_TOKEN_RESPONSE),
        ]
    )
    endpoint_route = mock_router.get("https://clearpass.test/api/endpoint").mock(
        side_effect=[
            httpx.Response(401, json={"message": "Unauthorized"}),
            httpx.Response(200, json={"id": 1, "mac_address": "AA-BB-CC-DD-EE-FF"}),
        ]
    )

    client = ClearPassClient(settings)
    result = await client.request("GET", "/endpoint")
    assert result["mac_address"] == "AA-BB-CC-DD-EE-FF"
    assert endpoint_route.call_count == 2
    await client.close()


# ---------------------------------------------------------------------------
# Retry on 5xx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_503(settings: Settings, mock_router: respx.MockRouter) -> None:
    """5xx responses are retried up to 3 times with tenacity."""
    mock_router.post("https://clearpass.test/api/oauth").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    route = mock_router.get("https://clearpass.test/api/endpoint").mock(
        side_effect=[
            httpx.Response(503, json={"message": "Service Unavailable"}),
            httpx.Response(503, json={"message": "Service Unavailable"}),
            httpx.Response(200, json={"id": 1}),
        ]
    )

    client = ClearPassClient(settings)
    # Patch tenacity wait to speed up the test
    with patch("clearpass_mcp.client.wait_exponential", return_value=lambda _: 0):
        result = await client.request("GET", "/endpoint")
    assert result["id"] == 1
    assert route.call_count == 3
    await client.close()


@pytest.mark.asyncio
async def test_raises_after_max_retries(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """HTTPStatusError is raised after all 3 retry attempts fail."""
    mock_router.post("https://clearpass.test/api/oauth").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    mock_router.get("https://clearpass.test/api/endpoint").mock(
        return_value=httpx.Response(502, json={"message": "Bad Gateway"})
    )

    client = ClearPassClient(settings)
    with pytest.raises(httpx.HTTPStatusError):
        with patch("clearpass_mcp.client.wait_exponential", return_value=lambda _: 0):
            await client.request("GET", "/endpoint")
    await client.close()


# ---------------------------------------------------------------------------
# 204 response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_204_returns_success_dict(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """A 204 No Content response is mapped to {"status": "success", "code": 204}."""
    mock_router.post("https://clearpass.test/api/oauth").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    mock_router.delete("https://clearpass.test/api/endpoint/1").mock(
        return_value=httpx.Response(204)
    )

    client = ClearPassClient(settings)
    result = await client.request("DELETE", "/endpoint/1")
    assert result == {"status": "success", "code": 204}
    await client.close()


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paginate_follows_next_link(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """paginate() follows _links.next until no next link is present."""
    mock_router.post("https://clearpass.test/api/oauth").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    # Page 1 → next link; Page 2 → no next link
    mock_router.get(url__startswith="https://clearpass.test/api/session").mock(
        side_effect=[
            httpx.Response(200, json=_make_hal_page([{"id": "s1"}], next_offset=25)),
            httpx.Response(200, json=_make_hal_page([{"id": "s2"}]))
        ]
    )

    client = ClearPassClient(settings)
    pages: list[dict[str, Any]] = []
    async for page in client.paginate("/session"):
        pages.append(page)

    assert len(pages) == 2
    assert pages[0]["_embedded"]["items"][0]["id"] == "s1"
    assert pages[1]["_embedded"]["items"][0]["id"] == "s2"
    await client.close()


@pytest.mark.asyncio
async def test_paginate_stops_at_max_pages(
    settings: Settings, mock_router: respx.MockRouter
) -> None:
    """paginate() stops after max_pages pages even if _links.next is present."""
    mock_router.post("https://clearpass.test/api/oauth").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    # Every page returns a next link
    mock_router.get(url__startswith="https://clearpass.test/api/session").mock(
        return_value=httpx.Response(200, json=_make_hal_page([{"id": "sx"}], next_offset=25))
    )

    client = ClearPassClient(settings)
    pages: list[dict[str, Any]] = []
    async for page in client.paginate("/session", max_pages=2):
        pages.append(page)

    assert len(pages) == 2
    await client.close()


# ---------------------------------------------------------------------------
# format_error helper
# ---------------------------------------------------------------------------


def test_format_error_shape() -> None:
    err = format_error("Something went wrong", status_code=404, detail="Not found", path="/foo")
    assert err["error"] == "Something went wrong"
    assert err["status_code"] == 404
    assert err["detail"] == "Not found"
    assert err["path"] == "/foo"


def test_format_error_defaults() -> None:
    err = format_error("Oops")
    assert err["status_code"] is None
    assert err["detail"] is None
    assert err["path"] == ""
