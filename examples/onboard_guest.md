# Example: Onboard a New Guest Account

This example walks through provisioning a time-limited guest account using natural language,
with a mandatory dry-run review step before the account is created.

---

## Scenario

A visitor is arriving for a meeting. You need to create a ClearPass guest account valid for
8 hours so they can access the corporate WiFi guest portal.

---

## Step 1 — Discover available guest roles

**You say:**
> "What guest roles are available in ClearPass?"

**Tool called:** `clearpass_get(path="/role")`

**Expected output (example):**
```json
{
  "_embedded": {
    "items": [
      {"id": 5, "name": "Guest"},
      {"id": 6, "name": "Contractor"},
      {"id": 7, "name": "Conference-Guest"}
    ]
  }
}
```

---

## Step 2 — Preview the account (dry run)

**You say:**
> "Create a guest account for alice@example.com using role ID 7, valid for 8 hours. Do a dry run first."

**Tool called:**
```
create_guest_account(
    username="alice@example.com",
    role_id=7,
    valid_hours=8,
    dry_run=True
)
```

**Expected output:**
```json
{
  "dry_run": true,
  "payload": {
    "username": "alice@example.com",
    "role_id": 7,
    "expire_time": "2024-01-15 18:00:00",
    "enabled": true
  },
  "message": "Dry run — guest account 'alice@example.com' would be created with role_id=7, valid for 8 hour(s). No request was sent to ClearPass."
}
```

---

## Step 3 — Confirm and create

After reviewing the payload:

**You say:**
> "Looks good. Create the account for real."

**Tool called:**
```
create_guest_account(
    username="alice@example.com",
    role_id=7,
    valid_hours=8,
    dry_run=False
)
```

**Expected output:**
```json
{
  "id": 9876,
  "username": "alice@example.com",
  "role_id": 7,
  "expire_time": "2024-01-15 18:00:00",
  "password": "xK9mP2rT",
  "enabled": true
}
```

---

## Step 4 — (Optional) Send a receipt

**You say:**
> "Send the guest receipt to alice@example.com."

**Tool called:**
```
clearpass_post(
    path="/guest/9876/sendreceipt/smtp",
    body={"email": "alice@example.com"}
)
```

---

## Using the Guided Prompt

Use the `onboard_guest_account` prompt to get a step-by-step guide automatically:

> **Prompt:** `onboard_guest_account`
> **Parameters:** `visitor_name="Alice Smith"`, `contact_email="alice@example.com"`, `valid_hours=8`
