#!/usr/bin/env python3
"""
Boot script — starts two processes inside the Docker container:
  1. The FastAPI webhook server (receives inbound SMS from Twilio)
  2. The MCP server (serves tools to the AI agent)

Both share the same SQLite inbox.db file.
"""

import subprocess
import sys
import os

def main():
    webhook_port = os.environ.get("WEBHOOK_PORT", "8080")

    # Start webhook server as a background subprocess
    webhook_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "twilio_sms_mcp.webhook:app",
            "--host", "0.0.0.0",
            "--port", webhook_port,
            "--log-level", "info",
        ],
        env=os.environ.copy(),
    )

    print(f"[boot] Webhook server started on port {webhook_port} (PID {webhook_proc.pid})", flush=True)
    print("[boot] Starting MCP server on stdio...", flush=True)

    # Run MCP server on stdio (foreground — this is what the agent connects to)
    try:
        from twilio_sms_mcp.server import main as mcp_main
        mcp_main()
    finally:
        webhook_proc.terminate()


if __name__ == "__main__":
    main()
