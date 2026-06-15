"""
tools/guests.py — Typed tool for guest account provisioning.

Tools
-----
create_guest_account — Create a time-limited ClearPass guest account
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from clearpass_mcp.audit import get_audit_logger
from clearpass_mcp.client import format_error, get_client
from clearpass_mcp.config import Settings


def register(mcp: FastMCP, settings: Settings) -> None:
    """Register guest account tools on *mcp*."""

    @mcp.tool()
    async def create_guest_account(
        username: str,
        role_id: int,
        valid_hours: int = 8,
        password: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Create a time-limited guest account in ClearPass.

        The account's ``expire_time`` is automatically calculated from
        ``valid_hours`` relative to the current UTC time.  If no ``password``
        is provided, ClearPass will generate one automatically (recommended).

        Args:
            username: Desired guest username (must be unique in ClearPass).
                Example: ``"john.doe@example.com"``
            role_id: ClearPass role ID to assign to the guest account.
                Use ``clearpass_get`` on ``/role`` to discover available roles.
            valid_hours: Account lifetime in hours from now.  Default: ``8``.
            password: Optional explicit password.  When omitted, ClearPass
                generates a random password — the response will include it.
            dry_run: When ``True``, preview the account payload without
                creating it in ClearPass.  Default: ``False``.

        Returns:
            Created guest account object (including generated password if
            applicable), or a dry-run preview dict.

        Example natural-language prompts:
            - "Create a guest account for visitor@example.com, valid for 8 hours"
            - "Provision a 24-hour guest account for Alice with role ID 5"
            - "Make a guest account for the conference room device, dry_run first"
        """
        if settings.CLEARPASS_READ_ONLY:
            return format_error(
                "Read-only mode is enabled. Guest account creation is not permitted.",
                path="/guest",
            )

        now = datetime.now(timezone.utc)
        expire_time = now + timedelta(hours=valid_hours)

        body: dict[str, Any] = {
            "username": username,
            "role_id": role_id,
            "expire_time": expire_time.strftime("%Y-%m-%d %H:%M:%S"),
            "enabled": True,
        }
        if password is not None:
            body["password"] = password

        audit = get_audit_logger()

        if dry_run:
            audit.log_write(
                tool="create_guest_account",
                path="/guest",
                method="POST",
                body=body,
                dry_run=True,
                outcome="dry_run",
                status_code=None,
            )
            return {
                "dry_run": True,
                "payload": body,
                "message": (
                    f"Dry run — guest account '{username}' would be created "
                    f"with role_id={role_id}, valid for {valid_hours} hour(s). "
                    "No request was sent to ClearPass."
                ),
            }

        try:
            result = await get_client().request("POST", "/guest", body=body)
            audit.log_write(
                tool="create_guest_account",
                path="/guest",
                method="POST",
                body=body,
                dry_run=False,
                outcome="success",
                status_code=result.get("code", 201),
            )
            return result
        except httpx.HTTPStatusError as e:
            audit.log_write(
                tool="create_guest_account",
                path="/guest",
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
                path="/guest",
            )
        except Exception as e:
            audit.log_write(
                tool="create_guest_account",
                path="/guest",
                method="POST",
                body=body,
                dry_run=False,
                outcome="error",
                status_code=None,
            )
            return format_error(str(e), path="/guest")
