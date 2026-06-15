"""
tools/generic.py — Hardened generic HTTP proxy tools.

These six tools give AI assistants unrestricted access to any ClearPass API
endpoint and serve as an "escape hatch" for endpoints that do not have a
dedicated typed wrapper.  They are intentionally kept broad, but hardened
compared to the original implementation:

- ``dry_run`` parameter on every write tool (POST/PATCH/PUT/DELETE).
- ``CLEARPASS_READ_ONLY`` mode blocks all write operations.
- Consistent JSON error shape on every failure path.
- Audit log entries for all successful write operations.
- Single persistent HTTP client (no per-request client creation).
- ``confirm=True`` required for DELETE.

Tools
-----
clearpass_get       — GET any endpoint
clearpass_post      — POST to any endpoint (create / action)
clearpass_patch     — PATCH any endpoint (partial update)
clearpass_put       — PUT any endpoint (full replace)
clearpass_delete    — DELETE any endpoint (requires confirm=True)
clearpass_list_apis — Browse the static endpoint catalog
"""
from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from clearpass_mcp.audit import get_audit_logger
from clearpass_mcp.catalog import CLEARPASS_APIS
from clearpass_mcp.client import format_error, get_client
from clearpass_mcp.config import Settings


def _read_only_error(path: str) -> dict[str, Any]:
    return format_error(
        "Read-only mode is enabled. Write operations are not permitted.",
        status_code=None,
        detail="Set CLEARPASS_READ_ONLY=false to allow writes.",
        path=path,
    )


