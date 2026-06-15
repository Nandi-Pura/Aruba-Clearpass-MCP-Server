# Example: Investigate a Device by MAC Address

This example shows how to use the ClearPass MCP server to investigate a suspicious or
unrecognised device using only natural language prompts.

---

## Scenario

Your network team has flagged MAC address `AA:BB:CC:DD:EE:FF` as potentially suspicious.
You want to investigate what ClearPass knows about it, check its active session, and review
its Insight history.

---

## Step 1 — Look up the endpoint

**You say:**
> "Look up the endpoint with MAC AA:BB:CC:DD:EE:FF in ClearPass."

**Tool called:** `find_endpoint_by_mac(mac_address="AA:BB:CC:DD:EE:FF")`

**Expected output:**
```json
{
  "id": 1234,
  "mac_address": "AA-BB-CC-DD-EE-FF",
  "status": "Known",
  "device_insight_tags": ["Windows-PC"],
  "attributes": {
    "Department": "Finance",
    "Owner": "john.doe@example.com"
  }
}
```

---

## Step 2 — Check active sessions

**You say:**
> "Is this device currently connected? Check its active sessions."

**Tool called:** `list_active_sessions(filter={"mac_address": "AA-BB-CC-DD-EE-FF"})`

**Expected output:**
```json
{
  "items": [
    {
      "id": "sess-abc123",
      "mac_address": "AA-BB-CC-DD-EE-FF",
      "ip_address": "10.0.100.50",
      "role_name": "Employee",
      "acctstatus": "Start",
      "nasipaddress": "10.0.0.1"
    }
  ],
  "total": 1,
  "retrieved": 1
}
```

---

## Step 3 — Review Insight data

**You say:**
> "Show me the ClearPass Insight history for this device."

**Tool called:** `get_endpoint_insight(mac_or_ip="AA:BB:CC:DD:EE:FF")`

---

## Step 4 — Disconnect (if needed)

**You say:**
> "Disconnect session sess-abc123. I confirm."

**Tool called (dry run first):**
```
disconnect_session(session_id="sess-abc123", confirm=True, dry_run=True)
```

**After reviewing the dry-run output:**
```
disconnect_session(session_id="sess-abc123", confirm=True, dry_run=False)
```

---

## Using the Guided Prompt

Instead of the individual steps above, you can use the built-in guided prompt:

> **Prompt:** `investigate_device_by_mac`
> **Parameter:** `mac_address = "AA:BB:CC:DD:EE:FF"`

The server will automatically combine all three lookups and summarise the findings.
