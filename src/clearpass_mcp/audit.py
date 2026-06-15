"""
audit.py — Structured JSON audit logging for write operations.

Every POST/PATCH/PUT/DELETE operation emits a JSON line containing:

- ``timestamp``  — UTC ISO-8601 string
- ``tool``       — MCP tool name that triggered the operation
- ``method``     — HTTP method
- ``path``       — API path
- ``body``       — Redacted request body (keys with "secret", "password", or "token" are hidden)
- ``dry_run``    — Whether the request was a dry-run preview
- ``outcome``    — ``"success"`` | ``"error"``
- ``status_code``— HTTP status code (or ``null`` for dry-run / connection errors)

Output goes to:
1. ``stdout`` always (so MCP clients with stdio transport see audit lines in the log stream)
2. A file at ``CLEARPASS_AUDIT_LOG_PATH`` (if configured).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Keys whose values are redacted in audit output (case-insensitive substring match)
_REDACT_SUBSTRINGS = ("secret", "password", "token", "key", "credential")


def _redact(obj: Any, depth: int = 0) -> Any:
    """
    Recursively redact sensitive keys from a dict.

    Args:
        obj: The object to redact (dict, list, or scalar).
        depth: Current recursion depth (capped at 10 to prevent abuse).

    Returns:
        A new object with sensitive string values replaced by ``"[REDACTED]"``.
    """
    if depth > 10:
        return obj
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]"
        if any(s in k.lower() for s in _REDACT_SUBSTRINGS)
        else _redact(v, depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(item, depth + 1) for item in obj]
    return obj


class AuditLogger:
    """
    Structured JSON audit logger for write operations.

    Usage::

        audit = AuditLogger(log_path="/var/log/clearpass-mcp/audit.jsonl")
        audit.log_write(
            tool="create_guest_account",
            path="/guest",
            method="POST",
            body={"username": "visitor1", "password": "secret!"},
            dry_run=False,
            outcome="success",
            status_code=201,
        )
    """

    def __init__(self, log_path: str | None = None) -> None:
        self._file_handle: Any = None
        if log_path:
            path = Path(log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._file_handle = path.open("a", encoding="utf-8")
                logger.info("Audit log file: %s", path.resolve())
            except OSError as exc:
                logger.warning("Cannot open audit log file %s: %s", log_path, exc)

    def log_write(
        self,
        *,
        tool: str,
        path: str,
        method: str,
        body: dict[str, Any] | None = None,
        dry_run: bool = False,
        outcome: str,
        status_code: int | None = None,
    ) -> None:
        """
        Emit one structured audit line.

        Args:
            tool: The MCP tool name (e.g. ``"disconnect_session"``).
            path: The ClearPass API path (e.g. ``"/session/abc123/disconnect"``).
            method: HTTP method (POST, PATCH, PUT, DELETE).
            body: Raw request body; sensitive keys will be automatically redacted.
            dry_run: ``True`` if no real HTTP request was sent.
            outcome: ``"success"`` or ``"error"``.
            status_code: HTTP status code returned by ClearPass (``None`` for dry-runs).
        """
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "method": method.upper(),
            "path": path,
            "body": _redact(body) if body else None,
            "dry_run": dry_run,
            "outcome": outcome,
            "status_code": status_code,
        }
        line = json.dumps(record, ensure_ascii=False)

        # Always log to stderr so it doesn't pollute the MCP stdio transport
        print(f"[AUDIT] {line}", file=sys.stderr, flush=True)

        if self._file_handle is not None:
            try:
                self._file_handle.write(line + "\n")
                self._file_handle.flush()
            except OSError as exc:
                logger.warning("Failed to write audit log entry: %s", exc)

    def close(self) -> None:
        """Close the audit log file handle if open."""
        if self._file_handle is not None:
            try:
                self._file_handle.close()
            except OSError:
                pass
            finally:
                self._file_handle = None


# ---------------------------------------------------------------------------
# Module-level singleton (set during server lifespan)
# ---------------------------------------------------------------------------
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Return the shared AuditLogger singleton."""
    if _audit_logger is None:
        raise RuntimeError("AuditLogger is not initialized.")
    return _audit_logger


def set_audit_logger(audit: AuditLogger | None) -> None:
    """Set the shared AuditLogger singleton (used by lifespan and tests)."""
    global _audit_logger
    _audit_logger = audit
