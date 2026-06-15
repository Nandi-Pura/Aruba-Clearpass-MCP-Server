# Contributing to Aruba-Clearpass-MCP-Server

Welcome, and thank you for considering contributing to the Aruba-Clearpass-MCP-Server! This project integrates HPE Aruba ClearPass (CPPM) with the Model Context Protocol (MCP). We welcome contributions, especially those that add coverage for new ClearPass API endpoints.

## Local Development Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Nandi-Pura/Aruba-Clearpass-MCP-Server.git
   cd Aruba-Clearpass-MCP-Server
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

## Running the Server Locally

After setting up your `.env` file with your ClearPass credentials:
```bash
# Validate your configuration
clearpass-mcp --check

# Run the MCP server using stdio (default)
clearpass-mcp

# Run the MCP server using SSE transport
clearpass-mcp --transport sse --port 8000
```

## Submitting Issues

If you encounter an issue or have a feature request, please open a GitHub Issue:
- **Bug Reports:** Include steps to reproduce, expected behavior, actual behavior, and relevant logs (with secrets redacted).
- **Feature Requests:** Describe the use case and how the new feature or endpoint coverage would be helpful.

## Pull Requests

1. Fork the repository and create a new branch from `main`.
2. **Branch Naming:** Use conventional prefixes for your branch name:
   - `feat/` for new features (e.g., `feat/new-api-endpoint`)
   - `fix/` for bug fixes (e.g., `fix/token-refresh`)
   - `docs/` for documentation updates (e.g., `docs/update-readme`)
3. Ensure your code passes all linting and type checks (`ruff check .` and `mypy src`).
4. Submit your Pull Request and provide a clear description of the changes.

## Code Style

- **PEP8:** Follow standard Python PEP8 conventions. We use `ruff` to enforce this.
- **Type Hints:** All functions and methods must include explicit Python type hints.
- **Docstrings:** Use Google-style docstrings for all modules, classes, and functions to ensure clear documentation.
