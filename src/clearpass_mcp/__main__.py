"""
__main__.py — CLI entry point for the ClearPass MCP Server.

Usage
-----
::

    clearpass-mcp --help
    clearpass-mcp --version
    clearpass-mcp --check                         # validate config + test OAuth2
    clearpass-mcp                                 # start server (stdio, default)
    clearpass-mcp --transport sse --port 8000     # start SSE server
    clearpass-mcp --transport sse --host 0.0.0.0 --port 8000

Exit codes for ``--check``
--------------------------
0 — Config is valid and an OAuth2 token was obtained successfully.
1 — Config validation failed (missing or placeholder values).
2 — OAuth2 token fetch failed (bad credentials, unreachable host, TLS error).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from clearpass_mcp import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clearpass-mcp",
        description=(
            "Aruba ClearPass MCP Server — community MCP server for Aruba ClearPass "
            "Policy Manager. MIT Licensed. Not an official HPE/Aruba product."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"clearpass-mcp {__version__}",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Validate configuration and test OAuth2 token fetch, then exit. "
            "Exit code 0 = success, 1 = config error, 2 = OAuth2 error."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to use (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for SSE transport (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on for SSE transport (default: 8000).",
    )
    return parser


async def _check() -> None:
    """Validate config and test OAuth2, printing results to stdout."""
    print("ClearPass MCP Server — configuration check\n")

    # Step 1: Config validation
    try:
        from clearpass_mcp.config import Settings

        settings = Settings()
        print(f"  ✓ CLEARPASS_HOST       = {settings.CLEARPASS_HOST}")
        print(f"  ✓ CLEARPASS_CLIENT_ID  = {settings.CLEARPASS_CLIENT_ID}")
        print(f"  ✓ CLEARPASS_VERIFY_SSL = {settings.CLEARPASS_VERIFY_SSL}")
        print(f"  ✓ CLEARPASS_READ_ONLY  = {settings.CLEARPASS_READ_ONLY}")
        print(f"  ✓ CLEARPASS_LOG_LEVEL  = {settings.CLEARPASS_LOG_LEVEL}")
        print()
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ Config error:\n\n{exc}\n", file=sys.stderr)
        sys.exit(1)

    # Step 2: OAuth2 token fetch
    print("Testing OAuth2 token fetch …")
    try:
        from clearpass_mcp.client import ClearPassClient

        client = ClearPassClient(settings)
        token = await client.get_token()
        await client.close()
        print(f"  ✓ Token obtained successfully (length={len(token)} chars).\n")
        print("All checks passed. The server is ready to start.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"\n  ✗ OAuth2 error:\n\n{exc}\n", file=sys.stderr)
        print(
            "Hint: Verify CLEARPASS_HOST, CLEARPASS_CLIENT_ID, "
            "CLEARPASS_CLIENT_SECRET, and CLEARPASS_VERIFY_SSL.",
            file=sys.stderr,
        )
        sys.exit(2)


def main() -> None:
    """CLI entry point registered as ``clearpass-mcp`` in pyproject.toml."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.check:
        asyncio.run(_check())
        return

    # Lazy import to avoid loading the full server stack during --check
    from clearpass_mcp.server import mcp

    if args.transport == "sse":
        print(
            f"Starting ClearPass MCP Server (SSE) on http://{args.host}:{args.port}",
            file=sys.stderr,
        )
        mcp.run(transport="sse", host=args.host, port=args.port)  # type: ignore[call-arg]
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
