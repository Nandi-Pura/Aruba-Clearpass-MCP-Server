"""
tools/endpoints.py — Typed tools for endpoint and device insight lookups.

Tools
-----
find_endpoint_by_mac   — Look up an endpoint by its MAC address
get_endpoint_insight   — Retrieve Insight analytics for a MAC or IP address
"""
from __future__ import annotations

import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from clearpass_mcp.client import format_error, get_client
from clearpass_mcp.config import Settings

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalise_mac(mac: str) -> str:
    """
    Normalise a MAC address to the ``AA-BB-CC-DD-EE-FF`` format expected by ClearPass.

    Accepts colon-separated (``aa:bb:cc:dd:ee:ff``), hyphen-separated, or
    bare hex strings (``aabbccddeeff``).
    """
    # Strip common separators and convert to upper-case
    clean = re.sub(r"[^0-9a-fA-F]", "", mac).upper()
    if len(clean) != 12:
        raise ValueError(
            f"Invalid MAC address '{mac}'."
            " Expected 12 hex digits (with or without separators)."
        )
    return "-".join(clean[i : i + 2] for i in range(0, 12, 2))


def _http_error_response(
    e: httpx.HTTPStatusError,
    path: str,
    *,
    not_found_msg: str | None = None,
) -> dict[str, Any]:
    """
    Convert an ``httpx.HTTPStatusError`` into a formatted error dict.

    If *not_found_msg* is provided and the status code is 404, that message is
    used instead of the generic one.
    """
    if not_found_msg and e.response.status_code == 404:
        return format_error(not_found_msg, status_code=404, path=path)
    return format_error(
        f"ClearPass API error {e.response.status_code}",
        status_code=e.response.status_code,
        detail=e.response.text,
        path=path,
    )


# ---------------------------------------------------------------------------
# Tool implementations (module-level so register() stays simple)
# ---------------------------------------------------------------------------


async def find_endpoint_by_mac(mac_address: str) -> dict[str, Any]:
    """
    Look up a ClearPass endpoint by its MAC address.

    Returns full endpoint details including status, attributes, device
    profiling data, and any custom attributes set by policy.

    Args:
        mac_address: MAC address in any common format.
            Examples: ``AA:BB:CC:DD:EE:FF``, ``aa-bb-cc-dd-ee-ff``,
            ``aabbccddeeff``

    Returns:
        Endpoint object from ClearPass, or an error dict if not found.

    Example natural-language prompts:
        - "Look up the endpoint with MAC AA:BB:CC:DD:EE:FF"
        - "What do we know about device aa-bb-cc-dd-ee-ff in ClearPass?"
        - "Is MAC 001122334455 registered in ClearPass?"
    """
    try:
        normalised = _normalise_mac(mac_address)
    except ValueError as e:
        return format_error(str(e), path=f"/endpoint/mac-address/{mac_address}")

    path = f"/endpoint/mac-address/{normalised}"
    try:
        return await get_client().request("GET", path)
    except httpx.HTTPStatusError as e:
        return _http_error_response(
            e, path, not_found_msg=f"Endpoint with MAC {normalised} not found in ClearPass."
        )
    except Exception as e:
        return format_error(str(e), path=path)


async def get_endpoint_insight(mac_or_ip: str) -> dict[str, Any]:
    """
    Retrieve ClearPass Insight analytics data for a device.

    Insight provides historical visibility data such as authentication
    events, IP history, OS fingerprinting, and network location.
    Accepts either a MAC address or an IP address as the lookup key.

    Args:
        mac_or_ip: Device identifier — either a MAC address
            (e.g. ``AA:BB:CC:DD:EE:FF``) or an IPv4/IPv6 address
            (e.g. ``192.168.1.100``).

    Returns:
        Insight endpoint record, or an error dict if not found.

    Example natural-language prompts:
        - "Show me the Insight data for MAC AA:BB:CC:DD:EE:FF"
        - "What is the history of device 10.0.0.50 in ClearPass Insight?"
        - "Look up endpoint insight for IP 192.168.100.25"
    """
    # Determine if the input looks like an IP address or a MAC address
    is_mac = bool(
        re.match(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$", mac_or_ip)
        or re.match(r"^[0-9A-Fa-f]{12}$", mac_or_ip)
    )

    if not is_mac:
        path = f"/insight/endpoint/ip/{mac_or_ip}"
    else:
        clean_mac = re.sub(r"[^a-fA-F0-9]", "", mac_or_ip).upper()
        normalised = "-".join(clean_mac[i : i + 2] for i in range(0, 12, 2))
        path = f"/insight/endpoint/mac/{normalised}"

    try:
        return await get_client().request("GET", path)
    except httpx.HTTPStatusError as e:
        return _http_error_response(
            e, path, not_found_msg=f"No Insight record found for '{mac_or_ip}'."
        )
    except Exception as e:
        return format_error(str(e), path=path)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, settings: Settings) -> None:  # noqa: ARG001
    """Register endpoint tools on *mcp*."""
    mcp.tool()(find_endpoint_by_mac)
    mcp.tool()(get_endpoint_insight)
