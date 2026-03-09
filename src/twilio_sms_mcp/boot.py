"""Launcher for the webhook HTTP server and the MCP stdio server."""

from __future__ import annotations

import threading

import uvicorn

from .config import get_settings
from .store import init_db
from .webhook import app


def main() -> None:
    settings = get_settings()
    init_db()

    webhook_server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=settings.webhook_port,
            log_level=settings.log_level.lower(),
            access_log=False,
        )
    )
    threading.Thread(target=webhook_server.run, name="twilio-webhook", daemon=True).start()

    from .server import main as run_mcp_server

    run_mcp_server()


if __name__ == "__main__":
    main()
