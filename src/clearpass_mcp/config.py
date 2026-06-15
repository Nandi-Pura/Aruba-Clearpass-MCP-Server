"""
config.py — Settings for the ClearPass MCP Server.

All configuration is read from environment variables or a ``.env`` file via
``pydantic-settings``. The server will refuse to start if any required variable
still holds its placeholder default value — fail-fast beats silent misconfiguration.

Environment Variables
---------------------
CLEARPASS_HOST
    Fully-qualified URL of the ClearPass Policy Manager instance.
    Example: ``https://clearpass.example.com``
CLEARPASS_CLIENT_ID
    OAuth2 API client ID (Administration → API Services → API Clients).
CLEARPASS_CLIENT_SECRET
    OAuth2 API client secret.
CLEARPASS_VERIFY_SSL
    Verify TLS certificates. Set to ``false`` **only** in lab environments.
    Default: ``true``.
CLEARPASS_READ_ONLY
    When ``true``, all write operations are blocked server-side.
    Default: ``false``.
CLEARPASS_LOG_LEVEL
    Python logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    Default: ``INFO``.
CLEARPASS_AUDIT_LOG_PATH
    Absolute path for the structured JSON audit log file.
    When unset, audit events are written to stderr only.
CLEARPASS_MAX_PAGES
    Maximum pages to follow when paginating list responses.
    Default: ``20``.
"""
from __future__ import annotations

import logging

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_PLACEHOLDER_VALUES: dict[str, str] = {
    "CLEARPASS_HOST": "https://clearpass.yourdomain.com",
    "CLEARPASS_CLIENT_ID": "your_client_id",
    "CLEARPASS_CLIENT_SECRET": "your_client_secret",
}


class Settings(BaseSettings):
    """
    Validated application settings loaded from environment variables or a ``.env`` file.

    Raises ``ValidationError`` on startup if any required variable is missing or
    still set to a placeholder value.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    CLEARPASS_HOST: str = "https://clearpass.yourdomain.com"
    CLEARPASS_CLIENT_ID: str = "your_client_id"
    CLEARPASS_CLIENT_SECRET: str = "your_client_secret"
    CLEARPASS_VERIFY_SSL: bool = True
    CLEARPASS_READ_ONLY: bool = False
    CLEARPASS_LOG_LEVEL: str = "INFO"
    CLEARPASS_AUDIT_LOG_PATH: str | None = None
    CLEARPASS_MAX_PAGES: int = 20

    @field_validator("CLEARPASS_HOST")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Remove any trailing slash so path joins work consistently."""
        return v.rstrip("/")

    @field_validator("CLEARPASS_LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure the log level is a recognised Python logging level name."""
        level = v.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "CLEARPASS_LOG_LEVEL must be one of "
                f"DEBUG, INFO, WARNING, ERROR, CRITICAL — got '{v}'"
            )
        return level

    @model_validator(mode="after")
    def check_no_placeholders(self) -> Settings:
        """Fail fast if any required variable still holds its placeholder default."""
        errors: list[str] = []
        for env_var, placeholder in _PLACEHOLDER_VALUES.items():
            value = getattr(self, env_var)
            if value == placeholder:
                errors.append(
                    f"  • {env_var} is still set to the placeholder value '{placeholder}'.\n"
                    f"    Set a real value via the environment variable or your .env file."
                )
        if errors:
            raise ValueError(
                "ClearPass MCP Server cannot start — required configuration is missing:\n\n"
                + "\n".join(errors)
                + "\n\nSee .env.example for a full configuration reference."
            )
        return self
