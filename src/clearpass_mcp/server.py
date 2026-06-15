"""FastMCP server wiring for the ClearPass MCP Server.

This module initializes the FastMCP application, manages the lifecycle of the
shared ClearPassClient and AuditLogger, and registers all MCP resources,
prompts, and tools.

Transports:
    stdio: Default transport compatible with Claude Desktop, Claude Code,
        and any MCP-conformant client.
    sse: Selectable via `--transport sse --port <port>` for remote or
        multi-user deployments.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from clearpass_mcp.audit import AuditLogger, set_audit_logger
from clearpass_mcp.catalog import CLEARPASS_APIS
from clearpass_mcp.client import ClearPassClient, set_client
from clearpass_mcp.config import Settings
from clearpass_mcp.tools import admin, endpoints, generic, guests, sessions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """FastMCP lifespan context manager.

    Handles startup and shutdown events for the MCP server, including
    configuration loading, client initialization, and resource cleanup.

    Args:
        server (FastMCP): The FastMCP server instance.

    Yields:
        None
    """
    try:
        settings = Settings()
    except Exception as exc:
        logger.error(f"Failed to load configuration: {exc}")
        raise

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.CLEARPASS_LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    logger.info(
        "Starting ClearPass MCP Server — host=%s read_only=%s",
        settings.CLEARPASS_HOST,
        settings.CLEARPASS_READ_ONLY,
    )

    try:
        client = ClearPassClient(settings)
        audit = AuditLogger(settings.CLEARPASS_AUDIT_LOG_PATH)

        set_client(client)
        set_audit_logger(audit)
    except Exception as exc:
        logger.error(f"Failed to initialize client or audit logger: {exc}")
        raise

    try:
        yield
    finally:
        logger.info("Shutting down ClearPass MCP Server.")
        try:
            await client.close()
            audit.close()
        except Exception as exc:
            logger.error(f"Error during shutdown: {exc}")
        finally:
            set_client(None)
            set_audit_logger(None)


# ---------------------------------------------------------------------------
# FastMCP application
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="clearpass-mcp",
    instructions=(
        "You are connected to an Aruba ClearPass Policy Manager (CPPM) via its REST API. "
        "Use the typed tools for common workflows (endpoint lookup, session management, "
        "guest provisioning, health checks). Use the generic proxy tools (clearpass_get, "
        "clearpass_post, etc.) for any endpoint not covered by a typed tool. "
        "Always use dry_run=True first for any write operation, then confirm with the user "
        "before proceeding with the real request. "
        "Read the clearpass://api-catalog resource for a full list of available endpoints."
    ),
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# MCP Resource: API Catalog
# ---------------------------------------------------------------------------


@mcp.resource("clearpass://api-catalog")
def api_catalog() -> str:
    """The complete ClearPass REST API endpoint catalog, grouped by category.

    Load this resource to understand what endpoints are available before
    constructing tool calls. The catalog covers all major CPPM v1 REST API
    categories: Identities, Policy Elements, Session Control, Onboard/CA,
    OnGuard, Guests, System & Logs, and more.

    Returns:
        str: JSON-formatted string containing the API catalog.
    """
    return json.dumps(CLEARPASS_APIS, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# MCP Prompts: Guided Workflows
# ---------------------------------------------------------------------------


@mcp.prompt()
def investigate_device_by_mac(mac_address: str) -> list[dict[str, Any]]:
    """Guided workflow: investigate a device by its MAC address.

    Combines endpoint lookup, session status, and Insight data into a
    comprehensive device investigation.

    Args:
        mac_address (str): The MAC address of the device to investigate.

    Returns:
        list[dict[str, Any]]: A list containing the prompt messages for the AI client.
    """
    return [
        {
            "role": "user",
            "content": (
                f"Please investigate the device with MAC address {mac_address} in ClearPass.\n\n"
                "1. Use find_endpoint_by_mac to get its registration status and attributes.\n"
                "2. Use list_active_sessions with a MAC filter "
                "to check if it has an active session.\n"
                "3. Use get_endpoint_insight to retrieve historical Insight data.\n"
                "4. Summarise the findings: Is the device known? Is it currently connected? "
                "What role/VLAN is it on? Any anomalies?"
            ),
        }
    ]


@mcp.prompt()
def onboard_guest_account(
    visitor_name: str,
    contact_email: str,
    valid_hours: int = 8,
) -> list[dict[str, Any]]:
    """Guided workflow: onboard a new temporary guest account.

    Walks through role selection, account creation, and receipt delivery.

    Args:
        visitor_name (str): Name of the visitor.
        contact_email (str): Email address of the visitor.
        valid_hours (int, optional): Number of hours the account is valid. Defaults to 8.

    Returns:
        list[dict[str, Any]]: A list containing the prompt messages for the AI client.
    """
    return [
        {
            "role": "user",
            "content": (
                f"I need to create a guest account for {visitor_name} ({contact_email}), "
                f"valid for {valid_hours} hours.\n\n"
                "1. Use clearpass_get on /role to list available guest roles.\n"
                "2. Ask me which role to assign.\n"
                "3. Use create_guest_account with dry_run=True first so I can review the payload.\n"
                "4. If I confirm, create the account for real.\n"
                "5. If an email address was provided, offer to send the receipt via "
                "clearpass_post on /guest/{id}/sendreceipt/smtp."
            ),
        }
    ]


@mcp.prompt()
def quarantine_endpoint(mac_address: str) -> list[dict[str, Any]]:
    """Guided workflow: quarantine or disconnect a suspicious endpoint.

    Investigates the device, then offers a targeted disconnect or CoA.

    Args:
        mac_address (str): The MAC address of the endpoint to quarantine.

    Returns:
        list[dict[str, Any]]: A list containing the prompt messages for the AI client.
    """
    return [
        {
            "role": "user",
            "content": (
                f"I need to quarantine the potentially suspicious "
                f"device with MAC {mac_address}.\n\n"
                "1. Use find_endpoint_by_mac to confirm the device is known.\n"
                "2. Use list_active_sessions with a MAC filter to find its session ID.\n"
                "3. If a session is found, use disconnect_session with dry_run=True first.\n"
                "4. Wait for my explicit confirmation before executing the real disconnect.\n"
                "5. After disconnect, optionally update the endpoint status via clearpass_patch "
                "to mark it as 'Quarantine' or update its attributes for policy enforcement."
            ),
        }
    ]


@mcp.prompt()
def daily_cluster_health_check() -> list[dict[str, Any]]:
    """Guided workflow: run a daily ClearPass cluster health check.

    Aggregates server health, license usage, and recent error events.

    Returns:
        list[dict[str, Any]]: A list containing the prompt messages for the AI client.
    """
    return [
        {
            "role": "user",
            "content": (
                "Please run a daily health check on the ClearPass cluster.\n\n"
                "1. Use get_server_health to get versions, cluster node status, and FIPS mode.\n"
                "2. Use clearpass_get on /application-license/summary for license consumption.\n"
                "3. Use search_audit_records for the past 24 hours "
                "to highlight any admin changes.\n"
                "4. Use clearpass_get on /system-event to check "
                "for recent system warnings or errors.\n"
                "5. Provide a concise health summary with any items requiring attention."
            ),
        }
    ]


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class _LazySettings:
    """Proxy that reads settings from the live ClearPassClient singleton at call time.

    This avoids calling `Settings()` at module import time (which would fail if
    environment variables are not yet set) while still passing a `settings`-like
    object to tool `register()` functions so they can enforce guards such as
    `CLEARPASS_READ_ONLY` on every invocation.
    """

    @property
    def CLEARPASS_READ_ONLY(self) -> bool:  # noqa: N802
        """Check if the server is in read-only mode.

        Returns:
            bool: True if read-only mode is enabled, False otherwise.
        """
        try:
            from clearpass_mcp.client import get_client
            return get_client()._settings.CLEARPASS_READ_ONLY
        except RuntimeError as e:
            logger.error(f"Error accessing settings: {e}. Defaulting to allow writes.")
            return False  # default: allow writes until client is initialised
        except Exception as e:
            logger.error(f"Unexpected error accessing settings: {e}. Defaulting to allow writes.")
            return False


def _register_tools() -> None:
    """Register all tool modules on the FastMCP instance at import time."""
    _settings = _LazySettings()
    generic.register(mcp, _settings)  # type: ignore[arg-type]
    endpoints.register(mcp, _settings)  # type: ignore[arg-type]
    sessions.register(mcp, _settings)  # type: ignore[arg-type]
    guests.register(mcp, _settings)  # type: ignore[arg-type]
    admin.register(mcp, _settings)  # type: ignore[arg-type]


_register_tools()
