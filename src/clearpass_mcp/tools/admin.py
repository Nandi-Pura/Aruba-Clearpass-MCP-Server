"""
tools/admin.py — Typed tools for server health and audit record retrieval.

Tools
-----
get_server_health      — Aggregated cluster health summary
search_audit_records   — Paginated audit record search with time/category filters
"""
from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from clearpass_mcp.client import format_error, get_client
from clearpass_mcp.config import Settings


def register(mcp: FastMCP, settings: Settings) -> None:  # noqa: ARG001
    """Register administrative tools on *mcp*."""

    @mcp.tool()
    async def get_server_health() -> dict[str, Any]:
        """
        Retrieve an aggregated health summary for the ClearPass cluster.

        Combines data from three endpoints into one concise status object:

        - ``/server/version``   — software versions for each cluster node
        - ``/cluster/server``   — cluster node list with roles (publisher/subscriber)
        - ``/server/fips``      — FIPS compliance mode

        Returns:
            ``{"versions": ..., "cluster_nodes": [...], "fips": ..., "errors": [...]}``

        Example natural-language prompts:
            - "What is the ClearPass cluster health right now?"
            - "Show me the software versions running on each node"
            - "Is the ClearPass cluster in FIPS mode?"
            - "Give me a daily health check of the ClearPass infrastructure"
        """
        results: dict[str, Any] = {}
        errors: list[str] = []
        client = get_client()

        for label, path in [
            ("versions", "/server/version"),
            ("cluster_nodes", "/cluster/server"),
            ("fips", "/server/fips"),
        ]:
            try:
                data = await client.request("GET", path)
                results[label] = data
            except httpx.HTTPStatusError as e:
                errors.append(f"{path}: HTTP {e.response.status_code} — {e.response.text[:200]}")
                results[label] = None
            except Exception as e:
                errors.append(f"{path}: {e}")
                results[label] = None

        return {**results, "errors": errors}

    @mcp.tool()
    async def search_audit_records(
        start_time: str,
        end_time: str,
        category: str | None = None,
        max_pages: int = 5,
    ) -> dict[str, Any]:
        """
        Search ClearPass audit records within a time range, with optional category filtering.

        Audit records capture all administrative and policy changes made through
        the ClearPass UI, REST API, or automated processes.

        Args:
            start_time: Start of the time range in ISO-8601 format or
                ``"YYYY-MM-DD HH:MM:SS"`` (UTC).
                Example: ``"2024-01-15 00:00:00"``
            end_time: End of the time range in ISO-8601 format or
                ``"YYYY-MM-DD HH:MM:SS"`` (UTC).
                Example: ``"2024-01-15 23:59:59"``
            category: Optional audit category to filter by.
                Examples: ``"endpoint"``, ``"guest"``, ``"session"``,
                ``"admin-user"``, ``"network-device"``
            max_pages: Maximum pages to retrieve.  Default: ``5``.

        Returns:
            ``{"items": [...], "total": int, "truncated": bool, "retrieved": int}``

        Example natural-language prompts:
            - "Show me all audit logs from yesterday"
            - "What guest accounts were created today?"
            - "Find all endpoint changes in the last 24 hours"
            - "Show admin-user audit records between 2024-01-01 and 2024-01-07"
        """
        import json as _json

        filter_dict: dict[str, Any] = {
            "timestamp": {"$ge": start_time, "$le": end_time},
        }
        if category:
            filter_dict["category"] = category

        params: dict[str, Any] = {
            "filter": _json.dumps(filter_dict),
            "sort": "-timestamp",
            "calculate_count": True,
        }

        items: list[Any] = []
        total = 0
        truncated = False

        try:
            async for page in get_client().paginate(
                "/audit-record", params=params, max_pages=max_pages
            ):
                embedded = page.get("_embedded", {})
                page_items = embedded.get("items", [])
                items.extend(page_items)
                if not total:
                    total = page.get("total", 0)
                if "_links" in page and "next" in page.get("_links", {}):
                    truncated = True
        except httpx.HTTPStatusError as e:
            return format_error(
                f"ClearPass API error {e.response.status_code}",
                status_code=e.response.status_code,
                detail=e.response.text,
                path="/audit-record",
            )
        except Exception as e:
            return format_error(str(e), path="/audit-record")

        return {
            "items": items,
            "total": total,
            "retrieved": len(items),
            "truncated": truncated,
        }
