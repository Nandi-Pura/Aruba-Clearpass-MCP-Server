"""
conftest.py — Shared pytest fixtures for the ClearPass MCP Server test suite.

All fixtures use ``respx`` to mock ``httpx`` transport — no real ClearPass
instance is needed. Tests run fully offline.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from clearpass_mcp.audit import AuditLogger, set_audit_logger
from clearpass_mcp.client import ClearPassClient, set_client
from clearpass_mcp.config import Settings

# ---------------------------------------------------------------------------
# Settings fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings() -> Settings:
    """
    Return a :class:`~clearpass_mcp.config.Settings` instance with safe
    test values that bypass the placeholder-detection validator.
    """
    return Settings.model_construct(
        CLEARPASS_HOST="https://clearpass.test",
        CLEARPASS_CLIENT_ID="test-client-id",
        CLEARPASS_CLIENT_SECRET="test-client-secret",
        CLEARPASS_VERIFY_SSL=False,
        CLEARPASS_READ_ONLY=False,
        CLEARPASS_LOG_LEVEL="DEBUG",
        CLEARPASS_AUDIT_LOG_PATH=None,
        CLEARPASS_MAX_PAGES=20,
    )


@pytest.fixture()
def ro_settings(settings: Settings) -> Settings:
    """Settings with ``CLEARPASS_READ_ONLY=True``."""
    return Settings.model_construct(
        **{**settings.model_dump(), "CLEARPASS_READ_ONLY": True}
    )


# ---------------------------------------------------------------------------
# Mock HTTP transport (respx)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_router() -> respx.MockRouter:
    """
    Activate a ``respx`` mock router for the duration of each test.

    All HTTP requests made by ``httpx`` are intercepted — any request that
    does not match a registered route raises ``respx.errors.NoMatchFound``.
    """
    with respx.mock(assert_all_called=False) as router:
        yield router


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

TOKEN_RESPONSE = {
    "access_token": "test-bearer-token-abc123",
    "token_type": "Bearer",
    "expires_in": 3600,
}

REFRESHED_TOKEN_RESPONSE = {
    "access_token": "refreshed-bearer-token-xyz789",
    "token_type": "Bearer",
    "expires_in": 3600,
}


def register_token_route(router: respx.MockRouter, response: dict | None = None) -> None:
    """Register a ``POST /api/oauth`` route on *router*."""
    router.post("https://clearpass.test/api/oauth").mock(
        return_value=httpx.Response(200, json=response or TOKEN_RESPONSE)
    )


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def client(settings: Settings, mock_router: respx.MockRouter) -> ClearPassClient:  # type: ignore[misc]
    """
    Provide a :class:`~clearpass_mcp.client.ClearPassClient` backed by
    ``respx`` mocks and register it as the module-level singleton.
    """
    register_token_route(mock_router)
    c = ClearPassClient(settings)
    set_client(c)
    yield c
    await c.close()
    set_client(None)


# ---------------------------------------------------------------------------
# Audit logger fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def audit_logger() -> AuditLogger:
    """Provide a no-op :class:`~clearpass_mcp.audit.AuditLogger` (no file output)."""
    audit = AuditLogger(log_path=None)
    set_audit_logger(audit)
    yield audit
    set_audit_logger(None)
