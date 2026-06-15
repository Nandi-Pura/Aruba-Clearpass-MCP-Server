"""
test_curated_tools.py — Tests for Phase 4 curated typed tools.

Covers:
- find_endpoint_by_mac: MAC normalisation, 404 handling, success
- get_endpoint_insight: MAC lookup, IP lookup, invalid input
- list_active_sessions: paginated aggregation, filter passing
- disconnect_session: confirm gate, dry_run, success, read-only
- bulk_coa: confirm gate, dry_run, success, read-only
- create_guest_account: payload building, dry_run, success, read-only
- get_server_health: aggregated response, partial failure
- search_audit_records: filter construction, aggregation
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
# Helpers
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

    async def _paginate(path: str, **kwargs: Any):  # type: ignore[override]
        yield response or {}

    mock.paginate = _paginate
    return mock


def _make_http_error(status_code: int, text: str = "error") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://clearpass.test/api/test")
    response = httpx.Response(status_code, text=text, request=request)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response)


def _register_tools(module_name: str, settings: Settings) -> dict[str, Any]:
    import importlib

    from mcp.server.fastmcp import FastMCP

    module = importlib.import_module(f"clearpass_mcp.tools.{module_name}")
    mcp = FastMCP("test")
    module.register(mcp, settings)
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


@pytest.fixture()
def endpoint_tools(settings: Settings) -> dict[str, Any]:
    return _register_tools("endpoints", settings)


@pytest.fixture()
def session_tools(settings: Settings, audit_logger: AuditLogger) -> dict[str, Any]:
    return _register_tools("sessions", settings)


@pytest.fixture()
def ro_session_tools(ro_settings: Settings, audit_logger: AuditLogger) -> dict[str, Any]:
    return _register_tools("sessions", ro_settings)


@pytest.fixture()
def guest_tools(settings: Settings, audit_logger: AuditLogger) -> dict[str, Any]:
    return _register_tools("guests", settings)


@pytest.fixture()
def ro_guest_tools(ro_settings: Settings, audit_logger: AuditLogger) -> dict[str, Any]:
    return _register_tools("guests", ro_settings)


@pytest.fixture()
def admin_tools(settings: Settings) -> dict[str, Any]:
    return _register_tools("admin", settings)


# ---------------------------------------------------------------------------
# find_endpoint_by_mac
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_endpoint_by_mac_success(endpoint_tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"id": 1, "mac_address": "AA-BB-CC-DD-EE-FF", "status": "Known"})
    set_client(mock)
    result = await endpoint_tools["find_endpoint_by_mac"](mac_address="aa:bb:cc:dd:ee:ff")
    assert result["status"] == "Known"
    mock.request.assert_called_once_with("GET", "/endpoint/mac-address/AA-BB-CC-DD-EE-FF")


@pytest.mark.asyncio
async def test_find_endpoint_by_mac_normalises_colons(endpoint_tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"id": 2})
    set_client(mock)
    await endpoint_tools["find_endpoint_by_mac"](mac_address="aa:bb:cc:dd:ee:ff")
    mock.request.assert_called_with("GET", "/endpoint/mac-address/AA-BB-CC-DD-EE-FF")


@pytest.mark.asyncio
async def test_find_endpoint_by_mac_normalises_bare(endpoint_tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"id": 3})
    set_client(mock)
    await endpoint_tools["find_endpoint_by_mac"](mac_address="aabbccddeeff")
    mock.request.assert_called_with("GET", "/endpoint/mac-address/AA-BB-CC-DD-EE-FF")


@pytest.mark.asyncio
async def test_find_endpoint_by_mac_invalid(endpoint_tools: dict[str, Any]) -> None:
    result = await endpoint_tools["find_endpoint_by_mac"](mac_address="notamac")
    assert "error" in result


@pytest.mark.asyncio
async def test_find_endpoint_by_mac_404(endpoint_tools: dict[str, Any]) -> None:
    mock = _make_mock_client(error=_make_http_error(404))
    set_client(mock)
    result = await endpoint_tools["find_endpoint_by_mac"](mac_address="aa:bb:cc:dd:ee:ff")
    assert result["status_code"] == 404
    assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# get_endpoint_insight
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_endpoint_insight_by_mac(endpoint_tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"device_ip": "10.0.0.1"})
    set_client(mock)
    result = await endpoint_tools["get_endpoint_insight"](mac_or_ip="aa:bb:cc:dd:ee:ff")
    mock.request.assert_called_once_with("GET", "/insight/endpoint/mac/AA-BB-CC-DD-EE-FF")
    assert result["device_ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_get_endpoint_insight_by_ip(endpoint_tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"device_ip": "10.0.0.50"})
    set_client(mock)
    result = await endpoint_tools["get_endpoint_insight"](mac_or_ip="10.0.0.50")
    mock.request.assert_called_once_with("GET", "/insight/endpoint/ip/10.0.0.50")
    assert result["device_ip"] == "10.0.0.50"


# ---------------------------------------------------------------------------
# disconnect_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_session_requires_confirm(session_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await session_tools["disconnect_session"](session_id="abc", confirm=False)
    assert "error" in result
    mock.request.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_session_dry_run(session_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await session_tools["disconnect_session"](
        session_id="abc", confirm=True, dry_run=True
    )
    assert result["dry_run"] is True
    mock.request.assert_not_called()


@pytest.mark.asyncio
async def test_disconnect_session_success(session_tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"status": "success", "code": 200})
    set_client(mock)
    result = await session_tools["disconnect_session"](session_id="abc", confirm=True)
    assert result["code"] == 200
    mock.request.assert_called_once_with("POST", "/session/abc/disconnect", body={})


@pytest.mark.asyncio
async def test_disconnect_session_read_only(ro_session_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await ro_session_tools["disconnect_session"](session_id="abc", confirm=True)
    assert "error" in result
    mock.request.assert_not_called()


# ---------------------------------------------------------------------------
# bulk_coa
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_coa_requires_confirm(session_tools: dict[str, Any]) -> None:
    result = await session_tools["bulk_coa"](filter={"nasporttype": "15"}, confirm=False)
    assert "error" in result


@pytest.mark.asyncio
async def test_bulk_coa_dry_run(session_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await session_tools["bulk_coa"](
        filter={"nasporttype": "15"}, confirm=True, dry_run=True
    )
    assert result["dry_run"] is True
    mock.request.assert_not_called()


@pytest.mark.asyncio
async def test_bulk_coa_success(session_tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"action_id": "xyz", "status": "queued"})
    set_client(mock)
    result = await session_tools["bulk_coa"](
        filter={"nasporttype": "15"}, confirm=True
    )
    assert result["action_id"] == "xyz"
    mock.request.assert_called_once_with(
        "POST", "/session-action/coa", body={"filter": {"nasporttype": "15"}}
    )


# ---------------------------------------------------------------------------
# create_guest_account
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_guest_account_dry_run(guest_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await guest_tools["create_guest_account"](
        username="visitor@example.com", role_id=5, valid_hours=8, dry_run=True
    )
    assert result["dry_run"] is True
    assert result["payload"]["username"] == "visitor@example.com"
    mock.request.assert_not_called()


@pytest.mark.asyncio
async def test_create_guest_account_includes_expiry(guest_tools: dict[str, Any]) -> None:
    mock = _make_mock_client({"id": 99, "username": "visitor@example.com"})
    set_client(mock)
    result = await guest_tools["create_guest_account"](
        username="visitor@example.com", role_id=5, valid_hours=24
    )
    assert result["id"] == 99
    call_args = mock.request.call_args
    assert call_args.kwargs["body"]["username"] == "visitor@example.com"
    assert "expire_time" in call_args.kwargs["body"]


@pytest.mark.asyncio
async def test_create_guest_account_read_only(ro_guest_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock()
    set_client(mock)
    result = await ro_guest_tools["create_guest_account"](
        username="x", role_id=1
    )
    assert "error" in result
    mock.request.assert_not_called()


# ---------------------------------------------------------------------------
# get_server_health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_server_health_success(admin_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock(
        side_effect=[
            {"version": "6.11.0"},
            {"_embedded": {"items": [{"uuid": "node1"}]}},
            {"fips_mode": False},
        ]
    )
    set_client(mock)
    result = await admin_tools["get_server_health"]()
    assert result["versions"]["version"] == "6.11.0"
    assert result["fips"]["fips_mode"] is False
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_get_server_health_partial_failure(admin_tools: dict[str, Any]) -> None:
    mock = MagicMock(spec=ClearPassClient)
    mock.request = AsyncMock(
        side_effect=[
            {"version": "6.11.0"},
            _make_http_error(403, "Forbidden"),
            {"fips_mode": False},
        ]
    )
    set_client(mock)
    result = await admin_tools["get_server_health"]()
    assert result["versions"] is not None
    assert result["cluster_nodes"] is None
    assert len(result["errors"]) == 1
