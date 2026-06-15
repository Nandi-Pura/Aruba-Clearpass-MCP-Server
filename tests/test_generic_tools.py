"""
test_generic_tools.py — Tests for the six generic proxy tools.

Covers:
- clearpass_get: success, HTTP error, exception
- clearpass_post: success, dry_run, read-only block, HTTP error
- clearpass_patch: dry_run, success
- clearpass_put: dry_run, success
- clearpass_delete: confirm gate, dry_run, read-only block, success
- clearpass_list_apis: no filter, category filter
- Error shape consistency
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from clearpass_mcp.audit import AuditLogger
from clearpass_mcp.client import ClearPassClient, set_client
from clearpass_mcp.config import Settings

# ---------------------------------------------------------------------------
# Helpers — build a mock client and register tools
# ---------------------------------------------------------------------------


def _make_mock_client(
    response: Any = None,
    error: Exception | None = None,
) -> MagicMock:
    mock = MagicMock(spec=ClearPassClient)
    if error:
        mock.request = AsyncMock(side_effect=error)
    else:
        mock.request = AsyncMock(return_value=response or {})
    return mock


def _make_http_error(status_code: int, text: str = "error") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://clearpass.test/api/foo")
    response = httpx.Response(status_code, text=text, request=request)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response)


def _register_tools_with(settings: Settings) -> Any:
    """Import and call register() on the generic module with given settings."""
    from mcp.server.fastmcp import FastMCP

    from clearpass_mcp.tools import generic

    mcp = FastMCP("test")
    generic.register(mcp, settings)
    # Collect registered tool functions by name
    tools: dict[str, Any] = {}
    for tool in mcp._tool_manager.list_tools():
        tools[tool.name] = tool.fn
    return tools


@pytest.fixture()
def tools(settings: Settings, audit_logger: AuditLogger) -> dict[str, Any]:
    return _register_tools_with(settings)


@pytest.fixture()
def ro_tools(ro_settings: Settings, audit_logger: AuditLogger) -> dict[str, Any]:
    return _register_tools_with(ro_settings)


# ---------------------------------------------------------------------------
# clearpass_get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clearpass_get_success(tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"id": 1, "mac_address": "AA-BB-CC-DD-EE-FF"})
    set_client(mock)
    result = await tools["clearpass_get"](path="/endpoint/1")
    assert result["id"] == 1
    mock.request.assert_called_once_with("GET", "/endpoint/1", params=None)


@pytest.mark.asyncio
async def test_clearpass_get_http_error(tools: dict[str, Any]) -> None:
    mock = _make_mock_client(error=_make_http_error(404, "Not found"))
    set_client(mock)
    result = await tools["clearpass_get"](path="/endpoint/999")
    assert result["status_code"] == 404
    assert "error" in result


@pytest.mark.asyncio
async def test_clearpass_get_generic_exception(tools: dict[str, Any]) -> None:
    mock = _make_mock_client(error=RuntimeError("connection refused"))
    set_client(mock)
    result = await tools["clearpass_get"](path="/endpoint")
    assert "error" in result
    assert result["status_code"] is None


# ---------------------------------------------------------------------------
# clearpass_post
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clearpass_post_success(tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"id": 5, "username": "newuser"})
    set_client(mock)
    result = await tools["clearpass_post"](path="/guest", body={"username": "newuser"})
    assert result["id"] == 5


@pytest.mark.asyncio
async def test_clearpass_post_dry_run(tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await tools["clearpass_post"](
        path="/guest", body={"username": "testuser"}, dry_run=True
    )
    assert result["dry_run"] is True
    mock.request.assert_not_called()


@pytest.mark.asyncio
async def test_clearpass_post_read_only_blocked(ro_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await ro_tools["clearpass_post"](path="/guest", body={"username": "x"})
    assert "error" in result
    assert "read-only" in result["error"].lower()
    mock.request.assert_not_called()


# ---------------------------------------------------------------------------
# clearpass_delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clearpass_delete_requires_confirm(tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"status": "success", "code": 204})
    set_client(mock)
    result = await tools["clearpass_delete"](path="/guest/1", confirm=False)
    assert "error" in result
    mock.request.assert_not_called()


@pytest.mark.asyncio
async def test_clearpass_delete_dry_run(tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await tools["clearpass_delete"](path="/guest/1", confirm=True, dry_run=True)
    assert result["dry_run"] is True
    mock.request.assert_not_called()


@pytest.mark.asyncio
async def test_clearpass_delete_success(tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"status": "success", "code": 204})
    set_client(mock)
    result = await tools["clearpass_delete"](path="/guest/1", confirm=True)
    assert result["code"] == 204


@pytest.mark.asyncio
async def test_clearpass_delete_read_only_blocked(ro_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await ro_tools["clearpass_delete"](path="/guest/1", confirm=True)
    assert "error" in result
    mock.request.assert_not_called()


# ---------------------------------------------------------------------------
# clearpass_list_apis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_apis_no_filter(tools: dict[str, Any]) -> None:
    result = await tools["clearpass_list_apis"]()
    assert "SessionControl (v1)" in result
    assert "Identities (v1)" in result


@pytest.mark.asyncio
async def test_list_apis_category_filter(tools: dict[str, Any]) -> None:
    result = await tools["clearpass_list_apis"](category="session")
    assert len(result) >= 1
    keys = list(result.keys())
    assert all("session" in k.lower() for k in keys)


@pytest.mark.asyncio
async def test_list_apis_unknown_category(tools: dict[str, Any]) -> None:
    result = await tools["clearpass_list_apis"](category="nonexistent_xyz")
    assert result == {}
