# Twilio SMS MCP Server

Production-grade [Model Context Protocol](https://modelcontextprotocol.io/) server for Twilio SMS.  
Send, receive, schedule, redact, and inspect SMS/MMS conversations through any MCP-compatible client — VS Code Copilot, Codex CLI, Claude Desktop, and more.

---

## Features

### Tools (16)

| Tool | Description |
|---|---|
| `sms_send` | Send a single SMS or MMS |
| `sms_send_bulk` | Send the same message to up to 100 recipients with bounded concurrency |
| `sms_schedule` | Schedule a message for future delivery (requires Messaging Service) |
| `sms_cancel_scheduled` | Cancel a scheduled message |
| `sms_list_sent` | List outbound messages with optional filters |
| `sms_get_message` | Fetch one message by SID, enriched with delivery status |
| `sms_delete_message` | Delete a message record from Twilio |
| `sms_redact_message` | **NEW** — Redact message body for GDPR / privacy compliance |
| `sms_list_inbox` | List inbound webhook-captured messages |
| `sms_get_conversation` | Merge local inbox with Twilio history for a full thread |
| `sms_mark_read` | Mark inbox messages as read |
| `sms_list_numbers` | List Twilio phone numbers on the account |
| `sms_lookup_number` | Carrier and line-type intelligence lookup |
| `sms_format_number` | **NEW** — Validate any phone string and return E.164 + national format |
| `sms_usage_stats` | **NEW** — Daily SMS/MMS usage and cost analytics |
| `sms_account_info` | Account balance, status, and metadata |

### Resources

| URI | Description |
|---|---|
| `twilio://account` | High-level account summary (SID, sender, version) |

### Prompts

| Prompt | Description |
|---|---|
| `draft_sms` | AI-assisted SMS drafting given a recipient and topic |
| `summarize_conversation` | Summarize all messages exchanged with a number |

### Production Hardening

- **Retry with exponential backoff** on transient Twilio API errors (429, 5xx, network failures)
- **Webhook rate limiting** — in-memory per-IP throttle (120 req/min)
- **Structured logging** — timestamped, leveled, consistent format on stderr
- **Input validation** — Pydantic v2 strict schemas with E.164, SID pattern enforcement
- **Webhook signature verification** — Twilio `RequestValidator` on all inbound hooks
- **Health and readiness endpoints** — `/healthz`, `/readyz` for orchestrators
- **Docker multi-stage build** with non-root user, health checks, persistent volume
- **`py.typed`** marker for downstream type-checker compatibility

## Requirements

- Python 3.11+
- A Twilio account and a Twilio phone number
- For scheduled messages: a Twilio Messaging Service SID
- For inbound messages: a publicly reachable webhook URL
- Docker Desktop (optional, for container deployment)

## Quick Start

```bash
cp env.example .env          # fill in your Twilio credentials; for local runs set TWILIO_DB_PATH=inbox.db
pip install -e ".[dev]"
pytest                        # run the test suite
python -m twilio_sms_mcp.boot # start MCP + webhook server
```

## Client Configuration

### VS Code (GitHub Copilot / Copilot Chat)

Add to your VS Code `settings.json` or `.vscode/mcp.json`:

```json
{
  "mcp": {
    "servers": {
      "twilio-sms": {
        "command": "python",
        "args": ["-m", "twilio_sms_mcp.boot"],
        "env": {
          "TWILIO_ACCOUNT_SID": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
          "TWILIO_AUTH_TOKEN": "your_auth_token_here",
          "TWILIO_FROM_NUMBER": "+12025551234"
        }
      }
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "twilio-sms": {
      "command": "python",
      "args": ["-m", "twilio_sms_mcp.boot"],
      "env": {
        "TWILIO_ACCOUNT_SID": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "TWILIO_AUTH_TOKEN": "your_auth_token_here",
        "TWILIO_FROM_NUMBER": "+12025551234"
      }
    }
  }
}
```

### Codex CLI

```bash
codex mcp add twilio-sms \
  -- docker run --rm -i \
  --env-file .env \
  -p 8080:8080 \
  -v twilio_sms_data:/data \
  twilio-sms-mcp
```

Verify:

```bash
codex mcp get twilio-sms
codex mcp list
```

## Docker

Build and run:

```bash
docker build -t twilio-sms-mcp .
docker run --rm -i \
  --env-file .env \
  -p 8080:8080 \
  -v twilio_sms_data:/data \
  twilio-sms-mcp
```

Or use Docker Compose:

```bash
docker compose up -d
```

## Webhook Notes

- Configure Twilio to POST to `<your-host>/webhook/sms` for inbound messages.
- Configure Twilio to POST to `<your-host>/webhook/status` for delivery callbacks.
- Set `TWILIO_PUBLIC_WEBHOOK_BASE_URL` when behind a reverse proxy or ngrok.
- Keep `TWILIO_VALIDATE_WEBHOOK_SIGNATURES=true` in production.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TWILIO_ACCOUNT_SID` | Yes | — | Twilio Account SID (starts with `AC`) |
| `TWILIO_AUTH_TOKEN` | Yes | — | Twilio Auth Token |
| `TWILIO_FROM_NUMBER` | Yes | — | Default sender in E.164 format |
| `TWILIO_MESSAGING_SERVICE_SID` | No | — | Required for `sms_schedule` |
| `TWILIO_WEBHOOK_AUTH_TOKEN` | No | — | Override for webhook signature validation |
| `TWILIO_PUBLIC_WEBHOOK_BASE_URL` | No | — | Public URL for webhook signature validation |
| `TWILIO_VALIDATE_WEBHOOK_SIGNATURES` | No | `true` | Disable only for local debugging |
| `TWILIO_BULK_SEND_CONCURRENCY` | No | `10` | Max parallel sends for `sms_send_bulk` |
| `TWILIO_LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `TWILIO_DB_PATH` | No | `inbox.db` | SQLite database location |
| `WEBHOOK_PORT` | No | `8080` | Webhook HTTP server port |
| `TWILIO_API_RETRY_ATTEMPTS` | No | `3` | Retry count for transient API errors |
| `TWILIO_API_RETRY_DELAY` | No | `1.0` | Base delay in seconds between retries |
| `MCP_TRANSPORT` | No | `stdio` | MCP transport: `stdio`, `sse`, or `http` |
| `MCP_HOST` | No | `0.0.0.0` | Bind address for SSE/HTTP transport |
| `MCP_PORT` | No | `8000` | Port for SSE/HTTP transport |

## Testing

```bash
pip install -e ".[dev]"
pytest -v
```

## Production Checklist

- [ ] Use HTTPS for webhook delivery
- [ ] Set `TWILIO_VALIDATE_WEBHOOK_SIGNATURES=true`
- [ ] Use a Messaging Service SID for sender pooling and scheduled messages
- [ ] Persist `/data` volume so inbox state survives restarts
- [ ] Never commit `.env` — it is excluded via `.gitignore` and `.dockerignore`
- [ ] Monitor `/healthz` and `/readyz` from your orchestrator
- [ ] Set `TWILIO_LOG_LEVEL=WARNING` in high-traffic environments

## License

[MIT](LICENSE)
