# Twilio SMS MCP Server

Production-grade MCP server for Twilio Programmable Messaging.
Lets any MCP-compatible AI agent (Claude, OpenAI, etc.) send, receive,
schedule, and manage SMS/MMS messages via your Twilio number — 100% ToS-compliant.

---

## Tools

| Tool | What it does |
|------|-------------|
| `sms_send` | Send a single SMS or MMS |
| `sms_send_bulk` | Send to multiple recipients concurrently |
| `sms_schedule` | Schedule a message for future delivery |
| `sms_cancel_scheduled` | Cancel a scheduled message |
| `sms_list_sent` | List outbound messages with filters |
| `sms_get_message` | Fetch one message by SID |
| `sms_delete_message` | Delete a message record |
| `sms_list_inbox` | List received messages (from webhook) |
| `sms_get_conversation` | Full conversation thread with a number |
| `sms_mark_read` | Mark messages as read |
| `sms_list_numbers` | List your Twilio phone numbers |
| `sms_lookup_number` | Carrier + line-type lookup |
| `sms_account_info` | Account balance and status |

---

## Architecture

```
AI Agent (Claude / any MCP client)
        │  stdio (MCP protocol)
        ▼
┌─────────────────────────────┐
│   Docker Container          │
│                             │
│   MCP Server (FastMCP)      │ ◄── agent reads/writes SMS here
│        │                    │
│        ▼                    │
│   SQLite inbox.db           │ ◄── shared state
│        ▲                    │
│        │                    │
│   Webhook Server            │
│   FastAPI :8080             │ ◄── Twilio POSTs inbound SMS here
└─────────────────────────────┘
        ▲
        │  HTTPS webhook
   Twilio Cloud
```

---

## Prerequisites

- [Twilio account](https://www.twilio.com/try-twilio) (free trial works)
- A Twilio phone number (buy one in Console for ~$1/month)
- Docker + Docker Compose
- For receiving SMS: a public URL (use [ngrok](https://ngrok.com) for local dev)

---

## Setup — 5 Steps

### 1. Clone and configure

```bash
git clone <your-repo>
cd twilio-sms-mcp
cp env.example .env
```

Edit `.env` and fill in your credentials from [console.twilio.com](https://console.twilio.com):
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+12015551234
```

### 2. Build and start

```bash
docker compose up --build
```

This starts:
- **MCP server** on stdio (the agent connects here)
- **Webhook server** on `http://localhost:8080`

### 3. Expose webhook for receiving SMS (local dev)

```bash
# In a separate terminal
ngrok http 8080
# Copy the https URL, e.g. https://abc123.ngrok.io
```

### 4. Configure Twilio webhooks

Go to [console.twilio.com → Phone Numbers → Manage → Active Numbers](https://console.twilio.com/us1/develop/phone-numbers/manage/active-numbers)
→ click your number → Messaging Configuration:

| Field | Value |
|-------|-------|
| **A message comes in** → URL | `https://abc123.ngrok.io/webhook/sms` |
| **A message comes in** → Method | `HTTP POST` |
| **Status Callback URL** | `https://abc123.ngrok.io/webhook/status` |

### 5. Connect Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "twilio-sms": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--env-file", "/absolute/path/to/your/.env",
        "-v", "sms_data:/data",
        "twilio-sms-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop. You'll see the SMS tools available.

---

## Example Agent Conversations

**Send a message:**
> "Send an SMS to +12025551234 saying the meeting is at 3pm"

**Check inbox:**
> "Do I have any unread messages?"

**Read a conversation:**
> "Show me my conversation with +12025551234"

**Schedule a reminder:**
> "Schedule an SMS to +12025551234 for tomorrow at 9am saying 'Don't forget the deadline today'"

**Send bulk:**
> "Text everyone on this list: [+1202..., +1415..., +1212...] that the event is cancelled"

---

## Production Deployment

For production (not just local dev):

1. **Deploy to a server** with a static IP or domain — no ngrok needed
2. **Use HTTPS** — Twilio requires HTTPS for webhooks in production
3. **Set `TWILIO_WEBHOOK_AUTH_TOKEN`** — enables Twilio signature validation so only real Twilio requests hit your webhook
4. **Use a Messaging Service** (`TWILIO_MESSAGING_SERVICE_SID`) for scheduled messages and better deliverability
5. **Mount `/data` on persistent storage** so the inbox survives container restarts

---

## Security Notes

- Never commit `.env` to git — add it to `.gitignore`
- The container runs as a non-root user (`appuser`)
- Twilio signature validation is enabled when `TWILIO_WEBHOOK_AUTH_TOKEN` is set
- The MCP server uses zero-trust: only the 13 declared tools are exposed

---

## License

MIT
