"""
tools/sessions.py — Typed tools for active session management.

Tools
-----
list_active_sessions  — Paginated list of active RADIUS/802.1X sessions
disconnect_session    — Disconnect a single active session (requires confirm)
bulk_coa              — Send a Change-of-Authorization to a filtered set of sessions
"""
from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from clearpass_mcp.audit import get_audit_logger
from clearpass_mcp.client import format_error, get_client
from clearpass_mcp.config import Settings


def register(mcp: FastMCP, settings: Settings) -> None:
    """Register session management tools on *mcp*."""

    @mcp.tool()
    async def list_active_sessions(
        filter: dict[str, Any] | None = None,
        max_pages: int = 5,
    ) -> dict[str, Any]:
        """
        List currently active RADIUS / 802.1X sessions on ClearPass.

        Uses automatic pagination to aggregate results across multiple pages,
        stopping at ``max_pages`` to prevent runaway queries on large deployments.

        Args:
            filter: Optional ClearPass filter dict to narrow results.
                Examples::

                    {"mac_address": "AA-BB-CC-DD-EE-FF"}
                    {"acctstatus": "Start", "nasporttype": "15"}
                    {"calling_station_id": "AA-BB-CC-DD-EE-FF"}

            max_pages: Maximum pages to retrieve (each page is up to 25 sessions).
                Default: ``5`` (up to ~125 sessions).

        Returns:
            ``{"items": [...], "total": int, "truncated": bool}``

        Example natural-language prompts:
            - "Show me all active sessions right now"
            - "List sessions for MAC AA:BB:CC:DD:EE:FF"
            - "Find all active wireless sessions from SSID 'CorpWiFi'"
        """
        params: dict[str, Any] = {"calculate_count": True}
        if filter:
            import json
            params["filter"] = json.dumps(filter)

        items: list[Any] = []
        total = 0
        truncated = False

        try:
            async for page in get_client().paginate("/session", params=params, max_pages=max_pages):
                embedded = page.get("_embedded", {})
                page_items = embedded.get("items", [])
                items.extend(page_items)
                if not total:
                    total = page.get("total", 0)
                # If there's a next link but we hit max_pages, mark as truncated
                if "_links" in page and "next" in page.get("_links", {}):
                    truncated = True
        except httpx.HTTPStatusError as e:
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code,
                detail=e.response.text,
                path="/session",
            )
        except Exception as e:
            return format_error(str(e), path="/session")

        return {"items": items, "total": total, "truncated": truncated, "retrieved": len(items)}

    @mcp.tool()
    async def disconnect_session(
        session_id: str,
        confirm: bool,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Disconnect a single active RADIUS session by its session ID.

        ⚠️ **Disruptive operation** — the device will lose network access until
        it re-authenticates.  Requires explicit ``confirm=True``.

        Args:
            session_id: ClearPass active session ID (the ``id`` field from
                ``list_active_sessions`` results).
            confirm: Must be ``True`` to execute the disconnect.  Confirm with
                the user before setting this to ``True``.
            dry_run: When ``True``, preview the action without executing it.
                Default: ``False``.

        Returns:
            Success confirmation or error dict.

        Example natural-language prompts:
            - "Disconnect session abc123 — I confirm"
            - "Force a re-auth for session ID xyz789, confirm=true"
        """
        if not confirm:
            return format_error(
                "Session disconnect requires confirm=True. "
                "Confirm the session ID with the user first.",
                path=f"/session/{session_id}/disconnect",
            )

        if settings.CLEARPASS_READ_ONLY:
            return format_error(
                "Read-only mode is enabled. Session disconnect is not permitted.",
                path=f"/session/{session_id}/disconnect",
            )

        path = f"/session/{session_id}/disconnect"
        audit = get_audit_logger()

        if dry_run:
            audit.log_write(
                tool="disconnect_session", path=path, method="POST",
                body={"session_id": session_id}, dry_run=True,
                outcome="dry_run", status_code=None,
            )
            return {
                "dry_run": True,
                "session_id": session_id,
                "message": "Dry run — session would be disconnected. No request was sent.",
            }

        try:
            result = await get_client().request("POST", path, body={})
            audit.log_write(
                tool="disconnect_session", path=path, method="POST",
                body={"session_id": session_id}, dry_run=False,
                outcome="success", status_code=result.get("code", 200),
            )
            return result
        except httpx.HTTPStatusError as e:
            audit.log_write(
                tool="disconnect_session", path=path, method="POST",
                body={"session_id": session_id}, dry_run=False,
                outcome="error", status_code=e.response.status_code,
            )
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code,
                detail=e.response.text,
                path=path,
            )
        except Exception as e:
            audit.log_write(
                tool="disconnect_session", path=path, method="POST",
                body={"session_id": session_id}, dry_run=False,
                outcome="error", status_code=None,
            )
            return format_error(str(e), path=path)

    @mcp.tool()
    async def bulk_coa(
        filter: dict[str, Any],
        confirm: bool,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Send a bulk Change-of-Authorization (CoA) to a set of active sessions.

        CoA forces affected devices to re-authenticate, which causes ClearPass
        to re-evaluate their network access policy.  Commonly used to apply
        updated policy to a group of devices without a full disconnect.

        ⚠️ **High-impact operation** — may affect many devices simultaneously.
        Requires explicit ``confirm=True``.

        Args:
            filter: ClearPass filter dict that identifies which sessions to target.
                Examples::

                    {"nasporttype": "15"}           # all wireless sessions
                    {"mac_address": "AA-BB-CC-DD-EE-FF"}
                    {"role_id": 7, "acctstatus": "Start"}

            confirm: Must be ``True`` to execute the CoA.
            dry_run: When ``True``, preview which sessions would be targeted
                without sending the CoA.  Default: ``False``.

        Returns:
            Bulk action response with an ``action_id`` you can poll with
            ``clearpass_get`` on ``/session-action/{action_id}``.

        Example natural-language prompts:
            - "Send a CoA to all wireless sessions — I confirm"
            - "Reauthorize sessions for VLAN 100, dry_run first"
        """
        if not confirm:
            return format_error(
                "Bulk CoA requires confirm=True. Review the filter carefully before confirming.",
                path="/session-action/coa",
            )

        if settings.CLEARPASS_READ_ONLY:
            return format_error(
                "Read-only mode is enabled. Bulk CoA is not permitted.",
                path="/session-action/coa",
            )

        path = "/session-action/coa"
        audit = get_audit_logger()

        if dry_run:
            audit.log_write(
                tool="bulk_coa", path=path, method="POST", body={"filter": filter},
                dry_run=True, outcome="dry_run", status_code=None,
            )
            return {
                "dry_run": True,
                "filter": filter,
                "message": "Dry run — CoA would be sent to sessions matching the filter. No request sent.",
            }

        body = {"filter": filter}
        try:
            result = await get_client().request("POST", path, body=body)
            audit.log_write(
                tool="bulk_coa", path=path, method="POST", body=body,
                dry_run=False, outcome="success", status_code=result.get("code", 200),
            )
            return result
        except httpx.HTTPStatusError as e:
            audit.log_write(
                tool="bulk_coa", path=path, method="POST", body=body,
                dry_run=False, outcome="error", status_code=e.response.status_code,
            )
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code,
                detail=e.response.text,
                path=path,
            )
        except Exception as e:
            audit.log_write(
                tool="bulk_coa", path=path, method="POST", body=body,
                dry_run=False, outcome="error", status_code=None,
            )
            return format_error(str(e), path=path)