def register(mcp: FastMCP, settings: Settings) -> None:
    """Register all generic proxy tools on *mcp*."""

    # ------------------------------------------------------------------
    # READ tools
    # ------------------------------------------------------------------

    @mcp.tool()
    async def clearpass_get(
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Send a GET request to **any** ClearPass API endpoint.

        Use ``clearpass_list_apis`` first to discover available endpoints and
        their supported query parameters.

        Args:
            path: API path relative to ``/api``.
                Examples: ``/endpoint``, ``/guest``, ``/session``,
                ``/config/service``, ``/audit-record``, ``/server/version``
            params: Optional query parameters as a dict.
                Examples: ``{"filter": '{"status":"Known"}', "limit": 25}``

        Returns:
            Parsed JSON response from ClearPass.

        Example natural-language prompts:
            - "List all endpoints with status Known"
            - "Show me the 10 most recent audit records"
            - "Get the details of guest account username john.doe"
        """
        try:
            return await get_client().request("GET", path, params=params)
        except httpx.HTTPStatusError as e:
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code,
                detail=e.response.text,
                path=path,
            )
        except Exception as e:
            return format_error(str(e), path=path)

    @mcp.tool()
    async def clearpass_list_apis(
        category: str | None = None,
    ) -> dict[str, list[str]]:
        """
        List all known ClearPass API endpoints, grouped by category.

        Useful for discovering which endpoints are available before making a
        ``clearpass_get`` / ``clearpass_post`` call.

        Args:
            category: Optional filter string.  Case-insensitive substring match
                against category names.
                Examples: ``"SessionControl"``, ``"PolicyElements"``,
                ``"GuestActions"``, ``"Identities"``

        Returns:
            Dict mapping category names to lists of endpoint strings
            (``"METHOD  /path  - Description"``).

        Example natural-language prompts:
            - "What session-related endpoints does ClearPass expose?"
            - "Show me all available guest management API endpoints"
        """
        if category:
            low = category.lower()
            return {k: v for k, v in CLEARPASS_APIS.items() if low in k.lower()}
        return CLEARPASS_APIS

    # ------------------------------------------------------------------
    # WRITE tools
    # ------------------------------------------------------------------

    @mcp.tool()
    async def clearpass_post(
        path: str,
        body: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Send a POST request to **any** ClearPass API endpoint.

        Use for creating resources or triggering actions (e.g. disconnect a
        session, initiate a CoA, sync the cluster database).

        Args:
            path: API path relative to ``/api``.
                Examples: ``/guest``, ``/local-user``,
                ``/session/{id}/disconnect``, ``/session-action/coa``,
                ``/cluster/db-sync``
            body: Request body as a JSON object.
            dry_run: When ``True``, log the intended request and return a
                preview without sending it to ClearPass. Default: ``False``.

        Returns:
            Parsed JSON response, or a dry-run preview dict.

        Example natural-language prompts:
            - "Create a guest account for visitor@example.com"
            - "Trigger a CoA for all sessions from VLAN 10"
            - "Sync the ClearPass subscriber database with the publisher"
        """
        if settings.CLEARPASS_READ_ONLY:
            return _read_only_error(path)

        audit = get_audit_logger()

        if dry_run:
            audit.log_write(
                tool="clearpass_post",
                path=path,
                method="POST",
                body=body,
                dry_run=True,
                outcome="dry_run",
                status_code=None,
            )
            return {
                "dry_run": True,
                "method": "POST",
                "path": path,
                "body": body,
                "message": "Dry run — no request was sent to ClearPass.",
            }

        try:
            result = await get_client().request("POST", path, body=body)
            audit.log_write(
                tool="clearpass_post",
                path=path,
                method="POST",
                body=body,
                dry_run=False,
                outcome="success",
                status_code=result.get("code", 200),
            )
            return result
        except httpx.HTTPStatusError as e:
            audit.log_write(
                tool="clearpass_post",
                path=path,
                method="POST",
                body=body,
                dry_run=False,
                outcome="error",
                status_code=e.response.status_code,
            )
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code,
                detail=e.response.text,
                path=path,
            )
        except Exception as e:
            audit.log_write(
                tool="clearpass_post", path=path, method="POST", body=body,
                dry_run=False, outcome="error", status_code=None,
            )
            return format_error(str(e), path=path)

    @mcp.tool()
    async def clearpass_patch(
        path: str,
        body: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Send a PATCH request to **any** ClearPass API endpoint (partial update).

        Args:
            path: API path relative to ``/api``.
                Examples: ``/endpoint/mac-address/AA-BB-CC-DD-EE-FF``,
                ``/config/service/{id}/enable``, ``/onboard/device/{id}``
            body: Fields to update as a JSON object.
            dry_run: When ``True``, preview the request without executing it.

        Returns:
            Updated resource dict, or dry-run preview.

        Example natural-language prompts:
            - "Update the description of endpoint AA-BB-CC-DD-EE-FF to 'Security Camera'"
            - "Enable the 802.1X wired service"
        """
        if settings.CLEARPASS_READ_ONLY:
            return _read_only_error(path)

        audit = get_audit_logger()

        if dry_run:
            audit.log_write(
                tool="clearpass_patch", path=path, method="PATCH", body=body,
                dry_run=True, outcome="dry_run", status_code=None,
            )
            return {
                "dry_run": True, "method": "PATCH", "path": path, "body": body,
                "message": "Dry run — no request was sent to ClearPass.",
            }

        try:
            result = await get_client().request("PATCH", path, body=body)
            audit.log_write(
                tool="clearpass_patch", path=path, method="PATCH", body=body,
                dry_run=False, outcome="success", status_code=result.get("code", 200),
            )
            return result
        except httpx.HTTPStatusError as e:
            audit.log_write(
                tool="clearpass_patch", path=path, method="PATCH", body=body,
                dry_run=False, outcome="error", status_code=e.response.status_code,
            )
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code, detail=e.response.text, path=path,
            )
        except Exception as e:
            audit.log_write(
                tool="clearpass_patch", path=path, method="PATCH", body=body,
                dry_run=False, outcome="error", status_code=None,
            )
            return format_error(str(e), path=path)

    @mcp.tool()
    async def clearpass_put(
        path: str,
        body: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Send a PUT request to **any** ClearPass API endpoint (full replacement).

        Args:
            path: API path relative to ``/api``.
                Examples: ``/auth-method/{id}``, ``/network-device/{id}``
            body: Full replacement resource as a JSON object.
            dry_run: When ``True``, preview the request without executing it.

        Returns:
            Replaced resource dict, or dry-run preview.

        Example natural-language prompts:
            - "Replace the full configuration of network device 42"
        """
        if settings.CLEARPASS_READ_ONLY:
            return _read_only_error(path)

        audit = get_audit_logger()

        if dry_run:
            audit.log_write(
                tool="clearpass_put", path=path, method="PUT", body=body,
                dry_run=True, outcome="dry_run", status_code=None,
            )
            return {
                "dry_run": True, "method": "PUT", "path": path, "body": body,
                "message": "Dry run — no request was sent to ClearPass.",
            }

        try:
            result = await get_client().request("PUT", path, body=body)
            audit.log_write(
                tool="clearpass_put", path=path, method="PUT", body=body,
                dry_run=False, outcome="success", status_code=result.get("code", 200),
            )
            return result
        except httpx.HTTPStatusError as e:
            audit.log_write(
                tool="clearpass_put", path=path, method="PUT", body=body,
                dry_run=False, outcome="error", status_code=e.response.status_code,
            )
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code, detail=e.response.text, path=path,
            )
        except Exception as e:
            audit.log_write(
                tool="clearpass_put", path=path, method="PUT", body=body,
                dry_run=False, outcome="error", status_code=None,
            )
            return format_error(str(e), path=path)

    @mcp.tool()
    async def clearpass_delete(
        path: str,
        confirm: bool,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Send a DELETE request to **any** ClearPass API endpoint.

        ⚠️ **Destructive operation** — requires explicit ``confirm=True``.

        Args:
            path: API path relative to ``/api``.
                Examples: ``/guest/123``,
                ``/endpoint/mac-address/AA-BB-CC-DD-EE-FF``,
                ``/network-device/{id}``
            confirm: Must be ``True`` to execute the deletion.  This is a
                mandatory safety gate — set it only after confirming the
                correct resource ID with the user.
            dry_run: When ``True``, preview the request without executing it
                (even if ``confirm=True``).

        Returns:
            ``{"status": "success", "code": 204}`` on success, or an error dict.

        Example natural-language prompts:
            - "Delete guest account with ID 42 — I confirm"
            - "Remove the stale endpoint AA-BB-CC-DD-EE-FF"
        """
        if not confirm:
            return format_error(
                "Deletion requires confirm=True. "
                "Verify the resource ID before setting confirm=True.",
                path=path,
            )

        if settings.CLEARPASS_READ_ONLY:
            return _read_only_error(path)

        audit = get_audit_logger()

        if dry_run:
            audit.log_write(
                tool="clearpass_delete", path=path, method="DELETE", body=None,
                dry_run=True, outcome="dry_run", status_code=None,
            )
            return {
                "dry_run": True, "method": "DELETE", "path": path,
                "message": "Dry run — no request was sent to ClearPass.",
            }

        try:
            result = await get_client().request("DELETE", path)
            audit.log_write(
                tool="clearpass_delete", path=path, method="DELETE", body=None,
                dry_run=False, outcome="success", status_code=result.get("code", 204),
            )
            return result
        except httpx.HTTPStatusError as e:
            audit.log_write(
                tool="clearpass_delete", path=path, method="DELETE", body=None,
                dry_run=False, outcome="error", status_code=e.response.status_code,
            )
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code, detail=e.response.text, path=path,
            )
        except Exception as e:
            audit.log_write(
                tool="clearpass_delete", path=path, method="DELETE", body=None,
                dry_run=False, outcome="error", status_code=None,
            )
            return format_error(str(e), path=path)

    # Expose catalog separately so tests can import it without registering
    clearpass_list_apis.__doc__ = clearpass_list_apis.__doc__  # noqa: B018

    return  # explicit for clarity
