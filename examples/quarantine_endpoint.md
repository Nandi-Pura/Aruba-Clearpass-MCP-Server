# Example: Quarantine / Disconnect a Suspicious Endpoint

This example shows how to investigate a potentially compromised device and safely
disconnect it from the network — with a mandatory dry-run step before the real action.

---

## Scenario

Your SOC has flagged unusual traffic from MAC address `BB:CC:DD:EE:FF:00`. You need to
investigate whether the device is legitimate, confirm its current network access, and if
necessary, disconnect it cleanly from ClearPass.

---

## Step 1 — Identify the device

**You say:**
> "Tell me everything ClearPass knows about MAC BB:CC:DD:EE:FF:00."

**Tool called:** `find_endpoint_by_mac(mac_address="BB:CC:DD:EE:FF:00")`

**Example output:**
```json
{
  "id": 5678,
  "mac_address": "BB-CC-DD-EE-FF-00",
  "status": "Known",
  "device_insight_tags": ["Android", "Mobile"],
  "attributes": {
    "Owner": "unknown",
    "Department": ""
  }
}
```

⚠️ **Red flag:** Owner is unknown and Department is empty — unexpected for a corporate device.

---

## Step 2 — Check its active session

**You say:**
> "Is this device currently connected? Show me its session details."

**Tool called:** `list_active_sessions(filter={"mac_address": "BB-CC-DD-EE-FF-00"})`

**Example output:**
```json
{
  "items": [
    {
      "id": "sess-danger456",
      "mac_address": "BB-CC-DD-EE-FF-00",
      "ip_address": "10.0.50.99",
      "role_name": "Employee",
      "nasipaddress": "10.0.0.1",
      "acctstatus": "Start"
    }
  ],
  "total": 1,
  "retrieved": 1
}
```

---

## Step 3 — Dry run the disconnect

**You say:**
> "Disconnect session sess-danger456 — dry run first."

**Tool called:**
```
disconnect_session(session_id="sess-danger456", confirm=True, dry_run=True)
```

**Output:**
```json
{
  "dry_run": true,
  "session_id": "sess-danger456",
  "message": "Dry run — session would be disconnected. No request was sent."
}
```

---

## Step 4 — Execute the disconnect

**You say:**
> "Do it for real. Disconnect sess-danger456. I confirm."

**Tool called:**
```
disconnect_session(session_id="sess-danger456", confirm=True, dry_run=False)
```

---

## Step 5 — Mark the endpoint for quarantine

**You say:**
> "Update the endpoint status to Unknown and add a note that it's under investigation."

**Tool called:**
```
clearpass_patch(
    path="/endpoint/mac-address/BB-CC-DD-EE-FF-00",
    body={
        "status": "Unknown",
        "attributes": {"Investigation-Note": "Flagged by SOC 2024-01-15"}
    }
)
```

---

## Using the Guided Prompt

Use the `quarantine_endpoint` prompt for an automated multi-step workflow:

> **Prompt:** `quarantine_endpoint`
> **Parameter:** `mac_address = "BB:CC:DD:EE:FF:00"`
