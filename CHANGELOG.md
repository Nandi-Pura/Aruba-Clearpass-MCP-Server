# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.0.0] — 2024-01-15

This release is a complete refactor of the original prototype into a production-grade,
installable Python package ready for community listing on the HPE Aruba Networking
Developer Hub Code Exchange.

### Added

**Package & Tooling**
- `pyproject.toml` with hatchling build backend; `pip install -e .` and `uvx clearpass-mcp` now work
- `clearpass-mcp` console script entry point
- `LICENSE` file (MIT) — was referenced in README but missing
- `.env.example` with all supported configuration variables documented
- `.gitignore` updated to cover `.env`, `__pycache__`, `.mypy_cache`, `dist/`, etc.

**Core Modules (`src/clearpass_mcp/`)**
- `config.py` — `pydantic-settings` `Settings` class with placeholder-detection validation; fails fast with a clear error if required variables are missing
- `client.py` — `ClearPassClient`: single persistent `httpx.AsyncClient` (connection pooling), `asyncio.Lock` for token refresh, automatic 401 → refresh → retry, `tenacity` exponential-backoff retry for 5xx/timeouts (3 attempts), `paginate()` async generator following `_links.next`
- `catalog.py` — API catalog relocated from `server.py`; expanded with CRUD operations for endpoints, users, and devices
- `audit.py` — Structured JSON audit logger; auto-redacts keys containing `secret`, `password`, `token`, `key`, `credential`; writes to stderr + optional file

**Tools (`src/clearpass_mcp/tools/`)**
- `generic.py` — Hardened `clearpass_get/post/patch/put/delete/list_apis` with `dry_run`, `CLEARPASS_READ_ONLY` guard, consistent error shape, and audit logging on writes
- `endpoints.py` — `find_endpoint_by_mac` (MAC normalisation), `get_endpoint_insight` (MAC or IP)
- `sessions.py` — `list_active_sessions` (paginated), `disconnect_session` (confirm gate), `bulk_coa` (confirm gate)
- `guests.py` — `create_guest_account` with auto-calculated `expire_time`
- `admin.py` — `get_server_health` (aggregated), `search_audit_records` (paginated with time/category filter)

**MCP Server (`src/clearpass_mcp/server.py`)**
- Migrated from `mcp.server.Server` (low-level) to `FastMCP` (decorator style)
- MCP Resource: `clearpass://api-catalog`
- MCP Prompts: `investigate_device_by_mac`, `onboard_guest_account`, `quarantine_endpoint`, `daily_cluster_health_check`
- Proper lifespan context manager (startup/shutdown with client and audit logger)

**CLI (`src/clearpass_mcp/__main__.py`)**
- `--version` flag
- `--check` flag (exit codes 0/1/2) — validates config and tests OAuth2 token fetch
- `--transport stdio|sse` — default stdio, SSE for remote deployments
- `--host` / `--port` for SSE

**Tests**
- `tests/conftest.py` — `respx` mock router, `Settings.model_construct()` fixture, `ClearPassClient` and `AuditLogger` fixtures
- `tests/test_client.py` — token caching, expiry, concurrent refresh lock, 401 auto-refresh, 5xx retry, timeout retry, pagination, `max_pages` truncation, error shape, 204 handling
- `tests/test_generic_tools.py` — all 6 generic tools: success, dry_run, read-only block, confirm gate, HTTP error, exception
- `tests/test_curated_tools.py` — all 8 curated tools against mocked responses
- `.github/workflows/ci.yml` — ruff + mypy + pytest on Python 3.10/3.11/3.12 matrix

**Documentation**
- `README.md` — full rewrite: badges, Mermaid architecture diagram, quick-start, tool reference table, security section, pyclearpass comparison, community disclaimer
- `CONTRIBUTING.md` — setup, testing, linting, project layout, tool-addition guide, PR process
- `SECURITY.md` — responsible-disclosure contact process
- `CHANGELOG.md` (this file)
- Guided workflow examples are provided as built-in MCP Prompts (see `server.py`)

**Distribution**
- `Dockerfile` — multi-stage Python build for SSE transport
- `docker-compose.yml` — minimal compose for SSE deployment
- Updated `claude_desktop_config.json` with `uvx clearpass-mcp` primary config

### Changed

- `datetime.utcnow()` → `datetime.now(timezone.utc)` throughout (deprecation fix)
- `httpx.AsyncClient` now created once at startup, not per-request
- Error responses now use consistent shape: `{"error": ..., "status_code": ..., "detail": ..., "path": ...}`
- `clearpass_delete` now also supported with `dry_run` parameter

### Removed

- Top-level `server.py` (replaced by `src/clearpass_mcp/server.py`)
- `requirements.txt` (replaced by `pyproject.toml` dependencies)

---

## [0.1.0] — 2024-01-01

### Added

- Initial prototype: single `server.py` with `mcp.server.Server` (low-level API)
- Generic proxy tools: `clearpass_get`, `clearpass_post`, `clearpass_patch`, `clearpass_put`, `clearpass_delete`, `clearpass_list_apis`
- Basic OAuth2 `client_credentials` token caching
- `README.md` and `claude_desktop_config.json`

[Unreleased]: https://github.com/Nandi-Pura/Aruba-Clearpass-MCP-Server/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Nandi-Pura/Aruba-Clearpass-MCP-Server/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/Nandi-Pura/Aruba-Clearpass-MCP-Server/releases/tag/v0.1.0
