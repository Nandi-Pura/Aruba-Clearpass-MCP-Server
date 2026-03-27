

import asyncio
import json
import httpx
from datetime import datetime, timedelta
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import os

CLEARPASS_HOST  = os.getenv("CLEARPASS_HOST", "https://clearpass.yourdomain.com")
CLIENT_ID       = os.getenv("CLEARPASS_CLIENT_ID", "your_client_id")
CLIENT_SECRET   = os.getenv("CLEARPASS_CLIENT_SECRET", "your_client_secret")
VERIFY_SSL      = os.getenv("CLEARPASS_VERIFY_SSL", "true").lower() == "true"

_token_cache = {"access_token": None, "expires_at": None}


async def get_token() -> str:
    now = datetime.utcnow()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now:
        return _token_cache["access_token"]
    url = f"{CLEARPASS_HOST}/api/oauth"
    payload = {"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        resp = await client.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + timedelta(seconds=data.get("expires_in", 3600) - 60)
    return _token_cache["access_token"]


async def cp_request(method: str, path: str, params: dict = None, body: dict = None) -> dict:
    token = await get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{CLEARPASS_HOST}/api{path}"
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        resp = await client.request(method=method.upper(), url=url, headers=headers, params=params, json=body, timeout=30)
        if resp.status_code == 204:
            return {"status": "success", "code": 204}
        resp.raise_for_status()
        return resp.json()


CLEARPASS_APIS = {
    "ApiOperations (v1)": [
        "POST   /oauth                             - Generate OAuth2 access token",
        "GET    /oauth/me                          - Get current authenticated user info",
        "GET    /oauth/privileges                  - Get current token privileges",
        "GET    /oauth/all-privileges              - List all system-defined privileges",
    ],
    "Identities (v1)": [
        "--- Endpoints & Devices ---",
        "GET    /endpoint                          - List all endpoints",
        "GET    /endpoint/mac-address/{mac}        - Get endpoint by MAC",
        "GET    /device                            - List device accounts",
        "GET    /device/mac/{macaddr}              - Get device by MAC",
        "--- Users & Guests ---",
        "GET    /local-user                        - List local users",
        "GET    /local-user/user-id/{id}           - Get local user by ID",
        "GET    /guest                             - List guest accounts",
        "GET    /guest/username/{user}             - Get guest by username",
        "--- API & Others ---",
        "GET    /api-client                        - List API clients",
        "GET    /static-host-list                  - List static host lists",
        "GET    /external-account                 - List external accounts",
    ],
    "PolicyElements (v1)": [
        "--- AuthMethod & AuthSource ---",
        "GET    /auth-method                       - List authentication methods",
        "POST   /auth-method                       - Create new authentication method",
        "GET    /auth-method/name/{name}           - Get method by name",
        "GET    /auth-source                       - List authentication sources",
        "GET    /auth-source/name/{name}           - Get source by name",
        "--- NetworkDevice & Groups ---",
        "GET    /network-device                    - List network devices (NAS)",
        "POST   /network-device                    - Create new network device",
        "GET    /network-device/name/{name}        - Get device by name",
        "DELETE /network-device/{id}               - Delete network device",
        "GET    /network-device-group              - List network device groups",
        "POST   /network-device-group              - Create new network device group",
        "--- RADIUS Proxy & Roles ---",
        "GET    /proxy-target                      - List RADIUS proxy targets",
        "GET    /role                              - List roles",
        "POST   /role                              - Create new role",
        "GET    /role/name/{name}                  - Get role by name",
        "--- Role Mapping & Services ---",
        "GET    /role-mapping                      - List role mapping policies",
        "GET    /role-mapping/name/{name}          - Get role mapping by name",
        "GET    /config/service                    - List CPPM configuration services",
        "GET    /config/service/name/{name}        - Get service by name",
        "PATCH  /config/service/{id}/enable       - Enable a service",
        "PATCH  /config/service/{id}/disable      - Disable a service",
    ],
    "SessionControl (v1)": [
        "--- Active Sessions ---",
        "GET    /session                           - List active sessions",
        "GET    /session/{id}                      - Get active session details",
        "POST   /session/{id}/disconnect           - Disconnect active session",
        "POST   /session/{id}/reauthorize          - Reauthorize active session",
        "--- Bulk Actions ---",
        "POST   /session-action/disconnect         - Bulk disconnect by filter",
        "POST   /session-action/coa                - Bulk reauthorize (CoA)",
        "GET    /session-action/{action_id}        - Get status of bulk action",
    ],
    "CertificateAuthority (v1)": [
        "--- Onboard Certificates ---",
        "GET    /certificate                       - List Onboard certificates",
        "POST   /certificate/new                   - Create new CSR and private key",
        "POST   /certificate/import                - Import CA or trusted certificate",
        "POST   /certificate/{id}/sign             - Sign a CSR",
        "POST   /certificate/{id}/revoke           - Revoke a certificate",
        "--- Onboard Device & User ---",
        "GET    /onboard/device                    - List Onboard devices",
        "GET    /onboard/device/{id}               - Get Onboard device details",
        "GET    /user                              - List Onboard users",
        "GET    /user/{id}                         - Get Onboard user details",
    ],
    "EndpointVisibility & OnGuard (v1)": [
        "--- Agentless & Profiler ---",
        "GET    /agentless-onguard/settings        - List Agentless OnGuard settings",
        "GET    /profiler-subnet-mapping           - List profiler subnet mappings",
        "POST   /device-profiler/device-fingerprint - Post device fingerprint attributes",
        "GET    /fingerprint                       - List known fingerprints",
        "--- Network Scan & Custom Scripts ---",
        "GET    /config/network-scan               - List Network Scan configurations",
        "POST   /config/network-scan               - Add a Network Scan",
        "GET    /onguard-custom-script             - List OnGuard custom scripts",
        "--- Global & Zone Settings ---",
        "GET    /onguard/global-settings           - Get OnGuard global settings",
        "GET    /onguard/policy-manager-zones      - Get PM Zones / Auth Server IPs",
    ],
    "GuestActions & Config (v1)": [
        "--- Guest Operations ---",
        "GET    /guest/{id}/receipt/{tpl}          - Generate guest receipt (HTML)",
        "GET    /guest/{id}/pass/{tpl}             - Generate digital pass",
        "POST   /guest/{id}/sendreceipt/sms        - Resend receipt via SMS",
        "POST   /guest/{id}/sendreceipt/smtp       - Resend receipt via Email",
        "--- Pages & Templates ---",
        "GET    /weblogin                          - List web login pages",
        "GET    /template/print                    - List print templates",
        "GET    /template/pass                     - List pass templates",
        "--- Guest Settings ---",
        "GET    /guest/authentication              - Guest auth configuration",
        "GET    /guestmanager                      - Guest manager settings",
    ],
    "GlobalServerConfiguration (v1)": [
        "--- Admins & Profiles ---",
        "GET    /admin-user                        - List administrator users",
        "GET    /admin-privilege                   - List administrator privileges",
        "GET    /operator-profile                  - List operator profiles",
        "--- Licenses & Attributes ---",
        "GET    /application-license               - List application licenses",
        "GET    /application-license/summary       - View license summary",
        "GET    /attribute                         - List custom attributes",
        "--- Cluster & Sync ---",
        "POST   /cluster/db-sync                   - Sync subscriber with publisher",
        "GET    /cluster/parameters                - Get cluster-wide parameters",
        "--- Policies & Messaging ---",
        "GET    /admin-user/password-policy        - Get admin password policy",
        "GET    /local-user/password-policy        - Get local user password policy",
        "GET    /messaging-setup                   - View messaging configuration",
    ],
    "LocalServerConfiguration (v1)": [
        "--- Server Info ---",
        "GET    /server/version                   - Get server versions",
        "GET    /cppm-version                     - Get CPPM specific version",
        "GET    /server/fips                      - Get FIPS mode info",
        "--- Cluster & Control ---",
        "GET    /cluster/server                    - List cluster nodes",
        "GET    /cluster/server/{uuid}             - Get node configuration",
        "GET    /server/service/{uuid}             - List all services on node",
        "PATCH  /server/service/{uuid}/{svc}/start - Start a server service",
        "--- Access & SNMP ---",
        "GET    /server/access-control/{uuid}      - View node access controls",
        "GET    /server/snmp/{uuid}                - View node SNMP settings",
    ],
    "Integrations & Extensions (v1)": [
        "--- Extensions ---",
        "GET    /extension/instance               - List installed extensions",
        "POST   /extension/instance/{id}/restart  - Restart extension",
        "GET    /extension/instance/{id}/log      - Get extension logs",
        "GET    /extension/store                   - Query extension store",
        "--- Context Servers ---",
        "GET    /endpoint-context-server          - List context servers",
        "POST   /context-server-action            - List context actions",
        "--- Syslog & Insight ---",
        "GET    /syslog-target                     - List syslog targets",
        "GET    /syslog-export-filter             - List export filters",
        "GET    /device-insight                    - Device Insight integration",
    ],
    "Logs & Audit (v1)": [
        "GET    /audit-record                     - Audit logs",
        "GET    /system-event                     - List system events",
        "GET    /login-audit/{name}               - Previous logins for admin",
        "--- Insight Endpoint Info ---",
        "GET    /insight/endpoint/mac/{mac}        - Get endpoint info by MAC",
        "GET    /insight/endpoint/ip/{ip}          - Lookup endpoint by IP",
        "GET    /insight/endpoint/time-range       - Lookup by time range",
    ],
    "PlatformCertificates (v1)": [
        "--- Trust & Revocation ---",
        "GET    /cert-trust-list                  - List trust certificates",
        "GET    /revocation-list                  - List revocation list (CRL)",
        "--- Server & Client Certs ---",
        "GET    /server-cert                      - List server certificates",
        "GET    /client-cert                      - List client certificates",
        "GET    /service-cert                     - List service certificates",
        "POST   /cert-sign-request                - Post certificate sign request",
    ],
    "ToolsAndUtilities (v1)": [
        "POST   /email/send                        - Send manual email",
        "POST   /sms/send                          - Send manual SMS",
        "GET    /random-mpsk                       - Generate random MPSK",
        "GET    /random-password                   - Generate random password",
    ],
}

app = Server("clearpass-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="clearpass_get",
            description="GET request to ANY ClearPass API endpoint. Use clearpass_list_apis to discover endpoints.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path":   {"type": "string", "description": "e.g. /endpoint, /guest, /session, /config/service, /onboard/device, /audit-record, /server/version"},
                    "params": {"type": "object", "description": "Query params e.g. {\"filter\":\"{\\\"status\\\":\\\"Known\\\"}\", \"limit\":25}"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="clearpass_post",
            description="POST request to ANY ClearPass API endpoint. Use for creating resources or triggering actions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "e.g. /guest, /local-user, /session/{id}/disconnect, /session-action/coa, /cluster/db-sync"},
                    "body": {"type": "object", "description": "Request body as JSON"},
                },
                "required": ["path", "body"],
            },
        ),
        Tool(
            name="clearpass_patch",
            description="PATCH request to ANY ClearPass API endpoint. Use for partial updates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "e.g. /endpoint/mac-address/AA-BB-CC-DD-EE-FF, /config/service/{id}/enable, /onboard/device/{id}"},
                    "body": {"type": "object", "description": "Fields to update"},
                },
                "required": ["path", "body"],
            },
        ),
        Tool(
            name="clearpass_put",
            description="PUT request to ANY ClearPass API endpoint. Use for full resource replacement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "e.g. /auth-method/{id}, /network-device/{id}"},
                    "body": {"type": "object"},
                },
                "required": ["path", "body"],
            },
        ),
        Tool(
            name="clearpass_delete",
            description="DELETE request to ANY ClearPass API endpoint.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "e.g. /guest/123, /endpoint/mac-address/AA-BB-CC-DD-EE-FF, /network-device/{id}"},
                    "confirm": {"type": "boolean", "description": "Must be true to execute"},
                },
                "required": ["path", "confirm"],
            },
        ),
        Tool(
            name="clearpass_list_apis",
            description="List all known ClearPass API endpoints grouped by category.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Optional filter e.g. 'SessionControl', 'PolicyElements', 'GuestActions', 'Identities'"},
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    except httpx.HTTPStatusError as e:
        err = {"error": f"ClearPass API error {e.response.status_code}", "detail": e.response.text, "path": str(e.request.url)}
        return [TextContent(type="text", text=json.dumps(err, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _dispatch(name: str, args: dict) -> Any:
    if name == "clearpass_list_apis":
        category_filter = args.get("category", "").lower()
        if category_filter:
            return {k: v for k, v in CLEARPASS_APIS.items() if category_filter in k.lower()}
        return CLEARPASS_APIS

    if name == "clearpass_get":
        return await cp_request("GET", args["path"], params=args.get("params"))

    if name == "clearpass_post":
        return await cp_request("POST", args["path"], body=args.get("body", {}))

    if name == "clearpass_patch":
        return await cp_request("PATCH", args["path"], body=args.get("body", {}))

    if name == "clearpass_put":
        return await cp_request("PUT", args["path"], body=args.get("body", {}))

    if name == "clearpass_delete":
        if not args.get("confirm"):
            return {"error": "Set confirm=true to execute deletion."}
        return await cp_request("DELETE", args["path"])

    return {"error": f"Unknown tool: {name}"}


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
