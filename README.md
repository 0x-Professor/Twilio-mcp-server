# Twilio SMS MCP Server

Twilio SMS MCP server for sending, receiving, scheduling, and inspecting SMS or MMS conversations through any MCP-compatible client.

## Features

- `sms_send`: send a single SMS or MMS
- `sms_send_bulk`: send the same message to multiple recipients with bounded concurrency
- `sms_schedule`: schedule a message for future delivery through a Twilio Messaging Service
- `sms_cancel_scheduled`: cancel a scheduled message
- `sms_list_sent`: inspect outbound messages
- `sms_get_message`: fetch one message by SID
- `sms_delete_message`: delete a message record from Twilio
- `sms_list_inbox`: inspect inbound webhook-captured messages
- `sms_get_conversation`: combine local inbox state with Twilio message history
- `sms_mark_read`: mark inbox messages as read
- `sms_list_numbers`: list Twilio phone numbers on the account
- `sms_lookup_number`: inspect carrier and line-type information
- `sms_account_info`: fetch account balance and status

## Requirements

- Python 3.11+
- A Twilio account and a Twilio phone number
- For scheduled messages: a Twilio Messaging Service SID
- For inbound messages: a publicly reachable webhook URL
- Docker Desktop, if you want the container deployment path

## Local Setup

```powershell
Copy-Item env.example .env
python -m pip install -e .[dev]
pytest
```

Fill in `.env` with your Twilio credentials before running the real server.

## Run Locally

Start the MCP server and the webhook sidecar in one process:

```powershell
python -m twilio_sms_mcp.boot
```

The webhook server listens on `http://127.0.0.1:8080` by default.

## Docker

Build the image:

```powershell
docker build -t twilio-sms-mcp .
```

Run it with your local `.env` file:

```powershell
docker run --rm -i `
  --env-file .env `
  -p 8080:8080 `
  -v twilio_sms_data:/data `
  twilio-sms-mcp
```

## Webhook Notes

- Configure Twilio to call `POST /webhook/sms` for inbound messages.
- Configure Twilio to call `POST /webhook/status` for delivery callbacks.
- Set `TWILIO_PUBLIC_WEBHOOK_BASE_URL` when the service runs behind ngrok, a reverse proxy, or a load balancer and the internal request URL differs from the public one.
- Leave `TWILIO_VALIDATE_WEBHOOK_SIGNATURES=true` in production.

## Codex Registration

This project supports a stable Codex registration path without copying secrets into Codex config. The Docker-backed registration below is the same flow that was validated locally.

```powershell
codex mcp add twilio-sms `
  -- docker run --rm -i `
  --env-file U:\Twilio-mcp-server\.env `
  -p 8080:8080 `
  -v twilio_sms_data:/data `
  twilio-sms-mcp
```

Verify it:

```powershell
codex mcp get twilio-sms
codex mcp list
```

## Production Notes

- Do not commit `.env`; it is ignored by `.gitignore` and excluded from Docker build context.
- Use HTTPS for webhook delivery.
- Prefer `TWILIO_MESSAGING_SERVICE_SID` for scheduled messages and sender pooling.
- Persist `/data` so inbox state and delivery status survive restarts.
- Keep webhook signature validation enabled unless you are diagnosing a local URL-mismatch problem.
