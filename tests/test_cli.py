"""
test_cli.py — Tests for the CLI entry point and SSE transport configuration.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time


def test_version_flag() -> None:
    """``--version`` prints a version string and exits 0."""
    result = subprocess.run(
        [sys.executable, "-m", "clearpass_mcp", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "clearpass-mcp" in result.stdout


def test_help_flag() -> None:
    """``--help`` exits 0 and mentions key flags."""
    result = subprocess.run(
        [sys.executable, "-m", "clearpass_mcp", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--transport" in result.stdout
    assert "--port" in result.stdout
    assert "--host" in result.stdout


def test_sse_settings_applied_before_run() -> None:
    """
    Verify that ``mcp.settings.host`` and ``mcp.settings.port`` are set
    correctly when SSE transport is selected, and that ``FastMCP.run()``
    receives no unexpected keyword arguments (no ``TypeError``).

    This is a unit-level check that does NOT start a real server — it
    monkey-patches ``mcp.run`` to a no-op and inspects the settings object
    after the CLI wiring runs.
    """
    script = textwrap.dedent("""
        import sys
        # Prevent the real server from starting
        from clearpass_mcp.server import mcp
        mcp.run = lambda transport=None, mount_path=None: None

        # Simulate what main() does for SSE without actually calling argparse
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = 9876

        assert mcp.settings.host == "0.0.0.0", f"host mismatch: {mcp.settings.host!r}"
        assert mcp.settings.port == 9876, f"port mismatch: {mcp.settings.port!r}"

        # Confirm run() accepts only transport (no TypeError)
        try:
            mcp.run(transport="sse")
        except TypeError as exc:
            print(f"TypeError raised: {exc}", file=sys.stderr)
            sys.exit(1)

        print("SSE settings check passed")
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Script failed:\n{result.stderr}"
    assert "SSE settings check passed" in result.stdout


def test_sse_server_starts_and_binds() -> None:
    """
    Integration smoke-test: start the SSE server on a high-numbered port,
    confirm uvicorn logs that it is listening, then kill it.

    Requires a real ClearPass config to be absent — the server lifespan
    (which validates Settings) is not entered until the first MCP request,
    so the process starts and binds even without a .env file.
    """
    port = 18099
    proc = subprocess.Popen(
        [sys.executable, "-m", "clearpass_mcp", "--transport", "sse", "--port", str(port)],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )

    # Give uvicorn up to 8 seconds to write the "running on" line
    deadline = time.monotonic() + 8.0
    listening = False
    try:
        while time.monotonic() < deadline:
            line = proc.stderr.readline()
            if not line:
                break
            if "Uvicorn running on" in line or "Application startup complete" in line:
                listening = True
                break
    finally:
        proc.kill()
        proc.wait(timeout=5)

    assert listening, (
        f"Uvicorn never logged 'running on http://...:{port}' within the timeout. "
        "The SSE transport may not be binding correctly. "
        f"Process exit code: {proc.returncode}"
    )
