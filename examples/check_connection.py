"""
check_connection.py — Standalone example: use ClearPassClient outside MCP.

This script demonstrates that ``ClearPassClient`` is a first-class Python
library — it can be used in regular scripts, automation pipelines, or
integration tests without running the MCP server at all.

Usage::

    # Ensure your .env is configured (or export env vars directly)
    python examples/check_connection.py

Exit codes:
    0 — Connected and token obtained successfully
    1 — Configuration or connection error
"""
from __future__ import annotations

import asyncio
import sys

# ---------------------------------------------------------------------------
# This example requires the package to be installed:
#   pip install -e .
# or run from the repo root with the src/ layout available on PYTHONPATH.
# ---------------------------------------------------------------------------


async def main() -> int:
    try:
        from clearpass_mcp.client import ClearPassClient
        from clearpass_mcp.config import Settings
    except ImportError:
        print("Error: clearpass_mcp is not installed. Run: pip install -e .", file=sys.stderr)
        return 1

    # Load and validate configuration from environment / .env
    try:
        settings = Settings()
    except Exception as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 1

    print(f"Connecting to ClearPass at {settings.CLEARPASS_HOST} …")

    client = ClearPassClient(settings)
    try:
        # Test 1: OAuth2 token
        token = await client.get_token()
        print(f"✓ OAuth2 token obtained ({len(token)} chars)")

        # Test 2: Retrieve server version (read-only, no side-effects)
        version_data = await client.request("GET", "/server/version")
        print(f"✓ Server version: {version_data}")

        # Test 3: List first page of endpoints
        endpoints = await client.request("GET", "/endpoint", params={"limit": 5})
        count = endpoints.get("count", "unknown")
        total = endpoints.get("total", "unknown")
        print(f"✓ Endpoints (showing {count} of {total})")

        print("\nAll checks passed! ClearPass is reachable and credentials are valid.")
        return 0

    except Exception as exc:
        print(f"\n✗ Error: {exc}", file=sys.stderr)
        return 1

    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
