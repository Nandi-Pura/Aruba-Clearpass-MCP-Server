# Contributing to Aruba ClearPass MCP Server

Thank you for considering a contribution! This document covers how to set up the development
environment, run the test suite, and submit a pull request.

## Code of Conduct

Please be respectful and constructive. This is a community project and everyone is welcome.

---

## Development Setup

### Prerequisites

- Python 3.10 or higher
- `git`
- A ClearPass Policy Manager instance for integration testing (optional — unit tests run fully offline)

### 1. Fork and clone

```bash
git clone https://github.com/Nandi-Pura/Aruba-Clearpass-MCP-Server.git
cd Aruba-Clearpass-MCP-Server
```

### 2. Create a virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install in editable mode with dev dependencies

```bash
pip install -e ".[dev]"
```

### 4. (Optional) Configure a real ClearPass instance

```bash
cp .env.example .env
# Edit .env with your ClearPass credentials
clearpass-mcp --check   # validates config + tests OAuth2
```

---

## Running Tests

All tests run fully offline using `respx` to mock the ClearPass API.

```bash
pytest                      # run all tests
pytest -v                   # verbose output
pytest tests/test_client.py # single file
```

### Test coverage

```bash
pip install pytest-cov
pytest --cov=clearpass_mcp --cov-report=term-missing
```

---

## Linting and Type Checking

```bash
ruff check .            # linter (PEP 8, imports, style)
ruff check . --fix      # auto-fix where possible
mypy src                # static type checking
```

The CI pipeline runs all three checks on every push and pull request.

---

## Project Layout

```
src/clearpass_mcp/
├── __init__.py         # version / metadata
├── __main__.py         # CLI entry point
├── config.py           # pydantic-settings configuration
├── client.py           # ClearPassClient (httpx pool, OAuth2, retry, paginate)
├── catalog.py          # static API endpoint catalog
├── audit.py            # structured JSON audit logger
├── server.py           # FastMCP wiring: resources, prompts, tool registration
└── tools/
    ├── generic.py      # clearpass_get/post/patch/put/delete/list_apis
    ├── endpoints.py    # find_endpoint_by_mac, get_endpoint_insight
    ├── sessions.py     # list_active_sessions, disconnect_session, bulk_coa
    ├── guests.py       # create_guest_account
    └── admin.py        # get_server_health, search_audit_records
```

---

## Adding a New Tool

1. Create or find the appropriate module in `src/clearpass_mcp/tools/`.
2. Add your tool function inside the `register(mcp, settings)` function using `@mcp.tool()`.
3. Add type hints and a docstring including:
   - What the tool does
   - Each parameter's purpose and example values
   - At least 2–3 example natural-language prompts a user might say
4. Add tests in `tests/test_curated_tools.py` (or a new test file).
5. Update the **Tool Reference** table in `README.md`.
6. Add an entry to `CHANGELOG.md` under `[Unreleased]`.

---

## Pull Request Process

1. Create a feature branch: `git checkout -b feat/my-new-tool`
2. Make your changes, ensuring:
   - `ruff check .` passes
   - `mypy src` passes
   - `pytest` passes
   - Docstrings and type hints are complete
3. Update `CHANGELOG.md` under `[Unreleased]`.
4. Open a PR against `main`. Describe what the change does and why.

---

## Reporting Bugs

Open a GitHub issue with:
- Python version and OS
- Steps to reproduce
- Expected vs. actual behaviour
- Relevant log output (redact any secrets!)

For security-sensitive issues, see [SECURITY.md](SECURITY.md) instead.
