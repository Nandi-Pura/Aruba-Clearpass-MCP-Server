# 🛡️ Aruba ClearPass MCP Server
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/Model%20Context%20Protocol-Supported-green.svg)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A high-performance **Model Context Protocol (MCP)** server that enables seamless integration between AI assistants (like Claude) and **Aruba ClearPass Policy Manager (CPPM)** via REST API (OAuth2).

This server empowers network administrators to manage access policies, monitor endpoints, and perform complex troubleshooting using natural language commands through an AI interface.

---

## 🚀 Key Features

- **Comprehensive API Support**: Supports **all** ClearPass v1 REST API endpoints via generic HTTP methods (GET, POST, PATCH, PUT, DELETE).
- **Dynamic Discovery**: Includes `clearpass_list_apis` to browse hundreds of available endpoints grouped by category.
- **Enterprise Ready**: Implements secure OAuth2 Client Credentials grant with automatic token caching and optional SSL verification.
- **Structured Categories**: APIs are organized following the official Aruba CPPM documentation (Identities, Policy, Session, Onboard, etc.).

---

## 🛠️ Supported API Categories

| Category | Primary Services |
| :--- | :--- |
| **Identities** | Endpoints, Device Accounts, Local/Guest Users, Static Host Lists. |
| **Policy Elements** | NAS Devices, Auth Sources, Auth Methods, CPPM Services. |
| **Session Control** | Active Session Monitoring, Change of Authorization (CoA), Bulk Disconnect. |
| **Onboard & CA** | Device/User Provisioning, CSR Management, Revocation, Trust Lists. |
| **OnGuard & Visibility** | Agentless OnGuard, Device Fingerprofiling, Network Scan, Zone Mapping. |
| **Guest Management** | Web Login Portals, Print Templates, Digital Pass, Receipt Generation. |
| **System & Logs** | Cluster Sync, License Management, Audit Records, Insight Analytics. |

---

## 📋 Prerequisites

- **Aruba ClearPass Policy Manager** (Version with REST API support).
- **Python 3.10** or higher.
- Required Libraries: `mcp`, `httpx`, `asyncio`.

---

## ⚙️ Installation & Setup

### 1. ClearPass Configuration
Go to **Administration → API Services → API Clients** in your ClearPass UI and add a new client:
- **Grant Type**: `client_credentials`
- **Profile**: Select an Operator Profile with appropriate permissions (e.g., *API Administrator*).
- Note down your **Client ID** and **Client Secret**.

### 2. Local Installation
```bash
# Clone or copy this repository
cd my-mcp-server

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Either create a `.env` file or export the following variables:
```bash
export CLEARPASS_HOST="https://your-clearpass.domain.com"
export CLEARPASS_CLIENT_ID="your_client_id"
export CLEARPASS_CLIENT_SECRET="your_client_secret"
export CLEARPASS_VERIFY_SSL="true" # Set to false for self-signed development certs
```

---

## 🤖 Client Integration Guide

Since this server follows the **Model Context Protocol (MCP)**, it can be integrated with any supporting AI client.

### 1. Claude Desktop
Add the following to your `claude_desktop_config.json`:
- **Path (macOS):** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Path (Windows):** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "clearpass": {
      "command": "/path/to/your/venv/python",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "CLEARPASS_HOST": "https://your-clearpass-url",
        "CLEARPASS_CLIENT_ID": "your_client_id",
        "CLEARPASS_CLIENT_SECRET": "your_client_secret",
        "CLEARPASS_VERIFY_SSL": "true"
      }
    }
  }
}
```

### 2. Continue.dev (VS Code & JetBrains)
Perfect for users of **Ollama**, **Qwen**, or local models. Add the MCP provider to your `config.json`:

```json
{
  "contextProviders": [
    {
      "name": "mcp",
      "args": {
        "command": "/path/to/venv/python",
        "args": ["/path/to/server.py"],
        "env": {
          "CLEARPASS_HOST": "...",
          "CLEARPASS_CLIENT_ID": "...",
          "CLEARPASS_CLIENT_SECRET": "..."
        }
      }
    }
  ]
}
```

### 3. ChatGPT & Other Platforms
While ChatGPT's official web UI does not yet support MCP directly, you can use:
- **MCP Bridge**: Connects MCP tools as custom Actions/GPTs.
- **ChatHub**: A multi-model client that bridges MCP with ChatGPT, Claude, and Gemini.

### 4. Ollama & Qwen via CLI
Use any MCP-compatible CLI tool (like `mcp-cli`) to invoke ClearPass tools using Qwen or Ollama models.

---

## 💬 Usage Examples

Once connected, you can use natural language prompts such as:

- 🔍 *"List all endpoints with the 'iPhone' OS profile."*
- 🔐 *"Create a new Guest account for a meeting guest, valid for 8 hours."*
- 🚫 *"Disconnect the session for the device with MAC AA-BB-CC-DD-EE-FF."*
- 📑 *"Show me the last 10 audit logs related to administrator logins."*
- 🛠️ *"Check the current cluster database synchronization status."*

---

## 🛡️ Security & Best Practices

1. **Principle of Least Privilege**: Use a ClearPass Operator Profile that only has the necessary permissions (use Read-only if you only need monitoring).
2. **Secure SSL**: Always keep `CLEARPASS_VERIFY_SSL` as `true` in production to prevent Man-in-the-Middle (MITM) attacks.
3. **Secrets Management**: Never commit your `Client Secret` to a public repository. Use Environment Variables or Secret Managers.

---

## 📄 License
This project is distributed under the **MIT License**. See `LICENSE` for more information.
